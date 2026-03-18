"""
个股技术指标监控云端无人值守自动化调度脚本 (7x24 小时运行)

功能:
  - 每天 08:30: 启动个股技术指标监控
  - 每天 16:10: 终止个股监控进程
  - 休眠至次日循环
"""
import schedule
import time
import subprocess
import sys
import os
from datetime import datetime
from loguru import logger

# 把项目根目录加到 sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

# 记录当前运行的股票监控进程引用
current_alert_process = None

def setup_scheduler_logger():
    logger.remove()
    logger.add(
        "logs/stock_scheduler_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
    )
    logger.add(sys.stdout, format="<g>{time:YYYY-MM-DD HH:mm:ss}</g> | <lvl>{level: <8}</lvl> | <lvl>{message}</lvl>")

def job_start_alert_monitor():
    """每天 08:30 启动个股技术指标监控"""
    if datetime.now().weekday() >= 5:
        logger.info("今天是周末，跳过个股监控启动。")
        return

    global current_alert_process

    if current_alert_process and current_alert_process.poll() is None:
        logger.warning("监控进程已在运行，尝试先杀掉旧进程...")
        current_alert_process.terminate()
        current_alert_process.wait()

    logger.info("=== 触发: 启动个股技术指标监控 ===")

    cmd = [sys.executable, "scripts/stock_alert_monitor.py"]

    try:
        current_alert_process = subprocess.Popen(
            cmd,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        logger.info(f"监控进程已在后台启动 (PID: {current_alert_process.pid})")
    except Exception as e:
        logger.error(f"启动监控进程失败: {e}")


def job_stop_alert_monitor():
    """每天 16:10 终止个股监控进程"""
    if datetime.now().weekday() >= 5:
        return

    global current_alert_process

    logger.info("=== 触发: 终止个股监控 ===")
    if current_alert_process and current_alert_process.poll() is None:
        logger.info(f"正在向监控进程 (PID: {current_alert_process.pid}) 发送终止信号...")
        current_alert_process.terminate()

        try:
            current_alert_process.wait(timeout=15)
            logger.info("监控进程已优雅关闭。")
        except subprocess.TimeoutExpired:
            current_alert_process.kill()
            logger.info("监控进程已被强制杀死。")

        current_alert_process = None
    else:
        logger.info("没有发现正在运行的监控进程。")


def start_scheduler():
    setup_scheduler_logger()
    logger.info("=====================================")
    logger.info("  个股监控 7x24 云端调度器已启动")
    logger.info("=====================================")
    
    # 设定定时任务
    schedule.every().day.at("08:30").do(job_start_alert_monitor)
    schedule.every().day.at("15:30").do(job_stop_alert_monitor)  # A股收盘后兜底终止
    
    # 打印当前所有排期的任务
    logger.info("当前设定的定时任务:")
    for job in schedule.get_jobs():
        logger.info(f" -> {job}")
        
    logger.info("进入挂起循环，按 Ctrl+C 退出...")
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到退出信号，调度器准备关闭...")
        if current_alert_process and current_alert_process.poll() is None:
            logger.info("正在清理附带的监控进程...")
            current_alert_process.terminate()
        logger.info("调度器已退出。")

if __name__ == "__main__":
    start_scheduler()
