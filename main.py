"""
量化交易工具主程序
使用CrewAI多智能体系统进行股票价格预测
"""
import os
# 在导入 CrewAI 之前禁用遥测和追踪功能（避免生成无法访问的链接）
os.environ["CREWAI_TELEMETRY_OPT_OUT"] = "1"
os.environ["DO_NOT_TRACK"] = "1"

import argparse
import json
from datetime import datetime
from crew.trading_crew import run_trading_analysis
from config import GEMINI_API_KEY


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="量化交易工具 - 股票价格预测")
    parser.add_argument(
        "--stock-code",
        type=str,
        required=True,
        help="股票代码（如：000001）"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="开始日期，格式：YYYYMMDD（可选，默认三年前）"
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="结束日期，格式：YYYYMMDD（可选，默认今天）"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出文件路径（可选，默认打印到控制台）"
    )
    
    args = parser.parse_args()
    
    # 检查API密钥
    if not GEMINI_API_KEY:
        print("错误：未设置GEMINI_API_KEY环境变量")
        print("请在.env文件中设置GEMINI_API_KEY，或使用环境变量")
        return
    
    print("=" * 80)
    print("量化交易工具 - 股票价格预测系统")
    print("=" * 80)
    print(f"股票代码: {args.stock_code}")
    print(f"开始日期: {args.start_date or '默认（三年前）'}")
    print(f"结束日期: {args.end_date or '默认（今天）'}")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()
    
    try:
        # 运行分析
        print("正在启动多智能体分析系统...")
        print()
        
        result = run_trading_analysis(
            stock_code=args.stock_code,
            start_date=args.start_date,
            end_date=args.end_date
        )
        
        print()
        print("=" * 80)
        print("分析完成！")
        print("=" * 80)
        print()
        
        # 输出结果
        if args.output:
            # 保存到文件
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)
            print(f"结果已保存到: {args.output}")
        else:
            # 打印到控制台
            print("分析结果:")
            print("-" * 80)
            print(result.get("result", "无结果"))
            print("-" * 80)
            
            # 打印各任务输出
            if result.get("tasks_output"):
                print("\n各任务输出:")
                for task_name, task_output in result["tasks_output"].items():
                    print(f"\n任务: {task_name}")
                    print(f"输出: {task_output}")
                    print("-" * 80)
            
            # 显示使用的模型
            if result.get("model_used"):
                print(f"\n使用的模型: {result['model_used']}")
        
        print()
        print(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        print(f"错误：{str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

