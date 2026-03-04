"""
ML 策略回测引擎

用法:
  python main.py ml-backtest --etf 159941 --days 30  # 单标的回测
  python main.py ml-backtest --days 30               # 全部标的回测

流程:
  1. 获取 ~200 天历史日线数据 (新浪 API)
  2. 前 150 天训练 XGBoost 模型 (预测次日 high/low ratio)
  3. 后 30 天逐日测试:
     - 预测当日 high/low
     - 合成日内 Tick (~20 点)
     - MLPriceStrategy 逐 Tick 评估 → 买/卖
     - 日终清仓 (T+0)
  4. 输出每标的胜率、盈亏汇总
"""
import sys
import random
from datetime import datetime, timedelta, time as dtime
from typing import Optional
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from loguru import logger

from config.settings import (
    ETF_UNIVERSE, ACTIVE_ETFS, INITIAL_CAPITAL,
    ML_MODEL_DIR,
)
from strategy.ml_predictor import MLPredictor, PricePrediction
from strategy.ml_price_strategy import MLPriceStrategy
from strategy.signal import MarketSnapshot, SignalType, OrderSide, TradeOrder
from risk.position_manager import PositionManager
from risk.risk_manager import RiskManager
from trader.mock_trader import MockTrader


# ======================================================================
#  数据类
# ======================================================================

@dataclass
class DayResult:
    """单日回测结果"""
    date: str
    etf_code: str
    # 预测值
    pred_high: float = 0.0
    pred_low: float = 0.0
    # 实际值
    actual_high: float = 0.0
    actual_low: float = 0.0
    actual_close: float = 0.0
    actual_open: float = 0.0
    # 交易结果
    trades: int = 0
    pnl: float = 0.0
    # 方向预测准确性
    high_error_pct: float = 0.0  # (pred - actual) / actual * 100
    low_error_pct: float = 0.0


@dataclass
class ETFSummary:
    """单个 ETF 的汇总结果"""
    etf_code: str
    etf_name: str
    test_days: int = 0
    win_days: int = 0
    lose_days: int = 0
    flat_days: int = 0
    total_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    avg_high_error: float = 0.0
    avg_low_error: float = 0.0
    daily_results: list = field(default_factory=list)


# ======================================================================
#  回测引擎
# ======================================================================

