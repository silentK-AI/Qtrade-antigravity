"""
开源免费行情数据源接口封装
基于腾讯行情 (qt.gtimg.cn) 与 东方财富 (push2.eastmoney.com) 公开 REST 接口
无需注册、无需 Token、开箱即用，支持主板批量实时行情与盘口抓取
"""

import time
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from models.stock_item import StockQuote
from utils.filters import StockFilter
from utils.calendar import TradeCalendar, get_beijing_now
from utils.logger import get_logger

logger = get_logger("open_data_provider")


def _safe_float(val: Any, default: float = 0.0) -> float:
    """安全将接口返回值转换为 float，兼容东财 '-' / None / 空字符串"""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s or s == "-" or s.lower() == "nan":
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


class OpenDataProvider:
    """开源实时行情获取器"""

    def __init__(self, timeout: int = 5):
        self.timeout = timeout
        self.filter = StockFilter()
        self._prev_zt_cache: Dict[str, Dict[str, int]] = {}

    def _get_url_content(self, url: str, encoding: str = "utf-8", max_retries: int = 3) -> str:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://finance.qq.com"
            }
        )
        last_err = None
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    return response.read().decode(encoding, errors="ignore")
            except Exception as e:
                last_err = e
                if attempt < max_retries - 1:
                    time.sleep(0.3 * (2 ** attempt))
        if last_err:
            raise last_err
        return ""

    def fetch_realtime_quotes(self, codes: List[str]) -> List[StockQuote]:
        """
        批量通过腾讯实时接口抓取股票最新快照
        codes: 形如 ['600519', '000001']
        """
        if not codes:
            return []

        # 转换为带市场前缀的代码 (sh600519, sz000001)
        formatted_codes = []
        for code in codes:
            c = str(code).strip()
            if c.startswith("6"):
                formatted_codes.append(f"sh{c}")
            elif c.startswith("0"):
                formatted_codes.append(f"sz{c}")

        if not formatted_codes:
            return []

        # 每次最多批量请求 60 只标的
        batch_size = 60
        quotes = []

        for i in range(0, len(formatted_codes), batch_size):
            chunk = formatted_codes[i:i + batch_size]
            url = f"https://qt.gtimg.cn/q={','.join(chunk)}"
            try:
                content = self._get_url_content(url, encoding="gbk")
                quotes.extend(self._parse_tencent_response(content))
            except Exception as e:
                # 网络受阻或异常时跳过当前批次
                continue

        return quotes

    def _parse_tencent_response(self, text: str) -> List[StockQuote]:
        """解析腾讯行情格式"""
        results = []
        lines = text.strip().split(";")
        for line in lines:
            line = line.strip()
            if not line or '="' not in line:
                continue
            
            raw_data = line.split('="')[1].rstrip('"')
            parts = raw_data.split("~")
            if len(parts) < 45:
                continue

            try:
                name = parts[1]
                code = parts[2]
                curr_price = _safe_float(parts[3])
                pre_close = _safe_float(parts[4])
                open_price = _safe_float(parts[5])
                volume = _safe_float(parts[6]) * 100  # 手转股
                amount = _safe_float(parts[37]) * 10000 if len(parts) > 37 else 0.0 # 万元
                turnover_rate = _safe_float(parts[38]) if len(parts) > 38 else 0.0
                change_pct = _safe_float(parts[32]) if len(parts) > 32 and parts[32] else ((curr_price - pre_close) / pre_close * 100 if pre_close else 0.0)
                high = _safe_float(parts[33], curr_price) if len(parts) > 33 and parts[33] else curr_price
                low = _safe_float(parts[34], curr_price) if len(parts) > 34 and parts[34] else curr_price
                float_market_cap = _safe_float(parts[44]) if len(parts) > 44 else 0.0
                total_market_cap = _safe_float(parts[45]) if len(parts) > 45 else 0.0
                
                # 真实买一/卖一五档盘口深度 (手转股)
                buy1_price = _safe_float(parts[9]) if len(parts) > 9 else 0.0
                buy1_volume = _safe_float(parts[10]) * 100 if len(parts) > 10 else 0.0
                sell1_price = _safe_float(parts[19]) if len(parts) > 19 else 0.0
                sell1_volume = _safe_float(parts[20]) * 100 if len(parts) > 20 else 0.0

                market = "SH" if code.startswith("6") else "SZ"
                vwap = (amount / volume) if volume > 0 else curr_price

                # 判断主板涨停（主板10%）
                limit_up_price = round(pre_close * 1.10, 2)
                is_limit_up = (curr_price >= limit_up_price - 0.01) if (curr_price > 0 and pre_close > 0) else False

                quote = StockQuote(
                    code=code,
                    name=name,
                    market=market,
                    current_price=curr_price,
                    pre_close=pre_close,
                    open_price=open_price,
                    high_price=high,
                    low_price=low,
                    change_pct=change_pct,
                    volume=volume,
                    amount=amount,
                    turnover_rate=turnover_rate,
                    float_market_cap=float_market_cap,
                    total_market_cap=total_market_cap,
                    vwap=vwap,
                    is_limit_up=is_limit_up,
                    buy1_price=buy1_price,
                    buy1_volume=buy1_volume,
                    sell1_price=sell1_price,
                    sell1_volume=sell1_volume
                )
                results.append(quote)
            except (ValueError, IndexError):
                continue

        return results

    def fetch_main_board_top_active(self, page_size: int = 100) -> List[StockQuote]:
        """
        从公开榜单接口抓取主板当下最活跃/涨幅居前的股票池
        支持按东财每页100条上限自动分页抓取，并容错处理集合竞价阶段 '-' 空值
        """
        # 东财官方纯沪深主板榜单 (m:0+t:6 为深市主板; m:1+t:2 为沪市主板，精准排除创业板与科创板)
        # 增加 f62 字段获取真实实时主力资金净买入额 (元)
        quotes: List[StockQuote] = []
        seen_codes = set()
        max_pages = min(6, max(1, (page_size + 99) // 100))

        for pn in range(1, max_pages + 1):
            url = (
                "https://push2.eastmoney.com/api/qt/clist/get?"
                f"pn={pn}&pz=100&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
                "&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:1+t:2"
                "&fields=f12,f14,f2,f3,f4,f5,f6,f7,f8,f15,f16,f17,f18,f20,f21,f62"
            )
            try:
                content = self._get_url_content(url)
                data = json.loads(content)
                diff = (data.get("data") or {}).get("diff") or []
                if not diff:
                    break
                for item in diff:
                    try:
                        code = str(item.get("f12", "")).strip()
                        name = str(item.get("f14", "")).strip()
                        if not code or code in seen_codes:
                            continue
                        curr = _safe_float(item.get("f2"))
                        if curr <= 0:
                            continue
                        change_pct = _safe_float(item.get("f3"))
                        pre_close = _safe_float(item.get("f18"), curr)
                        volume = _safe_float(item.get("f5")) * 100
                        amount = _safe_float(item.get("f6"))
                        turnover = _safe_float(item.get("f8"))
                        high = _safe_float(item.get("f15"), curr)
                        low = _safe_float(item.get("f16"), curr)
                        open_p = _safe_float(item.get("f17"), curr)
                        total_cap = _safe_float(item.get("f20")) / 100000000
                        float_cap = _safe_float(item.get("f21")) / 100000000
                        net_inflow = _safe_float(item.get("f62"))

                        quote = StockQuote(
                            code=code,
                            name=name,
                            market="SH" if code.startswith("6") else "SZ",
                            current_price=curr,
                            pre_close=pre_close,
                            open_price=open_p,
                            high_price=high,
                            low_price=low,
                            change_pct=change_pct,
                            volume=volume,
                            amount=amount,
                            turnover_rate=turnover,
                            float_market_cap=float_cap,
                            total_market_cap=total_cap,
                            vwap=(amount / volume) if volume > 0 else curr,
                            is_limit_up=(change_pct >= 9.9),
                            net_large_inflow=net_inflow
                        )
                        if self.filter.filter_quote(quote):
                            seen_codes.add(code)
                            quotes.append(quote)
                    except Exception:
                        continue
                if len(diff) < 100 or len(quotes) >= page_size:
                    break
            except Exception as e:
                logger.warning(f"抓取主板榜单第 {pn} 页异常: {e}")
                break

        return quotes[:page_size]

    def fetch_prev_day_volumes(self, codes: List[str]) -> Dict[str, float]:
        """
        并发抓取股票前一交易日的真实全天成交量（股），用于 09:25 集合竞价真实爆量比计算
        """
        from concurrent.futures import ThreadPoolExecutor

        def _fetch_single(code: str) -> Tuple[str, float]:
            market = 0 if code.startswith(("0", "3")) else 1
            url = (
                f"https://push2his.eastmoney.com/api/qt/stock/kline/get?"
                f"secid={market}.{code}&fields1=f1&fields2=f51,f56&klt=101&fqt=0&end=20500101&lmt=2"
            )
            try:
                content = self._get_url_content(url)
                data = json.loads(content)
                klines = data.get("data", {}).get("klines", [])
                if len(klines) >= 2:
                    return code, float(klines[0].split(",")[1]) * 100.0
                elif len(klines) == 1:
                    return code, float(klines[0].split(",")[1]) * 100.0
            except Exception:
                pass
            return code, 0.0

        if not codes:
            return {}
        with ThreadPoolExecutor(max_workers=min(10, len(codes))) as executor:
            return dict(executor.map(_fetch_single, codes))

    def fetch_recent_stock_stats(self, codes: List[str]) -> Dict[str, Dict[str, float]]:
        """
        并发抓取股票最近几个交易日的真实日K数据，计算：
        - turnover_3d: 近3个交易日（含今日）累计真实换手率 (%)
        - gain_5d: 近5个交易日累计涨跌幅 (%)
        """
        from concurrent.futures import ThreadPoolExecutor

        def _fetch_single(code: str) -> Tuple[str, Dict[str, float]]:
            market = 0 if code.startswith(("0", "3")) else 1
            url = (
                f"https://push2his.eastmoney.com/api/qt/stock/kline/get?"
                f"secid={market}.{code}&fields1=f1&fields2=f51,f53,f57,f59,f61&klt=101&fqt=0&end=20500101&lmt=6"
            )
            try:
                content = self._get_url_content(url)
                data = json.loads(content)
                klines = data.get("data", {}).get("klines", [])
                if klines:
                    recent_3 = klines[-3:]
                    turnover_3d = round(sum(float(item.split(",")[4]) for item in recent_3), 2)
                    base_close = float(klines[0].split(",")[1])
                    last_close = float(klines[-1].split(",")[1])
                    gain_5d = round(((last_close - base_close) / base_close * 100.0) if base_close > 0 else 0.0, 2)
                    return code, {"turnover_3d": turnover_3d, "gain_5d": gain_5d}
            except Exception:
                pass
            return code, {"turnover_3d": 0.0, "gain_5d": 0.0}

        if not codes:
            return {}
        with ThreadPoolExecutor(max_workers=min(10, len(codes))) as executor:
            return dict(executor.map(_fetch_single, codes))

    def fetch_yesterday_limit_up_pool(self) -> List[Dict[str, Any]]:
        """
        抓取东方财富【昨日涨停板】(BK0815) 全部成分股在今日的实际表现
        严格按沪深主板过滤，提取：代码、名称、现价、涨跌幅、最高涨幅、最低跌幅、换手、成交额、连板数等
        """
        items: List[Dict[str, Any]] = []
        seen_codes = set()
        for pn in (1, 2):
            url = (
                "https://push2.eastmoney.com/api/qt/clist/get?"
                f"pn={pn}&pz=100&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
                "&fltt=2&invt=2&fid=f3&fs=b:BK0815"
                "&fields=f12,f14,f2,f3,f15,f16,f17,f18,f8,f6,f21"
            )
            try:
                content = self._get_url_content(url)
                data = json.loads(content)
                diff = (data.get("data") or {}).get("diff") or []
                if not diff:
                    break
                for d in diff:
                    try:
                        code = str(d.get("f12", "")).strip()
                        name = str(d.get("f14", "")).strip()
                        if not code or code in seen_codes:
                            continue
                        if not self.filter.is_main_board_code(code) or not self.filter.is_valid_name(name):
                            continue

                        pre_close = _safe_float(d.get("f18"))
                        if pre_close <= 0:
                            continue

                        curr_price = _safe_float(d.get("f2"), pre_close)
                        close_pct = _safe_float(d.get("f3"))
                        high_price = _safe_float(d.get("f15"), curr_price)
                        low_price = _safe_float(d.get("f16"), curr_price)
                        high_pct = (high_price - pre_close) / pre_close * 100
                        low_pct = (low_price - pre_close) / pre_close * 100
                        turnover = _safe_float(d.get("f8"))
                        amount_yi = _safe_float(d.get("f6")) / 100000000
                        float_cap_yi = _safe_float(d.get("f21")) / 100000000

                        limit_up_price = round(pre_close * 1.10, 2)
                        is_today_limit_up = (curr_price >= limit_up_price - 0.01) or (close_pct >= 9.90)

                        seen_codes.add(code)
                        items.append({
                            "code": code,
                            "name": name,
                            "close_price": curr_price,
                            "pre_close": pre_close,
                            "close_pct": close_pct,
                            "high_pct": high_pct,
                            "low_pct": low_pct,
                            "turnover_rate": turnover,
                            "amount_yi": amount_yi,
                            "float_cap_yi": float_cap_yi,
                            "is_today_limit_up": is_today_limit_up
                        })
                    except Exception:
                        continue
                if len(diff) < 100:
                    break
            except Exception as e:
                logger.warning(f"抓取昨日涨停池第 {pn} 页失败: {e}")
                break
        prev_boards = self.fetch_prev_day_zt_boards()
        if prev_boards:
            for item in items:
                if item["code"] in prev_boards:
                    item["yesterday_boards"] = prev_boards[item["code"]]
        return items

    def fetch_prev_day_zt_boards(self, target_date: Optional[str] = None) -> Dict[str, int]:
        """
        查询上一个交易日东财涨停池全部主板股票的连板高度映射: {code: lbc}
        全系统据此精准识别 1进2 (昨日lbc=1)、2进3 (昨日lbc=2)、3进4 (昨日lbc=3)
        """
        if target_date:
            clean_date = target_date.replace("-", "").strip()
            anchor_dt = datetime.strptime(clean_date, "%Y%m%d")
        else:
            anchor_dt = get_beijing_now().replace(tzinfo=None)

        anchor_key = anchor_dt.strftime("%Y%m%d")
        if anchor_key in self._prev_zt_cache and self._prev_zt_cache[anchor_key]:
            return dict(self._prev_zt_cache[anchor_key])

        tried_days = 0
        for offset in range(1, 16):
            cand_dt = anchor_dt - timedelta(days=offset)
            if not TradeCalendar.is_trading_day(cand_dt):
                continue

            prev_str = cand_dt.strftime("%Y%m%d")
            tried_days += 1
            url = (
                f"https://push2ex.eastmoney.com/getTopicZTPool?"
                f"ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt&Pageindex=0&pagesize=500&sort=lbc:desc&date={prev_str}"
            )
            try:
                content = self._get_url_content(url)
                data = json.loads(content)
                pool = (data.get("data") or {}).get("pool") or []
                if pool:
                    result: Dict[str, int] = {}
                    for item in pool:
                        code = str(item.get("c", "")).strip()
                        name = str(item.get("n", "")).strip()
                        if not code or not self.filter.is_main_board_code(code) or not self.filter.is_valid_name(name):
                            continue
                        lbc = int(_safe_float(item.get("lbc"), 1))
                        result[code] = max(1, lbc)
                    if result:
                        self._prev_zt_cache[anchor_key] = result
                        return dict(result)
            except Exception as e:
                logger.warning(f"获取前交易日 {prev_str} 涨停池连板高度失败: {e}")

            if tried_days >= 3:
                break

        return {}

    def get_consecutive_board_count(self, code: str, is_today_limit_up: bool) -> int:
        """
        通过日K线历史收盘涨幅精准计算该股当前的真实连板数
        """
        secid = f"0.{code}" if code.startswith("0") else f"1.{code}"
        url = (
            f"https://push2his.eastmoney.com/api/qt/stock/kline/get?"
            f"secid={secid}&fields1=f1&fields2=f51,f53,f59&klt=101&fqt=1&end=20500101&lmt=10"
        )
        try:
            content = self._get_url_content(url)
            data = json.loads(content)
            klines = data.get("data", {}).get("klines", [])
            if not klines:
                return 2 if is_today_limit_up else 1

            count = 0
            # klines: 日期,收盘价,涨跌幅
            for k in reversed(klines):
                parts = k.split(",")
                if len(parts) >= 3:
                    pct = float(parts[2])
                    if pct >= 9.85:
                        count += 1
                    else:
                        break
            return max(count, 2 if is_today_limit_up else 1)
        except Exception:
            return 2 if is_today_limit_up else 1

    def fetch_today_zt_pool_details(self) -> Dict[str, Dict[str, Any]]:
        """
        调用东财官方今日实时涨停池接口，获取每只股票的首次封板时间、最后封板时间、炸板次数、封单金额与连板数
        """
        today = get_beijing_now().strftime("%Y%m%d")
        url = (
            f"https://push2ex.eastmoney.com/getTopicZTPool?"
            f"ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt&Pageindex=0&pagesize=500&sort=fbt:asc&date={today}"
        )
        try:
            content = self._get_url_content(url)
            data = json.loads(content)
            pool = (data.get("data") or {}).get("pool") or []
            details = {}
            for item in pool:
                code = str(item.get("c", "")).strip()
                if not code:
                    continue
                name = str(item.get("n", "")).strip()
                price = float(item.get("p", 0) or 0.0) / 1000.0
                zdp = float(item.get("zdp", 0.0) or 0.0)
                hs = float(item.get("hs", 0.0) or 0.0)
                fbt_raw = str(item.get("fbt", 0)).zfill(6)
                lbt_raw = str(item.get("lbt", 0)).zfill(6)
                fbt = f"{fbt_raw[:2]}:{fbt_raw[2:4]}:{fbt_raw[4:]}"
                lbt = f"{lbt_raw[:2]}:{lbt_raw[2:4]}:{lbt_raw[4:]}"
                zbc = int(item.get("zbc", 0) or 0)
                fund = float(item.get("fund", 0) or 0.0)
                lbc = int(item.get("lbc", 1) or 1)
                details[code] = {
                    "code": code,
                    "name": name,
                    "price": price,
                    "change_pct": zdp,
                    "turnover_rate": hs,
                    "first_seal_time": fbt,
                    "last_seal_time": lbt,
                    "open_board_count": zbc,
                    "seal_amount": fund,
                    "continuous_boards": lbc,
                    "industry": str(item.get("hybk", "")).strip()
                }
            return details
        except Exception as e:
            logger.warning(f"获取今日涨停池明细失败: {e}")
            return {}

    def fetch_today_zb_pool_details(self) -> Dict[str, Dict[str, Any]]:
        """
        调用东财官方今日实时炸板池接口，获取所有盘中涨停后炸板的标的
        """
        today = get_beijing_now().strftime("%Y%m%d")
        url = (
            f"https://push2ex.eastmoney.com/getTopicZBPool?"
            f"ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt&Pageindex=0&pagesize=500&sort=fbt:asc&date={today}"
        )
        try:
            content = self._get_url_content(url)
            data = json.loads(content)
            pool = (data.get("data") or {}).get("pool") or []
            details = {}
            for item in pool:
                code = str(item.get("c", "")).strip()
                if not code:
                    continue
                name = str(item.get("n", "")).strip()
                curr = float(item.get("p", 0.0) or 0.0) / 1000.0
                pct = float(item.get("zdp", 0.0) or 0.0)
                fbt_raw = str(item.get("fbt", 0)).zfill(6)
                fbt = f"{fbt_raw[:2]}:{fbt_raw[2:4]}:{fbt_raw[4:]}"
                zbc = int(item.get("zbc", 1) or 1)
                hs = float(item.get("hs", 0.0) or 0.0)
                details[code] = {
                    "code": code,
                    "name": name,
                    "current_price": curr,
                    "change_pct": pct,
                    "first_seal_time": fbt,
                    "open_board_count": zbc,
                    "turnover_rate": hs,
                    "industry": str(item.get("hybk", "")).strip()
                }
            return details
        except Exception as e:
            logger.warning(f"获取今日炸板池明细失败: {e}")
            return {}

