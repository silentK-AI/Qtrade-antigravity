# A股打板量化策略系统 (主板竞价与尾盘选股)

本系统专门针对 A 股主板（沪深 10% 涨跌幅限制）设计，以**资金流向与大单锁盘为主导（权重占比 $\ge 55\% \sim 60\%$）**。支持部署在 Linux 云服务器上，全天候无人值守运行，并在交易日四大实战关键节点将精选标的与操作指引**实时推送到个人微信**。

---

## 一、 四大核心实战时间节点

| 时间节点 | 策略目标 | 实战买入窗口 | 预期效果 |
| :--- | :--- | :--- | :--- |
| **09:23:05** | **早盘不可撤单抢筹锁板** | **09:23:00 - 09:24:50** 直接挂涨停价，抢在09:25开盘撮合进场 | 锁定**当天封死一整天（零炸板）+ 次日继续涨停** |
| **09:25:05** | **开盘集合竞价精选** | 09:25 开盘分时回踩均线低吸或挂单 | 锁定 1进2 加速接力与弱转强反包标的 |
| **14:50:00** | **尾盘异动放量蓄势冲板** | 14:50 - 14:55 分批市价潜伏买入 | 均线上方强势横盘，主力尾盘大单抢筹，次日冲板 |
| **14:58:05** | **尾盘集合竞价锁定** | **14:58:00 - 14:59:50** 挂涨停价进入收盘竞价，15:00成交 | **尾盘回封/蓄势未板标的能买进**，锁定次日早盘直接涨停 |

---

## 二、 微信推送配置（3秒搞定个人微信接收）

系统支持国内最方便的免开发微信推送渠道（推荐 **PushPlus 推送加**，免费且直接发送至个人微信）：

### 推荐渠道：PushPlus (推送加)
1. 手机微信打开官网：[http://www.pushplus.plus/](http://www.pushplus.plus/) 微信扫码一键登录。
2. 复制您的 **Token**。
3. 打开 [config.py](file:///Users/jiangpei/Desktop/历史资料/工作/报销/Work键盘/Work键盘/量化分析系统/config.py)，找到 `WeChatNotifyConfig` 并填入：
   ```python
   @dataclass
   class WeChatNotifyConfig:
       ENABLED: bool = True            # 改为 True
       CHANNEL: str = "pushplus"       # 保持 pushplus
       PUSHPLUS_TOKEN: str = "您的Token" # 粘贴进去
   ```
4. 测试微信推送连通性：
   ```bash
   python3 daemon_scheduler.py --test-push
   ```
   您的手机微信即可立刻收到排版精美的选股卡片！

*(同时也兼容 Server酱 的 `SERVERCHAN_KEY` 与企业微信群机器人的 `WECOM_WEBHOOK_KEY`)*

---

## 三、 服务器部署方案（Linux 云服务器）

### ⚡ 一键切换模式：全面下线老系统，仅保留新系统
如果您之前已在服务器部署过旧版量化系统，我们提供了一键平滑替换脚本，**自动检测并继承老系统的 PushPlus Token，停止老进程，无缝切换为新服务**：
```bash
# 进入项目目录后直接执行一键替换切换脚本：
sudo bash deploy/replace_old_system.sh
```
该脚本会自动：
1. 提取并保留老系统的 `PUSHPLUS_TOKEN`；
2. 停止并清理服务器上残留的老进程与旧服务；
3. 注册新系统为开机自启的系统服务 `quant-screener` 并立即启动；
4. 发送一次测试消息至您的微信确认替换成功。

---

### 常规手动部署方案：Systemd 系统服务后台常驻
1. 将本项目上传至服务器 `/opt/quant_system` 目录：
   ```bash
   scp -r 量化分析系统 root@your-server-ip:/opt/quant_system
   ```
2. 注册为 Linux 系统服务：
   ```bash
   cp /opt/quant_system/deploy/quant-screener.service /etc/systemd/system/
   systemctl daemon-reload
   systemctl enable quant-screener    # 开机自启
   systemctl start quant-screener     # 立即启动
   ```
3. 查看运行日志与状态：
   ```bash
   systemctl status quant-screener
   journalctl -u quant-screener -f
   ```

### 方案 B：Docker / Docker-Compose 一键部署
```bash
cd deploy
docker-compose up -d --build
docker-compose logs -f
```

### 方案 C：简单后台挂起 (nohup)
```bash
nohup python3 daemon_scheduler.py --source live > /var/log/quant.log 2>&1 &
```

---

## 四、 本地手动测试与单元测试

```bash
# 1. 立即运行并向微信测试推送
python3 daemon_scheduler.py --test-push

# 2. 模拟运行单个模式
python3 run.py --mode 0923 --source mock
python3 run.py --mode 1458 --source mock

# 3. 运行全套 8 项单元测试
python3 -m unittest discover tests
```
