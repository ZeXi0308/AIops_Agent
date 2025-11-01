# MCP Multi-Server Orchestration Implementation

## 概述 / Overview

本项目实现了MCP多服务器编排功能，支持在单个查询中先后调用多个不同的MCP服务器，并自动处理数据流转。

This project implements MCP multi-server orchestration, supporting sequential calls to different MCP servers within a single query with automatic data flow management.

## 核心特性 / Core Features

✅ **自动检测和执行 / Automatic Detection & Execution**
- 自动识别需要多个MCP服务器的查询
- 无需手动配置任务序列

✅ **数据流管理 / Data Flow Management**
- 自动在MCP服务器之间传递数据
- 智能数据格式转换

✅ **灵活扩展 / Flexible Extension**
- 易于添加新的编排模式
- 支持自定义MCP服务器集成

✅ **错误处理 / Error Handling**
- 优雅的故障恢复
- 部分结果返回

## 目录结构 / Directory Structure

```
AIops_Agent/
├── Router/
│   ├── mcp_orchestrator.py              # 核心编排引擎
│   ├── mcp_orchestration_integration.py # 集成指南和示例
│   └── main.py                          # 主应用 (需要集成)
├── examples/
│   └── orchestration_example.py         # 完整使用示例
├── tests/
│   └── test_orchestration.py            # 单元测试
├── docs/
│   └── MCP_Multi_Server_Orchestration_Guide.md  # 详细文档
└── MCP_Orchestration_README.md          # 本文件
```

## 快速开始 / Quick Start

### 1. 查看示例 / View Examples

```bash
# 运行完整示例，查看架构和用法
python examples/orchestration_example.py
```

输出包括：
- 架构图
- 6个详细使用示例
- 扩展指南

### 2. 运行测试 / Run Tests

```bash
# 运行单元测试
python tests/test_orchestration.py

# 或使用 pytest
pytest tests/test_orchestration.py -v
```

### 3. 集成到主应用 / Integrate into Main App

在 `Router/main.py` 的 `startup_event()` 中：

```python
from mcp_orchestrator import detect_and_orchestrate, is_orchestration_query

async def startup_event():
    # ... existing code ...
    mcp_tools = await fault_tolerant_client.get_tools()
    all_tools = list(mcp_tools)

    async def info_node(state: State) -> State | Command:
        # ... existing code ...

        # 在 LLM 调用前添加编排检测
        human_msgs = [m for m in state["messages"] if isinstance(m, HumanMessage)]
        if human_msgs:
            latest_query = human_msgs[-1].content

            # 检测并执行编排
            if is_orchestration_query(latest_query):
                orchestration_result = await detect_and_orchestrate(
                    query=latest_query,
                    available_tools=all_tools,
                    llm=llm
                )

                if orchestration_result:
                    formatted_output = orchestration_result["formatted_output"]
                    return {
                        "messages": state["messages"] + [AIMessage(content=formatted_output)],
                        "AI_Response": formatted_output,
                        "Thinking": state.get("Thinking", "") + "\n🎭 Orchestration executed",
                        # ... other state fields
                    }

        # ... 继续正常的 LLM 流程 ...
```

## 使用示例 / Usage Examples

### 示例 1: JIRA + 图表 / Example 1: JIRA + Chart

**用户查询:**
```
"Show me open S65 JIRA issues from 2025 and create a pie chart"
"显示2025年S65的开放JIRA问题并创建饼图"
```

**执行流程:**
```
1. 检测编排模式: JIRA + Chart ✓
2. 任务分解:
   - Task 1: query_jira_issues(component="S65", status="Open", year="2025")
   - Task 2: generate_pie_chart(data from Task 1)
3. 执行:
   - 调用 JIRA MCP (Port 8004) → 获取15个问题
   - 数据转换: JIRA结果 → Chart格式
   - 调用 Chart MCP (Port 8005) → 生成饼图
4. 返回:
   - JIRA详细报告
   - 饼图可视化
```

