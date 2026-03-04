"""
同花顺验证码自动处理器

当同花顺检测到剪贴板拷贝操作时，会弹出验证码窗口。
此模块自动检测弹窗、截取验证码图片、用 ddddocr 识别并填入。
"""
import time
from loguru import logger

try:
    import pywinauto
    from pywinauto import Desktop
    HAS_PYWINAUTO = True
except ImportError:
    HAS_PYWINAUTO = False

try:
    import ddddocr
    HAS_DDDDOCR = True
except ImportError:
    HAS_DDDDOCR = False


class CaptchaHandler:
    """自动处理同花顺验证码弹窗"""

    def __init__(self):
        self._ocr = None
        if HAS_DDDDOCR:
            self._ocr = ddddocr.DdddOcr(show_ad=False)
            logger.info("验证码处理器已初始化 (ddddocr)")
        else:
            logger.warning("ddddocr 未安装，验证码需要手动处理")

    def check_and_handle(self) -> bool:
        """
        检查是否有验证码弹窗，如果有则自动处理。
        返回 True 表示处理了验证码，False 表示没有弹窗。
        """
        if not HAS_PYWINAUTO or not self._ocr:
            return False

        try:
            # 查找标题为 "提示" 的弹窗
            dlg = None
            desktop = Desktop(backend="win32")
            windows = desktop.windows()
            for w in windows:
                try:
                    if "提示" in w.window_text():
                        # 检查是否包含验证码相关文字
                        dlg = w
                        break
                except Exception:
                    continue

            if dlg is None:
                return False

            logger.info("检测到验证码弹窗，正在自动处理...")

            # 获取弹窗的包装器
            app = pywinauto.Application(backend="win32").connect(handle=dlg.handle)
            dialog = app.window(handle=dlg.handle)

            # 查找验证码图片控件（Static 控件中的图片）
            # 同花顺的验证码弹窗结构：有一个输入框和一个显示验证码的图片区域
            captcha_image = None
            edit_ctrl = None

            # 尝试找到编辑框
            for ctrl in dialog.children():
                class_name = ctrl.friendly_class_name()
                if class_name == "Edit":
                    edit_ctrl = ctrl
                    break

            if edit_ctrl is None:
                logger.warning("未找到验证码输入框")
                return False

            # 截取整个弹窗图片，用 OCR 识别验证码
            # 方法：截取弹窗右侧的验证码区域
            dialog_rect = dialog.rectangle()
            edit_rect = edit_ctrl.rectangle()

            # 验证码图片通常在输入框右侧
            import PIL.ImageGrab
            # 截取输入框右侧区域（验证码图片位置）
            captcha_left = edit_rect.right + 5
            captcha_top = edit_rect.top - 5
            captcha_right = captcha_left + 120
            captcha_bottom = captcha_top + 40

            captcha_image = PIL.ImageGrab.grab(
                bbox=(captcha_left, captcha_top, captcha_right, captcha_bottom)
            )

            # 转为 bytes 给 ddddocr
            import io
            img_bytes = io.BytesIO()
            captcha_image.save(img_bytes, format="PNG")
            img_bytes = img_bytes.getvalue()

            # OCR 识别
            result = self._ocr.classification(img_bytes)
            logger.info(f"验证码识别结果: {result}")

            if not result or len(result) < 3:
                logger.warning(f"验证码识别结果异常: '{result}'")
                return False

            # 填入验证码
            edit_ctrl.set_text(result)
            time.sleep(0.3)

            # 点击确定按钮
            try:
                ok_btn = dialog["确定"]
                ok_btn.click()
            except Exception:
                # 尝试其他方式找确定按钮
                for ctrl in dialog.children():
                    if ctrl.friendly_class_name() == "Button":
                        if "确定" in ctrl.window_text():
                            ctrl.click()
                            break

            logger.info("验证码已自动填入并确认")
            time.sleep(0.5)
            return True

        except Exception as e:
            logger.warning(f"验证码自动处理失败: {e}")
            return False

    def handle_loop(self, max_retries: int = 3) -> bool:
        """
        循环检测并处理验证码，最多重试 max_retries 次。
        （有时第一次识别不对，同花顺会再弹一次新验证码）
        """
        for i in range(max_retries):
            time.sleep(0.5)
            handled = self.check_and_handle()
            if not handled:
                return i > 0  # 如果之前处理过返回 True
        return True
