"""
miniQMT 交易执行器 - 通过 xtquant SDK 对接 miniQMT 客户端

使用前提:
1. Windows 环境
2. pip install xtquant
3. XtMiniQmt.exe 在后台运行
4. 已开通 QMT/miniQMT 权限
"""
import os
from typing import Optional
from loguru import logger

from trader.base_trader import BaseTrader
from strategy.signal import TradeOrder, OrderSide
from risk.position_manager import PositionManager


class XtQuantTrader(BaseTrader):
    """
    miniQMT 实盘交易执行器。

    通过 xtquant SDK 与 miniQMT 客户端通信，执行真实交易。
    """

    def __init__(self, position_manager: PositionManager):
        super().__init__(position_manager)
        self._connected = False
        self._account_id = os.getenv("XTQUANT_ACCOUNT", "")
        self._mini_qmt_path = os.getenv(
            "XTQUANT_PATH", r"D:\国泰海通证券\miniQMT\userdata_mini"
        )
        self._xt_trader = None
        self._session_id = 0

    def connect(self) -> bool:
        """连接 miniQMT"""
        try:
            from xtquant import xttrader
            from xtquant.xttrader import XtQuantTrader as _XtTrader
            from xtquant.xttype import StockAccount

            logger.info(f"正在连接 miniQMT: {self._mini_qmt_path}")

            self._xt_trader = _XtTrader(self._mini_qmt_path, self._session_id)

            # 注册回调
            self._xt_trader.register_callback(self._TradeCallback(self))

            # 启动
            self._xt_trader.start()

            # 连接
            result = self._xt_trader.connect()
            if result != 0:
                logger.error(f"miniQMT 连接失败，错误码: {result}")
                return False

            # 订阅账户
            if self._account_id:
                account = StockAccount(self._account_id)
                self._xt_trader.subscribe(account)
                logger.info(f"已订阅账户: {self._account_id}")

            self._connected = True
            logger.info("miniQMT 连接成功")
            return True

        except ImportError:
            logger.error(
                "xtquant 未安装。请在 Windows 环境运行: pip install xtquant\n"
                "并确保 XtMiniQmt.exe 正在运行。"
            )
            return False
        except Exception as e:
            logger.error(f"miniQMT 连接异常: {e}")
            return False

    def execute(self, order: TradeOrder) -> bool:
        """执行交易指令"""
        if not self._connected or self._xt_trader is None:
            logger.error("miniQMT 未连接，无法执行交易")
            return False

        try:
            from xtquant.xttype import StockAccount

            account = StockAccount(self._account_id)

            # 构造股票代码（需要带交易所后缀）
            stock_code = self._format_stock_code(order.etf_code)

            # 交易方向
            if order.side == OrderSide.BUY:
                xt_direction = 23  # xtconstant.STOCK_BUY
            else:
                xt_direction = 24  # xtconstant.STOCK_SELL

            # 下单
            order_id = self._xt_trader.order_stock(
                account=account,
                stock_code=stock_code,
                order_type=11,     # xtconstant.FIX_PRICE（限价单）
                order_volume=order.quantity,
                price_type=11,     # 限价
                price=order.price,
            )

            if order_id and order_id > 0:
                order.order_id = str(order_id)
                logger.info(
                    f"[实盘] {order.side.value} {order.etf_code} "
                    f"{order.quantity}股 @ {order.price:.4f} "
                    f"委托号={order_id} | {order.reason}"
                )

                # 同步更新 PositionManager（实际应通过回调确认成交后更新）
                if order.side == OrderSide.BUY:
                        order.etf_code, order.etf_name,
                        order.price, order.quantity,
                        reason=order.reason,
                    )
                else:
                        order.etf_code, order.price, order.quantity,
                        reason=order.reason,
                    )

                return True
            else:
                logger.error(f"[实盘] 下单失败: {order.etf_code}")
                return False

        except Exception as e:
            logger.error(f"[实盘] 交易执行异常: {e}")
            return False

    def disconnect(self) -> None:
        """断开连接"""
        if self._xt_trader:
            try:
                self._xt_trader.stop()
            except Exception:
                pass
        self._connected = False
        logger.info("miniQMT 已断开")

    def is_connected(self) -> bool:
        return self._connected

    def _format_stock_code(self, etf_code: str) -> str:
        """格式化股票代码为 xtquant 格式"""
        from config.settings import ETF_UNIVERSE
        config = ETF_UNIVERSE.get(etf_code, {})
        exchange = config.get("exchange", "SH")
        return f"{etf_code}.{exchange}"

    class _TradeCallback:
        """xtquant 交易回调"""

        def __init__(self, parent: "XtQuantTrader"):
            self._parent = parent

        def on_disconnected(self):
            logger.warning("miniQMT 连接断开")
            self._parent._connected = False

        def on_order_stock_async_response(self, response):
            logger.debug(f"委托响应: {response}")

        def on_order_error(self, order_error):
            logger.error(f"委托错误: {order_error}")

        def on_order_callback(self, order_info):
            logger.info(f"委托状态更新: {order_info}")

        def on_trade_callback(self, trade_info):
            logger.info(f"成交回报: {trade_info}")
