"""
单元测试：14:58 尾盘集合竞价锁定次日涨停策略测试
"""

import unittest
from data.mock_replay import MockReplayProvider
from models.stock_item import StockQuote, Snapshot1458
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

    def test_1458_risk_vetoes_and_top3_cap(self):
        """验证高3日换手派发、低封成比虚封、多炸板烂板一票否决，且优质高封成比龙头排第一、输出严格不超过3只"""
        def _make_pair(code, name, amount, turnover, seal_amt, seal_float, zbc, lbt, to3d, yb=1, lbc=2):
            q = StockQuote(
                code=code, name=name, market="SH" if code.startswith("6") else "SZ",
                current_price=10.0, pre_close=9.09, open_price=9.5, high_price=10.0,
                low_price=9.4, change_pct=10.0, volume=1e7, amount=amount,
                turnover_rate=turnover, float_market_cap=20.0, total_market_cap=25.0,
                yesterday_status=f"昨日{yb}连板" if yb >= 2 else ("昨日首板" if yb == 1 else "普通"),
                yesterday_boards=yb, is_limit_up=True
            )
            seal_to_amt = (seal_amt / amount * 100.0) if amount > 0 else 0.0
            snap = Snapshot1458(
                code=code, indicative_price=10.0, indicative_change_pct=10.0,
                is_limit_up=True, closing_seal_amount=seal_amt, seal_to_float_ratio=seal_float,
                day_open_board_count=zbc, first_seal_time=lbt, continuous_board_count=lbc,
                last_seal_time=lbt, turnover_3d=to3d, seal_to_amount_ratio=round(seal_to_amt, 2)
            )
            return (q, snap)

        elite_1 = _make_pair("002160", "优质惜售一", 2.5e8, 6.3, 1.09e8, 7.0, 0, "14:19:00", 19.2)
        elite_2 = _make_pair("603536", "优质惜售二", 1.92e8, 7.8, 4.03e7, 6.0, 0, "14:28:00", 17.6, yb=2, lbc=3)
        elite_3 = _make_pair("001314", "优质惜售三", 2.43e8, 4.8, 4.00e7, 5.0, 0, "13:49:00", 11.9, yb=3, lbc=4)
        elite_4 = _make_pair("000782", "备选良性四", 1.77e8, 5.0, 3.18e7, 4.0, 0, "13:55:00", 15.0)
        trap_to3d = _make_pair("002045", "高位派发股", 9.78e8, 16.1, 7.08e7, 4.0, 1, "14:09:00", 57.0)
        trap_weak_seal = _make_pair("600892", "虚封派发股", 10.0e8, 20.0, 1.67e7, 2.0, 0, "14:41:00", 35.0)
        trap_rotten = _make_pair("601188", "高频烂板股", 19.2e8, 32.4, 8.99e6, 0.5, 11, "14:48:00", 62.9)

        signals = self.screener.run_strategy(
            [trap_to3d, trap_weak_seal, trap_rotten, elite_4, elite_3, elite_2, elite_1],
            sentiment_multiplier=1.0
        )
        codes = [s.code for s in signals]
        self.assertEqual(len(codes), 3, "精选输出严格不超过 Top 3 只")
        self.assertEqual(codes[0], "002160", "高封成比+低3日换手龙头必须排第1")
        self.assertNotIn("002045", codes, "近3日换手>48%派发股必须被否决")
        self.assertNotIn("600892", codes, "封成比<3%虚封股必须被否决")
        self.assertNotIn("601188", codes, "炸板>=4次烂板股必须被否决")

        sc_rotten, _, pat_rotten, _, _, _ = self.screener.calculate_1458_score(*trap_rotten)
        self.assertGreaterEqual(sc_rotten, 0.0, "得分应规范钳位在 >= 0.0")
        self.assertIn("回避", pat_rotten)

        # 验证严格梯队限制：0进1首板、昨日未涨停蓄势、4进5高标均必须被剔除
        first_board = _make_pair("600701", "零进一首板", 2.0e8, 6.0, 8.0e7, 6.0, 0, "14:20:00", 12.0, yb=0, lbc=1)
        high_board = _make_pair("600702", "四进五高标", 2.0e8, 6.0, 8.0e7, 6.0, 0, "14:20:00", 20.0, yb=4, lbc=5)
        unsealed_0 = (
            StockQuote(
                code="600703", name="零板未封", market="SH",
                current_price=10.75, pre_close=10.0, open_price=10.1, high_price=10.8,
                low_price=10.0, change_pct=7.5, volume=1e7, amount=1.075e8,
                turnover_rate=8.0, float_market_cap=30.0, total_market_cap=35.0,
                yesterday_status="普通", yesterday_boards=0, is_limit_up=False, net_large_inflow=50000000.0
            ),
            Snapshot1458(
                code="600703", indicative_price=10.75, indicative_change_pct=7.5,
                is_limit_up=False, closing_seal_amount=0.0, seal_to_float_ratio=0.0,
                day_open_board_count=0, first_seal_time="15:00", continuous_board_count=0
            )
        )
        rejected = self.screener.run_strategy([first_board, high_board, unsealed_0], sentiment_multiplier=1.0)
        self.assertEqual(rejected, [], "0进1首板、零板未封与4进5高标必须全部淘汰")


if __name__ == "__main__":
    unittest.main()
