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
                "title": title,
                "content": content,
                "template": template,
            }

            resp = requests.post(self.api_url, json=payload, timeout=10)
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
        """发送 Markdown 格式消息"""
        return self.send(title, content, template="markdown")

    def send_html(self, title: str, content: str) -> bool:
        """发送 HTML 格式消息"""
        return self.send(title, content, template="html")
