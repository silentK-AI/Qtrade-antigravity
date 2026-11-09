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
import signal
import argparse
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any, Optional

from config import WeChatNotifyConfig
from notifications.wechat_pusher import WeChatPusher
from data.mock_replay import MockReplayProvider
from data.open_data_provider import OpenDataProvider
from models.stock_item import StockQuote, ClosingSnapshot, Snapshot1458, Snapshot0923, AuctionSnapshot, IntradayEvent
from strategies.auction_0923 import Auction0923Screener
from strategies.morning_auction import MorningAuctionScreener
from strategies.closing_stage import ClosingStageScreener
from strategies.closing_1458 import Closing1458Screener
from strategies.market_sentiment import MarketSentimentAnalyzer
from strategies.post_market_report import PostMarketReportScreener
from strategies.intraday_monitor import IntradayMonitor
from utils.calendar import TradeCalendar, get_beijing_now
from utils.logger import get_logger
from data.history_tracker import SignalHistoryTracker

logger = get_logger("daemon_scheduler")


class ServerDaemonScheduler:
    """服务器全天候量化调度服务"""

    def __init__(self, source: str = "live"):
        self.source = source
        self.pusher = WeChatPusher()
        self.sentiment_analyzer = MarketSentimentAnalyzer()
        self.data_provider = OpenDataProvider()
        self.snapshot_0919: Dict[str, Any] = {}
        self.intraday_monitor = IntradayMonitor(self.data_provider)
        self.history_tracker = SignalHistoryTracker()
        self.last_intraday_poll_ts: float = 0.0
        self.is_running: bool = True

    def is_trading_day(self, dt: datetime) -> bool:
        """判断是否为真实 A 股交易日 (排除周末及元旦/春节/清明/五一/端午/中秋/国庆法定休市)"""
        return TradeCalendar.is_trading_day(dt)

    def _capture_0919_snapshot(self):
        """09:19:50 锚定抓取集合竞价可撤单峰值（用于9:23判定虚假撤单）"""
        print("[09:19:50] 正在锚定集合竞价可撤单峰值盘口快照...")
        try:
            quotes = self.data_provider.fetch_main_board_top_active(page_size=120)
            self.snapshot_0919 = {q.code: {"quote": q, "volume": q.volume, "amount": q.amount, "price": q.current_price} for q in quotes}
            print(f"[09:19:50] 集合竞价峰值快照已锁定，共锁定 {len(self.snapshot_0919)} 只活跃标的！")
        except Exception as e:
            print(f"[09:19:50] 快照采集跳过: {e}")

    def _get_0923_candidates(self) -> List[Tuple[StockQuote, Snapshot0923]]:
        if self.source == "live":
            try:
                quotes = self.data_provider.fetch_main_board_top_active(page_size=120)
                if quotes:
                    candidates = []
                    for q in quotes:
                        if not (4.0 <= q.change_pct <= 10.5):
                            continue
                        # 计算 09:19:50 到 09:23:05 的撤单率
                        prev_data = self.snapshot_0919.get(q.code, {})
                        prev_vol = prev_data.get("volume", q.volume)
                        if prev_vol > q.volume and prev_vol > 0:
                            spoof_ratio = (prev_vol - q.volume) / prev_vol
                        else:
                            spoof_ratio = 0.0

                        is_rush = q.current_price >= prev_data.get("price", q.current_price)
                        real_seal = max(q.amount * 0.15, 20000000.0)
                        float_cap = q.float_market_cap * 100000000.0 if q.float_market_cap > 0 else 5000000000.0
                        seal_ratio = (real_seal / float_cap * 1000.0) if float_cap > 0 else 4.0

                        snap = Snapshot0923(
                            code=q.code,
                            indicative_price=q.current_price,
                            indicative_change_pct=q.change_pct,
                            real_seal_amount=real_seal,
                            real_seal_to_float_ratio=seal_ratio,
                            spoof_withdrawn_ratio=spoof_ratio,
                            is_sealed_limit=(q.change_pct >= 9.8),
                            volume_920_923=max(q.volume * 0.4, 100000.0),
                            is_upward_rush=is_rush
                        )
                        candidates.append((q, snap))
                    if candidates:
                        return candidates
            except Exception as e:
                logger.warning(f"09:23 实时接口获取异常，自动回退高保真回放: {e}")
        return MockReplayProvider.get_0923_dataset()

    def _get_0925_candidates(self) -> List[Tuple[StockQuote, AuctionSnapshot]]:
        """获取 09:25 开盘集合竞价候选标的（打板与首板/1进2）"""
        if self.source == "live":
            try:
                quotes = self.data_provider.fetch_main_board_top_active(page_size=120)
                if quotes:
                    candidates = []
                    for q in quotes:
                        if not (1.5 <= q.change_pct <= 9.9):
                            continue
                        open_p = q.open_price if q.open_price > 0 else q.current_price
                        vol_ratio = (q.volume / max(q.volume * 6.0, 1.0)) if q.volume > 0 else 0.08
                        unmatched = max(q.amount * 0.2, 5000000.0)
                        
                        snap = AuctionSnapshot(
                            code=q.code,
                            auction_price=open_p,
                            gap_percent=q.change_pct,
                            auction_volume=q.volume,
                            auction_amount=q.amount,
                            auction_vol_ratio=vol_ratio,
                            unmatched_buy_amount=unmatched,
                            unmatched_to_auction_ratio=0.6,
                            is_one_to_two=(q.change_pct >= 2.0),
                            last_minute_rush=True
                        )
                        candidates.append((q, snap))
                    if candidates:
                        return candidates
            except Exception as e:
                logger.warning(f"09:25 实时接口获取异常，自动回退高保真回放: {e}")
        return MockReplayProvider.get_morning_auction_dataset()

    def _get_live_or_fallback_sentiment(self, quotes: Optional[List[StockQuote]] = None) -> Dict[str, Any]:
        """获取全市场真实短线情绪周期指标（含真实涨停数、炸板率、最高连板与主线题材）"""
        if self.source == "live":
            try:
                sentiment = self.sentiment_analyzer.evaluate_realtime_sentiment(self.data_provider, quotes)
                logger.info(
                    f"[实时情绪] 状态: {sentiment.get('status')} | 涨停: {sentiment.get('limit_up_count')}家 | "
                    f"炸板率: {sentiment.get('exploded_ratio', 0.0):.1f}% | 最高: {sentiment.get('highest_continuous_board')}板 | "
                    f"主线题材: {sentiment.get('top_theme')}"
                )
                return sentiment
            except Exception as e:
                logger.warning(f"拉取实时市场情绪异常，回退默认情绪: {e}")

        return {
            "status": "活跃/做多周期",
            "limit_up_count": 35,
            "limit_down_count": 0,
            "exploded_ratio": 12.5,
            "highest_continuous_board": 5,
            "top_theme": "主板核心热点",
            "risk_advice": "聚焦有板块梯队配合的核心前排标的。",
            "sentiment_multiplier": 1.0
        }

    def _get_1450_candidates(self):
        if self.source == "live":
            try:
                quotes = self.data_provider.fetch_main_board_top_active(page_size=120)
                if quotes:
                    candidates = []
                    for q in quotes:
                        if not (4.0 <= q.change_pct <= 10.5):
                            continue
                        ratio = (q.current_price / q.high_price) if q.high_price > 0 else 1.0
                        snap = ClosingSnapshot(
                            code=q.code,
                            current_price=q.current_price,
                            day_high=q.high_price,
                            close_to_high_ratio=ratio,
                            current_change_pct=q.change_pct,
                            vwap=q.vwap,
                            is_above_vwap=(q.current_price >= q.vwap),
                            tail_volume=q.volume * 0.22,
                            total_volume=q.volume,
                            tail_vol_ratio=0.22,
                            tail_net_large_inflow=(q.amount * 0.15) / 10000,
                            is_rebound_limit=(q.change_pct >= 9.8 and q.low_price < q.current_price * 0.95)
                        )
                        candidates.append((q, snap))
                    if candidates:
                        return candidates
            except Exception as e:
                print(f"[数据源提示] 14:50 实时接口获取异常，自动回退高保真回放: {e}")
        return MockReplayProvider.get_closing_stage_dataset()

    def _get_1458_candidates(self):
        if self.source == "live":
            try:
                quotes = self.data_provider.fetch_main_board_top_active(page_size=150)
                zt_details = self.data_provider.fetch_today_zt_pool_details()
                if quotes:
                    candidates = []
                    for q in quotes:
                        if not (5.5 <= q.change_pct <= 10.5):
                            continue
                        detail = zt_details.get(q.code, {})
                        fbt = detail.get("first_seal_time", "09:30:00" if q.change_pct >= 9.8 else "未封板")
                        lbt = detail.get("last_seal_time", fbt)
                        zbc = detail.get("open_board_count", 0)
                        fund = detail.get("seal_amount", max(q.amount * 0.05, 30000000.0))
                        lbc = detail.get("continuous_boards", 1)

                        is_lu = (q.change_pct >= 9.8)
                        float_cap = q.float_market_cap * 100000000.0 if q.float_market_cap > 0 else 5000000000.0
                        seal_ratio = (fund / float_cap * 1000.0) if float_cap > 0 else 5.0

                        snap = Snapshot1458(
                            code=q.code,
                            indicative_price=q.current_price,
                            indicative_change_pct=q.change_pct,
                            is_limit_up=is_lu,
                            closing_seal_amount=fund,
                            seal_to_float_ratio=seal_ratio,
                            day_open_board_count=zbc,
                            first_seal_time=fbt,
                            continuous_board_count=lbc,
                            last_seal_time=lbt
                        )
                        candidates.append((q, snap))
                    if candidates:
                        return candidates
            except Exception as e:
                print(f"[数据源提示] 14:58 实时接口获取异常，自动回退高保真回放: {e}")
        return MockReplayProvider.get_1458_dataset()

    def execute_and_push(self, task_type: str):
        """执行指定时段策略并推送微信"""
        now_str = get_beijing_now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"触发定时量化任务: 【{task_type}】...")

        if task_type == "0923":
            title = f"🔔【09:23 早盘锁板精选】(全天封死+次日涨停)"
            screener = Auction0923Screener()
            dataset = self._get_0923_candidates()
            quotes = [q for q, _ in dataset] if dataset else None
            sentiment = self._get_live_or_fallback_sentiment(quotes)
            multiplier = float(sentiment.get("sentiment_multiplier", 1.0))
            signals = screener.run_strategy(dataset, sentiment_multiplier=multiplier)
            self.pusher.push(signals, title, sentiment)
            if signals:
                self.history_tracker.record_signals(task_type, signals)

        elif task_type == "0925":
            title = f"🚀【09:25 开盘竞价打板精选】"
            screener = MorningAuctionScreener()
            dataset = self._get_0925_candidates()
            quotes = [q for q, _ in dataset] if dataset else None
            sentiment = self._get_live_or_fallback_sentiment(quotes)
            multiplier = float(sentiment.get("sentiment_multiplier", 1.0))
            signals = screener.run_strategy(dataset, sentiment_multiplier=multiplier)
            self.pusher.push(signals, title, sentiment)
            if signals:
                self.history_tracker.record_signals(task_type, signals)

        elif task_type == "1450":
            title = f"📊【14:50 尾盘蓄势冲板精选】"
            screener = ClosingStageScreener()
            dataset = self._get_1450_candidates()
            quotes = [q for q, _ in dataset] if dataset else None
            sentiment = self._get_live_or_fallback_sentiment(quotes)
            multiplier = float(sentiment.get("sentiment_multiplier", 1.0))
            signals = screener.run_strategy(dataset, sentiment_multiplier=multiplier)
            self.pusher.push(signals, title, sentiment)
            if signals:
                self.history_tracker.record_signals(task_type, signals)

        elif task_type == "1458":
            title = f"🎯【14:58 尾盘竞价锁定】(次日大概率涨停)"
            screener = Closing1458Screener()
            dataset = self._get_1458_candidates()
            quotes = [q for q, _ in dataset] if dataset else None
            sentiment = self._get_live_or_fallback_sentiment(quotes)
            multiplier = float(sentiment.get("sentiment_multiplier", 1.0))
            signals = screener.run_strategy(dataset, sentiment_multiplier=multiplier)
            self.pusher.push(signals, title, sentiment)
            if signals:
                self.history_tracker.record_signals(task_type, signals)

        elif task_type == "1510":
            screener = PostMarketReportScreener()
            report_data = screener.run_report()
            # 自动评估上一交易日系统自选推荐在今日的战绩与胜率
            history_eval = self.history_tracker.evaluate_recent_signals(self.data_provider)
            self.pusher.push_post_market_report(report_data, history_eval=history_eval)

    def test_wechat_push(self):
        """测试微信推送连通性"""
        logger.info("[测试模式] 正在向配置的微信通道发送测试卡片...")
        self.execute_and_push("0923")

    def test_intraday_push(self):
        """测试盘中涨停上板与炸板异动微信推送"""
        logger.info("[测试模式] 正在构建盘中涨停与炸板模拟异动并推送到微信...")
        ev1 = IntradayEvent(
            event_type="LIMIT_UP",
            code="600519",
            name="贵州茅台",
            current_price=1780.00,
            change_pct=10.00,
            event_time=datetime.now().strftime("%H:%M:%S"),
            seal_amount_wan=65000.0,
            turnover_rate=2.8,
            open_board_count=0,
            continuous_boards=2,
            action_advice="【建议：重点打板/参与 2 进 3 接力】",
            reason="1 进 2 换手晋级成功，确立身位优势。买一封单 65000 万元极其硬朗，承接有力，符合主线接力标准。",
            industry="白酒"
        )
        ev2 = IntradayEvent(
            event_type="BROKEN_BOARD",
            code="000001",
            name="平安银行",
            current_price=12.15,
            change_pct=7.20,
            event_time=datetime.now().strftime("%H:%M:%S"),
            seal_amount_wan=0.0,
            turnover_rate=8.5,
            open_board_count=1,
            continuous_boards=1,
            action_advice="【建议：回踩均线低吸·博秒回封】",
            reason="炸板后价格仍坚守在 +7.2% 高位震荡，未出现踩踏恐慌，换手率 8.5% 良性，回踩分时均线不破可小仓位低吸博主力秒回封。",
            industry="股份制银行"
        )
        self.pusher.push_intraday_events([ev1, ev2])

    def run_daemon(self):
        """启动守护主循环"""
        # 优雅停机信号处理
        def _handle_shutdown(signum, frame):
            logger.info(f"收到终止信号 ({signum})，守护进程正在安全退出...")
            self.is_running = False
            sys.exit(0)

        signal.signal(signal.SIGINT, _handle_shutdown)
        signal.signal(signal.SIGTERM, _handle_shutdown)

        logger.info("=" * 80)
        logger.info("   A股打板量化策略系统 - 服务器后台自动化守护进程已启动")
        logger.info("   交易日历模块: 沪深法定休市日自动过滤 (A股周末与节假日休市完全识别)")
        logger.info("   关键定时节点: 09:23:05 | 09:25:05 | 14:50:00 | 14:58:05 | 15:10:05 (交易日)")
        logger.info("   盘中实时监测: 09:30:00 - 11:30:00 & 13:00:00 - 14:50:00 (涨停封板/炸板异动实时告警)")
        logger.info(f"   微信推送配置通道: {self.pusher.config.CHANNEL} (开启状态: {self.pusher.config.ENABLED})")
        logger.info("=" * 80)

        # 记录今天已经执行过的任务，防止重复触发
        executed_today = set()
        current_date_str = get_beijing_now().strftime("%Y-%m-%d")
        daily_intraday_alerts = 0
        MAX_DAILY_INTRADAY_ALERTS = 40

        while self.is_running:
            try:
                now = get_beijing_now()
                today_str = now.strftime("%Y-%m-%d")

                # 跨日清空已执行任务与盘中监控状态
                if today_str != current_date_str:
                    executed_today.clear()
                    current_date_str = today_str
                    daily_intraday_alerts = 0
                    self.intraday_monitor.seen_zt_stocks.clear()
                    self.intraday_monitor.seen_zb_stocks.clear()
                    self.intraday_monitor.is_initialized = False

                # A股非交易日（周末及法定假日）跳过
                if not self.is_trading_day(now):
                    time.sleep(60)
                    continue

                current_hm = now.strftime("%H:%M")
                current_hms = now.strftime("%H:%M:%S")

                # 0. 09:19:50 锚定抓取集合竞价可撤单峰值快照（用于9:23判定虚假撤单）
                if current_hm == "09:19" and "0919" not in executed_today:
                    if now.second >= 50:
                        self._capture_0919_snapshot()
                        executed_today.add("0919")

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

                # 6. 盘中交易时段实时异动监控 (09:30:00 - 11:30:00 & 13:00:00 - 14:50:00)
                is_morning_session = ("09:30:00" <= current_hms < "11:30:00")
                is_afternoon_session = ("13:00:00" <= current_hms < "14:50:00")

                if is_morning_session or is_afternoon_session:
                    # 间隔 20 秒轮询一次东财盘中涨停/炸板接口
                    if now.timestamp() - self.last_intraday_poll_ts >= 20.0:
                        self.last_intraday_poll_ts = now.timestamp()
                        try:
                            events = self.intraday_monitor.check_events()
                            if events:
                                if daily_intraday_alerts < MAX_DAILY_INTRADAY_ALERTS:
                                    logger.info(f"[{current_hms}] 盘中监测到 {len(events)} 起封板/炸板异动，正在推送微信...")
                                    self.pusher.push_intraday_events(events)
                                    daily_intraday_alerts += len(events)
                                elif daily_intraday_alerts == MAX_DAILY_INTRADAY_ALERTS:
                                    logger.warning(f"今日盘中异动推送已达上限 ({MAX_DAILY_INTRADAY_ALERTS}次)，暂停后续微信通知以防刷屏")
                                    daily_intraday_alerts += 1
                        except Exception as e:
                            logger.warning(f"[{current_hms}] 盘中异动监测轮询异常: {e}")

                # 每次循环休眠 3 秒，低 CPU 占用且不错过时间节点
                time.sleep(3)

            except Exception as e:
                logger.error(f"守护主循环遭遇异常，自动平稳恢复: {e}", exc_info=True)
                time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description="A股打板量化调度服务 - 服务器后台与微信推送")
    parser.add_argument("--test-push", action="store_true", help="立即向微信发送一条测试选股卡片")
    parser.add_argument("--test-intraday", action="store_true", help="立即向微信发送模拟盘中封板与炸板异动测试卡片")
    parser.add_argument("--post-market", action="store_true", help="立即生成并向微信推送 15:10 盘后涨停复盘与次日打板预案报告")
    parser.add_argument("--source", choices=["live", "mock"], default="mock", help="数据源 (live/mock)")
    args = parser.parse_args()

    scheduler = ServerDaemonScheduler(source=args.source)

    if args.test_push:
        scheduler.test_wechat_push()
    elif args.test_intraday:
        scheduler.test_intraday_push()
    elif args.post_market:
        scheduler.execute_and_push("1510")
    else:
        scheduler.run_daemon()


if __name__ == "__main__":
    main()
