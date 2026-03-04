"""
直接用 pywinauto 操控同花顺下单（处理弹窗版本）
"""
import time
import pywinauto
from pywinauto import Application, Desktop

print("=" * 50)
print("同花顺下单测试 v3")
print("=" * 50)

# 1. 连接
print("\n[1] 连接同花顺...")
app = Application(backend="win32").connect(path=r'C:\同花顺软件\同花顺\xiadan.exe')
main = app.top_window()
print(f"    连接成功! 窗口='{main.window_text()}'")

# 2. 键盘输入下单信息
print("\n[2] 输入下单信息...")
main.set_focus()
time.sleep(0.5)

# F1 切换到买入
main.type_keys('{F1}', set_foreground=True)
time.sleep(1)
print("    F1 买入页面 ✓")

# 输入代码
main.type_keys('513310', set_foreground=True)
time.sleep(0.5)
print("    代码 513310 ✓")

# Tab → 价格
main.type_keys('{TAB}', set_foreground=True)
time.sleep(0.3)
main.type_keys('^a3.41', set_foreground=True)
time.sleep(0.3)
print("    价格 3.41 ✓")

# Tab → 数量
main.type_keys('{TAB}', set_foreground=True)
time.sleep(0.3)
main.type_keys('^a100', set_foreground=True)
time.sleep(0.3)
print("    数量 100 ✓")

# 3. 按回车提交
print("\n[3] 按回车提交...")
main.type_keys('{ENTER}', set_foreground=True)
time.sleep(1)

# 4. 处理弹窗
print("\n[4] 检查并处理弹窗...")
desktop = Desktop(backend="win32")

handled = False
for attempt in range(5):
    time.sleep(0.5)
    for w in desktop.windows():
        try:
            title = w.window_text()
            cls = w.class_name()
            
            if cls == 'TopWndTips' or ('提示' in title and cls == '#32770'):
                print(f"    发现弹窗: '{title}' (class={cls})")
                
                # 尝试找到并点击 "是" 或 "确定" 按钮
                popup_app = Application(backend="win32").connect(handle=w.handle)
                popup = popup_app.window(handle=w.handle)
                
                # 列出弹窗中的按钮
                for child in popup.children():
                    child_text = child.window_text()
                    child_class = child.class_name()
                    if child_class == 'Button' or child_text:
                        print(f"      控件: '{child_text}' (class={child_class})")
                
                # 尝试点各种确认按钮
                for btn_text in ['是(&Y)', '是(Y)', '确定', '是', 'Yes', 'OK']:
                    try:
                        btn = popup[btn_text]
                        btn.click()
                        print(f"    点击了 '{btn_text}' ✓")
                        handled = True
                        break
                    except Exception:
                        continue
                
                if not handled:
                    # 直接发送回车
                    print("    未找到按钮，发送回车...")
                    popup.type_keys('{ENTER}')
                    handled = True
                
                break
        except:
            pass
    
    if handled:
        break

if not handled:
    print("    未检测到弹窗")

# 5. 等待
print("\n[5] 等待 3 秒...")
time.sleep(3)

# 6. 再次检查弹窗
print("\n[6] 最终弹窗检查:")
for w in desktop.windows():
    try:
        title = w.window_text()
        cls = w.class_name()
        if cls == 'TopWndTips' or '提示' in title:
            print(f"    还有弹窗: '{title}' (class={cls})")
    except:
        pass

print("\n" + "=" * 50)
print("请检查同花顺「当日委托」是否有 513310 记录")
print("然后手动撤单！")
print("=" * 50)
