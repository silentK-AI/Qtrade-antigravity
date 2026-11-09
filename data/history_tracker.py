"""
量化策略选股信号持久化与战绩闭环追踪模块
核心功能：
1. 每日关键时段（09:23, 09:25, 14:50, 14:58）自动留痕推荐标的；
2. 15:10 盘后自动对照昨日系统推荐标的在当天的真实盘面表现；
3. 计算策略次日胜率（收红率、涨停率、平均最高冲高幅度），实现量化策略自我复盘闭环。
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from models.stock_item import StrategySignal, StockQuote
from utils.logger import get_logger

logger = get_logger("history_tracker")

HISTORY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "logs",
    "signal_history.json"
)


class SignalHistoryTracker:
    """策略历史信号与实战战绩追踪器"""

    def __init__(self, file_path: str = HISTORY_FILE):
        self.file_path = file_path
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

    def _load_history(self) -> Dict[str, Any]:
        """读取历史记录 JSON"""
        if not os.path.exists(self.file_path) or os.path.getsize(self.file_path) == 0:
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"读取历史推荐记录失败: {e}")
            return {}

    def _save_history(self, data: Dict[str, Any]):
        """持久化保存历史记录 JSON"""
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"持久化历史推荐记录失败: {e}")

    def record_signals(
        self,
        task_type: str,
        signals: List[StrategySignal],
        date_str: Optional[str] = None
    ):
        """
        保存某时段策略筛选出的优质标的（综合分 >= 80）
        """
        if not signals:
            return

        today = date_str or datetime.now().strftime("%Y-%m-%d")
        now_time = datetime.now().strftime("%H:%M:%S")

        history = self._load_history()
        if today not in history:
            history[today] = {}

        items = []
        for s in signals[:6]:  # 仅记录前排核心高分标的
            items.append({
                "code": s.code,
                "name": s.name,
                "score": s.score,
                "capital_score": s.capital_score,
                "rec_price": s.current_price,
                "rec_pct": s.change_pct,
                "pattern": s.target_pattern,
                "action": s.suggested_action,
                "time": now_time
            })

        history[today][task_type] = items
        self._save_history(history)
        logger.info(f"[{today} {task_type}] 已成功归档 {len(items)} 只策略推荐标的供次日胜率复盘！")

    def evaluate_recent_signals(
        self,
        provider: Any,
        today_str: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        在 15:10 盘后自动复盘「上一个推荐日」推送标的在今天的真实表现
        """
        today = today_str or datetime.now().strftime("%Y-%m-%d")
        history = self._load_history()

        # 找到在 today 之前的最近一个记录日
        past_dates = sorted([d for d in history.keys() if d < today], reverse=True)
        if not past_dates:
            return None

        last_date = past_dates[0]
        day_tasks = history[last_date]

        # 收集该日推荐的所有标的 (优先 14:58, 14:50, 09:23)
        stocks_map: Dict[str, Dict[str, Any]] = {}
        for t_type in ["1458", "1450", "0923", "0925"]:
            for item in day_tasks.get(t_type, []):
                code = item["code"]
                if code not in stocks_map:
                    stocks_map[code] = {**item, "task_type": t_type}

        if not stocks_map:
            return None

        # 批量拉取今天这批股票的最新收盘行情
        codes = list(stocks_map.keys())
        try:
            today_quotes = provider.fetch_realtime_quotes(codes)
            quote_dict: Dict[str, StockQuote] = {q.code: q for q in today_quotes}
        except Exception as e:
            logger.warning(f"复盘拉取行情失败: {e}")
            return None

        eval_items = []
        zt_count = 0
        up_count = 0
        total_max_gain = 0.0

        for code, info in stocks_map.items():
            q = quote_dict.get(code)
            if not q:
                continue

            max_gain = ((q.high_price - q.pre_close) / q.pre_close * 100.0) if q.pre_close > 0 else q.change_pct
            close_pct = q.change_pct
            is_zt = (q.is_limit_up or close_pct >= 9.85)

            if is_zt:
                zt_count += 1
            if close_pct > 0:
                up_count += 1
            total_max_gain += max_gain

            eval_items.append({
                "code": code,
                "name": info["name"],
                "rec_time": f"{info['task_type']}时段",
                "rec_price": info["rec_price"],
                "today_close": q.current_price,
                "today_pct": close_pct,
                "max_gain": max_gain,
                "is_limit_up": is_zt
            })

        total = len(eval_items)
        if total == 0:
            return None

        win_rate = (up_count / total * 100.0)
        zt_rate = (zt_count / total * 100.0)
        avg_max_gain = (total_max_gain / total)

        return {
            "record_date": last_date,
            "total_count": total,
            "zt_count": zt_count,
            "up_count": up_count,
            "win_rate": win_rate,
            "zt_rate": zt_rate,
            "avg_max_gain": avg_max_gain,
            "items": eval_items
        }
