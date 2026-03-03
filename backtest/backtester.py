"""
历史回测引擎

基于 baostock 历史数据，模拟交易主循环，评估策略在过去 N 天的表现。
"""
import sys
import random
from datetime import datetime, timedelta, time as dtime
from typing import Optional
from unittest.mock import patch
from loguru import logger

import pandas as pd

from config.settings import (
    ETF_UNIVERSE, ACTIVE_ETFS, INITIAL_CAPITAL,
    TAKE_PROFIT_PCT, STOP_LOSS_PCT, TRAILING_STOP_PCT,
    MARKET_OPEN, MARKET_CLOSE,
)
from strategy.signal import MarketSnapshot, SignalType, OrderSide, TradeOrder
from strategy.futures_etf_arb import FuturesETFArbStrategy
from risk.position_manager import PositionManager
from risk.risk_manager import RiskManager
from trader.mock_trader import MockTrader
from monitor.logger import setup_logger
from monitor.trade_store import TradeStore


class Backtester:
    """历史回测引擎"""

    def __init__(
        self,
        etf_codes: Optional[list[str]] = None,
        initial_capital: float = INITIAL_CAPITAL,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days: int = 30,
    ):
        self._etf_codes = etf_codes or ACTIVE_ETFS[:3]  # 默认前 3 个标的
        self._initial_capital = initial_capital

        # 日期范围
        if end_date:
            self._end_date = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            self._end_date = datetime.now() - timedelta(days=1)

        if start_date:
            self._start_date = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            self._start_date = self._end_date - timedelta(days=days)

        # 构建策略映射 (与 TradingEngine 保持一致)
        self._strategy_map = {}
        shared_arb = FuturesETFArbStrategy()
        
        exclusive_codes = ["513310", "513880"]
        for code in self._etf_codes:
            if code in exclusive_codes:
                self._strategy_map[code] = FuturesETFArbStrategy()
            else:
                # 回测中暂不混合 ML/VWAP 以保持纯粹，或保持与 main 一致
                self._strategy_map[code] = shared_arb 
        self._position_manager = PositionManager(initial_capital)
        self._risk_manager = RiskManager(self._position_manager)
        self._trader = MockTrader(self._position_manager)

        # 持久化
        self._trade_store = TradeStore()
        self._position_manager.set_mode("backtest")
        self._position_manager.set_store(self._trade_store)

        # 结果
        self._daily_pnl: list[dict] = []

    def run(self) -> dict:
        """运行回测"""
        logger.info("=" * 60)
        logger.info("回测引擎启动")
        logger.info(f"回测标的: {', '.join(self._etf_codes)}")
        logger.info(f"回测区间: {self._start_date.strftime('%Y-%m-%d')} ~ {self._end_date.strftime('%Y-%m-%d')}")
        logger.info(f"初始资金: {self._initial_capital:,.2f}")
        logger.info("=" * 60)

        self._trader.connect()

        # 获取历史数据
        hist_data = self._load_historical_data()
        if not hist_data:
            logger.error("无法加载历史数据，回测终止")
            return {}

        # 获取交易日列表
        all_dates = set()
        for code, df in hist_data.items():
            all_dates.update(df["date"].dt.date.unique())
        trade_dates = sorted(all_dates)

        logger.info(f"有效交易日数: {len(trade_dates)}")

        for trade_date in trade_dates:
            for strat in self._strategy_map.values():
                strat.reset()
            self._position_manager.reset_daily()

            day_start_assets = self._position_manager.total_assets

            for code in self._etf_codes:
                df = hist_data.get(code)
                if df is None:
                    continue

                day_rows = df[df["date"].dt.date == trade_date]
                if day_rows.empty:
                    continue

                row = day_rows.iloc[0]

                # 构造模拟行情快照
                etf_price = float(row.get("收盘", 0) or 0)
                open_price = float(row.get("开盘", 0) or 0)
                high = float(row.get("最高", 0) or 0)
                low = float(row.get("最低", 0) or 0)
                volume = float(row.get("成交量", 0) or 0)

                if etf_price <= 0:
                    continue

                # 模拟 IOPV：增加折溢价的覆盖面
                # 策略阈值是 0.3%，我们模拟 -0.5% 到 0.5% 的范围
                premium_rate = random.uniform(-0.006, 0.006)
                iopv = etf_price / (1 + premium_rate)

                # 模拟期货动量（随机模拟，确保有触发阈值 0.1% 的可能）
                momentum = random.uniform(-0.005, 0.005)

                # 回测使用模拟的交易时段时间（上午 10:00），避免真实时间干扰
                sim_time = datetime.combine(trade_date, dtime(10, 0))

                snapshot = MarketSnapshot(
                    etf_code=code,
                    etf_name=ETF_UNIVERSE.get(code, {}).get("name", code),
                    timestamp=sim_time,
                    etf_price=etf_price,
                    etf_open=open_price,
                    etf_high=high,
                    etf_low=low,
                    etf_volume=volume,
                    iopv=iopv,
                    futures_price=0,
                    exchange_rate=1.0,
                    premium_rate=premium_rate,
                    futures_momentum=momentum,
                )

                # 获取该标的的专属策略
                strategy = self._strategy_map.get(code)
                if not strategy: continue

                # 使用 mock 覆盖 datetime.now() 和 time.time()，让风控/策略中的时间检查
                # 认为当前是交易时段内，且冷却时间计算正确
                with patch('risk.risk_manager.datetime') as mock_dt:
                    mock_dt.now.return_value = sim_time
                    mock_dt.combine.side_effect = datetime.combine
                    mock_dt.fromisoformat.side_effect = datetime.fromisoformat

                    signal = strategy.evaluate(snapshot)

                    # 检查是否有退出信号
                    price_map = {code: etf_price}
                    self._position_manager.update_prices(price_map)
                    exit_orders = self._risk_manager.check_exit_rules({code: snapshot}, {code: signal}, now=sim_time)
                    for order in exit_orders:
                        order.timestamp = sim_time
                        self._trader.execute(order)

                    # 策略信号
                    if signal.is_actionable:
                        if signal.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
                            allowed, _ = self._risk_manager.validate_entry(signal)
                            if allowed:
                                qty = self._risk_manager.calc_order_quantity(signal)
                                if qty > 0:
                                    order = TradeOrder(
                                        etf_code=code, etf_name=snapshot.etf_name,
                                        side=OrderSide.BUY, price=etf_price,
                                        quantity=qty, reason=signal.reason,
                                    )
                                    self._trader.execute(order)

                        elif signal.signal_type in (SignalType.SELL, SignalType.STRONG_SELL):
                            if self._position_manager.has_position(code):
                                pos = self._position_manager.get_position(code)
                                order = TradeOrder(
                                    etf_code=code, etf_name=snapshot.etf_name,
                                    side=OrderSide.SELL, price=etf_price,
                                    quantity=pos.quantity, reason=signal.reason,
                                )
                                self._trader.execute(order)

            # 日终清仓（T+0 不留隔夜仓）
            for code in list(self._position_manager.positions.keys()):
                pos = self._position_manager.get_position(code)
                if pos and pos.quantity > 0:
                    self._position_manager.close_position(code, pos.current_price)

            day_end_assets = self._position_manager.total_assets
            day_pnl = day_end_assets - day_start_assets

            self._daily_pnl.append({
                "date": trade_date,
                "assets": day_end_assets,
                "pnl": day_pnl,
                "pnl_pct": day_pnl / day_start_assets * 100 if day_start_assets > 0 else 0,
            })

            # 保存每日汇总到数据库
            self._position_manager.save_daily_summary(trade_date=trade_date)

        # 打印结果
        return self._print_results()

    def _load_historical_data(self) -> dict[str, pd.DataFrame]:
        """加载历史 ETF 日线数据（使用 baostock）"""
        result = {}
        try:
            import baostock as bs

            lg = bs.login()
            if lg.error_code != '0':
                logger.error(f"baostock 登录失败: {lg.error_msg}")
                return result

            for code in self._etf_codes:
                try:
                    # 根据 ETF_UNIVERSE 中的 exchange 字段构造 baostock 代码
                    exchange = ETF_UNIVERSE.get(code, {}).get("exchange", "SH")
                    bs_code = f"{exchange.lower()}.{code}"

                    rs = bs.query_history_k_data_plus(
                        bs_code,
                        "date,open,high,low,close,preclose,volume,amount",
                        start_date=self._start_date.strftime("%Y-%m-%d"),
                        end_date=self._end_date.strftime("%Y-%m-%d"),
                        frequency="d",
                        adjustflag="2",  # 前复权
                    )

                    rows = []
                    while (rs.error_code == '0') and rs.next():
                        rows.append(rs.get_row_data())

                    if rows:
                        df = pd.DataFrame(rows, columns=rs.fields)
                        # 统一字段名，兼容回测逻辑
                        df = df.rename(columns={
                            "open": "开盘", "high": "最高", "low": "最低",
                            "close": "收盘", "preclose": "前收盘",
                            "volume": "成交量",
                        })
                        df["date"] = pd.to_datetime(df["date"])
                        # 转换数值类型
                        for col in ["开盘", "最高", "最低", "收盘", "前收盘", "成交量"]:
                            df[col] = pd.to_numeric(df[col], errors="coerce")
                        result[code] = df
                        logger.info(f"[{code}] 加载 {len(df)} 条历史数据")
                    else:
                        logger.warning(f"[{code}] baostock 返回空数据 (code={rs.error_code}, msg={rs.error_msg})")

                except Exception as e:
                    logger.warning(f"[{code}] 历史数据加载失败: {e}")

            bs.logout()

        except ImportError:
            logger.error("baostock 未安装，请运行: pip install baostock")

        return result

    def _print_results(self) -> dict:
        """打印回测结果"""
        if not self._daily_pnl:
            logger.warning("无回测数据")
            return {}

        total_pnl = self._daily_pnl[-1]["assets"] - self._initial_capital
        total_pnl_pct = total_pnl / self._initial_capital * 100

        win_days = sum(1 for d in self._daily_pnl if d["pnl"] > 0)
        lose_days = sum(1 for d in self._daily_pnl if d["pnl"] < 0)
        flat_days = sum(1 for d in self._daily_pnl if d["pnl"] == 0)

        max_dd = 0
        peak = self._initial_capital
        for d in self._daily_pnl:
            peak = max(peak, d["assets"])
            dd = (peak - d["assets"]) / peak
            max_dd = max(max_dd, dd)

        trades = self._position_manager.get_trade_history()

        logger.info("=" * 60)
        logger.info("回测结果")
        logger.info("=" * 60)
        logger.info(f"回测区间: {self._daily_pnl[0]['date']} ~ {self._daily_pnl[-1]['date']}")
        logger.info(f"交易日数: {len(self._daily_pnl)}")
        logger.info(f"初始资金: {self._initial_capital:,.2f}")
        logger.info(f"最终资产: {self._daily_pnl[-1]['assets']:,.2f}")
        logger.info(f"总收益:   {total_pnl:+,.2f} ({total_pnl_pct:+.2f}%)")
        logger.info(f"胜率:     {win_days}胜/{lose_days}负/{flat_days}平 ({win_days/(win_days+lose_days)*100:.1f}%)" if (win_days + lose_days) > 0 else "N/A")
        logger.info(f"最大回撤: {max_dd * 100:.2f}%")
        logger.info(f"总交易:   {len(trades)} 笔")
        logger.info("=" * 60)

        return {
            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl_pct,
            "win_days": win_days,
            "lose_days": lose_days,
            "max_drawdown": max_dd,
            "total_trades": len(trades),
            "daily_pnl": self._daily_pnl,
        }


def run_backtest(
    etf_codes: Optional[list[str]] = None,
    initial_capital: float = INITIAL_CAPITAL,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    days: int = 30,
):
    """回测入口函数"""
    setup_logger()
    bt = Backtester(
        etf_codes=etf_codes,
        initial_capital=initial_capital,
        start_date=start_date,
        end_date=end_date,
        days=days,
    )
    return bt.run()
