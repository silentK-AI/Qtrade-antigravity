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

    def check_events(self) -> List[IntradayEvent]:
        """
        单次检查并返回最新发生的【涨停封板】与【炸板开板】异动事件
        """
        if not self.is_initialized:
            self.initialize_current_state()
            return []

        events: List[IntradayEvent] = []
        now_time_str = datetime.now().strftime("%H:%M:%S")

        # -------------------------------------------------------------
        # 1. 检查【涨停封板】异动
        # -------------------------------------------------------------
        try:
            zt_pool = self.provider.fetch_today_zt_pool_details()
            for code, item in zt_pool.items():
                if not self.filter.is_main_board_code(code):
                    continue
                name = item.get("name", code)
                if not self.filter.is_valid_name(name):
                    continue

                # 如果这只股票之前不在已封板列表中，说明刚刚完成封板！
                if code not in self.seen_zt_stocks:
                    fund_wan = float(item.get("seal_amount", 0.0) or 0.0) / 10000.0
                    lbc = int(item.get("continuous_boards", 1) or 1)
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
                        reason=reason
                    )
                    events.append(event)
                    # 更新已封板缓存
                    self.seen_zt_stocks[code] = item
        except Exception as e:
            print(f"[盘中监控封板查询异常] {e}")

        # -------------------------------------------------------------
        # 2. 检查【炸板开板】异动
        # -------------------------------------------------------------
        try:
            zb_pool = self.provider.fetch_today_zb_pool_details()
            for code, item in zb_pool.items():
                if not self.filter.is_main_board_code(code):
                    continue
                name = item.get("name", code)
                if not self.filter.is_valid_name(name):
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
                        fbt=fbt
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
                        continuous_boards=1,
                        action_advice=advice,
                        reason=reason
                    )
                    events.append(event)
                    # 更新炸板次数记录
                    self.seen_zb_stocks[code] = curr_zbc
                    # 炸板后从已封死列表中移除，便于后续回封时再次捕获
                    if code in self.seen_zt_stocks:
                        del self.seen_zt_stocks[code]
        except Exception as e:
            print(f"[盘中监控炸板查询异常] {e}")

        return events

    def _generate_limit_up_advice(
        self,
        lbc: int,
        fund_wan: float,
        zbc: int,
        is_reseal: bool,
        seal_time: str
    ) -> Tuple[str, str]:
        """输出涨停封板买入建议与原因"""
        if is_reseal:
            advice = "【建议：可轻仓打板/博烂板出妖】"
            reason = f"日内炸板 {zbc} 次后顽强回封，浮筹已在盘中充分换手换血，大单回封锁单 {fund_wan:.0f} 万元，次日享受弱转强高开溢价。"
        elif lbc >= 3:
            if fund_wan >= 4000:
                advice = "【建议：空间龙头可排板/做高标接力】"
                reason = f"主线空间总标杆强势晋级 {lbc} 连板！买一封单 {fund_wan:.0f} 万元极其硬朗，辨识度拉满，次日大概率加速一字或弱转强秒板。"
            else:
                advice = "【建议：谨慎排板/防高位炸板】"
                reason = f"虽晋级 {lbc} 板，但封单仅 {fund_wan:.0f} 万元偏薄，高位筹码一旦松动易出现大分歧，不建议盲目挂巨量排单。"
        elif lbc == 2:
            advice = "【建议：重点打板/参与 2 进 3 接力】"
            reason = f"1 进 2 换手晋级成功，确立身位优势。封单 {fund_wan:.0f} 万元，承接有力，符合主线接力标准。"
        else:
            # 首板
            if seal_time <= "10:00:00" and fund_wan >= 5000:
                advice = "【建议：早盘急速首板·可排板介入】"
                reason = f"早盘 {seal_time} 极速冲天炮秒板，主力抢筹极其果断，封单高达 {fund_wan:.0f} 万元，首板硬度极高，次日高溢价无忧。"
            elif fund_wan >= 2000:
                advice = "【建议：符合标准·可适度打板】"
                reason = f"封板形态良好，买一封单 {fund_wan:.0f} 万元，量能配合健康，具备较好持续性。"
            else:
                advice = "【建议：不建议打板/后排跟风】"
                reason = f"封单仅 {fund_wan:.0f} 万元偏弱，大概率属于板块后排跟风冲板，缺乏主动进攻性，谨防随时炸板。"

        return advice, reason

    def _generate_broken_board_advice(
        self,
        pct: float,
        hs: float,
        zbc: int,
        fbt: str
    ) -> Tuple[str, str]:
        """输出炸板开板买入建议与原因"""
        if pct >= 6.5:
            advice = "【建议：回踩均线低吸·博秒回封】"
            reason = f"炸板后价格仍坚守在 +{pct:.1f}% 高位震荡，未出现踩踏恐慌，换手率 {hs:.1f}% 良性，回踩分时均线不破可小仓位低吸博主力秒回封。"
        elif pct >= 2.0:
            advice = "【建议：观望不接飞刀·等待回封确认】"
            reason = f"炸板后回落至 +{pct:.1f}%，多空分歧巨大，上方套牢抛盘较重，此时买入容易反复吃面，必须等待大单重新回封再打板。"
        else:
            advice = "【建议：坚决规避·严防天地板大面】"
            reason = f"炸板后直线暴跌至 +{pct:.1f}%（甚至深水），主力大单恐慌砸盘出逃，筹码彻底瓦解崩溃，次日惯性下杀风险极大，坚决禁止抄底！"

        return advice, reason
