"""
交易信号定义
"""
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class SignalType(Enum):
    """信号类型"""
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


class OrderSide(Enum):
    """交易方向"""
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class MarketSnapshot:
    """单个标的的行情快照"""
    etf_code: str
    etf_name: str
    timestamp: datetime

    # ETF 行情
    etf_price: float = 0.0          # ETF 最新价
    etf_open: float = 0.0           # 开盘价
    etf_high: float = 0.0           # 最高价
    etf_low: float = 0.0            # 最低价
    etf_volume: float = 0.0         # 成交量
    etf_amount: float = 0.0         # 成交额
    etf_bid1: float = 0.0           # 买一价
    etf_ask1: float = 0.0           # 卖一价

    # IOPV
    iopv: float = 0.0               # 基金实时估值

    # 关联期货/指数
    futures_price: float = 0.0      # 关联期货/指数最新价
    futures_change_pct: float = 0.0 # 关联期货/指数涨跌幅(%)

    # 汇率
    exchange_rate: float = 1.0      # 对应货币兑人民币汇率

    # 计算指标
    premium_rate: float = 0.0       # 溢价率 = (ETF价格 - IOPV) / IOPV
    futures_momentum: float = 0.0   # 期货动量（N分钟变化率）

    @property
    def is_valid(self) -> bool:
        """数据是否有效"""
        return self.etf_price > 0 and self.iopv > 0


@dataclass
class TradingSignal:
    """交易信号"""
    etf_code: str
    etf_name: str
    signal_type: SignalType
    timestamp: datetime
    price: float                     # 当前 ETF 价格
    iopv: float                      # 当前 IOPV
    premium_rate: float              # 当前溢价率
    futures_momentum: float          # 期货动量
    strength: float = 0.0            # 信号强度 (0-1)
    reason: str = ""                 # 信号理由

    @property
    def is_actionable(self) -> bool:
        """信号是否可执行（非 HOLD）"""
        return self.signal_type not in (SignalType.HOLD,)


@dataclass
class TradeOrder:
    """交易指令"""
    etf_code: str
    etf_name: str
    side: OrderSide
    price: float                     # 目标价格
    quantity: int                    # 数量（股）
    timestamp: datetime = field(default_factory=datetime.now)
    order_id: str = ""               # 委托编号（由交易执行器填充）
    reason: str = ""                 # 下单理由


@dataclass
class Position:
    """持仓信息"""
    etf_code: str
    etf_name: str
    quantity: int                    # 持仓数量
    avg_cost: float                  # 持仓均价
    current_price: float = 0.0       # 当前价格
    highest_price: float = 0.0       # 持仓以来最高价（用于跟踪止损）
    open_time: datetime = field(default_factory=datetime.now)
    profit_guard_active: bool = False # 是否已激活保本损（盈利过 0.4% 后触发）

    @property
    def market_value(self) -> float:
        """持仓市值"""
        return self.quantity * self.current_price

    @property
    def cost_value(self) -> float:
        """持仓成本"""
        return self.quantity * self.avg_cost

    @property
    def pnl(self) -> float:
        """浮动盈亏"""
        return self.market_value - self.cost_value

    @property
    def pnl_pct(self) -> float:
        """浮动盈亏百分比"""
        if self.cost_value == 0:
            return 0.0
        return self.pnl / self.cost_value

    @property
    def drawdown_from_high(self) -> float:
        """从最高价回撤幅度"""
        if self.highest_price == 0:
            return 0.0
        return (self.highest_price - self.current_price) / self.highest_price
