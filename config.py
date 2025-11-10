"""
配置文件
"""
import os
from dotenv import load_dotenv

load_dotenv()

# API配置 - Google Gemini
# 注意：请通过环境变量或 .env 文件设置 GEMINI_API_KEY
# 在 .env 文件中添加：GEMINI_API_KEY=your_api_key_here
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError(
        "未设置 GEMINI_API_KEY 环境变量。"
        "请在 .env 文件中设置 GEMINI_API_KEY，或使用环境变量。"
    )

# 设置环境变量供 LiteLLM 和 CrewAI 使用
os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY
# 设置 LiteLLM 的重试配置以避免 429 错误
os.environ["LITELLM_NUM_RETRIES"] = "3"
os.environ["LITELLM_RETRY_DELAY"] = "2"  # 重试延迟（秒）

# 禁用 CrewAI 的遥测和追踪功能（避免生成无法访问的链接）
os.environ["CREWAI_TELEMETRY_OPT_OUT"] = "1"
os.environ["DO_NOT_TRACK"] = "1"
# 注意：即使环境中存在 OPENAI_API_KEY，CrewAI 也会优先使用 Gemini（因为模型名称明确指定了 gemini/）

# CrewAI 使用正确的 Gemini 模型名称
# 注意：对于 LiteLLM，使用 gemini/ 前缀
# 主模型：gemini-2.0-flash
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini/gemini-2.0-flash")
# 备用模型：当主模型遇到 429 错误时使用
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini/gemini-2.0-flash-live")

# 数据源配置
DATA_SOURCE = "akshare"  # 使用akshare获取中国股市数据

# 股票数据配置
DEFAULT_START_DATE = "20210101"  # 默认开始日期（三年前）
DEFAULT_END_DATE = None  # 默认结束日期（今天）

# 数据字段配置
STOCK_DATA_COLUMNS = [
    "日期", "开盘", "收盘", "最高", "最低", 
    "成交量", "成交额", "振幅", "涨跌幅", "涨跌额",
    "换手率", "量比"
]

# 资讯搜索配置
NEWS_SOURCES = [
    "公司公告",
    "券商研报",
    "大宗商品价格",
    "美联储议息决议",
    "美国关税政策"
]

