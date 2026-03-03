
import sqlite3
import pandas as pd
from datetime import datetime

def check_data_integrity(db_path="data/trades.db"):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    print("=== 开始数据完整性校验 (backtest 模式) ===")
    
    # 1. 检查交易价格与快照价格是否匹配
    query = """
    SELECT 
        t.timestamp, 
        t.etf_code, 
        t.price as trade_price, 
        s.price as snapshot_price,
        ABS(t.price - s.price) as diff
    FROM trades t
    JOIN market_snapshots s ON t.timestamp = s.timestamp AND t.etf_code = s.etf_code AND t.mode = s.mode
    WHERE t.mode = 'backtest'
    """
    trades_vs_snapshots = pd.read_sql_query(query, conn)
    
    integrity_issues = []
    
    if len(trades_vs_snapshots) == 0:
        print("警告: 未在 trades 和 market_snapshots 中找到匹配记录。")
    else:
        mismatches = trades_vs_snapshots[trades_vs_snapshots['diff'] > 1e-6]
        if not mismatches.empty:
            print(f"❌ 发现 {len(mismatches)} 笔交易的价格与当时快照价格不匹配!")
            print(mismatches.head())
            integrity_issues.append("Trade price mismatch with snapshot")
        else:
            print("✅ 交易价格与快照价格完全一致。")

    # 2. 检查同一时间点不同 ETF 的价格是否异常重复 (Scoping Bug 检查)
    query = """
    SELECT timestamp, COUNT(DISTINCT price) as unique_prices, COUNT(*) as total_records
    FROM market_snapshots
    WHERE mode = 'backtest'
    GROUP BY timestamp
    HAVING total_records > 1 AND unique_prices < total_records
    """
    duplicate_prices = pd.read_sql_query(query, conn)
    
    if not duplicate_prices.empty:
        # 注意：有时候价格相同确实是巧合（比如涨跌停或极低价位），但如果是多个高价标的一模一样就不对
        print(f"⚠️ 发现 {len(duplicate_prices)} 个时间点存在不同标的价格相同。")
        # 进一步核实
        for _, row in duplicate_prices.head().iterrows():
            ts = row['timestamp']
            details = pd.read_sql_query(f"SELECT etf_code, price FROM market_snapshots WHERE mode='backtest' AND timestamp='{ts}'", conn)
            print(f"时间: {ts}")
            print(details)
            # 如果价格相同且不是涨跌停且标的代码不同，则标记为疑似 Bug
            if len(details['price'].unique()) == 1 and len(details) > 2:
                integrity_issues.append("Potential variable leakage (all ETFs same price)")
    else:
        print("✅ 同一时间点不同标的价格分布正常。")

    # 3. 检查快照价格分布是否异常 (如全为 0 或 NaN)
    query = "SELECT count(*) FROM market_snapshots WHERE mode = 'backtest' AND (price <= 0 OR price IS NULL)"
    bad_snapshots = conn.execute(query).fetchone()[0]
    if bad_snapshots > 0:
        print(f"❌ 发现 {bad_snapshots} 条异常行情快照（价格为 0 或空）!")
        integrity_issues.append("Bad snapshot values")
    else:
        print("✅ 行情快照数值合法。")

    # 4. 检查盈亏计算是否一致
    query = "SELECT * FROM trades WHERE mode = 'backtest' AND side = 'SELL'"
    sells = pd.read_sql_query(query, conn)
    if not sells.empty:
        # 这里逻辑较复杂，需要追溯买入价。暂时检查记录中是否存在 pnl
        if sells['pnl'].isnull().any():
             print("❌ 部分平仓记录没有盈亏数值。")
             integrity_issues.append("Missing PnL data")
        else:
             print("✅ 平仓记录盈亏数值完整。")

    conn.close()
    
    if not integrity_issues:
        print("\n🎉 结论: 数据完整性交叉验证通过！")
        return True
    else:
        print(f"\n❌ 结论: 数据存在 integrity 风险: {', '.join(integrity_issues)}")
        return False

if __name__ == "__main__":
    check_data_integrity()
