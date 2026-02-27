"""
日期工具函数
处理预测日期的逻辑
"""
from datetime import datetime, timedelta
from typing import Tuple
import pytz


def get_beijing_time() -> datetime:
    """
    获取当前北京时间
    
    Returns:
        当前北京时间的datetime对象
    """
    beijing_tz = pytz.timezone('Asia/Shanghai')
    return datetime.now(beijing_tz)


def get_prediction_date() -> Tuple[datetime, str]:
    """
    根据当前北京时间判断预测日期
    - 如果当前是北京时间上午9点之前，预测当天的
    - 如果是9点之后，预测第二天的走势
    
    Returns:
        (预测日期的datetime对象, 日期描述字符串)
    """
    beijing_time = get_beijing_time()
    current_hour = beijing_time.hour
    
    if current_hour < 9:
        # 9点之前，预测当天
        prediction_date = beijing_time.date()
        date_desc = f"{prediction_date.strftime('%Y年%m月%d日')}（当天）"
    else:
        # 9点之后，预测第二天
        prediction_date = (beijing_time + timedelta(days=1)).date()
        date_desc = f"{prediction_date.strftime('%Y年%m月%d日')}（第二天）"
    
    return datetime.combine(prediction_date, datetime.min.time()), date_desc


def format_prediction_date_desc() -> str:
    """
    格式化预测日期描述，用于任务描述中
    
    Returns:
        日期描述字符串，如"2025年11月12日（当天）"或"2025年11月13日（第二天）"
    """
    _, date_desc = get_prediction_date()
    return date_desc


def format_current_beijing_date() -> str:
    """
    返回当前北京时间的日期字符串，格式：YYYY年MM月DD日
    用于报告中的“评估日期”等强制性日期字段
    """
    bj = get_beijing_time()
    return bj.strftime("%Y年%m月%d日")
