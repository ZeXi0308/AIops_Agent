# MCP Multi-Server Orchestration Guide

## 概述 / Overview

本文档介绍如何实现和使用MCP多服务器编排功能，允许在一个查询中先后调用多个不同的MCP服务器。

This guide explains how to implement and use MCP multi-server orchestration, allowing sequential calls to different MCP servers within a single query.

## 核心概念 / Core Concepts

### 什么是MCP编排？ / What is MCP Orchestration?

MCP编排是一种自动化机制，能够：
- 检测需要多步骤处理的用户查询
- 自动分解为多个子任务
- 按顺序调用不同的MCP服务器
- 在工具之间传递数据
- 合并结果返回给用户

MCP Orchestration is an automation mechanism that:
- Detects user queries requiring multi-step processing
- Automatically breaks down into sub-tasks
- Sequentially calls different MCP servers
- Passes data between tools
- Combines results for user output

### 典型场景 / Typical Use Cases

1. **数据检索 + 可视化 / Data Retrieval + Visualization**
   - 查询JIRA问题，然后创建图表
   - Query JIRA issues, then create charts

2. **统计分析 + 展示 / Statistical Analysis + Display**
   - 获取统计数据，然后可视化
   - Get statistics, then visualize

3. **多数据源整合 / Multi-Source Integration**
   - 从多个MCP服务器获取数据并整合
   - Fetch and integrate data from multiple MCP servers

## 架构设计 / Architecture Design

### 组件结构 / Component Structure

```
Router/
├── mcp_orchestrator.py              # 核心编排引擎
├── mcp_orchestration_integration.py # 集成指南
└── main.py                          # 主应用（需要集成编排功能）

examples/
└── orchestration_example.py         # 使用示例
```

### 核心类 / Core Classes

#### MCPOrchestrator

主要编排器类，负责：
- 查询解析
- 任务规划
- 工具执行
- 数据转换
- 结果格式化

Main orchestrator class responsible for:
- Query parsing
- Task planning
- Tool execution
- Data transformation
- Result formatting

**主要方法 / Key Methods:**

```python
class MCPOrchestrator:
    def parse_orchestration_query(query: str) -> List[Dict[str, Any]]
        # 解析查询，返回任务列表
        # Parse query, return task list

    async def execute_orchestration(tasks: List[Dict], llm=None) -> Dict
        # 执行任务序列
        # Execute task sequence

    def _transform_data_for_chart(source_data: Any) -> List[Dict]
        # 转换数据格式
        # Transform data format

    def format_orchestration_result(results: Dict) -> str
        # 格式化输出
        # Format output
```

## 使用方法 / Usage

### 1. 基本集成 / Basic Integration

在 `main.py` 的 `info_node` 中添加编排检测：

Add orchestration detection in `info_node` of `main.py`:

```python
from mcp_orchestrator import detect_and_orchestrate, is_orchestration_query

async def info_node(state: State) -> State | Command:
    # Get latest user message
    human_msgs = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    if human_msgs:
        latest_query = human_msgs[-1].content

        # Check if orchestration is needed
        if is_orchestration_query(latest_query):
            # Execute orchestration
            orchestration_result = await detect_and_orchestrate(
                query=latest_query,
                available_tools=all_tools,
                llm=llm
            )

            if orchestration_result:
                # Return orchestration result
                formatted_output = orchestration_result["formatted_output"]
                state["AI_Response"] = formatted_output

                return {
                    "messages": state["messages"] + [AIMessage(content=formatted_output)],
                    "AI_Response": formatted_output,
                    "Thinking": state.get("Thinking", "") + "\n🎭 Orchestration executed",
                    "subgraph": state.get("subgraph", "false"),
                    "tool_images": state.get("tool_images", [])
                }

    # Continue with normal LLM flow
    response = await llm_with_tools.ainvoke(state["messages"])
    # ... rest of code
```

### 2. 支持的查询模式 / Supported Query Patterns

#### 模式1: JIRA + 图表 / Pattern 1: JIRA + Chart

