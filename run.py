"""
量化分析系统 - A股打板策略主运行入口
支持四大实战时间窗口：
1. 09:23:00 不可撤单竞价抢筹锁定（--mode 0923）: 抓取当天全天封死 + 次日继续涨停
2. 09:25:00 开盘撮合完成精选（--mode morning）
3. 14:50:00 尾盘放量抢筹蓄势（--mode closing）
4. 14:58:00 尾盘集合竞价锁定（--mode 1458）: 抓取次日大概率直接涨停，避免次日买不进去
5. 智能时段自适应（--mode auto）
"""

import sys
import argparse
from datetime import datetime

from config import (
    PreAuction0923Config,
    MorningAuctionConfig,
    ClosingStageConfig,
    ClosingAuction1458Config,
    SentimentConfig
)
from utils.logger import TerminalVisualizer
from data.mock_replay import MockReplayProvider
from data.open_data_provider import OpenDataProvider
from strategies.auction_0923 import Auction0923Screener
from strategies.morning_auction import MorningAuctionScreener
from strategies.closing_stage import ClosingStageScreener
from strategies.closing_1458 import Closing1458Screener
from strategies.market_sentiment import MarketSentimentAnalyzer


def run_0923_mode(source: str = "live", codes_filter: list = None):
    """【09:23:00 核心窗口】早盘不可撤单竞价抢筹锁定（09:23-09:24 操作）"""
    TerminalVisualizer.print_banner("A股主板【09:23 不可撤单竞价抢筹锁定】(全天封死 + 次日涨停)")
    print("  提示：当前处于 9:20-9:25 不可撤单阶段，已剔除 9:15-9:20 虚假撤单，真金白银大单锁板！")
    print("  操作窗口：09:23:00 - 09:24:50 提交竞价买单，抢在 09:25 撮合前成交进场！\n")

    sentiment_analyzer = MarketSentimentAnalyzer()
    screener = Auction0923Screener()

    if source == "mock":
        dataset = MockReplayProvider.get_0923_dataset()
        sentiment = {
            "status": "离线仿真测试",
            "limit_up_count": len([q for q, _ in dataset if q.is_limit_up]),
            "limit_down_count": 0,
            "exploded_ratio": 0.0,
            "highest_continuous_board": 1,
            "top_theme": "离线测试标的",
            "risk_advice": "当前处于本地离线回放模式，展示历史仿真切片。",
            "sentiment_multiplier": 1.00
        }
        TerminalVisualizer.print_sentiment_summary(sentiment)

        signals = screener.run_strategy(
            candidates=dataset,
            sentiment_multiplier=sentiment["sentiment_multiplier"]
        )
        TerminalVisualizer.print_signals_table(signals, "09:23 不可撤单真实封板池 (锁定全天封死+次日连板)")
    else:
        print("  正在从实时行情接口获取 09:23 不可撤单买一封单及盘口...")
        from daemon_scheduler import ServerDaemonScheduler
        scheduler = ServerDaemonScheduler(source="live")
        dataset = scheduler._get_0923_candidates()
        quotes = [q for q, _ in dataset] if dataset else None
        sentiment = scheduler._get_live_or_fallback_sentiment(quotes)
        TerminalVisualizer.print_sentiment_summary(sentiment)
        signals = screener.run_strategy(
            candidates=dataset,
            sentiment_multiplier=float(sentiment["sentiment_multiplier"])
        )
        TerminalVisualizer.print_signals_table(signals, "09:23 不可撤单实时封板池 (锁定全天封死+次日连板)")


