"""
结构化日志配置 - 使用 loguru
"""
import os
import sys
from loguru import logger

from config.settings import LOG_DIR, LOG_LEVEL


def setup_logger() -> None:
    """
    配置日志系统。

    - 控制台输出带颜色
    - 文件日志按天轮转
    """
    # 移除默认 handler
    logger.remove()

    # 控制台输出
    logger.add(
        sys.stderr,
        level=LOG_LEVEL,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # 文件日志
    os.makedirs(LOG_DIR, exist_ok=True)
    logger.add(
        os.path.join(LOG_DIR, "trade_{time:YYYY-MM-DD}.log"),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="00:00",  # 每天午夜轮转
        retention="30 days",
        encoding="utf-8",
    )

    logger.info("日志系统初始化完成")
