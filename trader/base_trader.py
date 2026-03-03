"""
交易执行基类
"""
from abc import ABC, abstractmethod
from strategy.signal import TradeOrder
from risk.position_manager import PositionManager


class BaseTrader(ABC):
    """所有交易执行器的基类"""

    def __init__(self, position_manager: PositionManager):
        self._pm = position_manager

    @abstractmethod
    def execute(self, order: TradeOrder) -> bool:
        """
        执行交易指令。

        Args:
            order: 交易指令

        Returns:
            是否执行成功
        """
        ...

    @abstractmethod
    def connect(self) -> bool:
        """连接交易通道"""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """断开交易通道"""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """是否已连接"""
        ...
