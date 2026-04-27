"""
Pushplus（推送加）通知模块

官网: http://www.pushplus.plus/
特点: 免费、无消息限制、支持 Markdown、无需实名认证
"""
import requests
from typing import Optional
from loguru import logger


class PushplusNotifier:
    """Pushplus 通知器"""

    def __init__(self, token: str):
        """
        初始化 Pushplus 通知器

        Args:
            token: Pushplus Token
        """
        self.token = token
        self.api_url = "http://www.pushplus.plus/send"

    def send(self, title: str, content: str, template: str = "markdown") -> bool:
        """
        发送通知

        Args:
            title: 消息标题
            content: 消息内容
            template: 消息模板（html/txt/json/markdown/cloudMonitor）

        Returns:
            是否发送成功
        """
        try:
            payload = {
                "token": self.token,
                "title": title[:100],
                "content": content,
                "template": template,
            }
            
            # 本地备份一份
            import os
            os.makedirs("logs", exist_ok=True)
            with open("logs/latest_report.md", "w", encoding="utf-8") as f:
                f.write(f"# {title}\n\n{content}")

            # 兼容 https
            url = self.api_url.replace("http://", "https://")
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()

            if data.get("code") == 200:
                logger.debug(f"[Pushplus] 消息发送成功: {title}")
                return True
            else:
                logger.warning(f"[Pushplus] 消息发送失败: {data.get('msg')}")
                return False

        except Exception as e:
            logger.error(f"[Pushplus] 发送消息异常: {e}")
            return False

    def send_markdown(self, title: str, content: str) -> bool:
        """发送 Markdown 格式消息（长度超出限制时切割推送）"""
        MAX_LEN = 15000
        if len(content) <= MAX_LEN:
            return self.send(title, content, template="markdown")
            
        logger.info(f"[Pushplus] 内容长达 {len(content)} 字符，超过单文件上限，执行拆分推送...")
        chunks = []
        parts = content.split("\n---\n")
        curr = ""
        for p in parts:
            if len(curr) + len(p) < MAX_LEN:
                curr += ("\n---\n" + p) if curr else p
            else:
                chunks.append(curr)
                curr = p
        if curr:
            chunks.append(curr)
            
        success = True
        for i, chunk in enumerate(chunks, 1):
            chunk_title = f"{title} (Part {i}/{len(chunks)})"
            if not self.send(chunk_title, chunk, template="markdown"):
                success = False
            import time
            time.sleep(1) # 避免推送被限流拦截
        return success

    def send_html(self, title: str, content: str) -> bool:
        """发送 HTML 格式消息"""
        return self.send(title, content, template="html")
