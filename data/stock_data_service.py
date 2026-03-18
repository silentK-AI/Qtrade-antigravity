"""
通用股票/ETF/港股行情数据服务

与 MarketDataService（仅服务 ETF T+0）独立并行，
为个股技术指标监控提供实时行情和历史 K 线数据。

数据源:
- 实时行情: 腾讯行情 (qt.gtimg.cn) / 新浪行情 (hq.sinajs.cn)
- 历史K线: akshare (stock_zh_a_hist / fund_etf_hist_em / stock_hk_hist)
- 黄金价格: 新浪行情 (hf_GC)
- 市场情绪: akshare (大盘涨跌统计)
"""
import time as _time
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field

import pandas as pd
import numpy as np
import requests as _req
from loguru import logger

from config.stock_settings import STOCK_ALERT_SYMBOLS, ALERT_HISTORY_DAYS
from data.data_cache import DataCache


@dataclass
class RealtimeQuote:
    """实时行情快照"""
    symbol: str
    name: str
    price: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    prev_close: float = 0.0
    volume: float = 0.0         # 成交量（股）
    amount: float = 0.0         # 成交额（元）
    change_pct: float = 0.0     # 涨跌幅 (%)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def is_valid(self) -> bool:
        return self.price > 0


@dataclass
class MarketSentiment:
    """市场情绪数据"""
    up_count: int = 0           # 上涨家数
    down_count: int = 0         # 下跌家数
    flat_count: int = 0         # 平盘家数
    limit_up: int = 0           # 涨停家数
    limit_down: int = 0         # 跌停家数
    north_flow: float = 0.0     # 北向资金净流入（亿元）
    gold_price: float = 0.0     # 黄金现货价格 (USD)
    gold_change_pct: float = 0.0  # 黄金涨跌幅 (%)
    # 恐慌/情绪指数
    vix: float = 0.0            # CBOE VIX 恐慌指数（<30常态, >30紧张, >40极端恐慌）
    vix_change_pct: float = 0.0 # VIX 涨跌幅 (%)
    vxn: float = 0.0            # 纳斯达克 VXN 波动率指数
    vxn_change_pct: float = 0.0 # VXN 涨跌幅 (%)
    ovx: float = 0.0            # 原油 ETF 波动率指数 OVX
    ovx_change_pct: float = 0.0 # OVX 涨跌幅 (%)
    fear_greed: int = -1        # 韭圈儿恐贪指数（0-100, -1=未获取）
    fear_greed_label: str = ""  # 恐贪指数标签（极度恐慌/恐慌/中性/贪婪/极度贪婪）
    sh_change_pct: float = 0.0  # 上证指数涨跌幅 (%)
    sz_change_pct: float = 0.0  # 深证成指涨跌幅 (%)
    timestamp: datetime = field(default_factory=datetime.now)


