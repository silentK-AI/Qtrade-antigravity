"""
今日日内回放脚本

逻辑：
1. 获取活跃标的今日分时数据 (ETF + 关联指数)
2. 模拟 TradingEngine 的循环逻辑，但使用历史数据点
3. 验证新风控逻辑（60s全局冷却）和新策略逻辑（信号确认）
"""
import sys
import time
import pandas as pd
from datetime import datetime
from loguru import logger

# 路径修复
sys.path.append('.')

from config.settings import ACTIVE_ETFS, ETF_UNIVERSE
from data.market_data import MarketDataService
from strategy.composite_strategy import CompositeStrategy
from strategy.futures_etf_arb import FuturesETFArbStrategy
from strategy.ml_price_strategy import MLPriceStrategy
from strategy.ml_predictor import MLPredictor
from strategy.signal import MarketSnapshot, SignalType, OrderSide, TradeOrder
from risk.position_manager import PositionManager
from risk.risk_manager import RiskManager
from trader.mock_trader import MockTrader

def fetch_intraday_data(code: str, target_date: str):
    """从新浪获取指定日期的 5 分钟数据用于回放"""
    import requests
    import json
    try:
        exchange = ETF_UNIVERSE[code].get("exchange", "SH").lower()
        symbol = f"{exchange}{code}"
        
        # 获取 5 分钟线，增加数据长度以覆盖历史日期
        url = (
            f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            f"CN_MarketData.getKLineData?symbol={symbol}&scale=5&ma=no&datalen=2000"
        )
        
        s = requests.Session()
        s.trust_env = False
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn"
        }
        
        resp = s.get(url, headers=headers, timeout=10)
        text = resp.text.strip()
        if not text or text == "null":
            return None
            
        data_list = json.loads(text)
        if not data_list:
            return None
            
        rows = []
        for item in data_list:
            if item["day"].startswith(target_date):
                rows.append({
                    "time": datetime.strptime(item["day"], "%Y-%m-%d %H:%M:%S"),
                    "open": float(item["open"]),
                    "close": float(item["close"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "volume": float(item["volume"])
                })
        
        if not rows:
            return None
            
        df = pd.DataFrame(rows)
        return df
    except Exception as e:
        logger.error(f"[{code}] 获取分时回放数据失败: {e}")
        return None

def run_replay(etf_codes=None, target_date: str = None):
    etf_codes = etf_codes or ACTIVE_ETFS
    target_date = target_date or datetime.now().strftime("%Y-%m-%d")
    logger.info(f"开始回放: 日期 {target_date} | 标的 {etf_codes}")
    
    # 初始化组件
    from monitor.trade_store import TradeStore
    store = TradeStore()
    
    pm = PositionManager(initial_capital=10000) # 对齐最新设置
    pm.set_mode("backtest") 
    pm.set_store(store)
    
    rm = RiskManager(pm)
    trader = MockTrader(pm)
    
    # 确保 pm 的当日初始资产被记录
    pm.reset_daily()
    
    predictor = MLPredictor()
    predictor.load_all_models(etf_codes)
    
    arb = FuturesETFArbStrategy()
    from strategy.vwap_reversion_strategy import VWAPReversionStrategy
    vwap = VWAPReversionStrategy()
    ml_strat = MLPriceStrategy(predictor)
    strategy = CompositeStrategy([arb, vwap, ml_strat])
    
    trader.connect()
    
    # 加载数据
    data_map = {}
    for code in etf_codes:
        df = fetch_intraday_data(code, target_date)
        if df is not None and not df.empty:
            data_map[code] = df
            logger.info(f"[{code}] 加载了 {len(df)} 条分钟数据")
        else:
            logger.warning(f"[{code}] {target_date} 无分时数据")

    if not data_map:
        return

    all_times = sorted(set().union(*(df["time"] for df in data_map.values())))
    sim_step = 0
    save_date_str = target_date or datetime.now().strftime("%Y-%m-%d")
    
    for current_time in all_times:
        sim_step += 1
        
        # 1) 获取并处理行情
        current_snapshots = {}
        for code in etf_codes:
            df = data_map.get(code)
            if df is None: continue
            
            row = df[df["time"] == current_time]
            if row.empty: continue
            row = row.iloc[0]
            
            price = row["close"]
            # 模拟折价（买入机会）
            is_buy_window = (sim_step // 10) % 2 == 0
            premium = -0.005 if is_buy_window else 0.005
            momentum = 0.002 if is_buy_window else -0.002
            
            snapshot = MarketSnapshot(
                etf_code=code, etf_name=ETF_UNIVERSE[code]["name"], timestamp=current_time,
                etf_price=price, etf_open=row["open"], etf_high=row["high"], etf_low=row["low"],
                etf_volume=row["volume"], etf_amount=row["volume"] * price,
                iopv=price / (1 + premium), futures_price=0, exchange_rate=1.0,
                premium_rate=premium, futures_momentum=momentum,
            )
            current_snapshots[code] = snapshot
            
            store.record_snapshot(
                mode="backtest", etf_code=code, price=snapshot.etf_price,
                iopv=snapshot.iopv, momentum=snapshot.futures_momentum,
                timestamp=current_time.isoformat()
            )

        # 2) 策略信号预读（用于 Alpha 衰减判断）
        signals_map = {}
        for code, snapshot in current_snapshots.items():
            signal = strategy.evaluate(snapshot)
            signals_map[code] = signal

        # 3) 风控检查 - 退出规则（含科学因子评价）
        exit_orders = rm.check_exit_rules(current_snapshots, signals_map, now=current_time)
        for order in exit_orders:
            order.timestamp = current_time 
            trader.execute(order)

        # 4) 生成并执行交易入场指令
        for code, snapshot in current_snapshots.items():
            signal = signals_map.get(code)
            if not signal or not signal.is_actionable:
                continue

            if signal.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
                allowed, reason = rm.validate_entry(signal, now=current_time)
                if allowed:
                    qty = rm.calc_order_quantity(signal)
                    if qty <= 0: continue
                    order = TradeOrder(
                        etf_code=code, etf_name=snapshot.etf_name,
                        side=OrderSide.BUY,
                        price=snapshot.etf_price, quantity=qty, reason=signal.reason,
                        timestamp=current_time
                    )
                    trader.execute(order)

    logger.info("回放完成")
    final_pm = pm.get_summary()
    logger.info(f"最终资产: {pm.total_assets:.2f}")
    
    # 保存当日汇总
    from datetime import date
    pm.save_daily_summary(trade_date=date.fromisoformat(save_date_str))
    logger.info(f"已保存回测当日 ({save_date_str}) 汇总")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="今日或历史日内数据回放")
    parser.add_argument("--date", type=str, help="回放日期 (格式: YYYY-MM-DD), 默认为今日")
    args = parser.parse_args()
    
    run_replay(target_date=args.date)
