"""
资讯搜索工具
搜索股票相关的各类资讯信息
"""
import requests
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NewsSearchTool:
    """资讯搜索工具类"""
    
    def __init__(self):
        self.sources = [
            "公司公告",
            "券商研报",
            "大宗商品价格",
            "美联储议息决议",
            "美国关税政策"
        ]
    
    def search_company_announcements(self, stock_code: str, limit: int = 10) -> Dict[str, Any]:
        """
        搜索公司公告
        
        Args:
            stock_code: 股票代码
            limit: 返回结果数量限制
        
        Returns:
            公告信息字典
        """
        try:
            # 这里可以使用实际的API或爬虫来获取公司公告
            import akshare as ak
            
            announcements = []
            
            # 尝试获取公告数据
            try:
                # 过滤掉 ETF (15, 51, 58 开头)，它们没有个股公告
                if stock_code.startswith(("15", "51", "58")):
                    raise ValueError("ETF 无个股公告")
                    
                stock_news = ak.stock_notice_report(symbol=stock_code)
                if stock_news is not None and not stock_news.empty:
                    announcements = stock_news.head(limit).to_dict(orient="records")
            except Exception as e:
                # 压制无公告导致的特殊报错
                if "infoCode" not in str(e) and "ETF" not in str(e):
                    logger.debug(f"无法通过akshare获取公告[{stock_code}]: {str(e)}")
            
            return {
                "success": True,
                "stock_code": stock_code,
                "source": "公司公告",
                "count": len(announcements),
                "data": announcements
            }
            
        except Exception as e:
            logger.error(f"搜索公司公告时出错: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "data": []
            }
    
    def search_research_reports(self, stock_code: str, limit: int = 10) -> Dict[str, Any]:
        """
        搜索券商研报
        
        Args:
            stock_code: 股票代码
            limit: 返回结果数量限制
        
        Returns:
            研报信息字典
        """
        try:
            import akshare as ak
            reports = []
            
            # 尝试获取研报数据
            try:
                if stock_code.startswith(("15", "51", "58")):
                    raise ValueError("ETF 无个股研报")
                    
                stock_reports = ak.stock_research_report_em(symbol=stock_code)
                if stock_reports is not None and not stock_reports.empty:
                    reports = stock_reports.head(limit).to_dict(orient="records")
            except Exception as e:
                if "infoCode" not in str(e) and "ETF" not in str(e):
                    logger.debug(f"无法通过akshare获取研报[{stock_code}]: {str(e)}")
            
            return {
                "success": True,
                "stock_code": stock_code,
                "source": "券商研报",
                "count": len(reports),
                "data": reports
            }
            
        except Exception as e:
            logger.error(f"搜索券商研报时出错: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "data": []
            }
    
    def get_commodity_prices(self, commodity_type: str = "原油") -> Dict[str, Any]:
        """
        获取大宗商品价格
        
        Args:
            commodity_type: 商品类型（原油、黄金、铜等）
        
        Returns:
            商品价格信息
        """
        try:
            import akshare as ak
            
            prices = {}
            
            # 根据商品类型获取价格
            if commodity_type == "原油":
                try:
                    oil_data = ak.futures_zh_spot(symbol="SC0", exchange="上海国际能源交易中心")
                    if oil_data is not None and not oil_data.empty:
                        prices = oil_data.to_dict(orient="records")
                except:
                    pass
            
            return {
                "success": True,
                "commodity_type": commodity_type,
                "source": "大宗商品价格",
                "data": prices
            }
            
        except Exception as e:
            logger.error(f"获取大宗商品价格时出错: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "data": {}
            }
    
    def get_fed_interest_rate_decision(self) -> Dict[str, Any]:
        """
        获取美联储议息决议信息
        
        Returns:
            美联储议息决议信息
        """
        try:
            # 这里可以集成实际的API或数据源
            # 示例返回结构
            return {
                "success": True,
                "source": "美联储议息决议",
                "data": {
                    "latest_decision": "待获取",
                    "interest_rate": "待获取",
                    "decision_date": "待获取",
                    "next_meeting": "待获取"
                },
                "note": "需要集成实际的数据源API"
            }
            
        except Exception as e:
            logger.error(f"获取美联储议息决议时出错: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "data": {}
            }
    
    def get_us_tariff_policy(self) -> Dict[str, Any]:
        """
        获取美国关税政策信息
        
        Returns:
            美国关税政策信息
        """
        try:
            # 这里可以集成实际的API或数据源
            # 示例返回结构
            return {
                "success": True,
                "source": "美国关税政策",
                "data": {
                    "latest_policy": "待获取",
                    "effective_date": "待获取",
                    "affected_industries": "待获取"
                },
                "note": "需要集成实际的数据源API"
            }
            
        except Exception as e:
            logger.error(f"获取美国关税政策时出错: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "data": {}
            }
    
    def search_all_news(self, stock_code: str) -> Dict[str, Any]:
        """
        搜索所有相关资讯
        
        Args:
            stock_code: 股票代码
        
        Returns:
            所有资讯信息
        """
        results = {
            "stock_code": stock_code,
            "search_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sources": {}
        }
        
        # 搜索公司公告
        results["sources"]["公司公告"] = self.search_company_announcements(stock_code)
        
        # 搜索券商研报
        results["sources"]["券商研报"] = self.search_research_reports(stock_code)
        
        # 获取大宗商品价格
        results["sources"]["大宗商品价格"] = self.get_commodity_prices()
        
        # 获取美联储议息决议
        results["sources"]["美联储议息决议"] = self.get_fed_interest_rate_decision()
        
        # 获取美国关税政策
        results["sources"]["美国关税政策"] = self.get_us_tariff_policy()
        
        return results


