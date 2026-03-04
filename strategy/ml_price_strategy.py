"""
ML 价格预测策略（区间交易版）

基于 XGBoost 模型预测的当日最高价/最低价，在价格接近预测边界时触发交易。

买入逻辑: 价格进入"预测低点区间" → BUY（越深入越强）
卖出逻辑: 价格进入"预测高点区间" → SELL（越接近越强）
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
)


class MLPriceStrategy(BaseStrategy):
    """
    基于 ML 价格区间预测的交易策略。

    将预测的日内价格区间 [predicted_low, predicted_high] 划分为 5 个区域：
      强买区  | 买入区 | 观望区 | 卖出区 | 强卖区
      <----30%---|---20%---|---HOLD---|---20%---|---30%---->

    信号强度随价格深入区间边界而递增。
    """

    # 区间比例参数
    STRONG_ZONE_PCT = 0.30   # 预测区间两端各 30% 为买入/卖出区
    ENTRY_ZONE_PCT = 0.20    # 紧邻强区的 20% 为普通买入/卖出区

    def __init__(self, predictor: MLPredictor):
        self._predictor = predictor
        # {etf_code: PricePrediction}
        self._daily_predictions: dict[str, PricePrediction] = {}
        self._cooldown_tracker: dict[str, dict[str, float]] = {}
        # 信号持久化追踪: {etf_code: (signal_type, count)}
        self._signal_persistence: dict[str, tuple[SignalType, int]] = {}

    @property
    def name(self) -> str:
        return "ML价格区间策略"

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
            spread = pred.predicted_high - pred.predicted_low
            logger.info(
                f"[{code}] ML预测: "
                f"最低={pred.predicted_low:.4f} "
                f"最高={pred.predicted_high:.4f} "
                f"区间={spread:.4f} "
                f"置信度={pred.confidence:.2f}"
            )

    def evaluate(self, snapshot: MarketSnapshot) -> TradingSignal:
        """
        根据当前价格在预测区间中的位置生成交易信号。
        """
        code = snapshot.etf_code
        now = datetime.now()

        # 无预测数据
        pred = self._daily_predictions.get(code)
        if pred is None:
            return self._hold_signal(snapshot, now, "无ML预测数据")

        # 置信度不足
        if pred.confidence < ML_PRED_CONFIDENCE_THRESHOLD:
            return self._hold_signal(
                snapshot, now,
                f"ML置信度不足({pred.confidence:.2f}<{ML_PRED_CONFIDENCE_THRESHOLD})"
            )

        price = snapshot.etf_price
        if price <= 0:
            return self._hold_signal(snapshot, now, "价格无效")

        # ---------- 计算价格区间 ----------
        pred_low = pred.predicted_low
        pred_high = pred.predicted_high
        spread = pred_high - pred_low

        if spread <= 0:
            return self._hold_signal(snapshot, now, "预测区间无效")

        # 价格在区间中的位置 (0=最低, 1=最高, <0=低于预测低点, >1=高于预测高点)
        position = (price - pred_low) / spread

        signal_type = SignalType.HOLD
        strength = 0.0
        reason_parts = [f"预测[{pred_low:.4f}~{pred_high:.4f}]"]

        # ---------- 信号生成 ----------

        # 强买区: position <= 0 (价格在预测最低价以下)
        if position <= 0:
            signal_type = SignalType.STRONG_BUY
            depth = abs(position)  # 越低于预测低点，strength 越大
            strength = min(1.0, 0.7 + depth * 2)
            reason_parts.append(f"强买(价格{price:.4f}≤预测低点{pred_low:.4f})")

        # 买入区: 0 < position <= STRONG_ZONE_PCT
        elif position <= self.STRONG_ZONE_PCT:
            signal_type = SignalType.BUY
            strength = min(0.7, 0.3 + (self.STRONG_ZONE_PCT - position) / self.STRONG_ZONE_PCT * 0.4)
            reason_parts.append(f"买入(价格{price:.4f}接近低点, 位置{position:.1%})")

        # 卖出区: (1 - STRONG_ZONE_PCT) <= position < 1
        elif position >= 1.0 - self.STRONG_ZONE_PCT:
            if position >= 1.0:
                # 强卖区: 价格在预测最高价以上
                signal_type = SignalType.STRONG_SELL
                depth = position - 1.0
                strength = min(1.0, 0.7 + depth * 2)
                reason_parts.append(f"强卖(价格{price:.4f}≥预测高点{pred_high:.4f})")
            else:
                signal_type = SignalType.SELL
                sell_depth = (position - (1.0 - self.STRONG_ZONE_PCT)) / self.STRONG_ZONE_PCT
                strength = min(0.7, 0.3 + sell_depth * 0.4)
                reason_parts.append(f"卖出(价格{price:.4f}接近高点, 位置{position:.1%})")

        # 观望区: 中间区域
        else:
            return self._hold_signal(
                snapshot, now,
                f"ML观望(位置{position:.1%}, 区间[{pred_low:.4f}~{pred_high:.4f}])"
            )

        # ---------- 折溢价安全网 ----------
        # 高溢价时不买入（防止在情绪溢价时追高）
        if signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
            if snapshot.premium_rate > 0.008:
                return self._hold_signal(
                    snapshot, now,
                    f"ML买入被高溢价({snapshot.premium_rate*100:.2f}%)拦截"
                )

        # 深折价时不卖出（防止恐慌割肉）
        if signal_type in (SignalType.SELL, SignalType.STRONG_SELL):
            if snapshot.premium_rate < -0.008:
                return self._hold_signal(
                    snapshot, now,
                    f"ML卖出被深折价({snapshot.premium_rate*100:.2f}%)拦截"
                )

        # ---------- 信号持久化校验 ----------
        prev_type, count = self._signal_persistence.get(code, (SignalType.HOLD, 0))

        def get_base_dir(st):
            if st in (SignalType.BUY, SignalType.STRONG_BUY): return "buy"
            if st in (SignalType.SELL, SignalType.STRONG_SELL): return "sell"
            return "hold"

        if get_base_dir(signal_type) == get_base_dir(prev_type) and signal_type != SignalType.HOLD:
            count += 1
        else:
            count = 1 if signal_type != SignalType.HOLD else 0

        self._signal_persistence[code] = (signal_type, count)

        # 至少连续 2 次确认
        if count < 2 and signal_type != SignalType.HOLD:
            return self._hold_signal(
                snapshot, now,
                f"ML信号确认中({count}/2), " + ", ".join(reason_parts)
            )

        # ---------- 冷却检查 ----------
        if self._is_cooling_down(code, signal_type):
            return self._hold_signal(
                snapshot, now,
                f"ML信号冷却中({signal_type.value})"
            )

        self._update_cooldown(code, signal_type)

        reason = f"[{self.name}] " + ", ".join(reason_parts)
        logger.info(
            f"[{code}] ML信号: {signal_type.value} | "
            f"强度: {strength:.2f} | 位置: {position:.1%} | {reason}"
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
        self._signal_persistence.clear()
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
        return (time.time() - tracker.get(direction, 0)) < SIGNAL_COOLDOWN_SECONDS

    def _update_cooldown(self, etf_code, signal_type):
        if etf_code not in self._cooldown_tracker:
            self._cooldown_tracker[etf_code] = {}
        direction = "buy" if signal_type in (SignalType.BUY, SignalType.STRONG_BUY) else "sell"
        self._cooldown_tracker[etf_code][direction] = time.time()
