"""
持仓管理器 - 跟踪多标的持仓状态和交易计数
"""
from datetime import datetime, date
from typing import Optional
from loguru import logger

from strategy.signal import Position, OrderSide
from config.etf_settings import INITIAL_CAPITAL, ETF_COMMISSION_RATE
from monitor.trade_store import TradeStore


class PositionManager:
    """管理所有标的的持仓和资金状态"""

    def __init__(self, initial_capital: float = INITIAL_CAPITAL):
        self._initial_capital = initial_capital
        self._cash = initial_capital
        self._positions: dict[str, Position] = {}  # {etf_code: Position}
        self._daily_trade_count: dict[str, int] = {}  # {etf_code: count}
        self._trade_date: Optional[date] = None
        self._trade_history: list[dict] = []  # 交易记录
        self._mode: str = "paper"  # live / paper / backtest
        self._trade_store: Optional[TradeStore] = None
        self._day_start_assets: float = initial_capital  # 当日开始资产
        self._last_trade_time: dict[str, datetime] = {}  # {etf_code: last_timestamp}

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def positions(self) -> dict[str, Position]:
        return self._positions.copy()

    @property
    def total_market_value(self) -> float:
        """全部持仓市值"""
        return sum(p.market_value for p in self._positions.values())

    @property
    def total_assets(self) -> float:
        """总资产 = 现金 + 持仓市值"""
        return self._cash + self.total_market_value

    @property
    def total_position_pct(self) -> float:
        """总仓位占比"""
        total = self.total_assets
        if total == 0:
            return 0.0
        return self.total_market_value / total

    def get_position(self, etf_code: str) -> Optional[Position]:
        """获取某标的的持仓"""
        return self._positions.get(etf_code)

    def has_position(self, etf_code: str) -> bool:
        """是否持有某标的"""
        pos = self._positions.get(etf_code)
        return pos is not None and pos.quantity > 0

    def get_daily_trade_count(self, etf_code: str) -> int:
        """获取某标的当日交易次数"""
        self._check_new_day()
        return self._daily_trade_count.get(etf_code, 0)

    def get_last_trade_time(self, etf_code: str) -> Optional[datetime]:
        """获取某标的最后一笔交易的时间"""
        return self._last_trade_time.get(etf_code)

    def get_position_pct(self, etf_code: str) -> float:
        """获取某标的仓位占总资产比例"""
        pos = self._positions.get(etf_code)
        if pos is None:
            return 0.0
        total = self.total_assets
        if total == 0:
            return 0.0
        return pos.market_value / total

    # ------------------------------------------------------------------
    #  交易操作
    # ------------------------------------------------------------------

    def open_position(
        self,
        etf_code: str,
        etf_name: str,
        price: float,
        quantity: int,
        reason: str = "",
        timestamp: Optional[datetime] = None,
    ) -> bool:
        """
        开仓（买入）。

        Returns:
            是否成功
        """
        cost = price * quantity
        commission = cost * ETF_COMMISSION_RATE
        total_buy_cost = cost + commission
        
        if total_buy_cost > self._cash:
            logger.warning(f"[{etf_code}] 资金不足（含佣金）: 需{total_buy_cost:.2f}, 可用{self._cash:.2f}")
            return False

        self._cash -= total_buy_cost
        self._check_new_day()
        self._daily_trade_count[etf_code] = self._daily_trade_count.get(etf_code, 0) + 1

        if etf_code in self._positions:
            # 加仓
            pos = self._positions[etf_code]
            # 更新均价（包含本次佣金）
            new_total_cost = pos.avg_cost * pos.quantity + total_buy_cost
            total_qty = pos.quantity + quantity
            pos.avg_cost = new_total_cost / total_qty
            pos.quantity = total_qty
            pos.current_price = price
            pos.highest_price = max(pos.highest_price, price)
        else:
            # 新建仓位（均价包含佣金）
            self._positions[etf_code] = Position(
                etf_code=etf_code,
                etf_name=etf_name,
                quantity=quantity,
                avg_cost=total_buy_cost / quantity,
                current_price=price,
                highest_price=price,
                open_time=timestamp or datetime.now(),
            )

        self._record_trade(etf_code, etf_name, OrderSide.BUY, price, quantity, commission=commission, reason=reason, timestamp=timestamp)
        logger.info(
            f"[{etf_code}] 买入 {quantity}股 @ {price:.3f} | "
            f"佣金: {commission:.2f} | 现金余额: {self._cash:.2f}"
        )
        return True

    def close_position(
        self,
        etf_code: str,
        price: float,
        quantity: Optional[int] = None,
        reason: str = "",
        timestamp: Optional[datetime] = None,
    ) -> bool:
        """
        平仓（卖出）。

        Args:
            etf_code: ETF 代码
            price: 卖出价格
            quantity: 卖出数量，None 则全部卖出

        Returns:
            是否成功
        """
        pos = self._positions.get(etf_code)
        if pos is None or pos.quantity <= 0:
            logger.warning(f"[{etf_code}] 无持仓可平")
            return False

        sell_qty = quantity or pos.quantity
        sell_qty = min(sell_qty, pos.quantity)

        proceeds = price * sell_qty
        commission = proceeds * ETF_COMMISSION_RATE
        net_proceeds = proceeds - commission
        
        self._cash += net_proceeds
        self._check_new_day()
        self._daily_trade_count[etf_code] = self._daily_trade_count.get(etf_code, 0) + 1

        # 盈亏计算（avg_cost 已包含买入佣金，此处扣除卖出佣金）
        pnl = net_proceeds - (pos.avg_cost * sell_qty)
        pnl_pct = pnl / (pos.avg_cost * sell_qty) * 100

        pos.quantity -= sell_qty
        if pos.quantity <= 0:
            del self._positions[etf_code]

        self._record_trade(etf_code, pos.etf_name, OrderSide.SELL, price, sell_qty, commission=commission, pnl=pnl, reason=reason, timestamp=timestamp)
        logger.info(
            f"[{etf_code}] 卖出 {sell_qty}股 @ {price:.3f} | "
            f"佣金: {commission:.2f} | 盈亏: {pnl:+.2f} ({pnl_pct:+.2f}%) | "
            f"现金余额: {self._cash:.2f}"
        )
        return True

    def update_prices(self, price_map: dict[str, float]) -> None:
        """更新所有持仓的当前价格"""
        for code, price in price_map.items():
            pos = self._positions.get(code)
            if pos and price > 0:
                pos.current_price = price
                pos.highest_price = max(pos.highest_price, price)

    def close_all(self, price_map: dict[str, float]) -> None:
        """平掉所有持仓"""
        for code in list(self._positions.keys()):
            price = price_map.get(code, self._positions[code].current_price)
            self.close_position(code, price)

    def set_mode(self, mode: str) -> None:
        """设置交易模式 (live/paper/backtest)"""
        self._mode = mode

    def set_store(self, store: TradeStore) -> None:
        """设置持久化存储"""
        self._trade_store = store

    def reset_daily(self) -> None:
        """每日重置（交易计数等）"""
        self._daily_trade_count.clear()
        self._trade_date = date.today()
        
        # 尝试从数据库恢复今日的初始资产，确保跨重启盈亏一致
        if self._trade_store:
            today_str = self._trade_date.isoformat()
            summary = self._trade_store.get_day_summary(self._mode, today_str)
            if summary:
                self._day_start_assets = summary["start_assets"]
                logger.info(f"持仓管理器 - 从数据库恢复今日初始资产: {self._day_start_assets:.2f}")
            else:
                self._day_start_assets = self.total_assets
                logger.info(f"持仓管理器 - 开启新交易日，初始资产: {self._day_start_assets:.2f}")
        else:
            self._day_start_assets = self.total_assets
            logger.info("持仓管理器 - 每日状态已重置")

    def save_daily_summary(self, trade_date: Optional[date] = None) -> None:
        """保存当日盈亏汇总到数据库"""
        if self._trade_store is None:
            return
        d = trade_date or date.today()
        end_assets = self.total_assets
        pnl = end_assets - self._day_start_assets
        pnl_pct = pnl / self._day_start_assets * 100 if self._day_start_assets > 0 else 0
        trade_count = sum(self._daily_trade_count.values())
        # 简单统计：用当日交易记录中的 pnl
        today_trades = [
            t for t in self._trade_history
            if t.get("timestamp", "")[:10] == d.isoformat()
            and t.get("side") == "SELL"
        ]
        win_trades = sum(1 for t in today_trades if t.get("pnl", 0) > 0)
        lose_trades = sum(1 for t in today_trades if t.get("pnl", 0) < 0)

        self._trade_store.record_daily_summary(
            mode=self._mode,
            trade_date=d.isoformat(),
            start_assets=self._day_start_assets,
            end_assets=end_assets,
            pnl=pnl,
            pnl_pct=pnl_pct,
            trade_count=trade_count,
            win_trades=win_trades,
            lose_trades=lose_trades,
        )

    def get_trade_history(self) -> list[dict]:
        """获取交易历史"""
        return self._trade_history.copy()

    def get_summary(self) -> dict:
        """获取持仓概要"""
        return {
            "cash": self._cash,
            "total_market_value": self.total_market_value,
            "total_assets": self.total_assets,
            "total_position_pct": f"{self.total_position_pct * 100:.1f}%",
            "positions": {
                code: {
                    "name": pos.etf_name,
                    "qty": pos.quantity,
                    "avg_cost": pos.avg_cost,
                    "current": pos.current_price,
                    "pnl": f"{pos.pnl:+.2f}",
                    "pnl_pct": f"{pos.pnl_pct * 100:+.2f}%",
                }
                for code, pos in self._positions.items()
            },
            "daily_trades": dict(self._daily_trade_count),
            "total_trades_today": sum(self._daily_trade_count.values()),
        }

    # ------------------------------------------------------------------
    #  内部方法
    # ------------------------------------------------------------------

    def _check_new_day(self) -> None:
        """检查是否新交易日，如果是则重置交易计数"""
        today = date.today()
        if self._trade_date != today:
            self._trade_date = today
            self._daily_trade_count.clear()

    def _record_trade(
        self, etf_code: str, etf_name: str,
        side: OrderSide, price: float, quantity: int,
        commission: float = 0.0, pnl: float = 0.0, reason: str = "",
        timestamp: Optional[datetime] = None,
    ) -> None:
        """记录交易"""
        now = timestamp or datetime.now()
        ts = now.isoformat()
        amount = price * quantity
        record = {
            "timestamp": ts,
            "etf_code": etf_code,
            "etf_name": etf_name,
            "side": side.value,
            "price": price,
            "quantity": quantity,
            "amount": amount,
            "commission": commission,
            "pnl": pnl,
            "reason": reason,
        }
        self._trade_history.append(record)
        self._last_trade_time[etf_code] = datetime.fromisoformat(ts)

        # 持久化到 SQLite
        if self._trade_store:
            self._trade_store.record_trade(
                mode=self._mode,
                timestamp=ts,
                etf_code=etf_code,
                etf_name=etf_name,
                side=side.value,
                price=price,
                quantity=quantity,
                amount=amount,
                commission=commission,
                pnl=pnl,
                reason=reason,
            )