def run_1458_mode(source: str = "live", codes_filter: list = None):
    """【14:58:00 核心窗口】尾盘集合竞价锁定（14:58-14:59 操作，锁定次日涨停）"""
    TerminalVisualizer.print_banner("A股主板【14:58 尾盘集合竞价锁定】(锁定次日大概率涨停)")
    print("  提示：当前处于 14:57-15:00 收盘不可撤单集合竞价，全天筹码沉淀完毕！")
    print("  操作窗口：14:58:00 - 14:59:50 提交收盘竞价买单，15:00 准时成交，规避次日早盘直接一字买不进去！\n")

    sentiment_analyzer = MarketSentimentAnalyzer()
    screener = Closing1458Screener()

    if source == "mock":
        dataset = MockReplayProvider.get_1458_dataset()
        sentiment = {
            "status": "离线仿真测试",
            "limit_up_count": len([q for q, _ in dataset if q.is_limit_up]),
            "limit_down_count": 0,
            "exploded_ratio": 0.0,
            "highest_continuous_board": 1,
            "top_theme": "离线测试标的",
            "risk_advice": "当前处于本地离线回放模式，展示历史仿真切片。",
            "sentiment_multiplier": 1.00
        }
        TerminalVisualizer.print_sentiment_summary(sentiment)

        signals = screener.run_strategy(
            candidates=dataset,
            sentiment_multiplier=sentiment["sentiment_multiplier"]
        )
        TerminalVisualizer.print_signals_table(signals, "14:58 尾盘竞价锁定池 (次日大概率涨停)")
    else:
        print("  正在从实时行情接口获取 14:58 收盘集合竞价盘口与封单...")
        from daemon_scheduler import ServerDaemonScheduler
        scheduler = ServerDaemonScheduler(source="live")
        dataset = scheduler._get_1458_candidates()
        quotes = [q for q, _ in dataset] if dataset else None
        sentiment = scheduler._get_live_or_fallback_sentiment(quotes)
        TerminalVisualizer.print_sentiment_summary(sentiment)
        signals = screener.run_strategy(
            candidates=dataset,
            sentiment_multiplier=float(sentiment["sentiment_multiplier"])
        )
        TerminalVisualizer.print_signals_table(signals, "14:58 尾盘竞价实时锁定池 (次日大概率涨停)")


def run_morning_mode(source: str = "live", codes_filter: list = None):
    """运行早盘竞价选股模式 (09:25:00 锁定)"""
    TerminalVisualizer.print_banner("A股主板【早盘集合竞价打板】选股模式启动 (09:25:00)")
    
    sentiment_analyzer = MarketSentimentAnalyzer()
    screener = MorningAuctionScreener()

    if source == "mock":
        dataset = MockReplayProvider.get_morning_auction_dataset()
        sentiment = {
            "status": "离线仿真测试",
            "limit_up_count": len([q for q, _ in dataset if q.is_limit_up]),
            "limit_down_count": 0,
            "exploded_ratio": 0.0,
            "highest_continuous_board": 1,
            "top_theme": "离线测试标的",
            "risk_advice": "当前处于本地离线回放模式，展示历史仿真切片。",
            "sentiment_multiplier": 1.00
        }
        TerminalVisualizer.print_sentiment_summary(sentiment)
        
        signals = screener.run_strategy(
            candidates=dataset,
            sentiment_multiplier=sentiment["sentiment_multiplier"]
        )
        TerminalVisualizer.print_signals_table(signals, "早盘竞价打板·09:25精选")
    else:
        print("  正在从开源实时行情接口抓取主板盘前竞价数据...")
        from daemon_scheduler import ServerDaemonScheduler
        scheduler = ServerDaemonScheduler(source="live")
        auction_candidates = scheduler._get_0925_candidates()
        quotes = [q for q, _ in auction_candidates] if auction_candidates else None
        sentiment = scheduler._get_live_or_fallback_sentiment(quotes)
        TerminalVisualizer.print_sentiment_summary(sentiment)

        signals = screener.run_strategy(
            candidates=auction_candidates,
            sentiment_multiplier=float(sentiment["sentiment_multiplier"])
        )
        TerminalVisualizer.print_signals_table(signals, "早盘竞价打板·实时精选")


