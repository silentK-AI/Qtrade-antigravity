import requests
import json

ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
headers = {"User-Agent": ua, "Referer": "https://finance.sina.com.cn"}

# 测试新浪历史K线接口获取VIX昨收价
test_cases = [
    ("VIX",  "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=hf_VIX&scale=240&ma=no&datalen=3"),
    ("VXN",  "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=hf_VXN&scale=240&ma=no&datalen=3"),
    ("OVX",  "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=hf_OVX&scale=240&ma=no&datalen=3"),
]

for name, url in test_cases:
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = "utf-8"
        text = r.text.strip()
        print(f"{name}: {text[:200]}")
    except Exception as e:
        print(f"{name} 失败: {e}")
