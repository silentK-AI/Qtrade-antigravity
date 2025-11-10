"""
资讯收集智能体
负责搜索并整理股票相关的最新资讯
"""
from crewai import Agent, LLM
from tools.news_search_tool import search_stock_news_tool_obj
from config import GEMINI_MODEL, GEMINI_API_KEY


def create_news_collector_agent() -> Agent:
    """
    创建资讯收集智能体
    
    Returns:
        配置好的资讯收集智能体
    """
    llm = LLM(
        model=GEMINI_MODEL,
        temperature=0.2,
        api_key=GEMINI_API_KEY
    )
    
    agent = Agent(
        role="股票资讯收集专家",
        goal="全面搜索并整理指定股票的最新相关资讯，包括公司公告、券商研报、大宗商品价格、美联储议息决议、美国关税政策等对股票价格有影响的信息",
        backstory="""你是一位专业的股票资讯收集专家，擅长从多个渠道收集和整理与股票相关的各类资讯。
        你了解哪些信息会对股票价格产生影响，能够识别重要资讯并准确分类整理。
        你熟悉公司公告、券商研报、宏观经济政策等多种信息源，能够高效地收集和整理这些信息。
        你的工作为后续的分析决策提供了重要的信息基础。""",
        verbose=True,
        allow_delegation=False,
        llm=llm,
        tools=[search_stock_news_tool_obj],
        max_iter=2,  # 降低迭代次数以减少 API 调用
        max_execution_time=300
    )
    
    return agent

