"""
单元测试：模块对外 Facade 门面测试
"""

import unittest
from limit_up_module import LimitUpModule


class TestLimitUpFacade(unittest.TestCase):

    def setUp(self):
        self.module = LimitUpModule(pushplus_token="mock_test_token", source="mock")

    def test_module_methods(self):
        # 测试 09:23 门面调用
        signals_0923 = self.module.run_0923(push=False)
        self.assertGreater(len(signals_0923), 0)

        # 测试 14:58 门面调用
        signals_1458 = self.module.run_1458(push=False)
        self.assertGreater(len(signals_1458), 0)

        # 测试 09:25 与 14:50
        signals_0925 = self.module.run_0925(push=False)
        signals_1450 = self.module.run_1450(push=False)
        self.assertGreater(len(signals_0925), 0)
        self.assertGreater(len(signals_1450), 0)


if __name__ == "__main__":
    unittest.main()
