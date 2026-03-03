"""
股票数据获取工具
使用akshare获取中国股市历史交易数据
"""
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging
from utils.date_utils import get_beijing_time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StockDataTool:
    """股票数据获取工具类"""
    
    def __init__(self):
        self.data_source = "akshare"
    
    def get_stock_history(
        self, 
        stock_code: str, 
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "daily"
    ) -> Dict[str, Any]:
        """
        获取股票历史交易数据
        
        Args:
            stock_code: 股票代码（如：000001）
            start_date: 开始日期，格式：YYYYMMDD
            end_date: 结束日期，格式：YYYYMMDD
            period: 数据周期，默认daily（日线）
        
        Returns:
            包含股票数据的字典
        """
        try:
            # 使用北京时间计算日期
            beijing_time = get_beijing_time()
            
            # 如果没有指定开始日期，默认获取过去三年的数据
            if start_date is None:
                three_years_ago = beijing_time - timedelta(days=3*365)
                start_date = three_years_ago.strftime("%Y%m%d")
            
            if end_date is None:
                end_date = beijing_time.strftime("%Y%m%d")
            
            logger.info(f"正在获取股票 {stock_code} 从 {start_date} 到 {end_date} 的数据...")
            
            # 使用akshare获取股票历史数据
            # 注意：akshare的接口可能需要调整股票代码格式
            stock_data = ak.stock_zh_a_hist(
                symbol=stock_code,
                period=period,
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="qfq"  # 前复权
            )
            
            if stock_data is None or stock_data.empty:
                return {
                    "success": False,
                    "error": f"无法获取股票 {stock_code} 的数据",
                    "data": None
                }
            
            # 重命名列名为中文
            column_mapping = {
                "日期": "日期",
                "开盘": "开盘价",
                "收盘": "收盘价",
                "最高": "最高价",
                "最低": "最低价",
                "成交量": "成交量",
                "成交额": "成交额",
                "振幅": "振幅",
                "涨跌幅": "涨跌幅",
                "涨跌额": "涨跌额",
                "换手率": "换手率"
            }
            
            # 重命名列
            for old_col, new_col in column_mapping.items():
                if old_col in stock_data.columns:
                    stock_data = stock_data.rename(columns={old_col: new_col})
            
            # 计算量比（需要前一日成交量）
            if "成交量" in stock_data.columns:
                stock_data["量比"] = stock_data["成交量"] / stock_data["成交量"].shift(1)
                stock_data["量比"] = stock_data["量比"].fillna(1.0)
            
            # 确保换手率存在
            if "换手率" not in stock_data.columns:
                stock_data["换手率"] = 0.0
            
            # 转换为字典格式
            data_dict = stock_data.to_dict(orient="records")
            
            # 计算统计信息
            stats = {
                "总交易日数": len(data_dict),
                "平均收盘价": float(stock_data["收盘价"].mean()) if "收盘价" in stock_data.columns else 0,
                "最高收盘价": float(stock_data["收盘价"].max()) if "收盘价" in stock_data.columns else 0,
                "最低收盘价": float(stock_data["收盘价"].min()) if "收盘价" in stock_data.columns else 0,
                "平均成交量": float(stock_data["成交量"].mean()) if "成交量" in stock_data.columns else 0,
                "平均换手率": float(stock_data["换手率"].mean()) if "换手率" in stock_data.columns else 0,
            }
            
            return {
                "success": True,
                "stock_code": stock_code,
                "start_date": start_date,
                "end_date": end_date,
                "data": data_dict,
                "statistics": stats,
                "dataframe": stock_data
            }
            
        except Exception as e:
            logger.error(f"获取股票数据时出错: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "data": None
            }
    
    def get_stock_basic_info(self, stock_code: str) -> Dict[str, Any]:
        """
        获取股票基本信息
        
        Args:
            stock_code: 股票代码
        
        Returns:
            股票基本信息字典
        """
        try:
            # 获取股票基本信息
            stock_info = ak.stock_individual_info_em(symbol=stock_code)
            
            if stock_info is None or stock_info.empty:
                return {
                    "success": False,
                    "error": f"无法获取股票 {stock_code} 的基本信息",
                    "data": None
                }
            
            info_dict = {}
            for _, row in stock_info.iterrows():
                info_dict[row.iloc[0]] = row.iloc[1]
            
            return {
                "success": True,
                "stock_code": stock_code,
                "data": info_dict
            }
            
        except Exception as e:
            logger.error(f"获取股票基本信息时出错: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "data": None
            }


