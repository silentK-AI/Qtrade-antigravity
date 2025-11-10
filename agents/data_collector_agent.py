"""
数据收集智能体
负责获取股票历史交易数据
"""
from crewai import Agent, LLM
from tools.stock_data_tool import get_stock_history_tool_obj
from config import GEMINI_MODEL, GEMINI_API_KEY


def create_data_collector_agent() -> Agent:
    """
    创建数据收集智能体
    
    Returns:
        配置好的数据收集智能体
    """
    llm = LLM(
        model=GEMINI_MODEL,
        temperature=0.1,
        api_key=GEMINI_API_KEY
    )
    
    agent = Agent(
        role="股票数据收集专家",
        goal="准确获取指定股票的历史交易数据，包括过去三年的每日开盘价、收盘价、最低价、最高价、量比、换手率等关键指标",
        backstory="""你是一位经验丰富的股票数据收集专家，擅长从各种数据源获取准确、完整的股票历史交易数据。
        你熟悉中国股市的数据格式和特点，能够高效地收集和整理股票交易数据。
        你的工作对于后续的分析和决策至关重要，因此你总是确保数据的准确性和完整性。""",
        verbose=True,
        allow_delegation=False,
        llm=llm,
        tools=[get_stock_history_tool_obj],
        max_iter=2,  # 降低迭代次数以减少 API 调用
        max_execution_time=300
    )
    
    return agent

