"""
统一行情数据服务 - 批量获取 ETF 实时行情、关联期货/指数、汇率数据
"""
import time
from datetime import datetime
from typing import Optional
from collections import deque

import pandas as pd
from loguru import logger

from config.settings import ETF_UNIVERSE, ACTIVE_ETFS, FUTURES_MOMENTUM_WINDOW
from strategy.signal import MarketSnapshot
from data.data_cache import DataCache
from data.iopv_calculator import IOPVCalculator


class MarketDataService:
    """
    统一行情数据服务。

    通过腾讯/新浪行情 HTTPS API 获取 ETF 实时行情，
    通过新浪/腾讯获取关联期货/指数价格和汇率。
    全部 HTTPS 直连，VPN 环境下可用。
    """

    def __init__(self):
        self._cache = DataCache()
        self._iopv_calc = IOPVCalculator()
        # 期货价格历史（用于计算动量）: {futures_symbol: deque of (timestamp, price)}
        self._futures_history: dict[str, deque] = {}
        # 创建不受系统代理影响的 HTTP 会话
        self._http = self._create_direct_session()

    @staticmethod
    def _create_direct_session():
        """创建绕过系统代理的 requests.Session"""
        import requests as _req
        s = _req.Session()
        s.trust_env = False  # 关键：不读取系统代理和环境变量代理
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        })
        return s

    # ------------------------------------------------------------------
    #  公开接口
    # ------------------------------------------------------------------

    def get_all_snapshots(self, etf_codes: Optional[list[str]] = None) -> dict[str, MarketSnapshot]:
        """
        批量获取所有活跃标的的行情快照。

        Args:
            etf_codes: 要获取的 ETF 代码列表，None 则获取所有活跃标的

        Returns:
            {etf_code: MarketSnapshot} 字典
        """
        codes = etf_codes or ACTIVE_ETFS
        now = datetime.now()
        snapshots = {}

        # 1) 批量获取 ETF 实时行情（一次 API 调用）
        etf_quotes = self._fetch_etf_quotes(codes)

        # 2) 获取汇率数据
        fx_rates = self._fetch_exchange_rates()

        # 3) 对每个标的组装 snapshot
        for code in codes:
            if code not in ETF_UNIVERSE:
                logger.warning(f"未知标的: {code}，跳过")
                continue

            config = ETF_UNIVERSE[code]
            etf_data = etf_quotes.get(code, {})

            # 获取关联期货/指数价格
            futures_symbol = config["ref_futures"]
            futures_price = self._fetch_futures_price(futures_symbol)

            # 记录期货价格历史
            self._record_futures_price(futures_symbol, futures_price)

            # 计算期货动量
            momentum = self._calc_futures_momentum(futures_symbol)

            # 获取汇率
            currency = config["currency"]
            fx_rate = fx_rates.get(currency, 1.0)

            # 获取 IOPV
            raw_iopv = float(etf_data.get("iopv", 0) or 0)
            iopv = self._iopv_calc.get_iopv(
                etf_code=code,
                akshare_iopv=raw_iopv,
                ref_index_price=futures_price,
                exchange_rate=fx_rate,
            )

            # 组装 snapshot
            etf_price = float(etf_data.get("price", 0) or 0)
            premium_rate = 0.0
            if iopv > 0 and etf_price > 0:
                premium_rate = (etf_price - iopv) / iopv

            snapshot = MarketSnapshot(
                etf_code=code,
                etf_name=config["name"],
                timestamp=now,
                etf_price=etf_price,
                etf_open=float(etf_data.get("open", 0) or 0),
                etf_high=float(etf_data.get("high", 0) or 0),
                etf_low=float(etf_data.get("low", 0) or 0),
                etf_volume=float(etf_data.get("volume", 0) or 0),
                etf_amount=float(etf_data.get("amount", 0) or 0),
                iopv=iopv,
                futures_price=futures_price,
                futures_change_pct=float(etf_data.get("futures_chg_pct", 0) or 0),
                exchange_rate=fx_rate,
                premium_rate=premium_rate,
                futures_momentum=momentum,
            )
            snapshots[code] = snapshot

        return snapshots

    # ------------------------------------------------------------------
    #  ETF 实时行情（腾讯/新浪多源）
    # ------------------------------------------------------------------

    def _fetch_etf_quotes(self, etf_codes: list[str] = None) -> dict[str, dict]:
        """
        批量获取 ETF 实时行情。
        支持多级回退和重试。

        主数据源: 腾讯行情 (qt.gtimg.cn)
        备用数据源: 新浪行情 (hq.sinajs.cn)
        """
        target_codes = etf_codes or ACTIVE_ETFS
        cache_key = f"etf_quotes_{','.join(sorted(target_codes))}"
        cached = self._cache.get(cache_key, ttl=3.0)
        if cached is not None:
            return cached

        # 尝试重试逻辑 (1次重试)
        for attempt in range(2):
            result = self._fetch_etf_quotes_tencent(target_codes)
            if not result:
                if attempt == 0:
                    logger.warning("腾讯行情获取失败，重试中...")
                    time.sleep(0.5)
                    continue
                
                logger.warning("腾讯行情获取失败，尝试新浪行情...")
                result = self._fetch_etf_quotes_sina(target_codes)

            if result:
                self._cache.set(cache_key, result)
                return result
            
            if attempt == 0:
                time.sleep(0.5)

        logger.error(f"所有 ETF 行情数据源均不可用 (标的: {target_codes})")
        return {}

    def _fetch_etf_quotes_tencent(self, etf_codes: list[str]) -> dict[str, dict]:
        """通过腾讯行情 API 获取 ETF 实时数据"""
        try:
            # 构建代码列表: sz159941,sh513180,...
            codes = []
            for code in etf_codes:
                if code not in ETF_UNIVERSE:
                    continue
                exchange = ETF_UNIVERSE[code].get("exchange", "SH").lower()
                codes.append(f"{exchange}{code}")

            if not codes:
                return {}

            url = f"https://qt.gtimg.cn/q={','.join(codes)}"
            resp = self._http.get(url, timeout=10)
            resp.encoding = "gbk"
            text = resp.text

            result = {}
            for line in text.strip().split("\n"):
                line = line.strip().rstrip(";")
                if "=" not in line:
                    continue
                # v_sz159941="51~纳指ETF~159941~1.341~1.350~..."
                var_name, _, raw = line.partition("=")
                raw = raw.strip('"')
                parts = raw.split("~")
                if len(parts) < 40:
                    continue

                code = parts[2]
                if code not in ETF_UNIVERSE:
                    continue

                try:
                    # 腾讯字段 [78] = IOPV实时估值, [81] = 单位净值
                    iopv_val = 0.0
                    if len(parts) > 78 and parts[78]:
                        iopv_val = float(parts[78])

                    result[code] = {
                        "price": float(parts[3] or 0),     # 最新价
                        "open": float(parts[5] or 0),      # 开盘价
                        "high": float(parts[33] or parts[3] or 0),  # 最高价
                        "low": float(parts[34] or parts[3] or 0),   # 最低价
                        "volume": float(parts[6] or 0),    # 成交量(手)
                        "amount": float(parts[37] or 0) * 10000 if parts[37] else 0,  # 成交额
                        "iopv": iopv_val,                   # IOPV 实时估值
                    }
                except (ValueError, IndexError):
                    logger.debug(f"[{code}] 腾讯行情解析失败")
                    continue

            return result

            return result

        except Exception as e:
            logger.warning(f"腾讯行情请求异常: {e}")
            return {}

    def _fetch_etf_quotes_sina(self, etf_codes: list[str]) -> dict[str, dict]:
        """通过新浪行情 API 获取 ETF 实时数据（备用）"""
        try:
            # 构建代码列表: sz159941,sh513180,...
            codes = []
            for code in etf_codes:
                if code not in ETF_UNIVERSE:
                    continue
                exchange = ETF_UNIVERSE[code].get("exchange", "SH").lower()
                codes.append(f"{exchange}{code}")

            if not codes:
                return {}

            url = f"https://hq.sinajs.cn/list={','.join(codes)}"
            self._http.headers["Referer"] = "https://finance.sina.com.cn"
            resp = self._http.get(url, timeout=10)
            resp.encoding = "gbk"
            text = resp.text

            result = {}
            for line in text.strip().split("\n"):
                line = line.strip().rstrip(";")
                if "=" not in line:
                    continue
                # var hq_str_sz159941="纳指ETF,1.341,1.350,1.341,1.345,1.340,..."
                var_name, _, raw = line.partition("=")
                raw = raw.strip('"')
                parts = raw.split(",")
                if len(parts) < 10:
                    continue

                # 从变量名提取代码: hq_str_sz159941 -> 159941
                code = var_name.strip().replace("var hq_str_", "")[-6:]
                if code not in ETF_UNIVERSE:
                    continue

                try:
                    result[code] = {
                        "price": float(parts[3] or 0),     # 当前价
                        "open": float(parts[1] or 0),      # 开盘价
                        "high": float(parts[4] or 0),      # 最高价
                        "low": float(parts[5] or 0),       # 最低价
                        "volume": float(parts[8] or 0),    # 成交量(股)
                        "amount": float(parts[9] or 0),    # 成交额
                        "iopv": 0,  # 新浪接口无 IOPV
                    }
                except (ValueError, IndexError):
                    logger.debug(f"[{code}] 新浪行情解析失败")
                    continue

            return result

            return result

        except Exception as e:
            logger.warning(f"新浪行情请求异常: {e}")
            return {}

    # ------------------------------------------------------------------
    #  关联期货/指数行情（新浪/腾讯 HTTPS，VPN 兼容）
    # ------------------------------------------------------------------

    # 内部符号 → (数据源, API代码) 映射
    _FUTURES_CODE_MAP = {
        # 美股期货 → Sina hf_ 格式
        "NQ=F": ("sina_futures", "hf_NQ"),     # 纳指期货
        "ES=F": ("sina_futures", "hf_ES"),     # 标普期货
        "YM=F": ("sina_futures", "hf_YM"),     # 道指期货
        "NKD=F": ("sina_index", "int_nikkei"), # 日经（无期货，用指数）
        # 港股指数 → Tencent hk 格式
        "HSI": ("tencent_hk", "hkHSI"),        # 恒生指数
        "HTI": ("tencent_hk", "hkHSTECH"),     # 恒生科技指数
        # 全球指数 → Sina int_ 格式
        "SOX": ("sina_index", "int_nasdaq"),    # 费城半导体（无直接源，用纳斯达克代替）
    }

    def _fetch_futures_price(self, symbol: str) -> float:
        """
        获取关联期货/指数的最新价格。
        使用新浪/腾讯 HTTPS 数据源，VPN 环境下全部可用。
        """
        cached = self._cache.get(f"futures_{symbol}", ttl=5.0)
        if cached is not None:
            return cached

        mapping = self._FUTURES_CODE_MAP.get(symbol)
        if mapping is None:
            logger.warning(f"[{symbol}] 未配置数据源映射")
            return 0.0

        source_type, api_code = mapping

        if source_type == "sina_futures":
            price = self._fetch_sina_futures(api_code, symbol)
        elif source_type == "tencent_hk":
            price = self._fetch_tencent_hk_index(api_code, symbol)
        elif source_type == "sina_index":
            price = self._fetch_sina_global_index(api_code, symbol)
        else:
            price = 0.0

        if price > 0:
            self._cache.set(f"futures_{symbol}", price)

        return price

    def _fetch_sina_futures(self, api_code: str, symbol: str) -> float:
        """通过新浪行情获取外盘期货价格 (hq.sinajs.cn/list=hf_XX)"""
        try:
            url = f"https://hq.sinajs.cn/list={api_code}"
            self._http.headers["Referer"] = "https://finance.sina.com.cn"
            resp = self._http.get(url, timeout=8)
            resp.encoding = "gbk"
            text = resp.text.strip()

            # 格式: var hq_str_hf_NQ="24840.725,,24832.250,...,纳斯达克指数期货,0";
            if "=" not in text:
                return 0.0
            _, _, raw = text.partition("=")
            raw = raw.strip('";')
            parts = raw.split(",")
            if len(parts) < 1 or not parts[0]:
                return 0.0

            price = float(parts[0])
            if price > 0:
                logger.debug(f"[{symbol}] 新浪期货 {api_code} = {price:.2f}")
            return price

        except Exception as e:
            logger.debug(f"新浪期货 {symbol} 获取失败: {e}")
            return 0.0

    def _fetch_tencent_hk_index(self, api_code: str, symbol: str) -> float:
        """通过腾讯行情获取港股指数价格 (qt.gtimg.cn/q=hkHSI)"""
        try:
            url = f"https://qt.gtimg.cn/q={api_code}"
            resp = self._http.get(url, timeout=8)
            resp.encoding = "gbk"
            text = resp.text.strip().rstrip(";")

            if "=" not in text:
                return 0.0
            _, _, raw = text.partition("=")
            raw = raw.strip('"')
            parts = raw.split("~")
            if len(parts) < 4:
                return 0.0

            price = float(parts[3] or 0)
            if price > 0:
                logger.debug(f"[{symbol}] 腾讯港股指数 {api_code} = {price:.2f}")
            return price

        except Exception as e:
            logger.debug(f"腾讯港股指数 {symbol} 获取失败: {e}")
            return 0.0

    def _fetch_sina_global_index(self, api_code: str, symbol: str) -> float:
        """通过新浪行情获取全球指数价格 (hq.sinajs.cn/list=int_xxx)"""
        try:
            url = f"https://hq.sinajs.cn/list={api_code}"
            self._http.headers["Referer"] = "https://finance.sina.com.cn"
            resp = self._http.get(url, timeout=8)
            resp.encoding = "gbk"
            text = resp.text.strip()

            # 格式: var hq_str_int_nikkei="日经指数,44946.64,-408.35,-0.90";
            if "=" not in text:
                return 0.0
            _, _, raw = text.partition("=")
            raw = raw.strip('";')
            parts = raw.split(",")
            if len(parts) < 2 or not parts[1]:
                return 0.0

            price = float(parts[1])
            if price > 0:
                logger.debug(f"[{symbol}] 新浪全球指数 {api_code} = {price:.2f}")
            return price

        except Exception as e:
            logger.debug(f"新浪全球指数 {symbol} 获取失败: {e}")
            return 0.0

    # ------------------------------------------------------------------
    #  汇率数据（新浪 HTTPS）
    # ------------------------------------------------------------------

    def _fetch_exchange_rates(self) -> dict[str, float]:
        """
        通过新浪行情获取主要币种兑人民币汇率。

        Returns:
            {currency: rate} 如 {"USD": 7.25, "HKD": 0.93, "JPY": 0.048}
        """
        cached = self._cache.get("fx_rates", ttl=60.0)  # 汇率 1 分钟缓存
        if cached is not None:
            return cached

        rates = {"CNY": 1.0}

        try:
            # 新浪外汇代码: fx_susdcny, fx_shkcny, fx_sjpycny
            url = "https://hq.sinajs.cn/list=fx_susdcny,fx_shkcny,fx_sjpycny"
            self._http.headers["Referer"] = "https://finance.sina.com.cn"
            resp = self._http.get(url, timeout=8)
            resp.encoding = "gbk"
            text = resp.text

            # 解析每行: var hq_str_fx_susdcny="10:16:27,6.8689,...,在岸人民币,...";
            for line in text.strip().split("\n"):
                line = line.strip().rstrip(";")
                if "=" not in line:
                    continue
                var_name, _, raw = line.partition("=")
                raw = raw.strip('"')
                parts = raw.split(",")
                if len(parts) < 2:
                    continue

                rate_val = float(parts[1] or 0)
                if rate_val <= 0:
                    continue

                if "usdcny" in var_name:
                    rates["USD"] = rate_val
                elif "hkcny" in var_name:
                    rates["HKD"] = rate_val
                elif "jpycny" in var_name:
                    # 新浪 JPY/CNY 报价是 100JPY/CNY
                    rates["JPY"] = rate_val / 100 if rate_val > 1 else rate_val

        except Exception as e:
            logger.warning(f"获取汇率失败，使用默认值: {e}")
            rates.setdefault("USD", 7.25)
            rates.setdefault("HKD", 0.93)
            rates.setdefault("JPY", 0.048)

        self._cache.set("fx_rates", rates)
        logger.debug(f"汇率: {rates}")
        return rates

    # ------------------------------------------------------------------
    #  期货动量计算
    # ------------------------------------------------------------------

    def _record_futures_price(self, symbol: str, price: float) -> None:
        """记录期货价格到历史队列"""
        if price <= 0:
            return
        if symbol not in self._futures_history:
            # 保留最近 60 个数据点（约 5 分钟 @ 5秒间隔）
            self._futures_history[symbol] = deque(maxlen=60)
        self._futures_history[symbol].append((time.time(), price))

    def _calc_futures_momentum(self, symbol: str) -> float:
        """
        计算期货动量（最近 N 分钟的价格变化率）。

        Returns:
            正值表示上涨动量，负值表示下跌动量
        """
        history = self._futures_history.get(symbol)
        if not history or len(history) < 2:
            return 0.0

        now = time.time()
        window_seconds = FUTURES_MOMENTUM_WINDOW * 60  # 分钟转秒

        # 找到窗口开始的价格
        oldest_price = None
        for ts, price in history:
            if now - ts <= window_seconds:
                oldest_price = price
                break

        if oldest_price is None or oldest_price == 0:
            return 0.0

        latest_price = history[-1][1]
        momentum = (latest_price - oldest_price) / oldest_price
        return momentum
