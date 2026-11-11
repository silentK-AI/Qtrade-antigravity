"""
单元测试：早盘集合竞价打板策略与评分测试
"""

import unittest
from data.mock_replay import MockReplayProvider
from models.stock_item import StockQuote, AuctionSnapshot
from strategies.morning_auction import MorningAuctionScreener


class TestMorningAuctionStrategy(unittest.TestCase):

    def setUp(self):
        self.screener = MorningAuctionScreener()
        self.dataset = MockReplayProvider.get_morning_auction_dataset()

    def test_morning_screener_execution(self):
        signals = self.screener.run_strategy(self.dataset, sentiment_multiplier=1.0)
        
        # 验证筛选出符合条件的 1进2 与 2进3 优质标的 (600123 和 002456)
        signal_codes = [s.code for s in signals]
        self.assertIn("600123", signal_codes, "600123 优质1进2标的应成功入选")
        self.assertIn("002456", signal_codes, "002456 优质2进3标的应成功入选")

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

    def test_morning_only_allows_123_to_234_boards(self):
        """验证早盘竞价严格排除 0进1（未涨停反包/普通）与 4进5 高标，保留 3进4"""
        def _make(code, yb, status):
            q = StockQuote(
                code=code, name=f"标{code}", market="SH",
                current_price=12.43, pre_close=12.00, open_price=12.43,
                high_price=12.43, low_price=12.43, change_pct=3.58,
                volume=4500000, amount=55935000, turnover_rate=1.8,
                float_market_cap=55.0, total_market_cap=60.0,
                yesterday_status=status, yesterday_boards=yb
            )
            a = AuctionSnapshot(
                code=code, auction_price=12.43, gap_percent=3.58,
                auction_volume=4500000, auction_amount=55935000,
                prev_day_volume=36000000, auction_vol_ratio=0.125,
                unmatched_buy_volume=1800000, unmatched_amount=22374000,
                bid_ask_strength=3.2, is_924_rush=True
            )
            return (q, a)

        cands = [
            _make("600021", 0, "昨日冲高回落"),  # 0进1 -> 排除
            _make("600022", 3, "昨日3连板"),     # 3进4 -> 保留
            _make("600023", 4, "昨日4连板"),     # 4进5 -> 排除
        ]
        codes = [s.code for s in self.screener.run_strategy(cands, sentiment_multiplier=1.0)]
        self.assertEqual(codes, ["600022"])


if __name__ == "__main__":
    unittest.main()
