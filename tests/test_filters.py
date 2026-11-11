"""
单元测试：主板代码与风控规则过滤测试
"""

import unittest
from utils.filters import StockFilter
from models.stock_item import StockQuote


class TestStockFilter(unittest.TestCase):

    def setUp(self):
        self.filter = StockFilter()

    def test_main_board_detection(self):
        # 沪市主板
        self.assertTrue(self.filter.is_main_board_code("600519"))
        self.assertTrue(self.filter.is_main_board_code("601398"))
        self.assertTrue(self.filter.is_main_board_code("603288"))
        self.assertTrue(self.filter.is_main_board_code("605111"))

        # 深市主板
        self.assertTrue(self.filter.is_main_board_code("000001"))
        self.assertTrue(self.filter.is_main_board_code("000858"))
        self.assertTrue(self.filter.is_main_board_code("002456"))

        # 创业板 (应被排除)
        self.assertFalse(self.filter.is_main_board_code("300750"))
        self.assertFalse(self.filter.is_main_board_code("301234"))

        # 科创板 (应被排除)
        self.assertFalse(self.filter.is_main_board_code("688981"))

        # 北交所 (应被排除)
        self.assertFalse(self.filter.is_main_board_code("832023"))
        self.assertFalse(self.filter.is_main_board_code("430047"))

    def test_st_and_abnormal_names(self):
        # 正常名字
        self.assertTrue(self.filter.is_valid_name("贵州茅台"))
        self.assertTrue(self.filter.is_valid_name("五粮液"))
        
        # ST 系列
        self.assertFalse(self.filter.is_valid_name("ST大集"))
        self.assertFalse(self.filter.is_valid_name("*ST左江"))
        self.assertFalse(self.filter.is_valid_name("退市保千"))
        
        # 新股无涨跌幅
        self.assertFalse(self.filter.is_valid_name("N新股"))
        self.assertFalse(self.filter.is_valid_name("C次新"))

    def test_market_cap_filter(self):
        # 自由流通市值小于20亿 (流动性不足)
        self.assertFalse(self.filter.check_market_cap(12.5))
        # 自由流通市值超过250亿 (超大盘股)
        self.assertFalse(self.filter.check_market_cap(350.0))
        # 正常区间
        self.assertTrue(self.filter.check_market_cap(55.0))

    def test_relay_board_filter(self):
        """验证全系统仅放行 1进2 / 2进3 / 3进4 接力标的，严格剔除 0进1 与 4进5+"""
        def _make_quote(status="普通", yb=0, is_lu=False):
            return StockQuote(
                code="600519", name="测试股", market="SH",
                current_price=10.0, pre_close=9.09, open_price=9.5,
                high_price=10.0, low_price=9.4, change_pct=10.0,
                volume=1000000, amount=10000000, turnover_rate=3.0,
                float_market_cap=50.0, total_market_cap=55.0,
                yesterday_status=status, yesterday_boards=yb, is_limit_up=is_lu
            )

        self.assertTrue(self.filter.is_target_relay_quote(_make_quote(status="昨日首板")))
        self.assertTrue(self.filter.is_target_relay_quote(_make_quote(status="昨日2连板")))
        self.assertTrue(self.filter.is_target_relay_quote(_make_quote(status="昨日3连板")))
        self.assertTrue(self.filter.is_target_relay_quote(_make_quote(yb=3, is_lu=True), today_boards=4))

        self.assertFalse(self.filter.is_target_relay_quote(_make_quote(status="普通", yb=0)))
        self.assertFalse(self.filter.is_target_relay_quote(_make_quote(status="昨日冲高回落", yb=0)))
        self.assertFalse(self.filter.is_target_relay_quote(_make_quote(status="昨日4连板")))
        self.assertFalse(self.filter.is_target_relay_quote(_make_quote(yb=4, is_lu=True), today_boards=5))
        self.assertFalse(self.filter.is_target_relay_quote(_make_quote(yb=1, is_lu=True), today_boards=1))


if __name__ == "__main__":
    unittest.main()
