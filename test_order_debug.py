"""
诊断脚本：逐步检查 easytrader 下单流程，定位问题
"""
import easytrader
import time

print("=" * 50)
print("同花顺下单诊断脚本")
print("=" * 50)

# 1. 连接
print("\n[1] 连接同花顺...")
user = easytrader.use('ths')
user.connect(r'C:\同花顺软件\同花顺\xiadan.exe')
print("    连接成功!")

# 2. 检查 easytrader 内部状态
print("\n[2] easytrader 内部状态:")
print(f"    app: {user.app}")
print(f"    main: {user.main}")

# 3. 尝试手动操作界面
print("\n[3] 尝试手动填入下单信息...")
try:
    # 切换到买入页面
    user.main.window(control_id=0x3EF, class_name='SysTreeView32').select('买入')
    time.sleep(0.5)
    print("    已切换到买入页面")
except Exception as e:
    print(f"    切换页面失败: {e}")

# 4. 查看当前窗口所有控件（帮助定位问题）
print("\n[4] 列出主窗口控件:")
try:
    user.main.print_control_identifiers()
except Exception as e:
    print(f"    列出控件失败: {e}")

# 5. 尝试买入
print("\n[5] 执行买入 513310 @ 3.41 x 100...")
try:
    result = user.buy('513310', price=3.41, amount=100)
    print(f"    返回结果: {result}")
except Exception as e:
    print(f"    买入异常: {e}")
    import traceback
    traceback.print_exc()

# 6. 等待并截图
print("\n[6] 等待 5 秒，请观察同花顺界面是否有变化...")
time.sleep(5)

# 7. 检查是否有弹窗
print("\n[7] 检查弹窗...")
try:
    from pywinauto import Desktop
    desktop = Desktop(backend="win32")
    windows = desktop.windows()
    for w in windows:
        try:
            title = w.window_text()
            if title and ('提示' in title or '确认' in title or 'Tips' in title or '同花顺' in title):
                print(f"    发现窗口: '{title}' (class={w.class_name()})")
        except:
            pass
except Exception as e:
    print(f"    检查弹窗失败: {e}")

print("\n" + "=" * 50)
print("诊断结束")
print("请检查同花顺「当日委托」是否出现了 513310 的记录")
print("并将以上所有输出发给我")
print("=" * 50)
