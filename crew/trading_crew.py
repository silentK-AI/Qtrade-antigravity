"""
量化交易Crew配置
协调四个智能体完成股票价格预测任务
"""
from crewai import Crew, Process
from tasks.task_definitions import (
    create_data_collection_task,
    create_news_collection_task,
    create_analysis_task,
    create_evaluation_task
)


def create_trading_crew(stock_code: str, start_date: str = None, end_date: str = None) -> Crew:
    """
    创建量化交易Crew
    
    Args:
        stock_code: 股票代码
        start_date: 开始日期（可选）
        end_date: 结束日期（可选）
    
    Returns:
        配置好的Crew实例
    """
    # 创建任务
    data_task = create_data_collection_task(stock_code, start_date, end_date)
    news_task = create_news_collection_task(stock_code)
    
    # 分析任务依赖于数据收集和资讯收集任务
    analysis_task = create_analysis_task(stock_code)
    analysis_task.context = [data_task, news_task]
    
    # 评估任务依赖于分析任务
    evaluation_task = create_evaluation_task(stock_code)
    evaluation_task.context = [analysis_task]
    
    # 创建Crew
    crew = Crew(
        agents=[
            data_task.agent,
            news_task.agent,
            analysis_task.agent,
            evaluation_task.agent
        ],
        tasks=[
            data_task,
            news_task,
            analysis_task,
            evaluation_task
        ],
        process=Process.sequential,  # 使用顺序执行，但通过context控制依赖
        verbose=True,
        memory=False,  # 禁用记忆功能（避免需要额外的 API 密钥）
        max_iter=10,  # 最大迭代次数（降低以减少 API 调用）
        max_rpm=5  # 每分钟最大请求数（降低以避免 429 错误）
    )
    
    return crew


def run_trading_analysis(stock_code: str, start_date: str = None, end_date: str = None) -> dict:
    """
    运行量化交易分析
    当遇到 429 错误时，自动切换到备用模型 gemini-2.0-flash-live
    
    Args:
        stock_code: 股票代码
        start_date: 开始日期（可选）
        end_date: 结束日期（可选）
    
    Returns:
        分析结果字典
    """
    import time
    import config
    from config import GEMINI_FALLBACK_MODEL
    from agents.data_collector_agent import create_data_collector_agent
    from agents.news_collector_agent import create_news_collector_agent
    from agents.analysis_agent import create_analysis_agent
    from agents.evaluator_agent import create_evaluator_agent
    
    max_retries = 2
    
    for attempt in range(max_retries):
        try:
            if attempt == 0:
                # 第一次尝试使用主模型
                crew = create_trading_crew(stock_code, start_date, end_date)
            else:
                # 第二次尝试使用备用模型
                print(f"\n⚠️  检测到 429 错误，切换到备用模型: {GEMINI_FALLBACK_MODEL}")
                print("正在重新创建智能体...")
                
                # 临时切换到备用模型
                original_model = config.GEMINI_MODEL
                config.GEMINI_MODEL = GEMINI_FALLBACK_MODEL
                
                # 重新创建所有智能体和任务
                from tasks.task_definitions import (
                    create_data_collection_task,
                    create_news_collection_task,
                    create_analysis_task,
                    create_evaluation_task
                )
                
                data_task = create_data_collection_task(stock_code, start_date, end_date)
                news_task = create_news_collection_task(stock_code)
                analysis_task = create_analysis_task(stock_code)
                analysis_task.context = [data_task, news_task]
                evaluation_task = create_evaluation_task(stock_code)
                evaluation_task.context = [analysis_task]
                
                crew = Crew(
                    agents=[
                        data_task.agent,
                        news_task.agent,
                        analysis_task.agent,
                        evaluation_task.agent
                    ],
                    tasks=[
                        data_task,
                        news_task,
                        analysis_task,
                        evaluation_task
                    ],
                    process=Process.sequential,
                    verbose=True,
                    memory=False,
                    max_iter=10,
                    max_rpm=5
                )
                
                # 恢复原始模型配置
                config.GEMINI_MODEL = original_model
            
            # 运行Crew
            result = crew.kickoff()
            
            # 整理结果
            output = {
                "stock_code": stock_code,
                "start_date": start_date,
                "end_date": end_date,
                "result": result,
                "tasks_output": {},
                "model_used": GEMINI_FALLBACK_MODEL if attempt > 0 else config.GEMINI_MODEL
            }
            
            # 提取各任务输出
            for task in crew.tasks:
                if hasattr(task, 'output'):
                    output["tasks_output"][task.description[:50]] = task.output
            
            return output
            
        except Exception as e:
            error_str = str(e)
            # 检查是否是 429 错误
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "Resource exhausted" in error_str:
                if attempt < max_retries - 1:
                    print(f"\n⚠️  遇到 429 错误（API 速率限制），等待 5 秒后切换到备用模型...")
                    time.sleep(5)
                    continue
                else:
                    raise Exception(f"主模型和备用模型都遇到 429 错误: {error_str}")
            else:
                # 其他错误直接抛出
                raise