def get_stock_history_tool_func(stock_code: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
    """
    CrewAI工具函数：获取股票历史数据
    
    Args:
        stock_code: 股票代码
        start_date: 开始日期
        end_date: 结束日期
    
    Returns:
        格式化的字符串结果
    """
    tool = StockDataTool()
    
    # 先获取股票基本信息（包括股票名称）
    stock_info = tool.get_stock_basic_info(stock_code)
    stock_name = "未知"
    if stock_info["success"] and stock_info["data"]:
        # 尝试从基本信息中获取股票名称
        info_data = stock_info["data"]
        # akshare返回的格式是 {"项目": "内容"}，例如 {"股票简称": "三花智控"}
        # 优先查找"股票简称"
        if "股票简称" in info_data:
            stock_name = str(info_data["股票简称"]).strip()
        # 其次查找包含"名称"或"简称"的键
        elif stock_name == "未知":
            for key, value in info_data.items():
                key_str = str(key).strip()
                if "简称" in key_str or ("名称" in key_str and "全称" not in key_str):
                    stock_name = str(value).strip()
                    break
        # 如果还是没找到，尝试查找任何包含"name"的键（英文）
        if stock_name == "未知":
            for key, value in info_data.items():
                if "name" in str(key).lower():
                    stock_name = str(value).strip()
                    break
    
    result = tool.get_stock_history(stock_code, start_date, end_date)
    
    if result["success"]:
        stats = result["statistics"]
        latest_date_str = ""
        try:
            if "日期" in result["dataframe"].columns:
                latest_date_str = str(result["dataframe"]["日期"].iloc[-1])
        except Exception:
            latest_date_str = ""
        return f"""
股票代码: {result['stock_code']}
股票名称: {stock_name}
数据期间: {result['start_date']} 至 {result['end_date']}
RANGE_CHECK: {result['start_date']}~{result['end_date']}
LATEST_DATE: {latest_date_str}
总交易日数: {stats['总交易日数']}
平均收盘价: {stats['平均收盘价']:.2f}
最高收盘价: {stats['最高收盘价']:.2f}
最低收盘价: {stats['最低收盘价']:.2f}
平均成交量: {stats['平均成交量']:.0f}
平均换手率: {stats['平均换手率']:.2f}%

最近5个交易日数据:
{result['dataframe'].tail(5).to_string()}
"""
    else:
        return f"获取股票数据失败: {result['error']}"


# CrewAI工具函数
def get_stock_history_tool(stock_code: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> str:
    """
    获取股票历史交易数据
    
    Args:
        stock_code: 股票代码（如：000001）
        start_date: 开始日期，格式：YYYYMMDD（可选）
        end_date: 结束日期，格式：YYYYMMDD（可选）
    
    Returns:
        格式化的股票数据报告
    """
    return get_stock_history_tool_func(stock_code, start_date, end_date)


# 使用CrewAI的tool装饰器
from crewai.tools import tool

@tool("获取股票历史数据")
def get_stock_history_tool_obj(
    stock_code: str, 
    start_date: str = "", 
    end_date: str = ""
) -> str:
    """
    获取股票历史交易数据，包括股票名称、过去三年的每日开盘价、收盘价、最低价、最高价、量比、换手率等指标。
    此工具会自动获取股票的基本信息（包括股票名称），然后获取历史交易数据。
    
    Args:
        stock_code: 股票代码（如：000001），必需参数
        start_date: 开始日期，格式：YYYYMMDD（可选，留空则默认三年前）
        end_date: 结束日期，格式：YYYYMMDD（可选，留空则默认今天）
    
    Returns:
        格式化的股票数据报告，包含股票代码、股票名称、数据期间、统计信息和最近5个交易日数据
    """
    # 将空字符串转换为None
    start_date = None if not start_date or start_date.strip() == "" else start_date
    end_date = None if not end_date or end_date.strip() == "" else end_date
    return get_stock_history_tool(stock_code, start_date, end_date)

