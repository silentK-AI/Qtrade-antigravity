import easytrader
import time

user = easytrader.use('ths')
user.connect(r'C:\同花顺软件\同花顺\xiadan.exe')
print('连接成功!')

# 查询账户余额
try:
    balance = user.balance
    print(f'账户余额: {balance}')
except Exception as e:
    print(f'查询余额失败: {e}')

# 查询当前持仓
try:
    position = user.position
    print(f'当前持仓: {position}')
except Exception as e:
    print(f'查询持仓失败: {e}')

# 以 3.41 买入 100 股 513310（中韩半导体ETF）
print('\n===== 实盘下单测试 =====')
print('买入 513310 100股 @ 3.41')
result = user.buy('513310', price=3.41, amount=100)
print(f'委托结果: {result}')

# 等待 3 秒
print('等待 3 秒...')
time.sleep(3)

# 查询当日委托
print('\n查询当日委托:')
try:
    entrusts = user.today_entrusts
    for ent in entrusts:
        print(f'  {ent}')
except Exception as e:
    print(f'查询委托失败: {e}')

# 逐笔撤单
print('\n开始撤单...')
try:
    entrusts = user.today_entrusts
    cancelled = 0
    for ent in entrusts:
        status = ent.get('备注', '')
        if status not in ('已成', '已撤', '废单'):
            contract_id = ent.get('合同编号', '')
            if contract_id:
                try:
                    user.cancel_entrust(contract_id)
                    print(f'  已撤单: 合同编号={contract_id}')
                    cancelled += 1
                except Exception as e:
                    print(f'  撤单失败 {contract_id}: {e}')
    if cancelled == 0:
        print('  没有需要撤销的委托')
    print(f'\n撤单完成! 共撤 {cancelled} 笔')
except Exception as e:
    print(f'撤单失败: {e}')
    print('请手动在同花顺客户端撤掉测试委托!')

# 最终确认
print('\n查询当日成交:')
try:
    trades = user.today_trades
    if trades:
        for t in trades:
            print(f'  {t}')
    else:
        print('  无成交记录（正常，说明撤单成功）')
except Exception as e:
    print(f'查询成交失败: {e}')

print('\n===== 测试结束 =====')
