"""
终端美化排版与日志记录工具
重点突出资金因子（资金得分 >= 55% 权重）、买入指引与止损风控
"""

import sys
from typing import List
from models.stock_item import StrategySignal


class TerminalVisualizer:
    """策略信号终端可视化排版"""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"      # A股涨/资金多头红色
    GREEN = "\033[92m"    # A股跌/绿色
    YELLOW = "\033[93m"   # 警告/提示黄色
    CYAN = "\033[96m"     # 辅助/表头青色
    MAGENTA = "\033[95m"  # 核心高亮洋红

    @classmethod
    def print_banner(cls, title: str):
        width = 92
        print("\n" + "=" * width)
        print(f"{cls.BOLD}{cls.CYAN}{title.center(width)}{cls.RESET}")
        print("=" * width + "\n")

    @classmethod
    def print_sentiment_summary(cls, sentiment_data: dict):
        """打印市场短线投机情绪看板"""
        cls.print_banner("全市场短线投机情绪看板 (大局观风控·天气预报)")
        
        status_color = cls.RED if "做多" in sentiment_data.get("status", "") else cls.YELLOW
        print(f"  当前情绪周期: {status_color}{cls.BOLD}{sentiment_data.get('status', '未知')}{cls.RESET}")
        print(f"  涨停家数: {cls.RED}{sentiment_data.get('limit_up_count', 0)}{cls.RESET} 家 | "
              f"跌停家数: {cls.GREEN}{sentiment_data.get('limit_down_count', 0)}{cls.RESET} 家 | "
              f"炸板率: {cls.YELLOW}{sentiment_data.get('exploded_ratio', 0):.1f}%{cls.RESET}")
        print(f"  连板最高梯队: {cls.MAGENTA}{cls.BOLD}{sentiment_data.get('highest_continuous_board', 1)} 连板{cls.RESET} | "
              f"领涨主线题材: {cls.CYAN}{sentiment_data.get('top_theme', '全市场轮动')}{cls.RESET}")
        print(f"  风控仓位指引: {cls.BOLD}{sentiment_data.get('risk_advice', '观望')}{cls.RESET}")
        print("-" * 92)

    @classmethod
    def print_signals_table(cls, signals: List[StrategySignal], mode_name: str):
        """格式化输出策略选股结果列表"""
        cls.print_banner(f"【{mode_name}】次日涨停潜力标的精选池 (资金因子占比 >= 55%)")
        
        if not signals:
            print(f"  {cls.YELLOW}当前未筛选出达到评分阈值（综合 >= 75分且资金充沛）的高确定性标的，建议空仓或防守。{cls.RESET}\n")
            return

        # 表头：明确展示综合评分与资金因子专属得分
        headers = ["代码", "名称", "综合评分", "资金得分(主导)", "现价/开盘", "涨幅%", "形态战法", "买入操作指引", "防守止损位"]
        row_format = "  {:<7} {:<8} {:<8} {:<15} {:<10} {:<8} {:<17} {:<19} {:<8}"
        print(cls.BOLD + cls.CYAN + row_format.format(*headers) + cls.RESET)
        print("  " + "-" * 102)

        for s in signals:
            score_color = cls.RED if s.score >= 85 else cls.YELLOW
            cap_color = cls.RED if s.capital_score >= 45 else cls.YELLOW
            pct_color = cls.RED if s.change_pct >= 0 else cls.GREEN
            
            print(row_format.format(
                s.code,
                s.name,
                f"{score_color}{s.score:.1f}{cls.RESET}",
                f"{cap_color}{s.capital_score:.1f}分{cls.RESET}",
                f"{s.current_price:.2f}元",
                f"{pct_color}{s.change_pct:+.2f}%{cls.RESET}",
                s.target_pattern[:15],
                s.suggested_action[:18],
                f"{s.stop_loss_price:.2f}元"
            ))
            
            # 详细资金因子证据
            cap_evidences = [f"{v}" for k, v in s.key_factors.items() if "资金" in k]
            cap_str = " | ".join(cap_evidences[:3]) if cap_evidences else "资金流入强劲"
            print(f"    ├─ {cls.BOLD}资金面证据:{cls.RESET} {cls.RED}{cap_str}{cls.RESET}")
            print(f"    └─ {cls.BOLD}次日涨停预期:{cls.RESET} {cls.MAGENTA}{s.next_day_expectation}{cls.RESET}")
            print()
