"""
隔夜行情数据获取模块

在 A 股开盘前获取美股/港股/日股期货的隔夜交易数据，
为开盘策略提供方向性参考信号。

数据源：新浪行情 (hq.sinajs.cn) / 腾讯行情 (qt.gtimg.cn)
全部 HTTPS 直连，VPN 环境下可用。
"""
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

import requests as _req
from loguru import logger

from data.data_cache import DataCache
from config.etf_settings import ETF_UNIVERSE


@dataclass
class OvernightInfo:
    """隔夜行情信息"""
    symbol: str                       # 期货/指数代码
    prev_close: float = 0.0           # 前收盘价
    overnight_price: float = 0.0      # 隔夜最新价
    overnight_change_pct: float = 0.0 # 隔夜涨跌幅 %
    overnight_high: float = 0.0       # 隔夜最高
    overnight_low: float = 0.0        # 隔夜最低
    overnight_volume: float = 0.0     # 隔夜成交量
    gap_direction: str = "FLAT"       # 缺口方向: UP / DOWN / FLAT
    momentum_score: float = 0.0       # 动量评分 (-1 ~ +1)
    updated_at: Optional[datetime] = None
    source: str = ""

    @property
    def is_valid(self) -> bool:
        return self.overnight_price > 0 and self.prev_close > 0


