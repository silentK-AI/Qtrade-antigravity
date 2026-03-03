"""
使用示例
演示如何使用量化交易工具进行股票价格预测
"""
from crew.trading_crew import run_trading_analysis


def example_basic_usage():
    """基本使用示例"""
    print("=" * 80)
    print("示例1: 基本使用 - 预测平安银行(000001)的当日价格")
    print("=" * 80)
    
    result = run_trading_analysis(
        stock_code="000001"  # 平安银行
    )
    
    print("\n分析结果:")
    print(result.get("result", "无结果"))
    print("\n" + "=" * 80)


def example_with_date_range():
    """指定日期范围示例"""
    print("=" * 80)
    print("示例2: 指定日期范围 - 预测万科A(000002)的当日价格")
    print("=" * 80)
    
    result = run_trading_analysis(
        stock_code="000002",  # 万科A
        start_date="20220101",  # 2022年1月1日
        end_date="20231231"     # 2023年12月31日
    )
    
    print("\n分析结果:")
    print(result.get("result", "无结果"))
    print("\n" + "=" * 80)


def example_save_to_file():
    """保存结果到文件示例"""
    print("=" * 80)
    print("示例3: 保存结果到文件")
    print("=" * 80)
    
    import json
    
    result = run_trading_analysis(
        stock_code="600000"  # 浦发银行
    )
    
    # 保存到文件
    output_file = "result_example.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n结果已保存到: {output_file}")
    print("=" * 80)


if __name__ == "__main__":
    # 注意：API密钥已在config.py中配置
    print("量化交易工具使用示例")
    print("注意：API密钥已在config.py中默认配置，可直接使用")
    print()
    
    # 取消注释以运行示例
    # example_basic_usage()
    # example_with_date_range()
    # example_save_to_file()
    
    print("请取消注释相应的示例函数来运行示例")

