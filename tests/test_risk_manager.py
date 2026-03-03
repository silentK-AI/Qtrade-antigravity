import pytest
from datetime import datetime, timedelta
from strategy.signal import TradingSignal, SignalType, OrderSide
from risk.position_manager import PositionManager
from risk.risk_manager import RiskManager

def test_global_cooldown():
    from unittest.mock import patch
    
    # 模拟交易时间（10:00），避免时间限制干扰
    mock_now = datetime(2026, 3, 2, 10, 0, 0)
    with patch("risk.risk_manager.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        # 因为 datetime.now() 在 risk_manager 里被调用，我们需要让模拟生效
        # 同时要保证 datetime.fromisoformat 等方法还能用
        mock_dt.fromisoformat = datetime.fromisoformat
        
        pm = PositionManager(initial_capital=100000)
        rm = RiskManager(pm)
        
        code = "159941"
        
        # 1. 模拟第一笔交易
        pm._record_trade(code, "纳指ETF", OrderSide.BUY, 1.5, 1000, 1.5, reason="Initial Buy")
        
        # 2. 立即尝试第二笔交易
        signal = TradingSignal(
            etf_code=code, etf_name="纳指ETF",
            signal_type=SignalType.SELL, timestamp=mock_now,
            price=1.51, iopv=1.5, premium_rate=0.006,
            futures_momentum=-0.005, strength=0.5
        )
        
        allowed, reason = rm.validate_entry(signal)
        assert allowed is False
        assert "全局冷却期" in reason
        
        # 3. 模拟 61 秒后
        pm._last_trade_time[code] = mock_now - timedelta(seconds=61)
        
        allowed, reason = rm.validate_entry(signal)
        assert allowed is True