class StockDataService:
    """
    通用股票行情数据服务。

    提供:
    - 批量实时行情获取（A 股 / ETF / 港股）
    - 历史日 K 线数据拉取（用于技术指标计算）
    - 黄金价格和市场情绪数据
    """

    def __init__(self):
        self._cache = DataCache()
        self._http = self._create_direct_session()

    @staticmethod
    def _create_direct_session():
        """创建绕过系统代理的 requests.Session（用于腾讯/新浪行情等白名单域名）"""
        s = _req.Session()
        s.trust_env = False
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        })
        return s

    @staticmethod
    def _create_proxy_session():
        """创建走系统代理的 requests.Session（用于需要代理的外部域名）"""
        s = _req.Session()
        s.trust_env = True
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        })
        return s

    # ------------------------------------------------------------------
    #  实时行情
    # ------------------------------------------------------------------

    def fetch_realtime_quotes(
        self, symbols: Optional[list[str]] = None
    ) -> dict[str, RealtimeQuote]:
        """
        批量获取实时行情。

        自动根据标的类型（A 股/ETF/港股）分流到对应 API。
        """
        targets = symbols or list(STOCK_ALERT_SYMBOLS.keys())

        # 按类型分组
        a_share_codes = []
        hk_codes = []

        for sym in targets:
            cfg = STOCK_ALERT_SYMBOLS.get(sym, {})
            if cfg.get("type") == "hk_stock":
                hk_codes.append(sym)
            else:
                a_share_codes.append(sym)

        result = {}

        # A 股 / ETF
        if a_share_codes:
            result.update(self._fetch_a_share_quotes(a_share_codes))

        # 港股
        if hk_codes:
            result.update(self._fetch_hk_quotes(hk_codes))

        return result

    def _fetch_a_share_quotes(self, codes: list[str]) -> dict[str, RealtimeQuote]:
        """通过腾讯行情 API 获取 A 股/ETF 实时数据"""
        cache_key = f"stock_quotes_{'_'.join(sorted(codes))}"
        cached = self._cache.get(cache_key, ttl=5.0)
        if cached is not None:
            return cached

        try:
            # 构建代码列表
            tencent_codes = []
            for code in codes:
                cfg = STOCK_ALERT_SYMBOLS.get(code, {})
                exchange = cfg.get("exchange", "SZ").lower()
                tencent_codes.append(f"{exchange}{code}")

            if not tencent_codes:
                return {}

            url = f"https://qt.gtimg.cn/q={','.join(tencent_codes)}"
            resp = self._http.get(url, timeout=10)
            resp.encoding = "gbk"
            text = resp.text

            result = {}
            for line in text.strip().split("\n"):
                line = line.strip().rstrip(";")
                if "=" not in line:
                    continue
                _, _, raw = line.partition("=")
                raw = raw.strip('"')
                parts = raw.split("~")
                if len(parts) < 40:
                    continue

                code = parts[2]
                if code not in STOCK_ALERT_SYMBOLS:
                    continue

                try:
                    price = float(parts[3] or 0)
                    prev_close = float(parts[4] or 0)
                    change_pct = 0.0
                    if prev_close > 0 and price > 0:
                        change_pct = (price - prev_close) / prev_close * 100

                    result[code] = RealtimeQuote(
                        symbol=code,
                        name=STOCK_ALERT_SYMBOLS[code]["name"],
                        price=price,
                        open=float(parts[5] or 0),
                        high=float(parts[33] or parts[3] or 0),
                        low=float(parts[34] or parts[3] or 0),
                        prev_close=prev_close,
                        volume=float(parts[6] or 0) * 100,  # 腾讯 API 返回手，转为股
                        amount=float(parts[37] or 0) * 10000 if parts[37] else 0,
                        change_pct=change_pct,
                    )
                except (ValueError, IndexError):
                    logger.debug(f"[{code}] 腾讯行情解析失败")
                    continue

            self._cache.set(cache_key, result)
            return result

        except Exception as e:
            logger.warning(f"A 股行情请求异常: {e}")
            return {}

    def _fetch_hk_quotes(self, codes: list[str]) -> dict[str, RealtimeQuote]:
        """通过腾讯行情 API 获取港股实时数据"""
        try:
            tencent_codes = []
            for code in codes:
                # HK0700 -> r_hk00700
                num = code.replace("HK", "").zfill(5)
                tencent_codes.append(f"r_hk{num}")

            url = f"https://qt.gtimg.cn/q={','.join(tencent_codes)}"
            resp = self._http.get(url, timeout=10)
            resp.encoding = "gbk"
            text = resp.text

            result = {}
            for line in text.strip().split("\n"):
                line = line.strip().rstrip(";")
                if "=" not in line:
                    continue
                _, _, raw = line.partition("=")
                raw = raw.strip('"')
                parts = raw.split("~")
                if len(parts) < 10:
                    continue

                try:
                    # 从变量名解析代码
                    price = float(parts[3] or 0)
                    prev_close = float(parts[4] or 0)
                    change_pct = 0.0
                    if prev_close > 0 and price > 0:
                        change_pct = (price - prev_close) / prev_close * 100

                    # 找到原始代码
                    for code in codes:
                        num = code.replace("HK", "").zfill(5)
                        if num in line:
                            cfg = STOCK_ALERT_SYMBOLS.get(code, {})
                            result[code] = RealtimeQuote(
                                symbol=code,
                                name=cfg.get("name", parts[1]),
                                price=price,
                                open=float(parts[5] or 0) if len(parts) > 5 else 0,
                                high=float(parts[33] or 0) if len(parts) > 33 else 0,
                                low=float(parts[34] or 0) if len(parts) > 34 else 0,
                                prev_close=prev_close,
                                volume=float(parts[6] or 0) if len(parts) > 6 else 0,
                                amount=float(parts[37] or 0) if len(parts) > 37 and parts[37] else 0,  # 港股 API 返回绝对值
                                change_pct=change_pct,
                            )
                            break
                except (ValueError, IndexError):
                    continue

            return result

        except Exception as e:
            logger.warning(f"港股行情请求异常: {e}")
            return {}

    # ------------------------------------------------------------------
    #  历史 K 线数据（通过 akshare）
    # ------------------------------------------------------------------

    def fetch_history_klines(
        self, symbol: str, days: int = ALERT_HISTORY_DAYS
    ) -> Optional[pd.DataFrame]:
        """
        获取指定标的的日 K 线历史数据。

        数据源策略:
        - A 股/ETF: 新浪 K 线 API（直连，绕过代理，稳定可靠）
        - 港股: akshare（stock_hk_hist，akshare 港股 API 走不同后端）

        Returns:
            DataFrame with columns: [date, open, high, low, close, volume, amount]
            按日期升序排列。None 表示获取失败。
        """
        cfg = STOCK_ALERT_SYMBOLS.get(symbol, {})
        sym_type = cfg.get("type", "stock")

        try:
            if sym_type == "hk_stock":
                # 港股: 使用 akshare（走雅虎/腾讯后端，非东方财富）
                import akshare as ak
                end_date = datetime.now().strftime("%Y%m%d")
                start_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y%m%d")
                df = self._fetch_hk_history(ak, symbol, start_date, end_date)
            else:
                # A 股 / ETF: 使用新浪 K 线 API（直连）
                df = self._fetch_sina_klines(symbol, cfg, days)

            if df is None or df.empty:
                logger.warning(f"[{symbol}] 历史 K 线数据为空")
                return None

            # 统一列名
            df = self._normalize_kline_columns(df, sym_type)

            # 取最后 N 天
            df = df.tail(days).reset_index(drop=True)
            logger.debug(f"[{symbol}] 获取 {len(df)} 天历史 K 线")
            return df

        except Exception as e:
            logger.error(f"[{symbol}] 获取历史 K 线失败: {e}")
            return None

    def _fetch_sina_klines(
        self, symbol: str, cfg: dict, days: int = 60
    ) -> Optional[pd.DataFrame]:
        """
        通过新浪 K 线 API 获取 A 股/ETF 日 K 线。

        API: https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/
             CN_MarketData.getKLineData?symbol=sz000559&scale=240&datalen=60
        """
        try:
            exchange = cfg.get("exchange", "SZ").lower()
            sina_symbol = f"{exchange}{symbol}"

            url = (
                "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
                "CN_MarketData.getKLineData"
            )
            params = {
                "symbol": sina_symbol,
                "scale": "240",      # 日 K（240 分钟 = 一个交易日）
                "ma": "no",
                "datalen": str(days + 10),  # 多取几天，去重后再截取
            }

            self._http.headers["Referer"] = "https://finance.sina.com.cn"
            resp = self._http.get(url, params=params, timeout=15)

            if resp.status_code != 200:
                logger.warning(f"[{symbol}] 新浪 K 线请求失败: HTTP {resp.status_code}")
                return None

            import json
            data = json.loads(resp.text)

            if not data or not isinstance(data, list):
                logger.warning(f"[{symbol}] 新浪 K 线返回空数据")
                return None

            # 转换为 DataFrame
            df = pd.DataFrame(data)
            # 新浪返回的列: day, open, high, low, close, volume
            df = df.rename(columns={"day": "date"})

            logger.debug(f"[{symbol}] 新浪 K 线获取 {len(df)} 条")
            return df

        except Exception as e:
            logger.warning(f"[{symbol}] 新浪 K 线获取失败: {e}")
            return None

    @staticmethod
    def _retry_akshare(func, max_retries: int = 3, base_delay: float = 2.0, **kwargs):
        """带重试的 akshare 调用（处理 RemoteDisconnected 等网络错误）"""
        for attempt in range(max_retries):
            try:
                return func(**kwargs)
            except Exception as e:
                err_str = str(e)
                is_conn_err = any(kw in err_str for kw in [
                    "RemoteDisconnected", "ConnectionReset", "ConnectionAborted",
                    "Connection aborted", "Remote end closed", "ConnectionError",
                ])
                if is_conn_err and attempt < max_retries - 1:
                    delay = base_delay * (attempt + 1)
                    logger.debug(f"akshare 连接断开，{delay:.0f}s 后重试 ({attempt+1}/{max_retries})...")
                    _time.sleep(delay)
                    continue
                raise

    def _fetch_stock_history(self, ak, symbol: str, start: str, end: str) -> Optional[pd.DataFrame]:
        """获取 A 股历史 K 线（带重试）"""
        try:
            df = self._retry_akshare(
                ak.stock_zh_a_hist,
                symbol=symbol,
                period="daily",
                start_date=start,
                end_date=end,
                adjust="qfq",
            )
            return df
        except Exception as e:
            logger.warning(f"[{symbol}] akshare stock_zh_a_hist 失败: {e}")
            return None

    def _fetch_etf_history(self, ak, symbol: str, start: str, end: str) -> Optional[pd.DataFrame]:
        """获取 ETF 历史 K 线（带重试）"""
        try:
            df = self._retry_akshare(
                ak.fund_etf_hist_em,
                symbol=symbol,
                period="daily",
                start_date=start,
                end_date=end,
                adjust="qfq",
            )
            return df
        except Exception as e:
            logger.warning(f"[{symbol}] akshare fund_etf_hist_em 失败: {e}")
            return None

    def _fetch_hk_history(self, ak, symbol: str, start: str, end: str) -> Optional[pd.DataFrame]:
        """获取港股历史 K 线（带重试）"""
        try:
            num = symbol.replace("HK", "").zfill(5)
            df = self._retry_akshare(
                ak.stock_hk_hist,
                symbol=num,
                period="daily",
                start_date=start,
                end_date=end,
                adjust="qfq",
            )
            return df
        except Exception as e:
            logger.warning(f"[{symbol}] akshare stock_hk_hist 失败: {e}")
            return None

    @staticmethod
    def _normalize_kline_columns(df: pd.DataFrame, sym_type: str) -> pd.DataFrame:
        """统一列名为 [date, open, high, low, close, volume, amount]"""
        # akshare 常见列名映射
        column_map = {
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
        }

        df = df.rename(columns=column_map)

        # 确保必要列存在
        required = ["date", "open", "high", "low", "close", "volume"]
        existing = [c for c in required if c in df.columns]
        if len(existing) < 5:
            # 尝试英文列名（港股）
            pass

        # 转换类型
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "amount" in df.columns:
            df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        else:
            df["amount"] = 0.0

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)

        return df

    # ------------------------------------------------------------------
    #  黄金价格
    # ------------------------------------------------------------------

    def fetch_gold_price(self) -> tuple[float, float]:
        """
        获取黄金现货价格 (COMEX 黄金期货)。

        Returns:
            (price, change_pct)
        """
        cached = self._cache.get("gold_price", ttl=60.0)
        if cached is not None:
            return cached

        try:
            url = "https://hq.sinajs.cn/list=hf_GC"
            self._http.headers["Referer"] = "https://finance.sina.com.cn"
            resp = self._http.get(url, timeout=8)
            resp.encoding = "gbk"
            text = resp.text.strip()

            if "=" not in text:
                return 0.0, 0.0

            _, _, raw = text.partition("=")
            raw = raw.strip('";')
            parts = raw.split(",")

            if len(parts) < 3:
                return 0.0, 0.0

            price = float(parts[0] or 0)
            prev_close = float(parts[7] or 0) if len(parts) > 7 else 0
            change_pct = 0.0
            if prev_close > 0 and price > 0:
                change_pct = (price - prev_close) / prev_close * 100

            result = (price, change_pct)
            self._cache.set("gold_price", result)
            logger.debug(f"黄金价格: ${price:.2f} ({change_pct:+.2f}%)")
            return result

        except Exception as e:
            logger.warning(f"获取黄金价格失败: {e}")
            return 0.0, 0.0

    # ------------------------------------------------------------------
    #  市场情绪
    # ------------------------------------------------------------------

    def fetch_market_sentiment(self) -> MarketSentiment:
        """
        获取市场情绪数据（大盘涨跌家数、北向资金等）。
        """
        cached = self._cache.get("market_sentiment", ttl=60.0)
        if cached is not None:
            return cached

        sentiment = MarketSentiment()

        # 黄金价格
        gold_price, gold_chg = self.fetch_gold_price()
        sentiment.gold_price = gold_price
        sentiment.gold_change_pct = gold_chg

        # 涨跌统计（通过腾讯）
        try:
            self._fetch_updown_stats(sentiment)
        except Exception as e:
            logger.debug(f"获取涨跌统计失败: {e}")

        # 北向资金（通过 akshare，非实时可接受延迟）
        try:
            self._fetch_north_flow(sentiment)
        except Exception as e:
            logger.debug(f"获取北向资金失败: {e}")

        # 恐慌指数 VIX / VXN / OVX
        try:
            self._fetch_vix_indices(sentiment)
        except Exception as e:
            logger.debug(f"获取恐慌指数失败: {e}")

        # 韭圈儿恐贪指数
        try:
            self._fetch_fear_greed(sentiment)
        except Exception as e:
            logger.debug(f"获取韭圈儿恐贪指数失败: {e}")

        sentiment.timestamp = datetime.now()
        self._cache.set("market_sentiment", sentiment)
        return sentiment

    def _fetch_updown_stats(self, sentiment: MarketSentiment):
        """从腾讯接口获取大盘涨跌家数及上证/深证涨跌幅"""
        try:
            # 上证指数获取市场概况
            url = "https://qt.gtimg.cn/q=sh000001,sz399001"
            resp = self._http.get(url, timeout=8)
            resp.encoding = "gbk"
            text = resp.text
            
            for line in text.strip().split("\n"):
                line = line.strip().rstrip(";")
                if "=" not in line:
                    continue
                _, _, raw = line.partition("=")
                raw = raw.strip('"')
                parts = raw.split("~")
                if len(parts) >= 45:
                    try:
                        if "sh000001" in line or parts[2] == "000001":
                            # 腾讯格式: parts[41]=上涨家数 parts[42]=下跌家数
                            if len(parts) > 42:
                                sentiment.up_count = int(float(parts[41] or 0))
                                sentiment.down_count = int(float(parts[42] or 0))
                            # parts[32]=涨跌幅%
                            if len(parts) > 32 and parts[32]:
                                sentiment.sh_change_pct = round(float(parts[32]), 2)
                        elif "sz399001" in line or parts[2] == "399001":
                            if len(parts) > 32 and parts[32]:
                                sentiment.sz_change_pct = round(float(parts[32]), 2)
                    except (ValueError, IndexError):
                        pass
        except Exception as e:
            logger.debug(f"涨跌统计获取失败: {e}")

    def _fetch_north_flow(self, sentiment: MarketSentiment):
        """通过 akshare 获取北向资金"""
        try:
            import akshare as ak
            df = ak.stock_hsgt_fund_flow_summary_em()
            if df is not None and not df.empty:
                # 查找包含 "北上" 或 "沪股通+深股通" 的行
                for _, row in df.iterrows():
                    row_str = str(row.values)
                    if "北" in row_str or "沪深" in row_str:
                        for col in df.columns:
                            col_str = str(col)
                            if "净流入" in col_str or "净买" in col_str:
                                val = float(row[col])
                                sentiment.north_flow = val / 1e8 if abs(val) > 1e6 else val
                                return
        except Exception as e:
            logger.debug(f"北向资金获取失败（akshare）: {e}")

    def _fetch_vix_indices(self, sentiment: MarketSentiment):
        """
        获取 VIX / VXN / OVX 恐慌指数。
        数据源: CBOE 官方 CSV（任意时段可用，国内直连）
        """
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
        cboe_map = {
            "VIX": ("https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",  "vix",  "vix_change_pct",  4),
            "VXN": ("https://cdn.cboe.com/api/global/us_indices/daily_prices/VXN_History.csv",  "vxn",  "vxn_change_pct",  4),
            "OVX": ("https://cdn.cboe.com/api/global/us_indices/daily_prices/OVX_History.csv",  "ovx",  "ovx_change_pct",  1),
        }
        for name, (url, price_attr, chg_attr, close_idx) in cboe_map.items():
            try:
                r = self._http.get(url, timeout=15, headers={"User-Agent": ua})
                if r.status_code != 200:
                    logger.debug(f"[CBOE] {name} status={r.status_code}")
                    continue
                lines = r.text.strip().split("\n")
                # 取最后两行计算涨跌幅
                if len(lines) < 2:
                    continue
                def parse_close(line, idx):
                    parts = line.strip().split(",")
                    return float(parts[idx]) if len(parts) > idx else 0.0
                last_close = parse_close(lines[-1], close_idx)
                prev_close = parse_close(lines[-2], close_idx) if len(lines) >= 3 else 0.0
                if last_close <= 0:
                    continue
                chg_pct = (last_close - prev_close) / prev_close * 100 if prev_close > 0 else 0.0
                setattr(sentiment, price_attr, round(last_close, 2))
                setattr(sentiment, chg_attr, round(chg_pct, 2))
                logger.debug(f"[CBOE] {name}: {last_close:.2f} ({chg_pct:+.2f}%)")
            except Exception as e:
                logger.debug(f"[CBOE] {name} 失败: {e}")
        import re
        got = {"vix": False, "vxn": False, "ovx": False}

        # --- 源1: 新浪行情 fx_VIX/fx_VXN/fx_OVX ---
        sina_map = {
            "fx_VIX": ("vix", "vix_change_pct"),
            "fx_VXN": ("vxn", "vxn_change_pct"),
            "fx_OVX": ("ovx", "ovx_change_pct"),
        }
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
        try:
            for sina_code, (price_attr, chg_attr) in sina_map.items():
                url = f"https://hq.sinajs.cn/?list={sina_code}"
                for sess in [self._http, self._create_proxy_session()]:
                    try:
                        sess.headers.update({
                            "Referer": "https://finance.sina.com.cn",
                            "User-Agent": ua,
                        })
                        resp = sess.get(url, timeout=8)
                        resp.encoding = "gbk"
                        text = resp.text.strip()
                        match = re.search(r'"([^"]+)"', text)
                        if not match:
                            continue
                        fields = match.group(1).split(",")
                        if len(fields) < 2:
                            continue
                        price = float(fields[1])  # fields[1] 是当前价
                        if price <= 0:
                            continue
                        # 涨跌幅: fields[2] 或从 fields[4](前收) 计算
                        chg_pct = 0.0
                        try:
                            if len(fields) > 2 and fields[2]:
                                chg_pct = float(fields[2])
                        except ValueError:
                            pass
                        if chg_pct == 0.0:
                            try:
                                prev = float(fields[4]) if len(fields) > 4 and fields[4] else 0.0
                                if prev > 0:
                                    chg_pct = (price - prev) / prev * 100
                            except (ValueError, IndexError):
                                pass
                        setattr(sentiment, price_attr, round(price, 2))
                        setattr(sentiment, chg_attr, round(chg_pct, 2))
                        got[price_attr] = True
                        logger.debug(f"[新浪] {sina_code}: {price:.2f} ({chg_pct:+.2f}%)")
                        break  # 当前标的成功，跳出 session 循环
                    except Exception as e:
                        logger.debug(f"[新浪VIX] {sina_code} session 失败: {e}")
                        continue
        except Exception as e:
            logger.debug(f"新浪 VIX/VXN/OVX 失败: {e}")

        # --- 源2: akshare（仅 VIX 备用）---
        if not got.get("vix"):
            try:
                import akshare as ak
                for func_name in ["index_vix_weeklyfutures", "futures_vix_baidu", "index_option_50etf_qvix"]:
                    try:
                        fn = getattr(ak, func_name, None)
                        if not fn:
                            continue
                        df_vix = fn()
                        if df_vix is None or df_vix.empty:
                            continue
                        last = df_vix.iloc[-1]
                        price_col = [c for c in df_vix.columns if "收盘" in c or "close" in c.lower() or "vix" in c.lower()]
                        if price_col:
                            price = float(last[price_col[0]])
                            if price > 0:
                                sentiment.vix = round(price, 2)
                                got["vix"] = True
                                logger.debug(f"[akshare] VIX: {price:.2f}")
                                break
                    except Exception:
                        continue
            except Exception as e:
                logger.debug(f"akshare VIX 失败: {e}")

    def _fetch_fear_greed(self, sentiment: MarketSentiment):
        """
        获取恐贪指数（A股/全球）。
        数据源优先级:
          1. 韭圈儿 open API（先直连，失败再走代理）
          2. alternative.me Fear & Greed（走系统代理，无代理环境跳过）
          3. 基于大盘涨跌家数估算（兜底，始终可用）
        """
        direct_http = self._http
        proxy_http = self._create_proxy_session()

        # --- 源1: 韭圈儿（先直连，失败再走代理）---
        try:
            url = "https://open.jiucaishuo.com/api/v1/greedy_index/newest"
            headers = {
                "Referer": "https://www.jiucaishuo.com/",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Origin": "https://www.jiucaishuo.com",
            }
            for sess in [direct_http, proxy_http]:
                try:
                    sess.headers.update(headers)
                    resp = sess.get(url, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("code") == 0 and "data" in data:
                            d = data["data"]
                            idx = int(d.get("index", -1))
                            label = str(d.get("label") or d.get("name") or "")
                            if idx >= 0:
                                sentiment.fear_greed = idx
                                sentiment.fear_greed_label = label
                                logger.debug(f"[韭圈儿] 恐贪指数: {idx} ({label})")
                                return
                except Exception as e:
                    logger.debug(f"韭圈儿 session 尝试失败: {e}")
                    continue
        except Exception as e:
            logger.debug(f"韭圈儿恐贪指数失败: {e}")

        # --- 源2: alternative.me（走系统代理，无代理环境会失败，有兜底）---
        try:
            resp2 = proxy_http.get("https://api.alternative.me/fng/?limit=1", timeout=8)
            if resp2.status_code == 200:
                data2 = resp2.json()
                items = data2.get("data", [])
                if items:
                    idx = int(items[0].get("value", -1))
                    raw_label = str(items[0].get("value_classification", ""))
                    label_map = {
                        "Extreme Fear": "极度恐慌",
                        "Fear": "恐慌",
                        "Neutral": "中性",
                        "Greed": "贪婪",
                        "Extreme Greed": "极度贪婪",
                    }
                    label = label_map.get(raw_label, raw_label)
                    if idx >= 0:
                        sentiment.fear_greed = idx
                        sentiment.fear_greed_label = label + "(全球)"
                        logger.debug(f"[alternative.me] 恐贪指数: {idx} ({label})")
                        return
        except Exception as e:
            logger.debug(f"alternative.me 恐贪指数失败: {e}")

        # --- 源3: 基于大盘技术面估算（兜底，始终可用）---
        try:
            # 用上证指数 RSI + 涨跌家数 简单估算
            # 已知 sentiment.up_count / down_count
            total = sentiment.up_count + sentiment.down_count
            if total > 0:
                up_ratio = sentiment.up_count / total  # 0~1
                # 线性映射到 0-100：0%上涨=极度恐慌(0), 100%上涨=极度贪婪(100)
                idx = round(up_ratio * 100)
                if idx >= 60:
                    label = "贪婪(估算)"
                elif idx >= 45:
                    label = "中性(估算)"
                elif idx >= 30:
                    label = "恐慌(估算)"
                else:
                    label = "极度恐慌(估算)"
                sentiment.fear_greed = idx
                sentiment.fear_greed_label = label
                logger.debug(f"[估算] 恐贪指数: {idx} ({label})，涨家{sentiment.up_count}/跌家{sentiment.down_count}")
        except Exception as e:
            logger.debug(f"恐贪指数估算失败: {e}")
