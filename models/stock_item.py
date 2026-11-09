"""
数据模型与实体定义
包含行情切片、竞价特征、尾盘特征与策略选股打分结果
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class StockQuote:
    """股票实时/快照行情对象"""
    code: str                   # 纯数字代码，如 '600519', '000001'
    name: str                   # 股票名称
    market: str                 # 'SH' 或 'SZ'
    current_price: float        # 当前价/最新成交价
    pre_close: float            # 昨收价
    open_price: float           # 今日开盘价
    high_price: float           # 今日最高价
    low_price: float            # 今日最低价
    change_pct: float           # 涨跌幅 (%)，例如 5.32
    volume: float               # 成交量（股）
    amount: float               # 成交金额（元）
    turnover_rate: float        # 换手率 (%)
    float_market_cap: float     # 流通市值（亿元）
    total_market_cap: float     # 总市值（亿元）
    pe_ratio: float = 0.0       # 市盈率
    sector: str = "未分类"       # 所属行业/核心题材
    
    # 扩展属性
    yesterday_status: str = "普通"  # 昨涨停(首板/连板)、昨炸板、昨阴线等
    is_limit_up: bool = False      # 当前是否已涨停
    vwap: float = 0.0              # 当日分时均价 (amount / volume)


@dataclass
class AuctionSnapshot:
    """早盘集合竞价切片特征 (09:15 - 09:25)"""
    code: str
    auction_price: float           # 9:25 最终撮合开盘价
    gap_percent: float             # 竞价高开涨跌幅 (%)
    auction_volume: float          # 9:25 竞价成交量（股）
    auction_amount: float          # 9:25 竞价成交额（元）
    prev_day_volume: float         # 前一日全天成交量（股）
    auction_vol_ratio: float       # 竞价成交量占前一日成交量比例 (0.0 ~ 1.0)
    unmatched_buy_volume: float    # 9:25 集合竞价未匹配买单量（买一挂单排队余量）
    unmatched_amount: float        # 9:25 未匹配买单总金额（元）
    bid_ask_strength: float        # 盘口抢筹买卖意愿强弱比
    is_924_rush: bool = False      # 9:24-9:25 是否出现最后时刻挂单向上抢筹


@dataclass
class ClosingSnapshot:
    """尾盘分时切片特征 (14:30 - 15:00)"""
    code: str
    current_price: float           # 尾盘当前价
    day_high: float                # 全天最高价
    close_to_high_ratio: float     # 当前价 / 最高价 比例
    current_change_pct: float      # 当前涨跌幅 (%)
    vwap: float                    # 当日分时均线价格
    is_above_vwap: bool            # 是否在均价线之上
    tail_volume: float             # 14:30以后的尾盘成交量（股）
    total_volume: float            # 全天累计成交量（股）
    tail_vol_ratio: float          # 尾盘成交量占全天比例
    tail_net_large_inflow: float   # 尾盘大单/特大单净买入额（万元）
    is_rebound_limit: bool = False # 是否属于首板烂板后尾盘强回封


@dataclass
class Snapshot0923:
    """早盘不可撤单阶段特征切片 (09:23:00 提取，锁定当天封死全天且次日涨停)"""
    code: str
    indicative_price: float        # 9:23 拟撮合开盘价
    indicative_change_pct: float   # 9:23 拟撮合涨跌幅 (%)
    real_seal_amount: float        # 9:23 不可撤单阶段真实买一排队封单金额（元）
    real_seal_to_float_ratio: float# 封单占自由流通市值千分比 (‰)
    spoof_withdrawn_ratio: float   # 9:19-9:20 虚假撤单比例 (0.0 ~ 1.0)
    is_sealed_limit: bool          # 9:23 是否已顶在涨停价（或逼近涨停）
    volume_920_923: float          # 9:20-9:23 真实新增撮合成交量（股）
    is_upward_rush: bool = True    # 9:20-9:23 拟撮合价是否持续向上跳档抢筹


@dataclass
class Snapshot1458:
    """尾盘集合竞价切片特征 (14:58:00 提取，锁定次日大概率涨停)"""
    code: str
    indicative_price: float        # 14:58 收盘集合竞价拟撮合价
    indicative_change_pct: float   # 14:58 拟撮合涨幅 (%)
    is_limit_up: bool              # 14:58 是否已坚决封死涨停
    closing_seal_amount: float     # 14:58 涨停板封单排队资金（元）
    seal_to_float_ratio: float     # 封单占流通市值千分比 (‰)
    day_open_board_count: int      # 全天炸板次数（0次代表金身不破）
    first_seal_time: str           # 首次封板时间（如 "09:36:00"）
    continuous_board_count: int = 1# 当前连板高度（如 1板、2板）
    last_seal_time: str = ""       # 最后封板时间（如 "14:55:23"）


@dataclass
class StrategySignal:
    """策略选股信号输出结果"""
    code: str
    name: str
    strategy_type: str             # "早盘竞价打板" 或 "尾盘抢筹打板"
    score: float                   # 综合评分 (0 - 100)
    capital_score: float           # 资金因子专属得分 (权重占比 >= 55%)
    current_price: float           # 当前价/竞价开盘价
    change_pct: float              # 涨跌幅 (%)
    target_pattern: str            # 典型形态：如 "1进2爆量抢筹" / "尾盘蓄势冲板"
    key_factors: Dict[str, Any]    # 关键因子明细与证据
    suggested_action: str          # 建议买入方式（如 "竞价挂单市价委托" / "回踩均线分批建仓"）
    stop_loss_price: float         # 建议防守止损价
    next_day_expectation: str      # 次日涨停预期与逻辑说明


@dataclass
class YesterdayLimitUpItem:
    """昨日涨停股票今日表现复盘与次日预案数据项"""
    code: str
    name: str
    close_price: float             # 今日收盘价
    close_pct: float               # 今日收盘涨跌幅 (%)
    high_pct: float                # 今日最高涨幅 (%)
    low_pct: float                 # 今日最低跌幅 (%)
    turnover_rate: float           # 今日换手率 (%)
    amount_yi: float               # 今日成交额（亿元）
    float_cap_yi: float            # 流通市值（亿元）
    consecutive_boards: int        # 连板数 (若今日涨停: 2, 3, 4...；若未涨停: 1 代表昨日首板断板)
    is_today_limit_up: bool        # 今日是否继续涨停
    board_status: str              # 连板状态备注 (如 "【3连板·主线龙头】"、"【断板冲高回落】")
    next_day_action: str           # 第二天是否打板建议 (如 "【强势连板·次日可打板】"、"【禁止接盘·观望】")
    detail_reason: str             # 逻辑分析与操作要点


@dataclass
class PostMarketReportData:
    """15:10 盘后涨停复盘综合统计数据"""
    report_time: str               # 报告生成时间
    total_yesterday_count: int     # 昨日主板涨停总数
    today_continue_count: int      # 今日成功连板家数
    broken_board_count: int        # 今日断板家数
    advancement_rate: float        # 今日晋级率 (%)
    highest_board: int             # 市场最高连板高度
    highest_board_stock: str       # 最高连板龙头标的 (代码+名称)
    tier_distribution: Dict[int, int] # 连板梯队分布 (如 {3: 1, 2: 12})
    sentiment_summary: str         # 明日打板总基调与行情定位
    items: List[YesterdayLimitUpItem] = field(default_factory=list)

