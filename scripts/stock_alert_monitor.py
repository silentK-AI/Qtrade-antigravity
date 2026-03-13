"""
个股技术指标监控与微信推送脚本

独立运行，不影响 T+0 交易引擎。

功能:
  - 08:30: 拉取历史 K 线，计算基础技术指标
  - 09:15: 生成盘前技术分析报告 → 微信推送
  - 09:30-15:00: 盘中实时监控，检测交易信号 → 微信推送
  - 15:00-16:00: 如有港股标的，继续监控

用法:
  python scripts/stock_alert_monitor.py                 # 常规运行
  python scripts/stock_alert_monitor.py --premarket     # 仅运行盘前报告
  python scripts/stock_alert_monitor.py --intraday      # 仅运行盘中监控
"""
import sys
import os
import time
import argparse
from datetime import datetime, timedelta
from typing import Optional

# 把项目根目录加到 sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

# 加载环境变量
try:
    from dotenv import load_dotenv
    # encoding='utf-8-sig' 可以自动处理 Windows PowerShell 生成的 UTF-8 BOM 文件
    load_dotenv(os.path.join(BASE_DIR, ".env"), override=True, encoding="utf-8-sig")
except ImportError:
    pass

from loguru import logger

from config.stock_settings import (
    STOCK_ALERT_SYMBOLS,
    ALERT_PREMARKET_TIME,
    ALERT_SCAN_INTERVAL,
    ALERT_SIGNAL_COOLDOWN,
    ALERT_HISTORY_DAYS,
)
from data.stock_data_service import StockDataService, MarketSentiment
from strategy.technical_analyzer import TechnicalAnalyzer, TechnicalReport, AlertSignal
from monitor.notifier import Notifier


