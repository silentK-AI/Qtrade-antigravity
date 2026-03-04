"""
ETF T+0 量化交易系统 - 主程序入口

支持模式:
  python main.py paper              # 模拟交易（全部标的）
  python main.py paper --etf 159941 # 模拟单个标的
  python main.py live               # 实盘交易（Phase 2）
  python main.py backtest           # 历史回测（Phase 3）
"""
import os
import sys
import time
import signal as os_signal
import argparse
from datetime import datetime, time as dtime
from loguru import logger

from monitor.logger import setup_logger
from config.settings import (
    ETF_UNIVERSE,
    ACTIVE_ETFS,
    MARKET_OPEN,
    MARKET_CLOSE,
    SCAN_INTERVAL,
    INITIAL_CAPITAL,
    ML_ENABLED,
    ML_MODEL_DIR,
)
from data.market_data import MarketDataService
from data.overnight_data import OvernightDataService
from strategy.futures_etf_arb import FuturesETFArbStrategy
from strategy.ml_price_strategy import MLPriceStrategy
from strategy.composite_strategy import CompositeStrategy
from strategy.ml_predictor import MLPredictor
from strategy.signal import SignalType, OrderSide, TradeOrder
from risk.position_manager import PositionManager
from risk.risk_manager import RiskManager
from trader.mock_trader import MockTrader
from trader.base_trader import BaseTrader
from monitor.trade_store import TradeStore