**查询示例 / Query Examples:**
```
- "Show me open S65 JIRA issues and create a pie chart"
- "显示S65的开放JIRA问题并创建饼图"
- "Get JIRA issues for S12 component and visualize them"
- "获取S12组件的JIRA问题并可视化"
```

**执行流程 / Execution Flow:**
```
1. Call query_jira_issues(component="S65", status="Open")
2. Transform JIRA results → chart data format
3. Call generate_pie_chart(data=[...], title="JIRA Issues")
4. Return combined results
```

#### 模式2: 统计 + 可视化 / Pattern 2: Statistics + Visualization

**查询示例 / Query Examples:**
```
- "Get JIRA statistics and visualize with bar chart"
- "获取JIRA统计数据并用柱状图展示"
- "Show me issue statistics and create a chart"
- "显示问题统计并创建图表"
```

**执行流程 / Execution Flow:**
```
1. Call get_issue_statistics(component="S12")
2. Extract status/vendor counts
3. Call generate_column_chart(data=[...])
4. Return statistics report + chart
```

### 3. 数据转换 / Data Transformation

#### JIRA → Chart 数据转换 / Data Transformation

**输入 (JIRA输出) / Input (JIRA Output):**
```json
{
  "statistics": {
    "by_status": {
      "Open": 10,
      "Closed": 12,
      "In Progress": 3
    }
  }
}
```

**输出 (Chart输入) / Output (Chart Input):**
```json
[
  {"category": "Open", "value": 10},
  {"category": "Closed", "value": 12},
  {"category": "In Progress", "value": 3}
]
```

**转换函数 / Transformation Function:**
```python
def _transform_data_for_chart(self, source_data: Any) -> List[Dict[str, Any]]:
    if isinstance(source_data, dict):
        if "statistics" in source_data:
            stats = source_data["statistics"]
            if "by_status" in stats:
                return [
                    {"category": status, "value": count}
                    for status, count in stats["by_status"].items()
                ]
    return []
```

## 扩展功能 / Extension

### 添加新的编排模式 / Adding New Orchestration Patterns

#### 步骤 / Steps:

1. **在 `parse_orchestration_query()` 中添加检测逻辑 / Add detection logic in `parse_orchestration_query()`**

```python
def parse_orchestration_query(self, query: str) -> List[Dict[str, Any]]:
    tasks = []
    query_lower = query.lower()

    # 新模式: 设备信息 + 趋势图
    # New pattern: Device info + Trend chart
    if "device" in query_lower and "trend" in query_lower:
        # 第一步: 获取设备信息
        # Step 1: Get device info
        device_task = {
            "tool_name": "DU_Name_IP_Mapping",
            "parameters": {},
            "output_key": "device_data"
        }
        tasks.append(device_task)

        # 第二步: 创建趋势图
        # Step 2: Create trend chart
        chart_task = {
            "tool_name": "generate_line_chart",
            "parameters": {
                "data_source": "device_data",
                "title": "Device Trend"
            },
            "output_key": "chart_result",
            "depends_on": ["device_data"]
        }
        tasks.append(chart_task)

    return tasks
```

2. **添加数据转换逻辑 / Add data transformation logic**

```python
def _transform_data_for_chart(self, source_data: Any) -> List[Dict[str, Any]]:
    # 添加新的数据格式处理
    # Add new data format handling
    if isinstance(source_data, dict) and "devices" in source_data:
        # 转换设备数据为图表格式
        # Transform device data to chart format
        return [
            {"time": device["timestamp"], "value": device["metric"]}
            for device in source_data["devices"]
        ]

    # ... existing transformation logic
```

3. **更新检测函数 / Update detection function**

```python
def is_orchestration_query(query: str) -> bool:
    query_lower = query.lower()

    patterns = [
        # 现有模式 / Existing patterns
        (["jira", "issue"], ["chart", "graph"]),
        (["statistics"], ["visualize"]),

        # 新模式 / New pattern
        (["device"], ["trend", "chart"])
    ]

    for data_keywords, action_keywords in patterns:
        has_data = any(kw in query_lower for kw in data_keywords)
        has_action = any(kw in query_lower for kw in action_keywords)
        if has_data and has_action:
            return True

    return False
```

