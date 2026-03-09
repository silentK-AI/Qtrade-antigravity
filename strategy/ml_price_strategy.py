"""
ML 价格预测策略（PP 混合区间版）

结合 ML 方向预测和 Pivot Point 点位：
- 买入: ML 预测高点 >= PP，且当前价格 <= S1（或 S2 强买）
- 卖出: 当前持有多头，且当前价格 >= PP（或 R1 强卖）
- 止损: 当前持有多头，且当前价格 <= S2（无条件强卖）
"""
import time
from datetime import datetime
from loguru import logger

from strategy.base_strategy import BaseStrategy
from strategy.signal import MarketSnapshot, TradingSignal, SignalType
from strategy.ml_predictor import MLPredictor, PricePrediction
from config.etf_settings import (
    SIGNAL_COOLDOWN_SECONDS,
    ML_PRED_CONFIDENCE_THRESHOLD,
)


class MLPriceStrategy(BaseStrategy):
    """
    基于 ML 方向预测 + Pivot Point 点位的混合策略。
    
    信号触发点位：
    - 买入 (BUY): 价格 <= S1
    - 强买 (STRONG_BUY): 价格 <= S2
    - 卖出 (SELL): 价格 >= PP
    - 强卖 (STRONG_SELL): 价格 >= R1 或 价格 <= S2 (止损)
    """

    def __init__(self, predictor: MLPredictor):
        self._predictor = predictor
        # {etf_code: PricePrediction}
        self._daily_predictions: dict[str, PricePrediction] = {}
        # {etf_code: dict_of_pp_levels}
        self._daily_pp_levels: dict[str, dict[str, float]] = {}
        self._cooldown_tracker: dict[str, dict[str, float]] = {}
        # 信号持久化追踪: {etf_code: (signal_type, count)}
        self._signal_persistence: dict[str, tuple[SignalType, int]] = {}

    @property
    def name(self) -> str:
        return "ML+PP混合策略"

    def set_daily_data(
        self, 
        predictions: dict[str, PricePrediction],
        pp_levels: dict[str, dict[str, float]]
    ) -> None:
        """
        每日开盘前设置 ML 预测值和 PP 点位。

        Args:
            predictions: {etf_code: PricePrediction}
            pp_levels: {etf_code: {"PP": x, "S1": x, "S2": x, "R1": x, "R2": x}}
        """
        self._daily_predictions = predictions
        self._daily_pp_levels = pp_levels
        
        for code, pred in predictions.items():
            pp = pp_levels.get(code)
            if pp:
                logger.info(
                    f"[{code}] 策略数据更新 - "
                    f"ML预测High={pred.predicted_high:.4f} | "
                    f"PP={pp['PP']:.4f}, S1={pp['S1']:.4f}, S2={pp['S2']:.4f}"
                )

    def evaluate(self, snapshot: MarketSnapshot, has_position: bool = False) -> TradingSignal:
        """
        根据当前价格在 PP 点位的位置，结合 ML 的高点预测生成信号。
        
        Args:
            snapshot: 行情快照
            has_position: 当前是否持有该 ETF 的仓位，影响卖出/止损判断
        """
        code = snapshot.etf_code
        now = datetime.now()

        # 无预测或 PP 数据
        pred = self._daily_predictions.get(code)
        pp = self._daily_pp_levels.get(code)
        
        if pred is None or pp is None:
            return self._hold_signal(snapshot, now, "无ML预测或PP数据")

        # 置信度不足
        if pred.confidence < ML_PRED_CONFIDENCE_THRESHOLD:
            return self._hold_signal(
                snapshot, now,
                f"ML置信度不足({pred.confidence:.2f}<{ML_PRED_CONFIDENCE_THRESHOLD})"
            )

        price = snapshot.etf_price
        if price <= 0:
            return self._hold_signal(snapshot, now, "价格无效")

        # ---------- 获取关键点位 ----------
        # 为了宽松触发，允许点位周围有 0.15% 的容差
        tolerance = 0.0015
        
        S2_threshold = pp["S2"] * (1 + tolerance)
        S1_threshold = pp["S1"] * (1 + tolerance)
        PP_threshold = pp["PP"] * (1 - tolerance)
        R1_threshold = pp["R1"] * (1 - tolerance)

        # ML 认为今天能涨到哪
        ml_target_high = pred.predicted_high

        signal_type = SignalType.HOLD
        strength = 0.0
        reason_parts = []

        # ==========================================
        # 1. 卖出逻辑 (如果有持仓)
        # ==========================================
        if has_position:
            # 止损: 跌破 S2 或接近 S2
            if price <= pp["S2"] * (1 + tolerance*2):
                signal_type = SignalType.STRONG_SELL
                strength = 1.0
                reason_parts.append(f"止损(价格{price:.4f}跌至S2:{pp['S2']:.4f})")
            
            # 强卖止盈: 涨到 R1 或接近 ML 预测高点
            elif price >= R1_threshold or price >= ml_target_high * 0.998:
                signal_type = SignalType.STRONG_SELL
                strength = 0.9
                reason_parts.append(f"强卖止盈(价格{price:.4f}到达R1或ML预测顶)")
                
            # 卖出止盈: 涨到 PP
            elif price >= PP_threshold:
                signal_type = SignalType.SELL
                strength = 0.7
                reason_parts.append(f"卖出止盈(价格{price:.4f}到达PP:{pp['PP']:.4f})")

        # ==========================================
        # 2. 买入逻辑 (且当前没有发出卖出信号)
        # ==========================================
        if signal_type == SignalType.HOLD:
            # ---------- ML 空间过滤 ----------
            # 要求 ML 预测高点至少比当前价格高 0.3%，保证有微小回调反弹空间
            if ml_target_high < price * 1.003:
                return self._hold_signal(
                    snapshot, now,
                    f"ML过滤: 预期反弹太弱 (预测高{ml_target_high:.4f} 距当前不足0.3%)"
                )
                
            # ---------- 新增高频买入逻辑 ----------
            # 高频进场点：只要低于 PP，并在 S1 与 PP 之间微跌处
            # 设定为 PP 往下走 20% 到 S1 距离处（小回调即入）
            fast_buy_threshold = pp["PP"] - (pp["PP"] - pp["S1"]) * 0.2
            
            # ---------- 点位触发 ----------
            if price <= pp["S2"]:
                # 极端超跌情况
                signal_type = SignalType.STRONG_BUY
                strength = 0.9
                reason_parts.append(f"强买(价格{price:.4f}落入S2:{pp['S2']:.4f})")
                
            elif price <= S1_threshold:
                # 正常 S1 支撑
                signal_type = SignalType.BUY
                strength = 0.7
                reason_parts.append(f"买入(价格{price:.4f}落入S1:{pp['S1']:.4f})")

            elif price <= fast_buy_threshold:
                # 高频微跌买入
                signal_type = SignalType.BUY
                strength = 0.5
                reason_parts.append(f"轻买(微跌买入,低于{fast_buy_threshold:.4f})")

        # 观望区: 中间区域或不需要操作
        if signal_type == SignalType.HOLD:
            return self._hold_signal(
                snapshot, now,
                f"区间震荡(价格{price:.4f}, S1={pp['S1']:.4f}, PP={pp['PP']:.4f})"
            )

        # ---------- 折溢价安全网 ----------
        if signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
            if snapshot.premium_rate > 0.008:
                return self._hold_signal(
                    snapshot, now,
                    f"买入被高溢价({snapshot.premium_rate*100:.2f}%)拦截"
                )

        if signal_type in (SignalType.SELL, SignalType.STRONG_SELL) and reason_parts and "止盈" in reason_parts[0]:
            if snapshot.premium_rate < -0.008:
                return self._hold_signal(
                    snapshot, now,
                    f"止盈被深折价({snapshot.premium_rate*100:.2f}%)拦截"
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

        # 至少连续 2 次确认 (防止一笔异常 tick)
        if count < 2 and signal_type != SignalType.HOLD:
            return self._hold_signal(
                snapshot, now,
                f"信号确认中({count}/2), " + ", ".join(reason_parts)
            )

        # ---------- 冷却检查 ----------
        if self._is_cooling_down(code, signal_type):
            return self._hold_signal(
                snapshot, now,
                f"信号冷却中({signal_type.value})"
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
        self._daily_pp_levels.clear()
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
