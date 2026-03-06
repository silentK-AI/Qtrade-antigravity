import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from loguru import logger

# 把项目根目录加到 sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from config.settings import STOCK_ALERT_SYMBOLS
from data.stock_data_service import StockDataService
from strategy.technical_analyzer import TechnicalAnalyzer

def run_backtest(symbols: list[str], test_days: int = 60, warmup_days: int = 60, shares: int = 200):
    """
    针对技术指标信号进行回测。

    回测逻辑：
    - 每天收盘后运行分析，生成信号
    - BUY 信号：次日开盘买入固定股数
    - TAKE_PROFIT / STOP_LOSS 信号：次日开盘卖出全部持仓
    """
    data_service = StockDataService()
    analyzer = TechnicalAnalyzer()

    total_pnl = 0.0
    total_trades = 0
    winning_trades = 0

    results = []

    logger.info(f"开始回测: {len(symbols)} 只标的, 近 {test_days} 天, 每次交易 {shares} 股")
    logger.info("-" * 50)

    for symbol in symbols:
        cfg = STOCK_ALERT_SYMBOLS.get(symbol, {})
        name = cfg.get("name", symbol)

        # 获取历史数据
        total_days = test_days + warmup_days
        df = data_service.fetch_history_klines(symbol, days=total_days)
        if df is None or len(df) < warmup_days + 10:
            logger.warning(f"[{symbol}] 数据不足，跳过回测")
            continue

        symbol_pnl = 0.0
        symbol_trades = 0
        symbol_wins = 0

        position = 0        # 持股数
        entry_price = 0.0   # 入场价
        entry_date = None

        # 遍历回测区间
        # 从 warmup_days 开始，步进模拟每一交易日
        for i in range(warmup_days, len(df) - 1):
            # 1. 截止到当日的历史 K 线数据
            hist_df = df.iloc[:i+1].copy()
            
            # 2. 运行分析
            report = analyzer.analyze(
                symbol=symbol,
                name=name,
                klines=hist_df,
                current_price=df.iloc[i]["close"],
                current_volume=df.iloc[i]["volume"],
                prev_close=df.iloc[i-1]["close"]
            )
            
            # 前一天的报告用于交叉检测
            prev_hist_df = df.iloc[:i].copy()
            prev_report = analyzer.analyze(
                symbol=symbol,
                name=name,
                klines=prev_hist_df,
                current_price=df.iloc[i-1]["close"],
                current_volume=df.iloc[i-1]["volume"],
                prev_close=df.iloc[i-2]["close"] if i > 1 else 0
            )

            if not report:
                continue

            signals = analyzer.detect_trade_signals(report, prev_report)

            # 3. 模拟日内逻辑 (简化版：次日开盘交易)
            next_open = df.iloc[i+1]["open"]
            next_date = df.iloc[i+1]["date"]

            # 处理退出信号
            exit_signal = any(s.signal_type in ("TAKE_PROFIT", "STOP_LOSS") for s in signals)
            if position > 0 and exit_signal:
                pnl = (next_open - entry_price) * position
                symbol_pnl += pnl
                symbol_trades += 1
                if pnl > 0:
                    symbol_wins += 1
                
                logger.debug(f"  [{symbol}] {next_date} 卖出 @ {next_open:.2f}, 盈亏: {pnl:.2f}")
                position = 0
                entry_price = 0.0

            # 处理入场信号
            buy_signal = any(s.signal_type == "BUY" for s in signals)
            if position == 0 and buy_signal:
                position = shares
                entry_price = next_open
                entry_date = next_date
                logger.debug(f"  [{symbol}] {next_date} 买入 @ {next_open:.2f}")

        # 如果结束时仍有持仓，按最后一天收盘价强制平仓
        if position > 0:
            last_price = df.iloc[-1]["close"]
            pnl = (last_price - entry_price) * position
            symbol_pnl += pnl
            symbol_trades += 1
            if pnl > 0:
                symbol_wins += 1
            logger.debug(f"  [{symbol}] 强制平仓 @ {last_price:.2f}, 盈亏: {pnl:.2f}")

        win_rate = (symbol_wins / symbol_trades * 100) if symbol_trades > 0 else 0
        results.append({
            "代码": symbol,
            "名称": name,
            "交易次数": symbol_trades,
            "胜率": f"{win_rate:.1f}%",
            "盈亏": round(symbol_pnl, 2)
        })

        total_pnl += symbol_pnl
        total_trades += symbol_trades
        winning_trades += symbol_wins

        logger.info(f"[{symbol} {name}] 完结: 交易 {symbol_trades} 次, 胜率 {win_rate:.1f}%, 总盈亏 {symbol_pnl:.2f}")

    # 输出统计报告
    logger.info("=" * 60)
    logger.info("回测汇总报告")
    logger.info("-" * 60)
    print(pd.DataFrame(results).to_markdown(index=False))
    logger.info("-" * 60)
    
    overall_win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    logger.info(f"总交易次数: {total_trades}")
    logger.info(f"总体胜率: {overall_win_rate:.1f}%")
    logger.info(f"总盈亏: ¥{total_pnl:.2f}")
    logger.info("=" * 60)

if __name__ == "__main__":
    symbols = list(STOCK_ALERT_SYMBOLS.keys())
    run_backtest(symbols)