class StockAlertMonitor:
    """
    个股技术指标监控器。

    盘前推送技术分析报告，盘中实时检测并推送交易信号。
    """

    def __init__(self):
        self._data_service = StockDataService()
        self._analyzer = TechnicalAnalyzer()
        self._notifier = Notifier()

        # 历史 K 线缓存: {symbol: DataFrame}
        self._klines_cache: dict = {}
        # 上一次技术报告: {symbol: TechnicalReport}
        self._prev_reports: dict[str, TechnicalReport] = {}
        # 信号冷却: {symbol_signaltype: (timestamp, reason)}
        self._signal_cooldown: dict[str, tuple[float, str]] = {}

    # ------------------------------------------------------------------
    #  主流程
    # ------------------------------------------------------------------

    def run(self, mode: str = "full"):
        """
        运行监控器。

        Args:
            mode: 'full' | 'premarket' | 'intraday'
        """
        self._setup_logger()
        logger.info("====================================")
        logger.info("  个股技术指标监控器启动")
        logger.info(f"  模式: {mode}")
        logger.info(f"  监控标的: {len(STOCK_ALERT_SYMBOLS)} 只")
        logger.info(f"  工作目录: {os.getcwd()}")
        logger.info(f"  Python 解释器: {sys.executable}")
        logger.info("====================================")

        if mode in ("full", "premarket"):
            # 拉取历史 K 线
            self._load_history_data()
            # 盘前报告
            self._premarket_report()

        if mode in ("full", "intraday"):
            if mode == "intraday":
                self._load_history_data()
            # 盘中监控循环
            self._intraday_monitor()

        logger.info("监控器退出。")

    # ------------------------------------------------------------------
    #  盘前流程
    # ------------------------------------------------------------------

    def _load_history_data(self):
        """拉取所有标的的历史 K 线数据"""
        logger.info("=== 拉取历史 K 线数据 ===")
        for symbol, cfg in STOCK_ALERT_SYMBOLS.items():
            logger.info(f"  拉取 [{symbol} {cfg['name']}] ...")
            df = self._data_service.fetch_history_klines(symbol, days=ALERT_HISTORY_DAYS)
            if df is not None and not df.empty:
                self._klines_cache[symbol] = df
                logger.info(f"  [{symbol}] 获取 {len(df)} 天 K 线")
            else:
                logger.warning(f"  [{symbol}] 获取 K 线失败")
            # 每个标的之间间隔 1.5 秒，避免 akshare 连接被拒
            time.sleep(1.5)

        logger.info(f"历史数据加载完成: {len(self._klines_cache)}/{len(STOCK_ALERT_SYMBOLS)} 只成功")

    def _premarket_report(self):
        """生成并推送盘前技术分析报告"""
        logger.info("=== 生成盘前技术分析报告 ===")

        # 获取实时行情（盘前竞价阶段可获取昨收等）
        quotes = self._data_service.fetch_realtime_quotes()

        # 获取市场情绪
        sentiment = self._data_service.fetch_market_sentiment()

        # 生成每个标的的技术报告
        reports = []
        for symbol, cfg in STOCK_ALERT_SYMBOLS.items():
            klines = self._klines_cache.get(symbol)
            if klines is None:
                logger.warning(f"[{symbol}] 无历史 K 线，跳过")
                continue

            quote = quotes.get(symbol)
            current_price = quote.price if quote and quote.is_valid else 0.0
            prev_close = quote.prev_close if quote else 0.0
            current_volume = quote.volume if quote else 0.0

            report = self._analyzer.analyze(
                symbol=symbol,
                name=cfg["name"],
                klines=klines,
                current_price=current_price,
                current_volume=current_volume,
                prev_close=prev_close,
            )

            if report:
                reports.append(report)
                self._prev_reports[symbol] = report

        if not reports:
            logger.warning("未生成任何技术报告")
            return

        # 组装完整报告
        content = self._format_premarket_content(reports, sentiment)

        # 推送
        logger.info(f"推送盘前报告 ({len(reports)} 只标的)")
        self._notifier.notify_premarket_report(content)
        logger.info("盘前报告推送完成 ✓")

    def _format_premarket_content(
        self, reports: list[TechnicalReport], sentiment: MarketSentiment
    ) -> str:
        """组装盘前报告完整内容"""
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        sections = [f"# 📊 盘前技术分析报告\n> {date_str}\n"]

        # ── 恐慌 / 情绪指数区块（置于报告最前）──
        fear_lines = []

        # VIX
        if sentiment.vix > 0:
            if sentiment.vix >= 40:
                vix_status = "🔴 极端恐慌"
            elif sentiment.vix >= 30:
                vix_status = "🟠 市场紧张"
            else:
                vix_status = "🟢 常态"
            vix_chg = f" ({sentiment.vix_change_pct:+.1f}%)" if sentiment.vix_change_pct != 0 else ""
            fear_lines.append(f"  VIX 恐慌指数: **{sentiment.vix:.2f}**{vix_chg} {vix_status}")
        else:
            fear_lines.append("  VIX 恐慌指数: 暂无数据")

        # VXN
        if sentiment.vxn > 0:
            if sentiment.vxn >= 40:
                vxn_status = "🔴 科技股恐慌"
            elif sentiment.vxn >= 30:
                vxn_status = "🟠 偏高"
            else:
                vxn_status = "🟢 常态"
            vxn_chg = f" ({sentiment.vxn_change_pct:+.1f}%)" if sentiment.vxn_change_pct != 0 else ""
            fear_lines.append(f"  纳斯达克 VXN: **{sentiment.vxn:.2f}**{vxn_chg} {vxn_status}")
        else:
            fear_lines.append("  纳斯达克 VXN: 暂无数据")

        # OVX
        if sentiment.ovx > 0:
            if sentiment.ovx >= 60:
                ovx_status = "🔴 极高波动"
            elif sentiment.ovx >= 40:
                ovx_status = "🟠 偏高"
            else:
                ovx_status = "🟢 常态"
            ovx_chg = f" ({sentiment.ovx_change_pct:+.1f}%)" if sentiment.ovx_change_pct != 0 else ""
            fear_lines.append(f"  原油 OVX: **{sentiment.ovx:.2f}**{ovx_chg} {ovx_status}")
        else:
            fear_lines.append("  原油 OVX: 暂无数据")

        # 韭圈儿恐贪指数
        if sentiment.fear_greed >= 0:
            fg = sentiment.fear_greed
            if fg >= 80:
                fg_icon = "🔴"
            elif fg >= 60:
                fg_icon = "🟠"
            elif fg >= 40:
                fg_icon = "🟡"
            elif fg >= 20:
                fg_icon = "🟢"
            else:
                fg_icon = "🔵"
            label = sentiment.fear_greed_label or ""
            fear_lines.append(f"  韭圈儿恐贪指数: **{fg}** {fg_icon} {label}")
        else:
            fear_lines.append("  韭圈儿恐贪指数: 暂无数据")

        sections.append("### 🌡️ 全球恐慌 / 情绪指数")
        sections.append("\n".join(fear_lines))
        sections.append("\n")

        # ── 市场环境概览 ──
        env_parts = []
        if sentiment.gold_price > 0:
            gold_icon = "↑" if sentiment.gold_change_pct > 0 else "↓"
            env_parts.append(f"黄金 ${sentiment.gold_price:.0f}{gold_icon}")
        if sentiment.north_flow != 0:
            flow_icon = "+" if sentiment.north_flow > 0 else ""
            env_parts.append(f"北向 {flow_icon}{sentiment.north_flow:.1f}亿")
        if sentiment.up_count > 0 or sentiment.down_count > 0:
            env_parts.append(f"涨{sentiment.up_count}/跌{sentiment.down_count}")

        if env_parts:
            sections.append(f"🌏 **市场环境**: {' | '.join(env_parts)}\n")

        sections.append("---\n")

        # 按评分排序（从高到低）
        reports.sort(key=lambda r: r.score, reverse=True)

        for report in reports:
            sections.append(TechnicalAnalyzer.format_report(report))
            sections.append("\n---\n")

        return "\n".join(sections)

    # ------------------------------------------------------------------
    #  盘中监控
    # ------------------------------------------------------------------

    def _intraday_monitor(self):
        """盘中实时监控循环"""
        logger.info("=== 进入盘中监控循环 ===")
        logger.info(f"扫描间隔: {ALERT_SCAN_INTERVAL} 秒")
        logger.info(f"信号冷却: {ALERT_SIGNAL_COOLDOWN} 秒")

        try:
            while True:
                now = datetime.now()
                current_time = now.strftime("%H:%M")

                # 判断是否在交易时间内
                a_share_active = self._is_a_share_trading_time(now)
                hk_active = self._is_hk_trading_time(now)

                if not a_share_active and not hk_active:
                    # 如果 A 股和港股都不在交易时间
                    if now.hour >= 16:
                        logger.info("港股收盘，监控结束")
                        break
                    elif now.hour < 9 or (now.hour == 9 and now.minute < 30):
                        logger.debug("等待开盘...")
                        time.sleep(30)
                        continue
                    else:
                        # 午休等
                        logger.debug(f"非交易时段 ({current_time})")
                        time.sleep(30)
                        continue

                # 确定本轮需要扫描的标的
                scan_symbols = self._get_active_symbols(a_share_active, hk_active)

                if scan_symbols:
                    self._scan_cycle(scan_symbols)

                time.sleep(ALERT_SCAN_INTERVAL)

        except KeyboardInterrupt:
            logger.info("收到退出信号，监控器停止")

    def _scan_cycle(self, symbols: list[str]):
        """单次扫描周期"""
        # 获取实时行情
        quotes = self._data_service.fetch_realtime_quotes(symbols)

        all_signals = []

        for symbol in symbols:
            quote = quotes.get(symbol)
            if not quote or not quote.is_valid:
                continue

            klines = self._klines_cache.get(symbol)
            if klines is None:
                continue

            cfg = STOCK_ALERT_SYMBOLS.get(symbol, {})

            # 生成技术报告
            report = self._analyzer.analyze(
                symbol=symbol,
                name=cfg.get("name", ""),
                klines=klines,
                current_price=quote.price,
                current_volume=quote.volume,
                prev_close=quote.prev_close,
            )

            if not report:
                continue

            # 检测信号
            prev_report = self._prev_reports.get(symbol)
            signals = self._analyzer.detect_trade_signals(report, prev_report)

            # 更新存储
            self._prev_reports[symbol] = report

            # 过滤冷却中的信号
            for signal in signals:
                if not self._is_signal_cooling(signal):
                    all_signals.append(signal)
                    self._update_signal_cooldown(signal)

        # 推送信号
        if all_signals:
            self._push_signals(all_signals)

    def _push_signals(self, signals: list[AlertSignal]):
        """推送交易信号"""
        for signal in signals:
            title = TechnicalAnalyzer.format_signal_title(signal)
            content = TechnicalAnalyzer.format_signal(signal)
            logger.info(f"[信号] {signal.signal_type} {signal.symbol} {signal.name} @ {signal.price:.3f}")
            self._notifier.send(title, content)
            # 避免推送过快被限流
            time.sleep(1)

    # ------------------------------------------------------------------
    #  辅助方法
    # ------------------------------------------------------------------

    def _is_a_share_trading_time(self, now: datetime) -> bool:
        """判断当前是否为 A 股交易时间"""
        if now.weekday() >= 5:
            return False
        t = now.hour * 100 + now.minute
        return (930 <= t <= 1130) or (1300 <= t <= 1500)

    def _is_hk_trading_time(self, now: datetime) -> bool:
        """判断当前是否为港股交易时间"""
        if now.weekday() >= 5:
            return False
        t = now.hour * 100 + now.minute
        # 港股: 09:30-12:00, 13:00-16:00
        return (930 <= t <= 1200) or (1300 <= t <= 1600)

    def _get_active_symbols(self, a_share_active: bool, hk_active: bool) -> list[str]:
        """获取当前时段应监控的标的列表"""
        result = []
        for symbol, cfg in STOCK_ALERT_SYMBOLS.items():
            sym_type = cfg.get("type", "stock")
            if sym_type == "hk_stock" and hk_active:
                result.append(symbol)
            elif sym_type != "hk_stock" and a_share_active:
                result.append(symbol)
        return result

    def _is_signal_cooling(self, signal: AlertSignal) -> bool:
        """检查信号是否在冷却期。如果是相同类型的信号，但触发原因不同，则不冷却（立即推送）。"""
        key = f"{signal.symbol}_{signal.signal_type}"
        if key not in self._signal_cooldown:
            return False
            
        last_time, last_reason = self._signal_cooldown[key]
        
        # 如果原因不同，说明情况有变，不冷却
        if last_reason != signal.reason:
            logger.debug(f"[{signal.symbol}] {signal.signal_type} 触发新原因: {signal.reason} (原: {last_reason}) -> 绕过冷却")
            return False
            
        return (time.time() - last_time) < ALERT_SIGNAL_COOLDOWN

    def _update_signal_cooldown(self, signal: AlertSignal):
        """更新信号冷却时间和原因"""
        key = f"{signal.symbol}_{signal.signal_type}"
        self._signal_cooldown[key] = (time.time(), signal.reason)

    @staticmethod
    def _setup_logger():
        """设置日志"""
        logger.remove()
        logger.add(
            "logs/stock_alert_{time:YYYY-MM-DD}.log",
            rotation="00:00",
            retention="30 days",
            level="INFO",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        )
        logger.add(
            sys.stdout,
            format="<g>{time:HH:mm:ss}</g> | <lvl>{level: <8}</lvl> | <lvl>{message}</lvl>",
        )


# ------------------------------------------------------------------
#  入口
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="个股技术指标监控与推送")
    parser.add_argument(
        "--premarket", action="store_true",
        help="仅运行盘前报告"
    )
    parser.add_argument(
        "--intraday", action="store_true",
        help="仅运行盘中监控"
    )
    args = parser.parse_args()

    monitor = StockAlertMonitor()

    if args.premarket:
        monitor.run("premarket")
    elif args.intraday:
        monitor.run("intraday")
    else:
        monitor.run("full")


if __name__ == "__main__":
    main()
