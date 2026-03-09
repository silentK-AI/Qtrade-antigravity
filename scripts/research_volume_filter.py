import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime
from loguru import logger

# 把项目根目录加到 sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from config.etf_settings import STOCK_ALERT_SYMBOLS
from data.stock_data_service import StockDataService
from strategy.technical_analyzer import TechnicalAnalyzer

def run_comparative_backtest(symbols: list[str], test_days: int = 60, shares: int = 200):
    data_service = StockDataService()
    analyzer = TechnicalAnalyzer()
    
    results = []

    # 定义两种测试逻辑
    # 1. Baseline: 原始逻辑
    # 2. Volume Filter: 买入信号必须满足量比 > 1.2
    
    for symbol in symbols:
        cfg = STOCK_ALERT_SYMBOLS.get(symbol, {})
        name = cfg.get("name", symbol)
        df = data_service.fetch_history_klines(symbol, days=test_days + 60)
        if df is None or len(df) < 70: continue

        for mode in ['Baseline', 'VolumeFilter']:
            symbol_pnl = 0.0
            symbol_trades = 0
            symbol_wins = 0
            position = 0
            entry_price = 0.0

            for i in range(60, len(df) - 1):
                hist_df = df.iloc[:i+1].copy()
                prev_hist_df = df.iloc[:i].copy()
                
                report = analyzer.analyze(symbol, name, hist_df, df.iloc[i]["close"], df.iloc[i]["volume"], df.iloc[i-1]["close"])
                prev_report = analyzer.analyze(symbol, name, prev_hist_df, df.iloc[i-1]["close"], df.iloc[i-1]["volume"], df.iloc[i-2]["close"] if i > 1 else 0)
                
                if not report: continue
                
                signals = analyzer.detect_trade_signals(report, prev_report)
                
                # Volume Filter 门槛
                if mode == 'VolumeFilter':
                    # 只过滤买入信号
                    signals = [s for s in signals if s.signal_type != "BUY" or report.volume_ratio >= 1.2]

                next_open = df.iloc[i+1]["open"]
                
                # Exit
                if position > 0 and any(s.signal_type in ("TAKE_PROFIT", "STOP_LOSS") for s in signals):
                    pnl = (next_open - entry_price) * position
                    symbol_pnl += pnl
                    symbol_trades += 1
                    if pnl > 0: symbol_wins += 1
                    position = 0
                
                # Entry
                if position == 0 and any(s.signal_type == "BUY" for s in signals):
                    position = shares
                    entry_price = next_open

            if position > 0:
                last_price = df.iloc[-1]["close"]
                pnl = (last_price - entry_price) * position
                symbol_pnl += pnl
                symbol_trades += 1
                if pnl > 0: symbol_wins += 1

            results.append({
                "Mode": mode,
                "Symbol": symbol,
                "Name": name,
                "Trades": symbol_trades,
                "WinRate": (symbol_wins / symbol_trades) if symbol_trades > 0 else 0,
                "PnL": symbol_pnl
            })

    summary = pd.DataFrame(results)
    final_report = summary.groupby('Mode').agg({
        'Trades': 'sum',
        'WinRate': 'mean',
        'PnL': 'sum'
    })
    
    print("\n=== 策略对比汇总 (最近60天) ===")
    print(final_report.to_markdown())
    
    print("\n=== 单标的差异筛选 (仅显示盈亏变化) ===")
    pivot = summary.pivot(index='Symbol', columns='Mode', values='PnL')
    pivot['Diff'] = pivot['VolumeFilter'] - pivot['Baseline']
    print(pivot[pivot['Diff'] != 0].to_markdown())

if __name__ == "__main__":
    symbols = list(STOCK_ALERT_SYMBOLS.keys())
    run_comparative_backtest(symbols)