class TradingEngine:
    """T+0 交易引擎 - 管理完整的交易主循环"""

    def __init__(
        self,
        mode: str = "paper",
        etf_codes: list[str] | None = None,
        initial_capital: float = INITIAL_CAPITAL,
    ):
        self._mode = mode
        self._etf_codes = etf_codes or ACTIVE_ETFS
        self._running = False

        # 初始化各模块
        self._data_service = MarketDataService()
        self._overnight_service = OvernightDataService()

        # 构建策略映射: {etf_code: StrategyInstance}
        self._strategy_map = {}

        # ML 策略初始化（主策略）
        self._ml_predictor = None
        self._ml_strategy = None
        if ML_ENABLED:
            self._ml_predictor = MLPredictor(model_dir=ML_MODEL_DIR)
            missing_codes = [c for c in self._etf_codes if not self._ml_predictor.has_model(c)]
            if missing_codes:
                logger.info(f"检测到 {len(missing_codes)} 个标的缺失 ML 模型，开始自动训练: {missing_codes}")
                self._auto_train_models(missing_codes)

            loaded = self._ml_predictor.load_all_models(self._etf_codes)
            if loaded > 0:
                self._ml_strategy = MLPriceStrategy(self._ml_predictor)
                logger.info(f"ML策略已启用: {loaded}/{len(self._etf_codes)} 个标的有模型")
            else:
                logger.warning("ML策略: 无可用模型，回退到传统策略")
        else:
            logger.info("ML策略已禁用 (ML_ENABLED=false)")

        # 回退策略（ML 不可用时使用）
        from strategy.vwap_reversion_strategy import VWAPReversionStrategy
        fallback_strategy = FuturesETFArbStrategy()

        # 为每个标的分配策略
        for code in self._etf_codes:
            if self._ml_strategy and self._ml_predictor.has_model(code):
                # ML 主策略（独立使用，不再用 CompositeStrategy 包裹）
                self._strategy_map[code] = self._ml_strategy
                logger.info(f"[{code}] 策略: ML价格区间策略")
            else:
                # 回退到传统策略
                self._strategy_map[code] = fallback_strategy
                logger.info(f"[{code}] 策略: 传统策略 (无ML模型)")

        self._position_manager = PositionManager(initial_capital)
        self._risk_manager = RiskManager(self._position_manager)
        self._overnight_loaded = False

        # 交易数据持久化
        self._trade_store = TradeStore()
        self._position_manager.set_mode(mode)
        self._position_manager.set_store(self._trade_store)

        # 根据模式选择交易执行器
        if mode == "paper":
            self._trader: BaseTrader = MockTrader(self._position_manager)
        elif mode == "live":
            from trader.easytrader_ths import EasyTrader
            self._trader = EasyTrader(self._position_manager)
        else:
            raise ValueError(f"未知运行模式: {mode}")

        # 注册信号处理（优雅退出，仅在主线程生效）
        try:
            os_signal.signal(os_signal.SIGINT, self._handle_shutdown)
            os_signal.signal(os_signal.SIGTERM, self._handle_shutdown)
        except ValueError:
            pass  # 非主线程时跳过信号注册

    def _auto_train_models(self, codes: list[str]) -> None:
        """自动训练指定标的的 ML 模型"""
        from scripts.train_model import fetch_training_data
        from config.settings import ML_TRAINING_DAYS

        logger.info("=" * 40)
        logger.info(f"自动训练 ML 模型 ({len(codes)} 个标的)")
        logger.info("=" * 40)

        for code in codes:
            try:
                hist_df = fetch_training_data(code, days=ML_TRAINING_DAYS)
                if hist_df is not None and len(hist_df) >= 25:
                    self._ml_predictor.train(code, hist_df)
                else:
                    logger.warning(f"[{code}] 数据不足，跳过训练")
            except Exception as e:
                logger.warning(f"[{code}] 自动训练失败: {e}")

        logger.info("自动训练过程完成")


    def run(self) -> None:
        """启动交易主循环"""
        logger.info("=" * 60)
        logger.info("ETF T+0 量化交易系统启动")
        logger.info(f"运行模式: {self._mode}")
        logger.info(f"交易标的: {', '.join(self._etf_codes)}")
        logger.info(f"初始资金: {self._position_manager.total_assets:,.2f}")
        logger.info(f"扫描间隔: {SCAN_INTERVAL} 秒")
        logger.info("=" * 60)

        # 连接交易通道
        if not self._trader.connect():
            logger.error("交易通道连接失败，退出")
            return

        # 每日重置
        for strategy in self._strategy_map.values():
            strategy.reset()
        self._position_manager.reset_daily()
        self._overnight_service.reset_daily()
        self._overnight_loaded = False

        self._running = True
        scan_count = 0

        while self._running:
            try:
                now = datetime.now()
                current_time = now.time()

                # 检查是否在交易时段
                market_open = dtime.fromisoformat(MARKET_OPEN)
                market_close = dtime.fromisoformat(MARKET_CLOSE)

                if current_time < market_open:
                    if not self._overnight_loaded:
                        self._load_overnight_data()
                    if scan_count == 0:
                        logger.info(f"等待开盘（{MARKET_OPEN}）...")
                    time.sleep(10)
                    continue

                if current_time >= market_close:
                    logger.info("已收盘，交易日结束")
                    self._end_of_day_report()
                    break

                # 开盘后首次加载隔夜数据
                if not self._overnight_loaded:
                    self._load_overnight_data()

                # ===== 交易主循环 =====
                scan_count += 1
                self._trading_cycle(scan_count)

                # 每 60 次扫描（约 5 分钟）定期保存当日汇总到数据库，供 Dashboard 实时展示
                if scan_count % 60 == 0:
                    self._position_manager.save_daily_summary()
                    logger.debug("已保存周期性当日汇总")

                time.sleep(SCAN_INTERVAL)

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"主循环异常: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(SCAN_INTERVAL)

        self._shutdown()

    def _trading_cycle(self, scan_count: int) -> None:
        """单次交易扫描周期"""
        # 1. 获取全部标的行情快照
        snapshots = self._data_service.get_all_snapshots(self._etf_codes)
        if not snapshots:
            logger.warning("未获取到任何行情数据")
            return

        # 更新持仓价格
        price_map = {
            code: snap.etf_price
            for code, snap in snapshots.items()
            if snap.etf_price > 0
        }
        self._position_manager.update_prices(price_map)

        # 记录行情快照用于 Dashboard 实时展示
        for code, snap in snapshots.items():
            if snap.is_valid:
                self._trade_store.record_snapshot(
                    self._mode, code, snap.etf_price, snap.iopv, snap.futures_momentum
                )

        # 定期清理旧快照（保留更长时间以供全天查看）
        if scan_count % 100 == 0:
            self._trade_store.prune_snapshots(self._mode, keep_hours=16)

        # 2. 策略信号预读
        signals_map = {}
        for code in self._etf_codes:
            snapshot = snapshots.get(code)
            if snapshot is None or not snapshot.is_valid:
                continue
            
            # 从映射表中获取该标的的专属策略
            strategy = self._strategy_map.get(code)
            if strategy:
                signal = strategy.evaluate(snapshot)
                signals_map[code] = signal

        # 3. 风控检查 - 退出规则（含科学因子评价）
        exit_orders = self._risk_manager.check_exit_rules(snapshots, signals_map)
        for order in exit_orders:
            self._trader.execute(order)

        # 4. 过滤可操作信号并排序（按强度降序）
        signals = [s for s in signals_map.values() if s.is_actionable]
        signals.sort(key=lambda s: s.strength, reverse=True)

        # 5. 生成并执行交易指令
        for signal in signals:
            if signal.signal_type in (SignalType.BUY, SignalType.STRONG_BUY):
                # 买入信号 - 验证风控
                allowed, reason = self._risk_manager.validate_entry(signal)
                if not allowed:
                    logger.debug(f"[{signal.etf_code}] 开仓被拒: {reason}")
                    continue

                # 计算下单数量
                quantity = self._risk_manager.calc_order_quantity(signal)
                if quantity <= 0:
                    continue

                order = TradeOrder(
                    etf_code=signal.etf_code,
                    etf_name=signal.etf_name,
                    side=OrderSide.BUY,
                    price=signal.price,
                    quantity=quantity,
                    reason=signal.reason,
                )
                self._trader.execute(order)

            elif signal.signal_type in (SignalType.SELL, SignalType.STRONG_SELL):
                # 卖出信号 - 有持仓才卖
                if self._position_manager.has_position(signal.etf_code):
                    pos = self._position_manager.get_position(signal.etf_code)
                    order = TradeOrder(
                        etf_code=signal.etf_code,
                        etf_name=signal.etf_name,
                        side=OrderSide.SELL,
                        price=signal.price,
                        quantity=pos.quantity,
                        reason=signal.reason,
                    )
                    self._trader.execute(order)

        # 6. 定期输出状态
        if scan_count % 12 == 0:  # 每分钟左右（12 * 5秒 = 60秒）
            self._print_status(snapshots)

    def _print_status(self, snapshots: dict) -> None:
        """输出当前状态摘要"""
        summary = self._position_manager.get_summary()
        logger.info("-" * 50)
        logger.info(
            f"资产: {summary['total_assets']:,.2f} | "
            f"现金: {summary['cash']:,.2f} | "
            f"仓位: {summary['total_position_pct']} | "
            f"今日交易: {summary['total_trades_today']}笔"
        )
        for code, info in summary["positions"].items():
            logger.info(
                f"  [{code}] {info['name']} "
                f"{info['qty']}股 @ {info['avg_cost']:.4f} "
                f"-> {info['current']:.4f} "
                f"盈亏: {info['pnl']} ({info['pnl_pct']})"
            )

        # 显示关键行情
        for code in self._etf_codes[:3]:  # 只显示前3个
            snap = snapshots.get(code)
            if snap and snap.is_valid:
                logger.info(
                    f"  [{code}] {snap.etf_name} "
                    f"价格={snap.etf_price:.4f} "
                    f"IOPV={snap.iopv:.4f} "
                    f"溢价率={snap.premium_rate * 100:+.2f}% "
                    f"动量={snap.futures_momentum * 100:+.3f}%"
                )
        logger.info("-" * 50)

    def _end_of_day_report(self) -> None:
        """交易日结束报告"""
        summary = self._position_manager.get_summary()
        trades = self._position_manager.get_trade_history()

        logger.info("=" * 60)
        logger.info("交易日结束报告")
        logger.info("=" * 60)
        logger.info(f"最终资产: {summary['total_assets']:,.2f}")
        logger.info(f"现金余额: {summary['cash']:,.2f}")
        logger.info(f"今日交易: {summary['total_trades_today']} 笔")

        if trades:
            logger.info("\n今日交易记录:")
            for t in trades:
                logger.info(
                    f"  {t['timestamp'][:19]} | "
                    f"{t['side']:4s} {t['etf_code']} {t['etf_name']} "
                    f"{t['quantity']}股 @ {t['price']:.4f} "
                    f"金额={t['amount']:,.2f}"
                )

        pnl = summary["total_assets"] - INITIAL_CAPITAL
        logger.info(f"\n累计盈亏: {pnl:+,.2f}")
        logger.info("=" * 60)

        # 保存每日汇总到数据库
        self._position_manager.save_daily_summary()

    def _handle_shutdown(self, signum, frame) -> None:
        """处理关闭信号"""
        logger.info("收到关闭信号，正在优雅退出...")
        self._running = False

    def _load_overnight_data(self) -> None:
        """加载隔夜行情数据并传递给策略引擎"""
        logger.info("正在获取隔夜行情数据...")
        overnight_map = self._overnight_service.get_all_overnight_info()

        # 遍历所有包含 FuturesETFArbStrategy 的策略实例
        for code, strategy in self._strategy_map.items():
            target_arb = None
            if isinstance(strategy, FuturesETFArbStrategy):
                target_arb = strategy
            elif isinstance(strategy, CompositeStrategy):
                target_arb = strategy.get_strategy(FuturesETFArbStrategy)
            
            if target_arb:
                target_arb.set_overnight_data(overnight_map or {})

        if overnight_map:
            logger.info(f"隔夜数据加载完成: {len(overnight_map)} 个标的")
        else:
            logger.warning("未获取到隔夜数据，策略将仅依赖日内信号")

        # ML 策略：生成当日预测
        if self._ml_predictor and self._ml_strategy:
            self._generate_ml_predictions(overnight_map or {})

        self._overnight_loaded = True

    def _generate_ml_predictions(self, overnight_map: dict) -> None:
        """使用 ML 模型生成当日价格预测"""
        from strategy.ml_predictor import PricePrediction
        predictions = {}

        for code in self._etf_codes:
            if not self._ml_predictor.has_model(code):
                continue

            try:
                # 获取最近 30 天历史数据用于特征构建
                hist_df = self._fetch_recent_history(code, days=30)
                if hist_df is None or len(hist_df) < 20:
                    logger.debug(f"[{code}] 历史数据不足，跳过ML预测")
                    continue

                overnight_info = overnight_map.get(code)
                pred = self._ml_predictor.predict(code, overnight_info, hist_df)
                if pred:
                    # 预测是相对比率，转为绝对价格
                    last_close = float(hist_df.iloc[-1]["收盘"])
                    pred.predicted_high *= last_close
                    pred.predicted_low *= last_close
                    predictions[code] = pred

            except Exception as e:
                logger.debug(f"[{code}] ML预测生成失败: {e}")

        if predictions:
            self._ml_strategy.set_daily_predictions(predictions)
            logger.info(f"ML预测完成: {len(predictions)} 个标的")

    def _fetch_recent_history(self, etf_code: str, days: int = 30):
        """获取最近 N 天历史数据（使用直连 EM API，绕过代理）"""
        try:
            import requests
            import pandas as pd
            from datetime import timedelta
            from config.settings import ETF_UNIVERSE

            # 计算日期范围
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=days + 15)).strftime("%Y%m%d")

            # 使用新浪 API 替代东财
            exchange = ETF_UNIVERSE.get(etf_code, {}).get("exchange", "SH").lower()
            symbol = f"{exchange}{etf_code}"
            
            # 获取日线数据 (scale=240)
            api_url = (
                f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
                f"CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen=30"
            )

            s = requests.Session()
            s.trust_env = False
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://finance.sina.com.cn"
            }
            
            resp = s.get(api_url, headers=headers, timeout=10)
            import json
            text = resp.text.strip()
            if not text or text == "null":
                return None
                
            data_list = json.loads(text)
            if not data_list:
                return None
                
            df = pd.DataFrame(data_list)
            df = df.rename(columns={
                "day": "date",
                "open": "开盘",
                "high": "最高",
                "low": "最低",
                "close": "收盘",
                "volume": "成交量"
            })
            for col in ["开盘", "最高", "最低", "收盘", "成交量"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            
            if "成交额" not in df.columns:
                df["成交额"] = df["成交量"] * df["收盘"]
            
            return df.tail(days)

        except Exception as e:
            logger.debug(f"[{etf_code}] 获取历史数据失败: {e}")
            return None

        except Exception as e:
            logger.debug(f"[{etf_code}] 获取历史数据失败: {e}")
            return None

    def _shutdown(self) -> None:
        """关闭引擎"""
        logger.info("正在关闭交易引擎...")
        self._trader.disconnect()
        self._end_of_day_report()
        logger.info("交易引擎已关闭")


def main():
    """入口函数"""
    parser = argparse.ArgumentParser(
        description="ETF T+0 量化交易系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py paper              # 模拟交易（全部 7 个 ETF）
  python main.py paper --etf 159941 # 仅模拟纳指 ETF
  python main.py backtest           # 历史回测
  python main.py dashboard          # 启动监控后台
        """,
    )

    parser.add_argument(
        "mode",
        choices=["paper", "live", "backtest", "dashboard", "train"],
        help="运行模式: paper(模拟) / live(实盘) / backtest(回测) / dashboard(监控后台) / train(训练ML模型)",
    )
    parser.add_argument(
        "--etf",
        nargs="+",
        default=None,
        help="指定交易标的（ETF代码），不指定则使用全部标的",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=INITIAL_CAPITAL,
        help=f"初始资金（默认 {INITIAL_CAPITAL:,.0f}）",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="回测天数（默认 30 天）",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="回测开始日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="回测结束日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8088,
        help="Dashboard 端口（默认 8088）",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="清空所有历史交易数据和汇总（删除 trades.db）",
    )

    args = parser.parse_args()

    # 初始化日志
    setup_logger()

    # 处理数据重置
    if args.reset:
        from monitor.trade_store import DB_PATH
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
            logger.info(f"已清空所有交易数据: {DB_PATH}")
        else:
            logger.info("交易数据库不存在，无需清空")

    # 验证标的
    etf_codes = args.etf
    if etf_codes:
        for code in etf_codes:
            if code not in ETF_UNIVERSE:
                logger.error(f"未知标的: {code}")
                logger.info(f"支持的标的: {list(ETF_UNIVERSE.keys())}")
                sys.exit(1)

    if args.mode == "dashboard":
        from monitor.dashboard import run_dashboard
        run_dashboard(port=args.port)
        sys.exit(0)

    if args.mode == "backtest":
        from backtest.backtester import run_backtest
        run_backtest(
            etf_codes=etf_codes,
            initial_capital=args.capital,
            start_date=args.start_date,
            end_date=args.end_date,
            days=args.days
        )
        sys.exit(0)

    if args.mode == "train":
        from scripts.train_model import run_training
        run_training(etf_codes=etf_codes, days=args.days)
        sys.exit(0)

    # 启动引擎
    engine = TradingEngine(
        mode=args.mode,
        etf_codes=etf_codes,
        initial_capital=args.capital,
    )
    engine.run()


if __name__ == "__main__":
    main()
