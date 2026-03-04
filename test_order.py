"""
同花顺下单测试脚本 - 测试买入 + 卖出 + 撤单
"""
import time
from pywinauto import Application, Desktop


def handle_popup():
    """处理同花顺弹窗"""
    desktop = Desktop(backend="win32")
    time.sleep(0.5)
    for w in desktop.windows():
        try:
            if w.class_name() == 'TopWndTips':
                popup_app = Application(backend="win32").connect(handle=w.handle)
                popup = popup_app.window(handle=w.handle)
                for btn_text in ['是(&Y)', '是(Y)', '确定', '是']:
                    try:
                        popup[btn_text].click()
                        print(f"  弹窗已处理: {btn_text}")
                        return True
                    except:
                        continue
                popup.type_keys('{ENTER}')
                print("  弹窗已处理: 回车")
                return True
        except:
            pass
    return False


def place_order(main, side, code, price, quantity):
    """下单通用方法"""
    label = "买入" if side == "buy" else "卖出"
    hotkey = '{F1}' if side == "buy" else '{F2}'
    price_str = f"{price:.3f}"
    safe_price = price_str.replace('.', '{.}')

    print(f"\n>>> {label} {code} {quantity}股 @ {price_str}")

    main.set_focus()
    time.sleep(0.3)

    main.type_keys(hotkey, set_foreground=True)
    time.sleep(0.8)

    main.type_keys(code, set_foreground=True)
    time.sleep(0.3)

    main.type_keys('{TAB}', set_foreground=True)
    time.sleep(0.3)

    main.type_keys('^a' + safe_price, set_foreground=True)
    time.sleep(0.3)

    main.type_keys('{TAB}', set_foreground=True)
    time.sleep(0.3)

    main.type_keys(f'^a{quantity}', set_foreground=True)
    time.sleep(0.3)

    main.type_keys('{ENTER}', set_foreground=True)
    time.sleep(1)

    handle_popup()
    print(f"  {label}指令已提交!")


print("=" * 50)
print("同花顺下单测试 (买入 + 卖出 + 撤单)")
print("=" * 50)

# 连接
app = Application(backend="win32").connect(path=r'C:\同花顺软件\同花顺\xiadan.exe')
main = app.top_window()
print(f"连接成功: {main.window_text()}")

# 测试1: 买入 513310 100股 @ 3.410
place_order(main, "buy", "513310", 3.410, 100)

time.sleep(1)

# 测试2: 卖出 159202 100股 @ 0.999
place_order(main, "sell", "159202", 0.999, 100)

# 等待 3 秒
print("\n等待 3 秒...")
time.sleep(3)

# 撤单
print("\n>>> 撤销所有委托...")
main.set_focus()
time.sleep(0.3)
main.type_keys('{F3}', set_foreground=True)
time.sleep(1)
main.type_keys('^a', set_foreground=True)
time.sleep(0.3)
main.type_keys('{DELETE}', set_foreground=True)
time.sleep(1)
handle_popup()

print("\n" + "=" * 50)
print("测试完成! 请检查同花顺「当日委托」:")
print("  1. 513310 买入 100股 @ 3.410")
print("  2. 159202 卖出 100股 @ 0.999")
print("  两笔应该都已撤销")
print("=" * 50)
