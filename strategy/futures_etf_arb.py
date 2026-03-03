"""
核心策略：关联期货/指数联动 + ETF 折溢价信号 + 隔夜行情增强
"""
import time
from datetime import datetime
from typing import Optional
from loguru import logger

from strategy.base_strategy import BaseStrategy
from strategy.signal import MarketSnapshot, TradingSignal, SignalType
from data.overnight_data import OvernightInfo
from config.settings import (
    PREMIUM_THRESHOLD,
    DISCOUNT_THRESHOLD,
    SIGNAL_COOLDOWN_SECONDS,
    VOLUME_CONFIRM_RATIO,
    MIN_SIGNAL_PERSISTENCE_COUNT,
)


class FuturesETFArbStrategy(BaseStrategy):
    """
    期货联动 + ETF 折溢价套利策略（含隔夜信号增强）。

    买入逻辑：关联期货动量向上 AND ETF 折价 (+ 隔夜上涨加分)
    卖出逻辑：关联期货动量向下 AND ETF 溢价 (+ 隔夜下跌加分)
    """

    def __init__(self):
        self._cooldown_tracker: dict[str, dict[str, float]] = {}
        self._avg_volumes: dict[str, float] = {}
        # 隔夜信号: {etf_code: OvernightInfo}
        self._overnight_data: dict[str, OvernightInfo] = {}
        # 信号持久化追踪: {etf_code: (signal_type, count)}
        self._signal_persistence: dict[str, tuple[SignalType, int]] = {}
        # ETF 价格历史（用于趋势确认）: {etf_code: deque of prices}
        from collections import deque
        self._price_history: dict[str, deque] = {}

    @property
    def name(self) -> str:
        return "期货联动+折溢价+隔夜增强策略"

    def set_overnight_data(self, overnight_map: dict[str, OvernightInfo]) -> None:
        """设置隔夜数据（每日开盘前由主循环调用）"""
        self._overnight_data = overnight_map
        for code, info in overnight_map.items():
            if info.is_valid:
                logger.info(
                    f"[{code}] 隔夜信号: {info.symbol} "
                    f"涨跌={info.overnight_change_pct:+.2f}% "
                    f"方向={info.gap_direction} "
                    f"评分={info.momentum_score:+.2f}"
                )

    def _calc_rsi(self, etf_code: str, period: int = 14) -> float:
        """计算短期 RSI"""
        prices = list(self._price_history.get(etf_code, []))
        if len(prices) < period + 1:
            return 50.0
        
        import numpy as np
        deltas = np.diff(prices[-(period+1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        
        if avg_loss == 0: return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - 100.0 / (1.0 + rs)

    def evaluate(self, snapshot: MarketSnapshot) -> TradingSignal:
        """
        根据行情快照评估交易信号。
        """
        code = snapshot.etf_code
        now = datetime.now()

        if not snapshot.is_valid:
            return self._hold_signal(snapshot, now, "数据无效")

        # ---------- 基础数据准备 ----------
        if code not in self._price_history:
            const_deque = __import__('collections').deque
            self._price_history[code] = const_deque(maxlen=20)
        self._price_history[code].append(snapshot.etf_price)
        
        rsi = self._calc_rsi(code, 6)

        # ---------- 期货动量判断 ----------
        momentum = snapshot.futures_momentum
        futures_up = momentum > 0.001
        futures_down = momentum < -0.001
        momentum_strength = abs(momentum) * 100

        # ---------- 折溢价判断 ----------
        premium = snapshot.premium_rate
        is_discount = premium < DISCOUNT_THRESHOLD
        is_premium = premium > PREMIUM_THRESHOLD
        premium_strength = abs(premium) * 100

        # ---------- 隔夜信号 ----------
        overnight = self._overnight_data.get(code)
        overnight_bias = 0.0        # 隔夜偏置 (-1 ~ +1)
        overnight_strength = 0.0    # 隔夜强度加成
        overnight_desc = ""

        if overnight and overnight.is_valid:
            overnight_bias = overnight.momentum_score
            overnight_strength = abs(overnight.momentum_score) * 0.3  # 最多加成 0.3
            overnight_desc = (
                f"隔夜{overnight.symbol}"
                f"{overnight.overnight_change_pct:+.2f}%"
                f"({overnight.gap_direction})"
            )

        # ---------- 信号生成 ----------
        signal_type = SignalType.HOLD
        strength = 0.0
        reason_parts = [f"RSI(6):{rsi:.1f}"]

        # 买入信号：期货向上 + ETF 折价
        if futures_up and is_discount:
            # 趋势确认：如果还在大跌，不要接飞刀 (除非 RSI 已经极度超卖 < 20)
            if rsi > 20 and len(self._price_history[code]) >= 3:
                if snapshot.etf_price < min(list(self._price_history[code])[-3:-1]):
                    return self._hold_signal(snapshot, now, f"买入拦截(下跌中), RSI={rsi:.1f}")

            reason_parts.append(f"期货动量+{momentum_strength:.2f}%")
            reason_parts.append(f"ETF折价{premium * 100:.2f}%")
            base_strength = (momentum_strength + premium_strength) / 2
            if overnight_bias > 0: base_strength += overnight_strength
            
            signal_type = SignalType.STRONG_BUY if base_strength > 0.4 else SignalType.BUY
            strength = min(1.0, base_strength)

        # 卖出信号：期货向下 + ETF 溢价
        elif futures_down and is_premium:
            # 科学卖出择时：如果还在加速上涨且 RSI 还没到 80，等一下
            if rsi < 80 and len(self._price_history[code]) >= 3:
                if snapshot.etf_price > max(list(self._price_history[code])[-3:-1]):
                    return self._hold_signal(snapshot, now, f"卖出拦截(冲锋中), RSI={rsi:.1f}")

            reason_parts.append(f"期货动量{momentum_strength:.2f}%")
            reason_parts.append(f"ETF溢价+{premium * 100:.2f}%")
            base_strength = (momentum_strength + premium_strength) / 2
            if overnight_bias < 0: base_strength += overnight_strength
            
            signal_type = SignalType.STRONG_SELL if base_strength > 0.4 else SignalType.SELL
            strength = min(1.0, base_strength)

        # 隔夜强信号单独触发（仅开盘前30分钟内有效）
        elif abs(overnight_bias) > 0.5 and now.hour == 9 and now.minute < 45:
            if overnight_bias > 0.5 and is_discount:
                signal_type = SignalType.BUY
                strength = min(0.6, overnight_strength + premium_strength / 2)
                reason_parts.append(f"{overnight_desc}(隔夜强势)")
                reason_parts.append(f"ETF折价{premium * 100:.2f}%")
            elif overnight_bias < -0.5 and is_premium:
                signal_type = SignalType.SELL
                strength = min(0.6, overnight_strength + premium_strength / 2)
                reason_parts.append(f"{overnight_desc}(隔夜弱势)")
                reason_parts.append(f"ETF溢价+{premium * 100:.2f}%")
            else:
                parts = [f"动量={momentum * 100:.2f}%", f"溢价率={premium * 100:.2f}%"]
                if overnight_desc:
                    parts.append(overnight_desc)
                return self._hold_signal(snapshot, now, ", ".join(parts))

            return self._hold_signal(snapshot, now, ", ".join(parts))

        # ---------- 趋势确认过滤器 (Trend Confirmation) ----------
        # 记录价格历史 (最近 2 个快照)
        if code not in self._price_history:
            const_deque = __import__('collections').deque
            self._price_history[code] = const_deque(maxlen=2)
        self._price_history[code].append(snapshot.etf_price)

        if signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
            # 如果当前价格还在创新低，则拦截
            if len(self._price_history[code]) >= 2:
                prices = list(self._price_history[code])
                if snapshot.etf_price < prices[0]:
                    return self._hold_signal(
                        snapshot, now, 
                        f"趋势拦截: 正在下跌({snapshot.etf_price:.3f} < {prices[0]:.3f}), " + ", ".join(reason_parts)
                    )
        
        elif signal_type in (SignalType.SELL, SignalType.STRONG_SELL):
            # 如果当前价格还在创新高，则拦截（尽量卖在高点）
            if len(self._price_history[code]) >= 3:
                prices = list(self._price_history[code])
                avg_prev = (prices[0] + prices[1]) / 2
                if snapshot.etf_price > avg_prev:
                    return self._hold_signal(
                        snapshot, now, 
                        f"趋势拦截: 正在上涨({snapshot.etf_price:.3f} > 均价{avg_prev:.3f}), " + ", ".join(reason_parts)
                    )

        # ---------- 信号持久化校验 ----------
        prev_type, count = self._signal_persistence.get(code, (SignalType.HOLD, 0))
        
        # 转换为基础方向 (简化：BUY/STRONG_BUY 都视为 BUY)
        def get_base_type(st):
            if st in (SignalType.BUY, SignalType.STRONG_BUY): return SignalType.BUY
            if st in (SignalType.SELL, SignalType.STRONG_SELL): return SignalType.SELL
            return SignalType.HOLD

        if get_base_type(signal_type) == get_base_type(prev_type) and signal_type != SignalType.HOLD:
            count += 1
        else:
            count = 1 if signal_type != SignalType.HOLD else 0
        
        self._signal_persistence[code] = (signal_type, count)

        if count < MIN_SIGNAL_PERSISTENCE_COUNT and signal_type != SignalType.HOLD:
            return self._hold_signal(
                snapshot, now,
                f"信号确认中({count}/{MIN_SIGNAL_PERSISTENCE_COUNT}), " + ", ".join(reason_parts)
            )

        # ---------- 信号冷却检查 ----------
        if self._is_cooling_down(code, signal_type):
            return self._hold_signal(
                snapshot, now,
                f"信号冷却中({signal_type.value}), " + ", ".join(reason_parts)
            )

        self._update_cooldown(code, signal_type)

        reason = f"[{self.name}] " + ", ".join(reason_parts)
        logger.info(
            f"[{code}] 信号: {signal_type.value} | "
            f"强度: {strength:.2f} | {reason}"
        )

        return TradingSignal(
            etf_code=code,
            etf_name=snapshot.etf_name,
            signal_type=signal_type,
            timestamp=now,
            price=snapshot.etf_price,
            iopv=snapshot.iopv,
            premium_rate=premium,
            futures_momentum=momentum,
            strength=strength,
            reason=reason,
        )

    def reset(self) -> None:
        """重置策略状态"""
        self._cooldown_tracker.clear()
        self._overnight_data.clear()
        logger.info(f"[{self.name}] 策略状态已重置")

    # ------------------------------------------------------------------
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

    def _is_cooling_down(self, etf_code, signal_type):
        tracker = self._cooldown_tracker.get(etf_code, {})
        direction = "buy" if signal_type in (SignalType.BUY, SignalType.STRONG_BUY) else "sell"
        last_time = tracker.get(direction, 0)
        return (time.time() - last_time) < SIGNAL_COOLDOWN_SECONDS

    def _update_cooldown(self, etf_code, signal_type):
        if etf_code not in self._cooldown_tracker:
            self._cooldown_tracker[etf_code] = {}
        direction = "buy" if signal_type in (SignalType.BUY, SignalType.STRONG_BUY) else "sell"
        self._cooldown_tracker[etf_code][direction] = time.time()
