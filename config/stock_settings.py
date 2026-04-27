"""
个股技术指标监控与推送 - 全局配置
"""
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(BASE_DIR, ".env")
load_dotenv(env_path, override=True)

# ============================================================
#  个股技术指标监控与推送
# ============================================================
STOCK_ALERT_SYMBOLS = {
    # 核心持仓/自选股票 (按用户指定顺序)
    "002230": {"name": "科大讯飞", "type": "stock", "exchange": "SZ"},  # 注意：用户原提供002030为笔误
    "002050": {"name": "三花智控", "type": "stock", "exchange": "SZ"},
    "000559": {"name": "万向钱潮", "type": "stock", "exchange": "SZ"},
    "301666": {"name": "大普微", "type": "stock", "exchange": "SZ"},
    "300274": {"name": "阳光电源", "type": "stock", "exchange": "SZ"},
    "300750": {"name": "宁德时代", "type": "stock", "exchange": "SZ"},
    "000988": {"name": "华工科技", "type": "stock", "exchange": "SZ"},
    "000063": {"name": "中兴通讯", "type": "stock", "exchange": "SZ"},
    "000333": {"name": "美的集团", "type": "stock", "exchange": "SZ"},
    "000100": {"name": "TCL科技", "type": "stock", "exchange": "SZ"},
    "002475": {"name": "立讯精密", "type": "stock", "exchange": "SZ"},
    "603667": {"name": "五洲新春", "type": "stock", "exchange": "SH"},
    "300308": {"name": "中际旭创", "type": "stock", "exchange": "SZ"},
    "002472": {"name": "双环传动", "type": "stock", "exchange": "SZ"},
    "601899": {"name": "紫金矿业", "type": "stock", "exchange": "SH"},
    
    # 行业/宽基 ETF (按用户指定顺序)
    "588200": {"name": "科创芯片ETF", "type": "etf", "exchange": "SH"},
    "159227": {"name": "航空航天ETF", "type": "etf", "exchange": "SZ"},
    "515230": {"name": "软件ETF", "type": "etf", "exchange": "SH"},
    "159326": {"name": "电网设备ETF", "type": "etf", "exchange": "SZ"},
    "159363": {"name": "AIGC ETF", "type": "etf", "exchange": "SZ"},
    "159770": {"name": "机器人ETF", "type": "etf", "exchange": "SZ"},
    "159767": {"name": "电池龙头ETF", "type": "etf", "exchange": "SZ"},
}

ALERT_PREMARKET_TIME = "09:25"      # 盘前报告推送时间（9:25开盘后获取开盘价）
ALERT_CLOSE_TIME    = "15:05"      # 收盘报告推送时间
ALERT_TRADE_AMOUNT  = 10000        # 模拟每笔操作金额（元）
ALERT_SCAN_INTERVAL = 30            # 盘中扫描间隔（秒）
ALERT_SIGNAL_COOLDOWN = 1800        # 同一标的同方向信号冷却时间（秒）= 30分钟
ALERT_HISTORY_DAYS = 260            # 技术指标需要的历史数据天数（260天支持MA250和近1年涨跌幅）
