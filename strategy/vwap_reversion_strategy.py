"""
VWAP 均值回归策略

基于当日成交均价 (VWAP) 的偏离度生成交易信号。
VWAP = 累计成交额 / 累计成交量

买入逻辑: 价格 < VWAP * (1 - threshold) 且趋势企稳
卖出逻辑: 价格 > VWAP * (1 + threshold)
"""
import time
from datetime import datetime
from loguru import logger
from collections import deque

from strategy.base_strategy import BaseStrategy
from strategy.signal import MarketSnapshot, TradingSignal, SignalType
from config.etf_settings import SIGNAL_COOLDOWN_SECONDS, MIN_SIGNAL_PERSISTENCE_COUNT

# 策略特有配置
VWAP_BUY_THRESHOLD = 0.0015   # 降低阈值到 -0.15%
VWAP_SELL_THRESHOLD = 0.0015  # 降低阈值到 +0.15%

class VWAPReversionStrategy(BaseStrategy):
    """
    VWAP 均值回归策略。
    """

    def __init__(self):
        self._cooldown_tracker: dict[str, dict[str, float]] = {}
        # 信号持久化追踪: {etf_code: (signal_type, count)}
        self._signal_persistence: dict[str, tuple[SignalType, int]] = {}
        # 价格历史用于趋势确认
        self._price_history: dict[str, deque] = {}

    @property
    def name(self) -> str:
        return "VWAP均值回归策略"

    def _calc_rsi(self, etf_code: str, period: int = 14) -> float:
        """计算短期 RSI 进行极值判断"""
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
        评估 VWAP 偏离信号。
        """
        code = snapshot.etf_code
        now = datetime.now()

        if not snapshot.is_valid:
            return self._hold_signal(snapshot, now, "数据无效")

        # ---------- 基础数据准备 ----------
        if code not in self._price_history:
            const_deque = __import__('collections').deque
            self._price_history[code] = const_deque(maxlen=20) # 扩大历史容量支持 RSI
        self._price_history[code].append(snapshot.etf_price)

        if snapshot.etf_volume <= 0:
            return self._hold_signal(snapshot, now, "无成交量数据")
        
        vwap = snapshot.etf_amount / snapshot.etf_volume
        price = snapshot.etf_price
        deviation = (price - vwap) / vwap
        rsi = self._calc_rsi(code, 6) # 短周期 RSI(6)

        # ---------- 信号生成 ----------
        signal_type = SignalType.HOLD
        strength = 0.0
        reason_parts = [f"VWAP偏差:{deviation*100:+.2f}%", f"RSI(6):{rsi:.1f}"]

        # 卖出逻辑 (Alpha 衰减器)：高于均价且开始超买/滞涨
        if deviation >= VWAP_SELL_THRESHOLD:
            # 科学卖出择时：如果 RSI 还没过 75 且价格还在创新高，先等等
            if rsi < 75 and len(self._price_history[code]) >= 3:
                prices = list(self._price_history[code])
                if price > max(prices[-3:-1]): # 还在加速上涨
                    return self._hold_signal(snapshot, now, "卖出拦截: 冲锋中, " + ", ".join(reason_parts))
            
            signal_type = SignalType.SELL
            strength = min(1.0, deviation / 0.02 + (rsi-50)/50)

        # 买入逻辑：严重低于均价
        elif deviation <= -VWAP_BUY_THRESHOLD:
            # 科学买入择时：如果还在加速下跌，先不要接飞刀
            if rsi > 25 and len(self._price_history[code]) >= 3:
                prices = list(self._price_history[code])
                if price < min(prices[-3:-1]):
                    return self._hold_signal(snapshot, now, "买入拦截: 下跌中, " + ", ".join(reason_parts))
            
            signal_type = SignalType.BUY
            strength = min(1.0, abs(deviation) / 0.02 + (50-rsi)/50)
        
        # ---------- 信号持久化校验 ----------
        prev_type, count = self._signal_persistence.get(code, (SignalType.HOLD, 0))
        
        def get_base_type(st):
            if st in (SignalType.BUY, SignalType.STRONG_BUY): return SignalType.BUY
            if st in (SignalType.SELL, SignalType.STRONG_SELL): return SignalType.SELL
            return SignalType.HOLD

        if get_base_type(signal_type) == get_base_type(prev_type) and signal_type != SignalType.HOLD:
            count += 1
        else:
            count = 1 if signal_type != SignalType.HOLD else 0
        
        self._signal_persistence[code] = (signal_type, count)

        if count < MIN_SIGNAL_PERSISTENCE_COUNT:
            return self._hold_signal(
                snapshot, now,
                f"VWAP信号确认中({count}/{MIN_SIGNAL_PERSISTENCE_COUNT}), " + ", ".join(reason_parts)
            )

        # 冷却检查
        if self._is_cooling_down(code, signal_type):
            return self._hold_signal(snapshot, now, "VWAP信号冷却中")

        self._update_cooldown(code, signal_type)

        return TradingSignal(
            etf_code=code,
            etf_name=snapshot.etf_name,
            signal_type=signal_type,
            timestamp=now,
            price=price,
            iopv=snapshot.iopv,
            premium_rate=snapshot.premium_rate,
            futures_momentum=snapshot.futures_momentum,
            strength=strength,
            reason=f"[{self.name}] " + ", ".join(reason_parts),
        )

    def reset(self) -> None:
        self._cooldown_tracker.clear()
        self._price_history.clear()

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
        return (time.time() - tracker.get(direction, 0)) < SIGNAL_COOLDOWN_SECONDS

    def _update_cooldown(self, etf_code, signal_type):
        if etf_code not in self._cooldown_tracker:
            self._cooldown_tracker[etf_code] = {}
        direction = "buy" if signal_type in (SignalType.BUY, SignalType.STRONG_BUY) else "sell"
        self._cooldown_tracker[etf_code][direction] = time.time()