### 添加新的MCP服务器 / Adding New MCP Servers

#### 步骤 / Steps:

1. **注册工具类别 / Register tool category**

```python
self.tool_categories = {
    "data_retrieval": [
        "query_jira_issues",
        "your_new_retrieval_tool"
    ],
    "processing": [
        "your_processing_tool"
    ],
    "visualization": [
        "generate_pie_chart",
        "your_visualization_tool"
    ]
}
```

2. **在编排逻辑中添加工具 / Add tool in orchestration logic**

3. **实现数据转换 / Implement data transformation**

## 测试 / Testing

### 运行示例 / Run Examples

```bash
# 运行完整示例
# Run complete examples
python examples/orchestration_example.py

# 输出将展示:
# Output will show:
# - 架构图
# - 6个详细示例
# - 使用说明
# - Architecture diagram
# - 6 detailed examples
# - Usage instructions
```

### 单元测试 / Unit Tests

创建测试文件 / Create test file:

```python
# tests/test_orchestration.py
import pytest
from Router.mcp_orchestrator import MCPOrchestrator, is_orchestration_query

def test_orchestration_detection():
    # 应该检测到的查询
    # Queries that should be detected
    assert is_orchestration_query("Show JIRA issues and create chart")
    assert is_orchestration_query("Get statistics and visualize")

    # 不应该检测到的查询
    # Queries that should NOT be detected
    assert not is_orchestration_query("What is JIRA?")
    assert not is_orchestration_query("Create a chart")

def test_query_parsing():
    orchestrator = MCPOrchestrator([])
    query = "Show open S65 JIRA issues and create pie chart"

    tasks = orchestrator.parse_orchestration_query(query)

    assert len(tasks) == 2
    assert tasks[0]["tool_name"] == "query_jira_issues"
    assert tasks[1]["tool_name"] == "generate_pie_chart"
    assert "S65" in str(tasks[0]["parameters"])

def test_data_transformation():
    orchestrator = MCPOrchestrator([])

    jira_data = {
        "statistics": {
            "by_status": {
                "Open": 10,
                "Closed": 5
            }
        }
    }

    chart_data = orchestrator._transform_data_for_chart(jira_data)

    assert len(chart_data) == 2
    assert chart_data[0]["category"] == "Open"
    assert chart_data[0]["value"] == 10
```

运行测试 / Run tests:
```bash
pytest tests/test_orchestration.py -v
```

## 实际应用示例 / Real-World Examples

### 示例1: JIRA问题分析 / Example 1: JIRA Issue Analysis

**用户查询 / User Query:**
```
"显示2025年S65组件的开放问题，并创建一个饼图展示问题分布"
"Show open issues for S65 component in 2025 and create a pie chart showing distribution"
```

**系统处理 / System Processing:**

1. **解析查询 / Parse Query**
   - 识别组件: S65
   - 识别状态: Open
   - 识别年份: 2025
   - 识别操作: 查询 + 可视化

2. **任务规划 / Task Planning**
   ```
   Task 1: query_jira_issues(component="S65", status="Open", year="2025")
   Task 2: generate_pie_chart(data from Task 1)
   ```

3. **执行 / Execution**
   - 调用JIRA MCP (Port 8004)
   - 获取15个问题
   - 转换数据格式
   - 调用Chart MCP (Port 8005)
   - 生成饼图

4. **输出 / Output**
   ```
   🎭 Multi-MCP Orchestration Results
   =========================================

   📊 jira_data:
   JIRA Query Results: 15 issues found
   [详细的JIRA报告]

   📊 chart_result:
   Chart generated successfully
   Chart URL: http://localhost:3000/chart/abc123
   ```

### 示例2: 问题趋势分析 / Example 2: Issue Trend Analysis

**用户查询 / User Query:**
```
"获取S12组件最近30天的问题统计，并用柱状图显示各状态的数量"
"Get issue statistics for S12 component in last 30 days and show counts by status with bar chart"
```

