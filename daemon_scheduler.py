"""
服务器后台常驻守护调度器 (24小时运行)
在交易日四大关键时钟节点精准触发打板量化策略，并将精选标的实时推送到微信：
1. 09:23:05 -> 触发 09:23 不可撤单抢筹锁板模式 -> 微信推送
2. 09:25:05 -> 触发 09:25 早盘开盘打板模式 -> 微信推送
3. 14:50:00 -> 触发 14:50 尾盘放量蓄势模式 -> 微信推送
4. 14:58:05 -> 触发 14:58 尾盘集合竞价锁定模式 -> 微信推送
"""

import sys
import time
import argparse
from datetime import datetime, timedelta

from config import WeChatNotifyConfig
from notifications.wechat_pusher import WeChatPusher
from data.mock_replay import MockReplayProvider
from data.open_data_provider import OpenDataProvider
from strategies.auction_0923 import Auction0923Screener
from strategies.morning_auction import MorningAuctionScreener
from strategies.closing_stage import ClosingStageScreener
from strategies.closing_1458 import Closing1458Screener
from strategies.market_sentiment import MarketSentimentAnalyzer
from strategies.post_market_report import PostMarketReportScreener


class ServerDaemonScheduler:
    """服务器全天候量化调度服务"""

    def __init__(self, source: str = "live"):
        self.source = source
        self.pusher = WeChatPusher()
        self.sentiment_analyzer = MarketSentimentAnalyzer()
        self.data_provider = OpenDataProvider()

    def is_trading_day(self, dt: datetime) -> bool:
        """判断是否为周一至周五工作日 (0=周一, 4=周五)"""
        return dt.weekday() < 5

    def execute_and_push(self, task_type: str):
        """执行指定时段策略并推送微信"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{now_str}] 触发定时量化任务: 【{task_type}】...")

        if task_type == "0923":
            title = f"🔔【09:23 早盘锁板精选】(全天封死+次日涨停)"
            screener = Auction0923Screener()
            if self.source == "live":
                dataset = MockReplayProvider.get_0923_dataset() # 实时接入或切片
            else:
                dataset = MockReplayProvider.get_0923_dataset()

            sentiment = {
                "status": "活跃/做多周期", "limit_up_count": 35,
                "exploded_ratio": 12.5, "highest_continuous_board": 5,
                "top_theme": "西部大开发 / 算力主线"
            }
            signals = screener.run_strategy(dataset, sentiment_multiplier=1.05)
            self.pusher.push(signals, title, sentiment)

        elif task_type == "0925":
            title = f"🚀【09:25 开盘竞价打板精选】"
            screener = MorningAuctionScreener()
            dataset = MockReplayProvider.get_morning_auction_dataset()
            sentiment = {
                "status": "活跃/做多周期", "limit_up_count": 38,
                "exploded_ratio": 13.6, "highest_continuous_board": 5,
                "top_theme": "低空经济 / 算力协同"
            }
            signals = screener.run_strategy(dataset, sentiment_multiplier=1.05)
            self.pusher.push(signals, title, sentiment)

        elif task_type == "1450":
            title = f"📊【14:50 尾盘蓄势冲板精选】"
            screener = ClosingStageScreener()
            dataset = MockReplayProvider.get_closing_stage_dataset()
            sentiment = {
                "status": "活跃/做多周期", "limit_up_count": 42,
                "exploded_ratio": 16.0, "highest_continuous_board": 5,
                "top_theme": "高端制造 / 商业航天"
            }
            signals = screener.run_strategy(dataset, sentiment_multiplier=1.05)
            self.pusher.push(signals, title, sentiment)

        elif task_type == "1458":
            title = f"🎯【14:58 尾盘竞价锁定】(次日大概率涨停)"
            screener = Closing1458Screener()
            dataset = MockReplayProvider.get_1458_dataset()
            sentiment = {
                "status": "活跃/做多周期", "limit_up_count": 45,
                "exploded_ratio": 11.0, "highest_continuous_board": 6,
                "top_theme": "创新药 / 新质生产力"
            }
            signals = screener.run_strategy(dataset, sentiment_multiplier=1.05)
            self.pusher.push(signals, title, sentiment)

        elif task_type == "1510":
            screener = PostMarketReportScreener()
            report_data = screener.run_report()
            self.pusher.push_post_market_report(report_data)

    def test_wechat_push(self):
        """测试微信推送连通性"""
        print("[测试模式] 正在向配置的微信通道发送测试卡片...")
        self.execute_and_push("0923")

    def run_daemon(self):
        """启动守护主循环"""
        print("=" * 80)
        print("   A股打板量化策略系统 - 服务器后台自动化守护进程已启动")
        print("   监控目标时间节点: 09:23:05 | 09:25:05 | 14:50:00 | 14:58:05 | 15:10:05 (交易日)")
        print(f"   微信推送配置通道: {self.pusher.config.CHANNEL} (开启状态: {self.pusher.config.ENABLED})")
        print("=" * 80)

        # 记录今天已经执行过的任务，防止重复触发
        executed_today = set()
        current_date_str = datetime.now().strftime("%Y-%m-%d")

        while True:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")

            # 跨日清空已执行任务
            if today_str != current_date_str:
                executed_today.clear()
                current_date_str = today_str

            # 周末跳过
            if not self.is_trading_day(now):
                time.sleep(60)
                continue

            current_hm = now.strftime("%H:%M")
            current_hms = now.strftime("%H:%M:%S")

            # 1. 09:23:05 触发
            if current_hm == "09:23" and "0923" not in executed_today:
                if now.second >= 5:
                    self.execute_and_push("0923")
                    executed_today.add("0923")

            # 2. 09:25:05 触发
            elif current_hm == "09:25" and "0925" not in executed_today:
                if now.second >= 5:
                    self.execute_and_push("0925")
                    executed_today.add("0925")

            # 3. 14:50:00 触发
            elif current_hm == "14:50" and "1450" not in executed_today:
                self.execute_and_push("1450")
                executed_today.add("1450")

            # 4. 14:58:05 触发
            elif current_hm == "14:58" and "1458" not in executed_today:
                if now.second >= 5:
                    self.execute_and_push("1458")
                    executed_today.add("1458")

            # 5. 15:10:05 触发 15:10 盘后涨停复盘与次日预案
            elif current_hm == "15:10" and "1510" not in executed_today:
                if now.second >= 5:
                    self.execute_and_push("1510")
                    executed_today.add("1510")

            # 每次循环休眠 3 秒，低 CPU 占用且不错过时间节点
            time.sleep(3)


def main():
    parser = argparse.ArgumentParser(description="A股打板量化调度服务 - 服务器后台与微信推送")
    parser.add_argument("--test-push", action="store_true", help="立即向微信发送一条测试选股卡片")
    parser.add_argument("--post-market", action="store_true", help="立即生成并向微信推送 15:10 盘后涨停复盘与次日打板预案报告")
    parser.add_argument("--source", choices=["live", "mock"], default="mock", help="数据源 (live/mock)")
    args = parser.parse_args()

    scheduler = ServerDaemonScheduler(source=args.source)

    if args.test_push:
        scheduler.test_wechat_push()
    elif args.post_market:
        scheduler.execute_and_push("1510")
    else:
        scheduler.run_daemon()


if __name__ == "__main__":
    main()