### 示例 2: 统计 + 可视化 / Example 2: Statistics + Visualization

**用户查询:**
```
"Get JIRA statistics for S12 component and visualize with bar chart"
"获取S12组件的JIRA统计并用柱状图展示"
```

**执行流程:**
```
1. 调用 get_issue_statistics(component="S12")
2. 提取统计数据 (by_status, by_vendor)
3. 转换为图表格式
4. 调用 generate_bar_chart
5. 返回统计报告 + 柱状图
```

## 支持的编排模式 / Supported Orchestration Patterns

### 模式 1: 数据检索 + 可视化
**关键词:** jira/issue/bug + chart/graph/visualize

### 模式 2: 统计分析 + 展示
**关键词:** statistics/stats + visualize/show/display

### 模式 3: 自定义模式 (可扩展)
参见文档了解如何添加新模式

## 核心组件 / Core Components

### MCPOrchestrator 类

主要编排器，包含以下关键方法：

```python
class MCPOrchestrator:
    def parse_orchestration_query(query: str) -> List[Dict]
        # 解析查询，生成任务列表

    async def execute_orchestration(tasks: List[Dict]) -> Dict
        # 执行任务序列

    def _transform_data_for_chart(source_data: Any) -> List[Dict]
        # 数据格式转换

    def format_orchestration_result(results: Dict) -> str
        # 格式化输出
```

### 工具函数

```python
def is_orchestration_query(query: str) -> bool
    # 快速检测是否需要编排

async def detect_and_orchestrate(query: str, available_tools: List, llm=None) -> Dict
    # 检测并执行编排的一站式函数
```

## 数据流示例 / Data Flow Example

### JIRA → Chart 数据转换

**输入 (JIRA MCP 输出):**
```json
{
  "success": true,
  "statistics": {
    "by_status": {
      "Open": 10,
      "Closed": 12,
      "In Progress": 3
    }
  }
}
```

**转换过程:**
```python
def _transform_data_for_chart(jira_output):
    # 提取 by_status
    # 转换为 chart 格式
    return [
        {"category": "Open", "value": 10},
        {"category": "Closed", "value": 12},
        {"category": "In Progress", "value": 3}
    ]
```

**输出 (Chart MCP 输入):**
```json
[
  {"category": "Open", "value": 10},
  {"category": "Closed", "value": 12},
  {"category": "In Progress", "value": 3}
]
```

## 扩展指南 / Extension Guide

### 添加新的编排模式

1. **在 `parse_orchestration_query()` 中添加模式检测:**
```python
if "your_pattern" in query_lower:
    tasks.append({
        "tool_name": "your_tool",
        "parameters": {...},
        "output_key": "your_data"
    })
```

2. **添加数据转换逻辑 (如需要):**
```python
def _transform_data_for_chart(self, source_data):
    if "your_data_format" in source_data:
        return transform_your_data(source_data)
```

3. **更新检测函数:**
```python
def is_orchestration_query(query: str) -> bool:
    patterns = [
        # ... existing patterns
        (["your_keywords"], ["action_keywords"])
    ]
```

### 添加新的MCP服务器

1. **注册工具类别:**
```python
self.tool_categories = {
    "your_category": ["your_tool_name"]
}
```

2. **在 `MCP_Client.py` 中添加配置:**
```python
config = {
    "YourMCP": {
        "url": "http://localhost:PORT/mcp/",
        "transport": "streamable_http"
    }
}
```

3. **实现编排逻辑和数据转换**

## 测试 / Testing

### 运行所有测试

```bash
# 基本测试
python tests/test_orchestration.py

# 使用 pytest (详细输出)
pytest tests/test_orchestration.py -v

# 运行特定测试类
pytest tests/test_orchestration.py::TestOrchestrationDetection -v

# 运行集成测试 (需要MCP服务器运行)
pytest tests/test_orchestration.py -m integration
```

### 测试覆盖

