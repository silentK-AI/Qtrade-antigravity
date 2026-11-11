"""
单元测试：09:23 不可撤单阶段抢筹锁板策略测试
"""

import json
import unittest
from unittest.mock import patch
from data.mock_replay import MockReplayProvider
from data.open_data_provider import OpenDataProvider
from daemon_scheduler import ServerDaemonScheduler
from models.stock_item import StockQuote, Snapshot0923
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

    def test_0923_call_auction_dash_and_zero_volume_resilience(self):
        """回归验证：09:23未成交集合竞价阶段的 '-' 空值、腾讯现价=昨收、买一排单及0成交量不再导致全军覆没"""
        provider = OpenDataProvider()
        # 模拟东财 09:23 集合竞价返回：含停牌股全 '-' 以及正常高开股 f5/f6/f15/f16/f17/f62 为 '-'
        mock_clist = json.dumps({
            "data": {
                "diff": [
                    {"f12": "000003", "f14": "PT金田A", "f2": "-", "f3": "-", "f5": "-", "f6": "-", "f8": 0.0, "f15": "-", "f16": "-", "f17": "-", "f18": 2.71, "f20": "-", "f21": "-", "f62": "-"},
                    {"f12": "603366", "f14": "日出东方", "f2": 11.97, "f3": 10.02, "f5": "-", "f6": "-", "f8": 0.0, "f15": "-", "f16": "-", "f17": "-", "f18": 10.88, "f20": 9732000000, "f21": 9732000000, "f62": "-"}
                ]
            }
        })
        with patch.object(provider, "_get_url_content", return_value=mock_clist):
            quotes = provider.fetch_main_board_top_active(page_size=50)
            yest_items = provider.fetch_yesterday_limit_up_pool()

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0].code, "603366")
        self.assertAlmostEqual(quotes[0].change_pct, 10.02)
        self.assertEqual(len(yest_items), 1)

        # 验证 09:23 集合竞价阶段腾讯现价=昨收、volume=0、仅 buy1_price=涨停价 时正确还原并打分入选
        scheduler = ServerDaemonScheduler(source="live")
        rq_preopen = StockQuote(
            code="002160", name="常铝股份", market="SZ",
            current_price=4.00, pre_close=4.00, open_price=0.0,
            high_price=0.0, low_price=0.0, change_pct=0.0,
            volume=0.0, amount=0.0, turnover_rate=0.0,
            float_market_cap=45.4, total_market_cap=45.4,
            buy1_price=4.40, buy1_volume=10000000.0, sell1_price=0.0, sell1_volume=0.0
        )
        scheduler.snapshot_0919 = {"002160": {"buy1_volume": 9500000.0, "volume": 0.0, "price": 4.40}}
        rq_4board = StockQuote(
            code="600999", name="高标四板", market="SH",
            current_price=22.00, pre_close=20.00, open_price=22.00,
            high_price=22.00, low_price=22.00, change_pct=10.0,
            volume=100000.0, amount=2200000.0, turnover_rate=1.0,
            float_market_cap=50.0, total_market_cap=55.0,
            buy1_price=22.00, buy1_volume=10000000.0, sell1_price=0.0, sell1_volume=0.0
        )
        with patch.object(scheduler.data_provider, "fetch_main_board_top_active", return_value=[]), \
             patch.object(scheduler.data_provider, "fetch_prev_day_zt_boards", return_value={"002160": 1, "600999": 4}), \
             patch.object(scheduler.data_provider, "fetch_realtime_quotes", return_value=[rq_preopen, rq_4board]):
            cands = scheduler._get_0923_candidates()

        self.assertEqual(len(cands), 1, "仅保留昨日1/2/3板，昨日4板(4进5)必须过滤")
        q_out, snap_out = cands[0]
        self.assertAlmostEqual(snap_out.indicative_change_pct, 10.0, places=1)
        self.assertTrue(snap_out.is_sealed_limit)
        self.assertEqual(q_out.yesterday_status, "昨日首板")
        self.assertEqual(q_out.yesterday_boards, 1)

        signals = self.screener.run_strategy(cands, sentiment_multiplier=1.0)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].code, "002160")
        self.assertGreaterEqual(signals[0].score, 80.0)

    def test_0923_rejects_first_board_and_high_board(self):
        """验证 09:23 严格拒绝 0进1 首板与 4进5 高标，仅接纳 1进2/2进3/3进4"""
        def _make_item(code, yb, status):
            q = StockQuote(
                code=code, name=f"测试{code}", market="SH",
                current_price=11.0, pre_close=10.0, open_price=11.0,
                high_price=11.0, low_price=11.0, change_pct=10.0,
                volume=3000000, amount=33000000, turnover_rate=2.0,
                float_market_cap=45.0, total_market_cap=48.0,
                yesterday_status=status, yesterday_boards=yb
            )
            s = Snapshot0923(
                code=code, indicative_price=11.0, indicative_change_pct=10.0,
                real_seal_amount=90000000.0, real_seal_to_float_ratio=6.5,
                spoof_withdrawn_ratio=0.01, is_sealed_limit=True,
                volume_920_923=2000000.0, is_upward_rush=True
            )
            return (q, s)

        cands = [
            _make_item("600010", 0, "普通"),       # 0进1 -> 排除
            _make_item("600011", 3, "昨日3连板"),  # 3进4 -> 入选
            _make_item("600012", 4, "昨日4连板"),  # 4进5 -> 排除
        ]
        codes = [sig.code for sig in self.screener.run_strategy(cands, sentiment_multiplier=1.0)]
        self.assertEqual(codes, ["600011"])


if __name__ == "__main__":
    unittest.main()
