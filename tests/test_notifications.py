"""
单元测试：微信通知格式化与推送模块测试
"""

import unittest
from notifications.wechat_pusher import WeChatPusher
from strategies.auction_0923 import Auction0923Screener
from data.mock_replay import MockReplayProvider


class TestWeChatNotification(unittest.TestCase):

    def setUp(self):
        self.pusher = WeChatPusher()
        self.screener = Auction0923Screener()
        self.dataset = MockReplayProvider.get_0923_dataset()

    def test_markdown_formatting(self):
        signals = self.screener.run_strategy(self.dataset, sentiment_multiplier=1.0)
        sentiment = {
            "status": "活跃/做多周期",
            "limit_up_count": 35,
            "exploded_ratio": 12.5,
            "highest_continuous_board": 5,
            "top_theme": "西部大开发"
        }

        # 格式化微信 Markdown 卡片
        body = self.pusher.format_markdown_message(signals, "【09:23 早盘锁板精选】", sentiment)

        self.assertIn("09:23", body)
        self.assertIn("四川金顶", body)
        self.assertIn("操作指引", body)
        self.assertIn("次日涨停预期", body)
        self.assertIn("防守止损", body)


if __name__ == "__main__":
    unittest.main()
