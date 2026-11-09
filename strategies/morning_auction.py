"""
早盘集合竞价打板选股策略引擎 (09:25:00 准时计算)
资金因子权重 >= 55%：
1. 竞价成交额与爆量比（占前一日全天成交量比例）—— 25分
2. 9:25 买一未匹配封单沉淀资金强度（占流通市值比例）—— 18分
3. 9:24 关键不可撤单时段主力急促抢筹脉冲与买卖大单比 —— 12分
价格与战法形态配合（30分）：
1. 黄金溢价开盘区间（+2.0% ~ +5.5%）—— 18分
2. 1进2首板加速 / 爆量弱转强反包战法 —— 12分
基础流动性与风控底分（15分）
"""

from typing import List, Tuple, Dict, Any
from config import MorningAuctionConfig
from models.stock_item import StockQuote, AuctionSnapshot, StrategySignal
from strategies.base_screener import BaseScreener


class MorningAuctionScreener(BaseScreener):
    """早盘集合竞价选股器（资金为王）"""

    def __init__(self, config: MorningAuctionConfig = None):
        super().__init__()
        self.config = config or MorningAuctionConfig()

    def calculate_auction_score(
        self,
        quote: StockQuote,
        auction: AuctionSnapshot,
        sentiment_multiplier: float = 1.0
    ) -> Tuple[float, float, str, Dict[str, Any], str]:
        """
        计算个股早盘竞价打板评分
        返回: (综合总分, 资金因子专属得分, 形态战法, 核心因子字典, 次日预期)
        """
        factors = {}
        pattern = "常规竞价异动"

        # -----------------------------------------------------------------
        # 一、 资金核心因子 (满分 55 分，占比 55%)
        # -----------------------------------------------------------------
        capital_score = 0.0

        # 1. 竞价爆量比与成交金额 (满分 25 分)
        vol_ratio = auction.auction_vol_ratio
        amount_wan = auction.auction_amount / 10000.0
        
        if vol_ratio >= self.config.HIGH_AUCTION_VOL_RATIO: # >= 12%
            score_vol = 25.0
            factors["【资金】竞价爆量比"] = f"{vol_ratio*100:.1f}% (极强爆量, 竞价成交{amount_wan:.0f}万)"
        elif vol_ratio >= self.config.MIN_AUCTION_VOL_RATIO: # >= 6%
            score_vol = 18.0
            factors["【资金】竞价爆量比"] = f"{vol_ratio*100:.1f}% (资金做多表态, 竞价成交{amount_wan:.0f}万)"
        elif vol_ratio >= 0.03:
            score_vol = 10.0
            factors["【资金】竞价爆量比"] = f"{vol_ratio*100:.1f}% (温和爆量)"
        else:
            score_vol = 2.0
            factors["【资金】竞价爆量比"] = f"{vol_ratio*100:.1f}% (竞价量能匮乏)"
        capital_score += score_vol

        # 2. 9:25 买一封单沉淀资金强度（未匹配买单占流通盘比例，满分 18 分）
        unmatched_wan = auction.unmatched_amount / 10000.0
        unmatched_ratio = (auction.unmatched_amount / (quote.float_market_cap * 100000000.0) * 1000.0) if quote.float_market_cap > 0 else 0.0
        
        if unmatched_ratio >= 2.0 or unmatched_wan >= 2000.0:
            score_unmatched = 18.0
            factors["【资金】封单沉淀强度"] = f"买一未匹配沉淀资金 {unmatched_wan:.0f} 万 (占流通盘 {unmatched_ratio:.2f}‰)"
        elif unmatched_ratio >= 0.8 or unmatched_wan >= 800.0:
            score_unmatched = 13.0
            factors["【资金】封单沉淀强度"] = f"买一沉淀资金 {unmatched_wan:.0f} 万"
        elif unmatched_wan > 0:
            score_unmatched = 6.0
            factors["【资金】封单沉淀强度"] = f"买一沉淀资金 {unmatched_wan:.0f} 万 (中规中矩)"
        else:
            score_unmatched = 0.0
            factors["【资金】封单沉淀强度"] = "无多头未匹配买单"
        capital_score += score_unmatched

        # 3. 9:24 关键抢筹脉冲与买卖委托意愿比 (满分 12 分)
        strength = auction.bid_ask_strength
        score_rush = 0.0
        if auction.is_924_rush:
            score_rush += 6.0
            factors["【资金】9:24尾段态势"] = "最后时刻挂单急促向上跳价抢筹"
        if strength >= 2.5:
            score_rush += 6.0
            factors["【资金】买卖委托意愿"] = f"买单/卖单比 {strength:.1f}x (多头资金绝对压制)"
        elif strength >= 1.5:
            score_rush += 4.0
            factors["【资金】买卖委托意愿"] = f"买单/卖单比 {strength:.1f}x (多头占优)"
        else:
            score_rush += 1.0
            factors["【资金】买卖委托意愿"] = f"买卖比 {strength:.1f}x"
        capital_score += score_rush

        # -----------------------------------------------------------------
        # 二、 价格与战法形态配合因子 (满分 30 分，占比 30%)
        # -----------------------------------------------------------------
        price_tech_score = 0.0

        # 1. 黄金溢价区间 (满分 18 分)
        gap = auction.gap_percent
        if 2.0 <= gap <= 5.5:
            score_gap = 18.0
            factors["【价格】高开溢价幅度"] = f"+{gap:.2f}% (处于黄金做多区间)"
        elif 0.5 <= gap < 2.0:
            score_gap = 13.0
            factors["【价格】高开溢价幅度"] = f"+{gap:.2f}% (平开小幅高开)"
        elif 5.5 < gap <= 7.5:
            score_gap = 10.0
            factors["【价格】高开溢价幅度"] = f"+{gap:.2f}% (较高开盘，需防冲高抛压)"
        elif gap > 7.5:
            score_gap = 4.0
            factors["【价格】高开溢价幅度"] = f"+{gap:.2f}% (大幅高开，谨防诱多)"
        else:
            score_gap = 1.0
            factors["【价格】高开溢价幅度"] = f"{gap:.2f}% (低开弱势)"
        price_tech_score += score_gap

        # 2. 核心战法加成（1进2 / 弱转强）(满分 12 分)
        expectation = "早盘竞价量价配合，预期日内拉升冲板并奠定次日连板基础。"
        if "首板" in quote.yesterday_status:
            price_tech_score += 12.0
            pattern = "【1进2】竞价加速接力"
            factors["【战法】历史形态"] = "昨首板干脆封死，今日竞价资金爆量加速"
            expectation = "首板晋级二板最强共识，竞价爆量承接坚决，预期日内快速封死涨停，次日享受高溢价或二连板。"
        elif ("冲高" in quote.yesterday_status or "炸板" in quote.yesterday_status or "阴线" in quote.yesterday_status) and gap >= 1.5:
            price_tech_score += 11.0
            pattern = "【弱转强】竞价反包洗盘"
            factors["【战法】历史形态"] = "昨日大阴/炸板洗盘，今日竞价超预期反包"
            expectation = "昨日空头筹码洗净，今日主力高开强行承接完成弱转强，预计日内拉板完成反包大长腿。"
        else:
            price_tech_score += 5.0
            pattern = "主板弹性突破"

        # -----------------------------------------------------------------
        # 三、 基础流动性与风控底分 (满分 15 分，占比 15%)
        # -----------------------------------------------------------------
        base_score = 15.0
        if quote.float_market_cap <= 100.0:
            base_score = 15.0
        else:
            base_score = 10.0  # 大盘股适当降低弹性分

        # 汇总与情绪系数乘数
        raw_total = capital_score + price_tech_score + base_score
        final_score = min(100.0, raw_total * sentiment_multiplier)

        return round(final_score, 1), round(capital_score, 1), pattern, factors, expectation

    def run_strategy(
        self,
        candidates: List[Tuple[StockQuote, AuctionSnapshot]],
        sentiment_multiplier: float = 1.0
    ) -> List[StrategySignal]:
        signals = []

        for quote, auction in candidates:
            if not self.stock_filter.filter_quote(quote):
                continue

            score, cap_score, pattern, factors, expectation = self.calculate_auction_score(
                quote, auction, sentiment_multiplier
            )

            if score >= self.config.SCORE_THRESHOLD:
                if "1进2" in pattern:
                    action = "09:25直接市价挂单 / 开盘若秒板直接挂排单"
                else:
                    action = "开盘分时回踩均线分批低吸，放量冲高确认时加仓"

                stop_loss = self.calculate_stop_loss(auction.auction_price, risk_tolerance_pct=4.0)

                signal = StrategySignal(
                    code=quote.code,
                    name=quote.name,
                    strategy_type="早盘竞价打板",
                    score=score,
                    capital_score=cap_score,
                    current_price=auction.auction_price,
                    change_pct=auction.gap_percent,
                    target_pattern=pattern,
                    key_factors=factors,
                    suggested_action=action,
                    stop_loss_price=stop_loss,
                    next_day_expectation=expectation
                )
                signals.append(signal)

        signals.sort(key=lambda s: s.score, reverse=True)
        return signals
