import os
import sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

from dotenv import load_dotenv
load_dotenv(".env")

from monitor.pushplus_notifier import PushplusNotifier

def test():
    token = os.getenv("PUSHPLUS_TOKEN")
    if not token:
        print("未找到 PUSHPLUS_TOKEN！")
        return
        
    try:
        with open("logs/latest_report.md", "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print("本地报告不存在，测试跳过")
        return

    notifier = PushplusNotifier(token)
    print(f"正在模块化测试 Pushplus 分条推送功能，原始内容长度 {len(content)} ...")
    # 模拟真实推送
    success = notifier.send_markdown("📊 测试超长报告", content)
    print("推送完成，状态:", success)

if __name__ == "__main__":
    test()
