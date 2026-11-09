"""
单元测试：系统全面优化项验证测试
验证项：
1. A 股交易日历 (TradeCalendar) 周末与法定节假日休市判定；
2. 真实全市场情绪分析器 (evaluate_realtime_sentiment) 与题材自动提炼；
3. 微信统一分发 (_dispatch_push) 与盘中行业属性；
4. 结构化日志 (get_logger) 与滚动文件记录；
5. 09:25 开盘集合竞价实盘数据流。
"""

import os
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

    def test_beijing_time_utils(self):
        """测试北京时间转换函数"""
        from utils.calendar import get_beijing_now
        bj_now = get_beijing_now()
        self.assertIsInstance(bj_now, datetime)
        self.assertIsNone(bj_now.tzinfo)

    def test_signal_history_tracker_record_and_evaluate(self):
        """测试策略推荐历史记录与战绩评估"""
        import tempfile
        from data.history_tracker import SignalHistoryTracker
        from models.stock_item import StrategySignal

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            tracker = SignalHistoryTracker(file_path=temp_path)
            sig = StrategySignal(
                code="600519",
                name="贵州茅台",
                strategy_type="14:58尾盘实战选股",
                score=92.0,
                capital_score=52.0,
                current_price=1750.0,
                change_pct=9.9,
                target_pattern="【尾盘回封·能买进】",
                key_factors={},
                suggested_action="买入",
                stop_loss_price=1700.0,
                next_day_expectation="冲高"
            )
            # 记录昨天的信号
            tracker.record_signals(task_type="1458", signals=[sig], date_str="2026-11-08")

            # 模拟今天拉取评测
            mock_provider = MagicMock()
            mock_provider.fetch_realtime_quotes.return_value = [
                StockQuote(
                    code="600519",
                    name="贵州茅台",
                    market="SH",
                    current_price=1925.0,
                    pre_close=1750.0,
                    open_price=1800.0,
                    high_price=1925.0,
                    low_price=1780.0,
                    change_pct=10.0,
                    volume=5000000.0,
                    amount=9500000000.0,
                    turnover_rate=1.8,
                    float_market_cap=22000.0,
                    total_market_cap=22000.0,
                    is_limit_up=True
                )
            ]

            evaluation = tracker.evaluate_recent_signals(mock_provider, today_str="2026-11-09")
            self.assertIsNotNone(evaluation)
            self.assertEqual(evaluation["total_count"], 1)
            self.assertEqual(evaluation["zt_count"], 1)
            self.assertEqual(evaluation["win_rate"], 100.0)
            self.assertAlmostEqual(evaluation["avg_max_gain"], 10.0, places=1)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_intraday_yiziban_advice(self):
        """测试集合竞价一字板输出持股锁仓建议"""
        from strategies.intraday_monitor import IntradayMonitor
        monitor = IntradayMonitor()
        advice, reason = monitor._generate_limit_up_advice(
            lbc=2,
            fund_wan=8000.0,
            zbc=0,
            is_reseal=False,
            seal_time="09:25:00"
        )
        self.assertIn("一字涨停", advice)
        self.assertIn("买不进", advice)


if __name__ == "__main__":
    unittest.main()
