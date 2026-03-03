"""
ETF T+0 量化交易系统 - 全局配置
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
#  交易标的池
#  每个 ETF 配置：名称、跟踪指数代码、关联期货代码、交易所后缀
# ============================================================
ETF_UNIVERSE = {
    "513180": {
        "name": "恒生科技ETF",
        "ref_index": "HSI_TECH",
        "ref_futures": "HTI",
        "exchange": "SH",
        "currency": "HKD",
    },
    "159920": {
        "name": "恒生ETF",
        "ref_index": "HSI",
        "ref_futures": "HSI",
        "exchange": "SZ",
        "currency": "HKD",
    },
    "159941": {
        "name": "纳指ETF",
        "ref_index": "NDX",
        "ref_futures": "NQ=F",
        "exchange": "SZ",
        "currency": "USD",
    },
    "513500": {
        "name": "标普500ETF",
        "ref_index": "SPX",
        "ref_futures": "ES=F",
        "exchange": "SH",
        "currency": "USD",
    },
    "513400": {
        "name": "道琼斯ETF",
        "ref_index": "DJI",
        "ref_futures": "YM=F",
        "exchange": "SH",
        "currency": "USD",
    },
    "513880": {
        "name": "日经ETF",
        "ref_index": "N225",
        "ref_futures": "NKD=F",
        "exchange": "SH",
        "currency": "JPY",
    },
    "513310": {
        "name": "中韩半导体ETF",
        "ref_index": "SOX",
        "ref_futures": "SOX",
        "exchange": "SH",
        "currency": "USD",
    },
}

# 默认启用的标的（可在运行时通过命令行参数覆盖）
ACTIVE_ETFS = list(ETF_UNIVERSE.keys())

# ============================================================
#  交易时间
# ============================================================
MARKET_OPEN = "09:30"
MARKET_CLOSE = "15:00"
FORCE_CLOSE_TIME = "14:50"   # 强制平仓时间
NO_OPEN_AFTER = "14:30"      # 此时间后不再开新仓

# ============================================================
#  风控参数（科学退出引擎）
# ============================================================
# 1. 价格屏障 (ATR 动态位)
ATR_MULTIPLIER_TP = 2.0       # 止盈：Entry + 2.0 * ATR
ATR_MULTIPLIER_SL = 1.2       # 止损：Entry - 1.2 * ATR
# 2. 时间屏障 (衰减退出)
TIME_DECAY_MINUTES = 30       # 买入后 30 分钟无利即出
# 3. 盈利保卫 (保本损)
PROFIT_GUARD_THRESHOLD = 0.004 # 盈利超过 0.4% 时启动保本
PROFIT_GUARD_RETRACEMENT = 0.0005 # 回落至 0.05% 利润时平仓 (Entry + 0.05%)

TAKE_PROFIT_PCT = 0.008       # 默认止盈 0.8% (作为兜底)
STOP_LOSS_PCT = 0.005         # 默认止损 0.5% (作为兜底)
TRAILING_STOP_PCT = 0.003     # 跟踪止损回撤 0.3%
MAX_DAILY_TRADES = 3          # 每标的每日最大交易笔数
MAX_POSITION_PCT = 0.30       # 单标的最大仓位占总资产比例
MAX_TOTAL_POSITION_PCT = 0.80 # 所有标的合计最大仓位占总资产比例
INITIAL_CAPITAL = 10000.0    # 初始资金（模拟交易用）
ETF_COMMISSION_RATE = 0.000061 # ETF 交易佣金率为 0.61%%

# ============================================================
#  策略参数
# ============================================================
PREMIUM_THRESHOLD = 0.003     # 溢价阈值 0.3%
DISCOUNT_THRESHOLD = -0.003   # 折价阈值 -0.3%
FUTURES_MOMENTUM_WINDOW = 5   # 期货动量计算窗口（分钟）
SIGNAL_COOLDOWN_SECONDS = 300 # 同一标的同方向信号冷却时间（秒）
GLOBAL_TRADE_COOLDOWN_SECONDS = 60 # 同一标的任意两次交易间的最小间隔（秒）
MIN_SIGNAL_PERSISTENCE_COUNT = 2   # 信号持久化：连续 N 次扫描信号一致才执行
VOLUME_CONFIRM_RATIO = 1.2    # 成交量确认倍率（需大于均量的此倍数）

# ============================================================
#  ML 预测策略参数
# ============================================================
ML_MODEL_DIR = os.getenv("ML_MODEL_DIR", "models")       # 模型存储目录
ML_TRAINING_DAYS = 180                                     # 训练数据天数
ML_PRED_CONFIDENCE_THRESHOLD = 0.3                         # 预测置信度阈值
ML_PRED_BUY_BUFFER = 0.001                                 # 买入缓冲（预测最低价 + buffer）
ML_PRED_SELL_BUFFER = 0.001                                # 卖出缓冲（预测最高价 - buffer）
ML_ENABLED = os.getenv("ML_ENABLED", "true").lower() == "true"  # 是否启用 ML 策略

# ============================================================
#  系统参数
# ============================================================
DATA_REFRESH_INTERVAL = 3     # 数据刷新间隔（秒）
SCAN_INTERVAL = 5             # 主循环扫描间隔（秒）
LOG_DIR = os.getenv("LOG_DIR", "logs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
