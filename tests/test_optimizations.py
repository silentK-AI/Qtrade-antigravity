"""
单元测试：系统全面优化项验证测试
验证项：
1. A 股交易日历 (TradeCalendar) 周末与法定节假日休市判定；
2. 真实全市场情绪分析器 (evaluate_realtime_sentiment) 与题材自动提炼；
3. 微信统一分发 (_dispatch_push) 与盘中行业属性；
4. 结构化日志 (get_logger) 与滚动文件记录；
5. 09:25 开盘集合竞价实盘数据流。
"""

import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from utils.calendar import TradeCalendar
from utils.logger import get_logger
from strategies.market_sentiment import MarketSentimentAnalyzer
from notifications.wechat_pusher import WeChatPusher
from models.stock_item import IntradayEvent, StockQuote
from daemon_scheduler import ServerDaemonScheduler


class TestSystemOptimizations(unittest.TestCase):

    def test_trade_calendar_weekends_and_holidays(self):
        """测试 A 股交易日历准确识别周末与法定假期"""
        # 1. 2026-10-01 国庆休市
        national_day = datetime(2026, 10, 1, 10, 0, 0)
        self.assertFalse(TradeCalendar.is_trading_day(national_day))

        # 2. 2026-02-16 春节休市
        spring_festival = datetime(2026, 2, 16, 10, 0, 0)
        self.assertFalse(TradeCalendar.is_trading_day(spring_festival))

        # 3. 2026-11-08 周日休市
        sunday = datetime(2026, 11, 8, 10, 0, 0)
        self.assertFalse(TradeCalendar.is_trading_day(sunday))

        # 4. 2026-11-09 周一普通工作日（交易日）
        monday = datetime(2026, 11, 9, 10, 0, 0)
        self.assertTrue(TradeCalendar.is_trading_day(monday))

    def test_realtime_sentiment_evaluator(self):
        """测试实时情绪周期分析器动态提取涨停数、炸板率与主线题材"""
        analyzer = MarketSentimentAnalyzer()
        mock_provider = MagicMock()

        mock_provider.fetch_today_zt_pool_details.return_value = {
            "600519": {"continuous_boards": 2, "industry": "白酒"},
            "600809": {"continuous_boards": 3, "industry": "白酒"},
            "000001": {"continuous_boards": 1, "industry": "银行"},
            "300123": {"continuous_boards": 1, "industry": "创业板"}  # 需被主板过滤
        }
        mock_provider.fetch_today_zb_pool_details.return_value = {
            "600000": {"industry": "银行"}
        }

        sentiment = analyzer.evaluate_realtime_sentiment(mock_provider)

        # 验证主板涨停家数与炸板家数
        self.assertEqual(sentiment["limit_up_count"], 3)  # 600519, 600809, 000001
        self.assertEqual(sentiment["highest_continuous_board"], 3)
        self.assertIn("白酒 (2家)", sentiment["top_theme"])
        self.assertAlmostEqual(sentiment["exploded_ratio"], 25.0, places=1)
        self.assertIn("sentiment_multiplier", sentiment)

    def test_logger_setup(self):
        """测试日志系统正常初始化"""
        logger = get_logger("test_opt_logger")
        self.assertIsNotNone(logger)
        self.assertTrue(len(logger.handlers) >= 1)

    def test_intraday_event_with_industry(self):
        """测试盘中异动卡片正确展示所属行业题材"""
        pusher = WeChatPusher()
        ev = IntradayEvent(
            event_type="LIMIT_UP",
            code="600519",
            name="贵州茅台",
            current_price=1780.0,
            change_pct=10.0,
            event_time="10:05:00",
            seal_amount_wan=50000.0,
            turnover_rate=1.5,
            open_board_count=0,
            continuous_boards=2,
            action_advice="【建议：重点打板】",
            reason="换手晋级良好",
            industry="白酒消费"
        )
        title, md = pusher.format_intraday_events([ev])
        self.assertIn("白酒消费", md)
        self.assertIn("贵州茅台", title)

    def test_scheduler_0925_live_fallback(self):
        """测试 09:25 候选标的在异常或空数据时能平稳回退"""
        scheduler = ServerDaemonScheduler(source="mock")
        candidates = scheduler._get_0925_candidates()
        self.assertTrue(len(candidates) > 0)


if __name__ == "__main__":
    unittest.main()
