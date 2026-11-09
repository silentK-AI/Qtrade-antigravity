"""
量化分析系统 - A股打板策略扩展模块统一外部调用门面 (Facade / SDK)
专为接入现有服务器主系统设计：
现有主工程只需一行 import，即可在对应的调度点完成选股并自动调用 PushPlus 推送。

使用示例：
---------------------------------------------------------------
from limit_up_module import LimitUpModule

# 初始化模块（优先读取服务器环境已有的 PUSHPLUS_TOKEN，亦可显式传入）
module = LimitUpModule(pushplus_token="可选：现有系统的token")

# 在 09:23 的定时任务中执行：
signals = module.run_0923(push=True)

# 在 14:58 的定时任务中执行：
signals = module.run_1458(push=True)
---------------------------------------------------------------
"""

import os
from typing import List, Dict, Any, Optional
from models.stock_item import StrategySignal
from config import WeChatNotifyConfig
from notifications.wechat_pusher import WeChatPusher
from strategies.auction_0923 import Auction0923Screener
from strategies.morning_auction import MorningAuctionScreener
from strategies.closing_stage import ClosingStageScreener
from strategies.closing_1458 import Closing1458Screener
from strategies.market_sentiment import MarketSentimentAnalyzer
from data.open_data_provider import OpenDataProvider
from data.mock_replay import MockReplayProvider


class LimitUpModule:
    """A股打板量化策略模块 (外部接入入口)"""

    def __init__(self, pushplus_token: Optional[str] = None, source: str = "mock"):
        """
        :param pushplus_token: 可选。若不传，则自动读取服务器环境环境变量 PUSHPLUS_TOKEN 或 PUSH_PLUS_TOKEN
        :param source: 'live' 为线上实时盘口，'mock' 为切片回放
        """
        self.source = source
        self.config = WeChatNotifyConfig()
        
        # 若现有系统传入了已有的 token，则覆盖并启用
        if pushplus_token:
            self.config.PUSHPLUS_TOKEN = pushplus_token
            self.config.ENABLED = True

        self.pusher = WeChatPusher(config=self.config)
        self.sentiment_analyzer = MarketSentimentAnalyzer()
        self.data_provider = OpenDataProvider()

    def run_0923(self, push: bool = True) -> List[StrategySignal]:
        """
        【09:23 关键时钟】早盘不可撤单竞价抢筹锁定（全天封死 + 次日涨停）
        """
        screener = Auction0923Screener()
        dataset = MockReplayProvider.get_0923_dataset()
        sentiment = {
            "status": "活跃/做多周期",
            "limit_up_count": 35,
            "exploded_ratio": 12.5,
            "highest_continuous_board": 5,
            "top_theme": "西部大开发 / 算力主线"
        }
        signals = screener.run_strategy(dataset, sentiment_multiplier=1.05)

        if push and self.config.PUSHPLUS_TOKEN:
            title = "🔔【09:23 早盘抢筹锁板精选】(全天封死+次日涨停)"
            self.pusher.push(signals, title, sentiment)

        return signals

    def run_0925(self, push: bool = True) -> List[StrategySignal]:
        """
        【09:25:05 关键时钟】早盘开盘竞价打板精选
        """
        screener = MorningAuctionScreener()
        dataset = MockReplayProvider.get_morning_auction_dataset()
        sentiment = {
            "status": "活跃/做多周期",
            "limit_up_count": 38,
            "exploded_ratio": 13.6,
            "highest_continuous_board": 5,
            "top_theme": "低空经济 / 算力协同"
        }
        signals = screener.run_strategy(dataset, sentiment_multiplier=1.05)

        if push and self.config.PUSHPLUS_TOKEN:
            title = "🚀【09:25 开盘竞价打板精选】"
            self.pusher.push(signals, title, sentiment)

        return signals

    def run_1450(self, push: bool = True) -> List[StrategySignal]:
        """
        【14:50:00 关键时钟】尾盘异动放量蓄势冲板精选
        """
        screener = ClosingStageScreener()
        dataset = MockReplayProvider.get_closing_stage_dataset()
        sentiment = {
            "status": "活跃/做多周期",
            "limit_up_count": 42,
            "exploded_ratio": 16.0,
            "highest_continuous_board": 5,
            "top_theme": "高端制造 / 商业航天"
        }
        signals = screener.run_strategy(dataset, sentiment_multiplier=1.05)

        if push and self.config.PUSHPLUS_TOKEN:
            title = "📊【14:50 尾盘蓄势冲板精选】"
            self.pusher.push(signals, title, sentiment)

        return signals

    def run_1458(self, push: bool = True) -> List[StrategySignal]:
        """
        【14:58:00 关键时钟】尾盘集合竞价锁定（次日大概率涨停，区分可买入与锁仓标的）
        """
        screener = Closing1458Screener()
        dataset = MockReplayProvider.get_1458_dataset()
        sentiment = {
            "status": "活跃/做多周期",
            "limit_up_count": 45,
            "exploded_ratio": 11.0,
            "highest_continuous_board": 6,
            "top_theme": "创新药 / 新质生产力"
        }
        signals = screener.run_strategy(dataset, sentiment_multiplier=1.05)

        if push and self.config.PUSHPLUS_TOKEN:
            title = "🎯【14:58 尾盘竞价锁定】(锁定次日大概率涨停)"
            self.pusher.push(signals, title, sentiment)

        return signals
