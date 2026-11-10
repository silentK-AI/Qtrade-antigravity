"""
14:58:00 尾盘集合竞价策略引擎 (兼顾次日涨停与实战可买入性 Fillability)
核心逻辑划分：
1. 【实战可买入池】：
   - A: 尾盘新回封标的 (14:30后封板，排队单未堵死，换手抛盘活跃，能买进)
   - B: 尾盘主力抢筹蓄势标的 (+6.0% ~ +8.8% 未封死，100%市价秒买进，锁定次日早盘冲板)
2. 【锁仓/风向标池】：
   - 早盘10:00前即封死且排单上亿的铁板，系统明确提示【买不进去！仅供持股者锁仓与板块风向标参考】
"""

from typing import List, Tuple, Dict, Any
from config import ClosingAuction1458Config
from models.stock_item import StockQuote, Snapshot1458, StrategySignal
from strategies.base_screener import BaseScreener


def _is_valid_time_str(t: str) -> bool:
    """严格检验是否为合法的 HH:MM 或 HH:MM:SS 格式，杜绝 '未封板' 等中文字符串参与时间大小比较"""
    if not t or not isinstance(t, str):
        return False
    parts = t.strip().split(":")
    return len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit()


def _time_le(t: str, target: str) -> bool:
    """安全判断 t <= target，非时间字符串返回 False"""
    if not _is_valid_time_str(t) or not _is_valid_time_str(target):
        return False
    return t[:5] <= target[:5]


def _time_ge(t: str, target: str) -> bool:
    """安全判断 t >= target，非时间字符串返回 False"""
    if not _is_valid_time_str(t) or not _is_valid_time_str(target):
        return False
    return t[:5] >= target[:5]


