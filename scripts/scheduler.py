"""
云端无人值守自动化调度脚本 (7x24 小时运行)

用法:
  python scripts/scheduler.py

功能:
  - 每天 09:00: 自动拉取数据并训练 ML 模型
  - 每天 09:25: 启动实盘（或模拟）交易引擎
  - 每天 15:00: 收盘，自动结束当天的交易引擎进程，打印日终报告
  - 休眠至次日 09:00 循环
"""
import schedule
import time
import subprocess
import threading
from datetime import datetime
from loguru import logger
import traceback
import sys
import os

# 把项目根目录加到 sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from config.settings import ACTIVE_ETFS

# 记录当前运行的交易进程引用
current_trading_process = None
# 记录当前运行的股票监控进程引用
current_alert_process = None

def setup_scheduler_logger():
    logger.remove()
    logger.add(
        "logs/scheduler_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
    )
    logger.add(sys.stdout, format="<g>{time:YYYY-MM-DD HH:mm:ss}</g> | <lvl>{level: <8}</lvl> | <lvl>{message}</lvl>")

def run_command(cmd_list, description):
    """阻塞运行系统命令并把结果打印出来"""
    logger.info(f"[{description}] 开始运行: {' '.join(cmd_list)}")
    try:
        result = subprocess.run(cmd_list, capture_output=True, text=True, check=True)
        logger.info(f"[{description}] 运行成功.")
        logger.debug(f"输出:\n{result.stdout}")
    except subprocess.CalledProcessError as e:
        logger.error(f"[{description}] 运行失败! 错误码: {e.returncode}")
        logger.error(f"错误输出:\n{e.stderr}")
    except Exception as e:
        logger.error(f"[{description}] 执行异常: {e}")

def job_train_model():
    """每天早上拉取数据并训练模型"""
    if datetime.now().weekday() >= 5: # 周六周日不跑
        logger.info("今天是周末，跳过模型训练。")
        return
        
    logger.info("=== 触发: 每日 ML 模型特征获取与训练 ===")
    cmd = [sys.executable, "main.py", "train"]
    # 也可以加上 --etf 参数来指定
    run_command(cmd, "模型训练")

def job_start_trading():
    """每天盘前启动交易主进程"""
    if datetime.now().weekday() >= 5:
        logger.info("今天是周末，跳过交易启动。")
        return
        
    global current_trading_process
    
    if current_trading_process and current_trading_process.poll() is None:
        logger.warning("交易进程已在运行，尝试先杀掉旧进程...")
        current_trading_process.terminate()
        current_trading_process.wait()
    
    logger.info("=== 触发: 启动 T+0 交易引擎 ===")
    
    # 根据需要修改为 'live' 或 'paper'
    cmd = [sys.executable, "main.py", "paper"]
    
    try:
        current_trading_process = subprocess.Popen(
            cmd, 
            stdout=sys.stdout, 
            stderr=sys.stderr
        )
        logger.info(f"交易进程已在后台启动 (PID: {current_trading_process.pid})")
    except Exception as e:
        logger.error(f"启动交易进程失败: {e}")

def job_stop_trading():
    """每天收盘后终止交易进程"""
    if datetime.now().weekday() >= 5:
        return
        
    global current_trading_process
    
    logger.info("=== 触发: 每日收盘清算 ===")
    if current_trading_process and current_trading_process.poll() is None:
        logger.info(f"正在向交易进程 (PID: {current_trading_process.pid}) 发送终止信号...")
        # 发送终止信号，main.py 内部会捕获 SIGINT/SIGTERM 进行日终报告和优雅退出
        current_trading_process.terminate()
        
        # 等待最多 30 秒以便它能打印出日终报告
        try:
            current_trading_process.wait(timeout=30)
            logger.info("交易引擎已优雅关闭。")
        except subprocess.TimeoutExpired:
            logger.warning("交易引擎未能在30秒内关闭，准备强制杀死 (SIGKILL)...")
            current_trading_process.kill()
            logger.info("交易引擎已被强制杀死。")
            
        current_trading_process = None
    else:
        logger.info("没有发现正在运行的交易进程。")

# ------------------------------------------------------------------
#  个股监控进程管理
# ------------------------------------------------------------------

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
    logger.info("  Quati Trade 7x24 云端调度器已启动")
    logger.info("=====================================")
    
    # 设定定时任务
    schedule.every().day.at("08:30").do(job_start_alert_monitor)
    schedule.every().day.at("09:00").do(job_train_model)
    schedule.every().day.at("09:25").do(job_start_trading)
    schedule.every().day.at("15:05").do(job_stop_trading)
    schedule.every().day.at("16:10").do(job_stop_alert_monitor)
    
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
        if current_trading_process and current_trading_process.poll() is None:
            logger.info("正在清理附带的交易进程...")
            current_trading_process.terminate()
        if current_alert_process and current_alert_process.poll() is None:
            logger.info("正在清理附带的监控进程...")
            current_alert_process.terminate()
        logger.info("调度器已退出。")

if __name__ == "__main__":
    start_scheduler()

