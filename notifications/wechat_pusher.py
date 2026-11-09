"""
微信消息推送服务封装
支持国内主流免服务器/免费的个人微信通知渠道：
1. PushPlus (推送加) —— 微信扫码即用，个人微信直接接收卡片，支持Markdown/富文本 (推荐)
2. Server酱 (Turbo版) —— 微信扫码即用，方糖微信服务号接收
3. 企业微信群机器人 / 微信插件 —— 零成本，直接映射推送到微信
4. WxPusher (微信推送平台) —— 免费微信公众号消息触达
"""

import time
import json
import urllib.request
import urllib.parse
from typing import List, Tuple, Dict, Any, Optional
from config import WeChatNotifyConfig
from models.stock_item import StrategySignal, PostMarketReportData


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

        # 2. 候选标的列表（精选评分最高的前8只标的，兼顾手机阅读与通道字数限制）
        if not signals:
            lines.append("当前时段未筛选出符合评分阈值（综合>=80且资金充沛）的确定性标的，建议防守观望。")
            return "\n".join(lines)

        for idx, s in enumerate(signals[:8], 1):
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

    def _split_markdown_chunks(self, text: str, max_chars: int = 12000) -> List[str]:
        """按段落或分隔线智能切分 Markdown，避免截断单行内容"""
        if len(text) <= max_chars:
            return [text]

        chunks = []
        lines = text.split("\n")
        current_chunk = []
        current_len = 0

        for line in lines:
            line_len = len(line) + 1
            if current_len + line_len > max_chars and current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = [line]
                current_len = line_len
            else:
                current_chunk.append(line)
                current_len += line_len

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        return chunks

    def _send_pushplus_payload(self, title: str, content: str) -> Tuple[bool, Dict[str, Any]]:
        """执行单次 PushPlus HTTP 请求"""
        url = "http://www.pushplus.plus/send"
        payload = {
            "token": self.config.PUSHPLUS_TOKEN,
            "title": title,
            "content": content,
            "template": "markdown"
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return (result.get("code") == 200, result)
        except Exception as e:
            return (False, {"code": -1, "msg": str(e)})

    def send_pushplus(self, title: str, content_markdown: str) -> bool:
        """通过 PushPlus (推送加) 发送到微信，含超长自动分段发送与容错重发保护"""
        if not self.config.PUSHPLUS_TOKEN:
            return False

        # 1. 预先保护：若内容字数超过安全阈值（12,000字，远低于通道20,000上限），主动切分多段分批发送
        chunks = self._split_markdown_chunks(content_markdown, max_chars=12000)
        if len(chunks) > 1:
            print(f"[微信推送防护] 内容总长 {len(content_markdown)} 字，已自动切分为 {len(chunks)} 段分批推送...")
            all_success = True
            for i, chunk in enumerate(chunks, 1):
                chunk_title = f"{title} (分段 {i}/{len(chunks)})"
                ok, res = self._send_pushplus_payload(chunk_title, chunk)
                if not ok:
                    print(f"[微信推送失败] 分段 {i} 推送异常: {res}")
                    all_success = False
                time.sleep(1)
            return all_success

        # 2. 单段正常发送
        success, res = self._send_pushplus_payload(title, content_markdown)
        if success:
            return True

        # 3. 容错保护：若服务端返回内容过大 (code 999 或提示超长)，自动降级强制切成两段重新补发
        err_msg = str(res.get("msg", "")) + str(res.get("data", ""))
        if res.get("code") == 999 or "过大" in err_msg or "超过" in err_msg or "2万" in err_msg:
            print(f"[微信推送熔断保护] 检测到服务端拒绝超长内容 ({err_msg})，立即启动紧急切分多段重发机制...")
            half_chunks = self._split_markdown_chunks(content_markdown, max_chars=max(len(content_markdown) // 2 + 100, 1000))
            all_ok = True
            for i, chunk in enumerate(half_chunks, 1):
                chunk_title = f"{title} (补发分段 {i}/{len(half_chunks)})"
                ok, r = self._send_pushplus_payload(chunk_title, chunk)
                if not ok:
                    print(f"[微信推送重发失败] 分段 {i} 仍失败: {r}")
                    all_ok = False
                time.sleep(1)
            return all_ok

        print(f"[微信推送失败] PushPlus 接口返回: {res}")
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

    def format_post_market_report(self, r: PostMarketReportData) -> str:
        """格式化适合微信手机阅读的 15:10 盘后涨停复盘与次日预案报告"""
        lines = []
        lines.append(f"### 📋【15:10 盘后涨停复盘与次日打板预案】\n")
        lines.append(f"> **生成时间**: {r.report_time} | **主板昨日涨停**: **{r.total_yesterday_count}** 家")
        lines.append(f"> **今日连板晋级**: <font color=\"#e74c3c\">**{r.today_continue_count}**</font> 家 | **断板**: {r.broken_board_count} 家 | **晋级率: {r.advancement_rate:.1f}%**")
        lines.append(f"> **最高连板高度**: **{r.highest_board_stock}**")
        
        # 梯队分布
        if r.tier_distribution:
            tier_str = " | ".join([f"{k}板 ({v}只)" for k, v in sorted(r.tier_distribution.items(), reverse=True)])
            lines.append(f"> **连板梯队**: {tier_str}")
        lines.append(f"> **明日打板总基调**: {r.sentiment_summary}\n")
        lines.append("---\n")

        # 区分连板组与断板组
        continue_items = [x for x in r.items if x.is_today_limit_up]
        broken_items = [x for x in r.items if not x.is_today_limit_up]

        if continue_items:
            lines.append(f"#### 🚀 【连板晋级池】(共 {len(continue_items)} 只·重点观察接力)\n")
            for idx, item in enumerate(continue_items, 1):
                lines.append(f"**{idx}. {item.name} ({item.code})** —— {item.board_status}")
                lines.append(f"- **今日表现**: 收盘 **{item.close_price:.2f}元** ({item.close_pct:+.2f}%) | 最高: **{item.high_pct:+.2f}%** | 最低: **{item.low_pct:+.2f}%**")
                lines.append(f"- **量能特征**: 换手率 **{item.turnover_rate:.1f}%** | 成交额 **{item.amount_yi:.1f}亿**")
                lines.append(f"- **次日打板建议**: <font color=\"#e67e22\">**{item.next_day_action}**</font>")
                lines.append(f"- **预案要点**: {item.detail_reason}\n")

        if broken_items:
            lines.append(f"#### ⚠️ 【断板分歧池】(精选前排·区分反包与风险)\n")
            for idx, item in enumerate(broken_items[:15], 1): # 选取最具代表性的断板标的
                lines.append(f"**{idx}. {item.name} ({item.code})** —— {item.board_status}")
                lines.append(f"- **今日表现**: 收盘 **{item.close_price:.2f}元** ({item.close_pct:+.2f}%) | 最高: **{item.high_pct:+.2f}%** | 最低: **{item.low_pct:+.2f}%**")
                lines.append(f"- **次日打板建议**: <font color=\"#2980b9\">**{item.next_day_action}**</font>")
                lines.append(f"- **预案要点**: {item.detail_reason}\n")

        lines.append("\n*注：15:10 盘后自动清算复盘，打板交易有风险，严格遵守仓位纪律*")
        return "\n".join(lines)

    def push_post_market_report(self, report: PostMarketReportData) -> bool:
        """推送 15:10 盘后涨停复盘与次日预案至微信"""
        title = f"📋【15:10 盘后涨停复盘】今日晋级率{report.advancement_rate:.1f}%，最高{report.highest_board}板"
        if not self.config.ENABLED:
            print("[微信推送] 配置为未开启状态 (ENABLED=False)，跳过网络推送。")
            return False

        markdown_body = self.format_post_market_report(report)
        channel = self.config.CHANNEL.lower()
        success = False

        if channel == "pushplus":
            success = self.send_pushplus(title, markdown_body)
        elif channel == "serverchan":
            success = self.send_serverchan(title, markdown_body)
        elif channel == "wecom":
            success = self.send_wecom(title, markdown_body)
        else:
            print(f"[微信推送] 未知通道: {channel}")
            return False

        if success:
            print(f"[微信推送成功] 盘后复盘报告已成功送达微信！")
        else:
            print(f"[微信推送提示] 盘后复盘推送未能送达，请检查网络或Token。")
        return success

