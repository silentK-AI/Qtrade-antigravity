import requests

ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
headers = {"User-Agent": ua}

# 东方财富 VIX/VXN/OVX 正确代码测试
print("=== 测试东方财富 VIX ===")
test_cases = [
    ("VIX-1",  "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=100.VIX&fields1=f1,f2,f3,f4,f5&fields2=f51,f52,f53,f54,f55&klt=101&fqt=0&beg=20260310&end=20260317"),
    ("VIX-2",  "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=101.VIX&fields1=f1,f2,f3,f4,f5&fields2=f51,f52,f53,f54,f55&klt=101&fqt=0&beg=20260310&end=20260317"),
    ("VIX-3",  "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=160.VIX&fields1=f1,f2,f3,f4,f5&fields2=f51,f52,f53,f54,f55&klt=101&fqt=0&beg=20260310&end=20260317"),
    ("CBOE",   "https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&invt=2&secids=100.VIX,100.VXN"),
    ("Search", "https://searchapi.eastmoney.com/api/suggest/get?input=VIX&type=14&token=D43BF722C8E33BDC906FB84D85E326E8"),
]

for name, url in test_cases:
    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"{name}: status={r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"{name}: {e}")
