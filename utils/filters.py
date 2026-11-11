"""
主板标的过滤与风控初筛工具
严格执行：
1. 仅保留沪深主板（600/601/603/605/000/001/002/003）
2. 剔除创业板(300/301)、科创板(688)、北交所(8/4/9)
3. 剔除 ST、*ST、退市整理、上市初期新股 (N/C字头)
4. 过滤极小盘流动性陷阱与超大盘迟钝股
"""

from typing import Optional
from config import MainBoardFilterConfig
from models.stock_item import StockQuote


class StockFilter:
    """股票主板及风控过滤器"""

    def __init__(self, config: Optional[MainBoardFilterConfig] = None):
        self.config = config or MainBoardFilterConfig()

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
