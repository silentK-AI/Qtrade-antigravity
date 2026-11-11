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
        to_3d = float(getattr(snap, "turnover_3d", 0.0) or 0.0)
        seal_to_amt = float(getattr(snap, "seal_to_amount_ratio", 0.0) or 0.0)
        if seal_to_amt == 0.0 and quote.amount > 0 and snap.closing_seal_amount > 0:
            seal_to_amt = round(snap.closing_seal_amount / quote.amount * 100.0, 2)

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
            raw_score = 90.0 + min(6.0, seal_wan / 15000.0 * 6.0) + min(2.0, (snap.continuous_board_count - 1) * 0.5)
            raw_cap = 54.0 + min(6.0, seal_wan / 15000.0 * 6.0)

        # -----------------------------------------------------------------
        # 场景二：真正的尾盘回封 / 午后弱转强回封 (最后封板 >= 13:45 或首次封板 >= 14:00，或盘中分歧后 >= 13:30 回封)
        # -----------------------------------------------------------------
        elif snap.is_limit_up and (_time_ge(last_time, "13:45") or _time_ge(first_time, "14:00") or (zbc >= 1 and _time_ge(last_time, "13:30"))):
            # 1. 资金封成强度与承接评分 (满分 60 分)
            # 封成比 (封单额 / 当日累计成交额，满分 25 分) —— 实盘验证核心第一因子：剔除巨量虚封、优选惜售锁筹
            if seal_to_amt >= 20.0:
                score_seal_amt = 25.0
                factors["【资金封成比】"] = f"封成比 {seal_to_amt:.1f}% (极度惜售·封单超日内成交五分之一)"
            elif seal_to_amt >= 12.0:
                score_seal_amt = 21.0
                factors["【资金封成比】"] = f"封成比 {seal_to_amt:.1f}% (主力控盘坚决·锁筹意愿极强)"
            elif seal_to_amt >= 6.0:
                score_seal_amt = 15.0
                factors["【资金封成比】"] = f"封成比 {seal_to_amt:.1f}% (封成比例合格)"
            elif seal_to_amt >= 3.0:
                score_seal_amt = 6.0
                factors["【资金封成比】"] = f"⚠️ 封成比仅 {seal_to_amt:.1f}% (成交体量偏大，封单相对薄弱)"
            else:
                score_seal_amt = 0.0
                factors["【资金封成比】"] = f"🚨 封成比仅 {seal_to_amt:.1f}% (严重虚弱，封单远小于日内抛压)"

            # 绝对封单规模 (满分 15 分)
            if seal_wan >= 8000.0:
                score_seal = 15.0
                factors["【资金承接】"] = f"不可撤单封单 {seal_wan:.0f} 万元 (超级主力顶格大单锁仓)"
            elif seal_wan >= 3500.0:
                score_seal = 12.0
                factors["【资金承接】"] = f"不可撤单封单 {seal_wan:.0f} 万元 (主力大单坚决封死)"
            elif seal_wan >= 2000.0:
                score_seal = 9.0
                factors["【资金承接】"] = f"不可撤单封单 {seal_wan:.0f} 万元 (排单承接良好)"
            elif seal_wan >= 1000.0:
                score_seal = 5.0
                factors["【资金承接】"] = f"不可撤单封单 {seal_wan:.0f} 万元 (封单体量中等)"
            else:
                score_seal = 1.0
                factors["【资金承接】"] = f"封单仅 {seal_wan:.0f} 万元 (体量单薄)"

            # 封单占自由流通市值千分比 (满分 10 分)
            if seal_ratio >= 6.0:
                score_ratio = 10.0
                factors["【封流比例】"] = f"封单占流通盘 {seal_ratio:.2f}‰ (顶格比例)"
            elif seal_ratio >= 3.0:
                score_ratio = 8.0
                factors["【封流比例】"] = f"封单占流通盘 {seal_ratio:.2f}‰ (比例充足)"
            elif seal_ratio >= 1.5:
                score_ratio = 5.0
                factors["【封流比例】"] = f"封单占流通盘 {seal_ratio:.2f}‰ (中规中矩)"
            else:
                score_ratio = 2.0
                factors["【封流比例】"] = f"封单占流通盘 {seal_ratio:.2f}‰"

            # 回封时效与尾盘突袭共振 (满分 10 分)
            if _time_ge(last_time, "14:15") and zbc <= 2:
                score_time = 10.0
                factors["【回封时机】"] = f"最后回封时间 {last_time} (尾盘突袭稳步封死，分歧转一致黄金时点)"
            elif _time_ge(last_time, "13:45"):
                score_time = 8.0
                factors["【回封时机】"] = f"最后回封时间 {last_time} (午后承接走强封死)"
            elif _time_ge(last_time, "13:30"):
                score_time = 6.0
                factors["【回封时机】"] = f"最后回封时间 {last_time} (午后回封)"
            else:
                score_time = 4.0
                factors["【回封时机】"] = f"回封时间 {last_time}"

            raw_cap = score_seal_amt + score_seal + score_ratio + score_time

            # 2. 筹码锁定与派发排雷评分 (满分 40 分)
            # 近3日累计换手 / 当日换手健康度 (满分 25 分) —— 严防高位巨量派发次日大面
            to = quote.turnover_rate
            if to_3d > 0.0:
                if to_3d <= 22.0 and to <= 12.0:
                    score_to = 25.0
                    factors["【换手硬度】"] = f"近3日累计换手仅 {to_3d:.1f}% (今日 {to:.1f}%)，筹码高度锁定未派发"
                elif to_3d <= 28.0:
                    score_to = 21.0
                    factors["【换手硬度】"] = f"近3日累计换手 {to_3d:.1f}% (今日 {to:.1f}%)，良性接力换手"
                elif to_3d <= 38.0:
                    score_to = 14.0
                    factors["【换手硬度】"] = f"近3日累计换手 {to_3d:.1f}% (今日 {to:.1f}%)，换手偏大存在分歧"
                elif to_3d <= 48.0:
                    score_to = 4.0
                    factors["【换手硬度】"] = f"⚠️ 近3日累计换手达 {to_3d:.1f}% (高位宽幅换手，谨慎防派发)"
                else:
                    score_to = -25.0
                    factors["【换手硬度】"] = f"🚨 近3日累计换手高达 {to_3d:.1f}% (连续巨量筹码派发，次日极易大面核按钮)"
            else:
                if 6.0 <= to <= 18.0:
                    score_to = 25.0
                    factors["【换手硬度】"] = f"全天充分换手 {to:.1f}%，筹码锁定与换手匹配良好"
                elif 18.0 < to <= 25.0:
                    score_to = 17.0
                    factors["【换手硬度】"] = f"全天活跃换手 {to:.1f}%"
                elif to < 6.0:
                    score_to = 15.0
                    factors["【换手硬度】"] = f"换手率 {to:.1f}% (筹码惜售锁定)"
                elif 25.0 < to <= 32.0:
                    score_to = 6.0
                    factors["【换手硬度】"] = f"⚠️ 换手率高达 {to:.1f}% (高位巨幅换手，次日承接压力大)"
                else:
                    score_to = -15.0
                    factors["【换手硬度】"] = f"🚨 换手率高达 {to:.1f}% (严重换手过载，警惕主力出货)"

            # 炸板次数抗性 (满分 15 分)
            if zbc == 0:
                score_zbc = 15.0
                factors["【炸板抗性】"] = "全天零炸板一次封死到底，筹码结构最坚固"
            elif zbc == 1:
                score_zbc = 13.0
                factors["【炸板抗性】"] = "盘中仅分歧炸板1次后顽强回封，筹码清洗相对充分"
            elif zbc == 2:
                score_zbc = 4.0
                factors["【炸板抗性】"] = f"⚠️ 盘中炸板 {zbc} 次，分歧偏大需严苛检视封成比"
            elif zbc == 3:
                score_zbc = -8.0
                factors["【炸板抗性】"] = f"🚨 盘中炸板达 {zbc} 次，筹码松动明显"
            else:
                score_zbc = -30.0
                factors["【风控警示】"] = f"❌ 盘中炸板高达 {zbc} 次，筹码彻底涣散，次日极易低开核按钮！"

            raw_risk = score_to + score_zbc
            raw_score = raw_cap + raw_risk

            # 3. 硬性风控一票否决与实战分级
            if zbc >= 4:
                raw_score = min(raw_score, 45.0)
                factors["【可买入性】"] = f"❌ 坚决回避！全天炸板高达 {zbc} 次，主力护盘乏力，次日大概率大幅低开"
                pattern = "【高危烂板·坚决回避】"
                action = f"【严禁排单！】全天炸板高达 {zbc} 次，属于典型日内烂板，次日极大概率直接低开被核"
                expectation = "筹码已被反复砸散，属于严重烂板，次日极易遭遇获利盘与割肉盘抢跑践踏。"
            elif to_3d > 48.0:
                raw_score = min(raw_score, 50.0)
                factors["【可买入性】"] = f"❌ 坚决回避！近3日累计换手高达 {to_3d:.1f}%，疑似高位筹码派发，次日大面风险极高"
                pattern = "【高位派发·坚决回避】"
                action = f"【严禁排单！】近3日换手率达 {to_3d:.1f}%，短线浮筹透支严重，次日极易低开兑现"
                expectation = "连续高换手伴随抛压释放，次日大概率面临获利盘集中出逃冲击。"
            elif seal_to_amt > 0.0 and seal_to_amt < 3.0:
                raw_score = min(raw_score, 60.0)
                factors["【可买入性】"] = f"⚠️ 坚决回避！封成比仅 {seal_to_amt:.1f}% (<3%)，封单相对日内成交额过于虚弱"
                pattern = "【封成比过弱·坚决回避】"
                action = f"【不建议排单】封成比仅 {seal_to_amt:.1f}%，缺乏主力真金白银锁仓，次日承接堪忧"
                expectation = "尾盘虚封痕迹较重，日内巨量换手后若无强封成比支撑，次日极易低开低走。"
            elif seal_wan < 800.0:
                raw_score = min(raw_score, 65.0)
                factors["【可买入性】"] = f"⚠️ 封单仅 {seal_wan:.0f} 万元 (<800万)，封单单薄缺乏护盘"
                pattern = "【封单单薄·谨慎排单】"
                action = f"【不建议排单】尾盘封单仅 {seal_wan:.0f} 万元，极易被尾盘最后一刻抛盘砸开"
                expectation = "封单不足，缺乏大资金锁仓支撑，次日溢价预期偏低。"
            else:
                factors["【可买入性】"] = f"✅ 能够买进！最后回封时间为 {last_time} (盘中炸板 {zbc} 次，封成比 {seal_to_amt:.1f}%)，排单成交率高"
                pattern = "【尾盘回封·能买进】分歧转一致次日连板"
                action = "【14:58立即挂涨停价委托】排队进入收盘集合竞价，预计大概率能成交！"
                expectation = "低累计换手配合高封成比强势封板，主力锁仓坚决，次日享受高溢价与连板预期。"

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
        # 场景四：尾盘放量蓄势冲板未遂 (+5.5% ~ +9.2%，100%市价秒买进！)
        # -----------------------------------------------------------------
        elif not snap.is_limit_up and 5.5 <= snap.indicative_change_pct <= 9.2:
            if to_3d > 48.0:
                factors["【可买入性】"] = f"❌ 坚决回避！近3日累计换手高达 {to_3d:.1f}%，尾盘拉高疑似派发"
                factors["【资金抢筹】"] = "近3日高换手透支买盘，不宜盲目市价追高"
                pattern = "【高位派发·坚决回避】"
                action = "【不建议买入】高位巨量换手下冲高未封，谨防次日低开"
                expectation = "筹码连续高换手松动，次日冲高回落概率较高。"
                raw_score, raw_cap = 55.0, 25.0
            else:
                inflow_bonus = min(4.0, max(0.0, quote.net_large_inflow / 50000000.0 * 4.0)) if quote.net_large_inflow > 0 else 0.0
                to_info = f"，近3日累计换手 {to_3d:.1f}% 健康" if to_3d > 0 else ""
                factors["【可买入性】"] = f"✅ 100%秒买进！盘口卖单充足，直接市价挂单即时成交{to_info}"
                factors["【资金抢筹】"] = "主力尾盘巨资逆势扫盘，故意不封死避免过早暴露"
                pattern = "【蓄势未板·100%买进】尾盘突击次日冲板"
                action = "【14:58-14:59市价直接买入】在收盘前锁定底仓，次日早盘享受抬轿"
                expectation = "全天主力沿均线蓄势推升，尾盘爆量隐蔽吸筹，次日早盘极高概率直接集合竞价高开抢筹冲涨停。"
                raw_score, raw_cap = 80.0 + inflow_bonus, 45.0 + inflow_bonus

        # -----------------------------------------------------------------
        # 其余平庸标的淘汰
        # -----------------------------------------------------------------
        else:
            return 0.0, 0.0, "平庸标的", {"【状态】": "不符合尾盘进攻特征"}, "观望", "无次日涨停预期"

        final_score = round(max(0.0, min(100.0, raw_score * sentiment_multiplier)), 1)
        final_cap = round(max(0.0, min(60.0, raw_cap * sentiment_multiplier)), 1)
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

        # 排序与风控过滤：严格剔除高危烂板、高位派发、封成比过弱及封单单薄标的
        qualified = [s for s in signals if "回避" not in s.target_pattern and "高危" not in s.target_pattern and "单薄" not in s.target_pattern]
        # 优先级：真正的尾盘回封涨停标的绝对排在第一梯队，蓄势未板次之，内部按综合得分严格降序
        qualified.sort(key=lambda s: (2 if "尾盘回封" in s.target_pattern else (1 if "蓄势未板" in s.target_pattern else 0), s.score), reverse=True)
        # 14:58 尾盘集合竞价仅 90 秒操作窗口，优中选优严格输出不超过 Top 3 只高胜率标的
        return qualified[:3]
