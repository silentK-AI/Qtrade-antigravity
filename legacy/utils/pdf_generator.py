"""
PDF报告生成工具
将各智能体的分析结果生成PDF报告
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import datetime
import os


def register_chinese_font():
    """注册中文字体"""
    # 尝试使用系统字体
    font_paths = [
        "/System/Library/Fonts/PingFang.ttc",  # macOS
        "/System/Library/Fonts/STHeiti Light.ttc",  # macOS
        "C:/Windows/Fonts/simhei.ttf",  # Windows
        "C:/Windows/Fonts/simsun.ttc",  # Windows
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
    ]
    
    chinese_font = None
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                # 对于.ttc文件，需要指定字体索引
                if font_path.endswith('.ttc'):
                    # PingFang.ttc 索引0是Regular
                    pdfmetrics.registerFont(TTFont('ChineseFont', font_path, subfontIndex=0))
                else:
                    pdfmetrics.registerFont(TTFont('ChineseFont', font_path))
                chinese_font = 'ChineseFont'
                break
            except:
                continue
    
    # 如果找不到中文字体，使用默认字体（可能不支持中文）
    if chinese_font is None:
        # 使用DejaVu Sans作为后备
        try:
            pdfmetrics.registerFont(TTFont('ChineseFont', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
            chinese_font = 'ChineseFont'
        except:
            chinese_font = 'Helvetica'  # 后备字体
    
    return chinese_font


def create_pdf_report(result: dict, output_path: str):
    """
    创建PDF报告
    
    Args:
        result: 分析结果字典，包含：
            - stock_code: 股票代码
            - start_date: 开始日期
            - end_date: 结束日期
            - result: 最终结果
            - tasks_output: 各任务输出字典
            - model_used: 使用的模型
        output_path: 输出PDF文件路径
    """
    # 注册中文字体
    chinese_font = register_chinese_font()
    
    # 创建PDF文档
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    # 获取样式
    styles = getSampleStyleSheet()
    
    # 创建自定义样式
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName=chinese_font,
        fontSize=20,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=1  # 居中
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontName=chinese_font,
        fontSize=16,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=12,
        spaceBefore=20
    )
    
    subheading_style = ParagraphStyle(
        'CustomSubHeading',
        parent=styles['Heading3'],
        fontName=chinese_font,
        fontSize=14,
        textColor=colors.HexColor('#34495e'),
        spaceAfter=10,
        spaceBefore=15
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName=chinese_font,
        fontSize=11,
        textColor=colors.HexColor('#333333'),
        leading=16,
        spaceAfter=8
    )
    
    # 构建PDF内容
    story = []
    
    # 标题页
    story.append(Paragraph("量化交易分析报告", title_style))
    story.append(Spacer(1, 1*cm))
    
    # 基本信息
    info_data = [
        ['股票代码', result.get('stock_code', 'N/A')],
        ['开始日期', result.get('start_date', '默认（三年前）')],
        ['结束日期', result.get('end_date', '默认（今天）')],
        ['生成时间', datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
        ['使用模型', result.get('model_used', 'N/A')]
    ]
    
    info_table = Table(info_data, colWidths=[4*cm, 10*cm])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ecf0f1')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2c3e50')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), chinese_font),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
    ]))
    story.append(info_table)
    story.append(PageBreak())
    
    # 各智能体分析结果
    tasks_output = result.get('tasks_output', {})
    
    # 1. 数据收集智能体结果
    story.append(Paragraph("一、数据收集智能体分析结果", heading_style))
    data_task_key = None
    for key in tasks_output.keys():
        if '数据' in key or '历史交易' in key or 'data' in key.lower():
            data_task_key = key
            break
    
    if data_task_key:
        data_output = str(tasks_output[data_task_key])
        # 处理长文本，分段显示
        paragraphs = _split_text(data_output, max_length=500)
        for para in paragraphs:
            story.append(Paragraph(para, normal_style))
    else:
        story.append(Paragraph("未找到数据收集结果", normal_style))
    
    story.append(Spacer(1, 0.5*cm))
    story.append(PageBreak())
    
    # 2. 资讯收集智能体结果
    story.append(Paragraph("二、资讯收集智能体分析结果", heading_style))
    news_task_key = None
    for key in tasks_output.keys():
        if '资讯' in key or '新闻' in key or 'news' in key.lower():
            news_task_key = key
            break
    
    if news_task_key:
        news_output = str(tasks_output[news_task_key])
        paragraphs = _split_text(news_output, max_length=500)
        for para in paragraphs:
            story.append(Paragraph(para, normal_style))
    else:
        story.append(Paragraph("未找到资讯收集结果", normal_style))
    
    story.append(Spacer(1, 0.5*cm))
    story.append(PageBreak())
    
    # 3. 分析决策智能体结果
    story.append(Paragraph("三、分析决策智能体分析结果", heading_style))
    analysis_task_key = None
    for key in tasks_output.keys():
        if '分析' in key or '预测' in key or 'analysis' in key.lower():
            analysis_task_key = key
            break
    
    if analysis_task_key:
        analysis_output = str(tasks_output[analysis_task_key])
        paragraphs = _split_text(analysis_output, max_length=500)
        for para in paragraphs:
            story.append(Paragraph(para, normal_style))
    else:
        story.append(Paragraph("未找到分析决策结果", normal_style))
    
    story.append(Spacer(1, 0.5*cm))
    story.append(PageBreak())
    
    # 4. 评估智能体结果
    story.append(Paragraph("四、评估智能体分析结果", heading_style))
    evaluator_task_key = None
    for key in tasks_output.keys():
        if '评估' in key or 'evaluat' in key.lower():
            evaluator_task_key = key
            break
    
    if evaluator_task_key:
        evaluator_output = str(tasks_output[evaluator_task_key])
        paragraphs = _split_text(evaluator_output, max_length=500)
        for para in paragraphs:
            story.append(Paragraph(para, normal_style))
    else:
        story.append(Paragraph("未找到评估结果", normal_style))
    
    story.append(Spacer(1, 0.5*cm))
    story.append(PageBreak())
    
    # 5. 最终结果总结
    story.append(Paragraph("五、最终分析结果总结", heading_style))
    final_result = result.get('result', '')
    if final_result:
        if isinstance(final_result, str):
            paragraphs = _split_text(str(final_result), max_length=500)
            for para in paragraphs:
                story.append(Paragraph(para, normal_style))
        else:
            story.append(Paragraph(str(final_result), normal_style))
    else:
        story.append(Paragraph("无最终结果", normal_style))
    
    story.append(Spacer(1, 0.5*cm))
    
    # 生成PDF
    doc.build(story)
    return output_path


def _escape_html(text: str) -> str:
    """转义HTML特殊字符"""
    if not text:
        return ""
    text = str(text)
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    return text


def _split_text(text: str, max_length: int = 500) -> list:
    """
    将长文本分割成多个段落
    
    Args:
        text: 要分割的文本
        max_length: 每段最大长度
    
    Returns:
        段落列表
    """
    if not text:
        return []
    
    # 转义HTML特殊字符
    text = _escape_html(str(text))
    
    # 按换行符分割
    lines = text.split('\n')
    paragraphs = []
    current_para = ""
    
    for line in lines:
        line = line.strip()
        if not line:
            if current_para:
                paragraphs.append(current_para)
                current_para = ""
            continue
        
        # 如果当前段落加上新行会超过最大长度，开始新段落
        if current_para and len(current_para) + len(line) + 1 > max_length:
            paragraphs.append(current_para)
            current_para = line
        else:
            if current_para:
                current_para += "<br/>" + line
            else:
                current_para = line
    
    if current_para:
        paragraphs.append(current_para)
    
    # 如果段落太长，进一步分割
    final_paragraphs = []
    for para in paragraphs:
        if len(para) > max_length:
            # 按句号、问号、感叹号分割
            sentences = []
            current_sentence = ""
            for char in para:
                current_sentence += char
                if char in ['。', '！', '？', '.', '!', '?']:
                    sentences.append(current_sentence)
                    current_sentence = ""
            if current_sentence:
                sentences.append(current_sentence)
            
            # 合并句子成段落
            temp_para = ""
            for sentence in sentences:
                if len(temp_para) + len(sentence) > max_length:
                    if temp_para:
                        final_paragraphs.append(temp_para)
                    temp_para = sentence
                else:
                    temp_para += sentence
            if temp_para:
                final_paragraphs.append(temp_para)
        else:
            final_paragraphs.append(para)
    
    return final_paragraphs if final_paragraphs else [text]

