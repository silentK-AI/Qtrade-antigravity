"""
开源免费行情数据源接口封装
基于腾讯行情 (qt.gtimg.cn) 与 东方财富 (push2.eastmoney.com) 公开 REST 接口
无需注册、无需 Token、开箱即用，支持主板批量实时行情与盘口抓取
"""

import json
import urllib.request
import urllib.parse
from typing import List, Dict, Optional, Any
from models.stock_item import StockQuote
from utils.filters import StockFilter


class OpenDataProvider:
    """开源实时行情获取器"""

    def __init__(self, timeout: int = 5):
        self.timeout = timeout
        self.filter = StockFilter()

    def _get_url_content(self, url: str, encoding: str = "utf-8") -> str:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://finance.qq.com"
            }
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            return response.read().decode(encoding, errors="ignore")

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
                curr_price = float(parts[3])
                pre_close = float(parts[4])
                open_price = float(parts[5])
                volume = float(parts[6]) * 100  # 手转股
                amount = float(parts[37]) * 10000 if len(parts) > 37 and parts[37] else 0.0 # 万元
                turnover_rate = float(parts[38]) if len(parts) > 38 and parts[38] else 0.0
                change_pct = float(parts[32]) if len(parts) > 32 and parts[32] else ((curr_price - pre_close) / pre_close * 100 if pre_close else 0.0)
                high = float(parts[33]) if len(parts) > 33 and parts[33] else curr_price
                low = float(parts[34]) if len(parts) > 34 and parts[34] else curr_price
                float_market_cap = float(parts[44]) if len(parts) > 44 and parts[44] else 0.0
                total_market_cap = float(parts[45]) if len(parts) > 45 and parts[45] else 0.0
                
                market = "SH" if code.startswith("6") else "SZ"
                vwap = (amount / volume) if volume > 0 else curr_price

                # 判断主板涨停（主板10%）
                limit_up_price = round(pre_close * 1.10, 2)
                is_limit_up = (curr_price >= limit_up_price - 0.01)

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
                    is_limit_up=is_limit_up
                )
                results.append(quote)
            except (ValueError, IndexError):
                continue

        return results

    def fetch_main_board_top_active(self, page_size: int = 100) -> List[StockQuote]:
        """
        从公开榜单接口抓取主板当下最活跃/涨幅居前的股票池
        """
        # 东财沪深主板榜单 (m:0+t:6,m:0+t:80 为深市主板; m:1+t:2,m:1+t:23 为沪市主板)
        url = (
            "https://push2.eastmoney.com/api/qt/clist/get?"
            "pn=1&pz=150&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
            "&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
            "&fields=f12,f14,f2,f3,f4,f5,f6,f7,f8,f15,f16,f17,f18,f20,f21"
        )
        try:
            content = self._get_url_content(url)
            data = json.loads(content)
            diff = data.get("data", {}).get("diff", [])
            quotes = []
            for item in diff:
                code = str(item.get("f12", ""))
                name = str(item.get("f14", ""))
                curr = float(item.get("f2", 0.0) or 0.0)
                change_pct = float(item.get("f3", 0.0) or 0.0)
                volume = float(item.get("f5", 0.0) or 0.0) * 100
                amount = float(item.get("f6", 0.0) or 0.0)
                turnover = float(item.get("f8", 0.0) or 0.0)
                high = float(item.get("f15", 0.0) or curr)
                low = float(item.get("f16", 0.0) or curr)
                open_p = float(item.get("f17", 0.0) or curr)
                pre_close = float(item.get("f18", 0.0) or curr)
                total_cap = float(item.get("f20", 0.0) or 0.0) / 100000000
                float_cap = float(item.get("f21", 0.0) or 0.0) / 100000000

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
                    is_limit_up=(change_pct >= 9.9)
                )
                if self.filter.filter_quote(quote):
                    quotes.append(quote)
            return quotes
        except Exception:
            return []

    def fetch_yesterday_limit_up_pool(self) -> List[Dict[str, Any]]:
        """
        抓取东方财富【昨日涨停板】(BK0815) 全部成分股在今日的实际表现
        严格按沪深主板过滤，提取：代码、名称、现价、涨跌幅、最高涨幅、最低跌幅、换手、成交额、连板数等
        """
        url = (
            "https://push2.eastmoney.com/api/qt/clist/get?"
            "pn=1&pz=150&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
            "&fltt=2&invt=2&fid=f3&fs=b:BK0815"
            "&fields=f12,f14,f2,f3,f15,f16,f17,f18,f8,f6,f21"
        )
        try:
            content = self._get_url_content(url)
            data = json.loads(content)
            diff = data.get("data", {}).get("diff", [])
            items = []
            for d in diff:
                code = str(d.get("f12", "")).strip()
                name = str(d.get("f14", "")).strip()
                if not self.filter.is_main_board_code(code) or not self.filter.is_valid_name(name):
                    continue

                curr_price = float(d.get("f2", 0.0) or 0.0)
                pre_close = float(d.get("f18", 0.0) or 0.0)
                if pre_close <= 0:
                    continue

                close_pct = float(d.get("f3", 0.0) or 0.0)
                high_price = float(d.get("f15", 0.0) or curr_price)
                low_price = float(d.get("f16", 0.0) or curr_price)
                high_pct = (high_price - pre_close) / pre_close * 100
                low_pct = (low_price - pre_close) / pre_close * 100
                turnover = float(d.get("f8", 0.0) or 0.0)
                amount_yi = float(d.get("f6", 0.0) or 0.0) / 100000000
                float_cap_yi = float(d.get("f21", 0.0) or 0.0) / 100000000

                limit_up_price = round(pre_close * 1.10, 2)
                is_today_limit_up = (curr_price >= limit_up_price - 0.01) or (close_pct >= 9.90)

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
            return items
        except Exception as e:
            print(f"[数据源错误] 抓取昨日涨停池失败: {e}")
            return []

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

