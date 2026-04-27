"""
个股基本面与风险监控 (LLM)
"""
import json
import logging
from typing import Optional
import requests

from strategy.technical_analyzer import TechnicalReport
# 复用旧版的资讯收集工具
from legacy.tools.news_search_tool import NewsSearchTool

import os
from dotenv import load_dotenv
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True, encoding="utf-8-sig")

THIRD_PARTY_API_BASE_URL = os.getenv("THIRD_PARTY_API_BASE_URL", "https://hiapi.online/v1")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "sk-wIddyarusR7H9wZyxhxvecRXctBaafuNNvXBUuKMMyffTL0q")
GEMINI_ANALYSIS_MODEL = os.getenv("GEMINI_ANALYSIS_MODEL", "openai/gemini-2.5-pro-maxthinking")

logger = logging.getLogger(__name__)

class LLMFundamentalAnalyzer:
    """基本面与风险特征 LLM 分析器"""

    def __init__(self):
        self.news_tool = NewsSearchTool()
        self.api_base = THIRD_PARTY_API_BASE_URL.rstrip("/")
        self.api_key = GEMINI_API_KEY
        # 兼容处理模型名称前缀
        self.model = GEMINI_ANALYSIS_MODEL.replace("openai/", "")

    def generate_analysis(self, report: TechnicalReport) -> str:
        """
        基于拉取的资讯和技术指标生成综合评估
        
        Args:
            report: 已经计算完各项技术指标的数据类报告
            
        Returns:
            一段格式化好的精简分析文本
        """
        try:
            # 1. 获取近期新闻和公告
            logger.info(f"[{report.symbol}] 开始拉取最新的资讯以供 LLM 分析...")
            news_data = self.news_tool.search_all_news(report.symbol)
            # 因为数据结构可能比较大，为了不过度浪费 Token，提取部分有效信息
            # 默认只取前 5 条有效新闻或提取概览
            news_str = self._compact_news_data(news_data)

            # 2. 构建 Prompt
            system_prompt = (
                "你是一位资深的量化与基本面结合分析师。你的任务是根据提供的技术指标现状和最近的新闻基本面信息，"
                "对其后续走势进行【纯粹客观】的剖析。不要产生废话，直接回答核心问题。"
            )

            user_prompt = f"""
正在分析的股票：{report.name} ({report.symbol})

【一、技术指标现状】
当前价格：{report.price:.3f} (涨跌幅：{report.change_pct:.2f}%)
当前量比：{report.volume_ratio:.2f}   (判断放量/缩量状态)
RSI(14)：{report.rsi_14:.1f} ({report.rsi_status})
MACD：{report.macd_status}
均线系统：MA5={report.ma5}, MA10={report.ma10}, MA20={report.ma20}

【二、最新外围资讯与基本面】
{news_str}

【分析要求】
结合上方所给的【技术指标现状】和【业务/公告新闻基本面信息】，请进行综合评估，并严格按以下三个要点进行回答，每个要点控制在一到两句话以内：
1. 基本面是否发生改变？（是否存在利好/利空，或者是稳定的）
2. 增长逻辑是否发生改变？（结合量价活跃度、均线和基本面，评估短期上行/下行趋势）
3. 重大风险隐患提示？（寻找隐藏的风险点，如均线空头、放量下跌风险或政策利空等）

格式如下：
**基本面变动**：...
**增长逻辑**：...
**风险提示**：...
"""

            # 3. 发起请求
            logger.info(f"[{report.symbol}] 正在向 LLM ({self.model}) 发起分析请求...")
            response = self._call_llm(system_prompt, user_prompt)
            
            if response:
                logger.info(f"[{report.symbol}] LLM 分析完成")
                return response.strip()
            else:
                return "暂无足够的资讯数据可供大模型评估，或模型生成失败。"
                
        except Exception as e:
            logger.error(f"[{report.symbol}] LLM 判断基本面逻辑发生错误: {e}")
            return "大模型分析时发生网络或处理异常。"

    def _compact_news_data(self, results: dict) -> str:
        """压缩新闻字典为字符串，避免 Token 超限"""
        output = ""
        sources = results.get("sources", {})
        for source_name, source_data in sources.items():
            if source_data.get("success") and source_data.get("data"):
                output += f"[{source_name}]:\n"
                data = source_data.get("data")
                if isinstance(data, list):
                    for i, item in enumerate(data[:5], 1):  # 限制条数
                        # 把 JSON dict 再压缩为字符串，裁切超长内容
                        item_str = str(item)[:150]
                        output += f"- {item_str}\n"
                elif isinstance(data, dict):
                    # 如果是很简单的数据结构
                    output += f"- {str(data)[:200]}\n"
            output += "\n"
        if not output.strip():
            output = "近期无重大公告或外部突发相关新闻。"
        return output

    def _call_llm(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """通用的 HTTP Restful OpenAI 兼容调用"""
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2, # 降低温度以保证逻辑推导的一致性
            "max_tokens": 1000
        }
        
        try:
            resp = requests.post(url, headers=headers, json=data, timeout=60)
            resp.raise_for_status()
            resp_json = resp.json()
            if "choices" in resp_json and len(resp_json["choices"]) > 0:
                return resp_json["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"LLM API 接口请求失败: {e}")
            if hasattr(e, "response") and getattr(e, "response") is not None:
                logger.error(f"返回详情: {e.response.text}")
        return None
