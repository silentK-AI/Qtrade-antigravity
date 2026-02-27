"""
任务定义
定义各个智能体的任务
"""
from crewai import Task
from agents.data_collector_agent import create_data_collector_agent
from agents.news_collector_agent import create_news_collector_agent
from agents.analysis_agent import create_analysis_agent
from agents.evaluator_agent import create_evaluator_agent


def create_data_collection_task(stock_code: str, start_date: str = None, end_date: str = None) -> Task:
    """
    创建数据收集任务
    
    Args:
        stock_code: 股票代码
        start_date: 开始日期
        end_date: 结束日期
    
    Returns:
        数据收集任务
    """
    agent = create_data_collector_agent()
    
    task = Task(
        description=f"""
        请获取股票代码为 {stock_code} 的历史交易数据。
        
        要求：
        1. 首先使用工具获取股票数据，工具会自动获取股票名称和历史交易数据
        2. 在报告中明确说明股票代码和股票名称（例如：002050 三花智控），确保股票名称准确无误
        3. 获取从当前北京时间倒序过去三年的每日交易数据，数据时间范围应该是最新的，使用北京时间计算
           - 严格要求：报告中必须原样包含工具返回的校验行：
             - 形如：RANGE_CHECK: <开始>~<结束>
             - 形如：LATEST_DATE: <最后交易日>
           - 禁止编造或改写日期格式，必须与工具输出一致
        4. 必须包含以下关键指标：
           - 股票代码和股票名称
           - 日期
           - 开盘价
           - 收盘价
           - 最高价
           - 最低价
           - 成交量
           - 成交额
           - 量比
           - 换手率
           - 涨跌幅
           - 振幅
        
        5. 如果指定了开始日期({start_date})和结束日期({end_date})，请使用指定的日期范围
        
        6. 整理并格式化数据，确保数据完整且易于后续分析使用
        
        7. 提供数据的统计摘要，包括：
           - 股票代码和股票名称
           - 数据期间（明确显示开始日期和结束日期）
           - 总交易日数
           - 平均收盘价
           - 最高收盘价
           - 最低收盘价
           - 平均成交量
           - 平均换手率
        """,
        agent=agent,
        expected_output="""
        格式化的股票历史数据报告，包括：
        1. 数据获取状态（成功/失败）
        2. 数据统计摘要
        3. 最近5个交易日的详细数据
        4. 数据质量说明
        """
    )
    
    return task


def create_news_collection_task(stock_code: str) -> Task:
    """
    创建资讯收集任务
    
    Args:
        stock_code: 股票代码
    
    Returns:
        资讯收集任务
    """
    agent = create_news_collector_agent()
    
    task = Task(
        description=f"""
        请搜索并整理股票代码为 {stock_code} 的最新相关资讯。
        
        要求：
        1. 搜索以下各类资讯：
           - 公司公告：最新的公司公告、业绩预告、重大事项等
           - 券商研报：各大券商对该股票的最新研报和评级
           - 大宗商品价格：相关大宗商品（如原油、黄金、铜等）的最新价格
           - 美联储议息决议：最新的美联储利率决议和政策变化
           - 美国关税政策：最新的美国关税政策变化，特别是影响该股票所在行业的政策
        
        2. 对每条资讯进行分类和重要性评估
        
        3. 整理资讯的关键信息，包括：
           - 资讯来源
           - 发布时间
           - 核心内容摘要
           - 对股票价格的潜在影响
        
        4. 按重要性排序，优先展示对股票价格影响较大的资讯
        """,
        agent=agent,
        expected_output="""
        格式化的资讯收集报告，包括：
        1. 各类资讯的搜索结果汇总
        2. 重要资讯的详细内容
        3. 资讯对股票价格的潜在影响分析
        4. 资讯来源和时间信息
        """
    )
    
    return task


