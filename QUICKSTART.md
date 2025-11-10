# 快速开始指南

## 5分钟快速上手

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量（可选）

API密钥已在 `config.py` 中默认配置。如需修改，可创建 `.env` 文件：

```bash
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash
```

### 3. 运行示例

```bash
# 基本使用
python main.py --stock-code 000001

# 指定日期范围
python main.py --stock-code 000001 --start-date 20220101 --end-date 20231231

# 保存结果到文件
python main.py --stock-code 000001 --output result.json
```

## 常见股票代码

- `000001`: 平安银行
- `000002`: 万科A
- `600000`: 浦发银行
- `600036`: 招商银行
- `000858`: 五粮液

## 使用Python代码

```python
from crew.trading_crew import run_trading_analysis

# 基本使用
result = run_trading_analysis(stock_code="000001")

# 指定日期范围
result = run_trading_analysis(
    stock_code="000001",
    start_date="20220101",
    end_date="20231231"
)

# 查看结果
print(result["result"])
```

## 故障排除

### 问题1: 无法获取股票数据

**解决方案**:
- 检查网络连接
- 确认股票代码格式正确（6位数字）
- 检查akshare是否正常安装

### 问题2: API密钥错误

**解决方案**:
- API密钥已在 `config.py` 中默认配置
- 如需修改，确认 `.env` 文件中的 `GEMINI_API_KEY` 已正确设置
- 检查API密钥是否有效
- 确认账户有足够的API额度

### 问题3: 导入错误

**解决方案**:
- 确认所有依赖已安装：`pip install -r requirements.txt`
- 检查Python版本（建议3.8+）
- 确认项目目录结构完整

## 下一步

- 阅读 [README.md](README.md) 了解详细功能
- 查看 [ARCHITECTURE.md](ARCHITECTURE.md) 了解系统架构
- 运行 `example.py` 查看更多示例

