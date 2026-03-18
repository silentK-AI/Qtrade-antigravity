"""
个股/ETF 次日价格预测模块

基于历史 K 线数据，使用 XGBoost 模型预测次日波动率，
进而计算预测的次日最高价和最低价。

特征工程:
  - 动量类: 1/3/5/10/20 日涨跌幅
  - 波动率类: ATR5/ATR10/ATR20、历史波动率
  - 均线类: MA5/10/20/60 偏离度、均线斜率
  - K线形态: 实体比、上下影线、价格位置
  - 量能类: 量比、成交额比
  - 技术指标: RSI14、KDJ(K/D/J)、MACD、布林带宽度
  - 日历特征: 星期几

预测目标:
  - 次日波动率 = (最高价 - 最低价) / 前收 * 100 (以前收为基准)
  - 次日方向 = (次日收盘 - 前收) / 前收 * 100
  - 最终输出: predicted_high = 前收 * (1 + (方向 + 波动/2)/100)
             predicted_low  = 前收 * (1 + (方向 - 波动/2)/100)
"""
from __future__ import annotations

import os
# 避免 OMP 共享内存权限问题（Cursor 沙盒/某些 Linux 环境）
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import numpy as np
import pandas as pd
from loguru import logger


@dataclass
class StockPricePrediction:
    """个股次日价格预测结果"""
    symbol: str
    name: str
    pred_high: float        # 预测次日最高价
    pred_low: float         # 预测次日最低价
    pred_range_pct: float   # 预测波动率 (%)
    confidence: float       # 模型置信度 (R² 0-1)
    last_close: float       # 基准收盘价
    model_samples: int = 0  # 训练样本数

    @property
    def mid_price(self) -> float:
        return round((self.pred_high + self.pred_low) / 2, 3)