def create_analysis_task(stock_code: str, prediction_date_desc: str = None) -> Task:
    """
    创建分析决策任务
    
    Args:
        stock_code: 股票代码
        prediction_date_desc: 预测日期描述（如"2025年11月12日（当天）"）
    
    Returns:
        分析决策任务
    """
    from utils.date_utils import format_prediction_date_desc
    
    # 如果没有提供日期描述，自动获取
    if prediction_date_desc is None:
        prediction_date_desc = format_prediction_date_desc()
    
    agent = create_analysis_agent()
    
    task = Task(
        description=f"""
        请基于收集到的历史交易数据和最新资讯，对股票代码为 {stock_code} 的{prediction_date_desc}价格进行预测。
        请注意：报告中所有出现的“当日/今日/今天”等日期概念，均指代：{prediction_date_desc}。严禁引用其他历史日期作为“当日”。
        
        要求：
        1. 综合分析以下数据：
           - 历史价格走势（过去三年的每日开盘价、收盘价、最高价、最低价）
           - 成交量、量比、换手率等技术指标
           - 公司公告、券商研报等基本面信息
           - 宏观经济政策（美联储议息决议、美国关税政策等）
           - 大宗商品价格等外部因素
        
        2. 运用专业的量化分析方法：
           - 技术分析：趋势分析、支撑位/阻力位、技术指标（如MA、MACD、RSI等）
           - 量价关系分析：成交量与价格的关系
           - 基本面分析：结合公司公告和研报信息
           - 市场环境分析：考虑宏观经济和政策因素
        
        3. 预测{prediction_date_desc}的最高价和最低价：
           - 提供最高价预测值
           - 提供最低价预测值
           - 说明预测依据和逻辑
           - 评估预测的置信度
        
        4. 识别潜在的风险因素和不确定性
        """,
        agent=agent,
        expected_output=f"""
        格式化的价格预测报告，包括：
        1. {prediction_date_desc}最高价预测值
        2. {prediction_date_desc}最低价预测值
        3. 预测依据和逻辑说明
        4. 使用的分析方法和技术指标
        5. 预测置信度评估
        6. 风险因素和不确定性说明
        """,
        context=[]  # 上下文将在运行时动态添加
    )
    
    return task


def create_evaluation_task(stock_code: str, report_date: str = None) -> Task:
    """
    创建评估任务
    
    Args:
        stock_code: 股票代码
        report_date: 报告日期（当前北京时间，格式：YYYY年MM月DD日）
    
    Returns:
        评估任务
    """
    from utils.date_utils import format_current_beijing_date
    if report_date is None:
        report_date = format_current_beijing_date()
    agent = create_evaluator_agent()
    
    task = Task(
        description=f"""
        请对股票代码为 {stock_code} 的价格预测结果进行全面评估。
        请注意：本评估报告的“评估日期”必须严格使用当前北京时间：{report_date}。严禁使用历史日期或虚构日期。
        
        要求：
        1. 评估预测结果的合理性：
           - 预测的最高价和最低价是否在合理范围内
           - 预测逻辑是否清晰和可靠
           - 使用的分析方法是否恰当
        
        2. 识别潜在问题：
           - 数据质量问题（如数据缺失、异常值等）
           - 分析方法问题（如模型选择不当、参数设置不合理等）
           - 市场环境变化（如突发新闻、政策变化等）
           - 预测假设是否合理
        
        3. 评估风险：
           - 预测的不确定性
           - 可能影响预测准确性的风险因素
           - 市场波动风险
        
        4. 提供优化建议：
           - 改进数据收集的建议
           - 优化分析方法的建议
           - 提高预测准确性的具体措施
           - 风险控制建议
        """,
        agent=agent,
        expected_output=f"""
        格式化的评估报告，包括：
        1. 报告头部需包含：股票代码与名称（若有）、评估日期（必须为：{report_date}）
        2. 预测结果评估（合理性、可靠性等）
        2. 识别的问题和风险
        3. 具体的优化建议
        4. 改进措施和行动计划
        """,
        context=[]  # 上下文将在运行时动态添加
    )
    
    return task


