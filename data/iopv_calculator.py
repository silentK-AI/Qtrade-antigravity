"""
IOPV 获取与回退估算模块
"""
from loguru import logger


class IOPVCalculator:
    """
    IOPV（基金实时估值）获取器。

    主路径：直接使用 akshare fund_etf_spot_em 返回的 IOPV 字段。
    回退路径：关联指数点位 x 汇率 x 系数（每周校准一次）。
    """

    def __init__(self):
        # 回退估算系数表（etf_code -> coefficient）
        # 初始值为经验估值，运行中会根据真实 IOPV 数据自动校准
        self._coefficients: dict[str, float] = {
            "513180": 0.01,
            "159920": 0.01,
            "159941": 0.01,
            "513500": 0.01,
            "513400": 0.01,
            "513880": 0.0001,   # 日经指数数值较大，系数较小
            "513310": 0.01,
        }
        self._calibration_count: dict[str, int] = {}

    def get_iopv(
        self,
        etf_code: str,
        akshare_iopv: float,
        ref_index_price: float = 0.0,
        exchange_rate: float = 1.0,
    ) -> float:
        """
        获取 IOPV 值。

        优先使用 akshare 直接提供的 IOPV；
        如果 akshare IOPV 无效，则使用回退公式估算。

        Args:
            etf_code: ETF 代码
            akshare_iopv: akshare 返回的 IOPV 值
            ref_index_price: 关联指数/期货价格（回退用）
            exchange_rate: 对应币种兑人民币汇率（回退用）

        Returns:
            IOPV 估值
        """
        # 主路径：akshare 直接提供
        if akshare_iopv and akshare_iopv > 0:
            # 用真实 IOPV 校准回退系数
            if ref_index_price > 0 and exchange_rate > 0:
                self._calibrate(etf_code, akshare_iopv, ref_index_price, exchange_rate)
            return akshare_iopv

        # 回退路径：公式估算
        if ref_index_price > 0 and exchange_rate > 0:
            coeff = self._coefficients.get(etf_code, 0.01)
            estimated = ref_index_price * exchange_rate * coeff
            logger.warning(
                f"[{etf_code}] IOPV 使用回退估算: "
                f"指数={ref_index_price:.2f} x 汇率={exchange_rate:.4f} x "
                f"系数={coeff:.6f} = {estimated:.4f}"
            )
            return estimated

        logger.error(f"[{etf_code}] 无法获取 IOPV，所有数据源均不可用")
        return 0.0

    def _calibrate(
        self,
        etf_code: str,
        real_iopv: float,
        ref_index_price: float,
        exchange_rate: float,
    ) -> None:
        """根据真实 IOPV 校准回退公式的系数"""
        if ref_index_price * exchange_rate == 0:
            return

        new_coeff = real_iopv / (ref_index_price * exchange_rate)
        old_coeff = self._coefficients.get(etf_code, new_coeff)

        # 使用指数移动平均平滑系数更新
        count = self._calibration_count.get(etf_code, 0)
        if count == 0:
            self._coefficients[etf_code] = new_coeff
        else:
            alpha = 0.1  # 平滑因子
            self._coefficients[etf_code] = alpha * new_coeff + (1 - alpha) * old_coeff

        self._calibration_count[etf_code] = count + 1
