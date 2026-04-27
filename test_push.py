import os
import requests
from dotenv import load_dotenv

# 确保能加载 markdown 库测试
try:
    import markdown
except ImportError:
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "markdown"])
    import markdown

load_dotenv(".env")
token = os.getenv("PUSHPLUS_TOKEN")

def test_push_local_report():
    try:
        with open("logs/latest_report.md", "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print("未找到本地备份报告 logs/latest_report.md")
        return

    # Pushplus 有时候对超长的 Markdown 内容解析会导致“验证失败”，
    # 更稳妥的做法是我们在本地把它渲染成 HTML，直接按 HTML 发过去，或者分批。
    html_content = markdown.markdown(content, extensions=['tables', 'fenced_code'])

    # 先测试发送纯 HTML
    payload = {
        "token": token,
        "title": "📊 盘前技术与基本面报表",
        "content": html_content,
        "template": "html"
    }

    url = "https://www.pushplus.plus/send"
    print(f"URL: {url}")
    print(f"正在发送HTML格式（长度: {len(html_content)}）...")
    resp = requests.post(url, json=payload, timeout=10)
    print("返回状态码:", resp.status_code)
    try:
        print("返回结果:", resp.json())
    except:
        print("原始返回:", resp.text)

if __name__ == "__main__":
    if not token:
        print("找不到 PUSHPLUS_TOKEN")
    else:
        test_push_local_report()
