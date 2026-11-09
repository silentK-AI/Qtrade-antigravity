"""
策略抽象基类与通用因子计算工具
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
from models.stock_item import StockQuote, StrategySignal
from utils.filters import StockFilter


class BaseScreener(ABC):
    """选股策略基类"""

    def __init__(self, filter_instance: StockFilter = None):
        self.stock_filter = filter_instance or StockFilter()

    @abstractmethod
    def run_strategy(self, *args, **kwargs) -> List[StrategySignal]:
        """运行策略并输出信号列表"""
        pass

    def calculate_stop_loss(self, current_price: float, risk_tolerance_pct: float = 3.5) -> float:
        """根据当前价格与风险容忍度动态计算防守止损位"""
        return round(current_price * (1.0 - risk_tolerance_pct / 100.0), 2)