def run_closing_mode(source: str = "live", codes_filter: list = None):
    """运行尾盘抢筹选股模式 (14:50:00 锁定)"""
    TerminalVisualizer.print_banner("A股主板【尾盘抢筹/蓄势冲板】选股模式启动 (14:50:00)")
    
    sentiment_analyzer = MarketSentimentAnalyzer()
    screener = ClosingStageScreener()

    if source == "mock":
        dataset = MockReplayProvider.get_closing_stage_dataset()
        sentiment = {
            "status": "离线仿真测试",
            "limit_up_count": len([q for q, _ in dataset if q.is_limit_up]),
            "limit_down_count": 0,
            "exploded_ratio": 0.0,
            "highest_continuous_board": 1,
            "top_theme": "离线测试标的",
            "risk_advice": "当前处于本地离线回放模式，展示历史仿真切片。",
            "sentiment_multiplier": 1.00
        }
        TerminalVisualizer.print_sentiment_summary(sentiment)
        
        signals = screener.run_strategy(
            candidates=dataset,
            sentiment_multiplier=sentiment["sentiment_multiplier"]
        )
        TerminalVisualizer.print_signals_table(signals, "尾盘选股·14:50精选")
    else:
        print("  正在从开源实时行情接口抓取主板尾盘分时异动数据...")
        from daemon_scheduler import ServerDaemonScheduler
        scheduler = ServerDaemonScheduler(source="live")
        closing_candidates = scheduler._get_1450_candidates()
        quotes = [q for q, _ in closing_candidates] if closing_candidates else None
        sentiment = scheduler._get_live_or_fallback_sentiment(quotes)
        TerminalVisualizer.print_sentiment_summary(sentiment)

        signals = screener.run_strategy(
            candidates=closing_candidates,
            sentiment_multiplier=float(sentiment["sentiment_multiplier"])
        )
        TerminalVisualizer.print_signals_table(signals, "尾盘选股·实时精选")


def main():
    parser = argparse.ArgumentParser(description="A股打板策略量化分析系统 - 四大实战时间窗口")
    parser.add_argument(
        "--mode",
        choices=["0923", "morning", "closing", "1458", "sentiment", "auto", "all"],
        default="auto",
        help="策略运行模式: 0923(9:23不可撤单抢筹), morning(9:25开盘竞价), closing(14:50尾盘选股), 1458(14:58收盘竞价锁次日涨停), auto(自动时段), all(全部运行)"
    )
    parser.add_argument(
        "--source",
        choices=["mock", "live"],
        default="live",
        help="数据源类型: mock(离线高保真仿真切片), live(开源实时接口)"
    )
    parser.add_argument(
        "--codes",
        type=str,
        default="",
        help="可选自定义输入股票池(逗号分隔，如 '600123,002456')"
    )

    args = parser.parse_args()

    mode = args.mode
    if mode == "auto":
        now_hour = datetime.now().hour
        now_minute = datetime.now().minute
        # 智能自适应判断时间
        if now_hour == 9 and now_minute < 25:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 判定处于早盘不可撤单关键竞价期，自动启动【09:23 竞价抢筹锁板模式】！")
            mode = "0923"
        elif (now_hour == 9 and now_minute >= 25) or (now_hour == 10) or (now_hour == 11 and now_minute <= 30):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 判定处于早盘开盘时段，自动启动【早盘 09:25 竞价打板模式】！")
            mode = "morning"
        elif (now_hour == 14 and now_minute >= 57) or (now_hour == 15 and now_minute <= 5):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 判定处于尾盘集合竞价关键期，自动启动【14:58 尾盘竞价锁次日涨停模式】！")
            mode = "1458"
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 判定处于尾盘选股窗口，自动启动【尾盘 14:50 蓄势冲板模式】！")
            mode = "closing"

    if mode == "0923":
        run_0923_mode(source=args.source)
    elif mode == "morning":
        run_morning_mode(source=args.source)
    elif mode == "closing":
        run_closing_mode(source=args.source)
    elif mode == "1458":
        run_1458_mode(source=args.source)
    elif mode == "all":
        run_0923_mode(source=args.source)
        run_morning_mode(source=args.source)
        run_closing_mode(source=args.source)
        run_1458_mode(source=args.source)


if __name__ == "__main__":
    main()
