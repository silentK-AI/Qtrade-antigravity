"""
量化分析系统 - 全局配置中心
资金因子为主导（资金权重 >= 55%），支持四个独立时间窗口的核心参数与阈值配置：
1. 09:23:00 - 早盘不可撤单竞价抢筹锁定（次日继续涨停）
2. 09:25:00 - 早盘开盘撮合完成精选
3. 14:50:00 - 尾盘异动蓄势潜伏
4. 14:58:00 - 尾盘集合竞价锁死次日涨停
"""

import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class MainBoardFilterConfig:
    """主板股票过滤配置"""
    ALLOWED_PREFIXES: tuple = ("600", "601", "603", "605", "000", "001", "002", "003")
    EXCLUDED_PREFIXES: tuple = ("300", "301", "688", "8", "4", "9")
    FILTER_ST: bool = True
    MIN_FLOAT_MARKET_CAP: float = 20.0     # 最小流通市值（亿元）
    MAX_FLOAT_MARKET_CAP: float = 250.0    # 最大流通市值（亿元）
    MIN_LISTED_DAYS: int = 60


@dataclass
class PreAuction0923Config:
    """09:23:00 早盘不可撤单竞价策略配置（买入窗口：09:23 - 09:24:50）"""
    CAPITAL_WEIGHT: float = 0.60           # 09:23 资金权重提高至 60%
    PRICE_TECH_WEIGHT: float = 0.25
    BASE_WEIGHT: float = 0.15

    # 1. 资金核心门槛：
    # 9:20 - 9:23 不可撤单阶段买一真实封单金额最低门槛（万元）
    MIN_REAL_SEAL_AMOUNT: float = 3000.0   # 真实买一资金至少 3000 万
    HIGH_REAL_SEAL_AMOUNT: float = 8000.0  # 8000 万以上判定为大机构强顶一整天
    # 真实买一封单金额占自由流通市值比例最低要求 (‰)
    MIN_SEAL_FLOAT_RATIO: float = 3.0      # 至少占流通盘千分之三
    
    # 2. 撤单诱多过滤（9:15-9:20 虚假撤单率必须极低）：
    MAX_SPOOF_WITHDRAW_RATIO: float = 0.20 # 9:19-9:20 撤单率超过 20% 判定为诱多直接淘汰

    # 3. 拟撮合涨幅门槛：必须在 +5.0% 以上，+9.5%~+10.0% 顶板为最优
    MIN_INDICATIVE_GAP: float = 5.0

    SCORE_THRESHOLD: float = 80.0          # 提高及格门槛至 80 分


@dataclass
class MorningAuctionConfig:
    """早盘集合竞价策略配置（09:25:00 锁定）"""
    CAPITAL_WEIGHT: float = 0.55
    PRICE_TECH_WEIGHT: float = 0.30
    BASE_WEIGHT: float = 0.15

    MIN_AUCTION_VOL_RATIO: float = 0.06
    HIGH_AUCTION_VOL_RATIO: float = 0.12
    MIN_AUCTION_AMOUNT: float = 1500.0
    MIN_UNMATCHED_RATIO: float = 0.5

    MIN_GAP_PERCENT: float = 1.8
    MAX_GAP_PERCENT: float = 6.0
    ENABLE_ONE_TO_TWO: bool = True
    SCORE_THRESHOLD: float = 75.0


@dataclass
class ClosingStageConfig:
    """尾盘选股策略配置（14:50:00 锁定）"""
    CAPITAL_WEIGHT: float = 0.55
    PRICE_TECH_WEIGHT: float = 0.30
    BASE_WEIGHT: float = 0.15

    MIN_TAIL_VOL_RATIO: float = 0.18
    MIN_TAIL_LARGE_INFLOW: float = 1000.0

    MIN_CHANGE_PERCENT: float = 3.5
    MAX_CHANGE_PERCENT: float = 9.8
    MIN_CLOSE_TO_HIGH_RATIO: float = 0.980
    REQUIRE_ABOVE_VWAP: bool = True

    MIN_TURNOVER_RATE: float = 5.0
    MAX_TURNOVER_RATE: float = 25.0
    SCORE_THRESHOLD: float = 75.0


@dataclass
class ClosingAuction1458Config:
    """14:58:00 尾盘集合竞价策略配置（买入窗口：14:58 - 14:59:50）"""
    CAPITAL_WEIGHT: float = 0.60           # 资金权重提高至 60%
    PRICE_TECH_WEIGHT: float = 0.25
    BASE_WEIGHT: float = 0.15

    # 1. 资金核心门槛：
    # 14:58 收盘集合竞价不可撤单封单排队金额（万元）
    MIN_CLOSING_SEAL_AMOUNT: float = 5000.0 # 封单至少 5000 万
    HIGH_CLOSING_SEAL_AMOUNT: float = 10000.0 # 1 亿以上超级大资金封死
    MIN_SEAL_FLOAT_RATIO: float = 5.0       # 封单占流通盘至少千分之五

    # 2. 板块与日内抗开板硬度：
    # 全天炸板次数上限：0次（全天零开板代表筹码坚不可摧，次日大概率继续顶涨停）
    MAX_DAY_OPEN_COUNT: int = 1
    # 首次封板时间要求：早盘10:30前首次封板，封板时间越早次日溢价越确定
    
    SCORE_THRESHOLD: float = 80.0


@dataclass
class SentimentConfig:
    """市场情绪周期风控配置"""
    PANIC_EXPLODED_RATIO: float = 0.40
    MAX_DOWN_LIMIT_COUNT: int = 15


@dataclass
class PostMarketReportConfig:
    """15:10 盘后涨停复盘与次日打板预案配置"""
    TRIGGER_TIME: str = "15:10:05"        # 触发时间（15:10分准时生成推送）
    MAX_DISPLAY_ITEMS: int = 40           # 最多展示个股数
    PROMOTION_RATE_ALERT: float = 0.35    # 晋级率低于 35% 判定为退潮预警
    HIGH_BOARD_ALERT: int = 4             # 4板及以上高标提示分歧风险



@dataclass
class WeChatNotifyConfig:
    """微信通知推送配置 - 优先自动读取服务器现有环境变量与 .env 配置"""
    # 自动探测环境变量中已配置的 Token，如果有则默认启用
    PUSHPLUS_TOKEN: str = field(
        default_factory=lambda: (
            os.getenv("PUSHPLUS_TOKEN")
            or os.getenv("PUSH_PLUS_TOKEN")
            or os.getenv("PUSH_TOKEN")
            or "f82973cf1342485fa7114d4f888fbbe2"
        )
    )
    # 默认开启微信推送
    ENABLED: bool = field(
        default_factory=lambda: (
            os.getenv("NOTIFY_ENABLED", "true").lower() != "false"
        )
    )
    CHANNEL: str = "pushplus"
    SERVERCHAN_KEY: str = field(default_factory=lambda: os.getenv("SERVERCHAN_KEY", ""))
    WECOM_WEBHOOK_KEY: str = field(default_factory=lambda: os.getenv("WECOM_WEBHOOK_KEY", ""))

