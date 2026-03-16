import requests

ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"

# 测试 investing.com API (存储历史收盘价，任何时段有效)
print("=== 测试 investing.com ===")
test_cases = [
    ("VIX",  "https://api.investing.com/api/financialdata/historical/44336?start-date=2026-03-10&end-date=2026-03-17&time-frame=Daily&add-missing-rows=false"),
]
for name, url in test_cases:
    try:
        headers = {
            "User-Agent": ua,
            "domain-id": "www",
            "Referer": "https://www.investing.com",
        }
        r = requests.get(url, headers=headers, timeout=10)
        print(f"{name}: status={r.status_code} {r.text[:300]}")
    except Exception as e:
        print(f"{name}: {e}")

# 测试 CBOE 官方数据
print("\n=== 测试 CBOE 官方 ===")
for name, url in [
    ("VIX", "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"),
    ("VXN", "https://cdn.cboe.com/api/global/us_indices/daily_prices/VXN_History.csv"),
    ("OVX", "https://cdn.cboe.com/api/global/us_indices/daily_prices/OVX_History.csv"),
]:
    try:
        r = requests.get(url, headers={"User-Agent": ua}, timeout=15)
        lines = r.text.strip().split("\n")
        print(f"{name}: status={r.status_code} lines={len(lines)} last={lines[-1] if lines else 'empty'}")
    except Exception as e:
        print(f"{name}: {e}")
