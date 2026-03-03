# ETF T+0 量化交易系统

跨境 ETF T+0 日内量化交易系统，覆盖 7 个跨境 ETF 标的，实现"隔夜研判 → 数据采集 → 信号计算 → 自动下单 → 风控管理"全流程自动化。

## 交易标的

| ETF | 名称 | 跟踪指数 | 关联期货 |
|-----|------|---------|---------|
| 513180 | 恒生科技ETF | 恒生科技指数 | HTI |
| 159920 | 恒生ETF | 恒生指数 | HSI |
| 159941 | 纳指ETF | 纳斯达克100 | NQ |
| 513500 | 标普500ETF | 标普500 | ES |
| 513400 | 道琼斯ETF | 道琼斯工业 | YM |
| 513880 | 日经ETF | 日经225 | NKD |
| 513310 | 中韩半导体ETF | 中韩半导体 | SOX |

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                       主程序 main.py                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ 数据采集  │ │ 策略引擎  │ │ 风控模块  │ │ 交易执行  │   │
│  │ data/    │→│ strategy/│→│ risk/    │→│ trader/  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐               │
│  │ 隔夜数据  │ │ 回测引擎  │ │ 通知监控  │               │
│  │overnight │ │ backtest/│ │ monitor/ │               │
│  └──────────┘ └──────────┘ └──────────┘               │
└─────────────────────────────────────────────────────────┘
```

### 核心策略

**关联期货/指数联动 + ETF 折溢价 + 隔夜行情增强**

- **买入信号**: 关联期货动量上涨 + ETF 折价 + 隔夜美股上涨加分
- **卖出信号**: 关联期货动量下跌 + ETF 溢价 + 隔夜美股下跌加分
- **隔夜增强**: 开盘前获取美股/港股隔夜走势，强信号可在开盘30分钟内独立触发

### 风控体系

| 规则 | 参数 |
|------|------|
| 止盈 | 0.8% |
| 止损 | 0.5% |
| 跟踪止损 | 回撤 0.3% |
| 每标的日交易上限 | 3 笔 |
| 单标的仓位上限 | 30% |
| 总仓位上限 | 80% |
| 强制平仓 | 14:50 |
| 禁止开仓 | 14:30 后 |

## 快速开始

### 安装

```bash
pip install -r requirements.txt
cp .env.example .env  # 按需修改配置
```

### 使用

```bash
# 模拟交易（全部标的）
python main.py paper

# 模拟单个标的
python main.py paper --etf 159941

# 自定义资金
python main.py paper --capital 200000

# 历史回测
python main.py backtest

# 实盘交易（需 Windows + miniQMT）
python main.py live
```

## 项目结构

```
Quati-Trade/
├── config/settings.py        # 全局配置（标的池、参数）
├── data/
│   ├── market_data.py        # 统一行情接口
│   ├── overnight_data.py     # 隔夜行情获取
│   ├── iopv_calculator.py    # IOPV 估值
│   └── data_cache.py         # 数据缓存
├── strategy/
│   ├── signal.py             # 数据类定义
│   ├── base_strategy.py      # 策略基类
│   └── futures_etf_arb.py    # 核心策略
├── risk/
│   ├── risk_manager.py       # 风控引擎
│   └── position_manager.py   # 持仓管理
├── trader/
│   ├── mock_trader.py        # 模拟交易
│   └── xtquant_trader.py     # miniQMT 实盘
├── backtest/
│   └── backtester.py         # 回测引擎
├── monitor/
│   ├── logger.py             # 结构化日志
│   └── notifier.py           # 微信/邮件通知
├── tests/                    # 单元测试
├── main.py                   # 主程序入口
└── legacy/                   # V0.1 旧代码
```

## 实盘部署（Phase 2）

1. Windows 云服务器安装 miniQMT
2. `pip install xtquant`
3. 配置 `.env` 中的 `XTQUANT_ACCOUNT` 和 `XTQUANT_PATH`
4. 运行 `python main.py live`

## 通知配置

- **微信推送**: 注册 [Server酱](https://sct.ftqq.com/)，将 Key 填入 `.env` 的 `SERVERCHAN_KEY`
- **邮件通知**: 配置 `.env` 中的 SMTP 参数
