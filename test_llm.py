import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True, encoding="utf-8-sig")

from strategy.technical_analyzer import TechnicalReport
from strategy.llm_fundamental_analyzer import LLMFundamentalAnalyzer

def test():
    report = TechnicalReport(
        symbol="000001", 
        name="平安银行", 
        price=10.5, 
        change_pct=1.2,
        volume_ratio=1.5,
        rsi_14=45, 
        rsi_status="中性",
        macd_status="金叉",
        ma5=10.2,
        ma10=10.3,
        ma20=11.0
    )
    analyzer = LLMFundamentalAnalyzer()
    print("---------------------------------")
    print(f"Testing LLMFundamentalAnalyzer for {report.name}...")
    res = analyzer.generate_analysis(report)
    print("---------------------------------")
    print("RESPONSE:")
    print(res)

if __name__ == "__main__":
    test()
