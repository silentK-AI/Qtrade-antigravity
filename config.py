"""
配置文件
"""
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(BASE_DIR, ".env")
load_dotenv(env_path, override=True)

# API配置 - 通过第三方API调用Gemini
# 第三方API配置
THIRD_PARTY_API_BASE_URL = os.getenv("THIRD_PARTY_API_BASE_URL", "https://hiapi.online/v1")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "sk-wIddyarusR7H9wZyxhxvecRXctBaafuNNvXBUuKMMyffTL0q")

# 设置环境变量供 LiteLLM 和 CrewAI 使用
# 使用第三方API，需要设置OPENAI_API_KEY和API_BASE
os.environ["OPENAI_API_KEY"] = GEMINI_API_KEY
os.environ["OPENAI_API_BASE"] = THIRD_PARTY_API_BASE_URL

# 设置 LiteLLM 的重试配置以避免 429 错误
os.environ["LITELLM_NUM_RETRIES"] = "3"
os.environ["LITELLM_RETRY_DELAY"] = "2"  # 重试延迟（秒）

# 禁用 CrewAI 的遥测和追踪功能（避免生成无法访问的链接）
os.environ["CREWAI_TELEMETRY_OPT_OUT"] = "1"
os.environ["DO_NOT_TRACK"] = "1"

# CrewAI 使用第三方API调用Gemini模型
# 第三方API兼容OpenAI格式，使用openai/前缀
# 分析决策智能体使用：gemini-2.5-pro-maxthinking（更强大的模型用于复杂分析）
GEMINI_ANALYSIS_MODEL = os.getenv("GEMINI_ANALYSIS_MODEL", "openai/gemini-2.5-pro-maxthinking")
# 其他智能体使用：gemini-2.5-flash（快速模型用于数据收集和资讯收集）
GEMINI_FLASH_MODEL = os.getenv("GEMINI_FLASH_MODEL", "openai/gemini-2.5-flash")
# 备用模型：当主模型遇到 429 错误时使用
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "openai/gemini-2.5-flash")
# 为了向后兼容，保留GEMINI_MODEL（默认使用flash模型）
_default_gemini_model = os.getenv("GEMINI_MODEL")
GEMINI_MODEL = _default_gemini_model if _default_gemini_model else GEMINI_FLASH_MODEL

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

