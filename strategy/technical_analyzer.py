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
    ma120: float = 0.0
    ma250: float = 0.0
    ma5_trend: str = "→"         # ↑/↓/→
    ma10_trend: str = "→"
    ma20_trend: str = "→"

    # 量价关系
    volume_ratio: float = 1.0     # 量比（当日/5日均量）

    # 当日开高低收
    today_open: float = 0.0
    day_high: float = 0.0
    day_low: float = 0.0

    # 区间涨跌幅（从 K 线历史计算）
    ret_10d: float = 0.0          # 近10日涨跌幅
    ret_60d: float = 0.0          # 近60日（约3月）涨跌幅
    ret_250d: float = 0.0         # 近250日（约1年）涨跌幅

    # 主力资金净流入（亿元，正=净流入，负=净流出，0=无数据）
    net_flow_main: float = 0.0
    net_flow_valid: bool = False   # 是否有有效资金流数据

    # 综合评分 (-100 到 100, 正=偏多 负=偏空)
    score: float = 0.0
    score_label: str = "中性"

    # XGBoost 次日价格预测
    pred_high: float = 0.0        # 预测次日最高价
    pred_low: float = 0.0         # 预测次日最低价
    pred_range_pct: float = 0.0   # 预测波动率 (%)
    pred_confidence: float = 0.0  # 模型置信度 (R²)
    pred_hit_high: bool = False   # 盘中是否已触及预测最高价
    pred_hit_low: bool = False    # 盘中是否已触及预测最低价

    # LLM 基本面综合评估
    llm_fundamental_analysis: str = ""

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
        self._calc_period_returns(report, close)
        self._calc_score(report)

        # 当日高低价（从 K 线最后一条取）
        report.day_high = round(float(high[-1]), 3)
        report.day_low = round(float(low[-1]), 3)

        return report

    def detect_trade_signals(
        self,
        report: TechnicalReport,
        prev_report: Optional[TechnicalReport] = None,
    ) -> list[AlertSignal]:
        """
        根据技术报告检测交易信号。

        优化后的检测规则:
        - 趋势过滤: 均线空头排列时禁止 BUY；多头排列时 STOP_LOSS 门槛收紧
        - 量能确认: 放量（量比>1.5）加权，缩量（量比<0.6）降权
        - MACD 防假叉: 需连续 2 根柱同向才确认金叉/死叉
        - 多重支撑共振: Pivot S1/S2 + 布林下轨 + MA20 三者叠加给更高权重
        - BUY 门槛: 强度 >= 0.55 且 >= 3 个条件
        - 新增 SELL 信号: 趋势由多转空时主动提示

        Args:
            report: 当前技术报告
            prev_report: 上一次报告（用于检测交叉/趋势变化）

        Returns:
            触发的信号列表
        """
        signals = []
        price = report.price

        # ── 死区过滤 (Deadzone Filter) ──────────────────────────────
        # 若日内涨跌幅在绝对值 0.5% 以内，视作死水横盘，屏蔽所有低评级的常规技术信号
        # 以免反复在均线附近金叉死叉造成无穷打扰。止损信号不受影响。
        is_deadzone = abs(report.change_pct) < 0.5

        # ── 预计算公共状态 ──────────────────────────────────────────
        # 趋势状态
        trend_bull = (
            report.ma5 > 0 and report.ma10 > 0 and report.ma20 > 0
            and report.ma5 > report.ma10 > report.ma20
        )
        trend_bear = (
            report.ma5 > 0 and report.ma10 > 0 and report.ma20 > 0
            and report.ma5 < report.ma10 < report.ma20
        )

        # 量能状态
        vol_strong = report.volume_ratio >= 1.5   # 明显放量
        vol_weak = report.volume_ratio < 0.6      # 明显缩量
        vol_bonus = 0.10 if vol_strong else (-0.08 if vol_weak else 0.0)

        # MACD 防假叉：判断 prev_report 的柱子方向（需连续 2 根才确认）
        macd_golden = (
            prev_report is not None
            and report.macd_hist > 0
            and prev_report.macd_hist <= 0
        )
        macd_death = (
            prev_report is not None
            and report.macd_hist < 0
            and prev_report.macd_hist >= 0
        )
        # 持续多头/空头（非刚交叉，连续在一侧）
        macd_bull_cont = report.macd_status == "多头" and report.macd_hist > 0
        macd_bear_cont = report.macd_status == "空头" and report.macd_hist < 0

        # 布林带位置（0=下轨, 1=上轨）
        boll_pos: float = 0.5
        if report.boll_upper > report.boll_lower > 0:
            boll_pos = (price - report.boll_lower) / (report.boll_upper - report.boll_lower)

        # 多重支撑共振计数（布林下轨 + MA20 + S1/S2 靠近）
        support_resonance = 0
        if report.boll_lower > 0 and price <= report.boll_lower * 1.008:
            support_resonance += 1
        if report.ma20 > 0 and price <= report.ma20 * 1.008:
            support_resonance += 1
        if report.support_s1 > 0 and price <= report.support_s1 * 1.008:
            support_resonance += 1
        if report.support_s2 > 0 and price <= report.support_s2 * 1.008:
            support_resonance += 1

        # 多重压力共振计数（布林上轨 + MA20 + R1/R2 靠近）
        resist_resonance = 0
        if report.boll_upper > 0 and price >= report.boll_upper * 0.992:
            resist_resonance += 1
        if report.ma20 > 0 and price >= report.ma20 * 0.992:
            resist_resonance += 1
        if report.resistance_r1 > 0 and price >= report.resistance_r1 * 0.992:
            resist_resonance += 1
        if report.resistance_r2 > 0 and price >= report.resistance_r2 * 0.992:
            resist_resonance += 1

        # ── 买入信号 ────────────────────────────────────────────────
        # 趋势过滤：空头排列时不发 BUY
        if not trend_bear:
            buy_reasons = []
            buy_strength = 0.0

            # 条件 1: 多重支撑共振（权重随共振数量递增）
            if support_resonance >= 3:
                buy_reasons.append(f"三重支撑共振（布林下轨/MA20/Pivot）")
                buy_strength += 0.35
            elif support_resonance == 2:
                # 标注具体是哪两个支撑
                sup_tags = []
                if report.boll_lower > 0 and price <= report.boll_lower * 1.008:
                    sup_tags.append(f"布林下轨{report.boll_lower:.3f}")
                if report.ma20 > 0 and price <= report.ma20 * 1.008:
                    sup_tags.append(f"MA20={report.ma20:.3f}")
                if report.support_s1 > 0 and price <= report.support_s1 * 1.008:
                    sup_tags.append(f"S1={report.support_s1:.3f}")
                if report.support_s2 > 0 and price <= report.support_s2 * 1.008:
                    sup_tags.append(f"S2={report.support_s2:.3f}")
                buy_reasons.append("双重支撑共振（" + "/".join(sup_tags) + ")")
                buy_strength += 0.25
            elif report.support_s2 > 0 and price <= report.support_s2 * 1.005:
                buy_reasons.append(f"触及S2支撑位 {report.support_s2:.3f}")
                buy_strength += 0.20
            elif report.support_s1 > 0 and price <= report.support_s1 * 1.005:
                buy_reasons.append(f"触及S1支撑位 {report.support_s1:.3f}")
                buy_strength += 0.15

            # 条件 2: RSI 超卖
            if report.rsi_14 < 25:
                buy_reasons.append(f"RSI={report.rsi_14:.1f} 极端超卖")
                buy_strength += 0.30
            elif report.rsi_14 < 32:
                buy_reasons.append(f"RSI={report.rsi_14:.1f} 超卖区")
                buy_strength += 0.18

            # 条件 3: MACD（防假叉：要求真实金叉，而非持续多头加分）
            if macd_golden:
                buy_reasons.append("MACD 金叉确认")
                buy_strength += 0.25
            elif macd_bull_cont and report.macd_dif > 0:  # 零轴上方多头，信号更可靠
                buy_reasons.append("MACD 零轴上方多头")
                buy_strength += 0.10

            # 条件 4: KDJ 超卖
            if report.kdj_j < 10:
                buy_reasons.append(f"KDJ J={report.kdj_j:.0f} 深度超卖")
                buy_strength += 0.20
            elif report.kdj_j < 20:
                buy_reasons.append(f"KDJ J={report.kdj_j:.0f} 超卖")
                buy_strength += 0.12

            # 条件 5: 趋势加成（多头排列额外加权）
            if trend_bull:
                buy_reasons.append("均线多头排列")
                buy_strength += 0.12

            # 量能加减权
            buy_strength += vol_bonus
            if vol_strong:
                buy_reasons.append(f"放量确认（量比{report.volume_ratio:.1f}x）")
            elif vol_weak:
                buy_reasons.append(f"缩量（量比{report.volume_ratio:.1f}x，信号偏弱）")

            # 门槛收紧：需 >= 3 个条件且强度 >= 0.65，且不在横盘死区
            if len(buy_reasons) >= 3 and buy_strength >= 0.65 and not is_deadzone:
                # 止损价：S2 下方 0.5%，无 S2 则用 ATR 动态止损
                if report.support_s2 > 0:
                    stop = report.support_s2 * 0.995
                elif report.atr_14 > 0:
                    stop = price - 2 * report.atr_14
                else:
                    stop = price * 0.97
                # 目标价：取 R1 或 ATR 2 倍上方
                if report.resistance_r1 > 0:
                    target = report.resistance_r1
                elif report.atr_14 > 0:
                    target = price + 2 * report.atr_14
                else:
                    target = report.pivot_point
                signals.append(AlertSignal(
                    symbol=report.symbol,
                    name=report.name,
                    signal_type="BUY",
                    price=price,
                    target_price=round(target, 3),
                    stop_price=round(stop, 3),
                    reason=" + ".join(buy_reasons),
                    strength=min(buy_strength, 1.0),
                ))

        # ── 止盈信号 ────────────────────────────────────────────────
        tp_reasons = []
        tp_strength = 0.0

        # 多重压力共振（权重递增）
        if resist_resonance >= 3:
            tp_reasons.append("三重压力共振（布林上轨/MA20/Pivot）")
            tp_strength += 0.35
        elif resist_resonance == 2:
            res_tags = []
            if report.boll_upper > 0 and price >= report.boll_upper * 0.992:
                res_tags.append(f"布林上轨{report.boll_upper:.3f}")
            if report.ma20 > 0 and price >= report.ma20 * 0.992:
                res_tags.append(f"MA20={report.ma20:.3f}")
            if report.resistance_r1 > 0 and price >= report.resistance_r1 * 0.992:
                res_tags.append(f"R1={report.resistance_r1:.3f}")
            if report.resistance_r2 > 0 and price >= report.resistance_r2 * 0.992:
                res_tags.append(f"R2={report.resistance_r2:.3f}")
            tp_reasons.append("双重压力共振（" + "/".join(res_tags) + ")")
            tp_strength += 0.25
        elif report.resistance_r2 > 0 and price >= report.resistance_r2 * 0.998:
            tp_reasons.append(f"超越R2压力位 {report.resistance_r2:.3f}")
            tp_strength += 0.20
        elif report.resistance_r1 > 0 and price >= report.resistance_r1 * 0.998:
            tp_reasons.append(f"触及R1压力位 {report.resistance_r1:.3f}")
            tp_strength += 0.15

        if report.rsi_14 > 78:
            tp_reasons.append(f"RSI={report.rsi_14:.1f} 极端超买")
            tp_strength += 0.30
        elif report.rsi_14 > 68:
            tp_reasons.append(f"RSI={report.rsi_14:.1f} 超买区")
            tp_strength += 0.18

        if macd_death:
            tp_reasons.append("MACD 死叉确认")
            tp_strength += 0.25
        elif macd_bear_cont and report.macd_dif < 0:
            tp_reasons.append("MACD 零轴下方空头")
            tp_strength += 0.10

        if report.kdj_j > 90:
            tp_reasons.append(f"KDJ J={report.kdj_j:.0f} 深度超买")
            tp_strength += 0.20
        elif report.kdj_j > 80:
            tp_reasons.append(f"KDJ J={report.kdj_j:.0f} 超买")
            tp_strength += 0.12

        # 量能加减权（止盈时放量更危险）
        tp_strength += vol_bonus
        if vol_strong:
            tp_reasons.append(f"放量见顶风险（量比{report.volume_ratio:.1f}x）")

        if len(tp_reasons) >= 2 and tp_strength >= 0.55 and not is_deadzone:
            signals.append(AlertSignal(
                symbol=report.symbol,
                name=report.name,
                signal_type="TAKE_PROFIT",
                price=price,
                reason=" + ".join(tp_reasons),
                strength=min(tp_strength, 1.0),
            ))

        # ── SELL 信号（趋势由多转空）────────────────────────────────
        # 条件：上一次是多头排列，现在转为空头排列 + MACD 死叉确认
        if prev_report is not None:
            prev_trend_bull = (
                prev_report.ma5 > 0 and prev_report.ma10 > 0 and prev_report.ma20 > 0
                and prev_report.ma5 > prev_report.ma10 > prev_report.ma20
            )
            if prev_trend_bull and trend_bear and macd_death:
                sell_reason = (
                    f"均线由多头转空头排列 + MACD死叉"
                    f"（MA5={report.ma5:.3f} MA10={report.ma10:.3f} MA20={report.ma20:.3f}）"
                )
                signals.append(AlertSignal(
                    symbol=report.symbol,
                    name=report.name,
                    signal_type="SELL",
                    price=price,
                    stop_price=round(price * 1.03, 3),  # 止损在上方 3%
                    reason=sell_reason,
                    strength=0.85,
                ))

        # ── 止损信号 ────────────────────────────────────────────────
        # 趋势过滤：多头排列时 STOP_LOSS 需更严格（至少 3 个条件）
        sl_reasons = []
        sl_strength = 0.0

        # 条件 1: 跌破关键支撑（叠加计分）
        if report.support_s2 > 0 and price < report.support_s2 * 0.995:
            sl_reasons.append(f"跌破S2支撑 {report.support_s2:.3f}")
            sl_strength += 0.35
        elif report.support_s1 > 0 and price < report.support_s1 * 0.995:
            sl_reasons.append(f"跌破S1支撑 {report.support_s1:.3f}")
            sl_strength += 0.20

        # 条件 2: RSI 极端超卖（已跌过头，说明趋势极弱）
        if report.rsi_14 < 18:
            sl_reasons.append(f"RSI={report.rsi_14:.1f} 极端超卖")
            sl_strength += 0.30
        elif report.rsi_14 < 25:
            sl_reasons.append(f"RSI={report.rsi_14:.1f} 深度超卖")
            sl_strength += 0.18

        # 条件 3: 跌破布林下轨
        if report.boll_lower > 0 and price < report.boll_lower * 0.992:
            sl_reasons.append(f"跌破布林下轨 {report.boll_lower:.3f}")
            sl_strength += 0.25

        # 条件 4: MACD 死叉
        if macd_death:
            sl_reasons.append("MACD 死叉")
            sl_strength += 0.15

        # 多头排列中需更严格（3 个条件才止损，避免洗盘误报）
        sl_min_conditions = 3 if trend_bull else 2
        sl_min_strength = 0.65 if trend_bull else 0.50

        if len(sl_reasons) >= sl_min_conditions and sl_strength >= sl_min_strength:
            signals.append(AlertSignal(
                symbol=report.symbol,
                name=report.name,
                signal_type="STOP_LOSS",
                price=price,
                reason=" + ".join(sl_reasons),
                strength=min(sl_strength, 1.0),
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
        """均线 MA5/MA10/MA20/MA60/MA120/MA250"""
        for period, attr in [(5, "ma5"), (10, "ma10"), (20, "ma20"), (60, "ma60"), (120, "ma120"), (250, "ma250")]:
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

    def _calc_period_returns(self, report: TechnicalReport, close: np.ndarray):
        """计算近 10/60/250 日区间涨跌幅"""
        cur = close[-1] if len(close) > 0 else 0
        if cur <= 0:
            return
        for n, attr in [(10, "ret_10d"), (60, "ret_60d"), (250, "ret_250d")]:
            if len(close) > n:
                base = close[-(n + 1)]
                if base > 0:
                    setattr(report, attr, round((cur - base) / base * 100, 2))

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
    def get_conclusion(score: float) -> str:
        if score > 40:
            return "短期技术偏强，多头格局延续，可积极关注。"
        elif score > 15:
            return "中期趋势向好，短期有所分歧，建议观望择机介入。"
        elif score > -15:
            return "技术指标中性，多空均衡，短期方向不明，宜观望为主。"
        elif score > -40:
            return "短期技术走弱，建议谨慎，等待企稳信号后再考虑介入。"
        else:
            return "技术指标全面走弱，空头占优，建议回避或减仓观望。"

    @staticmethod
    def _format_header_and_quotes(report: TechnicalReport) -> list[str]:
        _ts = report.timestamp
        now_str = f"{_ts.year}年{_ts.month}月{_ts.day}日 {_ts.strftime('%H:%M')}"
        change_icon = "📉" if report.change_pct < 0 else "📈" if report.change_pct > 0 else "➡️"
        conclusion = TechnicalAnalyzer.get_conclusion(report.score)

        lines = [
            f"**{report.name}（{report.symbol}）** — 截至 {now_str}",
            f"{conclusion}",
        ]

        # 使用开盘价作为预测涨跌的锚定点（避免盘后运行由于收盘价上涨导致的假性偏空）
        anchor = report.today_open if report.today_open > 0 else report.price
        
        if report.pred_high > 0 and report.pred_low > 0 and anchor > 0:
            mid = (report.pred_high + report.pred_low) / 2
            pred_dir_pct = (mid - anchor) / anchor * 100
            
            # 如果是盘中或盘后运行，说明是预测“今日”；如果是盘前运行，则是预测“今日”
            # 为避免歧义，统一改为“今日预测”
            if pred_dir_pct > 0:
                pred_color = f"**🔴 今日预测偏多 +{pred_dir_pct:.2f}%**（高 {report.pred_high:.3f} / 低 {report.pred_low:.3f}）"
            else:
                pred_color = f"**🟢 今日预测偏空 {pred_dir_pct:.2f}%**（高 {report.pred_high:.3f} / 低 {report.pred_low:.3f}）"
            lines.append(pred_color)

        lines.append("")
        lines.append(f"**一、核心行情**")
        chg_str = f"{report.change_pct:+.2f}%"
        lines.append(f"股价：{report.price:.3f} 元，当日 **{chg_str}** {change_icon}")
        if report.day_high > 0 and report.day_low > 0:
            lines.append(f"当日最高 {report.day_high:.3f} 元 / 最低 {report.day_low:.3f} 元")

        ret_parts = []
        if report.ret_10d != 0: ret_parts.append(f"近10日 {report.ret_10d:+.1f}%")
        if report.ret_60d != 0: ret_parts.append(f"近3月 {report.ret_60d:+.1f}%")
        if report.ret_250d != 0: ret_parts.append(f"近1年 {report.ret_250d:+.1f}%")
        if ret_parts: lines.append("区间涨跌：" + " | ".join(ret_parts))

        if report.net_flow_valid:
            flow_icon = "📥" if report.net_flow_main > 0 else "📤"
            flow_word = "净流入" if report.net_flow_main > 0 else "净流出"
            lines.append(f"主力资金：{flow_icon} {flow_word} {abs(report.net_flow_main):.2f} 亿元")
        lines.append("")
        return lines

    @staticmethod
    def _format_tech_details(report: TechnicalReport) -> list[str]:
        lines = []
        lines.append(f"**二、关键技术指标（日线）**")
        lines.append(f"**1. 趋势与均线**")
        ma_parts = []
        if report.ma5 > 0:   ma_parts.append(f"MA5={report.ma5:.3f}{report.ma5_trend}")
        if report.ma10 > 0:  ma_parts.append(f"MA10={report.ma10:.3f}{report.ma10_trend}")
        if report.ma20 > 0:  ma_parts.append(f"MA20={report.ma20:.3f}{report.ma20_trend}")
        if report.ma60 > 0:  ma_parts.append(f"MA60={report.ma60:.3f}")
        if report.ma120 > 0: ma_parts.append(f"MA120={report.ma120:.3f}")
        if report.ma250 > 0: ma_parts.append(f"MA250={report.ma250:.3f}")
        if ma_parts:
            lines.append("  " + "  ".join(ma_parts))

        if report.ma5 > 0 and report.ma10 > 0 and report.ma20 > 0:
            if report.ma5 > report.ma10 > report.ma20:
                lines.append("  多头排列（MA5>MA10>MA20），中期上升趋势延续")
            elif report.ma5 < report.ma10 < report.ma20:
                lines.append("  空头排列（MA5<MA10<MA20），中期下降趋势")
            else:
                lines.append("  均线交织，趋势不明朗，震荡格局")

        if report.ma5 > 0:
            rel5 = (report.price - report.ma5) / report.ma5 * 100
            pos5 = "上方" if rel5 > 0 else "下方"
            lines.append(f"  价格在5日线{pos5} {abs(rel5):.1f}%（MA5={report.ma5:.3f}）")
        if report.ma10 > 0:
            rel10 = (report.price - report.ma10) / report.ma10 * 100
            pos10 = "上方" if rel10 > 0 else "下方"
            lines.append(f"  价格在10日线{pos10} {abs(rel10):.1f}%（MA10={report.ma10:.3f}）")

        lines.append("")
        lines.append("**2. 震荡与超买（RSI / 布林带）**")
        rsi_desc = {
            "超买": "处于超买区，短期回调压力大",
            "偏强": "偏强，仍在多头区间",
            "中性": "中性区间，多空均衡",
            "偏弱": "偏弱，关注能否企稳",
            "超卖": "超卖区，存在超跌反弹机会",
        }.get(report.rsi_status, "")
        lines.append(f"  RSI（14日）：{report.rsi_14:.1f} — {rsi_desc}")
        if report.boll_upper > 0:
            boll_pos = (report.price - report.boll_lower) / (report.boll_upper - report.boll_lower) * 100 if (report.boll_upper - report.boll_lower) > 0 else 50
            if boll_pos >= 80:
                boll_desc = "接近上轨，注意超买风险"
            elif boll_pos <= 20:
                boll_desc = "接近下轨，关注超跌支撑"
            else:
                boll_desc = f"处于带内中性区域（位置 {boll_pos:.0f}%）"
            lines.append(f"  布林带：上轨 {report.boll_upper:.3f} / 中轨 {report.boll_middle:.3f} / 下轨 {report.boll_lower:.3f}，{boll_desc}")
            lines.append(f"  带宽 {report.boll_width:.1f}%（{'震荡加剧' if report.boll_width > 8 else '相对收窄'}）")

        lines.append("")
        lines.append("**3. 动能（MACD / 量能）**")
        macd_desc = {
            "金叉": "MACD 金叉，上涨动能启动",
            "多头": "MACD 多头区间，红柱持续",
            "死叉": "MACD 死叉，下跌动能释放",
            "空头": "MACD 空头区间，注意风险",
            "中性": "MACD 零轴附近，方向待定",
        }.get(report.macd_status, "")
        lines.append(f"  MACD：DIF={report.macd_dif:.4f} DEA={report.macd_dea:.4f} 柱={report.macd_hist:.4f}")
        lines.append(f"  {macd_desc}")
        vr = report.volume_ratio
        if vr > 2.0:
            vr_desc = f"量比 {vr:.2f}，明显放量，多空分歧加大"
        elif vr > 1.2:
            vr_desc = f"量比 {vr:.2f}，温和放量，关注方向确认"
        elif vr < 0.6:
            vr_desc = f"量比 {vr:.2f}，明显缩量，观望情绪浓"
        else:
            vr_desc = f"量比 {vr:.2f}，成交平稳"
        lines.append(f"  {vr_desc}")
        lines.append("")

        lines.append("**4. 支撑与压力（关键价位）**")
        if report.support_s1 > 0 or report.support_s2 > 0:
            sup_parts = []
            if report.support_s1 > 0: sup_parts.append(f"S1={report.support_s1:.3f}")
            if report.support_s2 > 0: sup_parts.append(f"S2={report.support_s2:.3f}")
            lines.append("  短期支撑：" + " → ".join(sup_parts))
        if report.resistance_r1 > 0 or report.resistance_r2 > 0:
            res_parts = []
            if report.resistance_r1 > 0: res_parts.append(f"R1={report.resistance_r1:.3f}")
            if report.resistance_r2 > 0: res_parts.append(f"R2={report.resistance_r2:.3f}")
            lines.append("  短期压力：" + " → ".join(res_parts))
        lines.append(f"  ATR（14日）：{report.atr_14:.4f}，波动性 {report.volatility}")
        lines.append("")
        return lines

    @staticmethod
    def _format_tail_parts(report: TechnicalReport) -> list[str]:
        lines = []
        conclusion = TechnicalAnalyzer.get_conclusion(report.score)
        lines.append("**三、综合评估与操作建议**")
        score_label_map = {
            "强势看多": ("当前技术面偏强，可考虑轻仓介入或持仓", "空仓可在支撑位分批建仓；持仓可持有，跌破S2止损"),
            "偏多":    ("技术面偏多，但需确认量能配合", "等待缩量回踩均线支撑后介入；持仓继续持有"),
            "中性":    ("技术面中性，不急于操作", "观望为主，等待方向明朗再决策"),
            "偏空":    ("短期走弱，不建议追买", "空仓继续观望；持仓设好止损（S2下方）"),
            "强势看空": ("技术全面走弱，建议回避", "空仓不介入；持仓优先止损减仓"),
        }
        conclusion_detail, action = score_label_map.get(report.score_label, (conclusion, "观望为主"))
        lines.append(f"  综合评分：{report.score:+.0f}（{report.score_label}）")
        lines.append(f"  结论：{conclusion_detail}")
        lines.append(f"  操作：{action}")

        if report.llm_fundamental_analysis:
            lines.append("")
            lines.append("**四、基本面与风险评价（AI分析）**")
            lines.append(report.llm_fundamental_analysis)
        return lines

    @staticmethod
    def format_report(report: TechnicalReport) -> str:
        """完整版报告（用于 ETF）"""
        lines = TechnicalAnalyzer._format_header_and_quotes(report)
        lines.extend(TechnicalAnalyzer._format_tech_details(report))
        lines.extend(TechnicalAnalyzer._format_tail_parts(report))
        return "\n".join(lines)

    @staticmethod
    def format_main_report(report: TechnicalReport) -> str:
        """核心版报告（用于股票主推）"""
        lines = TechnicalAnalyzer._format_header_and_quotes(report)
        lines.extend(TechnicalAnalyzer._format_tail_parts(report))
        return "\n".join(lines)

    @staticmethod
    def format_tech_report(report: TechnicalReport) -> str:
        """技术指标专门报告（用于股票副推）"""
        _ts = report.timestamp
        now_str = f"{_ts.year}年{_ts.month}月{_ts.day}日 {_ts.strftime('%H:%M')}"
        lines = [f"**{report.name}（{report.symbol}）** — 纯技术指标解析 ({now_str})\n"]
        lines.extend(TechnicalAnalyzer._format_tech_details(report))
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
            f"{label}",
            f"{signal.name}（{signal.symbol}）",
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
