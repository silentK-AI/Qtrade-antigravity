"""
单元测试：盘中交易时段实时异动监控与推送测试 (09:30 - 14:50)
"""

import unittest
from unittest.mock import MagicMock
from models.stock_item import IntradayEvent
from strategies.intraday_monitor import IntradayMonitor
from notifications.wechat_pusher import WeChatPusher


class TestIntradayMonitor(unittest.TestCase):

    def setUp(self):
        self.mock_provider = MagicMock()
        self.monitor = IntradayMonitor(provider=self.mock_provider)
        self.pusher = WeChatPusher()

    def test_initialization_does_not_fire_false_events(self):
        """测试首次启动建档不误报存量股票"""
        self.mock_provider.fetch_today_zt_pool_details.return_value = {
            "600519": {"name": "贵州茅台", "price": 1800.0, "seal_amount": 500000000.0, "continuous_boards": 1, "open_board_count": 0, "first_seal_time": "09:31:00", "last_seal_time": "09:31:00", "turnover_rate": 1.2}
        }
        self.mock_provider.fetch_today_zb_pool_details.return_value = {
            "000001": {"name": "平安银行", "current_price": 12.0, "change_pct": 8.0, "open_board_count": 1, "first_seal_time": "09:35:00", "turnover_rate": 3.5}
        }

        # 第一次调用 check_events 会自动触发 initialize_current_state，返回空列表
        events = self.monitor.check_events()
        self.assertEqual(len(events), 0)
        self.assertTrue(self.monitor.is_initialized)
        self.assertIn("600519", self.monitor.seen_zt_stocks)
        self.assertIn("000001", self.monitor.seen_zb_stocks)

    def test_detect_new_limit_up_seal(self):
        """测试捕获盘中新晋级封板标的"""
        # 初始建档
        self.mock_provider.fetch_today_zt_pool_details.return_value = {}
        self.mock_provider.fetch_today_zb_pool_details.return_value = {}
        self.monitor.initialize_current_state()

        # 盘中发生新封板：主板 600609 金杯汽车 2连板，创业板 300123（需被过滤）
        self.mock_provider.fetch_today_zt_pool_details.return_value = {
            "600609": {
                "name": "金杯汽车",
                "price": 5.80,
                "change_pct": 10.06,
                "seal_amount": 60000000.0,  # 6000万
                "continuous_boards": 2,
                "open_board_count": 0,
                "first_seal_time": "10:15:20",
                "last_seal_time": "10:15:20",
                "turnover_rate": 5.2
            },
            "300123": {
                "name": "创业板股",
                "price": 20.0,
                "change_pct": 20.0,
                "seal_amount": 10000000.0,
                "continuous_boards": 1,
                "open_board_count": 0
            }
        }

        events = self.monitor.check_events()
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev.event_type, "LIMIT_UP")
        self.assertEqual(ev.code, "600609")
        self.assertEqual(ev.name, "金杯汽车")
        self.assertEqual(ev.continuous_boards, 2)
        self.assertIn("2 进 3 接力", ev.action_advice)
        self.assertIn("600609", self.monitor.seen_zt_stocks)

        # 再次检查时状态去重，不再重复触发
        events_again = self.monitor.check_events()
        self.assertEqual(len(events_again), 0)

    def test_detect_broken_board_event(self):
        """测试捕获盘中炸板开板异动与风险建议"""
        self.mock_provider.fetch_today_zt_pool_details.return_value = {
            "002596": {
                "name": "海南瑞泽",
                "price": 4.50,
                "seal_amount": 30000000.0,
                "continuous_boards": 1,
                "open_board_count": 0,
                "first_seal_time": "09:32:00",
                "last_seal_time": "09:32:00",
                "turnover_rate": 4.0
            }
        }
        self.mock_provider.fetch_today_zb_pool_details.return_value = {}
        self.monitor.initialize_current_state()

        # 随后海南瑞泽炸板，回落至 +7.5%
        self.mock_provider.fetch_today_zb_pool_details.return_value = {
            "002596": {
                "name": "海南瑞泽",
                "current_price": 4.40,
                "change_pct": 7.5,
                "open_board_count": 1,
                "first_seal_time": "09:32:00",
                "turnover_rate": 8.0
            }
        }

        events = self.monitor.check_events()
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev.event_type, "BROKEN_BOARD")
        self.assertEqual(ev.code, "002596")
        self.assertIn("低吸", ev.action_advice)
        self.assertNotIn("002596", self.monitor.seen_zt_stocks)

    def test_reseal_after_broken_board(self):
        """测试炸板后顽强回封（烂板出妖/弱转强）识别"""
        self.mock_provider.fetch_today_zt_pool_details.return_value = {}
        self.mock_provider.fetch_today_zb_pool_details.return_value = {
            "600715": {
                "name": "文投控股",
                "current_price": 2.50,
                "change_pct": 6.8,
                "open_board_count": 1,
                "first_seal_time": "09:40:00",
                "turnover_rate": 10.5
            }
        }
        self.monitor.initialize_current_state()

        # 文投控股重新回封！
        self.mock_provider.fetch_today_zt_pool_details.return_value = {
            "600715": {
                "name": "文投控股",
                "price": 2.59,
                "change_pct": 10.21,
                "seal_amount": 35000000.0,
                "continuous_boards": 1,
                "open_board_count": 1,
                "first_seal_time": "09:40:00",
                "last_seal_time": "14:10:00",
                "turnover_rate": 12.0
            }
        }

        events = self.monitor.check_events()
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev.event_type, "LIMIT_UP")
        self.assertEqual(ev.code, "600715")
        self.assertIn("烂板出妖", ev.action_advice)
        self.assertIn("弱转强", ev.reason)

    def test_wechat_formatting(self):
        """测试盘中异动卡片微信 Markdown 格式化"""
        ev1 = IntradayEvent(
            event_type="LIMIT_UP",
            code="600609",
            name="金杯汽车",
            current_price=5.80,
            change_pct=10.06,
            event_time="10:15:20",
            seal_amount_wan=6000.0,
            turnover_rate=5.2,
            open_board_count=0,
            continuous_boards=2,
            action_advice="【建议：重点打板/参与 2 进 3 接力】",
            reason="1 进 2 换手晋级成功，确立身位优势。封单 6000 万元，承接有力。"
        )
        title, md = self.pusher.format_intraday_events([ev1])
        self.assertIn("金杯汽车", title)
        self.assertIn("2连板", title)
        self.assertIn("金杯汽车", md)
        self.assertIn("10:15:20", md)
        self.assertIn("重点打板", md)
        self.assertIn("原因逻辑", md)


if __name__ == "__main__":
    unittest.main()
