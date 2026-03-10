"""
交易通知模块 - 支持微信（Server酱）和邮件通知
"""
import os
import smtplib
from email.mime.text import MIMEText
from typing import Optional
from loguru import logger
import requests
from dotenv import load_dotenv


class Notifier:
    """
    交易通知器。

    支持:
    - Server酱（微信推送）: 设置环境变量 SERVERCHAN_KEY
    - 邮件通知: 设置 SMTP_HOST/SMTP_USER/SMTP_PASS/NOTIFY_EMAIL
    """

    def __init__(self):
        # 确保环境变量已加载
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        load_dotenv(os.path.join(base_dir, ".env"), override=True)

        self._serverchan_key = os.getenv("SERVERCHAN_KEY", "")
        self._smtp_host = os.getenv("SMTP_HOST", "")
        self._smtp_port = int(os.getenv("SMTP_PORT", "465"))
        self._smtp_user = os.getenv("SMTP_USER", "")
        self._smtp_pass = os.getenv("SMTP_PASS", "")
        self._notify_email = os.getenv("NOTIFY_EMAIL", "")

        if self._serverchan_key:
            logger.debug(f"Notifier: Server酱已配置 (Key前缀: {self._serverchan_key[:4]})")
        else:
            logger.warning("Notifier: Server酱密钥 (SERVERCHAN_KEY) 未配置！")

    def send(self, title: str, content: str) -> None:
        """发送通知（同时发送所有已配置的渠道）"""
        if self._serverchan_key:
            self._send_serverchan(title, content)
        if self._smtp_host and self._notify_email:
            self._send_email(title, content)
        if not self._serverchan_key and not self._smtp_host:
            logger.debug(f"通知（未配置推送渠道）: {title}")

    def notify_trade(
        self,
        etf_code: str,
        etf_name: str,
        side: str,
        price: float,
        quantity: int,
        reason: str,
    ) -> None:
        """发送交易通知"""
        title = f"[交易] {side} {etf_name}({etf_code})"
        content = (
            f"**{side}** {etf_name} ({etf_code})\n\n"
            f"- 价格: {price:.4f}\n"
            f"- 数量: {quantity} 股\n"
            f"- 金额: {price * quantity:,.2f}\n"
            f"- 原因: {reason}\n"
        )
        self.send(title, content)

    def notify_risk(self, etf_code: str, etf_name: str, reason: str) -> None:
        """发送风控预警通知"""
        title = f"[风控] {etf_name}({etf_code})"
        content = f"**风控预警** {etf_name} ({etf_code})\n\n{reason}"
        self.send(title, content)

    def notify_daily_report(self, report: str) -> None:
        """发送日报"""
        self.send("[日报] ETF T+0 交易日报", report)

    def notify_premarket_report(self, content: str) -> None:
        """发送盘前技术分析报告"""
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        title = f"📊 盘前技术分析 | {date_str}"
        self.send(title, content)

    def notify_trade_alert(self, content: str) -> None:
        """发送盘中交易信号提醒"""
        self.send("⚡ 交易信号提醒", content)

    # ------------------------------------------------------------------

    def _send_serverchan(self, title: str, content: str) -> None:
        """通过 Server酱 推送微信通知"""
        try:
            url = f"https://sctapi.ftqq.com/{self._serverchan_key}.send"
            resp = requests.post(url, data={
                "title": title[:100],
                "desp": content,
            }, timeout=10)
            if resp.status_code == 200:
                logger.debug(f"Server酱通知发送成功: {title}")
            else:
                logger.warning(f"Server酱通知失败: {resp.status_code}")
        except Exception as e:
            logger.warning(f"Server酱通知异常: {e}")

    def _send_email(self, title: str, content: str) -> None:
        """通过邮件发送通知"""
        try:
            msg = MIMEText(content, "plain", "utf-8")
            msg["Subject"] = title
            msg["From"] = self._smtp_user
            msg["To"] = self._notify_email

            with smtplib.SMTP_SSL(self._smtp_host, self._smtp_port) as server:
                server.login(self._smtp_user, self._smtp_pass)
                server.sendmail(self._smtp_user, [self._notify_email], msg.as_string())

            logger.debug(f"邮件通知发送成功: {title}")
        except Exception as e:
            logger.warning(f"邮件通知失败: {e}")
