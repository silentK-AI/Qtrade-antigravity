"""
同花顺交易执行器 - 直接通过 pywinauto 键盘操控下单

替代 easytrader 的按钮点击方式，使用键盘快捷键操控同花顺：
  F1 = 买入页面
  F2 = 卖出页面
  F3 = 撤单页面

兼容 64 位 Python + 32 位同花顺客户端。
"""
import os
import time
from typing import Optional
from loguru import logger

from trader.base_trader import BaseTrader
from strategy.signal import TradeOrder, OrderSide
from risk.position_manager import PositionManager

try:
    from pywinauto import Application, Desktop
    import win32clipboard
    HAS_PYWINAUTO = True
except ImportError:
    HAS_PYWINAUTO = False


class EasyTrader(BaseTrader):
    """
    同花顺键盘操控交易执行器。

    通过 pywinauto 发送键盘指令操控同花顺客户端完成买卖操作。
    不依赖 easytrader 库的按钮点击（该方式在 64 位 Python 下失效）。
    """

    # 下单后等待弹窗的超时时间(秒)
    POPUP_TIMEOUT = 3.0
    # 每步操作之间的间隔(秒)
    STEP_DELAY = 0.3
    # 提交后等待交易所响应的间隔(秒)
    SUBMIT_DELAY = 1.0

    def __init__(self, position_manager: PositionManager):
        super().__init__(position_manager)
        self._connected = False
        self._app = None
        self._main = None
        self._exe_path = os.getenv(
            "THS_EXE_PATH", r"C:\同花顺软件\同花顺\xiadan.exe"
        )

    def connect(self) -> bool:
        """连接同花顺客户端"""
        if not HAS_PYWINAUTO:
            logger.error(
                "pywinauto 未安装。请运行: pip install pywinauto\n"
                "并确保同花顺客户端已打开并登录。"
            )
            return False

        try:
            logger.info(f"正在连接同花顺客户端: {self._exe_path}")
            self._app = Application(backend="win32").connect(path=self._exe_path)
            self._main = self._app.top_window()
            title = self._main.window_text()
            logger.info(f"已连接同花顺客户端: {title}")
            self._connected = True
            return True
        except Exception as e:
            logger.error(f"同花顺连接失败: {e}")
            return False

    def execute(self, order: TradeOrder) -> bool:
        """执行交易指令"""
        if not self._connected or self._main is None:
            logger.error("同花顺未连接，无法执行交易")
            return False

        try:
            if order.side == OrderSide.BUY:
                success = self._keyboard_buy(
                    order.etf_code, order.price, order.quantity
                )
            else:
                success = self._keyboard_sell(
                    order.etf_code, order.price, order.quantity
                )

            if success:
                # 更新 PositionManager
                if order.side == OrderSide.BUY:
                    self._pm.open_position(
                        order.etf_code, order.etf_name,
                        order.price, order.quantity,
                        reason=order.reason,
                    )
                else:
                    self._pm.close_position(
                        order.etf_code, order.price, order.quantity,
                        reason=order.reason,
                    )

                logger.info(
                    f"[同花顺] {'买入' if order.side == OrderSide.BUY else '卖出'} "
                    f"{order.etf_code} {order.etf_name} "
                    f"{order.quantity}股 @ {order.price:.3f} | {order.reason}"
                )
                return True
            else:
                logger.warning(
                    f"[同花顺] 下单可能失败: {order.etf_code} "
                    f"{'买入' if order.side == OrderSide.BUY else '卖出'}"
                )
                return False

        except Exception as e:
            logger.error(f"[同花顺] 交易执行异常: {e}")
            return False

    # ------------------------------------------------------------------
    #  核心下单方法：键盘操控
    # ------------------------------------------------------------------

    def _keyboard_buy(self, code: str, price: float, quantity: int) -> bool:
        """通过键盘操控买入"""
        return self._keyboard_order("buy", code, price, quantity)

    def _keyboard_sell(self, code: str, price: float, quantity: int) -> bool:
        """通过键盘操控卖出"""
        return self._keyboard_order("sell", code, price, quantity)

    def _keyboard_order(
        self, side: str, code: str, price: float, quantity: int
    ) -> bool:
        """
        键盘操控下单通用方法。

        流程: 功能键(F1/F2) → 输入代码 → Tab → 输入价格 → Tab → 输入数量 → Enter
        """
        try:
            self._main.set_focus()
            time.sleep(self.STEP_DELAY)

            # 1. 切换到买入/卖出页面
            hotkey = '{F1}' if side == "buy" else '{F2}'
            self._main.type_keys(hotkey, set_foreground=True)
            time.sleep(0.8)

            # 2. 输入证券代码
            self._main.type_keys(code, set_foreground=True)
            time.sleep(self.STEP_DELAY)

            # 3. Tab 到价格栏，用剪贴板粘贴价格（避免输入法拦截小数点）
            self._main.type_keys('{TAB}', set_foreground=True)
            time.sleep(self.STEP_DELAY)

            price_str = f"{price:.3f}"
            self._clip_set(price_str)
            self._main.type_keys('^a^v', set_foreground=True)
            time.sleep(self.STEP_DELAY)

            # 4. Tab 到数量栏，输入数量
            self._main.type_keys('{TAB}', set_foreground=True)
            time.sleep(self.STEP_DELAY)

            self._main.type_keys(f'^a{quantity}', set_foreground=True)
            time.sleep(self.STEP_DELAY)

            # 5. 回车提交
            self._main.type_keys('{ENTER}', set_foreground=True)
            time.sleep(self.SUBMIT_DELAY)

            # 6. 处理可能的确认弹窗
            self._handle_popup()

            return True

        except Exception as e:
            logger.error(f"键盘下单异常: {e}")
            # 尝试处理弹窗（可能是错误提示）
            self._handle_popup()
            return False

    def _handle_popup(self) -> None:
        """检测并处理同花顺弹窗（确认框、提示框）"""
        try:
            desktop = Desktop(backend="win32")
            for attempt in range(3):
                time.sleep(0.5)
                for w in desktop.windows():
                    try:
                        cls = w.class_name()
                        title = w.window_text()

                        if cls == 'TopWndTips' or (
                            '提示' in title and cls == '#32770'
                        ):
                            popup_app = Application(backend="win32").connect(
                                handle=w.handle
                            )
                            popup = popup_app.window(handle=w.handle)

                            # 尝试点击确认按钮
                            for btn_text in [
                                '是(&Y)', '是(Y)', '确定', '是', 'Yes', 'OK'
                            ]:
                                try:
                                    btn = popup[btn_text]
                                    btn.click()
                                    logger.debug(f"弹窗已处理: 点击了 '{btn_text}'")
                                    return
                                except Exception:
                                    continue

                            # fallback: 发送回车
                            popup.type_keys('{ENTER}')
                            logger.debug("弹窗已处理: 发送回车")
                            return
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"弹窗检测失败: {e}")

    # ------------------------------------------------------------------
    #  撤单
    # ------------------------------------------------------------------

    def cancel_all(self) -> None:
        """撤销所有未成交委托"""
        if not self._connected or self._main is None:
            return
        try:
            self._main.set_focus()
            time.sleep(self.STEP_DELAY)

            # F3 = 撤单页面
            self._main.type_keys('{F3}', set_foreground=True)
            time.sleep(1)

            # Ctrl+A 全选
            self._main.type_keys('^a', set_foreground=True)
            time.sleep(self.STEP_DELAY)

            # 点击撤单按钮（发送 Alt+C 或直接查找按钮）
            # 尝试键盘 Delete 或 Alt+撤单
            self._main.type_keys('{DELETE}', set_foreground=True)
            time.sleep(self.SUBMIT_DELAY)

            # 处理确认弹窗
            self._handle_popup()

            logger.info("已发送撤销所有委托指令")
        except Exception as e:
            logger.error(f"撤单失败: {e}")

    # ------------------------------------------------------------------
    #  工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _clip_set(text: str) -> None:
        """设置剪贴板内容（用于粘贴价格，避免输入法问题）"""
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(str(text))
        win32clipboard.CloseClipboard()

    def disconnect(self) -> None:
        """断开连接"""
        self._app = None
        self._main = None
        self._connected = False
        logger.info("同花顺客户端已断开")

    def is_connected(self) -> bool:
        return self._connected
