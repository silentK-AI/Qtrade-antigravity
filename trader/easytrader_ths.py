"""
easytrader 交易执行器 - 通过同花顺客户端自动下单

使用前提:
1. Windows 环境
2. pip install easytrader
3. 同花顺交易客户端已登录
"""
import os
from typing import Optional
from loguru import logger

from trader.base_trader import BaseTrader
from strategy.signal import TradeOrder, OrderSide
from risk.position_manager import PositionManager


class EasyTrader(BaseTrader):
    """
    同花顺 easytrader 交易执行器。

    通过 easytrader 操控同花顺客户端完成买卖操作。
    """

    def __init__(self, position_manager: PositionManager):
        super().__init__(position_manager)
        self._connected = False
        self._user = None  # easytrader user object
        self._broker = os.getenv("EASYTRADER_BROKER", "ths")  # ths = 同花顺

    def connect(self) -> bool:
        """连接同花顺客户端"""
        try:
            import easytrader

            logger.info(f"正在连接同花顺客户端 (broker={self._broker})...")

            self._user = easytrader.use(self._broker)

            # 连接方式：同花顺客户端需已手动登录
            # easytrader 通过操控已打开的客户端窗口来下单
            exe_path = os.getenv("THS_EXE_PATH", "")
            if exe_path:
                self._user.connect(exe_path)
                logger.info(f"已连接同花顺客户端: {exe_path}")
            else:
                # 自动检测已打开的同花顺客户端
                self._user.connect()
                logger.info("已连接同花顺客户端（自动检测）")

            # 验证连接 - 查询余额
            try:
                balance = self._user.balance
                logger.info(f"账户余额: {balance}")
            except Exception as e:
                logger.warning(f"查询余额失败（不影响交易）: {e}")

            self._connected = True
            return True

        except ImportError:
            logger.error(
                "easytrader 未安装。请运行:\n"
                "  pip install easytrader\n"
                "并确保同花顺客户端已打开并登录。"
            )
            return False
        except Exception as e:
            logger.error(f"同花顺连接失败: {e}")
            return False

    def execute(self, order: TradeOrder) -> bool:
        """执行交易指令"""
        if not self._connected or self._user is None:
            logger.error("同花顺未连接，无法执行交易")
            return False

        try:
            stock_code = order.etf_code  # ETF 代码，如 "159941"

            if order.side == OrderSide.BUY:
                # 买入 - 限价单
                result = self._user.buy(
                    stock_code,
                    price=order.price,
                    amount=order.quantity,
                )
                logger.info(
                    f"[同花顺] 买入 {order.etf_code} {order.etf_name} "
                    f"{order.quantity}股 @ {order.price:.4f} | "
                    f"结果: {result} | {order.reason}"
                )

                # 更新 PositionManager
                if result:
                    self._pm.open_position(
                        order.etf_code, order.etf_name,
                        order.price, order.quantity,
                        reason=order.reason,
                    )
                    return True

            else:
                # 卖出 - 限价单
                result = self._user.sell(
                    stock_code,
                    price=order.price,
                    amount=order.quantity,
                )
                logger.info(
                    f"[同花顺] 卖出 {order.etf_code} {order.etf_name} "
                    f"{order.quantity}股 @ {order.price:.4f} | "
                    f"结果: {result} | {order.reason}"
                )

                if result:
                    self._pm.close_position(
                        order.etf_code, order.price, order.quantity,
                        reason=order.reason,
                    )
                    return True

            return False

        except Exception as e:
            logger.error(f"[同花顺] 交易执行异常: {e}")
            return False

    def disconnect(self) -> None:
        """断开连接"""
        self._user = None
        self._connected = False
        logger.info("同花顺客户端已断开")

    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    #  辅助方法
    # ------------------------------------------------------------------

    def get_position(self) -> list:
        """查询当前持仓"""
        if not self._connected or self._user is None:
            return []
        try:
            return self._user.position
        except Exception as e:
            logger.error(f"查询持仓失败: {e}")
            return []

    def get_balance(self) -> dict:
        """查询账户余额"""
        if not self._connected or self._user is None:
            return {}
        try:
            return self._user.balance
        except Exception as e:
            logger.error(f"查询余额失败: {e}")
            return {}

    def get_today_trades(self) -> list:
        """查询当日成交"""
        if not self._connected or self._user is None:
            return []
        try:
            return self._user.today_trades
        except Exception as e:
            logger.error(f"查询成交失败: {e}")
            return []

    def cancel_all(self) -> None:
        """撤销所有未成交委托"""
        if not self._connected or self._user is None:
            return
        try:
            entrusts = self._user.today_entrusts
            for ent in entrusts:
                # 只撤未成交的
                if ent.get("备注", "") not in ("已成", "已撤"):
                    self._user.cancel_entrust(ent.get("合同编号", ""))
            logger.info("已撤销所有未成交委托")
        except Exception as e:
            logger.error(f"撤单失败: {e}")
