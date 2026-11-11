"""
主板标的过滤与风控初筛工具
严格执行：
1. 仅保留沪深主板（600/601/603/605/000/001/002/003）
2. 剔除创业板(300/301)、科创板(688)、北交所(8/4/9)
3. 剔除 ST、*ST、退市整理、上市初期新股 (N/C字头)
4. 过滤极小盘流动性陷阱与超大盘迟钝股
"""

import re
from typing import Optional
from config import MainBoardFilterConfig
from models.stock_item import StockQuote


class StockFilter:
    """股票主板及风控过滤器（全系统仅梳理 1进2、2进3、3进4 连板梯队标的）"""

    ALLOWED_YESTERDAY_BOARDS = (1, 2, 3)
    ALLOWED_TODAY_BOARDS = (2, 3, 4)

    def __init__(self, config: Optional[MainBoardFilterConfig] = None):
        self.config = config or MainBoardFilterConfig()

    @staticmethod
    def format_relay_label(yesterday_boards: int) -> str:
        """格式化接力梯队标签（如 1进2 / 2进3 / 3进4）"""
        if yesterday_boards in StockFilter.ALLOWED_YESTERDAY_BOARDS:
            return f"{yesterday_boards}进{yesterday_boards + 1}"
        return ""

    @staticmethod
    def format_yesterday_status(yesterday_boards: int) -> str:
        """格式化昨日连板状态描述"""
        if yesterday_boards == 1:
            return "昨日首板"
        if yesterday_boards >= 2:
            return f"昨日{yesterday_boards}连板"
        return "普通"

    @staticmethod
    def extract_yesterday_boards(quote: StockQuote) -> int:
        """提取标的昨日真实连板数（0 表示昨日未涨停，不进入 1进2/2进3/3进4 池）"""
        yb = int(getattr(quote, "yesterday_boards", 0) or 0)
        if yb > 0:
            return yb

        status = str(getattr(quote, "yesterday_status", "") or "").strip()
        if not status:
            return 0

        for pattern in (r'(\d+)\s*进\s*\d+', r'昨日?\s*(\d+)\s*连?板', r'(\d+)\s*连?板'):
            m = re.search(pattern, status)
            if m:
                return int(m.group(1))

        if "首板" in status and "非首板" not in status:
            return 1

        return 0

    def is_target_relay_quote(self, quote: StockQuote, today_boards: Optional[int] = None) -> bool:
        """严格校验是否为系统允许的 1进2、2进3、3进4 接力标的"""
        yb = self.extract_yesterday_boards(quote)
        if yb not in self.ALLOWED_YESTERDAY_BOARDS:
            return False

        if today_boards is not None and int(today_boards) > 0:
            tb = int(today_boards)
            if tb not in self.ALLOWED_TODAY_BOARDS:
                return False
            if getattr(quote, "is_limit_up", False) and tb != yb + 1:
                return False

        return True

    def is_main_board_code(self, code: str) -> bool:
        """
        判断是否为主板股票代码
        """
        code_str = str(code).strip()
        # 补全6位代码
        if len(code_str) < 6:
            code_str = code_str.zfill(6)
            
        # 排除非主板
        for excluded in self.config.EXCLUDED_PREFIXES:
            if code_str.startswith(excluded):
                return False
                
        # 确认主板前缀
        for allowed in self.config.ALLOWED_PREFIXES:
            if code_str.startswith(allowed):
                return True
                
        return False

    def is_valid_name(self, name: str) -> bool:
        """
        过滤 ST、*ST、退市、首日未有涨跌幅限制等异动股
        """
        if not name:
            return False
            
        clean_name = name.strip().upper()
        
        # 过滤 ST 系列、退市及 PT 警示股
        if self.config.FILTER_ST:
            if "ST" in clean_name or "*ST" in clean_name or "退" in clean_name or clean_name.startswith("PT"):
                return False
                
        # 过滤次新无涨跌幅或特殊标示
        if clean_name.startswith("N") or clean_name.startswith("C"):
            # 上市首日或前5日可能无10%限制
            return False
            
        return True

    def check_market_cap(self, float_market_cap: float) -> bool:
        """
        检查自由流通市值（亿元）是否在适宜短线连板区间
        """
        if float_market_cap <= 0:
            return True  # 若无市值数据暂时放行，由后续综合打分处理
            
        return (self.config.MIN_FLOAT_MARKET_CAP <= float_market_cap <= self.config.MAX_FLOAT_MARKET_CAP)

    def filter_quote(self, quote: StockQuote) -> bool:
        """
        对行情对象进行整体主板与风控初筛
        """
        # 1. 检查主板代码
        if not self.is_main_board_code(quote.code):
            return False
            
        # 2. 检查名称
        if not self.is_valid_name(quote.name):
            return False
            
        # 3. 检查流通市值范围
        if not self.check_market_cap(quote.float_market_cap):
            return False
            
        return True
