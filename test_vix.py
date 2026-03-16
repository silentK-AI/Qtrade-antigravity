import requests

ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
headers = {"User-Agent": ua}

# stooq.com - 国内可直连，提供VIX/VXN/OVX历史数据
test_cases = [
    ("VIX", "https://stooq.com/q/d/l/?s=%5Evix&i=d"),
    ("VXN", "https://stooq.com/q/d/l/?s=%5Evxn&i=d"),
    ("OVX", "https://stooq.com/q/d/l/?s=%5Eovx&i=d"),
]

for name, url in test_cases:
    try:
        r = requests.get(url, headers=headers, timeout=10)
        lines = r.text.strip().split("\n")
        print(f"{name} status={r.status_code} lines={len(lines)}")
        if len(lines) >= 2:
            print(f"  header: {lines[0]}")
            print(f"  last:   {lines[-1]}")
    except Exception as e:
        print(f"{name} 失败: {e}")
