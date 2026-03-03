"""
分析决策智能体
负责利用收集的数据和资讯进行股票价格预测
"""
from crewai import Agent, LLM
from config import GEMINI_ANALYSIS_MODEL, GEMINI_API_KEY


def create_analysis_agent() -> Agent:
    """
    创建分析决策智能体
    
    Returns:
        配置好的分析决策智能体
    """
    llm = LLM(
        model=GEMINI_ANALYSIS_MODEL,
        temperature=0.3,
        api_key=GEMINI_API_KEY
    )
    
    agent = Agent(
        role="股票价格分析专家",
        goal="基于历史交易数据和最新资讯，运用专业的量化分析方法LSTM模型，准确预测股票目标日期的最高价和最低价",
        backstory="""你是一位资深的股票价格分析专家，拥有丰富的量化交易经验。
        你精通各种技术分析方法，包括趋势分析、技术指标分析、量价关系分析等。
        你能够综合考虑历史价格走势、成交量、换手率等技术指标，以及公司公告、研报、宏观经济政策等基本面信息，
        运用专业的分析模型和算法，对股票价格进行科学预测。
        你的预测结果直接影响交易决策，因此你总是力求准确和可靠。""",
        verbose=True,
        allow_delegation=False,
        llm=llm,
        tools=[],  # 分析智能体主要使用LLM进行分析，不需要特定工具
        max_iter=3,  # 降低迭代次数以减少 API 调用
        max_execution_time=600
    )
    
    return agent

