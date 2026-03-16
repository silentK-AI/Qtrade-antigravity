import requests

ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
headers = {"User-Agent": ua, "Referer": "https://finance.sina.com.cn"}

codes = ["gb_%5EVIX", "gb_%5EVXN", "gb_%5EOVX", "hf_VIX", "hf_VXN", "hf_OVX", "fx_VIX", "fx_VXN", "fx_OVX"]

for code in codes:
    try:
        r = requests.get(f"https://hq.sinajs.cn/list={code}", headers=headers, timeout=8)
        r.encoding = "gbk"
        text = r.text.strip()
        if '""' in text or not text:
            print(f"{code}: 空")
        else:
            print(f"{code}: {text[:150]}")
    except Exception as e:
        print(f"{code} 失败: {e}")
