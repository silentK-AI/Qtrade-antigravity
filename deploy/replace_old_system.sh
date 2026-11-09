#!/bin/bash
# ==============================================================================
# 一键下线老系统并全面上线全新【A股打板量化分析系统】
# 执行说明:
#   1. 上传本系统至服务器 (如 /opt/quant_system)
#   2. 赋予执行权限: chmod +x deploy/replace_old_system.sh
#   3. 执行切换: sudo bash deploy/replace_old_system.sh
# ==============================================================================

set -e

APP_DIR="/opt/quant_system"
SERVICE_NAME="quant-screener"

echo "=================================================================="
echo "    开始执行：下线老量化系统 -> 上线全新打板量化分析系统 (PushPlus)  "
echo "=================================================================="

# 1. 尝试备份/提取现有老环境中的 PUSHPLUS_TOKEN
DETECTED_TOKEN=""
if [ -n "$PUSHPLUS_TOKEN" ]; then
    DETECTED_TOKEN="$PUSHPLUS_TOKEN"
    echo "[配置继承] 检测到系统环境变量中已有 PUSHPLUS_TOKEN"
elif [ -f "/opt/quant_old/.env" ]; then
    DETECTED_TOKEN=$(grep -E "PUSHPLUS_TOKEN|PUSH_PLUS_TOKEN" /opt/quant_old/.env | cut -d '=' -f2 | tr -d '"' | tr -d "'" || true)
elif [ -f "/opt/quant_old/config.py" ]; then
    DETECTED_TOKEN=$(grep -oE "pushplus_token\s*=\s*['\"][^'\"]+['\"]" /opt/quant_old/config.py | cut -d"'" -f2 | cut -d'"' -f2 || true)
fi

# 2. 停用并下线老系统的后台进程与服务
echo "[步骤 1/4] 正在排查并下线老系统的运行进程..."

# 停用可能存在的旧 systemd 服务 (如 quant, stock, trading 等常见名)
for old_svc in quant-old quant stock-screener trading-bot myquant; do
    if systemctl is-active --quiet "$old_svc" 2>/dev/null; then
        echo "  - 停止旧系统服务: $old_svc"
        systemctl stop "$old_svc" || true
        systemctl disable "$old_svc" || true
    fi
done

# 终止可能在后台 nohup 运行的老 python 调度进程 (排除当前脚本)
echo "  - 清理后台残留的老量化进程..."
pkill -f "daemon_scheduler.py" 2>/dev/null || true
pkill -f "scheduler.py" 2>/dev/null || true

# 3. 部署新系统代码并配置
echo "[步骤 2/4] 配置全新量化系统目录与环境变量..."

# 确保目标运行目录就绪
mkdir -p "$APP_DIR"
cp -r . "$APP_DIR/"
cd "$APP_DIR"

# 如果提取到了老系统的 token，自动注入到 config.py 或 .env
if [ -n "$DETECTED_TOKEN" ]; then
    echo "  - 自动继承老系统的 PushPlus Token: ${DETECTED_TOKEN:0:8}********"
    export PUSHPLUS_TOKEN="$DETECTED_TOKEN"
    echo "PUSHPLUS_TOKEN=$DETECTED_TOKEN" > "$APP_DIR/.env"
fi

# 安装基础依赖
echo "[步骤 3/4] 检查 Python 运行环境与依赖..."
python3 -m pip install -r requirements.txt || true

# 4. 注册全新的 systemd 系统服务，接管 24 小时自动调度
echo "[步骤 4/4] 注册并启动全新打板量化守护服务 (开机自启)..."

cat <<EOF > /etc/systemd/system/${SERVICE_NAME}.service
[Unit]
Description=A-Share Limit Up Screener & WeChat Push Daemon
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/python3 ${APP_DIR}/daemon_scheduler.py --source live
Restart=always
RestartSec=10
EnvironmentFile=-${APP_DIR}/.env
Environment=PYTHONUNBUFFERED=1
Environment=TZ=Asia/Shanghai

[Install]
WantedBy=multi-user.target
EOF

# 启动并激活新服务
systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
systemctl restart ${SERVICE_NAME}

echo "=================================================================="
echo "    切换完成！新量化系统已全面接管服务器！"
echo "    - 守护服务名: ${SERVICE_NAME}"
echo "    - 运行状态: $(systemctl is-active ${SERVICE_NAME})"
echo "    - 查看实时日志: journalctl -u ${SERVICE_NAME} -f"
echo "=================================================================="

# 5. 执行一次快速验证
python3 daemon_scheduler.py --test-push || true
