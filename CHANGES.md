# 代码修改总结 - 统一使用 CrewAI

## 已完成的修改

### 1. 所有智能体 (agents/)
- ✅ 使用 `from crewai import Agent, LLM` 而不是 LangChain
- ✅ 使用 `LLM(model=..., api_key=...)` 而不是 `ChatGoogleGenerativeAI`
- ✅ 所有智能体已统一修改：
  - `agents/data_collector_agent.py`
  - `agents/news_collector_agent.py`
  - `agents/analysis_agent.py`
  - `agents/evaluator_agent.py`

### 2. 所有工具 (tools/)
- ✅ 使用 `from crewai.tools import tool` 装饰器
- ✅ 使用 `@tool("工具名称")` 装饰器定义工具
- ✅ 所有工具已统一修改：
  - `tools/stock_data_tool.py` - `get_stock_history_tool_obj`
  - `tools/news_search_tool.py` - `search_stock_news_tool_obj`

### 3. 配置文件 (config.py)
- ✅ 设置 `GOOGLE_API_KEY` 环境变量供 LiteLLM 使用
- ✅ 模型名称格式：`gemini/gemini-pro`

### 4. 依赖包 (requirements.txt)
- ✅ 添加 `litellm>=1.0.0`（CrewAI 的 LLM 类需要）
- ✅ 移除了 `langchain-google-genai`（不再需要）
- ✅ 移除了 `google-generativeai`（不再需要）

## 关键修改点

### LLM 配置
```python
# 之前（错误）：
from langchain_google_genai import ChatGoogleGenerativeAI
llm = ChatGoogleGenerativeAI(model=..., google_api_key=...)

# 现在（正确）：
from crewai import LLM
llm = LLM(model="gemini/gemini-pro", api_key=..., temperature=...)
```

### 工具定义
```python
# 之前（错误）：
from langchain.tools import Tool
tool = Tool(name=..., description=..., func=...)

# 现在（正确）：
from crewai.tools import tool
@tool("工具名称")
def tool_func(...):
    ...
```

### 环境变量
```python
# config.py 中设置：
os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY
```

## 安装步骤

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 确保 litellm 已安装（CrewAI 的 LLM 类需要）：
```bash
pip install litellm
```

## 验证

运行以下命令验证配置：
```bash
python main.py --stock-code 000001
```

## 注意事项

1. **LiteLLM 必需**：CrewAI 的 LLM 类需要 LiteLLM 来支持 Gemini
2. **环境变量**：需要在 config.py 中设置 `GOOGLE_API_KEY`
3. **模型格式**：使用 `gemini/gemini-pro` 格式，不是 `gemini-pro`
4. **工具装饰器**：必须使用 `crewai.tools.tool` 装饰器

