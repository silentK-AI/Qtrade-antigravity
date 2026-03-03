import easytrader

user = easytrader.use('ths')
user.connect(r'C:\同花顺软件\同花顺\xiadan.exe')
print('连接成功，开始下单测试...')

# 以极低价买入 100 股 513310（不会成交）
result = user.buy('513310', price=0.001, amount=100)
print('委托结果:', result)

# 立刻撤掉
user.cancel_all_entrusts()
print('已撤单，测试完成!')
