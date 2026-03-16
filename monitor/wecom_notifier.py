"""
企业微信通知模块

支持文本、Markdown、卡片消息推送
"""
import requests
import json
from datetime import datetime
from typing import Optional
from loguru import logger


class WeCOMNotifier:
    """企业微信通知器"""

    def __init__(self, corp_id: str, agent_id: str, secret: str, user_id: str):
        """
        初始化企业微信通知器

        Args:
            corp_id: 企业 ID
            agent_id: 应用 ID
            secret: 应用密钥
            user_id: 接收人 UserID
        """
        self.corp_id = corp_id
        self.agent_id = agent_id
        self.secret = secret
        self.user_id = user_id
        self.access_token = None
        self.token_expire_time = 0
        self.base_url = "https://qyapi.weixin.qq.com/cgi-bin"

    def _get_access_token(self) -> str:
        """获取 access_token（7200秒有效期，自动缓存）"""
        import time
        now = time.time()
        if self.access_token and now < self.token_expire_time:
            return self.access_token

        try:
            url = f"{self.base_url}/gettoken"
            params = {
                "corpid": self.corp_id,
                "corpsecret": self.secret,
            }
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if data.get("errcode") == 0:
                self.access_token = data["access_token"]
                self.token_expire_time = now + 7000  # 提前10秒过期
                logger.debug(f"[企业微信] 获取 access_token 成功")
                return self.access_token
            else:
                logger.error(f"[企业微信] 获取 token 失败: {data.get('errmsg')}")
                return None
        except Exception as e:
            logger.error(f"[企业微信] 获取 token 异常: {e}")
            return None

    def send_text(self, content: str, title: str = "") -> bool:
        """
        发送文本消息

        Args:
            content: 消息内容
            title: 消息标题（可选）

        Returns:
            是否发送成功
        """
        token = self._get_access_token()
        if not token:
            return False

        try:
            url = f"{self.base_url}/message/send"
            params = {"access_token": token}
            
            if title:
                content = f"**{title}**\n\n{content}"

            payload = {
                "touser": self.user_id,
                "msgtype": "text",
                "agentid": self.agent_id,
                "text": {
                    "content": content,
                },
                "safe": 0,
            }

            resp = requests.post(url, params=params, json=payload, timeout=10)
            data = resp.json()
            if data.get("errcode") == 0:
                logger.debug(f"[企业微信] 文本消息发送成功: {data.get('msgid')}")
                return True
            else:
                logger.warning(f"[企业微信] 文本消息发送失败: {data.get('errmsg')}")
                return False
        except Exception as e:
            logger.error(f"[企业微信] 发送文本消息异常: {e}")
            return False

    def send_markdown(self, content: str, title: str = "") -> bool:
        """
        发送 Markdown 消息

        Args:
            content: Markdown 内容
            title: 消息标题（可选）

        Returns:
            是否发送成功
        """
        token = self._get_access_token()
        if not token:
            return False

        try:
            url = f"{self.base_url}/message/send"
            params = {"access_token": token}

            if title:
                content = f"# {title}\n\n{content}"

            payload = {
                "touser": self.user_id,
                "msgtype": "markdown",
                "agentid": self.agent_id,
                "markdown": {
                    "content": content,
                },
            }

            resp = requests.post(url, params=params, json=payload, timeout=10)
            data = resp.json()
            if data.get("errcode") == 0:
                logger.debug(f"[企业微信] Markdown 消息发送成功: {data.get('msgid')}")
                return True
            else:
                logger.warning(f"[企业微信] Markdown 消息发送失败: {data.get('errmsg')}")
                return False
        except Exception as e:
            logger.error(f"[企业微信] 发送 Markdown 消息异常: {e}")
            return False

    def send_card(self, title: str, content: str, url: str = "", btn_text: str = "查看详情") -> bool:
        """
        发送卡片消息

        Args:
            title: 卡片标题
            content: 卡片内容
            url: 点击卡片跳转的 URL（可选）
            btn_text: 按钮文本

        Returns:
            是否发送成功
        """
        token = self._get_access_token()
        if not token:
            return False

        try:
            url_api = f"{self.base_url}/message/send"
            params = {"access_token": token}

            payload = {
                "touser": self.user_id,
                "msgtype": "news",
                "agentid": self.agent_id,
                "news": {
                    "articles": [
                        {
                            "title": title,
                            "description": content,
                            "url": url or "",
                            "picurl": "",
                        }
                    ]
                },
            }

            resp = requests.post(url_api, params=params, json=payload, timeout=10)
            data = resp.json()
            if data.get("errcode") == 0:
                logger.debug(f"[企业微信] 卡片消息发送成功: {data.get('msgid')}")
                return True
            else:
                logger.warning(f"[企业微信] 卡片消息发送失败: {data.get('errmsg')}")
                return False
        except Exception as e:
            logger.error(f"[企业微信] 发送卡片消息异常: {e}")
            return False
