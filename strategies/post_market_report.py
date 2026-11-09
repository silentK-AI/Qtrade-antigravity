"""
15:10 盘后涨停复盘与次日打板预案分析策略模块
主要职责：
1. 梳理前一天涨停的股票在当天的完整表现（最高涨跌幅度、最低、收盘、换手、成交额）；
2. 识别连板高度，标注当前是几连板（2连板、3连板、高标空间板）；
3. 针对不同形态与筹码结构，输出第二天是否打板的明确操作指引（如：集合竞价弱转强打板、排板、低吸反包、坚决规避等）；
4. 统计全市场主板连板晋级率与梯队分布，定调明日打板总策略。
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from models.stock_item import YesterdayLimitUpItem, PostMarketReportData
from config import PostMarketReportConfig
from data.open_data_provider import OpenDataProvider


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

        # 1. 计算连板数
        consecutive_boards = raw_data.get("consecutive_boards")
        if consecutive_boards is None:
            consecutive_boards = self.provider.get_consecutive_board_count(code, is_today_limit_up)

        # 2. 诊断连板状态标签
        amplitude = high_pct - low_pct
        if is_today_limit_up:
            if amplitude < 0.2:
                board_status = f"【{consecutive_boards}连板·一字死封】"
            elif consecutive_boards >= 4:
                board_status = f"【{consecutive_boards}连板·高标总龙头】"
            elif consecutive_boards == 3:
                board_status = f"【3连板·主线核心龙头】"
            else:
                board_status = f"【2连板·换手晋级】"
        else:
            if close_pct >= 5.0:
                board_status = "【断板强冲高·收高位】"
            elif close_pct >= 0.0:
                board_status = "【断板冲高回落·收红】"
            elif close_pct >= -3.0:
                board_status = "【断板微跌震荡】"
            else:
                board_status = "【断板深水大面】"

        # 3. 生成次日打板操作建议与逻辑分析
        next_day_action, detail_reason = self._generate_advice(
            consecutive_boards=consecutive_boards,
            is_today_limit_up=is_today_limit_up,
            close_pct=close_pct,
            high_pct=high_pct,
            low_pct=low_pct,
            turnover_rate=turnover_rate,
            amplitude=amplitude
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
            detail_reason=detail_reason
        )

    def _generate_advice(
        self,
        consecutive_boards: int,
        is_today_limit_up: bool,
        close_pct: float,
        high_pct: float,
        low_pct: float,
        turnover_rate: float,
        amplitude: float
    ) -> (str, str):
        """
        基于 A 股经典打板与接力纪律，输出次日打板预案
        """
        if is_today_limit_up:
            # 缩量一字板
            if amplitude < 0.2:
                if consecutive_boards >= 3:
                    action = "【高位一字加速·严禁排板/次日警惕天地板】"
                    reason = f"已连续缩量一字顶至{consecutive_boards}板，筹码未换手，次日一旦分歧爆量开板极易引发主力抢跑，严禁打板接盘。"
                else:
                    action = "【强势一字板·次日若开板放量换手回封可排板】"
                    reason = "2板一字极度强势，次日若盘中开板给换手回踩机会，并在大买单回封瞬间可跟随排板。"
            # 高位连板龙头 (>= 3板)
            elif consecutive_boards >= 3:
                action = "【空间板龙头·次日关注集合竞价弱转强打板】"
                reason = f"主线标杆晋级{consecutive_boards}板，筹码换手良好。次日集合竞价若高开+2%~+5%且量能达标，可直接挂单打板。"
            # 2连板 (1进2成功)
            else:
                if turnover_rate > 28.0:
                    action = "【高换手二板·次日需大单高开确认才可打板】"
                    reason = "今日换手率偏高，筹码分歧较重。次日早盘必须高开在+3%以上且快速冲板，才可打板上车做3板。"
                else:
                    action = "【强势二板·次日重点做2进3接力打板】"
                    reason = "1进2成功确立身位，分时结构扎实，次日早盘集合竞价与开盘若承接有力，可作为主打标的参与打板。"
        else:
            # 断板但收高位 (> 5%)
            if close_pct >= 5.0 and turnover_rate <= 22.0:
                action = "【断板企稳·次日重点低吸博反包首板】"
                reason = "日内大单冲高后虽未封死，但收在全天高位且未破分时均线，主力未撤退，次日水下平开或-1%~-2%可低吸博反包首板。"
            # 冲高回落 (0% ~ 5%)
            elif close_pct >= 0.0:
                action = "【冲高回落断板·禁止打板/保持观望】"
                reason = f"日内最高冲至+{high_pct:.1f}%后遭获利盘大幅抛压，收盘仅+{close_pct:.1f}%，上方套牢盘较重，次日惯性承压，禁止追高打板。"
            # 大跌深水面 (< -3%)
            elif close_pct < -3.0:
                action = "【高位核按钮·深水大面/坚决规避】"
                reason = f"今日振幅达{amplitude:.1f}%，收大阴线杀跌，筹码结构严重破坏，次日大概率继续惯性补跌，坚决规避，严禁接飞刀。"
            # 微跌震荡 (-3% ~ 0%)
            else:
                action = "【缩量震荡断板·缺乏进攻性/不参与】"
                reason = "断板后多空僵持，日内缺乏大资金主动做多信号，次日难以形成涨停合力，观望为主。"

        return action, reason

    def run_report(self, raw_items: Optional[List[Dict[str, Any]]] = None) -> PostMarketReportData:
        """
        生成全套盘后复盘报告数据
        """
        if raw_items is None:
            raw_items = self.provider.fetch_yesterday_limit_up_pool()

        analyzed_items: List[YesterdayLimitUpItem] = []
        for raw in raw_items:
            item = self.analyze_item(raw)
            analyzed_items.append(item)

        # 排序：连板股排前面（连板数从大到小，再按涨幅降序），断板股排后面（按涨幅降序）
        continue_items = [x for x in analyzed_items if x.is_today_limit_up]
        broken_items = [x for x in analyzed_items if not x.is_today_limit_up]

        continue_items.sort(key=lambda x: (x.consecutive_boards, x.close_pct, x.amount_yi), reverse=True)
        broken_items.sort(key=lambda x: (x.close_pct, x.high_pct), reverse=True)

        all_sorted = continue_items + broken_items

        total_count = len(analyzed_items)
        continue_count = len(continue_items)
        broken_count = len(broken_items)
        advancement_rate = (continue_count / total_count * 100) if total_count > 0 else 0.0

        # 最高连板与梯队统计
        tier_distribution: Dict[int, int] = {}
        highest_board = 1
        highest_stock_name = "暂无连板"

        for item in continue_items:
            b = item.consecutive_boards
            tier_distribution[b] = tier_distribution.get(b, 0) + 1
            if b > highest_board:
                highest_board = b
                highest_stock_name = f"{item.name} ({item.code}) [{b}连板]"

        # 明日打板总基调判断
        if advancement_rate >= 45.0 and highest_board >= 3:
            sentiment_summary = "🔥【极佳做多期】连板晋级率高、高标空间打开，明日可积极参与前排核心龙头的打板接力！"
        elif advancement_rate >= 30.0:
            sentiment_summary = "⚖️【中性分歧期】晋级率适中，市场处于分歧换手阶段，明日只做核心题材前排，严禁后排杂毛跟风！"
        else:
            sentiment_summary = "❄️【冰点退潮期】晋级率偏低、大面亏损效应扩散，明日严格控仓防守，严禁盲目追高打板！"

        return PostMarketReportData(
            report_time=datetime.now().strftime("%Y-%m-%d 15:10"),
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
