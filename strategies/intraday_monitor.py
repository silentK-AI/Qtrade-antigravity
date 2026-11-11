"""
盘中交易时段实时异动监控模块 (09:30 - 14:50)
核心功能：
1. 实时捕获主板个股【涨停封板】异动（包括早盘秒板、连板晋级、午后突袭）；
2. 实时捕获主板个股【炸板开板】异动（包括高位大面开板、分歧换手开板）；
3. 针对每只异动标的，输出专业的操作建议（买入/排单/低吸/坚决回避）及具体的筹码与资金逻辑原因；
4. 严格状态去重，同一事件不重复推送。
"""

from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from models.stock_item import IntradayEvent
from utils.filters import StockFilter
from data.open_data_provider import OpenDataProvider
from utils.logger import get_logger
from utils.calendar import get_beijing_now

logger = get_logger("intraday_monitor")


class IntradayMonitor:
    """盘中涨停上板与炸板异动实时监控器"""

    def __init__(self, provider: Optional[OpenDataProvider] = None):
        self.provider = provider or OpenDataProvider()
        self.filter = StockFilter()
        # 记录已封板股票状态: code -> info
        self.seen_zt_stocks: Dict[str, Dict[str, Any]] = {}
        # 记录已提醒过的炸板股票及对应炸板次数: code -> last_alerted_zbc
        self.seen_zb_stocks: Dict[str, int] = {}
        # 初始化是否已完成底量建档
        self.is_initialized: bool = False

    def initialize_current_state(self):
        """盘中启动时先拉取一次当前盘口存量，避免把开盘前就已板的标的大批量当成新异动误报"""
        try:
            zt_pool = self.provider.fetch_today_zt_pool_details()
            for code, item in zt_pool.items():
                name = item.get("name", code)
                if self.filter.is_main_board_code(code) and self.filter.is_valid_name(name):
                    self.seen_zt_stocks[code] = item

            zb_pool = self.provider.fetch_today_zb_pool_details()
            for code, item in zb_pool.items():
                name = item.get("name", code)
                if self.filter.is_main_board_code(code) and self.filter.is_valid_name(name):
                    self.seen_zb_stocks[code] = item.get("open_board_count", 1)
            self.is_initialized = True
        except Exception as e:
            print(f"[盘中监控初始化提示] {e}")

    def _get_allowed_prev_zt_boards(self) -> Dict[str, int]:
        """获取昨日 1板 / 2板 / 3板 主板标的映射（严格仅监控 1进2 / 2进3 / 3进4）"""
        if not hasattr(self.provider, "fetch_prev_day_zt_boards"):
            return {}
        prev_zt = self.provider.fetch_prev_day_zt_boards() or {}
        return {
            code: int(yb) for code, yb in prev_zt.items()
            if int(yb or 0) in self.filter.ALLOWED_YESTERDAY_BOARDS
        }

    def check_events(self) -> List[IntradayEvent]:
        """
        单次检查并返回最新发生的【涨停封板】与【炸板开板】异动事件（严格仅限 1进2 / 2进3 / 3进4）
        """
        if not self.is_initialized:
            self.initialize_current_state()
            return []

        events: List[IntradayEvent] = []
        now_time_str = get_beijing_now().strftime("%H:%M:%S")
        allowed_prev = self._get_allowed_prev_zt_boards()

        # -------------------------------------------------------------
        # 1. 检查【涨停封板】异动（严格仅保留 今日2/3/4板 即 1进2/2进3/3进4）
        # -------------------------------------------------------------
        try:
            zt_pool = self.provider.fetch_today_zt_pool_details()
            for code, item in zt_pool.items():
                if not self.filter.is_main_board_code(code):
                    continue
                name = item.get("name", code)
                if not self.filter.is_valid_name(name):
                    continue

                lbc = int(item.get("continuous_boards", 1) or 1)
                if lbc not in self.filter.ALLOWED_TODAY_BOARDS:
                    continue

                # 如果这只股票之前不在已封板列表中，说明刚刚完成 1进2/2进3/3进4 封板！
                if code not in self.seen_zt_stocks:
                    fund_wan = float(item.get("seal_amount", 0.0) or 0.0) / 10000.0
                    zbc = int(item.get("open_board_count", 0) or 0)
                    fbt = item.get("first_seal_time", now_time_str)
                    lbt = item.get("last_seal_time", now_time_str)

                    # 判断是否属于炸板后的【弱转强回封】
                    is_reseal = (code in self.seen_zb_stocks and zbc >= 1)

                    # 生成买入/不买入建议与原因
                    advice, reason = self._generate_limit_up_advice(
                        lbc=lbc,
                        fund_wan=fund_wan,
                        zbc=zbc,
                        is_reseal=is_reseal,
                        seal_time=lbt
                    )

                    event = IntradayEvent(
                        event_type="LIMIT_UP",
                        code=code,
                        name=name,
                        current_price=float(item.get("price", 0.0) or 0.0),
                        change_pct=float(item.get("change_pct", 10.0) or 10.0),
                        event_time=lbt,
                        seal_amount_wan=fund_wan,
                        turnover_rate=float(item.get("turnover_rate", 0.0) or 0.0),
                        open_board_count=zbc,
                        continuous_boards=lbc,
                        action_advice=advice,
                        reason=reason,
                        industry=str(item.get("industry", "") or "主板题材")
                    )
                    events.append(event)
                    # 更新已封板缓存
                    self.seen_zt_stocks[code] = item
        except Exception as e:
            logger.warning(f"盘中监控封板查询异常: {e}")

        # -------------------------------------------------------------
        # 2. 检查【炸板开板】异动（严格仅保留昨日1/2/3板冲击 2/3/4板时炸板）
        # -------------------------------------------------------------
        try:
            zb_pool = self.provider.fetch_today_zb_pool_details()
            for code, item in zb_pool.items():
                if not self.filter.is_main_board_code(code):
                    continue
                name = item.get("name", code)
                if not self.filter.is_valid_name(name):
                    continue

                yb = int(item.get("yesterday_boards", 0) or allowed_prev.get(code, 0) or 0)
                if yb not in self.filter.ALLOWED_YESTERDAY_BOARDS:
                    continue

                curr_zbc = int(item.get("open_board_count", 1) or 1)
                last_alerted_zbc = self.seen_zb_stocks.get(code, 0)

                # 如果炸板次数增加，说明发生了新的炸板！
                if curr_zbc > last_alerted_zbc:
                    curr_price = float(item.get("current_price", 0.0) or 0.0)
                    pct = float(item.get("change_pct", 0.0) or 0.0)
                    hs = float(item.get("turnover_rate", 0.0) or 0.0)
                    fbt = item.get("first_seal_time", now_time_str)

                    advice, reason = self._generate_broken_board_advice(
                        pct=pct,
                        hs=hs,
                        zbc=curr_zbc,
                        fbt=fbt,
                        yb=yb
                    )

                    event = IntradayEvent(
                        event_type="BROKEN_BOARD",
                        code=code,
                        name=name,
                        current_price=curr_price,
                        change_pct=pct,
                        event_time=now_time_str,
                        seal_amount_wan=0.0,
                        turnover_rate=hs,
                        open_board_count=curr_zbc,
                        continuous_boards=yb + 1,
                        action_advice=advice,
                        reason=reason,
                        industry=str(item.get("industry", "") or "主板题材")
                    )
                    events.append(event)
                    # 更新炸板次数记录
                    self.seen_zb_stocks[code] = curr_zbc
                    # 炸板后从已封死列表中移除，便于后续回封时再次捕获
                    if code in self.seen_zt_stocks:
                        del self.seen_zt_stocks[code]
        except Exception as e:
            logger.warning(f"盘中监控炸板查询异常: {e}")

        return events

    def _generate_limit_up_advice(
        self,
        lbc: int,
        fund_wan: float,
        zbc: int,
        is_reseal: bool,
        seal_time: str
    ) -> Tuple[str, str]:
        """输出 1进2 / 2进3 / 3进4 涨停封板买入建议与原因"""
        relay = f"{lbc - 1}进{lbc}" if lbc in self.filter.ALLOWED_TODAY_BOARDS else f"{lbc}板"

        # 一字开盘封死处理 (竞价一字板，排单通道封死)
        if seal_time <= "09:25:00" and zbc == 0:
            advice = f"【建议：{relay}一字涨停·排队买不进/持股锁仓】"
            reason = f"集合竞价直接巨单封死{relay}一字涨停，封单高达 {fund_wan:.0f} 万元堵死队列，无法挂单成交，持有者锁仓继续享受连板溢价。"
            return advice, reason

        if is_reseal:
            if fund_wan >= 2000:
                advice = f"【建议：{relay}分歧回封·可轻仓打板接力】"
                reason = f"{relay}日内经受 {zbc} 次炸板洗盘后顽强回封，主力再度斥资 {fund_wan:.0f} 万元死封买一，浮筹洗净确立弱转强。"
            else:
                advice = f"【建议：{relay}弱次回封·封单偏薄谨慎接】"
                reason = f"{relay}日内炸板 {zbc} 次后于 {seal_time} 虽重新封板，但封单仅 {fund_wan:.0f} 万元偏薄，筹码仍有松动风险，不建议激进追打。"
        elif lbc == 4:
            if fund_wan >= 4000:
                advice = "【建议：3进4换手晋级·核心龙头可排板】"
                reason = f"主线强标顺利晋级 4 连板（3进4）！买一封单 {fund_wan:.0f} 万元极其硬朗，辨识度拉满。"
            else:
                advice = "【建议：3进4封单偏薄·谨慎防高位炸板】"
                reason = f"虽晋级 3进4，但封单仅 {fund_wan:.0f} 万元偏薄，高位筹码一旦松动易出现大分歧，不建议盲目挂巨量排单。"
        elif lbc == 3:
            if fund_wan >= 3500:
                advice = "【建议：2进3主线卡位·重点排单打板】"
                reason = f"2 进 3 强势晋级确立板块前排身位！买一封单 {fund_wan:.0f} 万元承接充足，次日享连板溢价预期。"
            else:
                advice = "【建议：弱三板·观察封单稳固度再打板】"
                reason = f"2 进 3 封单仅 {fund_wan:.0f} 万元相对有限，需警惕盘中受板块分歧影响出现炸板。"
        else:
            # 1进2 (lbc == 2)
            if fund_wan >= 3000:
                advice = "【建议：1进2放量晋级·重点打板接力】"
                reason = f"1 进 2 换手晋级成功，确立身位优势。封单 {fund_wan:.0f} 万元，承接有力，符合主线接力标准。"
            else:
                advice = "【建议：弱二板·观察承接不盲目打板】"
                reason = f"1 进 2 封单 {fund_wan:.0f} 万元相对偏小，需观察明日早盘集合竞价能否弱转强高开确认。"

        return advice, reason

    def _generate_broken_board_advice(
        self,
        pct: float,
        hs: float,
        zbc: int,
        fbt: str,
        yb: int = 1
    ) -> Tuple[str, str]:
        """输出 1进2 / 2进3 / 3进4 炸板开板买入建议与原因（多维度筹码与盘口细分）"""
        relay = f"{yb}进{yb + 1}" if yb in self.filter.ALLOWED_YESTERDAY_BOARDS else "连板"

        # 1. 多次炸板 / 筹码反复松动 (>= 3 次) —— 极高风险
        if zbc >= 3:
            advice = f"【建议：{relay}已反复炸板{zbc}次·严禁低吸/观望】"
            reason = f"{relay}冲板日内已发生 {zbc} 次炸板，多头接力资金明显疲态，获利盘反复出逃导致筹码松动恶化。即使价格暂守在 +{pct:.1f}%，也极易演变成午后跳水大面，坚决不接飞刀。"
            return advice, reason

        # 2. 涨停档位微幅漏单 (涨幅 >= +9.5%) —— 极小分歧/盘口试盘
        if pct >= 9.5:
            if zbc == 1:
                advice = f"【建议：{relay}涨停微幅漏单·紧盯回封可打板】"
                reason = f"{relay}现价 +{pct:.2f}% 仅微幅脱离涨停，属于主力盘口换血或微量漏单。若买一迅速出现万手大单回封可果断排单；若抛压蔓延跌破 +9.0% 则立即停止排单。"
            else:
                advice = f"【建议：{relay}高位微开频发·防主力出货】"
                reason = f"{relay}虽维持在 +{pct:.2f}% 涨停边缘，但已是日内第 {zbc} 次开板，主力有对倒出货嫌疑，建议等待大单重新死封再跟随。"

        # 3. 良性回踩分时均线 (+6.5% ~ +9.5%)
        elif pct >= 6.5:
            if hs <= 15.0:
                advice = f"【建议：{relay}回踩均线低吸·博秒回封】"
                reason = f"{relay}第 {zbc} 次炸板后坚守在 +{pct:.1f}% 高位震荡，换手率 {hs:.1f}% 良性健康未现踩踏，回踩分时均线不破可小仓位低吸博主力弱转强回封。"
            elif hs <= 25.0:
                advice = f"【建议：{relay}分歧换手加剧·等待大单回封】"
                reason = f"{relay}炸板后价格维持在 +{pct:.1f}%，但换手率已达 {hs:.1f}%，多空分歧显著放大，建议等待大单真正回封涨停瞬间再跟随打板。"
            else:
                advice = f"【建议：{relay}爆量高换手炸板·禁止追高】"
                reason = f"{relay}换手率已飙升至 {hs:.1f}%，筹码剧烈派发，高位抛压沉重，即便回封也是烂板，盈亏比极差，禁止低吸追涨。"

        # 4. 中度跳水回落 (+2.0% ~ +6.5%)
        elif pct >= 2.0:
            advice = f"【建议：{relay}炸板承接走弱·观望不接飞刀】"
            reason = f"{relay}炸板后价格快速下坠至 +{pct:.1f}%，日内买盘承接严重不足，上方套牢盘堆积，此时介入极易反复吃面，观望为主。"

        # 5. 深度大面 (< +2.0% 或翻绿)
        else:
            advice = f"【建议：{relay}炸板大面·坚决规避】"
            reason = f"{relay}炸板后出现踩踏杀跌至 +{pct:.1f}%，主力资金坚决出逃，形态严重破位，次日大概率低开核按钮，严禁抄底。"

        return advice, reason