- ✅ 编排检测
- ✅ 查询解析
- ✅ 参数提取
- ✅ 图表类型选择
- ✅ 数据转换
- ✅ 依赖解析
- ✅ 结果格式化
- ✅ 工具分类
- ⏸️ 异步执行 (需要mock改进)
- ⏸️ 集成测试 (需要运行的MCP服务器)

## 架构图 / Architecture Diagram

```
User Query
    ↓
┌─────────────────────────┐
│ Orchestration Detection │
│ (is_orchestration_query)│
└────────────┬────────────┘
             ↓
┌─────────────────────────┐
│    Query Parsing        │
│(parse_orchestration_...)│
└────────────┬────────────┘
             ↓
┌─────────────────────────────────────┐
│      Task Execution                 │
│  ┌──────────────────────────────┐  │
│  │ Step 1: JIRA MCP (8004)     │  │
│  │ → query_jira_issues         │  │
│  │ → Output: JIRA data         │  │
│  └──────────┬───────────────────┘  │
│             ↓                       │
│  ┌──────────────────────────────┐  │
│  │ Data Transformation          │  │
│  │ → _transform_data_for_chart │  │
│  │ → Output: Chart format      │  │
│  └──────────┬───────────────────┘  │
│             ↓                       │
│  ┌──────────────────────────────┐  │
│  │ Step 2: Chart MCP (8005)    │  │
│  │ → generate_pie_chart        │  │
│  │ → Output: Chart URL         │  │
│  └──────────────────────────────┘  │
└─────────────────────────────────────┘
             ↓
┌─────────────────────────┐
│   Result Formatting     │
│ (format_orchestration_) │
└────────────┬────────────┘
             ↓
    Combined Output
    (JIRA Report + Chart)
```

## 性能考虑 / Performance Considerations

### 当前实现
- 串行执行 (Sequential execution)
- 适合有依赖关系的任务

### 未来优化
- 并行执行独立任务
- 结果缓存
- 超时控制

## 故障排查 / Troubleshooting

### 问题: 编排未触发

**检查:**
```python
query = "Your query here"
print(f"Is orchestration: {is_orchestration_query(query)}")
```

**解决:** 调整关键词模式匹配

### 问题: 数据转换失败

**检查:**
```python
# 打印中间数据
print(f"JIRA output: {jira_result}")
print(f"Chart input: {transform_data(jira_result)}")
```

**解决:** 更新 `_transform_data_for_chart()` 逻辑

### 问题: MCP服务连接失败

**检查:**
```bash
curl http://localhost:8004/mcp/
curl http://localhost:8005/mcp/
```

**解决:** 确保所有MCP服务器运行

## 文档 / Documentation

- 📘 **完整指南:** `docs/MCP_Multi_Server_Orchestration_Guide.md`
- 📝 **集成示例:** `Router/mcp_orchestration_integration.py`
- 🎯 **使用示例:** `examples/orchestration_example.py`
- 🧪 **测试代码:** `tests/test_orchestration.py`

## 贡献 / Contributing

欢迎贡献新的编排模式、数据转换逻辑和测试用例！

### 添加新模式的步骤:
1. 在 `mcp_orchestrator.py` 中实现模式检测
2. 添加数据转换逻辑
3. 编写测试用例
4. 更新文档

## 版本历史 / Version History

### v1.0 (2025-11-01)
- ✅ 核心编排引擎
- ✅ JIRA + Chart 模式
- ✅ Statistics + Visualization 模式
- ✅ 数据转换框架
- ✅ 单元测试
- ✅ 完整文档

## 许可 / License

MIT License

## 联系 / Contact

有问题或建议？请创建 Issue 或 Pull Request。

---

**开始使用 / Get Started:**
```bash
# 1. 查看示例
python examples/orchestration_example.py

# 2. 运行测试
python tests/test_orchestration.py

# 3. 阅读文档
cat docs/MCP_Multi_Server_Orchestration_Guide.md

# 4. 集成到你的应用
# 参考 Router/mcp_orchestration_integration.py
```

**祝使用愉快！ / Happy Orchestrating! 🎭**
