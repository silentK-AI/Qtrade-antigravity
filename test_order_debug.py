"""
直接用 pywinauto 操控同花顺下单（绕过 easytrader）
逐步操作并输出每步结果，定位问题
"""
import time
import pywinauto
from pywinauto import Application, Desktop

print("=" * 50)
print("直接操控同花顺下单测试")
print("=" * 50)

# 1. 连接同花顺客户端
print("\n[1] 连接同花顺...")
try:
    app = Application(backend="win32").connect(path=r'C:\同花顺软件\同花顺\xiadan.exe')
    print("    连接成功!")
except Exception as e:
    print(f"    连接失败: {e}")
    print("    尝试连接所有同花顺窗口...")
    try:
        app = Application(backend="win32").connect(class_name='AfxMDIFrame42s')
        print("    通过 class_name 连接成功!")
    except Exception as e2:
        print(f"    连接失败: {e2}")
        exit(1)

# 2. 找到主窗口
print("\n[2] 查找主窗口...")
try:
    main_window = app.top_window()
    print(f"    主窗口标题: '{main_window.window_text()}'")
    print(f"    主窗口类名: '{main_window.class_name()}'")
    print(f"    主窗口句柄: {main_window.handle}")
except Exception as e:
    print(f"    查找主窗口失败: {e}")
    exit(1)

# 3. 列出所有顶层窗口（寻找下单窗口）
print("\n[3] 列出所有同花顺相关窗口:")
desktop = Desktop(backend="win32")
for w in desktop.windows():
    try:
        title = w.window_text()
        cls = w.class_name()
        if title or 'Afx' in cls or 'ths' in cls.lower():
            print(f"    标题='{title}', 类名='{cls}', 句柄={w.handle}")
    except:
        pass

# 4. 尝试用快捷键买入
print("\n[4] 使用键盘操控下单...")
try:
    # 激活主窗口
    main_window.set_focus()
    time.sleep(0.5)
    
    # F1 = 买入
    print("    发送 F1 (切换到买入页面)...")
    main_window.type_keys('{F1}', set_foreground=True)
    time.sleep(1)
    
    # 输入证券代码
    print("    输入证券代码 513310...")
    main_window.type_keys('513310', set_foreground=True)
    time.sleep(0.5)
    
    # Tab 到价格栏
    print("    Tab 到价格栏...")
    main_window.type_keys('{TAB}', set_foreground=True)
    time.sleep(0.3)
    
    # 清空并输入价格
    print("    输入价格 3.41...")
    main_window.type_keys('^a', set_foreground=True)  # 全选
    time.sleep(0.1)
    main_window.type_keys('3.41', set_foreground=True)
    time.sleep(0.3)
    
    # Tab 到数量栏
    print("    Tab 到数量栏...")
    main_window.type_keys('{TAB}', set_foreground=True)
    time.sleep(0.3)
    
    # 输入数量
    print("    输入数量 100...")
    main_window.type_keys('^a', set_foreground=True)
    time.sleep(0.1)
    main_window.type_keys('100', set_foreground=True)
    time.sleep(0.3)
    
    # 回车提交
    print("    按回车提交...")
    main_window.type_keys('{ENTER}', set_foreground=True)
    time.sleep(1)
    
    # 如果有确认弹窗，再按一次回车
    print("    再按一次回车（确认弹窗）...")
    main_window.type_keys('{ENTER}', set_foreground=True)
    time.sleep(1)
    
    print("    下单操作完成!")

except Exception as e:
    print(f"    下单失败: {e}")
    import traceback
    traceback.print_exc()

# 5. 等待
print("\n[5] 等待 3 秒...")
time.sleep(3)

# 6. 检查是否有弹窗
print("\n[6] 检查弹窗:")
for w in desktop.windows():
    try:
        title = w.window_text()
        if title and ('提示' in title or '确认' in title or 'TopWnd' in title):
            print(f"    弹窗: '{title}' (class={w.class_name()})")
    except:
        pass

print("\n" + "=" * 50)
print("请立刻检查同花顺「当日委托」是否有 513310 记录")
print("然后手动撤单！")
print("=" * 50)
