"""
微信消息推送服务封装
支持国内主流免服务器/免费的个人微信通知渠道：
1. PushPlus (推送加) —— 微信扫码即用，个人微信直接接收卡片，支持Markdown/富文本 (推荐)
2. Server酱 (Turbo版) —— 微信扫码即用，方糖微信服务号接收
3. 企业微信群机器人 / 微信插件 —— 零成本，直接映射推送到微信
4. WxPusher (微信推送平台) —— 免费微信公众号消息触达
"""

import json
import urllib.request
import urllib.parse
from typing import List, Dict, Any, Optional
from config import WeChatNotifyConfig
from models.stock_item import StrategySignal


class WeChatPusher:
    """微信通知分发器"""

    def __init__(self, config: Optional[WeChatNotifyConfig] = None):
        self.config = config or WeChatNotifyConfig()

    def format_markdown_message(
        self,
        signals: List[StrategySignal],
        title: str,
        sentiment: Dict[str, Any]
    ) -> str:
        """格式化适合微信手机端阅读的精美 Markdown 内容"""
        lines = []
        lines.append(f"### {title}\n")
        
        # 1. 市场天气与大局观
        if sentiment:
            lines.append(
                f"> **市场天气**: {sentiment.get('status', '正常')} | "
                f"涨停: <font color=\"#e74c3c\">{sentiment.get('limit_up_count', 0)}</font> 家 | "
                f"炸板率: {sentiment.get('exploded_ratio', 0):.1f}% | "
                f"高度: {sentiment.get('highest_continuous_board', 1)}板"
            )
            lines.append(f"> **主线题材**: {sentiment.get('top_theme', '全市场轮动')}\n")

        # 2. 候选标的列表
        if not signals:
            lines.append("当前时段未筛选出符合评分阈值（综合>=80且资金充沛）的确定性标的，建议防守观望。")
            return "\n".join(lines)

        for idx, s in enumerate(signals, 1):
            lines.append(f"#### **{idx}. {s.name} ({s.code})** —— {s.target_pattern}")
            lines.append(f"- **现价/涨幅**: **{s.current_price:.2f}元** ({s.change_pct:+.2f}%)")
            lines.append(f"- **综合评分**: **{s.score:.1f}分** | **资金得分: {s.capital_score:.1f}分**")
            
            # 关键资金面与可买入性
            cap_evidences = [v for k, v in s.key_factors.items() if "资金" in k or "可买入" in k]
            if cap_evidences:
                lines.append(f"- **资金面与可买入**: {cap_evidences[0]}")
            
            lines.append(f"- **操作指引**: <font color=\"#e67e22\">**{s.suggested_action}**</font>")
            lines.append(f"- **防守止损**: {s.stop_loss_price:.2f}元")
            lines.append(f"- **次日涨停预期**: {s.next_day_expectation}\n")
            lines.append("---")

        lines.append(f"\n*量化策略系统自动监控推送，交易有风险，请遵守交易纪律*")
        return "\n".join(lines)

    def send_pushplus(self, title: str, content_markdown: str) -> bool:
        """通过 PushPlus (推送加) 发送到个人微信"""
        if not self.config.PUSHPLUS_TOKEN:
            return False

        url = "http://www.pushplus.plus/send"
        payload = {
            "token": self.config.PUSHPLUS_TOKEN,
            "title": title,
            "content": content_markdown,
            "template": "markdown"
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("code") == 200
        except Exception as e:
            print(f"[微信推送异常] PushPlus 发送失败: {e}")
            return False

    def send_serverchan(self, title: str, content_markdown: str) -> bool:
        """通过 Server酱 发送到微信"""
        if not self.config.SERVERCHAN_KEY:
            return False

        url = f"https://sctapi.ftqq.com/{self.config.SERVERCHAN_KEY}.send"
        data = urllib.parse.urlencode({
            "title": title,
            "desp": content_markdown
        }).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=8) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("code") == 0
        except Exception as e:
            print(f"[微信推送异常] Server酱 发送失败: {e}")
            return False

    def send_wecom(self, title: str, content_markdown: str) -> bool:
        """通过 企业微信机器人 发送 (微信插件可直接在普通微信接收)"""
        if not self.config.WECOM_WEBHOOK_KEY:
            return False

        url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={self.config.WECOM_WEBHOOK_KEY}"
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"## {title}\n" + content_markdown
            }
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("errcode") == 0
        except Exception as e:
            print(f"[微信推送异常] 企业微信 发送失败: {e}")
            return False

    def push(
        self,
        signals: List[StrategySignal],
        title: str,
        sentiment: Dict[str, Any]
    ) -> bool:
        """
        统一推送入口：根据配置的通道自动分发
        """
        if not self.config.ENABLED:
            print("[微信推送] 配置为未开启状态 (ENABLED=False)，跳过网络推送。")
            return False

        markdown_body = self.format_markdown_message(signals, title, sentiment)
        channel = self.config.CHANNEL.lower()
        success = False

        if channel == "pushplus":
            success = self.send_pushplus(title, markdown_body)
        elif channel == "serverchan":
            success = self.send_serverchan(title, markdown_body)
        elif channel == "wecom":
            success = self.send_wecom(title, markdown_body)
        else:
            print(f"[微信推送] 未知通道: {channel}，请在 config.py 中配置为 pushplus / serverchan / wecom")
            return False

        if success:
            print(f"[微信推送成功] 标题: {title} 已成功送达微信！")
        else:
            print(f"[微信推送提示] 未能成功推送，请检查 config.py 中的 Token 或 Key 配置。")
        return success
