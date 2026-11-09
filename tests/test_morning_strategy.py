"""
单元测试：早盘集合竞价打板策略与评分测试
"""

import unittest
from data.mock_replay import MockReplayProvider
from strategies.morning_auction import MorningAuctionScreener


class TestMorningAuctionStrategy(unittest.TestCase):

    def setUp(self):
        self.screener = MorningAuctionScreener()
        self.dataset = MockReplayProvider.get_morning_auction_dataset()

    def test_morning_screener_execution(self):
        signals = self.screener.run_strategy(self.dataset, sentiment_multiplier=1.0)
        
        # 验证至少筛选出符合条件的优质标的 (如 600123 和 002456)
        signal_codes = [s.code for s in signals]
        self.assertIn("600123", signal_codes, "600123 优质1进2标的应成功入选")
        self.assertIn("002456", signal_codes, "002456 弱转强反包标的应成功入选")

        # 验证创业板 300123 与 ST 600666 被严格过滤
        self.assertNotIn("300123", signal_codes, "创业板标的必须被排除")
        self.assertNotIn("600666", signal_codes, "ST标的必须被排除")

        # 验证低分/弱势标的 000999 与假拉诱多 603789 不及格
        self.assertNotIn("000999", signal_codes, "弱势低开标的不应入选")
        self.assertNotIn("603789", signal_codes, "虚假高开标的不应入选")

        # 检查信号属性、资金得分与止损价
        top_signal = signals[0]
        self.assertGreaterEqual(top_signal.score, 75.0)
        self.assertGreaterEqual(top_signal.capital_score, 30.0, "资金因子得分应突出")
        self.assertGreater(top_signal.stop_loss_price, 0)
        self.assertIn("预期", top_signal.next_day_expectation)


if __name__ == "__main__":
    unittest.main()
