"""
XGBoost 模型训练脚本

用法:
  python scripts/train_model.py --all              # 训练所有标的
  python scripts/train_model.py --etf 159941       # 训练单个标的
  python scripts/train_model.py --etf 159941 --days 180  # 指定训练天数
  python main.py train                             # 通过主程序入口训练
"""
import sys
import os
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from loguru import logger

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import ETF_UNIVERSE, ACTIVE_ETFS, ML_MODEL_DIR, ML_TRAINING_DAYS
from strategy.ml_predictor import MLPredictor


def fetch_training_data(etf_code: str, days: int = 180):
    """获取历史训练数据 (使用新浪 API，更稳定)"""
    import requests
    import pandas as pd
    import json

    # 新浪 API 符号格式
    exchange = ETF_UNIVERSE.get(etf_code, {}).get("exchange", "SH").lower()
    symbol = f"{exchange}{etf_code}"
    
    # 获取日线数据 (scale=240)
    api_url = (
        f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen={days}"
    )

    logger.info(f"[{etf_code}] 获取历史数据 (Sina): {symbol}, 最近 {days} 天")

    try:
        s = requests.Session()
        s.trust_env = False
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn"
        }
        
        resp = s.get(api_url, headers=headers, timeout=15)
        text = resp.text.strip()
        
        if not text or text == "null":
            logger.warning(f"[{etf_code}] 新浪 API 无数据记录")
            return None
            
        # 新浪返回的是标准 JSON 列表
        data_list = json.loads(text)
        if not data_list:
            return None
            
        df = pd.DataFrame(data_list)
        
        # 字段映射
        df = df.rename(columns={
            "day": "日期",
            "open": "开盘",
            "high": "最高",
            "low": "最低",
            "close": "收盘",
            "volume": "成交量"
        })
        
        # 转换数值类型
        df["日期"] = pd.to_datetime(df["日期"])
        for col in ["开盘", "最高", "最低", "收盘", "成交量"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            
        # 补全成交额 (模拟，新浪日线 JSON 没带成交额)
        if "amount" not in df.columns:
            df["成交额"] = df["成交量"] * df["收盘"]
            
        df = df.sort_values("日期").reset_index(drop=True)
        logger.info(f"[{etf_code}] 获取到 {len(df)} 条历史数据")
        return df

    except Exception as e:
        logger.error(f"[{etf_code}] 新浪 API 获取历史数据失败: {e}")
        return None


def run_training(
    etf_codes: list[str] = None,
    days: int = ML_TRAINING_DAYS,
):
    """执行模型训练"""
    codes = etf_codes or ACTIVE_ETFS
    predictor = MLPredictor(model_dir=ML_MODEL_DIR)

    success_count = 0
    fail_count = 0

    logger.info("=" * 60)
    logger.info("XGBoost 模型训练")
    logger.info(f"标的: {', '.join(codes)}")
    logger.info(f"训练天数: {days}")
    logger.info(f"模型目录: {ML_MODEL_DIR}")
    logger.info("=" * 60)

    for code in codes:
        if code not in ETF_UNIVERSE:
            logger.warning(f"[{code}] 未知标的，跳过")
            fail_count += 1
            continue

        name = ETF_UNIVERSE[code]["name"]
        logger.info(f"\n{'='*40}")
        logger.info(f"训练 [{code}] {name}")
        logger.info(f"{'='*40}")

        # 获取数据
        hist_df = fetch_training_data(code, days=days)
        if hist_df is None or len(hist_df) < 30:
            logger.warning(f"[{code}] 数据不足，跳过训练")
            fail_count += 1
            continue

        # 训练
        ok = predictor.train(code, hist_df, overnight_series=None)
        if ok:
            success_count += 1
            logger.info(f"[{code}] ✅ 训练成功")
        else:
            fail_count += 1
            logger.warning(f"[{code}] ❌ 训练失败")

    logger.info("\n" + "=" * 60)
    logger.info(f"训练完成: {success_count} 成功, {fail_count} 失败")
    logger.info(f"模型保存在: {Path(ML_MODEL_DIR).resolve()}")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="XGBoost 价格预测模型训练",
    )
    parser.add_argument(
        "--etf", nargs="+", default=None,
        help="指定训练标的（ETF代码），不指定则训练全部",
    )
    parser.add_argument(
        "--days", type=int, default=ML_TRAINING_DAYS,
        help=f"训练数据天数（默认 {ML_TRAINING_DAYS}）",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="训练所有标的",
    )

    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="INFO")

    codes = args.etf
    if args.all or codes is None:
        codes = ACTIVE_ETFS

    run_training(etf_codes=codes, days=args.days)


if __name__ == "__main__":
    main()
