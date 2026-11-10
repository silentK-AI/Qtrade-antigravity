"""
全市场短线投机情绪与大局观风控评估模块
用于为打板策略提供“天气预报”，规避退潮期高位杀跌
"""

from typing import Dict, Any, List, Optional
from config import SentimentConfig
from models.stock_item import StockQuote


class MarketSentimentAnalyzer:
    """短线情绪周期分析器"""

    def __init__(self, config: SentimentConfig = None):
        self.config = config or SentimentConfig()

    def evaluate_realtime_sentiment(
        self,
        provider: Any,
        quotes: Optional[List[StockQuote]] = None
    ) -> Dict[str, Any]:
        """
        全自动化从交易所实时数据源拉取涨停池、炸板池与行业板块，生成真实盘面情绪与大局观风控
        """
        try:
            from collections import Counter
            from utils.filters import StockFilter
            stock_filter = StockFilter()

            zt_details = provider.fetch_today_zt_pool_details()
            zb_details = provider.fetch_today_zb_pool_details()

            zt_main = {k: v for k, v in zt_details.items() if stock_filter.is_main_board_code(k)}
            zb_main = {k: v for k, v in zb_details.items() if stock_filter.is_main_board_code(k)}

            limit_up_count = len(zt_main)
            exploded_count = len(zb_main)
            total_attempts = limit_up_count + exploded_count
            exploded_ratio = (exploded_count / total_attempts * 100.0) if total_attempts > 0 else 0.0

            highest_continuous_board = max([int(v.get("continuous_boards", 1) or 1) for v in zt_main.values()], default=1)

            # 自动提取领涨主线题材 (基于东财 API 真实行业)
            industries = [v.get("industry") for v in zt_main.values() if v.get("industry")]
            if industries:
                top_2 = Counter(industries).most_common(2)
                top_theme = " / ".join([f"{name} ({cnt}家)" for name, cnt in top_2])
            else:
                top_theme = "主板全市场轮动"

            limit_down_count = 0
            if quotes:
                limit_down_count = sum(1 for q in quotes if q.change_pct <= -9.8 and stock_filter.is_main_board_code(q.code))

            # 情绪周期定位
            if limit_up_count == 0 and exploded_count == 0:
                status = "早盘集合竞价 / 待开盘"
                risk_advice = "早盘竞价初期，全市场尚未产生大面积封单，等待开盘后分时量价确认。"
                sentiment_multiplier = 1.00
            elif (exploded_ratio > self.config.PANIC_EXPLODED_RATIO * 100 and total_attempts >= 10) or limit_down_count >= self.config.MAX_DOWN_LIMIT_COUNT:
                status = "情绪退潮期 / 大分歧"
                risk_advice = "谨慎做多！炸板率高企或跌停偏多，应严格控制仓位在3成以下，仅关注绝对核心龙头。"
                sentiment_multiplier = 0.80
            elif limit_up_count >= 35 and exploded_ratio <= 25.0:
                status = "情绪高潮 / 主升期"
                risk_advice = "市场赚钱效应极佳，首板与连板接力胜率高，可积极上仓位参与强势题材。"
                sentiment_multiplier = 1.10
            else:
                status = "活跃/震荡分化期"
                risk_advice = "结构性轮动行情，去弱留强，聚焦有板块梯队配合的核心前排标的。"
                sentiment_multiplier = 1.00

            return {
                "status": status,
                "limit_up_count": limit_up_count,
                "limit_down_count": limit_down_count,
                "exploded_ratio": exploded_ratio,
                "highest_continuous_board": highest_continuous_board,
                "top_theme": top_theme,
                "risk_advice": risk_advice,
                "sentiment_multiplier": sentiment_multiplier
            }
        except Exception:
            return {
                "status": "数据同步中",
                "limit_up_count": 0,
                "limit_down_count": 0,
                "exploded_ratio": 0.0,
                "highest_continuous_board": 0,
                "top_theme": "数据同步中",
                "risk_advice": "聚焦有板块梯队配合的核心前排标的。",
                "sentiment_multiplier": 1.00
            }

    def evaluate_sentiment(
        self,
        quotes: List[StockQuote],
        exploded_count: int = 0,
        highest_continuous_board: int = 1,
        top_theme: str = "主板全市场轮动"
    ) -> Dict[str, Any]:
        """
        评估当前全市场短线情绪
        """
        limit_up_count = sum(1 for q in quotes if q.is_limit_up or q.change_pct >= 9.8)
        limit_down_count = sum(1 for q in quotes if q.change_pct <= -9.8)
        total_zt_attempt = limit_up_count + exploded_count
        exploded_ratio = (exploded_count / total_zt_attempt * 100.0) if total_zt_attempt > 0 else 0.0

        # 判断情绪周期状态
        if exploded_ratio > self.config.PANIC_EXPLODED_RATIO * 100 or limit_down_count >= self.config.MAX_DOWN_LIMIT_COUNT:
            status = "情绪退潮期 / 大分歧"
            risk_advice = "谨慎做多！炸板率高企或跌停偏多，应严格控制仓位在3成以下，仅关注绝对核心龙头。"
            sentiment_multiplier = 0.80
        elif limit_up_count >= 40 and exploded_ratio <= 25.0:
            status = "情绪高潮 / 主升期"
            risk_advice = "市场赚钱效应极佳，首板与连板接力胜率高，可积极上仓位参与强势题材。"
            sentiment_multiplier = 1.10
        else:
            status = "活跃/震荡分化期"
            risk_advice = "结构性轮动行情，去弱留强，聚焦有板块梯队配合的核心前排标的。"
            sentiment_multiplier = 1.00

        return {
            "status": status,
            "limit_up_count": limit_up_count,
            "limit_down_count": limit_down_count,
            "exploded_ratio": exploded_ratio,
            "highest_continuous_board": highest_continuous_board,
            "top_theme": top_theme,
            "risk_advice": risk_advice,
            "sentiment_multiplier": sentiment_multiplier
        }
