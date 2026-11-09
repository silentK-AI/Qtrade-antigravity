"""
单元测试：09:23 不可撤单阶段抢筹锁板策略测试
"""

import unittest
from data.mock_replay import MockReplayProvider
from strategies.auction_0923 import Auction0923Screener


class TestAuction0923Strategy(unittest.TestCase):

    def setUp(self):
        self.screener = Auction0923Screener()
        self.dataset = MockReplayProvider.get_0923_dataset()

    def test_0923_screener_execution(self):
        signals = self.screener.run_strategy(self.dataset, sentiment_multiplier=1.0)
        signal_codes = [s.code for s in signals]

        # 标的 600678 真实不可撤单 9500 万死封必须高分入选
        self.assertIn("600678", signal_codes, "600678 必须成功入选 09:23 铁板池")
        
        # 标的 601888 (9:19-9:20 撤单率75% 诱多标的) 必须被一票否决淘汰
        self.assertNotIn("601888", signal_codes, "虚假撤单诱多标的必须被淘汰")

        # 检查首位标的信号属性
        top_signal = signals[0]
        self.assertGreaterEqual(top_signal.score, 80.0)
        self.assertGreaterEqual(top_signal.capital_score, 40.0)
        self.assertIn("09:23", top_signal.suggested_action)


if __name__ == "__main__":
    unittest.main()
