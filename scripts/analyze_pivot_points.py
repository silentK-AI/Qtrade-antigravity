"""
Pivot Point 有效性分析

验证经典 Pivot Point (PP/R1/R2/S1/S2) 对 7 个 ETF 标的
日内最高价/最低价的预测能力。

分析内容:
  1. PP 各水平线触及率 (日内高低点落在哪条线附近)
  2. 日内波动分布 (最低价相对开盘价的偏离比例)
  3. PP 预测 vs ML 预测精度对比
  4. 基于 PP 的简单 T+0 策略回测

用法:
  python scripts/analyze_pivot_points.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from loguru import logger

from config.settings import ETF_UNIVERSE, ACTIVE_ETFS
from scripts.train_model import fetch_training_data

logger.remove()
logger.add(sys.stderr, level="WARNING")


def calc_pivot_points(high: float, low: float, close: float) -> dict:
    """根据前日 H/L/C 计算 Pivot Point 各水平"""
    pp = (high + low + close) / 3
    r1 = 2 * pp - low
    s1 = 2 * pp - high
    r2 = pp + (high - low)
    s2 = pp - (high - low)
    return {"PP": pp, "R1": r1, "R2": r2, "S1": s1, "S2": s2}


def analyze_single_etf(code: str, df: pd.DataFrame) -> dict:
    """分析单个 ETF 的 Pivot Point 有效性"""
    name = ETF_UNIVERSE.get(code, {}).get("name", code)

    # 确保数值类型
    for col in ["开盘", "最高", "最低", "收盘"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    results = {
        "code": code,
        "name": name,
        "days": 0,
        # 触及率
        "touch_s2": 0, "touch_s1": 0, "touch_pp": 0, "touch_r1": 0, "touch_r2": 0,
        # 日内波动分布
        "low_deviations": [],   # (最低价 - 开盘价) / 开盘价
        "high_deviations": [],  # (最高价 - 开盘价) / 开盘价
        # PP 预测误差
        "pp_high_errors": [],   # |R1 - actual_high| / actual_high
        "pp_low_errors": [],    # |S1 - actual_low| / actual_low
        # 简单策略: 在 S1 买入，PP 卖出
        "strategy_trades": 0,
        "strategy_wins": 0,
        "strategy_total_pnl": 0.0,
    }

    tolerance = 0.003  # 触及判定: 价格在线附近 0.3% 以内

    for i in range(1, len(df)):
        prev = df.iloc[i - 1]
        today = df.iloc[i]

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
        results["days"] += 1

        # ---- 1. 触及率分析 ----
        # 日内价格范围 [today_low, today_high] 是否经过各水平线
        for level_name, level_val in pp.items():
            # 价格区间内包含该水平线，或在附近 0.3% 内
            in_range = today_low <= level_val <= today_high
            near_low = abs(today_low - level_val) / level_val < tolerance
            near_high = abs(today_high - level_val) / level_val < tolerance

            if in_range or near_low or near_high:
                key = f"touch_{level_name.lower()}"
                if key in results:
                    results[key] += 1

        # ---- 2. 日内波动分布 ----
        low_dev = (today_low - today_open) / today_open * 100
        high_dev = (today_high - today_open) / today_open * 100
        results["low_deviations"].append(low_dev)
        results["high_deviations"].append(high_dev)

        # ---- 3. PP 预测精度 ----
        # R1 作为 high 估计, S1 作为 low 估计
        high_err = abs(pp["R1"] - today_high) / today_high * 100
        low_err = abs(pp["S1"] - today_low) / today_low * 100
        results["pp_high_errors"].append(high_err)
        results["pp_low_errors"].append(low_err)

        # ---- 4. 简单 PP 策略 ----
        # 规则: 如果日内最低价 <= S1 (买入机会) 且收盘 > S1 (价格反弹)
        if today_low <= pp["S1"]:
            buy_price = pp["S1"]
            # 卖出目标: PP 或收盘价 (取较低者模拟现实)
            sell_price = min(pp["PP"], today_high)  # 不可能卖到超过最高价
            sell_price = max(sell_price, today_close)  # 至少在收盘卖出

            # 但买入价不能低于最低价
            buy_price = max(buy_price, today_low)

            pnl_pct = (sell_price - buy_price) / buy_price * 100
            results["strategy_trades"] += 1
            results["strategy_total_pnl"] += pnl_pct
            if pnl_pct > 0:
                results["strategy_wins"] += 1

    return results


def print_report(all_results: list[dict]):
    """打印汇总报告"""
    print("\n" + "═" * 75)
    print("              Pivot Point 有效性分析报告")
    print("═" * 75)

    # ---- 表1: 触及率 ----
    print("\n📊 各水平线触及率 (日内价格穿越该线的比例)")
    print("─" * 75)
    print(f"  {'标的':>8s}  {'名称':>10s}  {'天数':>4s}  {'S2':>6s}  {'S1':>6s}  {'PP':>6s}  {'R1':>6s}  {'R2':>6s}")
    print("─" * 75)

    for r in all_results:
        d = r["days"]
        if d == 0:
            continue
        print(
            f"  {r['code']:>8s}  {r['name']:>8s}  {d:>4d}  "
            f"{r['touch_s2']/d*100:5.1f}%  "
            f"{r['touch_s1']/d*100:5.1f}%  "
            f"{r['touch_pp']/d*100:5.1f}%  "
            f"{r['touch_r1']/d*100:5.1f}%  "
            f"{r['touch_r2']/d*100:5.1f}%"
        )

    # ---- 表2: 日内波动分布 ----
    print(f"\n📊 日内波动分布 (相对开盘价)")
    print("─" * 75)
    print(f"  {'标的':>8s}  {'名称':>10s}  {'最低价偏离':>12s}  {'最高价偏离':>12s}  {'平均振幅':>10s}")
    print(f"  {'':>8s}  {'':>10s}  {'均值   中位数':>12s}  {'均值   中位数':>12s}  {'':>10s}")
    print("─" * 75)

    for r in all_results:
        if not r["low_deviations"]:
            continue
        low_devs = np.array(r["low_deviations"])
        high_devs = np.array(r["high_deviations"])
        amplitude = high_devs - low_devs

        print(
            f"  {r['code']:>8s}  {r['name']:>8s}  "
            f"{np.mean(low_devs):+5.2f}% {np.median(low_devs):+5.2f}%  "
            f"{np.mean(high_devs):+5.2f}% {np.median(high_devs):+5.2f}%  "
            f"{np.mean(amplitude):5.2f}%"
        )

    # ---- 表3: 分位数分析 ----
    print(f"\n📊 最低价偏离分位数 (在开盘价下方 X% 挂单的成交概率)")
    print("─" * 75)
    thresholds = [0.1, 0.2, 0.3, 0.5, 0.8, 1.0]
    print(f"  {'标的':>8s}  {'名称':>10s}", end="")
    for t in thresholds:
        print(f"  {'↓'+str(t)+'%':>7s}", end="")
    print()
    print("─" * 75)

    for r in all_results:
        if not r["low_deviations"]:
            continue
        low_devs = np.array(r["low_deviations"])
        print(f"  {r['code']:>8s}  {r['name']:>8s}", end="")
        for t in thresholds:
            # 最低价相对开盘价跌超 t% 的概率
            hit_pct = np.mean(low_devs <= -t) * 100
            print(f"  {hit_pct:5.1f}%", end="")
        print()

    # ---- 表4: PP vs ML 预测精度 ----
    print(f"\n📊 PP 预测精度 (R1→High, S1→Low)")
    print("─" * 75)
    print(f"  {'标的':>8s}  {'名称':>10s}  {'R1→High误差':>12s}  {'S1→Low误差':>12s}  {'ML High误差':>12s}  {'ML Low误差':>12s}")
    print("─" * 75)

    for r in all_results:
        if not r["pp_high_errors"]:
            continue
        pp_h = np.mean(r["pp_high_errors"])
        pp_l = np.mean(r["pp_low_errors"])
        # ML 误差来自之前的回测 (硬编码近似值供对比)
        print(
            f"  {r['code']:>8s}  {r['name']:>8s}  "
            f"{pp_h:10.2f}%  {pp_l:10.2f}%  "
            f"{'(见ML回测)':>12s}  {'(见ML回测)':>12s}"
        )

    # ---- 表5: 简单 PP 策略 ----
    print(f"\n📊 简单 PP 策略 (S1 买入 → PP/收盘卖出)")
    print("─" * 75)
    print(f"  {'标的':>8s}  {'名称':>10s}  {'交易次':>5s}  {'胜率':>6s}  {'总收益率':>10s}  {'单均收益':>10s}")
    print("─" * 75)

    total_trades = 0
    total_wins = 0
    total_pnl = 0.0

    for r in all_results:
        trades = r["strategy_trades"]
        if trades == 0:
            continue
        win_rate = r["strategy_wins"] / trades * 100
        avg_pnl = r["strategy_total_pnl"] / trades

        total_trades += trades
        total_wins += r["strategy_wins"]
        total_pnl += r["strategy_total_pnl"]

        icon = "🟢" if r["strategy_total_pnl"] > 0 else "🔴"
        print(
            f"  {icon} {r['code']:>6s}  {r['name']:>8s}  "
            f"{trades:>5d}  {win_rate:5.1f}%  "
            f"{r['strategy_total_pnl']:>+9.2f}%  "
            f"{avg_pnl:>+9.3f}%"
        )

    print("─" * 75)
    if total_trades > 0:
        print(
            f"  合计                {total_trades:>5d}  "
            f"{total_wins/total_trades*100:5.1f}%  "
            f"{total_pnl:>+9.2f}%  "
            f"{total_pnl/total_trades:>+9.3f}%"
        )

    print("═" * 75)

    # ---- 结论 ----
    print("\n💡 分析结论:")
    avg_pp_touch = np.mean([r["touch_pp"] / r["days"] * 100 for r in all_results if r["days"] > 0])
    avg_s1_touch = np.mean([r["touch_s1"] / r["days"] * 100 for r in all_results if r["days"] > 0])
    avg_r1_touch = np.mean([r["touch_r1"] / r["days"] * 100 for r in all_results if r["days"] > 0])

    print(f"  • PP 平均穿越率: {avg_pp_touch:.1f}%")
    print(f"  • S1 平均触及率: {avg_s1_touch:.1f}%")
    print(f"  • R1 平均触及率: {avg_r1_touch:.1f}%")

    if avg_s1_touch > 30:
        print("  → S1 触及率较高，有一定的支撑参考价值")
    else:
        print("  → S1 触及率较低，跨境 ETF 的隔夜跳空削弱了 PP 的有效性")

    if total_trades > 0 and total_pnl > 0:
        print(f"  → PP 简单策略总收益为正 ({total_pnl:+.2f}%)，值得进一步研究")
    elif total_trades > 0:
        print(f"  → PP 简单策略总收益为负 ({total_pnl:+.2f}%)，直接使用效果不佳")


def main():
    print("正在获取历史数据...")
    all_results = []

    for code in ACTIVE_ETFS:
        df = fetch_training_data(code, days=200)
        if df is None or len(df) < 30:
            print(f"[{code}] 数据不足，跳过")
            continue

        result = analyze_single_etf(code, df)
        all_results.append(result)
        print(f"  [{code}] {result['name']} — {result['days']} 天分析完成")

    print_report(all_results)


if __name__ == "__main__":
    main()