**执行流程 / Execution Flow:**
```
1. get_issue_statistics(component="S12", days_updated=30)
   └─ Returns: {total: 25, by_status: {Open: 10, Closed: 12, InProgress: 3}}

2. Transform: Extract by_status → chart format
   └─ [{category: "Open", value: 10}, ...]

3. generate_bar_chart(data=[...], title="S12 Issue Statistics")
   └─ Returns: Chart URL

4. Combine: Statistics report + Bar chart
```

## 错误处理 / Error Handling

### 常见错误场景 / Common Error Scenarios

#### 1. MCP服务不可用 / MCP Service Unavailable

```python
# 场景: Chart MCP服务未启动
# Scenario: Chart MCP service not running

Result:
{
    "jira_data": { "success": True, ... },
    "chart_result": { "error": "Chart service unavailable" }
}

# 系统返回部分结果
# System returns partial results
```

#### 2. 数据转换失败 / Data Transformation Failed

```python
# 场景: JIRA返回意外格式
# Scenario: JIRA returns unexpected format

try:
    chart_data = transform_data(jira_result)
except Exception as e:
    logger.error(f"Transformation failed: {e}")
    # 使用默认格式或跳过图表
    # Use default format or skip chart
```

#### 3. 工具不存在 / Tool Not Found

```python
# 场景: 请求的工具未注册
# Scenario: Requested tool not registered

if tool_name not in self.tool_map:
    return {"error": f"Tool {tool_name} not available"}
```

### 错误恢复策略 / Error Recovery Strategies

```python
# 在 execute_orchestration() 中
# In execute_orchestration()

for task in tasks:
    try:
        result = await execute_tool(task)
        results[task["output_key"]] = result
    except Exception as e:
        results[task["output_key"]] = {"error": str(e)}

        # 检查是否为关键任务
        # Check if critical task
        if task.get("critical", True):
            break  # 停止执行 / Stop execution
        else:
            continue  # 继续下一个任务 / Continue to next task
```

## 性能优化 / Performance Optimization

### 并行执行 / Parallel Execution

对于独立的任务，可以并行执行：

For independent tasks, execute in parallel:

```python
async def execute_orchestration_parallel(self, tasks):
    independent_tasks = [t for t in tasks if not t.get("depends_on")]
    dependent_tasks = [t for t in tasks if t.get("depends_on")]

    # 并行执行独立任务
    # Execute independent tasks in parallel
    independent_results = await asyncio.gather(*[
        self._execute_task(task) for task in independent_tasks
    ])

    # 串行执行依赖任务
    # Execute dependent tasks serially
    for task in dependent_tasks:
        result = await self._execute_task(task, independent_results)
```

### 缓存结果 / Result Caching

```python
from functools import lru_cache
import hashlib

class MCPOrchestrator:
    def __init__(self, available_tools):
        self.result_cache = {}

    async def execute_with_cache(self, task):
        # 生成缓存键
        # Generate cache key
        cache_key = hashlib.md5(
            json.dumps(task, sort_keys=True).encode()
        ).hexdigest()

        if cache_key in self.result_cache:
            return self.result_cache[cache_key]

        result = await self._execute_task(task)
        self.result_cache[cache_key] = result
        return result
```

## 最佳实践 / Best Practices

### 1. 查询设计 / Query Design

✅ **好的查询 / Good Queries:**
```
- "Show S65 open issues and create pie chart"
- "Get JIRA statistics for S12 and visualize"
```

❌ **不好的查询 / Bad Queries:**
```
- "Show issues" (太模糊 / Too vague)
- "Create a chart" (缺少数据源 / Missing data source)
```

### 2. 任务定义 / Task Definition

```python
# 清晰的任务定义 / Clear task definition
{
    "tool_name": "query_jira_issues",  # 明确的工具名 / Clear tool name
    "parameters": {                     # 完整的参数 / Complete parameters
        "component": "S65",
        "status": "Open"
    },
    "output_key": "jira_data",         # 描述性的输出键 / Descriptive output key
    "depends_on": [],                   # 明确的依赖 / Clear dependencies
    "critical": True                    # 明确的重要性 / Clear criticality
}
```

### 3. 错误处理 / Error Handling