class MLBacktester:
    """ML 策略回测引擎"""

    def __init__(
        self,
        etf_codes: Optional[list[str]] = None,
        initial_capital: float = INITIAL_CAPITAL,
        test_days: int = 30,
        train_days: int = 150,
    ):
        self._etf_codes = etf_codes or ACTIVE_ETFS
        self._initial_capital = initial_capital
        self._test_days = test_days
        self._train_days = train_days
        self._total_fetch_days = train_days + test_days + 30  # 额外 buffer

    def run(self) -> dict[str, ETFSummary]:
        """运行回测，返回每个 ETF 的汇总结果"""
        logger.info("=" * 60)
        logger.info("ML 策略回测引擎启动")
        logger.info(f"标的: {', '.join(self._etf_codes)}")
        logger.info(f"训练窗口: {self._train_days} 天")
        logger.info(f"测试窗口: {self._test_days} 天")
        logger.info(f"每标的初始资金: {self._initial_capital:,.2f}")
        logger.info("=" * 60)

        results: dict[str, ETFSummary] = {}

        for code in self._etf_codes:
            name = ETF_UNIVERSE.get(code, {}).get("name", code)
            logger.info(f"\n{'=' * 50}")
            logger.info(f"回测 [{code}] {name}")
            logger.info(f"{'=' * 50}")

            summary = self._backtest_single_etf(code)
            if summary:
                results[code] = summary

        # 打印汇总报告
        self._print_summary(results)
        return results

    # ------------------------------------------------------------------
    #  单标的回测
    # ------------------------------------------------------------------

    def _backtest_single_etf(self, etf_code: str) -> Optional[ETFSummary]:
        """对单个 ETF 执行完整回测"""
        name = ETF_UNIVERSE.get(etf_code, {}).get("name", etf_code)

        # 1. 获取历史数据
        hist_df = self._fetch_data(etf_code)
        if hist_df is None or len(hist_df) < self._train_days + 20:
            logger.warning(f"[{etf_code}] 数据不足，跳过")
            return None

        total_rows = len(hist_df)
        # 划分训练集和测试集
        # 测试集 = 最后 test_days 天，训练集 = 之前的数据
        test_start_idx = total_rows - self._test_days
        if test_start_idx < 25:
            logger.warning(f"[{etf_code}] 训练数据不足 (仅 {test_start_idx} 条)，跳过")
            return None

        train_df = hist_df.iloc[:test_start_idx].copy()
        test_df = hist_df.iloc[test_start_idx:].copy()

        logger.info(f"[{etf_code}] 训练集: {len(train_df)} 天, 测试集: {len(test_df)} 天")

        # 2. 训练 XGBoost 模型
        predictor = MLPredictor(model_dir=ML_MODEL_DIR)
        ok = predictor.train(etf_code, train_df, overnight_series=None)
        if not ok:
            logger.warning(f"[{etf_code}] 模型训练失败，跳过")
            return None

        # 3. 逐日测试
        summary = ETFSummary(etf_code=etf_code, etf_name=name)
        capital = self._initial_capital

        for test_idx in range(len(test_df)):
            # 构建截止到前一天的历史窗口（用于特征构建）
            # test_df 在 hist_df 中的绝对位置
            abs_idx = test_start_idx + test_idx
            # 给 predictor 的历史数据 = 训练集 + 之前已测完的天数
            feature_df = hist_df.iloc[:abs_idx].copy()

            if len(feature_df) < 20:
                continue

            test_row = test_df.iloc[test_idx]
            day_result = self._test_single_day(
                etf_code, name, predictor, feature_df, test_row, capital
            )

            if day_result:
                capital += day_result.pnl
                summary.daily_results.append(day_result)

        # 4. 计算汇总
        self._calc_summary(summary)
        return summary

    def _test_single_day(
        self,
        etf_code: str,
        etf_name: str,
        predictor: MLPredictor,
        feature_df: pd.DataFrame,
        test_row: pd.Series,
        capital: float,
    ) -> Optional[DayResult]:
        """测试单日：预测 → 合成 Tick → 策略评估 → 交易"""
        try:
            # 获取日期
            date_val = test_row.get("日期", test_row.name)
            if isinstance(date_val, pd.Timestamp):
                date_str = date_val.strftime("%Y-%m-%d")
            else:
                date_str = str(date_val)

            actual_open = float(test_row["开盘"])
            actual_high = float(test_row["最高"])
            actual_low = float(test_row["最低"])
            actual_close = float(test_row["收盘"])

            if actual_close <= 0 or actual_open <= 0:
                return None

            # --- 生成预测 ---
            last_close = float(feature_df.iloc[-1]["收盘"])
            pred = predictor.predict(etf_code, None, feature_df)
            if pred is None:
                return None

            # 预测输出是比率，转为绝对价格
            pred_high = pred.predicted_high * last_close
            pred_low = pred.predicted_low * last_close

            # 确保 high >= low
            if pred_high < pred_low:
                pred_high, pred_low = pred_low, pred_high

            # --- 合成日内 Tick ---
            ticks = self._generate_intraday_ticks(
                actual_open, actual_high, actual_low, actual_close
            )

            # --- 计算 PP 点位 ---
            prev_high = float(feature_df.iloc[-1]["最高"])
            prev_low = float(feature_df.iloc[-1]["最低"])
            prev_close = float(feature_df.iloc[-1]["收盘"])
            
            pp = (prev_high + prev_low + prev_close) / 3
            pp_levels = {
                etf_code: {
                    "PP": pp,
                    "R1": 2 * pp - prev_low,
                    "S1": 2 * pp - prev_high,
                    "R2": pp + (prev_high - prev_low),
                    "S2": pp - (prev_high - prev_low),
                }
            }

            # --- 用 MLPriceStrategy 评估 ---
            strategy = MLPriceStrategy(predictor)
            # 设置当日预测和点位
            prediction = PricePrediction(
                etf_code=etf_code,
                predicted_high=pred_high,
                predicted_low=pred_low,
                confidence=1.0,  # 回测中强制置信度=1，测试全部预测
            )
            strategy.set_daily_data({etf_code: prediction}, pp_levels)
            # 回测中禁用信号持久化 → 直接注入 count >= 2
            strategy._signal_persistence[etf_code] = (SignalType.HOLD, 10)

            # 简化持仓管理
            position_mgr = PositionManager(capital)
            risk_mgr = RiskManager(position_mgr)
            trader = MockTrader(position_mgr)
            trader.connect()

            trade_count = 0

            for tick_time, tick_price in ticks:
                # 构建 snapshot
                snapshot = MarketSnapshot(
                    etf_code=etf_code,
                    etf_name=etf_name,
                    timestamp=tick_time,
                    etf_price=tick_price,
                    etf_open=actual_open,
                    etf_high=actual_high,
                    etf_low=actual_low,
                    etf_volume=0,
                    iopv=tick_price,  # 简化: IOPV = 价格
                    futures_price=0,
                    exchange_rate=1.0,
                    premium_rate=0.0,
                    futures_momentum=0.0,
                )

                # 评估信号（跳过冷却检查）
                signal = strategy.evaluate(snapshot)

                # 检查退出规则
                price_map = {etf_code: tick_price}
                position_mgr.update_prices(price_map)

                # 处理 BUY
                if signal.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
                    if not position_mgr.has_position(etf_code):
                        allowed, _ = risk_mgr.validate_entry(signal, now=tick_time)
                        if allowed:
                            qty = risk_mgr.calc_order_quantity(signal)
                            if qty > 0:
                                order = TradeOrder(
                                    etf_code=etf_code,
                                    etf_name=etf_name,
                                    side=OrderSide.BUY,
                                    price=tick_price,
                                    quantity=qty,
                                    reason=signal.reason,
                                    timestamp=tick_time,
                                )
                                trader.execute(order)
                                trade_count += 1

                # 处理 SELL
                elif signal.signal_type in (SignalType.SELL, SignalType.STRONG_SELL):
                    if position_mgr.has_position(etf_code):
                        pos = position_mgr.get_position(etf_code)
                        order = TradeOrder(
                            etf_code=etf_code,
                            etf_name=etf_name,
                            side=OrderSide.SELL,
                            price=tick_price,
                            quantity=pos.quantity,
                            reason=signal.reason,
                            timestamp=tick_time,
                        )
                        trader.execute(order)
                        trade_count += 1

            # 日终清仓
            for pos_code in list(position_mgr.positions.keys()):
                pos = position_mgr.get_position(pos_code)
                if pos and pos.quantity > 0:
                    position_mgr.close_position(
                        pos_code, actual_close,
                        reason="日终清仓",
                        timestamp=ticks[-1][0] if ticks else None,
                    )

            # 计算当日盈亏
            day_pnl = position_mgr.total_assets - capital

            # 预测误差
            high_err = (pred_high - actual_high) / actual_high * 100 if actual_high > 0 else 0
            low_err = (pred_low - actual_low) / actual_low * 100 if actual_low > 0 else 0

            result = DayResult(
                date=date_str,
                etf_code=etf_code,
                pred_high=pred_high,
                pred_low=pred_low,
                actual_high=actual_high,
                actual_low=actual_low,
                actual_close=actual_close,
                actual_open=actual_open,
                trades=trade_count,
                pnl=day_pnl,
                high_error_pct=high_err,
                low_error_pct=low_err,
            )

            # 打印每日结果
            pnl_mark = "✅" if day_pnl > 0 else ("❌" if day_pnl < 0 else "➖")
            logger.info(
                f"  {date_str} | {pnl_mark} PnL={day_pnl:+.2f} | "
                f"交易={trade_count} | "
                f"预测[{pred_low:.4f}~{pred_high:.4f}] "
                f"实际[{actual_low:.4f}~{actual_high:.4f}] | "
                f"误差 H={high_err:+.2f}% L={low_err:+.2f}%"
            )

            return result

        except Exception as e:
            logger.debug(f"[{etf_code}] 单日测试异常: {e}")
            import traceback
            traceback.print_exc()
            return None

    # ------------------------------------------------------------------
    #  合成日内 Tick
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_intraday_ticks(
        open_p: float, high: float, low: float, close: float,
        num_ticks: int = 20,
    ) -> list[tuple[datetime, float]]:
        """
        从日线 OHLC 生成合成的日内价格路径。

        路径逻辑:
          阳线 (Close >= Open): Open → Low → High → Close
          阴线 (Close < Open):  Open → High → Low → Close

        Returns:
            [(datetime, price), ...] 按时间排序的 tick 列表
        """
        base_date = datetime(2026, 1, 1)  # 日期不影响逻辑
        market_open = datetime.combine(base_date, dtime(9, 30))
        market_close = datetime.combine(base_date, dtime(15, 0))
        total_minutes = int((market_close - market_open).total_seconds() / 60)

        # 分配时间段
        # Phase 1: Open → 第一个极值 (前 30%)
        # Phase 2: 第一极值 → 第二极值 (中间 40%)
        # Phase 3: 第二极值 → Close (后 30%)
        ticks_p1 = max(2, num_ticks * 3 // 10)
        ticks_p2 = max(2, num_ticks * 4 // 10)
        ticks_p3 = num_ticks - ticks_p1 - ticks_p2

        is_bullish = close >= open_p

        if is_bullish:
            # Open → Low → High → Close
            prices_p1 = np.linspace(open_p, low, ticks_p1)
            prices_p2 = np.linspace(low, high, ticks_p2)
            prices_p3 = np.linspace(high, close, ticks_p3)
        else:
            # Open → High → Low → Close
            prices_p1 = np.linspace(open_p, high, ticks_p1)
            prices_p2 = np.linspace(high, low, ticks_p2)
            prices_p3 = np.linspace(low, close, ticks_p3)

        all_prices = list(prices_p1) + list(prices_p2[1:]) + list(prices_p3[1:])

        # 加入微小噪声增加真实感 (振幅的 5%)
        spread = high - low if high > low else 0.001
        noise_scale = spread * 0.03
        noisy_prices = []
        for i, p in enumerate(all_prices):
            if i == 0 or i == len(all_prices) - 1:
                noisy_prices.append(p)  # open/close 保持精确
            else:
                noise = random.gauss(0, noise_scale)
                noisy_p = max(low * 0.999, min(high * 1.001, p + noise))
                noisy_prices.append(noisy_p)

        # 生成时间戳
        result = []
        for i, price in enumerate(noisy_prices):
            t = i / max(len(noisy_prices) - 1, 1)
            minutes = int(t * total_minutes)
            tick_time = market_open + timedelta(minutes=minutes)
            result.append((tick_time, round(price, 4)))

        return result

    # ------------------------------------------------------------------
    #  数据加载
    # ------------------------------------------------------------------

    def _fetch_data(self, etf_code: str) -> Optional[pd.DataFrame]:
        """获取历史数据 (复用 train_model.py 的逻辑)"""
        try:
            from scripts.train_model import fetch_training_data
            df = fetch_training_data(etf_code, days=self._total_fetch_days)
            if df is not None:
                logger.info(f"[{etf_code}] 获取到 {len(df)} 条历史数据")
            return df
        except Exception as e:
            logger.error(f"[{etf_code}] 数据获取失败: {e}")
            return None

    # ------------------------------------------------------------------
    #  汇总计算
    # ------------------------------------------------------------------

    @staticmethod
    def _calc_summary(summary: ETFSummary) -> None:
        """计算汇总统计"""
        results = summary.daily_results
        if not results:
            return

        summary.test_days = len(results)
        summary.win_days = sum(1 for r in results if r.pnl > 0)
        summary.lose_days = sum(1 for r in results if r.pnl < 0)
        summary.flat_days = sum(1 for r in results if r.pnl == 0)
        summary.total_trades = sum(r.trades for r in results)
        summary.total_pnl = sum(r.pnl for r in results)

        # 最大回撤
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for r in results:
            cumulative += r.pnl
            peak = max(peak, cumulative)
            dd = peak - cumulative
            max_dd = max(max_dd, dd)
        summary.max_drawdown = max_dd

        # 平均预测误差
        summary.avg_high_error = np.mean([abs(r.high_error_pct) for r in results])
        summary.avg_low_error = np.mean([abs(r.low_error_pct) for r in results])

    # ------------------------------------------------------------------
    #  打印汇总
    # ------------------------------------------------------------------

    def _print_summary(self, results: dict[str, ETFSummary]) -> None:
        """打印所有标的的汇总报告"""
        if not results:
            logger.warning("无回测结果")
            return

        logger.info("\n" + "═" * 70)
        logger.info("                  ML 策略回测汇总报告")
        logger.info("═" * 70)
        logger.info(f"  训练窗口: {self._train_days} 天 | 测试窗口: {self._test_days} 天")
        logger.info(f"  每标的初始资金: {self._initial_capital:,.2f}")
        logger.info("═" * 70)

        # 表头
        logger.info(
            f"  {'标的':>10s} | {'名称':>10s} | "
            f"{'测试天':>4s} | {'胜/负/平':>8s} | {'胜率':>6s} | "
            f"{'总收益':>10s} | {'收益率':>7s} | "
            f"{'最大回撤':>8s} | {'交易数':>5s} | "
            f"{'高预测误差':>8s} | {'低预测误差':>8s}"
        )
        logger.info("─" * 70)

        total_pnl = 0.0
        total_trades = 0

        for code, s in results.items():
            win_rate = s.win_days / (s.win_days + s.lose_days) * 100 if (s.win_days + s.lose_days) > 0 else 0
            pnl_pct = s.total_pnl / self._initial_capital * 100

            total_pnl += s.total_pnl
            total_trades += s.total_trades

            icon = "🟢" if s.total_pnl > 0 else ("🔴" if s.total_pnl < 0 else "⚪")

            logger.info(
                f"  {icon} {code:>6s} | {s.etf_name:>8s} | "
                f"{s.test_days:>4d} | "
                f"{s.win_days}胜/{s.lose_days}负/{s.flat_days}平 | "
                f"{win_rate:5.1f}% | "
                f"{s.total_pnl:>+10.2f} | "
                f"{pnl_pct:>+6.2f}% | "
                f"{s.max_drawdown:>8.2f} | "
                f"{s.total_trades:>5d} | "
                f"{s.avg_high_error:>7.2f}% | "
                f"{s.avg_low_error:>7.2f}%"
            )

        logger.info("─" * 70)

        avg_pnl_pct = total_pnl / (self._initial_capital * len(results)) * 100 if results else 0
        logger.info(
            f"  合计 | 总盈亏: {total_pnl:+,.2f} | "
            f"平均收益率: {avg_pnl_pct:+.2f}% | "
            f"总交易: {total_trades} 笔"
        )
        logger.info("═" * 70)


# ======================================================================
#  入口函数
# ======================================================================

def run_ml_backtest(
    etf_codes: Optional[list[str]] = None,
    initial_capital: float = INITIAL_CAPITAL,
    test_days: int = 30,
    train_days: int = 150,
) -> dict[str, ETFSummary]:
    """ML 回测入口"""
    from monitor.logger import setup_logger
    setup_logger()

    bt = MLBacktester(
        etf_codes=etf_codes,
        initial_capital=initial_capital,
        test_days=test_days,
        train_days=train_days,
    )
    return bt.run()
