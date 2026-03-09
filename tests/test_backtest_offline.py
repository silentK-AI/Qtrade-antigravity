"""
离线回测测试：使用合成数据验证策略逻辑能正常产生交易。
不需要网络连接。
"""
import sys
import random
from datetime import datetime, timedelta, time as dtime
from unittest.mock import patch

import pandas as pd
from loguru import logger

# 设置日志到 stderr
logger.remove()
logger.add(sys.stderr, level="INFO")

from config.etf_settings import ETF_UNIVERSE, ACTIVE_ETFS, INITIAL_CAPITAL
from strategy.signal import MarketSnapshot, SignalType, OrderSide, TradeOrder
from strategy.futures_etf_arb import FuturesETFArbStrategy
from risk.position_manager import PositionManager
from risk.risk_manager import RiskManager
from trader.mock_trader import MockTrader


def generate_synthetic_data(code: str, days: int = 10) -> pd.DataFrame:
    """生成合成 ETF 日线数据"""
    base_price = random.uniform(1.0, 5.0)
    rows = []
    end_date = datetime(2026, 2, 20)

    prev_close = base_price
    for i in range(days):
        trade_date = end_date - timedelta(days=days - 1 - i)
        # 跳过周末
        if trade_date.weekday() >= 5:
            continue

        # 模拟涨跌
        change_pct = random.uniform(-0.03, 0.03)
        close = prev_close * (1 + change_pct)
        open_p = prev_close * (1 + random.uniform(-0.01, 0.01))
        high = max(open_p, close) * (1 + random.uniform(0, 0.01))
        low = min(open_p, close) * (1 - random.uniform(0, 0.01))
        volume = random.randint(100000, 10000000)

        rows.append({
            "date": trade_date,
            "开盘": round(open_p, 4),
            "最高": round(high, 4),
            "最低": round(low, 4),
            "收盘": round(close, 4),
            "前收盘": round(prev_close, 4),
            "成交量": volume,
        })
        prev_close = close

    return pd.DataFrame(rows)


def test_strategy_generates_trades():
    """测试策略在合成数据上能产生交易"""
    random.seed(42)

    code = "159941"
    strategy = FuturesETFArbStrategy()
    position_manager = PositionManager(INITIAL_CAPITAL)
    risk_manager = RiskManager(position_manager)
    trader = MockTrader(position_manager)
    trader.connect()

    df = generate_synthetic_data(code, days=30)
    print(f"\n合成数据: {len(df)} 条记录")
    print(df[["date", "开盘", "收盘", "前收盘"]].to_string(index=False))

    total_signals = 0
    total_trades = 0

    for _, row in df.iterrows():
        strategy.reset()
        position_manager.reset_daily()

        etf_price = float(row["收盘"])
        open_price = float(row["开盘"])
        high = float(row["最高"])
        low = float(row["最低"])
        volume = float(row["成交量"])
        prev_close = float(row["前收盘"])

        # IOPV 模拟（和修复后的 backtester 一样）
        price_range = high - low if high > low else etf_price * 0.005
        iopv_offset = price_range * random.uniform(-0.6, 0.6)
        iopv = etf_price + iopv_offset
        if iopv <= 0:
            iopv = etf_price

        momentum = (etf_price - prev_close) / prev_close if prev_close > 0 else 0
        premium_rate = (etf_price - iopv) / iopv if iopv > 0 else 0

        trade_date = row["date"]
        sim_time = datetime.combine(trade_date.date() if isinstance(trade_date, datetime) else trade_date, dtime(10, 0))

        snapshot = MarketSnapshot(
            etf_code=code,
            etf_name="纳指ETF",
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

        # Mock datetime.now()
        with patch('risk.risk_manager.datetime') as mock_dt, \
             patch('strategy.futures_etf_arb.datetime') as mock_dt2:
            mock_dt.now.return_value = sim_time
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            mock_dt2.now.return_value = sim_time
            mock_dt2.side_effect = lambda *a, **kw: datetime(*a, **kw)

            signal = strategy.evaluate(snapshot)

            if signal.is_actionable:
                total_signals += 1
                print(f"\n[{trade_date}] 信号: {signal.signal_type.value} | "
                      f"动量={momentum*100:+.2f}% | 溢价率={premium_rate*100:+.2f}% | "
                      f"强度={signal.strength:.2f}")

                if signal.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
                    allowed, reason = risk_manager.validate_entry(signal)
                    if allowed:
                        qty = risk_manager.calc_order_quantity(signal)
                        if qty > 0:
                            order = TradeOrder(
                                etf_code=code, etf_name="纳指ETF",
                                side=OrderSide.BUY, price=etf_price,
                                quantity=qty, reason=signal.reason,
                            )
                            trader.execute(order)
                            total_trades += 1
                            print(f"  → 买入 {qty} 股 @ {etf_price:.4f}")
                    else:
                        print(f"  → 风控拒绝: {reason}")

    print(f"\n{'='*50}")
    print(f"结果: {total_signals} 个信号, {total_trades} 笔交易")
    print(f"最终资产: {position_manager.total_assets:,.2f}")
    print(f"{'='*50}")

    if total_signals == 0:
        print("\n⚠️ 警告: 没有产生任何信号，策略阈值可能太严格")
    elif total_trades == 0:
        print("\n⚠️ 警告: 有信号但没有成交，风控可能拒绝了所有交易")
    else:
        print("\n✅ 策略逻辑正常，能产生交易")


if __name__ == "__main__":
    test_strategy_generates_trades()
