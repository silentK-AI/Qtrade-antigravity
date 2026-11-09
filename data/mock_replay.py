"""
离线高保真仿真与历史切片回放生成器
包含四个关键时钟节点：
1. 09:23:00 不可撤单竞价切片（提前锁定全天封死+次日连板）
2. 09:25:00 竞价开盘切片
3. 14:50:00 尾盘异动切片
4. 14:58:00 尾盘不可撤单集合竞价切片（提前锁定次日涨停买入）
"""

from typing import List, Tuple
from models.stock_item import StockQuote, AuctionSnapshot, ClosingSnapshot, Snapshot0923, Snapshot1458


class MockReplayProvider:
    """提供高保真主板行情与四个时间节点的切片"""

    @classmethod
    def get_0923_dataset(cls) -> List[Tuple[StockQuote, Snapshot0923]]:
        """
        09:23:00 真实不可撤单阶段样本：
        标的1: 600678 (沪市主板) - 拟撮合涨停+10%，真实不可撤单买一封单 9500 万(占流通盘 7.2‰)，9:19-9:20撤单率仅1.2%(无诱多)，昨首板 (极高概率全天封死+次日连板)
        标的2: 002345 (深市主板) - 拟撮合涨幅+7.5%，不可撤单封单 4800 万，9:20-9:23价格逐级跳档抢筹 (主板强势突破冲板)
        标的3: 601888 (沪市主板) - 9:15-9:20假挂涨停，9:19:55大单撤单率高达75% (诱多出货标的，必须淘汰)
        标的4: 300999 (创业板) - 必须被主板规则严格过滤
        """
        samples = []

        # 1. 超强真金白银锁单龙: 600678
        q1 = StockQuote(
            code="600678", name="四川金顶", market="SH",
            current_price=11.00, pre_close=10.00, open_price=11.00,
            high_price=11.00, low_price=11.00, change_pct=10.00,
            volume=3500000, amount=38500000, turnover_rate=1.5,
            float_market_cap=45.0, total_market_cap=48.0,
            yesterday_status="昨日首板", sector="西部大开发 / 算力"
        )
        s1 = Snapshot0923(
            code="600678", indicative_price=11.00, indicative_change_pct=10.00,
            real_seal_amount=95000000.0, real_seal_to_float_ratio=7.2, # 9500万封单
            spoof_withdrawn_ratio=0.012, # 撤单率仅1.2%，绝非诱多
            is_sealed_limit=True, volume_920_923=2800000.0,
            is_upward_rush=True
        )
        samples.append((q1, s1))

        # 2. 09:23 抢筹冲板龙头: 002345
        q2 = StockQuote(
            code="002345", name="潮宏基", market="SZ",
            current_price=16.85, pre_close=15.68, open_price=16.85,
            high_price=16.85, low_price=16.85, change_pct=7.46,
            volume=2600000, amount=43810000, turnover_rate=1.1,
            float_market_cap=58.0, total_market_cap=62.0,
            yesterday_status="昨日首板", sector="消费新质"
        )
        s2 = Snapshot0923(
            code="002345", indicative_price=16.85, indicative_change_pct=7.46,
            real_seal_amount=48000000.0, real_seal_to_float_ratio=3.8,
            spoof_withdrawn_ratio=0.045, is_sealed_limit=False,
            volume_920_923=2100000.0, is_upward_rush=True
        )
        samples.append((q2, s2))

        # 3. 虚假撤单诱多标的: 601888
        q3 = StockQuote(
            code="601888", name="中国中免", market="SH",
            current_price=82.50, pre_close=80.00, open_price=82.50,
            high_price=82.50, low_price=82.50, change_pct=3.12,
            volume=500000, amount=41250000, turnover_rate=0.2,
            float_market_cap=150.0, total_market_cap=160.0,
            yesterday_status="普通", sector="免税"
        )
        s3 = Snapshot0923(
            code="601888", indicative_price=82.50, indicative_change_pct=3.12,
            real_seal_amount=5000000.0, real_seal_to_float_ratio=0.3,
            spoof_withdrawn_ratio=0.75, # 撤单率高达75%！
            is_sealed_limit=False, volume_920_923=400000.0,
            is_upward_rush=False
        )
        samples.append((q3, s3))

        return samples

    @classmethod
    def get_1458_dataset(cls) -> List[Tuple[StockQuote, Snapshot1458]]:
        """
        14:58:00 尾盘集合竞价切片样本：
        标的1: 600789 (沪市主板) - 早盘09:36封死 + 1.25亿封单 -> 【买不进·龙头风向标/持股锁仓】
        标的2: 000888 (深市主板) - 14:42 尾盘刚回封 + 3800万封单 + 换手15% -> 【刚封板·能排进买进】
        标的3: 600345 (沪市主板) - +7.8% 蓄势待发未封死 + 尾盘主力大单扫盘4500万 -> 【100%秒买进·次日冲板】
        标的4: 600111 (沪市主板) - 涨幅仅+2.1% 平庸标的 (淘汰)
        """
        samples = []

        # 1. 早盘极早封死+1亿封单 (买不进，仅供风向标/持仓锁仓)
        q1 = StockQuote(
            code="600789", name="鲁抗医药", market="SH",
            current_price=13.20, pre_close=12.00, open_price=12.60,
            high_price=13.20, low_price=12.50, change_pct=10.00,
            volume=32000000, amount=422400000, turnover_rate=9.8,
            float_market_cap=52.0, total_market_cap=55.0,
            is_limit_up=True, sector="创新药 / 合成生物"
        )
        s1 = Snapshot1458(
            code="600789", indicative_price=13.20, indicative_change_pct=10.00,
            is_limit_up=True, closing_seal_amount=125000000.0,
            seal_to_float_ratio=11.2, day_open_board_count=0,
            first_seal_time="09:36", continuous_board_count=2
        )
        samples.append((q1, s1))

        # 2. 尾盘刚刚回封 (14:42封死，抛盘活跃，能排进买到！)
        q2 = StockQuote(
            code="000888", name="峨眉山A", market="SZ",
            current_price=15.40, pre_close=14.00, open_price=14.30,
            high_price=15.40, low_price=14.20, change_pct=10.00,
            volume=38000000, amount=570000000, turnover_rate=15.2,
            float_market_cap=60.0, total_market_cap=64.0,
            is_limit_up=True, sector="文旅消费"
        )
        s2 = Snapshot1458(
            code="000888", indicative_price=15.40, indicative_change_pct=10.00,
            is_limit_up=True, closing_seal_amount=38000000.0,
            seal_to_float_ratio=3.8, day_open_board_count=1,
            first_seal_time="14:42", continuous_board_count=1
        )
        samples.append((q2, s2))

        # 3. 尾盘蓄势未板 (+7.85%，100%市价秒买进，次日冲板)
        q3 = StockQuote(
            code="600345", name="长城科技", market="SH",
            current_price=16.88, pre_close=15.65, open_price=15.80,
            high_price=16.95, low_price=15.70, change_pct=7.85,
            volume=42000000, amount=708000000, turnover_rate=13.5,
            float_market_cap=55.0, total_market_cap=58.0,
            is_limit_up=False, sector="高端制造"
        )
        s3 = Snapshot1458(
            code="600345", indicative_price=16.88, indicative_change_pct=7.85,
            is_limit_up=False, closing_seal_amount=0.0,
            seal_to_float_ratio=0.0, day_open_board_count=0,
            first_seal_time="15:00", continuous_board_count=0
        )
        samples.append((q3, s3))

        # 4. 平庸淘汰标的
        q4 = StockQuote(
            code="600111", name="北方稀土", market="SH",
            current_price=20.42, pre_close=20.00, open_price=20.10,
            high_price=20.60, low_price=19.90, change_pct=2.10,
            volume=15000000, amount=306300000, turnover_rate=2.1,
            float_market_cap=120.0, total_market_cap=130.0,
            is_limit_up=False, sector="有色"
        )
        s4 = Snapshot1458(
            code="600111", indicative_price=20.42, indicative_change_pct=2.10,
            is_limit_up=False, closing_seal_amount=0.0,
            seal_to_float_ratio=0.0, day_open_board_count=0,
            first_seal_time="15:00", continuous_board_count=0
        )
        samples.append((q4, s4))

        return samples

    @classmethod
    def get_morning_auction_dataset(cls) -> List[Tuple[StockQuote, AuctionSnapshot]]:
        """09:25:00 集合竞价开盘切片"""
        samples = []
        q1 = StockQuote(
            code="600123", name="华新龙头", market="SH",
            current_price=12.43, pre_close=12.00, open_price=12.43,
            high_price=12.43, low_price=12.43, change_pct=3.58,
            volume=4500000, amount=55935000, turnover_rate=1.8,
            float_market_cap=55.0, total_market_cap=60.0,
            yesterday_status="昨日首板", sector="低空经济"
        )
        a1 = AuctionSnapshot(
            code="600123", auction_price=12.43, gap_percent=3.58,
            auction_volume=4500000, auction_amount=55935000,
            prev_day_volume=36000000, auction_vol_ratio=0.125,
            unmatched_buy_volume=1800000, unmatched_amount=22374000,
            bid_ask_strength=3.2, is_924_rush=True
        )
        samples.append((q1, a1))

        q2 = StockQuote(
            code="002456", name="智能先锋", market="SZ",
            current_price=18.43, pre_close=18.00, open_price=18.43,
            high_price=18.43, low_price=18.43, change_pct=2.39,
            volume=3200000, amount=58976000, turnover_rate=1.2,
            float_market_cap=68.0, total_market_cap=72.0,
            yesterday_status="昨日冲高回落", sector="人工智能"
        )
        a2 = AuctionSnapshot(
            code="002456", auction_price=18.43, gap_percent=2.39,
            auction_volume=3200000, auction_amount=58976000,
            prev_day_volume=35500000, auction_vol_ratio=0.090,
            unmatched_buy_volume=1100000, unmatched_amount=20273000,
            bid_ask_strength=2.4, is_924_rush=True
        )
        samples.append((q2, a2))

        return samples

    @classmethod
    def get_closing_stage_dataset(cls) -> List[Tuple[StockQuote, ClosingSnapshot]]:
        """14:50:00 尾盘选股切片"""
        samples = []
        q1 = StockQuote(
            code="600345", name="长城科技", market="SH",
            current_price=16.88, pre_close=15.80, open_price=16.00,
            high_price=16.95, low_price=15.90, change_pct=6.84,
            volume=35000000, amount=577500000, turnover_rate=11.5,
            float_market_cap=48.0, total_market_cap=52.0,
            vwap=16.50, sector="高端制造"
        )
        c1 = ClosingSnapshot(
            code="600345", current_price=16.88, day_high=16.95,
            close_to_high_ratio=0.996, current_change_pct=6.84,
            vwap=16.50, is_above_vwap=True,
            tail_volume=8400000, total_volume=35000000,
            tail_vol_ratio=0.24, tail_net_large_inflow=4800.0,
            is_rebound_limit=False
        )
        samples.append((q1, c1))

        q2 = StockQuote(
            code="000568", name="红星发展", market="SZ",
            current_price=22.00, pre_close=20.00, open_price=20.50,
            high_price=22.00, low_price=20.20, change_pct=10.00,
            volume=28000000, amount=590800000, turnover_rate=14.2,
            float_market_cap=56.0, total_market_cap=60.0,
            vwap=21.10, is_limit_up=True, sector="化工新材料"
        )
        c2 = ClosingSnapshot(
            code="000568", current_price=22.00, day_high=22.00,
            close_to_high_ratio=1.000, current_change_pct=10.00,
            vwap=21.10, is_above_vwap=True,
            tail_volume=6160000, total_volume=28000000,
            tail_vol_ratio=0.22, tail_net_large_inflow=3600.0,
            is_rebound_limit=True
        )
        samples.append((q2, c2))

        return samples
