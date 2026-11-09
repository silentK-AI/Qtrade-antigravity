"""
14:58:00 尾盘集合竞价策略引擎 (兼顾次日涨停与实战可买入性 Fillability)
核心逻辑划分：
1. 【实战可买入池】：
   - A: 尾盘新回封标的 (14:30后封板，排队单未堵死，换手抛盘活跃，能买进)
   - B: 尾盘主力抢筹蓄势标的 (+6.0% ~ +8.8% 未封死，100%市价秒买进，锁定次日早盘冲板)
2. 【锁仓/风向标池】：
   - 早盘10:00前即封死且排单上亿的铁板，系统明确提示【买不进去！仅供持股者锁仓与板块风向标参考】
"""

from typing import List, Tuple, Dict, Any
from config import ClosingAuction1458Config
from models.stock_item import StockQuote, Snapshot1458, StrategySignal
from strategies.base_screener import BaseScreener


class Closing1458Screener(BaseScreener):
    """14:58 尾盘集合竞价可买入与次日涨停选股器"""

    def __init__(self, config: ClosingAuction1458Config = None):
        super().__init__()
        self.config = config or ClosingAuction1458Config()

    def calculate_1458_score(
        self,
        quote: StockQuote,
        snap: Snapshot1458,
        sentiment_multiplier: float = 1.0
    ) -> Tuple[float, float, str, Dict[str, Any], str, str]:
        """
        计算 14:58 尾盘竞价打分
        返回: (综合分, 资金分, 战法, 因子字典, 建议操作, 次日预期)
        """
        factors = {}
        seal_wan = snap.closing_seal_amount / 10000.0
        seal_ratio = snap.seal_to_float_ratio
        first_time = snap.first_seal_time

        # -----------------------------------------------------------------
        # 场景一：早盘极早封死 (<=10:00) 且封单上亿 —— 绝对买不进去！
        # -----------------------------------------------------------------
        if snap.is_limit_up and first_time <= "10:30" and (seal_wan >= 5000.0 or seal_ratio >= 6.0):
            factors["【可买入性】"] = "❌ 队列已堵死！前面积压巨量封单，14:58挂单100%买不进去"
            factors["【实战定位】"] = "板块情绪定海神针 / 持筹者锁仓标杆"
            factors["【资金】排队封单规模"] = f"排队封单 {seal_wan:.0f} 万元 (占流通盘 {seal_ratio:.2f}‰)"
            pattern = "【龙头风向标·买不进】铁板锁仓"
            action = "【14:58已封死·买不进去！】若早盘已持有，则坚决锁仓一股不卖，次日坐等连板"
            expectation = "绝对核心领涨龙头，次日高概率一字板或秒板，为同板块蓄势股打开高度空间。"
            return 98.0, 60.0, pattern, factors, action, expectation

        # -----------------------------------------------------------------
        # 场景二：尾盘刚封板回封 (14:30 以后封板，换手充分，能排进成交！)
        # -----------------------------------------------------------------
        elif snap.is_limit_up and first_time >= "14:20":
            factors["【可买入性】"] = "✅ 能够买进！尾盘刚刚封死，前面封单不厚且盘中有抛盘成交，排单成交率高"
            factors["【资金承接】"] = f"尾盘集合竞价扫单 {seal_wan:.0f} 万元，多头尾盘突袭锁单"
            factors["【换手硬度】"] = f"全天充分换手 {quote.turnover_rate:.1f}%，筹码洗净"
            pattern = "【尾盘回封·能买进】分歧转一致次日连板"
            action = "【14:58立即挂涨停价委托】排队进入收盘集合竞价，预计大概率能成交！"
            expectation = "尾盘经受分歧后顽强回封，浮筹已在盘中洗尽，次日享受弱转强高开连板溢价。"
            return 92.0, 52.0, pattern, factors, action, expectation

        # -----------------------------------------------------------------
        # 场景三：尾盘放量蓄势冲板未遂 (+5.5% ~ +8.8%，100%市价秒买进！)
        # -----------------------------------------------------------------
        elif not snap.is_limit_up and snap.indicative_change_pct >= 5.5:
            factors["【可买入性】"] = "✅ 100%秒买进！盘口卖单充足，直接市价挂单即时成交"
            factors["【资金抢筹】"] = "主力尾盘巨资逆势扫盘，故意不封死避免过早暴露"
            pattern = "【蓄势未板·100%买进】尾盘突击次日冲板"
            action = "【14:58-14:59市价直接买入】在收盘前锁定底仓，次日早盘享受抬轿"
            expectation = "全天主力沿均线蓄势推升，尾盘爆量隐蔽吸筹，次日早盘极高概率直接集合竞价高开抢筹冲涨停。"
            return 88.0, 48.0, pattern, factors, action, expectation

        # -----------------------------------------------------------------
        # 其余平庸标的淘汰
        # -----------------------------------------------------------------
        return 0.0, 0.0, "平庸标的", {"【状态】": "不符合尾盘进攻特征"}, "观望", "无次日涨停预期"

    def run_strategy(
        self,
        candidates: List[Tuple[StockQuote, Snapshot1458]],
        sentiment_multiplier: float = 1.0
    ) -> List[StrategySignal]:
        signals = []

        for quote, snap in candidates:
            if not self.stock_filter.filter_quote(quote):
                continue

            score, cap_score, pattern, factors, action, expectation = self.calculate_1458_score(
                quote, snap, sentiment_multiplier
            )

            if score >= self.config.SCORE_THRESHOLD:
                stop_loss = self.calculate_stop_loss(snap.indicative_price, risk_tolerance_pct=3.0)

                signal = StrategySignal(
                    code=quote.code,
                    name=quote.name,
                    strategy_type="14:58尾盘实战选股",
                    score=score,
                    capital_score=cap_score,
                    current_price=snap.indicative_price,
                    change_pct=snap.indicative_change_pct,
                    target_pattern=pattern,
                    key_factors=factors,
                    suggested_action=action,
                    stop_loss_price=stop_loss,
                    next_day_expectation=expectation
                )
                signals.append(signal)

        # 排序：优先展示能够买进的高价值标的，其次展示风向标
        signals.sort(key=lambda s: (("能买进" in s.target_pattern or "100%" in s.target_pattern), s.score), reverse=True)
        return signals
