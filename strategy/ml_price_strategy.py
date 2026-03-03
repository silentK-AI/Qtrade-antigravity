"""
ML 价格预测策略

基于 XGBoost 模型的次日最高价/最低价预测，生成买卖信号。

买入逻辑: 当前价格 ≤ 预测最低价 → BUY
卖出逻辑: 当前价格 ≥ 预测最高价 → SELL
"""
import time
from datetime import datetime
from loguru import logger

from strategy.base_strategy import BaseStrategy
from strategy.signal import MarketSnapshot, TradingSignal, SignalType
from strategy.ml_predictor import MLPredictor, PricePrediction
from config.settings import (
    SIGNAL_COOLDOWN_SECONDS,
    ML_PRED_CONFIDENCE_THRESHOLD,
    ML_PRED_BUY_BUFFER,
    ML_PRED_SELL_BUFFER,
    MIN_SIGNAL_PERSISTENCE_COUNT,
)


class MLPriceStrategy(BaseStrategy):
    """
    基于 ML 价格预测的交易策略。

    每日开盘前通过 set_daily_predictions 设置预测值，
    实盘运行时比较当前价格与预测价格生成交易信号。
    """

    def __init__(self, predictor: MLPredictor):
        self._predictor = predictor
        # {etf_code: PricePrediction}
        self._daily_predictions: dict[str, PricePrediction] = {}
        self._cooldown_tracker: dict[str, dict[str, float]] = {}
        # 信号持久化追踪: {etf_code: (signal_type, count)}
        self._signal_persistence: dict[str, tuple[SignalType, int]] = {}

    @property
    def name(self) -> str:
        return "ML价格预测策略"

    def set_daily_predictions(
        self, predictions: dict[str, PricePrediction]
    ) -> None:
        """
        每日开盘前设置预测值。

        Args:
            predictions: {etf_code: PricePrediction}
        """
        self._daily_predictions = predictions
        for code, pred in predictions.items():
            logger.info(
                f"[{code}] ML预测: "
                f"最高={pred.predicted_high:.4f} "
                f"最低={pred.predicted_low:.4f} "
                f"置信度={pred.confidence:.2f}"
            )

    def evaluate(self, snapshot: MarketSnapshot) -> TradingSignal:
        """
        根据当前价格与预测价格的关系生成交易信号。

        信号逻辑:
          - 当前价 ≤ 预测最低价 + buffer → BUY
          - 当前价 ≥ 预测最高价 - buffer → SELL
          - 否则 → HOLD
        """
        code = snapshot.etf_code
        now = datetime.now()

        # 无预测数据时返回 HOLD
        pred = self._daily_predictions.get(code)
        if pred is None:
            return self._hold_signal(snapshot, now, "无ML预测数据")

        # 置信度过低不触发
        if pred.confidence < ML_PRED_CONFIDENCE_THRESHOLD:
            return self._hold_signal(
                snapshot, now,
                f"ML置信度不足({pred.confidence:.2f}<{ML_PRED_CONFIDENCE_THRESHOLD})"
            )

        price = snapshot.etf_price
        if price <= 0:
            return self._hold_signal(snapshot, now, "价格无效")

        signal_type = SignalType.HOLD
        strength = 0.0
        reason_parts = []

        buy_target = pred.predicted_low + ML_PRED_BUY_BUFFER
        sell_target = pred.predicted_high - ML_PRED_SELL_BUFFER

        # 买入信号: 价格触及或低于预测最低价
        if price <= buy_target:
            depth = (buy_target - price) / buy_target if buy_target > 0 else 0
            strength = min(1.0, 0.4 + depth * 20 + pred.confidence * 0.3)

            if strength > 0.6:
                signal_type = SignalType.STRONG_BUY
            else:
                signal_type = SignalType.BUY

            # 新增：溢价检查（防止在高溢价时买入，即便ML预测价格低）
            if snapshot.premium_rate > 0.008: # > 0.8% 溢价
                 return self._hold_signal(snapshot, now, f"ML买入被高溢价({snapshot.premium_rate*100:.2f}%)拦截")

            reason_parts.append(
                f"ML预测低点{pred.predicted_low:.4f}"
            )
            reason_parts.append(f"当前价{price:.4f}≤目标{buy_target:.4f}")
            reason_parts.append(f"置信度{pred.confidence:.2f}")

        # 卖出信号: 价格触及或高于预测最高价
        elif price >= sell_target:
            depth = (price - sell_target) / sell_target if sell_target > 0 else 0
            strength = min(1.0, 0.4 + depth * 20 + pred.confidence * 0.3)

            if strength > 0.6:
                signal_type = SignalType.STRONG_SELL
            else:
                signal_type = SignalType.SELL

            # 新增：折价检查（防止在深折价时卖出）
            if snapshot.premium_rate < -0.008: # < -0.8% 折价
                 return self._hold_signal(snapshot, now, f"ML卖出被深折价({snapshot.premium_rate*100:.2f}%)拦截")

            reason_parts.append(
                f"ML预测高点{pred.predicted_high:.4f}"
            )
            reason_parts.append(f"当前价{price:.4f}≥目标{sell_target:.4f}")
            reason_parts.append(f"置信度{pred.confidence:.2f}")

        else:
            # 价格在预测区间内
            return self._hold_signal(
                snapshot, now,
                f"ML区间内(低={pred.predicted_low:.4f}~高={pred.predicted_high:.4f})"
            )

        # ---------- 信号持久化校验 ----------
        prev_type, count = self._signal_persistence.get(code, (SignalType.HOLD, 0))
        
        # 转换为基础方向
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
                f"ML信号确认中({count}/{MIN_SIGNAL_PERSISTENCE_COUNT}), " + ", ".join(reason_parts)
            )

        # 冷却检查
        if self._is_cooling_down(code, signal_type):
            return self._hold_signal(
                snapshot, now,
                f"ML信号冷却中({signal_type.value})"
            )

        self._update_cooldown(code, signal_type)

        reason = f"[{self.name}] " + ", ".join(reason_parts)
        logger.info(
            f"[{code}] ML信号: {signal_type.value} | "
            f"强度: {strength:.2f} | {reason}"
        )

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
            reason=reason,
        )

    def reset(self) -> None:
        """重置策略状态"""
        self._daily_predictions.clear()
        self._cooldown_tracker.clear()
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
