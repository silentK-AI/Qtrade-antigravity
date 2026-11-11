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
        with patch.object(scheduler.data_provider, "fetch_main_board_top_active", return_value=[]), \
             patch.object(scheduler.data_provider, "fetch_yesterday_limit_up_pool", return_value=[{"code": "002160", "name": "常铝股份"}]), \
             patch.object(scheduler.data_provider, "fetch_realtime_quotes", return_value=[rq_preopen]):
            cands = scheduler._get_0923_candidates()

        self.assertEqual(len(cands), 1)
        q_out, snap_out = cands[0]
        self.assertAlmostEqual(snap_out.indicative_change_pct, 10.0, places=1)
        self.assertTrue(snap_out.is_sealed_limit)
        self.assertEqual(q_out.yesterday_status, "昨日首板")

        signals = self.screener.run_strategy(cands, sentiment_multiplier=1.0)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].code, "002160")
        self.assertGreaterEqual(signals[0].score, 80.0)


if __name__ == "__main__":
    unittest.main()
