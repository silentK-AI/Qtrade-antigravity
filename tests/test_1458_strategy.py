"""
单元测试：14:58 尾盘集合竞价锁定次日涨停策略测试
"""

import unittest
from data.mock_replay import MockReplayProvider
from strategies.closing_1458 import Closing1458Screener


class TestClosing1458Strategy(unittest.TestCase):

    def setUp(self):
        self.screener = Closing1458Screener()
        self.dataset = MockReplayProvider.get_1458_dataset()

    def test_1458_screener_execution(self):
        signals = self.screener.run_strategy(self.dataset, sentiment_multiplier=1.0)
        signal_codes = [s.code for s in signals]

        # 标的 600789 (早盘封死+上亿大单) 识别为风向标/锁仓标的
        self.assertIn("600789", signal_codes, "600789 必须在榜")
        # 标的 000888 (尾盘刚回封) 识别为可排进买入标的
        self.assertIn("000888", signal_codes, "000888 尾盘回封能买进标的必须入选")
        # 标的 600345 (尾盘蓄势未板) 识别为100%买进标的
        self.assertIn("600345", signal_codes, "600345 尾盘蓄势100%买进标的必须入选")

        # 标的 600111 (平庸标的) 必须被淘汰
        self.assertNotIn("600111", signal_codes, "平庸标的必须被淘汰")

        for s in signals:
            self.assertGreaterEqual(s.score, 80.0)
            self.assertIn("14:58", s.suggested_action)


if __name__ == "__main__":
    unittest.main()
