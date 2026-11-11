"""
09:23:00 早盘不可撤单竞价抢筹策略引擎
专门应对：9:15-9:20虚假撤单过滤，锁定9:20-9:23真金白银大资金顶板标的
目标：找出“当天全天封死一整天涨停 + 次日继续涨停”的超级强势股
买入操作窗口：09:23:00 - 09:24:50 直接提交竞价挂单，抢在 09:25 撮合前成交进场
"""

from typing import List, Tuple, Dict, Any
from config import PreAuction0923Config
from models.stock_item import StockQuote, Snapshot0923, StrategySignal
from strategies.base_screener import BaseScreener


class Auction0923Screener(BaseScreener):
    """09:23 早盘真金白银锁板选股引擎"""

    def __init__(self, config: PreAuction0923Config = None):
        super().__init__()
        self.config = config or PreAuction0923Config()

    def calculate_0923_score(
        self,
        quote: StockQuote,
        snap: Snapshot0923,
        sentiment_multiplier: float = 1.0
    ) -> Tuple[float, float, str, Dict[str, Any], str]:
        """
        计算 09:23 核心指标评分
        """
        factors = {}
        pattern = "09:23竞价异动"

        # -----------------------------------------------------------------
        # 一、 诱多虚假撤单过滤（9:19-9:20 撤单率检验）—— 一票否决项
        # -----------------------------------------------------------------
        if snap.spoof_withdrawn_ratio > self.config.MAX_SPOOF_WITHDRAW_RATIO:
            return 0.0, 0.0, "虚假撤单诱多", {
                "【风控】撤单异常": f"9:19-9:20 撤单率 {snap.spoof_withdrawn_ratio*100:.1f}% 远超阈值，主力假挂单诱多出货"
            }, "主力诱多撤单，无持续封板动力"

        # -----------------------------------------------------------------
        # 二、 资金核心因子 (满分 60 分，占比 60%)
        # -----------------------------------------------------------------
        capital_score = 0.0

        # 1. 9:20-9:23 真实不可撤单排队买一封单沉淀金额 (满分 28 分)
        seal_wan = snap.real_seal_amount / 10000.0
        seal_ratio = snap.real_seal_to_float_ratio
        
        if seal_wan >= self.config.HIGH_REAL_SEAL_AMOUNT or seal_ratio >= 6.0: # >= 8000万或占流通盘千分之六
            score_seal = 28.0
            factors["【资金】9:23真实封单"] = f"不可撤单封单 {seal_wan:.0f} 万元 (占流通盘 {seal_ratio:.2f}‰，超级大机构顶格锁仓)"
        elif seal_wan >= self.config.MIN_REAL_SEAL_AMOUNT or seal_ratio >= self.config.MIN_SEAL_FLOAT_RATIO: # >= 3000万
            score_seal = 20.0
            factors["【资金】9:23真实封单"] = f"不可撤单封单 {seal_wan:.0f} 万元 (占流通盘 {seal_ratio:.2f}‰，主力真金白银抢盘)"
        elif seal_wan >= 1000.0:
            score_seal = 10.0
            factors["【资金】9:23真实封单"] = f"不可撤单封单 {seal_wan:.0f} 万元 (资金一般)"
        else:
            score_seal = 2.0
            factors["【资金】9:23真实封单"] = f"封单偏弱仅 {seal_wan:.0f} 万元"
        capital_score += score_seal

        # 2. 9:20-9:23 不可撤单阶段持续抢筹动能 (满分 18 分)
        if snap.is_upward_rush:
            score_rush = 18.0
            factors["【资金】不可撤单加码"] = "9:20-9:23 拟撮合价向上跳档抢筹，筹码被抢盘扫光"
        else:
            score_rush = 6.0
            factors["【资金】不可撤单加码"] = "价格平稳未出现剧烈加码"
        capital_score += score_rush

        # 3. 9:20-9:23 真实成交换手承接 / 竞价锁筹排队强度 (满分 14 分)
        if snap.volume_920_923 > 0:
            score_vol = 14.0
            factors["【资金】不可撤阶段成交"] = "多空在不可撤单区间真金白银巨额撮合，多头完全压制"
        elif snap.is_sealed_limit and seal_wan >= self.config.MIN_REAL_SEAL_AMOUNT:
            score_vol = 14.0
            factors["【资金】不可撤阶段排队"] = f"开盘前未撮合阶段买一顶格排队 {seal_wan:.0f} 万元，不可撤单锁筹坚决"
        else:
            score_vol = 8.0
            factors["【资金】不可撤阶段成交"] = "成交量温和"
        capital_score += score_vol

        # -----------------------------------------------------------------
        # 三、 价格与形态战法配合 (满分 25 分，占比 25%)
        # -----------------------------------------------------------------
        price_tech_score = 0.0
        gap = snap.indicative_change_pct

        if snap.is_sealed_limit or gap >= 9.8:
            price_tech_score += 15.0
            factors["【价格】拟开盘价"] = f"+{gap:.2f}% (直接顶在涨停价不可撼动)"
        elif gap >= 5.5:
            price_tech_score += 10.0
            factors["【价格】拟开盘价"] = f"+{gap:.2f}% (强势高开逼近涨停)"
        else:
            price_tech_score += 2.0
            factors["【价格】拟开盘价"] = f"+{gap:.2f}% (开盘强度一般)"

        if "首板" in quote.yesterday_status:
            price_tech_score += 10.0
            pattern = "【9:23顶格锁单】1进2大单封死龙"
            factors["【战法】形态配合"] = "昨首板干脆，今9:20后不可撤单阶段主力直接挂巨单封死"
            expectation = "不可撤单阶段主力真金白银顶格封板，全天炸板率极低（封死一整天），次日极大概率继续顶涨停。"
        else:
            price_tech_score += 6.0
            pattern = "【9:23抢筹】主板强势突破封板"
            expectation = "不可撤单阶段大单急促扫盘锁定涨停，日内封板确定性极强，次日享受连板溢价。"

        # -----------------------------------------------------------------
        # 四、 基础流动性与风控底分 (满分 15 分，占比 15%)
        # -----------------------------------------------------------------
        base_score = 15.0
        if quote.float_market_cap <= 100.0:
            base_score = 15.0
        else:
            base_score = 10.0

        raw_total = capital_score + price_tech_score + base_score
        final_score = min(100.0, raw_total * sentiment_multiplier)

        return round(final_score, 1), round(capital_score, 1), pattern, factors, expectation

    def run_strategy(
        self,
        candidates: List[Tuple[StockQuote, Snapshot0923]],
        sentiment_multiplier: float = 1.0
    ) -> List[StrategySignal]:
        signals = []

        for quote, snap in candidates:
            if not self.stock_filter.filter_quote(quote):
                continue

            score, cap_score, pattern, factors, expectation = self.calculate_0923_score(
                quote, snap, sentiment_multiplier
            )

            if score >= self.config.SCORE_THRESHOLD:
                # 09:23 极其关键的操作建议
                action = "【09:23-09:24窗口】挂涨停价委托！抢在09:25撮合前买入排队！"
                stop_loss = self.calculate_stop_loss(snap.indicative_price, risk_tolerance_pct=3.0)

                signal = StrategySignal(
                    code=quote.code,
                    name=quote.name,
                    strategy_type="09:23真金白银锁板",
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

        signals.sort(key=lambda s: (s.score, s.capital_score), reverse=True)
        return signals[:5]
