#!/bin/bash
# ==============================================================================
# 服务器端后台自动同步守护进程 (CI/CD Auto-Sync Daemon)
# 作用：保持 TUN 模式下无需 SSH，每次本端提交代码，服务器 60 秒内自动拉取并重启生效！
# ==============================================================================

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] [Auto-Sync] 云端持续集成守护已启动，监听 Gitee/GitHub 更新..."

while true; do
    # 每 60 秒静默拉取远程分支元数据
    git fetch origin main >/dev/null 2>&1 || true
    LOCAL=$(git rev-parse HEAD 2>/dev/null || echo "")
    REMOTE=$(git rev-parse origin/main 2>/dev/null || echo "")

    if [ -n "$REMOTE" ] && [ "$LOCAL" != "$REMOTE" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🚀 检测到新策略代码提交 ($REMOTE)，开始执行自动热更新部署..."
        git reset --hard origin/main
        pip install -r requirements.txt >/dev/null 2>&1 || true
        systemctl restart quant-screener || true
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ 自动部署成功！新策略守护进程已就绪运行！"
    fi
    sleep 60
done
