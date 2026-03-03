"""
复合策略管理器

将多个独立策略并行评估，按规则合并信号。

合并规则:
  - 同方向信号 → 取最强信号（强度叠加）
  - 冲突信号（BUY vs SELL）→ HOLD（保守策略）
  - 仅单一策略有信号 → 直接采纳
"""
from datetime import datetime
from loguru import logger

from strategy.base_strategy import BaseStrategy
from strategy.signal import MarketSnapshot, TradingSignal, SignalType


class CompositeStrategy(BaseStrategy):
    """
    复合策略：管理多个子策略，合并输出统一信号。
    """

    def __init__(self, strategies: list[BaseStrategy]):
        if not strategies:
            raise ValueError("至少需要一个子策略")
        self._strategies = strategies

    @property
    def name(self) -> str:
        names = [s.name for s in self._strategies]
        return "复合策略[" + "+".join(names) + "]"

    def evaluate(self, snapshot: MarketSnapshot) -> TradingSignal:
        """
        并行评估所有子策略，合并信号。
        """
        code = snapshot.etf_code
        now = datetime.now()

        # 收集所有子策略的信号
        signals: list[TradingSignal] = []
        for strategy in self._strategies:
            try:
                signal = strategy.evaluate(snapshot)
                signals.append(signal)
            except Exception as e:
                logger.warning(f"[{code}] 子策略 {strategy.name} 评估失败: {e}")

        if not signals:
            return self._hold_signal(snapshot, now, "无子策略返回信号")

        # 过滤出有效信号（非 HOLD）
        actionable = [s for s in signals if s.is_actionable]

        if not actionable:
            # 所有策略都是 HOLD，返回第一个 HOLD 信号
            return signals[0]

        if len(actionable) == 1:
            # 仅一个策略有信号，直接采纳
            return actionable[0]

        # 多个信号 → 检查方向性
        buy_signals = [
            s for s in actionable
            if s.signal_type in (SignalType.BUY, SignalType.STRONG_BUY)
        ]
        sell_signals = [
            s for s in actionable
            if s.signal_type in (SignalType.SELL, SignalType.STRONG_SELL)
        ]

        # 冲突: 同时有买入和卖出信号
        if buy_signals and sell_signals:
            reasons = [s.reason for s in actionable]
            return self._hold_signal(
                snapshot, now,
                f"信号冲突(买:{len(buy_signals)} 卖:{len(sell_signals)}) - "
                + " | ".join(reasons)
            )

        # 同方向: 合并信号
        if buy_signals:
            return self._merge_signals(buy_signals, snapshot, now)
        else:
            return self._merge_signals(sell_signals, snapshot, now)

    def reset(self) -> None:
        """重置所有子策略"""
        for strategy in self._strategies:
            strategy.reset()
        logger.info(f"[{self.name}] 所有子策略已重置")

    def get_strategy(self, strategy_type: type) -> BaseStrategy | None:
        """按类型获取子策略实例（用于设置隔夜数据等）"""
        for s in self._strategies:
            if isinstance(s, strategy_type):
                return s
        return None

    # ------------------------------------------------------------------

    def _merge_signals(
        self,
        signals: list[TradingSignal],
        snapshot: MarketSnapshot,
        now: datetime,
    ) -> TradingSignal:
        """
        合并同方向信号。

        取强度最高的信号为基础，叠加其他信号的强度增益。
        """
        # 按强度降序
        signals.sort(key=lambda s: s.strength, reverse=True)
        primary = signals[0]

        # 叠加：其他信号的强度贡献 30%
        merged_strength = primary.strength
        for s in signals[1:]:
            merged_strength += s.strength * 0.3

        merged_strength = min(1.0, merged_strength)

        # 合并理由
        reasons = [s.reason for s in signals]
        merged_reason = " + ".join(reasons)

        # 如果叠加后强度更高，可能升级信号类型
        signal_type = primary.signal_type
        if merged_strength > 0.6:
            if signal_type == SignalType.BUY:
                signal_type = SignalType.STRONG_BUY
            elif signal_type == SignalType.SELL:
                signal_type = SignalType.STRONG_SELL

        logger.info(
            f"[{snapshot.etf_code}] 复合信号: {signal_type.value} | "
            f"合并强度: {merged_strength:.2f} (基础: {primary.strength:.2f})"
        )

        return TradingSignal(
            etf_code=snapshot.etf_code,
            etf_name=snapshot.etf_name,
            signal_type=signal_type,
            timestamp=now,
            price=snapshot.etf_price,
            iopv=snapshot.iopv,
            premium_rate=snapshot.premium_rate,
            futures_momentum=snapshot.futures_momentum,
            strength=merged_strength,
            reason=merged_reason,
        )

    def _hold_signal(self, snapshot, now, reason):
        return TradingSignal(
            etf_code=snapshot.etf_code,
            etf_name=snapshot.etf_name,
            signal_type=SignalType.HOLD,
            timestamp=now,
            price=snapshot.etf_price,
            iopv=snapshot.iopv,
            premium_rate=snapshot.premium_rate,
            futures_momentum=snapshot.futures_momentum,
            strength=0.0,
            reason=reason,
        )
