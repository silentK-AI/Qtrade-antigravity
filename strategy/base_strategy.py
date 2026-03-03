"""
策略基类
"""
from abc import ABC, abstractmethod
from strategy.signal import MarketSnapshot, TradingSignal


class BaseStrategy(ABC):
    """所有交易策略的基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """策略名称"""
        ...

    @abstractmethod
    def evaluate(self, snapshot: MarketSnapshot) -> TradingSignal:
        """
        根据行情快照生成交易信号。

        Args:
            snapshot: 行情快照

        Returns:
            交易信号
        """
        ...

    @abstractmethod
    def reset(self) -> None:
        """重置策略状态（用于新交易日）"""
        ...