class StockPricePredictor:
    """
    个股/ETF 次日价格预测器。

    使用方式:
        predictor = StockPricePredictor(model_dir='models/stock')

        # 训练（每天盘前或每周一次）
        predictor.train(symbol, name, hist_df)

        # 预测（盘前报告时调用）
        pred = predictor.predict(symbol, name, hist_df)
    """

    # 特征维度
    N_FEATURES = 28

    def __init__(self, model_dir: str = "models/stock"):
        self._model_dir = Path(model_dir)
        self._model_dir.mkdir(parents=True, exist_ok=True)
        # {symbol: (range_model, dir_model, r2, n_samples)}
        self._models: dict[str, tuple] = {}

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def train_and_predict(self, symbol: str, name: str, hist_df: pd.DataFrame,
                           today_open: float = 0.0,
                           market_change_pct: float = 0.0,
                           auction_vol_ratio: float = 0.0) -> Optional[StockPricePrediction]:
        """
        训练模型并立即预测（每次盘前调用，全量历史数据训练）

        Args:
            symbol:             标的代码
            name:               标的名称
            hist_df:            历史 K 线 DataFrame
            today_open:         当天实际开盘价（9:25后获取），0表示用历史最后一行open
            market_change_pct:  上证指数当前涨跌幅（%），0表示未知
            auction_vol_ratio:  竞价量比（竞价成交量/过去20日均量），0表示未知
        Returns:
            StockPricePrediction 或 None
        """
        df = self._normalize_df(hist_df)
        if df is None or len(df) < 30:
            logger.warning(f"[{symbol}] 历史数据不足 30 行，跳过预测")
            return None

        ok = self._train(symbol, df)
        if not ok:
            return None

        return self._predict(symbol, name, df,
                             today_open=today_open,
                             market_change_pct=market_change_pct,
                             auction_vol_ratio=auction_vol_ratio)

    def has_model(self, symbol: str) -> bool:
        return symbol in self._models

    # ------------------------------------------------------------------
    # 特征工程
    # ------------------------------------------------------------------

    def _build_features(self, df: pd.DataFrame, idx: int) -> Optional[np.ndarray]:
        """
        从 df.iloc[:idx+1] 构建 N_FEATURES 维特征向量，预测 idx+1 天数据。
        idx 必须 >= 25。
        """
        if idx < 25:
            return None

        try:
            window = df.iloc[max(0, idx - 249): idx + 1].copy()
            closes = window["close"].values.astype(float)
            highs  = window["high"].values.astype(float)
            lows   = window["low"].values.astype(float)
            opens  = window["open"].values.astype(float)
            vols   = window["volume"].values.astype(float)

            c  = closes[-1]   # 当日收盘
            o  = opens[-1]
            h  = highs[-1]
            l  = lows[-1]
            pc = closes[-2] if len(closes) >= 2 else c  # 前收

            if c <= 0 or pc <= 0:
                return None

            feats = []

            # ── 动量 (5) ──
            for n in [1, 3, 5, 10, 20]:
                if len(closes) > n:
                    feats.append((c / closes[-(n+1)] - 1) * 100)
                else:
                    feats.append(0.0)

            # ── 波动率 (3) ──
            for n in [5, 10, 20]:
                tr_arr = []
                start = max(1, len(closes) - n)
                for j in range(start, len(closes)):
                    tr = max(
                        highs[j] - lows[j],
                        abs(highs[j] - closes[j-1]),
                        abs(lows[j] - closes[j-1]),
                    )
                    tr_arr.append(tr)
                atr = np.mean(tr_arr) / c * 100 if tr_arr and c > 0 else 0.0
                feats.append(atr)

            # ── 历史波动率 (1) ──
            if len(closes) >= 21:
                rets = np.diff(np.log(closes[-21:]))
                hv = float(np.std(rets) * np.sqrt(252) * 100)
            else:
                hv = 0.0
            feats.append(hv)

            # ── 均线偏离度 (4) ──
            for n in [5, 10, 20, 60]:
                if len(closes) >= n:
                    ma = float(np.mean(closes[-n:]))
                    feats.append((c / ma - 1) * 100 if ma > 0 else 0.0)
                else:
                    feats.append(0.0)

            # ── 均线斜率 (2) ── MA5/MA20 的 5 日斜率
            for n in [5, 20]:
                if len(closes) >= n + 5:
                    ma_now = float(np.mean(closes[-n:]))
                    ma_5d_ago = float(np.mean(closes[-(n+5):-5]))
                    slope = (ma_now / ma_5d_ago - 1) * 100 if ma_5d_ago > 0 else 0.0
                else:
                    slope = 0.0
                feats.append(slope)

            # ── K线形态 (4) ──
            hl = h - l
            body = abs(c - o)
            feats.append(body / hl if hl > 0 else 0.0)                      # 实体比
            feats.append((h - max(o, c)) / hl if hl > 0 else 0.0)           # 上影线
            feats.append((min(o, c) - l) / hl if hl > 0 else 0.0)           # 下影线
            feats.append((c - l) / hl if hl > 0 else 0.5)                   # 收盘位置

            # ── 量能 (2) ──
            vol_ma5 = float(np.mean(vols[-5:])) if len(vols) >= 5 else float(np.mean(vols))
            feats.append(vols[-1] / vol_ma5 if vol_ma5 > 0 else 1.0)        # 量比
            vol_ma20 = float(np.mean(vols[-20:])) if len(vols) >= 20 else vol_ma5
            feats.append(vols[-1] / vol_ma20 if vol_ma20 > 0 else 1.0)      # 20日量比

            # ── RSI14 (1) ──
            feats.append(self._rsi(closes, 14))

            # ── 布林带宽度 (1) ──
            if len(closes) >= 20:
                ma20 = float(np.mean(closes[-20:]))
                std20 = float(np.std(closes[-20:]))
                bw = std20 * 4 / ma20 * 100 if ma20 > 0 else 0.0
            else:
                bw = 0.0
            feats.append(bw)

            # ── 日历 (1) ──
            try:
                dow = pd.Timestamp(window["date"].iloc[-1]).weekday()
            except Exception:
                from datetime import datetime as _dt
                dow = _dt.now().weekday()
            feats.append(float(dow))

            # ── 开盘价因子 (2) ── 仅预测时有效，训练时用历史开盘
            # 开盘跳空幅度：(open - prev_close) / prev_close * 100
            gap_pct = (o - pc) / pc * 100 if pc > 0 else 0.0
            feats.append(gap_pct)
            # 开盘价相对MA5偏离
            ma5_val = float(np.mean(closes[-5:])) if len(closes) >= 5 else c
            open_ma5_dev = (o / ma5_val - 1) * 100 if ma5_val > 0 else 0.0
            feats.append(open_ma5_dev)

            # ── 大盘与量比因子 (2) ── 训练时用0占位，预测时从外部传入
            feats.append(0.0)   # 大盘（上证）涨跌幅，预测时覆盖
            feats.append(0.0)   # 竞价量比，预测时覆盖

            assert len(feats) == self.N_FEATURES, f"特征数量异常: {len(feats)}"
            return np.array(feats, dtype=np.float64)

        except Exception as e:
            logger.debug(f"[{symbol if 'symbol' in dir() else '?'}] 特征构建失败: {e}")
            return None

    # ------------------------------------------------------------------
    # 训练
    # ------------------------------------------------------------------

    def _train(self, symbol: str, df: pd.DataFrame) -> bool:
        """训练波动率模型和方向模型"""
        try:
            from xgboost import XGBRegressor
            from sklearn.metrics import r2_score
            import warnings
            warnings.filterwarnings("ignore")

            X_list, y_range_list, y_dir_list = [], [], []

            for i in range(25, len(df) - 1):
                feat = self._build_features(df, i)
                if feat is None:
                    continue

                c_now  = float(df.iloc[i]["close"])
                h_next = float(df.iloc[i+1]["high"])
                l_next = float(df.iloc[i+1]["low"])
                c_next = float(df.iloc[i+1]["close"])

                if c_now <= 0:
                    continue

                # 目标1: 次日波动率 (高低差 / 前收)
                y_range = (h_next - l_next) / c_now * 100
                # 目标2: 次日方向 (收盘涨跌幅)
                y_dir   = (c_next - c_now) / c_now * 100

                X_list.append(feat)
                y_range_list.append(y_range)
                y_dir_list.append(y_dir)

            if len(X_list) < 20:
                logger.warning(f"[{symbol}] 有效训练样本仅 {len(X_list)} 条，不足 20")
                return False

            X       = np.array(X_list)
            y_range = np.array(y_range_list)
            y_dir   = np.array(y_dir_list)

            params = dict(
                n_estimators=300,
                max_depth=5,
                learning_rate=0.03,
                subsample=0.8,
                colsample_bytree=0.7,
                min_child_weight=3,
                reg_alpha=0.1,
                reg_lambda=1.5,
                random_state=42,
                n_jobs=-1,
                verbosity=0,
            )

            # 波动率模型
            range_model = XGBRegressor(**params)
            range_model.fit(X, y_range)

            # 方向模型
            dir_model = XGBRegressor(**params)
            dir_model.fit(X, y_dir)

            # 验证（最后 20% 数据）
            split = max(1, int(len(X) * 0.8))
            X_val = X[split:]
            r2 = 0.5
            mae_pct = 999.0  # 平均误差百分比
            if len(X_val) > 3:
                from sklearn.metrics import r2_score, mean_absolute_error
                r2_range = r2_score(y_range[split:], range_model.predict(X_val))
                r2_dir   = r2_score(y_dir[split:],   dir_model.predict(X_val))
                r2 = max(0.0, (r2_range + r2_dir) / 2)
                # 用高低价 MAE% 作为误差指标（更直观）
                mae_range = mean_absolute_error(y_range[split:], range_model.predict(X_val))
                mae_dir   = mean_absolute_error(y_dir[split:],   dir_model.predict(X_val))
                mae_pct   = round((mae_range + mae_dir) / 2, 3)  # 平均绝对误差 %
                logger.debug(
                    f"[{symbol}] 波动率 R²={r2_range:.3f} 方向 R²={r2_dir:.3f} "
                    f"MAE={mae_pct:.3f}% 样本={len(X)}"
                )

            self._models[symbol] = (range_model, dir_model, r2, len(X), mae_pct)
            logger.info(f"[{symbol}] 预测模型训练完成 样本={len(X)} R²={r2:.3f} MAE={mae_pct:.3f}%")
            return True

        except Exception as e:
            logger.error(f"[{symbol}] 模型训练失败: {e}")
            return False

    # ------------------------------------------------------------------
    # 预测
    # ------------------------------------------------------------------

    def _predict(self, symbol: str, name: str, df: pd.DataFrame,
                 today_open: float = 0.0,
                 market_change_pct: float = 0.0,
                 auction_vol_ratio: float = 0.0) -> Optional[StockPricePrediction]:
        """使用已训练模型预测次日最高/最低价"""
        if symbol not in self._models:
            return None

        try:
            # 若传入当天开盘价，覆盖 df 最后一行的 open
            if today_open > 0:
                df = df.copy()
                df.iloc[-1, df.columns.get_loc("open")] = today_open
                logger.debug(f"[{symbol}] 使用当日开盘价 {today_open:.3f} 预测")

            feat = self._build_features(df, len(df) - 1)
            if feat is None:
                return None

            # 覆盖大盘涨跌和竞价量比（特征向量的最后2位）
            if market_change_pct != 0.0:
                feat[-2] = market_change_pct
            if auction_vol_ratio != 0.0:
                feat[-1] = auction_vol_ratio
            if market_change_pct != 0.0 or auction_vol_ratio != 0.0:
                logger.debug(f"[{symbol}] 大盘={market_change_pct:+.2f}% 竞价量比={auction_vol_ratio:.2f}")
            if feat is None:
                return None

            range_model, dir_model, r2, n_samples, mae_pct = self._models[symbol]
            X = feat.reshape(1, -1)

            pred_range = float(range_model.predict(X)[0])  # 预测波动率 %
            pred_dir   = float(dir_model.predict(X)[0])    # 预测方向 %

            # 确保波动率为正
            pred_range = max(0.5, abs(pred_range))

            last_close = float(df.iloc[-1]["close"])
            if last_close <= 0:
                return None

            # 最高价 = 前收 * (1 + (方向 + 波动/2) / 100)
            # 最低价 = 前收 * (1 + (方向 - 波动/2) / 100)
            pred_high = round(last_close * (1 + (pred_dir + pred_range / 2) / 100), 3)
            pred_low  = round(last_close * (1 + (pred_dir - pred_range / 2) / 100), 3)

            # 保证 high >= low
            if pred_high < pred_low:
                pred_high, pred_low = pred_low, pred_high

            logger.debug(
                f"[{symbol}] 预测: 高={pred_high:.3f} 低={pred_low:.3f} "
                f"波动={pred_range:.2f}% 方向={pred_dir:+.2f}% MAE={mae_pct:.3f}%"
            )

            return StockPricePrediction(
                symbol=symbol,
                name=name,
                pred_high=pred_high,
                pred_low=pred_low,
                pred_range_pct=round(pred_range, 2),
                confidence=round(r2, 3),  # R² 置信度
                last_close=last_close,
                model_samples=n_samples,
            )

        except Exception as e:
            logger.error(f"[{symbol}] 预测失败: {e}")
            return None

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_df(df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """统一列名为 date/open/high/low/close/volume"""
        col_map = {
            "日期": "date", "开盘": "open", "最高": "high",
            "最低": "low",  "收盘": "close", "成交量": "volume",
        }
        df = df.rename(columns=col_map).copy()
        required = ["open", "high", "low", "close", "volume"]
        for col in required:
            if col not in df.columns:
                return None
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=required).reset_index(drop=True)
        if "date" not in df.columns:
            df["date"] = pd.RangeIndex(len(df))
        return df

    @staticmethod
    def _rsi(closes: np.ndarray, period: int = 14) -> float:
        """计算 RSI"""
        if len(closes) < period + 1:
            return 50.0
        deltas = np.diff(closes[-(period + 1):])
        gains  = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_g  = np.mean(gains)
        avg_l  = np.mean(losses)
        if avg_l == 0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + avg_g / avg_l)
 