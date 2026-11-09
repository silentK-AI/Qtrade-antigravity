"""
单元测试：尾盘选股打板策略与评分测试
"""

import unittest
from data.mock_replay import MockReplayProvider
from strategies.closing_stage import ClosingStageScreener


class TestClosingStageStrategy(unittest.TestCase):

    def setUp(self):
        self.screener = ClosingStageScreener()
        self.dataset = MockReplayProvider.get_closing_stage_dataset()

    def test_closing_screener_execution(self):
        signals = self.screener.run_strategy(self.dataset, sentiment_multiplier=1.0)
        
        signal_codes = [s.code for s in signals]
        # 600345 (蓄势待发·尾盘抢筹) 应高分入选
        self.assertIn("600345", signal_codes, "600345 尾盘抢筹蓄势冲板标的应入选")
        # 000568 (首板强回封) 应入选
        self.assertIn("000568", signal_codes, "000568 首板强回封标的应入选")

        # 601999 (冲高跳水跌破均线) 应被彻底淘汰
        self.assertNotIn("601999", signal_codes, "跌破均线跳水标的必须淘汰")

        # 验证止损价、资金得分与买入指引
        for s in signals:
            self.assertGreaterEqual(s.score, 75.0)
            self.assertGreaterEqual(s.capital_score, 30.0, "资金因子得分应突出")
            self.assertLess(s.stop_loss_price, s.current_price)
            self.assertTrue(len(s.suggested_action) > 0)


if __name__ == "__main__":
    unittest.main()
