"""
智能 LLM 包装器
当遇到 429 错误时自动切换到备用模型
"""
from crewai import LLM
from config import GEMINI_MODEL, GEMINI_FALLBACK_MODEL, GEMINI_API_KEY
import logging

logger = logging.getLogger(__name__)


class SmartLLM:
    """
    智能 LLM 包装器
    当主模型遇到 429 错误时，自动切换到备用模型
    """
    
    def __init__(self, temperature: float = 0.1, use_fallback: bool = False):
        """
        初始化智能 LLM
        
        Args:
            temperature: 温度参数
            use_fallback: 是否直接使用备用模型
        """
        self.temperature = temperature
        self.use_fallback = use_fallback
        self.primary_model = GEMINI_MODEL
        self.fallback_model = GEMINI_FALLBACK_MODEL
        self.current_model = self.fallback_model if use_fallback else self.primary_model
        
        # 创建 LLM 实例
        self.llm = LLM(
            model=self.current_model,
            temperature=temperature,
            api_key=GEMINI_API_KEY
        )
        
        logger.info(f"初始化 SmartLLM，使用模型: {self.current_model}")
    
    def switch_to_fallback(self):
        """切换到备用模型"""
        if self.current_model != self.fallback_model:
            logger.warning(f"检测到 429 错误，从 {self.current_model} 切换到 {self.fallback_model}")
            self.current_model = self.fallback_model
            self.llm = LLM(
                model=self.fallback_model,
                temperature=self.temperature,
                api_key=GEMINI_API_KEY
            )
            return True
        return False
    
    def get_llm(self) -> LLM:
        """
        获取 LLM 实例
        
        Returns:
            LLM 实例
        """
        return self.llm


def create_smart_llm(temperature: float = 0.1, use_fallback: bool = False) -> LLM:
    """
    创建智能 LLM 实例
    
    Args:
        temperature: 温度参数
        use_fallback: 是否直接使用备用模型
    
    Returns:
        LLM 实例
    """
    smart_llm = SmartLLM(temperature=temperature, use_fallback=use_fallback)
    return smart_llm.get_llm()

