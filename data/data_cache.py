"""
数据缓存层 - 减少对外部 API 的重复调用
"""
import time
from typing import Any, Optional
from loguru import logger


class DataCache:
    """简单的内存缓存，带 TTL（生存时间）"""

    def __init__(self):
        self._cache: dict[str, dict] = {}

    def get(self, key: str, ttl: float = 5.0) -> Optional[Any]:
        """
        获取缓存数据。

        Args:
            key: 缓存键
            ttl: 数据有效期（秒），超过后返回 None

        Returns:
            缓存的数据，如果过期或不存在则返回 None
        """
        entry = self._cache.get(key)
        if entry is None:
            return None

        if time.time() - entry["timestamp"] > ttl:
            logger.debug(f"缓存过期: {key}")
            del self._cache[key]
            return None

        return entry["data"]

    def set(self, key: str, data: Any) -> None:
        """设置缓存数据"""
        self._cache[key] = {
            "data": data,
            "timestamp": time.time(),
        }

    def clear(self) -> None:
        """清空所有缓存"""
        self._cache.clear()

    def invalidate(self, key: str) -> None:
        """删除指定缓存"""
        self._cache.pop(key, None)
