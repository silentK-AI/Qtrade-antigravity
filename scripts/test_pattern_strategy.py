"""
规律策略回测系统 (版本 2.0) - 基于“信号触发”原因进行验证。
逻辑：
1. 从数据库读取所有已记录的行情快照 (market_snapshots)。
2. 筛选符合“原因”(Details of cause) 的时刻：
    - 期货动量 (futures_momentum) >= 0.15%
    - 溢价率 (premium_rate) <= -0.3% (即折价 0.3% 以上)
3. 统计这些时刻之后的盈亏表现（持有 30 分钟）。
"""
import sys
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from loguru import logger

# 路径修复
sys.path.append('.')

DB_PATH = 'data/trades.db'

def run_pattern_analysis_v2():
    logger.info("开始执行规律模式回测 (V2 - 信号触发触发)...")
    
    conn = sqlite3.connect(DB_PATH)
    # 读取所有快照
    df = pd.read_sql_query("SELECT * FROM market_snapshots WHERE mode = 'backtest' ORDER BY timestamp ASC", conn)
    conn.close()
    
    if df.empty:
        logger.error("数据库为空，请先运行回测生成快照数据")
        return

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # 定义触发条件 (按用户成功的细节动因)
    MOMENTUM_THRESHOLD = 0.0015 # 0.15%
    DISCOUNT_THRESHOLD = -0.003 # -0.3% (折价)
    
    results = []
    
    # 按标的分组分析
    for code in df['etf_code'].unique():
        etf_df = df[df['etf_code'] == code].copy()
        etf_df = etf_df.sort_values('timestamp')
        
        # 计算溢价率 (数据库中只有 price 和 iopv)
        etf_df['premium_rate'] = (etf_df['price'] - etf_df['iopv']) / etf_df['iopv']
        
        trades = []
        for i in range(len(etf_df)):
            row = etf_df.iloc[i]
            
            # 检查触发信号 (Details of Cause)
            if row['momentum'] >= MOMENTUM_THRESHOLD and row['premium_rate'] <= DISCOUNT_THRESHOLD:
                buy_price = row['price']
                buy_time = row['timestamp']
                
                # 寻找 30 分钟后的价格 (或最近的下一条记录)
                target_time = buy_time + timedelta(minutes=30)
                future_rows = etf_df[etf_df['timestamp'] >= target_time]
                
                if future_rows.empty:
                    continue # 接近收盘，跳过
                
                sell_row = future_rows.iloc[0]
                sell_price = sell_row['price']
                
                pnl_pct = (sell_price - buy_price) / buy_price * 100
                
                trades.append({
                    "timestamp": buy_time,
                    "momentum": row['momentum'],
                    "premium": row['premium_rate'],
                    "pnl_pct": pnl_pct
                })
                
                # 跳过 30 分钟内的快照，避免同一个信号点重复触发多次
                # 我们寻找下一个 buy_time 之后的索引
                while i + 1 < len(etf_df) and etf_df.iloc[i+1]['timestamp'] < target_time:
                    i += 1
        
        if trades:
            trade_df = pd.DataFrame(trades)
            avg_pnl = trade_df['pnl_pct'].mean()
            win_rate = (trade_df['pnl_pct'] > 0).mean() * 100
            
            results.append({
                "code": code,
                "trades": len(trade_df),
                "avg_pnl": avg_pnl,
                "win_rate": win_rate,
                "total_ret": trade_df['pnl_pct'].sum()
            })
            logger.info(f"[{code}] 触发 {len(trade_df)} 次 | 胜率 {win_rate:.1f}% | 平均收益 {avg_pnl:.3f}%")

    if results:
        res_df = pd.DataFrame(results).sort_values("total_ret", ascending=False)
        print("\n" + "="*80)
        print("『细节驱动模式回测』(期货强动量 + ETF 深度折价)")
        print(f"触发阈值: 动量 >= {MOMENTUM_THRESHOLD*100:.2f}%, 溢价率 <= {DISCOUNT_THRESHOLD*100:.2f}%")
        print("="*80)
        print(res_df.to_string(index=False))
        print("="*80)
        print(f"模式平均胜率: {res_df['win_rate'].mean():.1f}%")
        print(f"模式平均单笔收益: {res_df['avg_pnl'].mean():.3f}%")
        print(f"该模式在历史数据中总共被触发了 {res_df['trades'].sum()} 次")
    else:
        logger.warning("在历史快照中未找到符合该‘强信号’组合的时刻")

if __name__ == "__main__":
    run_pattern_analysis_v2()
