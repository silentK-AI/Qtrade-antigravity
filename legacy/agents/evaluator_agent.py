"""
评估智能体
负责对分析决策结果进行评估并提供优化建议
"""
from crewai import Agent, LLM
from config import GEMINI_FLASH_MODEL, GEMINI_API_KEY


def create_evaluator_agent() -> Agent:
    """
    创建评估智能体
    
    Returns:
        配置好的评估智能体
    """
    llm = LLM(
        model=GEMINI_FLASH_MODEL,
        temperature=0.2,
        api_key=GEMINI_API_KEY
    )
    
    agent = Agent(
        role="交易策略评估专家",
        goal="客观评估分析决策智能体的预测结果，识别潜在的风险和问题，并提供具体的优化建议，帮助改进预测准确性",
        backstory="""你是一位严格的交易策略评估专家，拥有丰富的量化交易策略评估经验。
        你擅长从多个维度评估交易策略和预测结果，包括准确性、风险控制、逻辑合理性等。
        你能够识别预测中的潜在问题，如数据偏差、模型缺陷、市场环境变化等，
        并提供具体、可操作的优化建议。
        你的评估和建议对于提高整个系统的预测准确性和可靠性至关重要。""",
        verbose=True,
        allow_delegation=False,
        llm=llm,
        tools=[],  # 评估智能体主要使用LLM进行评估，不需要特定工具
        max_iter=2,  # 降低迭代次数以减少 API 调用
        max_execution_time=300
    )
    
    return agent

