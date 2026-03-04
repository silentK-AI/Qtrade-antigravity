"""
同花顺下单测试脚本 - 使用新的键盘操控方式
"""
import time
from pywinauto import Application, Desktop

print("=" * 50)
print("同花顺下单测试 (键盘操控)")
print("=" * 50)

# 连接
exe_path = r'C:\同花顺软件\同花顺\xiadan.exe'
app = Application(backend="win32").connect(path=exe_path)
main = app.top_window()
print(f"连接成功: {main.window_text()}")

# 买入
print("\n买入 513310 100股 @ 3.410")
main.set_focus()
time.sleep(0.3)

main.type_keys('{F1}', set_foreground=True)
time.sleep(0.8)

main.type_keys('513310', set_foreground=True)
time.sleep(0.3)

main.type_keys('{TAB}', set_foreground=True)
time.sleep(0.3)

# 用 {.} 避免小数点被输入法拦截
main.type_keys('^a3{.}410', set_foreground=True)
time.sleep(0.3)

main.type_keys('{TAB}', set_foreground=True)
time.sleep(0.3)

main.type_keys('^a100', set_foreground=True)
time.sleep(0.3)

main.type_keys('{ENTER}', set_foreground=True)
print("已提交!")
time.sleep(1)

# 处理弹窗
desktop = Desktop(backend="win32")
for w in desktop.windows():
    try:
        if w.class_name() == 'TopWndTips':
            popup_app = Application(backend="win32").connect(handle=w.handle)
            popup = popup_app.window(handle=w.handle)
            for btn_text in ['是(&Y)', '是(Y)', '确定', '是']:
                try:
                    popup[btn_text].click()
                    print(f"弹窗已处理: {btn_text}")
                    break
                except:
                    continue
    except:
        pass

# 等待
print("\n等待 3 秒...")
time.sleep(3)

# 撤单
print("撤单...")
main.set_focus()
time.sleep(0.3)
main.type_keys('{F3}', set_foreground=True)
time.sleep(1)
main.type_keys('^a', set_foreground=True)
time.sleep(0.3)
main.type_keys('{DELETE}', set_foreground=True)
time.sleep(1)

# 处理撤单确认弹窗
for w in desktop.windows():
    try:
        if w.class_name() == 'TopWndTips':
            popup_app = Application(backend="win32").connect(handle=w.handle)
            popup = popup_app.window(handle=w.handle)
            for btn_text in ['是(&Y)', '是(Y)', '确定', '是']:
                try:
                    popup[btn_text].click()
                    print(f"撤单弹窗已处理: {btn_text}")
                    break
                except:
                    continue
    except:
        pass

print("\n测试完成! 请检查同花顺「当日委托」确认下单和撤单都正常。")