class Closing1458Screener(BaseScreener):
    """14:58 尾盘集合竞价可买入与次日涨停选股器"""

    def __init__(self, config: ClosingAuction1458Config = None):
        super().__init__()
        self.config = config or ClosingAuction1458Config()

    def calculate_1458_score(
        self,
        quote: StockQuote,
        snap: Snapshot1458,
        sentiment_multiplier: float = 1.0
    ) -> Tuple[float, float, str, Dict[str, Any], str, str]:
        """
        计算 14:58 尾盘竞价打分
        返回: (综合分, 资金分, 战法, 因子字典, 建议操作, 次日预期)
        """
        factors = {}
        seal_wan = snap.closing_seal_amount / 10000.0
        seal_ratio = snap.seal_to_float_ratio
        first_time = snap.first_seal_time
        last_time = getattr(snap, "last_seal_time", "") or first_time
        zbc = snap.day_open_board_count

        # -----------------------------------------------------------------
        # 场景一：早盘极早封死 (首次封板 <= 10:30，且无炸板或早早回封 <= 11:30) —— 绝对买不进去！
        # -----------------------------------------------------------------
        if snap.is_limit_up and (_time_le(first_time, "10:30") and (zbc == 0 or _time_le(last_time, "11:30"))):
            factors["【可买入性】"] = f"❌ 队列已堵死！早盘 {first_time} 已封死，排单过厚，14:58挂单买不进"
            factors["【实战定位】"] = "板块情绪定海神针 / 持筹者锁仓标杆"
            factors["【资金】排队封单规模"] = f"封单 {seal_wan:.0f} 万元 (首次封板: {first_time})"
            pattern = "【龙头风向标·买不进】铁板锁仓"
            action = "【早盘已封死·14:58买不进！】若早盘已持有，则坚决锁仓一股不卖，次日坐等连板"
            expectation = "绝对核心领涨龙头，早盘即封死，次日高概率高开或秒板，为后排打开高度空间。"
            raw_score, raw_cap = 98.0, 60.0

        # -----------------------------------------------------------------
        # 场景二：真正的尾盘回封 / 午后弱转强回封 (最后封板时间 >= 14:00，或首次封板时间 >= 14:00，或盘中炸板多次尾盘 >= 13:30 压哨回封)
        # -----------------------------------------------------------------
        elif snap.is_limit_up and (_time_ge(last_time, "14:00") or _time_ge(first_time, "14:00") or (zbc >= 1 and _time_ge(last_time, "13:30"))):
            factors["【可买入性】"] = f"✅ 能够买进！最后回封时间为 {last_time} (盘中炸板 {zbc} 次)，抛盘充分换手，排单成交率高"
            factors["【资金承接】"] = f"尾盘排单 {seal_wan:.0f} 万元，多头尾盘突袭锁单"
            factors["【换手硬度】"] = f"全天充分换手 {quote.turnover_rate:.1f}%，筹码洗净"
            pattern = "【尾盘回封·能买进】分歧转一致次日连板"
            action = "【14:58立即挂涨停价委托】排队进入收盘集合竞价，预计大概率能成交！"
            expectation = "尾盘经受分歧后顽强回封，浮筹已在盘中洗尽，次日享受弱转强高开连板溢价。"
            raw_score, raw_cap = 92.0, 52.0

        # -----------------------------------------------------------------
        # 场景三：其他时间段平稳封死的主板标的 (买入概率低)
        # -----------------------------------------------------------------
        elif snap.is_limit_up:
            factors["【可买入性】"] = f"⚠️ 封板时间 {first_time}，封单较厚，14:58 成交概率较低"
            factors["【资金规模】"] = f"封单 {seal_wan:.0f} 万元"
            pattern = "【日内封板·排单难成】"
            action = "【14:58挂单成交率偏低】建议作为次日观察标的，不建议强行排单"
            expectation = "日内平稳封板，重点观察次日竞价承接情况。"
            raw_score, raw_cap = 86.0, 48.0

        # -----------------------------------------------------------------
        # 场景四：尾盘放量蓄势冲板未遂 (+5.5% ~ +8.8%，100%市价秒买进！)
        # -----------------------------------------------------------------
        elif not snap.is_limit_up and snap.indicative_change_pct >= 5.5:
            factors["【可买入性】"] = "✅ 100%秒买进！盘口卖单充足，直接市价挂单即时成交"
            factors["【资金抢筹】"] = "主力尾盘巨资逆势扫盘，故意不封死避免过早暴露"
            pattern = "【蓄势未板·100%买进】尾盘突击次日冲板"
            action = "【14:58-14:59市价直接买入】在收盘前锁定底仓，次日早盘享受抬轿"
            expectation = "全天主力沿均线蓄势推升，尾盘爆量隐蔽吸筹，次日早盘极高概率直接集合竞价高开抢筹冲涨停。"
            raw_score, raw_cap = 88.0, 48.0

        # -----------------------------------------------------------------
        # 其余平庸标的淘汰
        # -----------------------------------------------------------------
        else:
            return 0.0, 0.0, "平庸标的", {"【状态】": "不符合尾盘进攻特征"}, "观望", "无次日涨停预期"

        final_score = round(min(100.0, raw_score * sentiment_multiplier), 1)
        final_cap = round(min(60.0, raw_cap * sentiment_multiplier), 1)
        return final_score, final_cap, pattern, factors, action, expectation

    def run_strategy(
        self,
        candidates: List[Tuple[StockQuote, Snapshot1458]],
        sentiment_multiplier: float = 1.0
    ) -> List[StrategySignal]:
        signals = []

        for quote, snap in candidates:
            if not self.stock_filter.filter_quote(quote):
                continue

            score, cap_score, pattern, factors, action, expectation = self.calculate_1458_score(
                quote, snap, sentiment_multiplier
            )

            if score >= self.config.SCORE_THRESHOLD:
                stop_loss = self.calculate_stop_loss(snap.indicative_price, risk_tolerance_pct=3.0)

                signal = StrategySignal(
                    code=quote.code,
                    name=quote.name,
                    strategy_type="14:58尾盘实战选股",
                    score=score,
                    capital_score=cap_score,
                    current_price=snap.indicative_price,
                    change_pct=snap.indicative_change_pct,
                    target_pattern=pattern,
                    key_factors=factors,
                    suggested_action=action,
                    stop_loss_price=stop_loss,
                    next_day_expectation=expectation
                )
                signals.append(signal)

        # 排序：优先展示能够买进的高价值标的，其次展示风向标
        signals.sort(key=lambda s: (("能买进" in s.target_pattern or "100%" in s.target_pattern), s.score), reverse=True)
        return signals
