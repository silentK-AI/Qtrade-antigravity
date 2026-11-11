"""
15:10 盘后涨停复盘与次日打板预案分析策略模块
主要职责：
1. 梳理前一天涨停的股票在当天的完整表现（最高涨跌幅度、最低、收盘、换手、成交额）；
2. 识别连板高度，标注当前是几连板（2连板、3连板、高标空间板）；
3. 针对不同形态与筹码结构，输出第二天是否打板的明确操作指引（如：集合竞价弱转强打板、排板、低吸反包、坚决规避等）；
4. 统计全市场主板连板晋级率与梯队分布，定调明日打板总策略。
"""

from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from models.stock_item import YesterdayLimitUpItem, PostMarketReportData
from config import PostMarketReportConfig
from data.open_data_provider import OpenDataProvider
from utils.calendar import get_beijing_now
from utils.filters import StockFilter


class PostMarketReportScreener:
    """15:10 盘后涨停复盘与打板预案生成器"""

    def __init__(self, config: Optional[PostMarketReportConfig] = None):
        self.config = config or PostMarketReportConfig()
        self.provider = OpenDataProvider()

    def analyze_item(self, raw_data: Dict[str, Any]) -> YesterdayLimitUpItem:
        """
        对单只昨日涨停股票进行综合量化诊断并生成次日打板预案
        """
        code = raw_data["code"]
        name = raw_data["name"]
        close_price = raw_data["close_price"]
        close_pct = raw_data["close_pct"]
        high_pct = raw_data["high_pct"]
        low_pct = raw_data["low_pct"]
        turnover_rate = raw_data["turnover_rate"]
        amount_yi = raw_data["amount_yi"]
        float_cap_yi = raw_data.get("float_cap_yi", 0.0)
        is_today_limit_up = raw_data.get("is_today_limit_up", False)

        # 1. 计算连板数与昨日连板基数（仅聚焦 1进2 / 2进3 / 3进4）
        yesterday_boards = int(raw_data.get("yesterday_boards") or 0)
        consecutive_boards = raw_data.get("consecutive_boards")
        if consecutive_boards is None:
            if yesterday_boards > 0:
                consecutive_boards = yesterday_boards + 1 if is_today_limit_up else yesterday_boards
            else:
                consecutive_boards = self.provider.get_consecutive_board_count(code, is_today_limit_up)
        else:
            consecutive_boards = int(consecutive_boards)

        if yesterday_boards <= 0:
            yesterday_boards = (consecutive_boards - 1) if is_today_limit_up else consecutive_boards

        relay_tag = StockFilter.format_relay_label(yesterday_boards) or f"{consecutive_boards}板"

        # 2. 诊断连板状态标签
        amplitude = high_pct - low_pct
        if is_today_limit_up:
            if amplitude < 0.2:
                board_status = f"【{consecutive_boards}连板·{relay_tag}一字死封】"
            elif consecutive_boards == 4:
                board_status = f"【4连板·3进4强势晋级】"
            elif consecutive_boards == 3:
                board_status = f"【3连板·2进3主线卡位】"
            else:
                board_status = f"【2连板·1进2换手晋级】"
        else:
            if close_pct >= 5.0:
                board_status = f"【{relay_tag}断板·收高位】"
            elif close_pct >= 0.0:
                board_status = f"【{relay_tag}断板·冲高回落】"
            elif close_pct >= -3.0:
                board_status = f"【{relay_tag}断板·微跌震荡】"
            else:
                board_status = f"【{relay_tag}断板·深水大面】"

        # 3. 生成次日打板操作建议与逻辑分析
        next_day_action, detail_reason = self._generate_advice(
            consecutive_boards=consecutive_boards,
            is_today_limit_up=is_today_limit_up,
            close_pct=close_pct,
            high_pct=high_pct,
            low_pct=low_pct,
            turnover_rate=turnover_rate,
            amplitude=amplitude,
            yesterday_boards=yesterday_boards
        )

        return YesterdayLimitUpItem(
            code=code,
            name=name,
            close_price=close_price,
            close_pct=close_pct,
            high_pct=high_pct,
            low_pct=low_pct,
            turnover_rate=turnover_rate,
            amount_yi=amount_yi,
            float_cap_yi=float_cap_yi,
            consecutive_boards=consecutive_boards,
            is_today_limit_up=is_today_limit_up,
            board_status=board_status,
            next_day_action=next_day_action,
            detail_reason=detail_reason,
            yesterday_boards=yesterday_boards
        )

    def _generate_advice(
        self,
        consecutive_boards: int,
        is_today_limit_up: bool,
        close_pct: float,
        high_pct: float,
        low_pct: float,
        turnover_rate: float,
        amplitude: float,
        yesterday_boards: int = 1
    ) -> Tuple[str, str]:
        """
        基于 A 股 1进2 / 2进3 / 3进4 连板纪律，输出次日打板预案
        """
        relay_tag = StockFilter.format_relay_label(yesterday_boards) or f"{consecutive_boards}板"
        if is_today_limit_up:
            # 3进4 已晋级 4连板 -> 次日为 4进5，超出系统接力梯队
            if consecutive_boards >= 4:
                action = "【3进4已兑现·次日超4板不再新开接力】"
                reason = f"今日成功晋级{consecutive_boards}连板（3进4），明日进入4进5高危博弈区，超出系统1进2/2进3/3进4范围，持筹者可顺势止盈、次日不再打板。"
            # 缩量一字板 (2板 / 3板)
            elif amplitude < 0.2:
                if consecutive_boards == 3:
                    action = "【2进3一字加速·明日3进4严禁无量顶一字排单】"
                    reason = "已连续一字顶至3板，筹码未充分换手，次日3进4一旦放量爆开易引发获利盘抢跑，需见充分换手回封方能谨慎观察。"
                else:
                    action = "【1进2强势一字·次日2进3若开板放量回封可排板】"
                    reason = "2板一字极度强势，次日若盘中开板给换手回踩机会，并在大买单回封瞬间可跟随做2进3接力。"
            # 3连板 (2进3成功 -> 次日看 3进4)
            elif consecutive_boards == 3:
                action = "【2进3成功·次日重点观察3进4弱转强打板】"
                reason = "主线标杆顺利晋级3连板（2进3），筹码换手良好。次日集合竞价若高开+2%~+5%且量能达标，可作为3进4核心观察。"
            # 2连板 (1进2成功 -> 次日看 2进3)
            else:
                if turnover_rate > 28.0:
                    action = "【高换手二板·次日2进3需大单高开确认才可打板】"
                    reason = "今日1进2换手率偏高，筹码分歧较重。次日早盘必须高开在+3%以上且快速冲板，才可打板上车做2进3。"
                else:
                    action = "【强势二板·次日重点做2进3接力打板】"
                    reason = "1进2成功确立身位，分时结构扎实，次日早盘集合竞价与开盘若承接有力，可作为主打标的参与2进3接力。"
        else:
            # 断板但收高位 (> 5%)
            if close_pct >= 5.0 and turnover_rate <= 22.0:
                action = f"【{relay_tag}断板收强·已脱离连板梯队/不打连板】"
                reason = f"日内冲击{relay_tag}虽未封死但收在全天高位，因已断板不再属于1进2/2进3/3进4连板接力范围，次日不再新开打板。"
            # 冲高回落 (0% ~ 5%)
            elif close_pct >= 0.0:
                action = f"【{relay_tag}冲高回落断板·禁止打板/观望】"
                reason = f"日内冲击{relay_tag}最高冲至+{high_pct:.1f}%后遭抛压回落至+{close_pct:.1f}%，上方套牢盘较重，禁止追高。"
            # 大跌深水面 (< -3%)
            elif close_pct < -3.0:
                action = f"【{relay_tag}断板核按钮·深水大面/坚决规避】"
                reason = f"今日振幅达{amplitude:.1f}%，收大阴线杀跌，筹码结构严重破坏，坚决规避，严禁接飞刀。"
            # 微跌震荡 (-3% ~ 0%)
            else:
                action = f"【{relay_tag}缩量震荡断板·不参与】"
                reason = "断板后多空僵持，日内缺乏大资金主动封板合力，观望为主。"

        return action, reason

    def run_report(self, raw_items: Optional[List[Dict[str, Any]]] = None) -> PostMarketReportData:
        """
        生成全套盘后复盘报告数据：
        - 顶部大局观统计（昨日涨停总数、连板数、断板数、晋级率、最高板、全梯队分布）保留全市场真实数据；
        - 下方个股复盘与预案列表（report.items）严格仅梳理 1进2 / 2进3 / 3进4 标的。
        """
        is_live = (raw_items is None)
        if raw_items is None:
            raw_items = self.provider.fetch_yesterday_limit_up_pool() or []

        prev_zt: Dict[str, int] = {}
        today_zt_pool: Dict[str, Dict[str, Any]] = {}
        if is_live:
            try:
                prev_zt = self.provider.fetch_prev_day_zt_boards() or {}
            except Exception:
                prev_zt = {}
            try:
                today_zt_pool = self.provider.fetch_today_zt_pool_details() or {}
            except Exception:
                today_zt_pool = {}

        # 1. 全市场真实大局观汇总 + 筛选 1进2 / 2进3 / 3进4 目标梳理池
        total_count = 0
        continue_count = 0
        broken_count = 0
        tier_distribution: Dict[int, int] = {}
        highest_board = 1
        highest_stock_name = "暂无连板"

        analyzed_items: List[YesterdayLimitUpItem] = []

        for raw in raw_items:
            code = raw.get("code", "")
            name = raw.get("name", code)
            is_lu = bool(raw.get("is_today_limit_up", False))
            total_count += 1

            yb = int(raw.get("yesterday_boards") or prev_zt.get(code, 0) or 0)
            cb = raw.get("consecutive_boards")

            if is_lu:
                if cb is None:
                    if code in today_zt_pool:
                        cb = int(today_zt_pool[code].get("continuous_boards", 2) or 2)
                    elif yb > 0:
                        cb = yb + 1
                    else:
                        cb = self.provider.get_consecutive_board_count(code, True)
                else:
                    cb = int(cb)

                if yb <= 0:
                    yb = max(0, cb - 1)

                continue_count += 1
                tier_distribution[cb] = tier_distribution.get(cb, 0) + 1
                if cb > highest_board:
                    highest_board = cb
                    highest_stock_name = f"{name} ({code}) [{cb}连板]"
            else:
                broken_count += 1
                if cb is not None:
                    cb = int(cb)
                if yb <= 0 and (not is_live) and cb is not None:
                    yb = cb

            # 严格过滤：个股复盘明细列表仅保留 1进2 / 2进3 / 3进4 标的
            if yb not in StockFilter.ALLOWED_YESTERDAY_BOARDS:
                continue
            if is_lu and cb not in StockFilter.ALLOWED_TODAY_BOARDS:
                continue

            raw_enriched = dict(raw)
            raw_enriched["yesterday_boards"] = yb
            if cb is not None:
                raw_enriched["consecutive_boards"] = cb

            item = self.analyze_item(raw_enriched)
            if item.yesterday_boards not in StockFilter.ALLOWED_YESTERDAY_BOARDS:
                continue
            if item.is_today_limit_up and item.consecutive_boards not in StockFilter.ALLOWED_TODAY_BOARDS:
                continue
            analyzed_items.append(item)

        # 排序：连板股排前面（连板数从大到小，再按涨幅降序），断板股排后面（按涨幅降序）
        continue_items = [x for x in analyzed_items if x.is_today_limit_up]
        broken_items = [x for x in analyzed_items if not x.is_today_limit_up]

        continue_items.sort(key=lambda x: (x.consecutive_boards, x.close_pct, x.amount_yi), reverse=True)
        broken_items.sort(key=lambda x: (x.close_pct, x.high_pct), reverse=True)

        all_sorted = continue_items + broken_items
        advancement_rate = (continue_count / total_count * 100) if total_count > 0 else 0.0

        # 明日打板总基调判断
        if advancement_rate >= 45.0 and highest_board >= 3:
            sentiment_summary = "🔥【极佳做多期】连板晋级率高、高标空间打开，明日可积极参与前排核心龙头的打板接力！"
        elif advancement_rate >= 30.0:
            sentiment_summary = "⚖️【中性分歧期】晋级率适中，市场处于分歧换手阶段，明日只做核心题材前排，严禁后排杂毛跟风！"
        else:
            sentiment_summary = "❄️【冰点退潮期】晋级率偏低、大面亏损效应扩散，明日严格控仓防守，严禁盲目追高打板！"

        return PostMarketReportData(
            report_time=get_beijing_now().strftime("%Y-%m-%d 15:10"),
            total_yesterday_count=total_count,
            today_continue_count=continue_count,
            broken_board_count=broken_count,
            advancement_rate=advancement_rate,
            highest_board=highest_board,
            highest_board_stock=highest_stock_name,
            tier_distribution=tier_distribution,
            sentiment_summary=sentiment_summary,
            items=all_sorted[:self.config.MAX_DISPLAY_ITEMS]
        )
