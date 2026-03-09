"""
PP + ML 混合策略以及严格 PP 回测

验证在真实日内路径约束下：
1. 精确在 S1 成交的胜率
2. 选择性在 PP 卖出的胜率（考虑高低点先后顺序）
3. ML 预测作为过滤器的能力
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from loguru import logger

from config.etf_settings import ETF_UNIVERSE, ACTIVE_ETFS
from scripts.train_model import fetch_training_data
from strategy.ml_predictor import MLPredictor

logger.remove()
logger.add(sys.stderr, level="WARNING")


def calc_pivot_points(high: float, low: float, close: float) -> dict:
    pp = (high + low + close) / 3
    r1 = 2 * pp - low
    s1 = 2 * pp - high
    r2 = pp + (high - low)
    s2 = pp - (high - low)
    return {"PP": pp, "R1": r1, "R2": r2, "S1": s1, "S2": s2}


def analyze_mixed_strategy(code: str, df: pd.DataFrame, train_days=150) -> dict:
    name = ETF_UNIVERSE.get(code, {}).get("name", code)

    for col in ["开盘", "最高", "最低", "收盘"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        
    if len(df) < train_days + 15:
        return None

    # 1. 训练 ML 模型
    train_df = df.iloc[:train_days].copy()
    test_df = df.iloc[train_days:].copy()
    
    predictor = MLPredictor()
    ok = predictor.train(code, train_df)
    if not ok:
        return None

    results = {
        "code": code,
        "name": name,
        "test_days": len(test_df),
        "pp_trades": 0, "pp_wins": 0, "pp_pnl": 0.0,
        "mix_trades": 0, "mix_wins": 0, "mix_pnl": 0.0,
    }

    # 逐日测试
    for i in range(len(test_df)):
        abs_idx = train_days + i
        feature_df = df.iloc[:abs_idx].copy()
        
        prev = df.iloc[abs_idx - 1]
        today = df.iloc[abs_idx]

        prev_high = float(prev["最高"])
        prev_low = float(prev["最低"])
        prev_close = float(prev["收盘"])

        today_open = float(today["开盘"])
        today_high = float(today["最高"])
        today_low = float(today["最低"])
        today_close = float(today["收盘"])

        if any(v <= 0 for v in [prev_high, prev_low, prev_close, today_open, today_high, today_low]):
            continue

        pp = calc_pivot_points(prev_high, prev_low, prev_close)
        S1, PP = pp["S1"], pp["PP"]

        # --- ML 预测 ---
        pred_high_val, pred_low_val = 0, 0
        pred = predictor.predict(code, None, feature_df)
        if pred:
            pred_high_val = pred.predicted_high * prev_close
            pred_low_val = pred.predicted_low * prev_close

        # ==========================================
        # 1. 严格 PP 策略仿真
        # ==========================================
        pp_buy_price = 0
        pp_sell_price = 0
        pp_traded = False

        if today_low <= S1:
            pp_traded = True
            # 情况 A: 开盘就低于 S1，直接以开盘价买入
            if today_open <= S1:
                pp_buy_price = today_open
                # 因为开盘即最低，必然先买后涨。如果最高价摸到 PP，则以 PP 卖出，否则收盘卖
                if today_high >= PP:
                    pp_sell_price = PP
                else:
                    pp_sell_price = today_close
            # 情况 B: 开盘在 S1 之上，盘中回落触及 S1
            else:
                pp_buy_price = S1
                # 盘中先后顺序推断（基于日线实体的常见结构）
                if today_close >= today_open:
                    # 阳线: open -> low -> high -> close。先跌到 S1 买入，再涨到 high
                    if today_high >= PP:
                        pp_sell_price = PP
                    else:
                        pp_sell_price = today_close
                else:
                    # 阴线: open -> high -> low -> close。先涨到 PP (错过了)，再跌到 S1 买入
                    # 这意味着买入后，不再有机会以 PP 卖出（除非低位震荡又上去，但保守起见算只能收盘卖）
                    pp_sell_price = today_close

            # 结算 PP 策略
            pnl_pct = (pp_sell_price - pp_buy_price) / pp_buy_price * 100
            # 扣除手续费 (算单边 1.5bps 简单模拟)
            pnl_pct -= 0.03 
            
            results["pp_trades"] += 1
            results["pp_pnl"] += pnl_pct
            if pnl_pct > 0:
                results["pp_wins"] += 1

        # ==========================================
        # 2. PP + ML 混合策略
        # ==========================================
        # 混合策略规则：必须有买入机会 (today_low <= S1)，且 ML 预测最高价能到达 PP
        if pp_traded:
            mix_condition = False
            if pred_high_val > 0:
                # 过滤器 1: ML 认为不仅能到买入价之上，而且能接近 PP (放宽 0.2% 误差)
                if pred_high_val >= PP * 0.998:
                    mix_condition = True
            
            if mix_condition:
                results["mix_trades"] += 1
                results["mix_pnl"] += pnl_pct
                if pnl_pct > 0:
                    results["mix_wins"] += 1

    return results


def print_report(all_results):
    print("\n" + "═" * 85)
    print("                  PP 与 ML+PP 组合策略 严格日内路轮回测报告")
    print("═" * 85)
    print(f"  测试说明: ")
    print(f"  - 考虑到日内价格先后顺序 (阳线先 low 后 high，阴线先 high 后 low)")
    print(f"  - 若开盘 > S1 但日内下跌触及 S1，以 S1 成交")
    print(f"  - 若开盘 < S1，直接以 开盘价 成交")
    print(f"  - 仅在确认高点发生在买入之后的路径下，才假设在 PP 卖出，否则收盘卖出")
    print(f"  - 减去 0.03% 双边估算手续费")
    print(f"  - ML 过滤条件: 当日 ML_Pred_High >= PP 附近才开仓")
    print("─" * 85)

    print(f"  {'':>16s} | {'纯 PP 严格执行':>27s} | {'PP + ML 混合过滤':>27s}")
    print(f"  {'标的':>8s}  {'名称':>6s} | {'交易数':>6s}  {'胜率':>6s}  {'总收益率':>9s} | {'交易数':>6s}  {'胜率':>6s}  {'总收益率':>9s}")
    print("─" * 85)

    t_pp_trades = t_pp_wins = t_mix_trades = t_mix_wins = 0
    t_pp_pnl = t_mix_pnl = 0.0

    for r in all_results:
        pp_trades = r["pp_trades"]
        mix_trades = r["mix_trades"]
        
        pp_win_rt = r["pp_wins"]/pp_trades*100 if pp_trades else 0
        mix_win_rt = r["mix_wins"]/mix_trades*100 if mix_trades else 0

        t_pp_trades += pp_trades
        t_pp_wins += r["pp_wins"]
        t_pp_pnl += r["pp_pnl"]
        
        t_mix_trades += mix_trades
        t_mix_wins += r["mix_wins"]
        t_mix_pnl += r["mix_pnl"]

        print(
            f"  {r['code']:>8s}  {r['name']:>6s} | "
            f"{pp_trades:>6d}  {pp_win_rt:5.1f}%  {r['pp_pnl']:>8.2f}% | "
            f"{mix_trades:>6d}  {mix_win_rt:5.1f}%  {r['mix_pnl']:>8.2f}%"
        )

    print("─" * 85)
    if t_pp_trades:
        pp_total_rt = t_pp_wins/t_pp_trades*100
        mix_total_rt = t_mix_wins/t_mix_trades*100 if t_mix_trades else 0
        print(
            f"  {'合计':>16s} | "
            f"{t_pp_trades:>6d}  {pp_total_rt:5.1f}%  {t_pp_pnl:>8.2f}% | "
            f"{t_mix_trades:>6d}  {mix_total_rt:5.1f}%  {t_mix_pnl:>8.2f}%"
        )
    print("═" * 85)
    
    print("\n💡 结论分析:")
    avg_pp = t_pp_pnl / len(all_results)
    avg_mix = t_mix_pnl / len(all_results)
    print(f"  • 严格路径下的纯 PP 策略胜率下降至 {pp_total_rt:.1f}%，总收益 {t_pp_pnl:.2f}% (因为修复了不可能的卖出点和扣除了手续费)")
    print(f"  • 引入 ML 过滤后，交易次数减少了 {t_pp_trades - t_mix_trades} 笔，胜率变为 {mix_total_rt:.1f}%，总收益 {t_mix_pnl:.2f}%")
    
    if mix_total_rt > pp_total_rt:
        print(f"  → ML 成功过滤了部分错误开仓信号，胜率提升，结合使用是更好的选择！")
    else:
        print(f"  → ML 过滤效果不明显，纯 PP 的性价比可能更高。")


def main():
    print("获取数据并执行回测 (前 150天 训练，后 ~50天 严格测试)...")
    all_results = []
    import warnings
    warnings.filterwarnings('ignore')

    for code in ACTIVE_ETFS:
        df = fetch_training_data(code, days=200)
        if df is None or len(df) < 160:
            print(f"  [{code}] 数据不足，跳过")
            continue
            
        res = analyze_mixed_strategy(code, df, train_days=150)
        if res:
            all_results.append(res)
            print(f"  [{code}] 测试完成! (测试集 {res['test_days']} 天)")

    print_report(all_results)


if __name__ == "__main__":
    main()
