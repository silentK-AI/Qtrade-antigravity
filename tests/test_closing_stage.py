"""
单元测试：尾盘选股打板策略与评分测试
"""

import unittest
from data.mock_replay import MockReplayProvider
from models.stock_item import StockQuote, ClosingSnapshot
from strategies.closing_stage import ClosingStageScreener


class TestClosingStageStrategy(unittest.TestCase):

    def setUp(self):
        self.screener = ClosingStageScreener()
        self.dataset = MockReplayProvider.get_closing_stage_dataset()

    def test_closing_screener_execution(self):
        signals = self.screener.run_strategy(self.dataset, sentiment_multiplier=1.0)
        
        signal_codes = [s.code for s in signals]
        # 600345 (1进2蓄势待发·尾盘抢筹) 应高分入选
        self.assertIn("600345", signal_codes, "600345 1进2尾盘抢筹蓄势冲板标的应入选")
        # 000568 (2进3强回封) 应入选
        self.assertIn("000568", signal_codes, "000568 2进3强回封标的应入选")

        # 601999 (冲高跳水跌破均线) 应被彻底淘汰
        self.assertNotIn("601999", signal_codes, "跌破均线跳水标的必须淘汰")

        # 验证止损价、资金得分与买入指引
        for s in signals:
            self.assertGreaterEqual(s.score, 75.0)
            self.assertGreaterEqual(s.capital_score, 30.0, "资金因子得分应突出")
            self.assertLess(s.stop_loss_price, s.current_price)
            self.assertTrue(len(s.suggested_action) > 0)

    def test_closing_stage_only_allows_123_to_234(self):
        """验证 14:50 严格排除 0进1 与 4进5 高标"""
        def _make(code, yb, status):
            q = StockQuote(
                code=code, name=f"标{code}", market="SH",
                current_price=16.88, pre_close=15.80, open_price=16.00,
                high_price=16.95, low_price=15.90, change_pct=6.84,
                volume=35000000, amount=577500000, turnover_rate=11.5,
                float_market_cap=48.0, total_market_cap=52.0,
                yesterday_status=status, yesterday_boards=yb, vwap=16.50
            )
            c = ClosingSnapshot(
                code=code, current_price=16.88, day_high=16.95,
                close_to_high_ratio=0.996, current_change_pct=6.84,
                vwap=16.50, is_above_vwap=True,
                tail_volume=8400000, total_volume=35000000,
                tail_vol_ratio=0.24, tail_net_large_inflow=4800.0,
                is_rebound_limit=False
            )
            return (q, c)

        cands = [
            _make("600031", 0, "普通"),       # 0进1 -> 排除
            _make("600032", 3, "昨日3连板"),  # 3进4 -> 保留
            _make("600033", 4, "昨日4连板"),  # 4进5 -> 排除
        ]
        codes = [s.code for s in self.screener.run_strategy(cands, sentiment_multiplier=1.0)]
        self.assertEqual(codes, ["600032"])


if __name__ == "__main__":
    unittest.main()