class OvernightDataService:
    """
    隔夜行情数据服务。

    每日 A 股开盘前（09:00-09:30）获取关联期货/指数的隔夜走势，
    计算变动幅度和方向，为日内策略提供开盘参考。

    使用新浪/腾讯 HTTPS 数据源，VPN 环境下全部可用。
    """

    # ETF 代码 -> [(数据源类型, API代码)] 列表（按优先级排列）
    _OVERNIGHT_MAP = {
        "513180": [("tencent_hk", "hkHSTECH")],                       # 恒生科技
        "159920": [("tencent_hk", "hkHSI")],                           # 恒生指数
        "159941": [("sina_futures", "hf_NQ"), ("sina_index", "int_nasdaq")],  # 纳指
        "513500": [("sina_futures", "hf_ES"), ("sina_index", "int_sp500")],   # 标普
        "513400": [("sina_futures", "hf_YM"), ("sina_index", "int_dji")],     # 道指
        "513880": [("sina_index", "int_nikkei")],                      # 日经
        "513310": [("sina_index", "int_nasdaq")],                      # 半导体→纳斯达克
    }

    def __init__(self):
        self._cache = DataCache()
        self._daily_data: dict[str, OvernightInfo] = {}
        # 创建不受系统代理影响的 HTTP 会话
        self._http = _req.Session()
        self._http.trust_env = False
        self._http.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://finance.sina.com.cn",
        })

    def get_overnight_info(self, etf_code: str) -> Optional[OvernightInfo]:
        """
        获取某标的的隔夜行情信息。

        优先返回缓存数据（当日有效），否则实时获取。
        """
        cached = self._daily_data.get(etf_code)
        if cached and cached.updated_at and cached.updated_at.date() == datetime.now().date():
            return cached

        info = self._fetch_overnight(etf_code)
        if info and info.is_valid:
            self._daily_data[etf_code] = info
        return info

    def get_all_overnight_info(self) -> dict[str, OvernightInfo]:
        """批量获取所有标的的隔夜信息"""
        result = {}
        for code in ETF_UNIVERSE:
            info = self.get_overnight_info(code)
            if info:
                result[code] = info
        return result

    def reset_daily(self) -> None:
        """每日重置（新交易日开始时调用）"""
        self._daily_data.clear()
        logger.info("隔夜数据已重置")

    def _fetch_overnight(self, etf_code: str) -> Optional[OvernightInfo]:
        """获取隔夜数据（尝试多个数据源）"""
        entries = self._OVERNIGHT_MAP.get(etf_code, [])
        if not entries:
            return None

        for source_type, api_code in entries:
            if source_type == "sina_futures":
                info = self._fetch_sina_futures_overnight(api_code)
            elif source_type == "tencent_hk":
                info = self._fetch_tencent_hk_overnight(api_code)
            elif source_type == "sina_index":
                info = self._fetch_sina_index_overnight(api_code)
            else:
                continue

            if info and info.is_valid:
                logger.info(
                    f"[{etf_code}] 隔夜数据({api_code}): "
                    f"涨跌={info.overnight_change_pct:+.2f}% "
                    f"方向={info.gap_direction} "
                    f"评分={info.momentum_score:+.2f}"
                )
                return info

        logger.warning(f"[{etf_code}] 无法获取隔夜数据")
        return None

    def _fetch_sina_futures_overnight(self, api_code: str) -> Optional[OvernightInfo]:
        """通过新浪获取外盘期货隔夜数据"""
        try:
            url = f"https://hq.sinajs.cn/list={api_code}"
            resp = self._http.get(url, timeout=8)
            resp.encoding = "gbk"
            text = resp.text.strip()

            if "=" not in text:
                return None
            _, _, raw = text.partition("=")
            raw = raw.strip('";')
            parts = raw.split(",")
            # 格式: 最新价,,昨收盘价,昨结算价,最高,最低,时间,昨收,买价,...,名称,0
            if len(parts) < 8 or not parts[0]:
                return None

            latest = float(parts[0] or 0)
            prev_close = float(parts[7] or 0)
            high = float(parts[4] or 0)
            low = float(parts[5] or 0)

            if latest <= 0 or prev_close <= 0:
                return None

            return self._build_overnight_info(api_code, latest, prev_close, high, low, "sina")

        except Exception as e:
            logger.debug(f"新浪期货隔夜数据 {api_code} 获取失败: {e}")
            return None

    def _fetch_tencent_hk_overnight(self, api_code: str) -> Optional[OvernightInfo]:
        """通过腾讯获取港股指数隔夜数据"""
        try:
            url = f"https://qt.gtimg.cn/q={api_code}"
            resp = self._http.get(url, timeout=8)
            resp.encoding = "gbk"
            text = resp.text.strip().rstrip(";")

            if "=" not in text:
                return None
            _, _, raw = text.partition("=")
            raw = raw.strip('"')
            parts = raw.split("~")
            # 腾讯格式: 100~名称~代码~最新价~昨收~开盘~...~最高~最低~...
            if len(parts) < 35:
                return None

            latest = float(parts[3] or 0)
            prev_close = float(parts[4] or 0)
            high = float(parts[33] or parts[3] or 0)
            low = float(parts[34] or parts[3] or 0)

            if latest <= 0 or prev_close <= 0:
                return None

            return self._build_overnight_info(api_code, latest, prev_close, high, low, "tencent")

        except Exception as e:
            logger.debug(f"腾讯港股指数隔夜数据 {api_code} 获取失败: {e}")
            return None

    def _fetch_sina_index_overnight(self, api_code: str) -> Optional[OvernightInfo]:
        """通过新浪获取全球指数隔夜数据"""
        try:
            url = f"https://hq.sinajs.cn/list={api_code}"
            resp = self._http.get(url, timeout=8)
            resp.encoding = "gbk"
            text = resp.text.strip()

            if "=" not in text:
                return None
            _, _, raw = text.partition("=")
            raw = raw.strip('";')
            parts = raw.split(",")
            # 格式: 名称,最新价,涨跌点数,涨跌幅
            if len(parts) < 4 or not parts[1]:
                return None

            latest = float(parts[1] or 0)
            change_points = float(parts[2] or 0)
            prev_close = latest - change_points if latest > 0 else 0

            if latest <= 0 or prev_close <= 0:
                return None

            return self._build_overnight_info(api_code, latest, prev_close, 0, 0, "sina")

        except Exception as e:
            logger.debug(f"新浪全球指数隔夜数据 {api_code} 获取失败: {e}")
            return None

    @staticmethod
    def _build_overnight_info(
        symbol: str,
        latest: float,
        prev_close: float,
        high: float,
        low: float,
        source: str,
    ) -> OvernightInfo:
        """根据原始数据构建 OvernightInfo"""
        change_pct = (latest - prev_close) / prev_close * 100

        if change_pct > 0.3:
            gap = "UP"
        elif change_pct < -0.3:
            gap = "DOWN"
        else:
            gap = "FLAT"

        raw_score = change_pct / 2.0
        momentum_score = max(-1.0, min(1.0, raw_score))

        return OvernightInfo(
            symbol=symbol,
            prev_close=prev_close,
            overnight_price=latest,
            overnight_change_pct=change_pct,
            overnight_high=high,
            overnight_low=low,
            overnight_volume=0,
            gap_direction=gap,
            momentum_score=momentum_score,
            updated_at=datetime.now(),
            source=source,
        )
