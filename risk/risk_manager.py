"""
风控引擎 - 统一管理所有风控规则
"""
from datetime import datetime, time as dtime
from typing import Optional
from loguru import logger

from strategy.signal import MarketSnapshot, TradingSignal, SignalType, TradeOrder, OrderSide
from risk.position_manager import PositionManager
from config.settings import (
    TAKE_PROFIT_PCT,
    STOP_LOSS_PCT,
    TRAILING_STOP_PCT,
    MAX_DAILY_TRADES,
    MAX_POSITION_PCT,
    MAX_TOTAL_POSITION_PCT,
    FORCE_CLOSE_TIME,
    NO_OPEN_AFTER,
    GLOBAL_TRADE_COOLDOWN_SECONDS,
)


class RiskManager:
    """
    风控引擎。

    负责在策略信号转化为交易指令之前/之后进行风控检查：
    - 止盈 / 止损 / 跟踪止损
    - 日交易次数限制
    - 仓位比例限制
    - 时间限制（禁止开仓 / 强制清仓）
    """

    def __init__(self, position_manager: PositionManager):
        self._pm = position_manager
        # 价格历史记录 (用于计算动态波动率)
        from collections import deque
        self._price_history: dict[str, deque] = {}

    def _update_volatility(self, etf_code: str, snapshot: MarketSnapshot):
        """记录价格及其高低位，用于计算精准 ATR"""
        if etf_code not in self._price_history:
            const_deque = __import__('collections').deque
            self._price_history[etf_code] = const_deque(maxlen=30)
        
        # 记录 (最高, 最低, 收盘)
        self._price_history[etf_code].append((
            snapshot.etf_high or snapshot.etf_price,
            snapshot.etf_low or snapshot.etf_price,
            snapshot.etf_price
        ))

    def _get_atr(self, etf_code: str, period: int = 14) -> float:
        """获取最近价格波幅参考 (ATR - Average True Range)"""
        history = self._price_history.get(etf_code)
        if not history or len(history) < period + 1:
            return 0.0
        
        # 计算每一笔的 True Range (TR)
        # TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list = []
        hist_list = list(history)
        for i in range(1, len(hist_list)):
            high, low, close = hist_list[i]
            _, _, prev_close = hist_list[i-1]
            
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_list.append(tr)
        
        # 返回平均值
        import numpy as np
        return float(np.mean(tr_list[-period:]))

    # ------------------------------------------------------------------
    #  主入口
    # ------------------------------------------------------------------

    # _get_atr 已被重写在上方

    def check_exit_rules(
        self, 
        snapshots: dict[str, MarketSnapshot], 
        signals: dict[str, TradingSignal] = None,
        now: Optional[datetime] = None
    ) -> list[TradeOrder]:
        """
        [科学退出引擎] 评估多因子平仓规则：
        1. 强制清仓 (14:55)
        2. ATR 动态止盈 / 止损 (价格屏障)
        3. 盈利保卫 / 保本损 (盈亏屏障)
        4. 时间衰减退出 (时间屏障)
        5. 信号反转平仓 (alpha 屏障)
        """
        orders = []
        now = now or datetime.now()
        current_time = now.time()
        # ===== 0. 全域更新波动率 (无论是否有持仓) =====
        for code, snap in snapshots.items():
            if snap.is_valid:
                self._update_volatility(code, snap)

        signals = signals or {}

        # ===== 1. 强制清仓 =====
        force_close = dtime.fromisoformat(FORCE_CLOSE_TIME)
        if current_time >= force_close:
            for code, pos in self._pm.positions.items():
                if pos.quantity > 0:
                    price_snap = snapshots.get(code)
                    sell_price = price_snap.etf_price if price_snap else pos.current_price
                    orders.append(TradeOrder(
                        etf_code=code, etf_name=pos.etf_name, side=OrderSide.SELL,
                        price=sell_price, quantity=pos.quantity,
                        reason=f"强制清仓({FORCE_CLOSE_TIME})",
                    ))
            return orders

        # ===== 逐持仓检查多因子屏障 =====
        for code, pos in self._pm.positions.items():
            if pos.quantity <= 0: continue
            
            snapshot = snapshots.get(code)
            if not snapshot or snapshot.etf_price <= 0: continue

            price = snapshot.etf_price
            atr = self._get_atr(code)
            
            # --- 更新持仓状态 ---
            pos.current_price = price
            pos.highest_price = max(pos.highest_price, price)

            # --- A. 信号反转 (Alpha 屏障) ---
            # 如果策略当前给出反向的 STRONG 信号，提前出场
            signal = signals.get(code)
            if signal and signal.signal_type in (SignalType.SELL, SignalType.STRONG_SELL):
                orders.append(TradeOrder(
                    etf_code=code, etf_name=pos.etf_name, side=OrderSide.SELL,
                    price=price, quantity=pos.quantity,
                    reason=f"Alpha衰减({signal.reason})",
                ))
                logger.info(f"[{code}] 触发 Alpha 衰减退出: {signal.reason}")
                continue

            # --- B. 盈利保卫 (Profit Guard / 保本损) ---
            # 导入配置
            from config.settings import (
                PROFIT_GUARD_THRESHOLD, PROFIT_GUARD_RETRACEMENT,
                ATR_MULTIPLIER_TP, ATR_MULTIPLIER_SL,
                TIME_DECAY_MINUTES, STOP_LOSS_PCT
            )
            
            # 激活保本损：盈利率超过阈值 (如 0.4%)
            if not pos.profit_guard_active and pos.pnl_pct >= PROFIT_GUARD_THRESHOLD:
                pos.profit_guard_active = True
                logger.info(f"[{code}] 盈利达 {pos.pnl_pct*100:.2f}%, 激活保本损保护")

            # 如果已激活保本损，在利润回落到安全垫以下时平仓
            if pos.profit_guard_active and pos.pnl_pct <= PROFIT_GUARD_RETRACEMENT:
                orders.append(TradeOrder(
                    etf_code=code, etf_name=pos.etf_name, side=OrderSide.SELL,
                    price=price, quantity=pos.quantity,
                    reason=f"盈利保护({pos.pnl_pct*100:.3f}% <= {PROFIT_GUARD_RETRACEMENT*100}%)",
                ))
                logger.warning(f"[{code}] 触发盈利保护平仓 @ {price:.4f}")
                continue

            # --- C. ATR 动态屏障 (价格屏障) ---
            # 止盈：Entry + 2*ATR
            if atr > 0:
                tp_price = pos.avg_cost + ATR_MULTIPLIER_TP * atr
                sl_price = pos.avg_cost - ATR_MULTIPLIER_SL * atr
                
                # 触发 ATR 止盈
                if price >= tp_price:
                    orders.append(TradeOrder(
                        etf_code=code, etf_name=pos.etf_name, side=OrderSide.SELL,
                        price=price, quantity=pos.quantity,
                        reason=f"ATR止盈(价格{price:.3f} >= 目标{tp_price:.3f})",
                    ))
                    logger.info(f"[{code}] 触发 ATR 极致止盈")
                    continue
                
                # 触发 ATR 动态止损
                if price <= sl_price:
                    orders.append(TradeOrder(
                        etf_code=code, etf_name=pos.etf_name, side=OrderSide.SELL,
                        price=price, quantity=pos.quantity,
                        reason=f"ATR止损(价格{price:.3f} <= 阈值{sl_price:.3f})",
                    ))
                    logger.info(f"[{code}] 触发 ATR 动态止损")
                    continue
            
            # --- D. 固定止损兜底 ---
            if pos.pnl_pct <= -STOP_LOSS_PCT:
                orders.append(TradeOrder(
                    etf_code=code, etf_name=pos.etf_name, side=OrderSide.SELL,
                    price=price, quantity=pos.quantity,
                    reason=f"固定止损兜底({pos.pnl_pct*100:.2f}%)",
                ))
                continue

            # --- E. 时间衰减 (时间屏障) ---
            # 如果持仓时间超过阈值，且当前处于盈利状态但未达预期，离场以释放资金
            holding_duration = (now - pos.open_time).total_seconds() / 60
            if holding_duration >= TIME_DECAY_MINUTES and price > pos.avg_cost:
                orders.append(TradeOrder(
                    etf_code=code, etf_name=pos.etf_name, side=OrderSide.SELL,
                    price=price, quantity=pos.quantity,
                    reason=f"时间衰减退出(持有{int(holding_duration)}min, 且当前有微利)",
                ))
                logger.info(f"[{code}] 触发时间衰减退出 (微利离场释放资金)")
                continue

        return orders

    def validate_entry(
        self, signal: TradingSignal, now: Optional[datetime] = None
    ) -> tuple[bool, str]:
        """
        验证是否允许开仓。

        Returns:
            (是否允许, 原因)
        """
        code = signal.etf_code
        now = now or datetime.now()

        # 时间限制
        current_time = now.time()
        no_open = dtime.fromisoformat(NO_OPEN_AFTER)
        if current_time >= no_open:
            return False, f"已过{NO_OPEN_AFTER}，禁止开新仓"

        # 全局冷却时间限制
        last_trade = self._pm.get_last_trade_time(code)
        if last_trade:
            diff = (now - last_trade).total_seconds()
            if diff < GLOBAL_TRADE_COOLDOWN_SECONDS:
                return False, f"[{code}] 处于全局冷却期 ({int(diff)}s < {GLOBAL_TRADE_COOLDOWN_SECONDS}s)"

        # 日交易次数限制
        daily_count = self._pm.get_daily_trade_count(code)
        if daily_count >= MAX_DAILY_TRADES:
            return False, f"[{code}] 今日交易已达上限 {MAX_DAILY_TRADES} 笔"

        # 单标的仓位限制
        pos_pct = self._pm.get_position_pct(code)
        if pos_pct >= MAX_POSITION_PCT:
            return False, f"[{code}] 仓位已达上限 {MAX_POSITION_PCT * 100}%"

        # 总仓位限制
        total_pct = self._pm.total_position_pct
        if total_pct >= MAX_TOTAL_POSITION_PCT:
            return False, f"总仓位已达上限 {MAX_TOTAL_POSITION_PCT * 100}%"

        return True, "通过"

    def calc_order_quantity(
        self, signal: TradingSignal
    ) -> int:
        """
        根据风控规则计算下单数量。
        ETF 最小交易单位为 100 股。

        Returns:
            建议买入数量（股数，100 的整数倍）
        """
        total_assets = self._pm.total_assets
        if total_assets <= 0 or signal.price <= 0:
            return 0

        # 可用于该标的的最大金额
        max_for_etf = total_assets * MAX_POSITION_PCT
        current_pos_value = 0
        pos = self._pm.get_position(signal.etf_code)
        if pos:
            current_pos_value = pos.market_value

        available = max_for_etf - current_pos_value

        # 同时不能超过总仓位上限
        total_available = total_assets * MAX_TOTAL_POSITION_PCT - self._pm.total_market_value
        available = min(available, total_available)

        # 也不能超过可用现金
        available = min(available, self._pm.cash)

        if available <= 0:
            return 0

        # 根据信号强度调整（强信号买更多）
        strength_factor = max(0.3, signal.strength)
        target_amount = available * strength_factor

        # 计算股数（100 的整数倍）
        quantity = int(target_amount / signal.price / 100) * 100
        return max(0, quantity)