def search_stock_news_tool_func(stock_code: str) -> str:
    """
    CrewAI工具函数：搜索股票相关资讯
    
    Args:
        stock_code: 股票代码
    
    Returns:
        格式化的字符串结果
    """
    tool = NewsSearchTool()
    results = tool.search_all_news(stock_code)
    
    output = f"股票代码: {stock_code}\n"
    output += f"搜索时间: {results['search_time']}\n\n"
    
    for source_name, source_data in results["sources"].items():
        output += f"=== {source_name} ===\n"
        if source_data.get("success"):
            if isinstance(source_data.get("data"), list):
                output += f"找到 {len(source_data['data'])} 条记录\n"
                for i, item in enumerate(source_data["data"][:3], 1):  # 只显示前3条
                    output += f"{i}. {str(item)[:100]}...\n"
            elif isinstance(source_data.get("data"), dict):
                output += f"{json.dumps(source_data['data'], ensure_ascii=False, indent=2)}\n"
        else:
            output += f"获取失败: {source_data.get('error', '未知错误')}\n"
        output += "\n"
    
    return output


# CrewAI工具函数
def search_stock_news_tool(stock_code: str) -> str:
    """
    搜索股票相关的最新资讯，包括公司公告、券商研报、大宗商品价格、美联储议息决议、美国关税政策等
    
    Args:
        stock_code: 股票代码（如：000001）
    
    Returns:
        格式化的资讯收集报告
    """
    return search_stock_news_tool_func(stock_code)


# 使用CrewAI的tool装饰器（可选）
try:
    from crewai.tools import tool

    @tool("搜索股票相关资讯")
    def search_stock_news_tool_obj(stock_code: str) -> str:
        """
        搜索股票相关的最新资讯，包括公司公告、券商研报、大宗商品价格、美联储议息决议、美国关税政策等
        
        Args:
            stock_code: 股票代码（如：000001）
        
        Returns:
            格式化的资讯收集报告
        """
        return search_stock_news_tool(stock_code)
except ImportError:
    # 如果没装 crewai，则不注册该 tool 装饰器
    pass