```python
# 在每个关键点添加日志
# Add logging at every critical point
logger.info(f"Executing task: {task['tool_name']}")

try:
    result = await tool.ainvoke(parameters)
    logger.info(f"Task completed: {task['tool_name']}")
except Exception as e:
    logger.error(f"Task failed: {task['tool_name']}, Error: {e}")
    # 提供有用的错误信息
    # Provide helpful error message
    return {"error": f"Failed to execute {task['tool_name']}: {str(e)}"}
```

### 4. 数据验证 / Data Validation

```python
def _validate_chart_data(self, data: List[Dict]) -> bool:
    """验证图表数据格式 / Validate chart data format"""
    if not data:
        return False

    for item in data:
        if not isinstance(item, dict):
            return False
        if "category" not in item or "value" not in item:
            return False

    return True

# 使用验证 / Use validation
chart_data = self._transform_data_for_chart(source_data)
if not self._validate_chart_data(chart_data):
    logger.warning("Invalid chart data format")
    return default_data
```

## 故障排查 / Troubleshooting

### 问题1: 编排未触发 / Issue 1: Orchestration Not Triggered

**症状 / Symptoms:**
- 查询应该触发编排但没有

**检查 / Check:**
```python
# 测试检测函数
# Test detection function
query = "Show JIRA issues and create chart"
print(f"Is orchestration query: {is_orchestration_query(query)}")

# 检查模式匹配
# Check pattern matching
patterns = ["jira", "issue", "chart", "graph"]
for pattern in patterns:
    print(f"{pattern} in query: {pattern in query.lower()}")
```

**解决 / Solution:**
- 调整 `is_orchestration_query()` 中的模式
- 添加更多关键词

### 问题2: 数据转换失败 / Issue 2: Data Transformation Failed

**症状 / Symptoms:**
- Chart MCP收到无效数据

**检查 / Check:**
```python
# 打印中间数据
# Print intermediate data
jira_result = await jira_tool.ainvoke(params)
print(f"JIRA result structure: {json.dumps(jira_result, indent=2)}")

chart_data = transform_data(jira_result)
print(f"Chart data: {chart_data}")
```

**解决 / Solution:**
- 检查 `_transform_data_for_chart()` 逻辑
- 添加对新数据格式的支持

### 问题3: MCP服务连接失败 / Issue 3: MCP Service Connection Failed

**症状 / Symptoms:**
- 工具调用超时或失败

**检查 / Check:**
```bash
# 检查MCP服务状态
# Check MCP service status
curl http://localhost:8004/mcp/
curl http://localhost:8005/mcp/

# 检查日志
# Check logs
tail -f Router/chart_server.log
```

**解决 / Solution:**
- 确保所有MCP服务器都在运行
- 检查端口配置
- 查看服务日志

## 总结 / Summary

MCP多服务器编排功能提供了：

The MCP multi-server orchestration feature provides:

✅ **自动化 / Automation**
- 自动检测多步骤查询
- 自动任务分解和执行

✅ **灵活性 / Flexibility**
- 支持任意MCP服务器组合
- 可扩展的模式匹配

✅ **数据流 / Data Flow**
- 工具间无缝数据传递
- 自动格式转换

✅ **错误处理 / Error Handling**
- 优雅的失败处理
- 部分结果返回

## 相关资源 / Related Resources

- 核心代码: `Router/mcp_orchestrator.py`
- 集成指南: `Router/mcp_orchestration_integration.py`
- 使用示例: `examples/orchestration_example.py`
- 测试脚本: `tests/test_orchestration.py`

## 下一步 / Next Steps

1. ✅ 阅读本文档 / Read this documentation
2. ✅ 运行示例代码 / Run example code
3. ✅ 集成到main.py / Integrate into main.py
4. ✅ 测试现有场景 / Test existing scenarios
5. ✅ 添加自定义模式 / Add custom patterns
6. ✅ 扩展新的MCP服务器 / Extend with new MCP servers

---

**版本 / Version:** 1.0
**日期 / Date:** 2025-11-01
**作者 / Author:** Claude Code
