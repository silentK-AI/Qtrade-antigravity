"""
全市场短线投机情绪与大局观风控评估模块
用于为打板策略提供“天气预报”，规避退潮期高位杀跌
"""

from typing import Dict, Any, List
from config import SentimentConfig
from models.stock_item import StockQuote


class MarketSentimentAnalyzer:
    """短线情绪周期分析器"""

    def __init__(self, config: SentimentConfig = None):
        self.config = config or SentimentConfig()

    def evaluate_sentiment(
        self,
        quotes: List[StockQuote],
        exploded_count: int = 8,
        highest_continuous_board: int = 5,
        top_theme: str = "低空经济 / 商业航天"
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
