"""
交易数据持久化存储 - SQLite

存储所有交易记录和每日资产快照，支持按 mode(live/paper/backtest) 区分。
"""
import os
import sqlite3
from datetime import datetime, date, timedelta
from typing import Optional
from loguru import logger

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "trades.db")


class TradeStore:
    """SQLite 交易数据存储"""

    def __init__(self, db_path: str = DB_PATH):
        self._db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        """初始化数据库表"""
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mode TEXT NOT NULL DEFAULT 'paper',
                    timestamp TEXT NOT NULL,
                    etf_code TEXT NOT NULL,
                    etf_name TEXT DEFAULT '',
                    side TEXT NOT NULL,
                    price REAL NOT NULL,
                    quantity INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    commission REAL DEFAULT 0,
                    pnl REAL DEFAULT 0,
                    reason TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS daily_summary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mode TEXT NOT NULL DEFAULT 'paper',
                    date TEXT NOT NULL,
                    start_assets REAL NOT NULL,
                    end_assets REAL NOT NULL,
                    pnl REAL NOT NULL,
                    pnl_pct REAL NOT NULL,
                    trade_count INTEGER DEFAULT 0,
                    win_trades INTEGER DEFAULT 0,
                    lose_trades INTEGER DEFAULT 0,
                    UNIQUE(mode, date)
                );

                CREATE TABLE IF NOT EXISTS market_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    etf_code TEXT NOT NULL,
                    price REAL NOT NULL,
                    iopv REAL NOT NULL,
                    momentum REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_trades_mode ON trades(mode);
                CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
                CREATE INDEX IF NOT EXISTS idx_trades_etf ON trades(etf_code);
                CREATE INDEX IF NOT EXISTS idx_daily_mode_date ON daily_summary(mode, date);
                CREATE INDEX IF NOT EXISTS idx_snapshots_mode_etf ON market_snapshots(mode, etf_code);
                CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON market_snapshots(timestamp);
            """)
            conn.commit()
            
            # 迁移：为旧数据库添加 commission 列
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN commission REAL DEFAULT 0")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # 已存在
        finally:
            conn.close()

    # ------------------------------------------------------------------
    #  写入
    # ------------------------------------------------------------------

    def record_trade(
        self,
        mode: str,
        timestamp: str,
        etf_code: str,
        etf_name: str,
        side: str,
        price: float,
        quantity: int,
        amount: float,
        commission: float = 0.0,
        pnl: float = 0.0,
        reason: str = "",
    ):
        """记录一笔交易"""
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO trades
                   (mode, timestamp, etf_code, etf_name, side, price, quantity, amount, commission, pnl, reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (mode, timestamp, etf_code, etf_name, side, price, quantity, amount, commission, pnl, reason),
            )
            conn.commit()
        finally:
            conn.close()

    def record_daily_summary(
        self,
        mode: str,
        trade_date: str,
        start_assets: float,
        end_assets: float,
        pnl: float,
        pnl_pct: float,
        trade_count: int = 0,
        win_trades: int = 0,
        lose_trades: int = 0,
    ):
        """记录每日盈亏汇总（始终从 trades 表中重新计算笔数和胜率）"""
        conn = self._get_conn()
        try:
            # 1. 从 trades 表中重新聚合当日数据（确保跨 session 准确）
            row = conn.execute(
                """SELECT 
                       COUNT(*) as cnt,
                       SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as loses
                   FROM trades 
                   WHERE mode = ? AND timestamp LIKE ?""",
                (mode, f"{trade_date}%"),
            ).fetchone()
            
            real_count = row["cnt"] or 0
            real_wins = row["wins"] or 0
            real_loses = row["loses"] or 0

            # 2. UPSERT 逻辑：如果已存在，保留最早的 start_assets，更新其他
            conn.execute(
                """INSERT INTO daily_summary
                   (mode, date, start_assets, end_assets, pnl, pnl_pct, trade_count, win_trades, lose_trades)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(mode, date) DO UPDATE SET
                       end_assets=excluded.end_assets,
                       pnl=excluded.pnl,
                       pnl_pct=excluded.pnl_pct,
                       trade_count=?,
                       win_trades=?,
                       lose_trades=?""",
                (mode, trade_date, start_assets, end_assets, pnl, pnl_pct, real_count, real_wins, real_loses,
                 real_count, real_wins, real_loses),
            )
            conn.commit()
        finally:
            conn.close()

    def get_day_summary(self, mode: str, trade_date: str) -> Optional[dict]:
        """获取特定日期的汇总（用于恢复 start_assets）"""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM daily_summary WHERE mode = ? AND date = ?",
                (mode, trade_date)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def record_snapshot(self, mode: str, etf_code: str, price: float, iopv: float, momentum: float, timestamp: Optional[str] = None):
        """记录一个行情快照"""
        conn = self._get_conn()
        try:
            ts = timestamp or datetime.now().isoformat()
            conn.execute(
                """INSERT INTO market_snapshots
                   (timestamp, mode, etf_code, price, iopv, momentum)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (ts, mode, etf_code, price, iopv, momentum),
            )
            conn.commit()
        finally:
            conn.close()

    def prune_snapshots(self, mode: str, keep_hours: int = 1):
        """定期清理旧快照"""
        conn = self._get_conn()
        try:
            cutoff = (datetime.now() - timedelta(hours=keep_hours)).isoformat()
            conn.execute(
                "DELETE FROM market_snapshots WHERE mode = ? AND timestamp < ?",
                (mode, cutoff),
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    #  查询
    # ------------------------------------------------------------------

    def get_trades(
        self,
        mode: str = "paper",
        etf_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 500,
    ) -> list[dict]:
        """查询交易记录"""
        conn = self._get_conn()
        try:
            sql = "SELECT * FROM trades WHERE mode = ?"
            params: list = [mode]

            if etf_code:
                sql += " AND etf_code = ?"
                params.append(etf_code)
            if start_date:
                sql += " AND timestamp >= ?"
                params.append(start_date + "T00:00:00")
            if end_date:
                sql += " AND timestamp <= ?"
                params.append(end_date + "T23:59:59")

            sql += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_daily_pnl(self, mode: str = "paper", start_date: str = None, end_date: str = None) -> list[dict]:
        """查询每日盈亏"""
        conn = self._get_conn()
        try:
            sql = "SELECT * FROM daily_summary WHERE mode = ?"
            params = [mode]
            if start_date:
                sql += " AND date >= ?"
                params.append(start_date)
            if end_date:
                sql += " AND date <= ?"
                params.append(end_date)
            sql += " ORDER BY date DESC"
            
            rows = conn.execute(sql, params).fetchall()
            result = [dict(r) for r in rows]
            result.reverse()  # 按日期正序
            return result
        finally:
            conn.close()

    def get_weekly_pnl(self, mode: str = "paper", weeks: int = 24) -> list[dict]:
        """查询每周盈亏（按自然周聚合）"""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT
                       strftime('%%Y-W%%W', date) AS week,
                       MIN(date) AS start_date,
                       MAX(date) AS end_date,
                       SUM(pnl) AS pnl,
                       SUM(trade_count) AS trade_count,
                       SUM(win_trades) AS win_trades,
                       SUM(lose_trades) AS lose_trades
                   FROM daily_summary
                   WHERE mode = ?
                   GROUP BY week
                   ORDER BY week DESC LIMIT ?""",
                (mode, weeks),
            ).fetchall()
            result = [dict(r) for r in rows]
            result.reverse()
            return result
        finally:
            conn.close()

    def get_monthly_pnl(self, mode: str = "paper", months: int = 12) -> list[dict]:
        """查询每月盈亏"""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT
                       strftime('%%Y-%%m', date) AS month,
                       SUM(pnl) AS pnl,
                       SUM(trade_count) AS trade_count,
                       SUM(win_trades) AS win_trades,
                       SUM(lose_trades) AS lose_trades
                   FROM daily_summary
                   WHERE mode = ?
                   GROUP BY month
                   ORDER BY month DESC LIMIT ?""",
                (mode, months),
            ).fetchall()
            result = [dict(r) for r in rows]
            result.reverse()
            return result
        finally:
            conn.close()

    def get_summary(self, mode: str = "paper", start_date: str = None, end_date: str = None) -> dict:
        """获取统计摘要"""
        conn = self._get_conn()
        try:
            # 构建过滤子句
            where_clause = "WHERE mode = ?"
            params = [mode]
            if start_date:
                where_clause += " AND date >= ?"
                params.append(start_date)
            if end_date:
                where_clause += " AND date <= ?"
                params.append(end_date)

            # 总盈亏
            row = conn.execute(
                f"""SELECT
                       COUNT(*) AS total_days,
                       COALESCE(SUM(pnl), 0) AS total_pnl,
                       COALESCE(SUM(trade_count), 0) AS total_trades,
                       COALESCE(SUM(win_trades), 0) AS total_wins,
                       COALESCE(SUM(lose_trades), 0) AS total_loses,
                       MIN(date) AS first_date,
                       MAX(date) AS last_date
                   FROM daily_summary {where_clause}""",
                tuple(params),
            ).fetchone()

            total_days = row["total_days"] or 0
            total_pnl = row["total_pnl"] or 0
            total_trades = row["total_trades"] or 0
            total_wins = row["total_wins"] or 0
            total_loses = row["total_loses"] or 0

            # 胜率（以天为单位）
            win_days = conn.execute(
                f"SELECT COUNT(*) FROM daily_summary {where_clause} AND pnl > 0",
                tuple(params),
            ).fetchone()[0]
            lose_days = conn.execute(
                f"SELECT COUNT(*) FROM daily_summary {where_clause} AND pnl < 0",
                tuple(params),
            ).fetchone()[0]

            # 交易维度的胜率
            trade_win_rate = total_wins / (total_wins + total_loses) * 100 if (total_wins + total_loses) > 0 else 0

            # 最大回撤 (改进版：包含起始资产)
            daily_data = conn.execute(
                f"SELECT start_assets, end_assets FROM daily_summary {where_clause} ORDER BY date",
                tuple(params),
            ).fetchall()

            max_drawdown = 0
            peak = 0
            if daily_data:
                peak = daily_data[0]["start_assets"]
                for d in daily_data:
                    # 考虑开盘资产和收盘资产
                    peak = max(peak, d["start_assets"], d["end_assets"])
                    if peak > 0:
                        dd_start = (peak - d["start_assets"]) / peak
                        dd_end = (peak - d["end_assets"]) / peak
                        max_drawdown = max(max_drawdown, dd_start, dd_end)

            day_win_rate = win_days / (win_days + lose_days) * 100 if (win_days + lose_days) > 0 else 0

            return {
                "mode": mode,
                "total_days": total_days,
                "total_pnl": round(total_pnl, 2),
                "total_trades": total_trades,
                "total_wins": total_wins,
                "total_loses": total_loses,
                "win_days": win_days,
                "lose_days": lose_days,
                "win_rate": round(day_win_rate, 1),
                "trade_win_rate": round(trade_win_rate, 1),
                "max_drawdown": round(max_drawdown * 100, 2),
                "first_date": row["first_date"] or "",
                "last_date": row["last_date"] or "",
            }
        finally:
            conn.close()

    def get_equity_curve(self, mode: str = "paper", start_date: str = None, end_date: str = None) -> list[dict]:
        """获取资金曲线数据"""
        conn = self._get_conn()
        try:
            sql = "SELECT date, end_assets FROM daily_summary WHERE mode = ?"
            params = [mode]
            if start_date:
                sql += " AND date >= ?"
                params.append(start_date)
            if end_date:
                sql += " AND date <= ?"
                params.append(end_date)
            sql += " ORDER BY date"
            
            rows = conn.execute(sql, params).fetchall()
            return [{"date": r["date"], "assets": r["end_assets"]} for r in rows]
        finally:
            conn.close()

    def get_recent_snapshots(self, mode: str, etf_code: str, limit: int = 3000) -> list[dict]:
        """获取最近的行情快照，并关联期间发生的交易记录"""
        conn = self._get_conn()
        try:
            # 1. 获取快照
            rows = conn.execute(
                """SELECT * FROM market_snapshots
                   WHERE mode = ? AND etf_code = ?
                   ORDER BY timestamp DESC, rowid DESC LIMIT ?""",
                (mode, etf_code, limit),
            ).fetchall()
            snapshots = [dict(r) for r in rows]
            if not snapshots:
                return []

            snapshots.reverse()  # 恢复正序
            start_ts = snapshots[0]["timestamp"]
            end_ts = snapshots[-1]["timestamp"]

            # 2. 获取该时间段内的交易记录
            trade_rows = conn.execute(
                """SELECT timestamp, side, price FROM trades
                   WHERE mode = ? AND etf_code = ?
                   AND timestamp >= ? AND timestamp <= ?""",
                (mode, etf_code, start_ts, end_ts),
            ).fetchall()
            trades = [dict(r) for r in trade_rows]

            # 3. 将交易标记匹配到最接近的快照上
            # 预处理：清除快照中可能存在的旧标记（如果是在内存中复用对象）
            for s in snapshots:
                s["trade_side"] = None
                s["trade_price"] = None

            for trade in trades:
                trade_ts = datetime.fromisoformat(trade["timestamp"])
                
                # 寻找最接近的快照
                best_snapshot = None
                min_diff = 999999
                
                for s in snapshots:
                    try:
                        snap_ts = datetime.fromisoformat(s["timestamp"])
                        diff = abs((trade_ts - snap_ts).total_seconds())
                        if diff < min_diff:
                            min_diff = diff
                            best_snapshot = s
                    except Exception:
                        continue
                
                # 如果在 10 秒内找到匹配项，则标记（如果已有标记，保留更近的，或者简单覆盖）
                if best_snapshot and min_diff < 10:
                    best_snapshot["trade_side"] = trade["side"]
                    best_snapshot["trade_price"] = trade["price"]
                    best_snapshot["trade_reason"] = trade.get("reason", "")

            return snapshots
        finally:
            conn.close()
    def get_symbol_stats(self, mode: str = "paper", start_date: str = None, end_date: str = None) -> dict:
        """获取分标的的盈亏统计和曲线数据"""
        conn = self._get_conn()
        try:
            # 1. 查询该时段内所有已完成的卖出交易（用于计算 PnL）
            sql = "SELECT etf_code, etf_name, timestamp, pnl FROM trades WHERE mode = ? AND side = 'SELL'"
            params = [mode]
            if start_date:
                sql += " AND timestamp >= ?"
                params.append(start_date + "T00:00:00")
            if end_date:
                sql += " AND timestamp <= ?"
                params.append(end_date + "T23:59:59")
            sql += " ORDER BY timestamp ASC"
            
            rows = conn.execute(sql, params).fetchall()
            
            stats = {}
            for r in rows:
                code = r["etf_code"]
                if code not in stats:
                    stats[code] = {
                        "code": code,
                        "name": r["etf_name"],
                        "total_pnl": 0.0,
                        "pnl_history": [] # 记录累计盈亏曲线
                    }
                
                stats[code]["total_pnl"] += r["pnl"]
                # 记录每一个时间点的累计盈亏
                stats[code]["pnl_history"].append({
                    "timestamp": r["timestamp"],
                    "cumulative_pnl": round(stats[code]["total_pnl"], 3)
                })
            
            # 格式化输出为列表以便前端处理
            result = sorted(stats.values(), key=lambda x: x["total_pnl"], reverse=True)
            return result
        finally:
            conn.close()
