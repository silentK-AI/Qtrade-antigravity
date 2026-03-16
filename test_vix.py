import requests

ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
headers = {"User-Agent": ua}

# 源1: wsj.com (华尔街日报，国内可访问)
print("=== 测试 wsj.com ===")
for name, sym in [("VIX", "VIX"), ("VXN", "VXN"), ("OVX", "OVX")]:
    try:
        url = f"https://www.wsj.com/market-data/quotes/index/{sym}/historical-prices/download?num_rows=1&startDate=03/01/2026&endDate=03/16/2026"
        r = requests.get(url, headers=headers, timeout=10)
        print(f"{name}: status={r.status_code} {r.text[:100]}")
    except Exception as e:
        print(f"{name}: {e}")

# 源2: alphavantage (免费API，国内可访问)
print("\n=== 测试 alphavantage ===")
try:
    url = "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=VIXY&apikey=demo&datatype=json"
    r = requests.get(url, headers=headers, timeout=10)
    print(f"status={r.status_code} {r.text[:150]}")
except Exception as e:
    print(f"失败: {e}")

# 源3: 东方财富 VIX
print("\n=== 测试东方财富 ===")
try:
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=100.VIX&fields1=f1,f2,f3,f4,f5&fields2=f51,f52,f53,f54,f55&klt=101&fqt=0&beg=20260310&end=20260316"
    r = requests.get(url, headers=headers, timeout=10)
    print(f"status={r.status_code} {r.text[:200]}")
except Exception as e:
    print(f"失败: {e}")

# 源4: 富途 VIX
print("\n=== 测试富途 ===")
try:
    url = "https://quote.futunn.com/quote/real-time/index?market_type=2&code=.VIX"
    r = requests.get(url, headers=headers, timeout=10)
    print(f"status={r.status_code} {r.text[:200]}")
except Exception as e:
    print(f"失败: {e}")
