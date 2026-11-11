"""
15:10 盘后涨停复盘与次日预案模块单元测试
"""

import unittest
from strategies.post_market_report import PostMarketReportScreener
from notifications.wechat_pusher import WeChatPusher


class TestPostMarketReport(unittest.TestCase):
    def setUp(self):
        self.screener = PostMarketReportScreener()
        self.mock_dataset = [
            {
                "code": "002578",
                "name": "闽发铝业",
                "close_price": 5.51,
                "pre_close": 5.01,
                "close_pct": 9.98,
                "high_pct": 9.98,
                "low_pct": 9.98,
                "turnover_rate": 5.8,
                "amount_yi": 2.8,
                "float_cap_yi": 45.0,
                "is_today_limit_up": True,
                "consecutive_boards": 6
            },
            {
                "code": "002588",
                "name": "四板龙头",
                "close_price": 11.00,
                "pre_close": 10.00,
                "close_pct": 10.00,
                "high_pct": 10.00,
                "low_pct": 10.00,
                "turnover_rate": 4.2,
                "amount_yi": 3.1,
                "float_cap_yi": 38.0,
                "is_today_limit_up": True,
                "yesterday_boards": 3,
                "consecutive_boards": 4
            },
            {
                "code": "002086",
                "name": "东方海洋",
                "close_price": 4.37,
                "pre_close": 3.97,
                "close_pct": 10.08,
                "high_pct": 10.08,
                "low_pct": 4.79,
                "turnover_rate": 40.2,
                "amount_yi": 27.2,
                "float_cap_yi": 32.0,
                "is_today_limit_up": True,
                "yesterday_boards": 2,
                "consecutive_boards": 3
            },
            {
                "code": "600540",
                "name": "新赛股份",
                "close_price": 4.87,
                "pre_close": 4.58,
                "close_pct": 6.33,
                "high_pct": 10.04,
                "low_pct": -1.53,
                "turnover_rate": 18.5,
                "amount_yi": 5.2,
                "float_cap_yi": 28.0,
                "is_today_limit_up": False,
                "yesterday_boards": 1,
                "consecutive_boards": 1
            },
            {
                "code": "603999",
                "name": "深水大面股",
                "close_price": 8.10,
                "pre_close": 9.00,
                "close_pct": -10.00,
                "high_pct": 5.00,
                "low_pct": -10.00,
                "turnover_rate": 25.0,
                "amount_yi": 8.0,
                "float_cap_yi": 30.0,
                "is_today_limit_up": False,
                "yesterday_boards": 2,
                "consecutive_boards": 2
            },
            {
                "code": "603888",
                "name": "四进五断板高标",
                "close_price": 9.10,
                "pre_close": 10.00,
                "close_pct": -9.00,
                "high_pct": 2.00,
                "low_pct": -9.50,
                "turnover_rate": 30.0,
                "amount_yi": 9.0,
                "float_cap_yi": 35.0,
                "is_today_limit_up": False,
                "yesterday_boards": 4,
                "consecutive_boards": 4
            }
        ]

    def test_screener_output(self):
        report = self.screener.run_report(self.mock_dataset)
        # 1. 顶部汇总保留全市场真实数据 (全部 6 只昨日涨停股：3只今日连板、3只断板、最高 6 连板)
        self.assertEqual(report.total_yesterday_count, 6)
        self.assertEqual(report.today_continue_count, 3)
        self.assertEqual(report.broken_board_count, 3)
        self.assertEqual(report.advancement_rate, 50.0)
        self.assertEqual(report.highest_board, 6)
        self.assertIn("闽发铝业", report.highest_board_stock)
        self.assertEqual(report.tier_distribution, {6: 1, 4: 1, 3: 1})

        # 2. 个股梳理列表严格仅保留 1进2/2进3/3进4 标的（剔除 6连板 002578 与 4进5断板 603888）
        items = report.items
        codes = [x.code for x in items]
        self.assertEqual(len(items), 4)
        self.assertNotIn("002578", codes)
        self.assertNotIn("603888", codes)
        self.assertTrue(items[0].is_today_limit_up)
        self.assertEqual(items[0].consecutive_boards, 4)
        self.assertIn("一字", items[0].board_status)

        # 检查深水大面股建议
        bad_stock = next(x for x in items if x.code == "603999")
        self.assertIn("坚决规避", bad_stock.next_day_action)

    def test_wechat_formatting(self):
        report = self.screener.run_report(self.mock_dataset)
        pusher = WeChatPusher()
        md = pusher.format_post_market_report(report)
        self.assertIn("15:10 盘后涨停复盘", md)
        self.assertIn("全市场昨日涨停", md)
        self.assertIn("闽发铝业 (002578) [6连板]", md)
        self.assertIn("1进2 / 2进3 / 3进4 连板晋级池", md)
        self.assertIn("四板龙头", md)
        self.assertNotIn("002578)**", md)


if __name__ == "__main__":
    unittest.main()
