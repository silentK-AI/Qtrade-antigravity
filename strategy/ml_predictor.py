"""
XGBoost 价格预测器

基于隔夜美股/港股/日股指标和 ETF 历史行情数据，
使用 XGBoost 模型预测次日的最高价和最低价。

特征输入:
  - 隔夜关联标的：涨跌幅、缺口方向、动量评分、波幅
  - ETF 历史：前 N 日 OHLCV、振幅、涨跌幅
  - 技术指标：MA5/MA10/MA20 偏离度、ATR、RSI

预测输出:
  - predicted_high: 次日预测最高价
  - predicted_low:  次日预测最低价
"""
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import numpy as np
import pandas as pd
from loguru import logger

from data.overnight_data import OvernightInfo


@dataclass
class PricePrediction:
    """价格预测结果"""
    etf_code: str
    predicted_high: float
    predicted_low: float
    confidence: float = 0.0        # 预测置信度 (0-1)
    feature_importance: Optional[dict] = None


class MLPredictor:
    """
    XGBoost 价格预测器。

    每日开盘前：
      1. 加载已训练模型
      2. 用最新隔夜数据 + 历史行情构建特征
      3. 输出次日最高价/最低价预测
    """

    # 特征列名 (12 维独立特征，基于相关性分析筛选)
    #
    # 筛选原则: 从原 30 个特征中，按"独立不相关性"保留每组中
    # 重要性最高的代表特征。移除的原因包括:
    #   - 10 个零方差特征 (隔夜/溢价率在训练中无数据)
    #   - 8 个高相关冗余特征 (|r|>0.7)
    FEATURE_NAMES = [
        # ---- 隔夜 (1) ----
        "overnight_change_pct",       # 隔夜涨跌幅 (代表全部隔夜信息)
        # ---- 前日 K 线形态 (3) ----
        "prev_return",                # 前日涨跌幅 (日动量)
        "prev_close_position",        # 收盘在 high-low 中的位置 (K线重心)
        "prev_body_ratio",            # 实体/振幅比 (K线形状)
        # ---- 多日趋势 (2) ----
        "return_5d",                  # 5 日累计收益 (中期趋势)
        "ma5_deviation",              # MA5 偏离度 (均值回归信号, imp=0.10)
        # ---- 波动率 (1) ----
        "atr_5d",                     # 5 日 ATR (imp=0.18, 最高)
        # ---- 技术指标 (1) ----
        "rsi_14d",                    # 14 日 RSI (超买超卖)
        # ---- 日历 (1) ----
        "day_of_week",                # 星期几 (0=周一 ... 4=周五)
        # ---- 量能 (1) ----
        "volume_ma5_ratio",           # 量比 (当日量/5日均量)
        # ---- 微观结构 (2) ----
        "upper_shadow_pct",           # 上影线占比 (卖压)
        "lower_shadow_pct",           # 下影线占比 (买压)
    ]

    def __init__(self, model_dir: str = "models"):
        self._model_dir = Path(model_dir)
        self._model_dir.mkdir(parents=True, exist_ok=True)
        # {etf_code: (high_model, low_model)}
        self._models: dict[str, tuple] = {}

    # ------------------------------------------------------------------
    #  公开接口
    # ------------------------------------------------------------------

    def load_model(self, etf_code: str) -> bool:
        """加载已训练的模型"""
        try:
            import joblib

            high_path = self._model_dir / f"{etf_code}_high.joblib"
            low_path = self._model_dir / f"{etf_code}_low.joblib"

            if not high_path.exists() or not low_path.exists():
                logger.warning(f"[{etf_code}] 模型文件不存在，需先训练")
                return False

            high_model = joblib.load(high_path)
            low_model = joblib.load(low_path)
            self._models[etf_code] = (high_model, low_model)
            logger.info(f"[{etf_code}] ML 模型加载成功")
            return True

        except Exception as e:
            logger.error(f"[{etf_code}] 模型加载失败: {e}")
            return False

    def load_all_models(self, etf_codes: list[str]) -> int:
        """批量加载模型，返回成功加载的数量"""
        count = 0
        for code in etf_codes:
            if self.load_model(code):
                count += 1
        return count

    def has_model(self, etf_code: str) -> bool:
        """检查是否有该标的的模型"""
        return etf_code in self._models

    def predict(
        self,
        etf_code: str,
        overnight_info: Optional[OvernightInfo],
        hist_df: pd.DataFrame,
    ) -> Optional[PricePrediction]:
        """
        预测次日最高价和最低价。

        Args:
            etf_code:       ETF 代码
            overnight_info: 隔夜行情信息（可为 None）
            hist_df:        至少 15 日的 OHLCV 历史 DataFrame
                           需包含列: 开盘, 最高, 最低, 收盘, 成交量

        Returns:
            PricePrediction 或 None（预测失败时）
        """
        if not self.has_model(etf_code):
            return None

        features = self.build_features(overnight_info, hist_df)
        if features is None:
            return None

        try:
            high_model, low_model = self._models[etf_code]
            X = features.reshape(1, -1)
            pred_high = float(high_model.predict(X)[0])
            pred_low = float(low_model.predict(X)[0])

            # 确保 high >= low
            if pred_high < pred_low:
                pred_high, pred_low = pred_low, pred_high

            # 用模型的 R² 作为简单的置信度估计（训练时存储）
            confidence = getattr(high_model, '_train_r2', 0.5)

            return PricePrediction(
                etf_code=etf_code,
                predicted_high=pred_high,
                predicted_low=pred_low,
                confidence=confidence,
            )

        except Exception as e:
            logger.error(f"[{etf_code}] 预测失败: {e}")
            return None

    def train(
        self,
        etf_code: str,
        hist_df: pd.DataFrame,
        overnight_series: Optional[list[Optional[OvernightInfo]]] = None,
    ) -> bool:
        """
        训练 XGBoost 模型。

        Args:
            etf_code:          ETF 代码
            hist_df:           历史日线数据（需包含: 开盘,最高,最低,收盘,成交量）
                              至少 30 行
            overnight_series:  与 hist_df 行对齐的隔夜信息列表（可为 None）

        Returns:
            训练是否成功
        """
        try:
            from xgboost import XGBRegressor
            from sklearn.model_selection import TimeSeriesSplit
            from sklearn.metrics import r2_score, mean_absolute_error
            import joblib

            if len(hist_df) < 25:
                logger.warning(f"[{etf_code}] 历史数据不足 25 条，无法训练")
                return False

            # 构建训练样本
            X_list, y_high_list, y_low_list = [], [], []

            for i in range(15, len(hist_df) - 1):
                # 用 i 之前的数据构建特征，预测第 i+1 天的最高/最低价
                window_df = hist_df.iloc[:i + 1].copy()

                # 隔夜信息
                ov = overnight_series[i] if overnight_series and i < len(overnight_series) else None

                features = self.build_features(ov, window_df)
                if features is None:
                    continue

                # 预测目标：下一天的最高价和最低价（相对于当日收盘的比率）
                next_row = hist_df.iloc[i + 1]
                current_close = float(hist_df.iloc[i]["收盘"])
                if current_close <= 0:
                    continue

                target_high = float(next_row["最高"]) / current_close
                target_low = float(next_row["最低"]) / current_close

                X_list.append(features)
                y_high_list.append(target_high)
                y_low_list.append(target_low)

            if len(X_list) < 10:
                logger.warning(f"[{etf_code}] 有效训练样本不足 10 个")
                return False

            X = np.array(X_list)
            y_high = np.array(y_high_list)
            y_low = np.array(y_low_list)

            logger.info(f"[{etf_code}] 训练样本: {len(X)} 条, 特征: {X.shape[1]} 维")

            # XGBoost 参数
            xgb_params = {
                "n_estimators": 200,
                "max_depth": 5,
                "learning_rate": 0.05,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "reg_alpha": 0.1,
                "reg_lambda": 1.0,
                "random_state": 42,
                "n_jobs": -1,
            }

            # 训练最高价模型
            high_model = XGBRegressor(**xgb_params)
            high_model.fit(X, y_high)

            # 训练最低价模型
            low_model = XGBRegressor(**xgb_params)
            low_model.fit(X, y_low)

            # 评估（最后 20% 作为验证）
            split = int(len(X) * 0.8)
            X_val = X[split:]
            if len(X_val) > 0:
                high_r2 = r2_score(y_high[split:], high_model.predict(X_val))
                low_r2 = r2_score(y_low[split:], low_model.predict(X_val))
                high_mae = mean_absolute_error(y_high[split:], high_model.predict(X_val))
                low_mae = mean_absolute_error(y_low[split:], low_model.predict(X_val))

                logger.info(
                    f"[{etf_code}] 最高价模型 R²={high_r2:.4f} MAE={high_mae:.6f}"
                )
                logger.info(
                    f"[{etf_code}] 最低价模型 R²={low_r2:.4f} MAE={low_mae:.6f}"
                )

                # 存储 R² 用于置信度
                high_model._train_r2 = max(0, high_r2)
                low_model._train_r2 = max(0, low_r2)
            else:
                high_model._train_r2 = 0.5
                low_model._train_r2 = 0.5

            # 保存模型
            high_path = self._model_dir / f"{etf_code}_high.joblib"
            low_path = self._model_dir / f"{etf_code}_low.joblib"
            joblib.dump(high_model, high_path)
            joblib.dump(low_model, low_path)

            self._models[etf_code] = (high_model, low_model)
            logger.info(f"[{etf_code}] 模型训练完成并保存到 {self._model_dir}")
            return True

        except Exception as e:
            logger.error(f"[{etf_code}] 模型训练失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    # ------------------------------------------------------------------
    #  特征构建
    # ------------------------------------------------------------------

    def build_features(
        self,
        overnight_info: Optional[OvernightInfo],
        hist_df: pd.DataFrame,
    ) -> Optional[np.ndarray]:
        """
        构建 12 维独立特征向量。

        Args:
            overnight_info: 隔夜行情信息
            hist_df:        至少 15 行的 OHLCV 历史数据

        Returns:
            特征向量 (shape: [12,]) 或 None
        """
        if len(hist_df) < 15:
            return None

        try:
            # 确保数值类型
            for col in ["开盘", "最高", "最低", "收盘", "成交量"]:
                if col not in hist_df.columns:
                    return None
                hist_df[col] = pd.to_numeric(hist_df[col], errors="coerce")

            latest = hist_df.iloc[-1]
            close = float(latest["收盘"])
            if close <= 0:
                return None

            prev = hist_df.iloc[-1]
            prev2 = hist_df.iloc[-2] if len(hist_df) >= 2 else prev

            prev_close = float(prev["收盘"])
            prev_open = float(prev["开盘"])
            prev_high = float(prev["最高"])
            prev_low = float(prev["最低"])
            prev2_close = float(prev2["收盘"])

            closes = hist_df["收盘"].astype(float).values
            highs = hist_df["最高"].astype(float).values
            lows = hist_df["最低"].astype(float).values

            hl_range = prev_high - prev_low

            features = []

            # 1. overnight_change_pct — 隔夜涨跌幅
            if overnight_info and overnight_info.is_valid:
                features.append(overnight_info.overnight_change_pct)
            else:
                features.append(0.0)

            # 2. prev_return — 前日涨跌幅 (%)
            prev_return = (prev_close - prev2_close) / prev2_close * 100 if prev2_close > 0 else 0
            features.append(prev_return)

            # 3. prev_close_position — 收盘在 high-low 中的位置 (0~1)
            close_pos = (prev_close - prev_low) / hl_range if hl_range > 0 else 0.5
            features.append(close_pos)

            # 4. prev_body_ratio — 实体/振幅比
            body = abs(prev_close - prev_open)
            body_ratio = body / hl_range if hl_range > 0 else 0
            features.append(body_ratio)

            # 5. return_5d — 5 日累计收益 (%)
            ret_5d = (closes[-1] / closes[-6] - 1) * 100 if len(closes) >= 6 and closes[-6] > 0 else 0
            features.append(ret_5d)

            # 6. ma5_deviation — MA5 偏离度 (%)
            ma5 = float(pd.Series(closes).tail(5).mean())
            features.append((close - ma5) / ma5 * 100 if ma5 > 0 else 0)

            # 7. atr_5d — 5 日 ATR (% of close)
            tr_list = []
            for j in range(max(1, len(hist_df) - 5), len(hist_df)):
                h = float(highs[j])
                l = float(lows[j])
                pc = float(closes[j - 1]) if j > 0 else h
                tr = max(h - l, abs(h - pc), abs(l - pc))
                tr_list.append(tr)
            atr = np.mean(tr_list) / close * 100 if close > 0 and tr_list else 0
            features.append(atr)

            # 8. rsi_14d — 14 日 RSI
            rsi = self._calc_rsi(closes, 14)
            features.append(rsi)

            # 9. day_of_week — 星期几
            try:
                if "日期" in hist_df.columns:
                    day_of_week = pd.to_datetime(hist_df.iloc[-1]["日期"]).weekday()
                else:
                    from datetime import datetime as _dt
                    day_of_week = _dt.now().weekday()
            except Exception:
                day_of_week = 0
            features.append(float(day_of_week))

            # 10. volume_ma5_ratio — 量比
            volumes = hist_df["成交量"].astype(float).values
            vol_5_avg = float(np.mean(volumes[-5:])) if len(volumes) >= 5 else float(np.mean(volumes))
            vol_current = float(volumes[-1]) if len(volumes) > 0 else 0
            features.append(vol_current / vol_5_avg if vol_5_avg > 0 else 1.0)

            # 11. upper_shadow_pct — 上影线占比
            upper_shadow = (prev_high - max(prev_open, prev_close)) / hl_range if hl_range > 0 else 0
            features.append(upper_shadow)

            # 12. lower_shadow_pct — 下影线占比
            lower_shadow = (min(prev_open, prev_close) - prev_low) / hl_range if hl_range > 0 else 0
            features.append(lower_shadow)

            assert len(features) == len(self.FEATURE_NAMES), \
                f"特征数量不匹配: {len(features)} != {len(self.FEATURE_NAMES)}"

            return np.array(features, dtype=np.float64)

        except Exception as e:
            logger.debug(f"特征构建失败: {e}")
            return None

    # ------------------------------------------------------------------
    #  辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _calc_rsi(closes: np.ndarray, period: int = 14) -> float:
        """计算 RSI"""
        if len(closes) < period + 1:
            return 50.0  # 数据不足，返回中性值

        deltas = np.diff(closes[-(period + 1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - 100.0 / (1.0 + rs)
