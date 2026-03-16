import requests

ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
headers = {"User-Agent": ua}

# 测试 akshare VIX
print("=== 测试 akshare ===")
try:
    import akshare as ak
    for func_name in ["index_vix_weeklyfutures", "index_vix_weeklyfutures"]:
        try:
            fn = getattr(ak, func_name, None)
            if fn:
                df = fn()
                print(f"{func_name}: {df.tail(2).to_string()}")
        except Exception as e:
            print(f"{func_name}: {e}")
except Exception as e:
    print(f"akshare 失败: {e}")

# 测试东方财富美股实时接口 VIXY (VIX短期期货ETF)
print("\n=== 测试东方财富 VIXY 实时价格 ===")
try:
    url = "https://push2.eastmoney.com/api/qt/stock/get?secid=106.VIXY&fields=f43,f57,f58,f169,f170,f46,f44,f45"
    r = requests.get(url, headers=headers, timeout=10)
    print(f"status={r.status_code} {r.text[:300]}")
except Exception as e:
    print(f"失败: {e}")

# 测试东方财富美股实时接口 UVXY
print("\n=== 测试东方财富 UVXY ===")
try:
    url = "https://push2.eastmoney.com/api/qt/stock/get?secid=106.UVXY&fields=f43,f57,f58,f169,f170,f46,f44,f45"
    r = requests.get(url, headers=headers, timeout=10)
    print(f"status={r.status_code} {r.text[:300]}")
except Exception as e:
    print(f"失败: {e}")
