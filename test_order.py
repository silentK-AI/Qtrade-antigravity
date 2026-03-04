import easytrader
import time

user = easytrader.use('ths')
user.connect(r'C:\同花顺软件\同花顺\xiadan.exe')
print('连接成功!')

# 买入 513310 100股 @ 3.41
print('买入 513310 100股 @ 3.41')
result = user.buy('513310', price=3.41, amount=100)
print(f'委托结果: {result}')

# 等待 3 秒
print('等待 3 秒...')
time.sleep(3)

# 撤单
print('撤单...')
try:
    user.cancel_all_entrusts()
    print('撤单完成!')
except Exception as e:
    print(f'自动撤单失败: {e}')
    print('请手动在同花顺客户端撤单!')

print('测试结束')
