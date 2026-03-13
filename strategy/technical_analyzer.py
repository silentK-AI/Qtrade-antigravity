"""
技术指标计算引擎

使用纯 numpy/pandas 计算核心技术指标（不依赖 TA-Lib），
为个股技术指标监控提供支撑位/压力位和交易信号检测。

支持指标:
- RSI (14日)
- MACD (12/26/9)
- KDJ (9/3/3)
- 布林带 (20日, 2σ)
- Pivot Point (经典轴心点)
- ATR (14日)
- 均线 (MA5/MA10/MA20/MA60)
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd
import numpy as np
from loguru import logger


# ------------------------------------------------------------------
#  数据结构定义
# ------------------------------------------------------------------

@dataclass
class TechnicalReport:
    """单标的技术分析报告"""
    symbol: str
    name: str
    price: float = 0.0
    prev_close: float = 0.0
    change_pct: float = 0.0

    # 支撑位和压力位
    support_s1: float = 0.0
    support_s2: float = 0.0
    resistance_r1: float = 0.0
    resistance_r2: float = 0.0
    pivot_point: float = 0.0

    # RSI
    rsi_14: float = 50.0
    rsi_status: str = "中性"     # 超买/偏强/中性/偏弱/超卖

    # MACD
    macd_dif: float = 0.0
    macd_dea: float = 0.0
    macd_hist: float = 0.0
    macd_status: str = "中性"    # 金叉/多头/死叉/空头

    # KDJ
    kdj_k: float = 50.0
    kdj_d: float = 50.0
    kdj_j: float = 50.0
    kdj_status: str = "中性"

    # 布林带
    boll_upper: float = 0.0
    boll_middle: float = 0.0
    boll_lower: float = 0.0
    boll_width: float = 0.0      # 带宽

    # ATR
    atr_14: float = 0.0
    volatility: str = "适中"     # 低/适中/高

    # 均线
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    ma60: float = 0.0
    ma5_trend: str = "→"         # ↑/↓/→
    ma10_trend: str = "→"
    ma20_trend: str = "→"

    # 量价关系
    volume_ratio: float = 1.0     # 量比（当日/5日均量）

    # 综合评分 (-100 到 100, 正=偏多 负=偏空)
    score: float = 0.0
    score_label: str = "中性"

    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AlertSignal:
    """交易信号（推送用）"""
    symbol: str
    name: str
    signal_type: str              # BUY / SELL / STOP_LOSS / TAKE_PROFIT
    price: float
    target_price: float = 0.0     # 目标价
    stop_price: float = 0.0       # 止损价
    reason: str = ""
    strength: float = 0.0         # 信号强度 0-1
    timestamp: datetime = field(default_factory=datetime.now)


# ------------------------------------------------------------------
#  核心计算引擎
# ------------------------------------------------------------------

class TechnicalAnalyzer:
    """
    技术指标分析引擎。

    用法:
        analyzer = TechnicalAnalyzer()
        report = analyzer.analyze(symbol, klines_df, realtime_quote)
        signals = analyzer.detect_trade_signals(report, prev_report)
    """

    # ------------------------------------------------------------------
    #  公开接口
    # ------------------------------------------------------------------

    def analyze(
        self,
        symbol: str,
        name: str,
        klines: pd.DataFrame,
        current_price: float = 0.0,
        current_volume: float = 0.0,
        prev_close: float = 0.0,
    ) -> Optional[TechnicalReport]:
        """
        生成完整技术分析报告。

        Args:
            symbol: 证券代码
            name: 证券名称
            klines: 历史日 K 线 DataFrame (需含 open/high/low/close/volume)
            current_price: 最新价（0 则使用 K 线最后一条 close）
            current_volume: 当日成交量
            prev_close: 前收盘价

        Returns:
            TechnicalReport 或 None（数据不足时）
        """
        if klines is None or len(klines) < 14:
            logger.warning(f"[{symbol}] K 线数据不足 ({len(klines) if klines is not None else 0} 条)")
            return None

        close = klines["close"].values.astype(float)
        high = klines["high"].values.astype(float)
        low = klines["low"].values.astype(float)
        volume = klines["volume"].values.astype(float)

        price = current_price if current_price > 0 else close[-1]
        pclose = prev_close if prev_close > 0 else close[-2] if len(close) >= 2 else close[-1]

        report = TechnicalReport(
            symbol=symbol,
            name=name,
            price=price,
            prev_close=pclose,
            change_pct=(price - pclose) / pclose * 100 if pclose > 0 else 0,
        )

        # 各指标计算
        self._calc_pivot_points(report, high, low, close)
        self._calc_rsi(report, close)
        self._calc_macd(report, close)
        self._calc_kdj(report, high, low, close)
        self._calc_bollinger(report, close, price)
        self._calc_atr(report, high, low, close)
        self._calc_moving_averages(report, close)
        self._calc_volume_ratio(report, volume, current_volume)
        self._calc_score(report)

        return report

    def detect_trade_signals(
        self,
        report: TechnicalReport,
        prev_report: Optional[TechnicalReport] = None,
    ) -> list[AlertSignal]:
        """
        根据技术报告检测交易信号。

        检测规则:
        - 买入: 价格触及 S1/S2 + RSI 偏弱/超卖 + MACD 柱放大
        - 止盈: 价格触及 R1/R2 + RSI 超买
        - 止损: 价格跌破 S2 + RSI 极端超卖

        Args:
            report: 当前技术报告
            prev_report: 上一次报告（用于检测交叉/趋势变化）

        Returns:
            触发的信号列表
        """
        signals = []
        price = report.price

        # ---- 买入信号 ----
        buy_reasons = []
        buy_strength = 0.0

        # 条件 1: 价格接近支撑位
        if report.support_s2 > 0 and price <= report.support_s2 * 1.005:
            buy_reasons.append(f"触及S2支撑位 {report.support_s2:.3f}")
            buy_strength += 0.35
        elif report.support_s1 > 0 and price <= report.support_s1 * 1.005:
            buy_reasons.append(f"触及S1支撑位 {report.support_s1:.3f}")
            buy_strength += 0.25

        # 条件 2: RSI 超卖
        if report.rsi_14 < 25:
            buy_reasons.append(f"RSI={report.rsi_14:.1f} 极端超卖")
            buy_strength += 0.30
        elif report.rsi_14 < 35:
            buy_reasons.append(f"RSI={report.rsi_14:.1f} 超卖区")
            buy_strength += 0.20

        # 条件 3: MACD 金叉
        if prev_report and report.macd_hist > 0 and prev_report.macd_hist <= 0:
            buy_reasons.append("MACD 金叉")
            buy_strength += 0.25
        elif report.macd_hist > 0 and report.macd_status in ("金叉", "多头"):
            buy_strength += 0.10

        # 条件 4: 布林带下轨附近
        if report.boll_lower > 0 and price <= report.boll_lower * 1.005:
            buy_reasons.append(f"触及布林下轨 {report.boll_lower:.3f}")
            buy_strength += 0.20

        # 条件 5: KDJ 超卖金叉
        if report.kdj_j < 20:
            buy_reasons.append(f"KDJ J={report.kdj_j:.0f} 超卖")
            buy_strength += 0.15

        # 满足至少 2 个条件且强度 >= 0.4 才触发
        if len(buy_reasons) >= 2 and buy_strength >= 0.4:
            signals.append(AlertSignal(
                symbol=report.symbol,
                name=report.name,
                signal_type="BUY",
                price=price,
                target_price=report.pivot_point,
                stop_price=report.support_s2 * 0.995 if report.support_s2 > 0 else price * 0.97,
                reason=" + ".join(buy_reasons),
                strength=min(buy_strength, 1.0),
            ))

        # ---- 止盈信号 ----
        tp_reasons = []
        tp_strength = 0.0

        if report.resistance_r1 > 0 and price >= report.resistance_r1 * 0.998:
            tp_reasons.append(f"触及R1压力位 {report.resistance_r1:.3f}")
            tp_strength += 0.30

        if report.resistance_r2 > 0 and price >= report.resistance_r2 * 0.998:
            tp_reasons.append(f"超越R2压力位 {report.resistance_r2:.3f}")
            tp_strength += 0.20

        if report.rsi_14 > 75:
            tp_reasons.append(f"RSI={report.rsi_14:.1f} 超买")
            tp_strength += 0.25
        elif report.rsi_14 > 65:
            tp_reasons.append(f"RSI={report.rsi_14:.1f} 偏强")
            tp_strength += 0.10

        if report.boll_upper > 0 and price >= report.boll_upper * 0.998:
            tp_reasons.append(f"触及布林上轨 {report.boll_upper:.3f}")
            tp_strength += 0.20

        if prev_report and report.macd_hist < 0 and prev_report.macd_hist >= 0:
            tp_reasons.append("MACD 死叉")
            tp_strength += 0.25

        if len(tp_reasons) >= 2 and tp_strength >= 0.4:
            signals.append(AlertSignal(
                symbol=report.symbol,
                name=report.name,
                signal_type="TAKE_PROFIT",
                price=price,
                reason=" + ".join(tp_reasons),
                strength=min(tp_strength, 1.0),
            ))

        # ---- 止损信号 ----
        sl_reasons = []

        if report.support_s2 > 0 and price < report.support_s2 * 0.995:
            sl_reasons.append(f"跌破S2支撑位 {report.support_s2:.3f}")

        if report.rsi_14 < 20:
            sl_reasons.append(f"RSI={report.rsi_14:.1f} 极端超卖")

        if report.boll_lower > 0 and price < report.boll_lower * 0.99:
            sl_reasons.append(f"跌破布林下轨 {report.boll_lower:.3f}")

        if len(sl_reasons) >= 2:
            signals.append(AlertSignal(
                symbol=report.symbol,
                name=report.name,
                signal_type="STOP_LOSS",
                price=price,
                reason=" + ".join(sl_reasons),
                strength=0.9,
            ))

        return signals

    # ------------------------------------------------------------------
    #  指标计算（内部）
    # ------------------------------------------------------------------

    def _calc_pivot_points(self, report: TechnicalReport, high: np.ndarray, low: np.ndarray, close: np.ndarray):
        """经典轴心点（基于前一日 H/L/C）"""
        if len(close) < 2:
            return
        prev_h = high[-2]
        prev_l = low[-2]
        prev_c = close[-2]

        pp = (prev_h + prev_l + prev_c) / 3
        r1 = 2 * pp - prev_l
        s1 = 2 * pp - prev_h
        r2 = pp + (prev_h - prev_l)
        s2 = pp - (prev_h - prev_l)

        report.pivot_point = round(pp, 3)
        report.resistance_r1 = round(r1, 3)
        report.resistance_r2 = round(r2, 3)
        report.support_s1 = round(s1, 3)
        report.support_s2 = round(s2, 3)

    def _calc_rsi(self, report: TechnicalReport, close: np.ndarray, period: int = 14):
        """RSI 相对强弱指标"""
        if len(close) < period + 1:
            return

        deltas = np.diff(close)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)

        # 使用 EMA 方式
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])

        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        report.rsi_14 = round(rsi, 2)

        if rsi >= 80:
            report.rsi_status = "超买"
        elif rsi >= 65:
            report.rsi_status = "偏强"
        elif rsi >= 35:
            report.rsi_status = "中性"
        elif rsi >= 20:
            report.rsi_status = "偏弱"
        else:
            report.rsi_status = "超卖"

    def _calc_macd(self, report: TechnicalReport, close: np.ndarray,
                   fast: int = 12, slow: int = 26, signal: int = 9):
        """MACD 指数平滑移动平均线"""
        if len(close) < slow + signal:
            return

        # EMA 计算
        ema_fast = self._ema(close, fast)
        ema_slow = self._ema(close, slow)
        dif = ema_fast - ema_slow
        dea = self._ema(dif, signal)
        hist = 2 * (dif - dea)  # MACD 柱

        report.macd_dif = round(dif[-1], 4)
        report.macd_dea = round(dea[-1], 4)
        report.macd_hist = round(hist[-1], 4)

        # 状态判断
        if len(hist) >= 2:
            if hist[-1] > 0 and hist[-2] <= 0:
                report.macd_status = "金叉"
            elif hist[-1] < 0 and hist[-2] >= 0:
                report.macd_status = "死叉"
            elif dif[-1] > dea[-1]:
                report.macd_status = "多头"
            else:
                report.macd_status = "空头"

    def _calc_kdj(self, report: TechnicalReport, high: np.ndarray, low: np.ndarray,
                  close: np.ndarray, n: int = 9, m1: int = 3, m2: int = 3):
        """KDJ 随机指标"""
        if len(close) < n:
            return

        # RSV 计算
        k_values = [50.0]  # K 初始值
        d_values = [50.0]  # D 初始值

        for i in range(n - 1, len(close)):
            period_high = np.max(high[i - n + 1: i + 1])
            period_low = np.min(low[i - n + 1: i + 1])

            if period_high == period_low:
                rsv = 50.0
            else:
                rsv = (close[i] - period_low) / (period_high - period_low) * 100

            k = (2 / m1) * k_values[-1] + (1 / m1) * rsv
            d = (2 / m2) * d_values[-1] + (1 / m2) * k
            k_values.append(k)
            d_values.append(d)

        k = k_values[-1]
        d = d_values[-1]
        j = 3 * k - 2 * d

        report.kdj_k = round(k, 2)
        report.kdj_d = round(d, 2)
        report.kdj_j = round(j, 2)

        if j > 100:
            report.kdj_status = "超买"
        elif k > 80 and d > 80:
            report.kdj_status = "偏强"
        elif j < 0:
            report.kdj_status = "超卖"
        elif k < 20 and d < 20:
            report.kdj_status = "偏弱"
        else:
            report.kdj_status = "中性"

    def _calc_bollinger(self, report: TechnicalReport, close: np.ndarray,
                        current_price: float, period: int = 20, num_std: float = 2.0):
        """布林带"""
        if len(close) < period:
            return

        sma = np.mean(close[-period:])
        std = np.std(close[-period:], ddof=1)

        upper = sma + num_std * std
        lower = sma - num_std * std

        report.boll_upper = round(upper, 3)
        report.boll_middle = round(sma, 3)
        report.boll_lower = round(lower, 3)
        report.boll_width = round((upper - lower) / sma * 100, 2) if sma > 0 else 0

    def _calc_atr(self, report: TechnicalReport, high: np.ndarray, low: np.ndarray,
                  close: np.ndarray, period: int = 14):
        """ATR 真实波幅"""
        if len(close) < period + 1:
            return

        tr = np.zeros(len(close) - 1)
        for i in range(1, len(close)):
            hl = high[i] - low[i]
            hc = abs(high[i] - close[i - 1])
            lc = abs(low[i] - close[i - 1])
            tr[i - 1] = max(hl, hc, lc)

        atr = np.mean(tr[-period:])
        report.atr_14 = round(atr, 4)

        # 波动率评级
        if close[-1] > 0:
            atr_pct = atr / close[-1] * 100
            if atr_pct < 1.5:
                report.volatility = "低"
            elif atr_pct < 3.0:
                report.volatility = "适中"
            else:
                report.volatility = "高"

    def _calc_moving_averages(self, report: TechnicalReport, close: np.ndarray):
        """均线 MA5/MA10/MA20/MA60"""
        for period, attr in [(5, "ma5"), (10, "ma10"), (20, "ma20"), (60, "ma60")]:
            if len(close) >= period:
                ma_val = np.mean(close[-period:])
                setattr(report, attr, round(ma_val, 3))

        # 均线趋势 (3 日方向)
        for period, attr in [(5, "ma5_trend"), (10, "ma10_trend"), (20, "ma20_trend")]:
            if len(close) >= period + 3:
                ma_now = np.mean(close[-period:])
                ma_prev = np.mean(close[-period - 3:-3])
                if ma_now > ma_prev * 1.001:
                    setattr(report, attr, "↑")
                elif ma_now < ma_prev * 0.999:
                    setattr(report, attr, "↓")
                else:
                    setattr(report, attr, "→")

    def _calc_volume_ratio(self, report: TechnicalReport, volume: np.ndarray,
                           current_volume: float = 0):
        """量比（当日成交量 / 近5日均量）"""
        if len(volume) < 5:
            return
        avg_vol = np.mean(volume[-5:])
        if avg_vol > 0:
            today_vol = current_volume if current_volume > 0 else volume[-1]
            report.volume_ratio = round(today_vol / avg_vol, 2)

    def _calc_score(self, report: TechnicalReport):
        """
        综合评分 (-100 到 100)。
        正值偏多，负值偏空。
        """
        score = 0.0

        # RSI 贡献 (-25 到 25)
        if report.rsi_14 > 70:
            score -= (report.rsi_14 - 70) * 0.5  # 超买扣分
        elif report.rsi_14 < 30:
            score += (30 - report.rsi_14) * 0.5  # 超卖加分（反转预期）
        else:
            score += (report.rsi_14 - 50) * 0.3  # 中性区域跟随

        # MACD 贡献 (-20 到 20)
        if report.macd_status == "金叉":
            score += 20
        elif report.macd_status == "死叉":
            score -= 20
        elif report.macd_status == "多头":
            score += 10
        elif report.macd_status == "空头":
            score -= 10

        # 均线排列 (-15 到 15)
        if report.ma5 > report.ma10 > report.ma20 > 0:
            score += 15  # 多头排列
        elif report.ma5 < report.ma10 < report.ma20 and report.ma20 > 0:
            score -= 15  # 空头排列

        # 价格位置 (-15 到 15)
        if report.boll_upper > 0 and report.boll_lower > 0:
            band_range = report.boll_upper - report.boll_lower
            if band_range > 0:
                position = (report.price - report.boll_lower) / band_range
                score += (0.5 - position) * 20  # 靠近下轨加分，靠近上轨减分

        # KDJ 贡献 (-10 到 10)
        if report.kdj_status == "超卖":
            score += 10
        elif report.kdj_status == "超买":
            score -= 10
        elif report.kdj_j < 30:
            score += 5
        elif report.kdj_j > 70:
            score -= 5

        # 量比
        if report.volume_ratio > 2.0:
            score += 5  # 放量
        elif report.volume_ratio < 0.5:
            score -= 3  # 缩量

        report.score = round(max(-100, min(100, score)), 1)

        if score > 30:
            report.score_label = "强势看多"
        elif score > 10:
            report.score_label = "偏多"
        elif score > -10:
            report.score_label = "中性"
        elif score > -30:
            report.score_label = "偏空"
        else:
            report.score_label = "强势看空"

    # ------------------------------------------------------------------
    #  工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _ema(data: np.ndarray, period: int) -> np.ndarray:
        """计算 EMA (Exponential Moving Average)"""
        k = 2 / (period + 1)
        ema = np.zeros_like(data, dtype=float)
        ema[0] = data[0]
        for i in range(1, len(data)):
            ema[i] = data[i] * k + ema[i - 1] * (1 - k)
        return ema

    # ------------------------------------------------------------------
    #  格式化输出
    # ------------------------------------------------------------------

    @staticmethod
    def format_report(report: TechnicalReport) -> str:
        """将 TechnicalReport 格式化为微信推送的 Markdown 文本"""
        change_icon = "🔴" if report.change_pct < 0 else "🟢" if report.change_pct > 0 else "⚪"
        rsi_icon = "🔴" if report.rsi_status == "超买" else "🟢" if report.rsi_status in ("超卖", "偏弱") else "⚪"

        lines = [
            f"**【{report.symbol} {report.name}】** {change_icon} ¥{report.price:.3f} ({report.change_pct:+.2f}%)",
            f"━━━━━━━━━━━━━━━━━",
            f"📌 **支撑/压力位**",
            f"  压力: R2={report.resistance_r2:.3f}  R1={report.resistance_r1:.3f}",
            f"  轴心: PP={report.pivot_point:.3f}",
            f"  支撑: S1={report.support_s1:.3f}  S2={report.support_s2:.3f}",
            f"",
            f"📊 **核心指标**",
            f"  {rsi_icon} RSI(14): {report.rsi_14:.1f} ({report.rsi_status})",
            f"  MACD: DIF={report.macd_dif:.4f} DEA={report.macd_dea:.4f} 柱={report.macd_hist:.4f} ({report.macd_status})",
            f"  KDJ: K={report.kdj_k:.0f} D={report.kdj_d:.0f} J={report.kdj_j:.0f} ({report.kdj_status})",
            f"",
            f"📈 **布林带**",
            f"  上轨={report.boll_upper:.3f}  中轨={report.boll_middle:.3f}  下轨={report.boll_lower:.3f}",
            f"  带宽: {report.boll_width:.1f}%",
            f"",
            f"📏 **均线**",
            f"  5日={report.ma5:.3f}{report.ma5_trend}  10日={report.ma10:.3f}{report.ma10_trend}  20日={report.ma20:.3f}{report.ma20_trend}",
            f"  60日={report.ma60:.3f}",
            f"",
            f"⚡ **波动/量价**",
            f"  ATR(14): {report.atr_14:.4f} ({report.volatility})",
            f"  量比: {report.volume_ratio:.2f}",
            f"",
            f"🎯 **综合评分: {report.score:+.0f} ({report.score_label})**",
        ]
        return "\n".join(lines)

    @staticmethod
    def format_signal(signal: AlertSignal) -> str:
        """将 AlertSignal 格式化为微信推送文本"""
        type_map = {
            "BUY": "🟢 买入信号",
            "SELL": "🔴 卖出信号",
            "TAKE_PROFIT": "🟡 止盈信号",
            "STOP_LOSS": "🔴 止损信号",
        }
        label = type_map.get(signal.signal_type, signal.signal_type)

        lines = [
            f"当前价: ¥{signal.price:.3f}",
        ]

        if signal.target_price > 0:
            lines.append(f"目标价: ¥{signal.target_price:.3f}")
        if signal.stop_price > 0:
            lines.append(f"止损价: ¥{signal.stop_price:.3f}")

        lines.append(f"信号强度: {'★' * int(signal.strength * 5)}{'☆' * (5 - int(signal.strength * 5))}")
        lines.append(f"触发原因: {signal.reason}")

        return "\n".join(lines)

    @staticmethod
    def format_signal_title(signal: AlertSignal) -> str:
        """生成推送标题：含标的名称和动作，不点开就能看到关键信息"""
        type_map = {
            "BUY": "买入",
            "SELL": "卖出",
            "TAKE_PROFIT": "止盈",
            "STOP_LOSS": "止损",
        }
        action = type_map.get(signal.signal_type, signal.signal_type)
        icon_map = {
            "BUY": "🟢",
            "SELL": "🔴",
            "TAKE_PROFIT": "🟡",
            "STOP_LOSS": "🔴",
        }
        icon = icon_map.get(signal.signal_type, "")
        return f"{icon}【{action}】{signal.name}({signal.symbol}) ¥{signal.price:.3f}"
