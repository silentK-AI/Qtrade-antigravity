import sys
import os
import pandas as pd
from datetime import datetime

# 把项目根目录加到 sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from config.settings import STOCK_ALERT_SYMBOLS
from data.stock_data_service import StockDataService
from strategy.technical_analyzer import TechnicalAnalyzer

def get_detailed_logs(symbols: list[str], test_days: int = 60, warmup_days: int = 60, shares: int = 200):
    data_service = StockDataService()
    analyzer = TechnicalAnalyzer()
    
    all_trades = []

    for symbol in symbols:
        cfg = STOCK_ALERT_SYMBOLS.get(symbol, {})
        name = cfg.get("name", symbol)
        
        df = data_service.fetch_history_klines(symbol, days=test_days + warmup_days)
        if df is None: continue

        position = 0
        entry_price = 0.0
        entry_date = None

        for r_idx in range(warmup_days, len(df) - 1):
            hist_df = df.iloc[:r_idx+1].copy()
            prev_hist_df = df.iloc[:r_idx].copy()
            
            report = analyzer.analyze(symbol, name, hist_df, df.iloc[r_idx]["close"], df.iloc[r_idx]["volume"], df.iloc[r_idx-1]["close"])
            prev_report = analyzer.analyze(symbol, name, prev_hist_df, df.iloc[r_idx-1]["close"], df.iloc[r_idx-1]["volume"], df.iloc[r_idx-2]["close"] if r_idx > 1 else 0)
            
            if not report: continue
            
            signals = analyzer.detect_trade_signals(report, prev_report)
            next_day = df.iloc[r_idx+1]
            
            # Exit
            if position > 0 and any(s.signal_type in ("TAKE_PROFIT", "STOP_LOSS") for s in signals):
                pnl = (next_day["open"] - entry_price) * position
                all_trades.append({
                    "代码": symbol, "名称": name,
                    "买入日期": entry_date, "买入价格": f"{entry_price:.2f}",
                    "卖出日期": next_day["date"], "卖出价格": f"{next_day['open']:.2f}",
                    "盈亏": f"{pnl:.2f}"
                })
                position = 0
            
            # Entry
            if position == 0 and any(s.signal_type == "BUY" for s in signals):
                position = shares
                entry_price = next_day["open"]
                entry_date = next_day["date"]

        if position > 0:
            last_day = df.iloc[-1]
            pnl = (last_day["close"] - entry_price) * position
            all_trades.append({
                "代码": symbol, "名称": name,
                "买入日期": entry_date, "买入价格": f"{entry_price:.2f}",
                "卖出日期": last_day["date"], "卖出价格": f"{last_day['close']:.2f} (强制)",
                "盈亏": f"{pnl:.2f}"
            })

    print(pd.DataFrame(all_trades).to_markdown(index=False))

if __name__ == "__main__":
    top_4 = ['603667', '000977', '002230', '000559']
    get_detailed_logs(top_4)
