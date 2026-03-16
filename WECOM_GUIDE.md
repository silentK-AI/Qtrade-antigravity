# 企业微信通知使用指南

## 1. 配置企业微信

### 1.1 获取企业 ID
1. 登录 [企业微信管理后台](https://work.weixin.qq.com/)
2. 进入「我的企业」
3. 复制「企业 ID」（CorpID）

### 1.2 创建应用
1. 进入「应用管理」→ 「创建应用」
2. 填写应用名称（如 "交易通知"）
3. 选择可见范围（选择你的账号）
4. 创建后获得：
   - **应用 ID**（AgentID）
   - **应用密钥**（Secret）

### 1.3 获取接收人 UserID
1. 进入「通讯录」
2. 点击你的账号
3. 复制 **UserID**（通常是你的企业微信账号名）

## 2. 配置 .env 文件

在项目根目录的 `.env` 文件中添加：

```env
# 企业微信配置
WECOM_CORP_ID=wwf31f6a2077ea8791
WECOM_AGENT_ID=1000002
WECOM_SECRET=6hSsinqYsURS55FnQ8Dhog7ZvF6Te0KbObZFmYUD8jc
WECOM_USER_ID=JiangPei
```

## 3. 使用方式

### 3.1 在代码中使用

```python
from monitor.notifier import Notifier

notifier = Notifier()

# 发送通知
notifier.send("标题", "内容（支持 Markdown）")

# 发送交易通知
notifier.notify_trade(
    etf_code="159770",
    etf_name="机器人ETF",
    side="BUY",
    price=15.23,
    quantity=100,
    reason="触及支撑位"
)

# 发送交易信号提醒
notifier.notify_trade_alert("⚡ 603667 五洲新春 触及 S1 支撑位")
```

### 3.2 通过 HTTP API 调用

启动 HTTP 服务：

```bash
python -m monitor.notify_api
```

服务运行在 `http://localhost:5000`

#### 发送通知

```bash
curl -X POST http://localhost:5000/api/notify \
  -H "Content-Type: application/json" \
  -d '{
    "title": "📊 盘前技术分析",
    "content": "# 今日行情\n\n- VIX: 26.95\n- 恐贪指数: 15（极度恐慌）"
  }'
```

#### 发送交易通知

```bash
curl -X POST http://localhost:5000/api/notify/trade \
  -H "Content-Type: application/json" \
  -d '{
    "etf_code": "159770",
    "etf_name": "机器人ETF",
    "side": "BUY",
    "price": 15.23,
    "quantity": 100,
    "reason": "触及支撑位"
  }'
```

#### 发送交易信号提醒

```bash
curl -X POST http://localhost:5000/api/notify/alert \
  -H "Content-Type: application/json" \
  -d '{
    "content": "⚡ 603667 五洲新春 触及 S1 支撑位 + RSI 超卖"
  }'
```

#### 健康检查

```bash
curl http://localhost:5000/health
```

## 4. 多渠道通知

系统支持同时配置多个通知渠道，会自动发送到所有已配置的渠道：

- **Server 酱**（微信）：设置 `SERVERCHAN_KEY`
- **企业微信**：设置 `WECOM_CORP_ID` 等四个参数
- **邮件**：设置 `SMTP_HOST` 等参数

## 5. 企业微信消息格式

### 文本消息

```python
notifier._wecom_notifier.send_text("这是一条文本消息")
```

### Markdown 消息

```python
notifier._wecom_notifier.send_markdown("""
# 标题

- 项目 1
- 项目 2

**加粗文本**
""")
```

### 卡片消息

```python
notifier._wecom_notifier.send_card(
    title="卡片标题",
    content="卡片内容描述",
    url="https://example.com",
    btn_text="查看详情"
)
```

## 6. 常见问题

### Q: 为什么收不到消息？
A: 检查以下几点：
1. 企业微信配置是否正确（CorpID、AgentID、Secret、UserID）
2. 应用是否已启用
3. 接收人是否在应用的可见范围内
4. 查看日志是否有错误信息

### Q: 如何设置多个接收人？
A: 目前代码支持单个 UserID，如需多人接收，可修改 `wecom_notifier.py` 中的 `touser` 参数为多个 UserID（用 `|` 分隔）或使用部门 ID。

### Q: 企业微信和 Server 酱可以同时使用吗？
A: 可以，只需同时配置两个的环境变量即可。系统会自动发送到所有已配置的渠道。

### Q: HTTP API 如何部署到服务器？
A: 可以使用 Gunicorn 或 uWSGI 部署：

```bash
# 使用 Gunicorn
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 'monitor.notify_api:create_notify_app()'

# 或使用 uWSGI
pip install uwsgi
uwsgi --http :5000 --wsgi-file monitor/notify_api.py --callable create_notify_app
```

## 7. 集成到现有脚本

在 `scripts/stock_alert_monitor.py` 中已自动使用 `Notifier`，无需额外配置。

在 `trader/trader.py` 中的交易执行也会自动推送通知。

所有通知都会同时发送到已配置的所有渠道。
