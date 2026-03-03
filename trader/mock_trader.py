"""
模拟交易执行器 - 用于 Paper Trading 和回测
"""
from loguru import logger

from trader.base_trader import BaseTrader
from strategy.signal import TradeOrder, OrderSide
from risk.position_manager import PositionManager


class MockTrader(BaseTrader):
    """
    模拟交易器。

    不连接任何真实交易通道，直接在 PositionManager 中记录买卖操作。
    """

    def __init__(self, position_manager: PositionManager):
        super().__init__(position_manager)
        self._connected = False

    def execute(self, order: TradeOrder) -> bool:
        """模拟执行交易"""
        if not self._connected:
            logger.error("模拟交易器未连接")
            return False

        if order.quantity <= 0:
            logger.warning(f"[{order.etf_code}] 数量为 0，跳过")
            return False

        if order.side == OrderSide.BUY:
            success = self._pm.open_position(
                etf_code=order.etf_code,
                etf_name=order.etf_name,
                price=order.price,
                quantity=order.quantity,
                reason=order.reason,
                timestamp=order.timestamp,
            )
        else:
            success = self._pm.close_position(
                etf_code=order.etf_code,
                price=order.price,
                quantity=order.quantity,
                reason=order.reason,
                timestamp=order.timestamp,
            )

        if success:
            logger.info(
                f"[模拟] {order.side.value} {order.etf_code} "
                f"{order.quantity}股 @ {order.price:.4f} | {order.reason}"
            )
        return success

    def connect(self) -> bool:
        self._connected = True
        logger.info("模拟交易器已连接")
        return True

    def disconnect(self) -> None:
        self._connected = False
        logger.info("模拟交易器已断开")

    def is_connected(self) -> bool:
        return self._connected
