"""
尾盘选股打板策略引擎 (14:50:00 准时计算)
资金因子权重 >= 55%：
1. 14:30 尾盘主力大单/特大单净买入绝对金额 —— 25分
2. 尾盘抢筹放量占比（14:30后量能占全天比例） —— 18分
3. 尾盘主力大单资金控盘锁筹强度 —— 12分
价格与分时均线配合（30分）：
1. 现价极度贴近日内最高价（>= 98.5%） —— 18分
2. 首板强回封 / 强势蓄势突破形态 —— 12分
3. 坚守分时均价线 VWAP 之上（一票否决淘汰项）
基础流动性与健康换手率（15分）
"""

from typing import List, Tuple, Dict, Any
from config import ClosingStageConfig
from models.stock_item import StockQuote, ClosingSnapshot, StrategySignal
from strategies.base_screener import BaseScreener


class ClosingStageScreener(BaseScreener):
    """尾盘选股策略器（资金为主导）"""

    def __init__(self, config: ClosingStageConfig = None):
        super().__init__()
        self.config = config or ClosingStageConfig()

    def calculate_closing_score(
        self,
        quote: StockQuote,
        closing: ClosingSnapshot,
        sentiment_multiplier: float = 1.0
    ) -> Tuple[float, float, str, Dict[str, Any], str]:
        """
        计算个股尾盘打板评分
        返回: (综合总分, 资金因子专属得分, 形态战法, 核心因子字典, 次日预期)
        """
        factors = {}
        pattern = "常规尾盘异动"

        # -----------------------------------------------------------------
        # 一、 均线一票否决检查
        # -----------------------------------------------------------------
        if not closing.is_above_vwap:
            return 0.0, 0.0, "均线下破位", {"【风控】分时均线": "价格跌破分时均线，主力出货砸盘"}, "无次日涨停预期"

        # -----------------------------------------------------------------
        # 二、 资金核心因子 (满分 55 分，占比 55%)
        # -----------------------------------------------------------------
        capital_score = 0.0

        # 1. 尾盘主力大单/特大单净流入金额 (满分 25 分)
        inflow = closing.tail_net_large_inflow
        if inflow >= 3000.0: # >= 3000万元
            score_inflow = 25.0
            factors["【资金】尾盘主力净买入"] = f"+{inflow:.0f} 万元 (特大资金扫盘入场)"
        elif inflow >= 1500.0:
            score_inflow = 19.0
            factors["【资金】尾盘主力净买入"] = f"+{inflow:.0f} 万元 (主力坚决抢筹)"
        elif inflow >= self.config.MIN_TAIL_LARGE_INFLOW: # >= 1000万
            score_inflow = 14.0
            factors["【资金】尾盘主力净买入"] = f"+{inflow:.0f} 万元 (资金净流入良好)"
        elif inflow > 0:
            score_inflow = 6.0
            factors["【资金】尾盘主力净买入"] = f"+{inflow:.0f} 万元 (微幅流入)"
        else:
            score_inflow = 0.0
            factors["【资金】尾盘主力净买入"] = f"{inflow:.0f} 万元 (主力净流出)"
        capital_score += score_inflow

        # 2. 尾盘抢筹放量占比 (满分 18 分)
        tail_ratio = closing.tail_vol_ratio
        if tail_ratio >= 0.22:
            score_vol = 18.0
            factors["【资金】尾盘抢筹放量"] = f"14:30后量能占全天 {tail_ratio*100:.1f}% (极强尾盘放量抢筹)"
        elif tail_ratio >= self.config.MIN_TAIL_VOL_RATIO:
            score_vol = 13.0
            factors["【资金】尾盘抢筹放量"] = f"14:30后量能占全天 {tail_ratio*100:.1f}% (资金显著进场)"
        elif tail_ratio >= 0.12:
            score_vol = 8.0
            factors["【资金】尾盘抢筹放量"] = f"尾盘量能占全天 {tail_ratio*100:.1f}% (平稳放量)"
        else:
            score_vol = 2.0
            factors["【资金】尾盘抢筹放量"] = f"尾盘量能仅 {tail_ratio*100:.1f}% (无抢筹动向)"
        capital_score += score_vol

        # 3. 尾盘资金控盘吸筹意愿 (满分 12 分)
        # 尾盘净买入与总成交量的配合
        if inflow >= 2000.0 and tail_ratio >= 0.20:
            score_hold = 12.0
            factors["【资金】控盘吸筹强度"] = "大单扫盘锁仓，尾盘承接极强"
        elif inflow > 500.0:
            score_hold = 8.0
            factors["【资金】控盘吸筹强度"] = "控盘良好，无抛盘抵抗"
        else:
            score_hold = 2.0
            factors["【资金】控盘吸筹强度"] = "资金控盘意愿一般"
        capital_score += score_hold

        # -----------------------------------------------------------------
        # 三、 日内价格与战法形态配合 (满分 30 分，占比 30%)
        # -----------------------------------------------------------------
        price_tech_score = 0.0

        # 1. 现价极度贴近日内最高价 (满分 18 分)
        ratio = closing.close_to_high_ratio
        if ratio >= 0.995:
            score_ratio = 18.0
            factors["【价格】最高价贴合度"] = f"现价接近全天最高 ({ratio*100:.1f}%) 毫无高位抛压"
        elif ratio >= self.config.MIN_CLOSE_TO_HIGH_RATIO: # >= 98.0%
            score_ratio = 14.0
            factors["【价格】最高价贴合度"] = f"贴近日内最高价 ({ratio*100:.1f}%) 承接良好"
        elif ratio >= 0.970:
            score_ratio = 8.0
            factors["【价格】最高价贴合度"] = f"略有上影线 ({ratio*100:.1f}%)"
        else:
            score_ratio = 0.0
            factors["【价格】最高价贴合度"] = f"冲高回落 ({ratio*100:.1f}%)，上档套牢盘偏重"
        price_tech_score += score_ratio

        # 2. 战法形态分类 (满分 12 分)
        change = closing.current_change_pct
        if closing.is_rebound_limit or quote.is_limit_up:
            price_tech_score += 12.0
            pattern = "【首板强回封】分歧换手龙"
            factors["【战法】形态分类"] = "全天充分换手洗盘，尾盘坚决回封涨停"
            expectation = "经历全天盘中分歧换手，浮筹已在盘中充分沉淀，尾盘主力坚决回封，次日开盘极高概率直接高开冲连板。"
        elif 4.0 <= change <= 8.5:
            price_tech_score += 11.0
            pattern = "【蓄势待发】尾盘潜伏冲板"
            factors["【战法】形态分类"] = f"日内涨幅 +{change:.2f}%，强势控盘蓄势"
            expectation = "全天主力沿分时均线稳步推升，尾盘爆量抢筹且拒绝开板，预期次日早盘直接集合竞价高开抢筹冲涨停。"
        else:
            price_tech_score += 5.0
            pattern = "尾盘温和拉升"
            expectation = "尾盘主力护盘良好，关注次日早盘量能接力表现。"

        # -----------------------------------------------------------------
        # 四、 基础流动性与健康换手率 (满分 15 分，占比 15%)
        # -----------------------------------------------------------------
        base_score = 15.0
        turnover = quote.turnover_rate
        if 6.0 <= turnover <= 20.0:
            factors["【换手】流动性指标"] = f"全天换手率 {turnover:.1f}% (主力充分换手黄金区间)"
        elif turnover > 25.0:
            base_score -= 5.0
            factors["【换手】流动性指标"] = f"换手率偏高 {turnover:.1f}% (次日需防分歧)"

        raw_total = capital_score + price_tech_score + base_score
        final_score = min(100.0, raw_total * sentiment_multiplier)

        return round(final_score, 1), round(capital_score, 1), pattern, factors, expectation

    def run_strategy(
        self,
        candidates: List[Tuple[StockQuote, ClosingSnapshot]],
        sentiment_multiplier: float = 1.0
    ) -> List[StrategySignal]:
        signals = []

        for quote, closing in candidates:
            if not self.stock_filter.filter_quote(quote):
                continue

            score, cap_score, pattern, factors, expectation = self.calculate_closing_score(
                quote, closing, sentiment_multiplier
            )

            if score >= self.config.SCORE_THRESHOLD:
                if "首板强回封" in pattern:
                    action = "14:52前挂涨停价排单买入 / 尾盘集合竞价市价买入"
                else:
                    action = "14:50 - 14:55分批市价潜伏买入，锁定次日早盘冲高利润"

                stop_loss = self.calculate_stop_loss(closing.current_price, risk_tolerance_pct=3.0)

                signal = StrategySignal(
                    code=quote.code,
                    name=quote.name,
                    strategy_type="尾盘抢筹打板",
                    score=score,
                    capital_score=cap_score,
                    current_price=closing.current_price,
                    change_pct=closing.current_change_pct,
                    target_pattern=pattern,
                    key_factors=factors,
                    suggested_action=action,
                    stop_loss_price=stop_loss,
                    next_day_expectation=expectation
                )
                signals.append(signal)

        signals.sort(key=lambda s: s.score, reverse=True)
        return signals
