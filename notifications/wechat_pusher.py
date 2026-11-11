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
from datetime import datetime
from typing import List, Tuple, Dict, Any, Optional
from config import WeChatNotifyConfig
from models.stock_item import StrategySignal, PostMarketReportData, IntradayEvent
from utils.logger import get_logger

logger = get_logger("wechat_pusher")


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
            for k, v in s.key_factors.items():
                clean_k = k.strip("【】")
                lines.append(f"- **{clean_k}**: {v}")
            
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

    def _dispatch_push(self, title: str, markdown_body: str, log_tag: str = "微信推送") -> bool:
        """统一底层推送通道分发与容错"""
        if not self.config.ENABLED:
            logger.info(f"[{log_tag}] 配置为未开启状态 (ENABLED=False)，跳过网络推送。")
            return False

        channel = self.config.CHANNEL.lower()
        success = False

        if channel == "pushplus":
            success = self.send_pushplus(title, markdown_body)
        elif channel == "serverchan":
            success = self.send_serverchan(title, markdown_body)
        elif channel == "wecom":
            success = self.send_wecom(title, markdown_body)
        else:
            logger.error(f"[{log_tag}] 未知通道: {channel}，请在 config.py 中配置为 pushplus / serverchan / wecom")
            return False

        if success:
            logger.info(f"[{log_tag}成功] 标题: {title} 已成功送达微信！")
        else:
            logger.warning(f"[{log_tag}提示] 未能成功推送，请检查网络或 Token 配置。")
        return success

    def push(
        self,
        signals: List[StrategySignal],
        title: str,
        sentiment: Dict[str, Any]
    ) -> bool:
        """统一策略选股信号推送入口"""
        markdown_body = self.format_markdown_message(signals, title, sentiment)
        return self._dispatch_push(title, markdown_body, log_tag="策略信号推送")

    def format_post_market_report(
        self,
        r: PostMarketReportData,
        history_eval: Optional[Dict[str, Any]] = None
    ) -> str:
        """格式化适合微信手机阅读的 15:10 盘后涨停复盘与次日预案报告"""
        lines = []
        lines.append(f"### 📋【15:10 盘后涨停复盘·1进2/2进3/3进4】\n")
        lines.append(f"> **生成时间**: {r.report_time} | **昨日1/2/3板**: **{r.total_yesterday_count}** 家")
        lines.append(f"> **今日连板晋级**: <font color=\"#e74c3c\">**{r.today_continue_count}**</font> 家 | **断板**: {r.broken_board_count} 家 | **晋级率: {r.advancement_rate:.1f}%**")
        lines.append(f"> **最高连板高度**: **{r.highest_board_stock}**")
        
        # 梯队分布
        if r.tier_distribution:
            tier_str = " | ".join([f"{k}板 ({v}只)" for k, v in sorted(r.tier_distribution.items(), reverse=True)])
            lines.append(f"> **连板梯队**: {tier_str}")
        lines.append(f"> **明日打板总基调**: {r.sentiment_summary}\n")

        # 系统自建策略实战跟踪战绩（闭环验证）
        if history_eval and history_eval.get("total_count", 0) > 0:
            lines.append("---\n")
            lines.append(f"#### 🎯 【系统前日策略战绩闭环追踪】(推荐日: {history_eval['record_date']})")
            lines.append(
                f"> **推荐跟踪**: 共 **{history_eval['total_count']}** 只 | "
                f"今日封死涨停: <font color=\"#e74c3c\">**{history_eval['zt_count']}** 只 ({history_eval['zt_rate']:.1f}%)</font> | "
                f"收红胜率: **{history_eval['win_rate']:.1f}%**"
            )
            lines.append(f"> **日内冲高**: 候选股平均最高冲高 **+{history_eval['avg_max_gain']:.1f}%**")
            lines.append("- **个股实战核验**:")
            for item in history_eval.get("items", [])[:5]:
                status_tag = "<font color=\"#e74c3c\">【涨停封死 ✅】</font>" if item["is_limit_up"] else f"最高 +{item['max_gain']:.1f}%"
                lines.append(
                    f"  - **{item['name']} ({item['code']})** [{item['rec_time']}]: "
                    f"收盘 **{item['today_close']:.2f}元** ({item['today_pct']:+.2f}%) —— {status_tag}"
                )
            lines.append("")

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

    def push_post_market_report(
        self,
        report: PostMarketReportData,
        history_eval: Optional[Dict[str, Any]] = None
    ) -> bool:
        """推送 15:10 盘后涨停复盘与次日预案至微信（支持实战战绩追踪）"""
        title = f"📋【15:10 盘后涨停复盘】今日晋级率{report.advancement_rate:.1f}%，最高{report.highest_board}板"
        markdown_body = self.format_post_market_report(report, history_eval=history_eval)
        return self._dispatch_push(title, markdown_body, log_tag="盘后复盘推送")

    def format_intraday_events(self, events: List[IntradayEvent]) -> Tuple[str, str]:
        """格式化盘中涨停封板/炸板异动提醒，返回 (title, markdown_content)"""
        if not events:
            return "", ""

        if len(events) == 1:
            ev = events[0]
            relay_desc = f"{ev.continuous_boards - 1}进{ev.continuous_boards}" if ev.continuous_boards in (2, 3, 4) else f"{ev.continuous_boards}板"
            if ev.event_type == "LIMIT_UP":
                board_desc = f"{ev.continuous_boards}连板({relay_desc})" if ev.continuous_boards > 1 else "封板"
                title = f"⚡【盘中异动·涨停封板】{ev.name}({ev.code}) {board_desc}"
            else:
                title = f"⚠️【盘中异动·{relay_desc}炸板预警】{ev.name}({ev.code}) 炸板开板"
        else:
            zt_cnt = sum(1 for e in events if e.event_type == "LIMIT_UP")
            zb_cnt = sum(1 for e in events if e.event_type == "BROKEN_BOARD")
            summary_names = "、".join([e.name for e in events[:3]])
            if len(events) > 3:
                summary_names += f"等{len(events)}只"
            title = f"🔔【盘中异动·1进2/2进3/3进4】{summary_names} (封板{zt_cnt}家/炸板{zb_cnt}家)"

        lines = []
        lines.append(f"### {title}\n")
        lines.append(f"> **监控时段**: 09:30 - 14:50 盘中实时捕获 (1进2/2进3/3进4) | **捕获时间**: `{datetime.now().strftime('%H:%M:%S')}`\n")

        for idx, ev in enumerate(events, 1):
            industry_str = f" | 题材: **{ev.industry}**" if ev.industry else ""
            relay_desc = f"{ev.continuous_boards - 1}进{ev.continuous_boards}" if ev.continuous_boards in (2, 3, 4) else f"{ev.continuous_boards}板"
            if ev.event_type == "LIMIT_UP":
                tag = f"<font color=\"#e74c3c\">⚡【涨停封板·{relay_desc} ({ev.continuous_boards}连板)】</font>"
                lines.append(f"#### **{idx}. {ev.name} ({ev.code})** —— {tag}")
                lines.append(f"- **封板时间**: `{ev.event_time}` | **现价**: **{ev.current_price:.2f}元** (+{ev.change_pct:.2f}%){industry_str}")
                lines.append(f"- **盘口资金**: 封板资金 **{ev.seal_amount_wan:.0f}万元** | 换手率 **{ev.turnover_rate:.1f}%** | 炸板次数: **{ev.open_board_count}次**")
                lines.append(f"- **操作建议**: <font color=\"#e67e22\">**{ev.action_advice}**</font>")
                lines.append(f"- **原因逻辑**: {ev.reason}\n")
            else:
                tag = f"<font color=\"#2980b9\">⚠️【{relay_desc}炸板开板·今日第{ev.open_board_count}次】</font>"
                lines.append(f"#### **{idx}. {ev.name} ({ev.code})** —— {tag}")
                lines.append(f"- **炸板时间**: `{ev.event_time}` | **现价**: **{ev.current_price:.2f}元** ({ev.change_pct:+.2f}%){industry_str}")
                lines.append(f"- **换手特征**: 换手率 **{ev.turnover_rate:.1f}%**")
                lines.append(f"- **操作建议**: <font color=\"#2980b9\">**{ev.action_advice}**</font>")
                lines.append(f"- **原因逻辑**: {ev.reason}\n")

        lines.append("---\n*量化策略系统实时监测，交易有风险，请遵守打板纪律*")
        return title, "\n".join(lines)

    def push_intraday_events(self, events: List[IntradayEvent]) -> bool:
        """推送盘中异动事件至微信"""
        if not events:
            return False
        title, markdown_body = self.format_intraday_events(events)
        return self._dispatch_push(title, markdown_body, log_tag="盘中异动推送")

    def push_intraday_event(self, event: IntradayEvent) -> bool:
        """单只标的异动快捷推送"""
        return self.push_intraday_events([event])

