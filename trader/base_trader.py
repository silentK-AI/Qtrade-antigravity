"""
交易执行基类
"""
from abc import ABC, abstractmethod
from loguru import logger
from strategy.signal import TradeOrder
from risk.position_manager import PositionManager
from config.etf_settings import ETF_UNIVERSE


class BaseTrader(ABC):
    """所有交易执行器的基类"""

    # 允许交易的标的白名单（仅限 T+0 ETF）
    ALLOWED_CODES = set(ETF_UNIVERSE.keys())

    def __init__(self, position_manager: PositionManager):
        self._pm = position_manager

    def execute(self, order: TradeOrder) -> bool:
        """
        执行交易指令（含白名单校验）。

        Args:
            order: 交易指令

        Returns:
            是否执行成功
        """
        # 白名单校验：只允许交易 ETF_UNIVERSE 中定义的 T+0 ETF
        if order.etf_code not in self.ALLOWED_CODES:
            logger.error(
                f"[安全拦截] 标的 {order.etf_code} 不在允许交易的白名单中! "
                f"仅允许: {sorted(self.ALLOWED_CODES)}"
            )
            return False

        return self._do_execute(order)

    @abstractmethod
    def _do_execute(self, order: TradeOrder) -> bool:
        """
        实际执行交易指令（子类实现）。

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
