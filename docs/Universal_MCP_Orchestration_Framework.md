# Universal MCP Orchestration Framework
# 通用MCP编排框架

**Version:** 2.0
**Status:** ✅ Production Ready
**Date:** 2025-11-04

---

## 📋 Table of Contents / 目录

1. [Overview / 概述](#overview)
2. [Key Features / 核心特性](#key-features)
3. [Architecture / 架构](#architecture)
4. [Quick Start / 快速开始](#quick-start)
5. [Components / 组件](#components)
6. [Configuration / 配置](#configuration)
7. [Usage Examples / 使用示例](#usage-examples)
8. [Extending the Framework / 扩展框架](#extending-the-framework)
9. [Testing / 测试](#testing)
10. [Troubleshooting / 故障排查](#troubleshooting)
11. [Migration Guide / 迁移指南](#migration-guide)

---

## Overview / 概述

The Universal MCP Orchestration Framework is a **metadata-driven, configuration-based** system for orchestrating multi-MCP server workflows. Unlike hardcoded solutions, this framework allows you to add new orchestration scenarios through **configuration files only** - no code changes required.

通用MCP编排框架是一个**元数据驱动、基于配置**的系统，用于编排多MCP服务器工作流。与硬编码解决方案不同，此框架允许您**仅通过配置文件**添加新的编排场景 - 无需更改代码。

### Why Universal Framework? / 为什么选择通用框架？

**Problem with Previous Approach (v1.0):**
- ❌ Hardcoded trigger conditions
- ❌ Fixed tool selection logic
- ❌ Hardcoded parameter extraction
- ❌ Single transformation function for all data types
- ❌ Every new scenario requires code changes
- ⚠️ "临时方案" (temporary solution) - good for demos, not production

**Universal Framework (v2.0) Advantages:**
- ✅ Configuration-driven rules (YAML)
- ✅ Metadata-defined tools
- ✅ Pluggable transformers
- ✅ Dynamic rule matching
- ✅ Add new scenarios via config only
- ✅ Production-ready architecture

---

## Key Features / 核心特性

### 1. **Metadata-Driven Tool Definitions** / 元数据驱动的工具定义

Tools are defined in `mcp_tools_metadata.yaml` with:
- Input/output schemas
- Categories and tags
- Server information
- Keywords for matching

```yaml
tools:
  query_jira_issues:
    category: data_retrieval
    mcp_server: "JIRAExtractor"
    port: 8004
    input_schema: {...}
    output_schema: {...}
    tags: ["jira", "issue", "bug"]
```

### 2. **Configuration-Based Orchestration Rules** / 基于配置的编排规则

Rules are defined in `orchestration_rules.yaml`:

```yaml
rules:
  jira_issues_pie_chart:
    trigger:
      keywords_all:
        - group1: ["jira", "issue"]
        - group2: ["pie", "chart"]
    tasks:
      - tool: "query_jira_issues"
        parameters: {...}
      - tool: "generate_pie_chart"
        depends_on: ["query_jira"]
```

### 3. **Pluggable Transformer Registry** / 可插拔转换器注册表

Data transformations are registered and reusable:

```python
registry = TransformerRegistry()
chart_data = registry.transform(
    source_data=jira_result,
    from_type="jira_issues",
    to_type="chart_data",
    strategy="by_status"
)
```

### 4. **Dynamic Rule Matching** / 动态规则匹配

No hardcoded `if` statements - rules are matched dynamically based on:
- Keyword groups (all/any/none)
- Regex patterns
- Priority ordering

### 5. **Zero State Coupling** / 零状态耦合

The framework doesn't modify the State structure - it integrates cleanly with existing systems.

---

## Architecture / 架构

### System Architecture / 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Query                               │
│               "Show S65 issues and create pie chart"             │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   UniversalOrchestrator                          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  1. Load Metadata (mcp_tools_metadata.yaml)              │  │
│  │  2. Load Rules (orchestration_rules.yaml)                │  │
│  │  3. Match Rule (dynamic keyword/pattern matching)        │  │
│  └──────────────────────────────────────────────────────────┘  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Task Execution Engine                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Task 1: query_jira_issues(component="S65")              │  │
│  │    → Extract params from query                           │  │
│  │    → Execute MCP tool                                    │  │
│  │    → Store result with output_key                        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            │                                     │
│                            ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Data Transformation (TransformerRegistry)                │  │
│  │    jira_issues → chart_data (strategy: by_status)        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            │                                     │
│                            ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Task 2: generate_pie_chart(data=transformed)            │  │
│  │    → Resolve dependency                                  │  │
│  │    → Execute chart MCP tool                              │  │
│  │    → Store chart result                                  │  │
│  └──────────────────────────────────────────────────────────┘  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Output Formatting                             │
│  Apply template with task results → Formatted response          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
                       User Response
```

### Component Diagram / 组件图

```
┌─────────────────────────────────────────────────────────────────┐
│                      Universal Framework                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐  ┌───────────────────┐  ┌─────────────┐ │
│  │  mcp_tools_      │  │  orchestration_   │  │  transformer│ │
│  │  metadata.yaml   │  │  rules.yaml       │  │  _registry  │ │
│  │                  │  │                   │  │  .py        │ │
│  │  - Tools         │  │  - Rules          │  │             │ │
│  │  - Schemas       │  │  - Triggers       │  │  - Built-in │ │
│  │  - Categories    │  │  - Tasks          │  │    logic    │ │
│  │  - Transform     │  │  - Parameters     │  │  - Custom   │ │
│  │    definitions   │  │  - Templates      │  │    registry │ │
│  └──────────────────┘  └───────────────────┘  └─────────────┘ │
│           │                      │                     │        │
│           └──────────────────────┼─────────────────────┘        │
│                                  │                              │
│                                  ▼                              │
│              ┌────────────────────────────────────┐            │
│              │   UniversalOrchestrator            │            │
│              │                                    │            │
│              │  - load_metadata()                 │            │
│              │  - load_rules()                    │            │
│              │  - match_rule()                    │            │
│              │  - extract_parameter()             │            │
│              │  - execute_task()                  │            │
│              │  - orchestrate()                   │            │
│              └────────────────────────────────────┘            │
│                                  │                              │
└──────────────────────────────────┼──────────────────────────────┘
                                   │
                                   ▼
                          Integration Point
                          (main.py: info_node)
```

---

## Quick Start / 快速开始

### Installation / 安装

No installation required - the framework is part of the AIops_Agent project.

### Basic Usage / 基本使用

```python
from universal_orchestrator import UniversalOrchestrator
from pathlib import Path

# 1. Create orchestrator with available tools
orchestrator = UniversalOrchestrator(all_tools)

# 2. Load configurations
base_path = Path(__file__).parent
orchestrator.load_metadata(str(base_path / "mcp_tools_metadata.yaml"))
orchestrator.load_rules(str(base_path / "orchestration_rules.yaml"))

# 3. Execute orchestration
result = await orchestrator.orchestrate(
    query="Show S65 open JIRA issues and create pie chart"
)

# 4. Use the result
if result:
    print(result['formatted_output'])
```

### Integration with main.py / 与main.py集成

The framework is already integrated in `Router/main.py`:

```python
# In startup_event():
universal_orchestrator = UniversalOrchestrator(all_tools)
universal_orchestrator.load_metadata(...)
universal_orchestrator.load_rules(...)

# In info_node():
if is_orchestration_query(query, universal_orchestrator):
    result = await universal_orchestrator.orchestrate(query, llm)
    if result:
        return {...}  # Return orchestration result
```

---

## Components / 组件

### 1. **mcp_tools_metadata.yaml**

Defines all available MCP tools with their specifications.

**Structure:**
```yaml
tools:
  tool_name:
    category: "data_retrieval" | "visualization" | "analysis"
    mcp_server: "ServerName"
    port: 8004
    description: "Tool description"
    input_schema: {...}
    output_schema:
      output_type: "jira_issues"  # Important for transformations
    tags: ["tag1", "tag2"]
    keywords: ["keyword1", "keyword2"]

transformations:
  transformation_name:
    from_type: "jira_issues"
    to_type: "chart_data"
    strategies:
      strategy_name:
        source_path: "statistics.by_status"
        transform_logic: "dict_to_category_value_pairs"
```

### 2. **orchestration_rules.yaml**

Defines orchestration workflows.

**Structure:**
```yaml
rules:
  rule_id:
    name: "Human-readable name"
    priority: 100  # Higher = matched first

    trigger:
      keywords_all:
        - group1: ["keyword1", "keyword2"]
        - group2: ["keyword3"]
      keywords_any: [...]  # Optional
      keywords_none: [...]  # Optional
      patterns: ["regex_pattern"]  # Optional

    tasks:
      - task_id: "unique_id"
        tool: "tool_name"
        depends_on: ["previous_task_id"]  # Optional

        parameters:
          param_name:
            source: "query" | "static" | "task_output"
            extractor: "regex" | "keyword_match" | "time_range"
            # ... extractor-specific config

        output:
          key: "output_key"
          type: "output_type"

    output_format:
      template: |
        Formatted output with {task_id.field} placeholders
```

### 3. **TransformerRegistry** (`transformer_registry.py`)

Manages data transformations between MCP tools.

**Built-in Transform Logic:**
- `dict_to_category_value_pairs`: `{key: value}` → `[{category, value}]`
- `count_by_field`: Count occurrences in list
- `extract_metric_values`: Extract nested metrics

**Usage:**
```python
registry = TransformerRegistry()
registry.load_from_metadata(metadata)

# Transform data
result = registry.transform(
    source_data=jira_data,
    from_type="jira_issues",
    to_type="chart_data",
    strategy="by_status"
)

# Register custom logic
def custom_transform(data):
    return [...]

registry.register_custom_logic("custom_name", custom_transform)
```

### 4. **UniversalOrchestrator** (`universal_orchestrator.py`)

Main orchestration engine.

**Key Methods:**
- `load_metadata(path)`: Load tool metadata
- `load_rules(path)`: Load orchestration rules
- `match_rule(query)`: Find matching rule
- `extract_parameter(config, query, results)`: Extract parameter value
- `execute_task(task_config, query, results)`: Execute single task
- `orchestrate(query, llm)`: Main orchestration method

---

## Configuration / 配置

### Adding a New Tool / 添加新工具

**Step 1:** Add tool metadata in `mcp_tools_metadata.yaml`

```yaml
tools:
  my_new_tool:
    category: data_retrieval
    mcp_server: "MyServer"
    port: 8006
    description: "My new tool"

    input_schema:
      type: object
      properties:
        param1: {type: string}

    output_schema:
      type: object
      output_type: "my_data_type"

    tags: ["tag1", "tag2"]
    keywords: ["keyword1"]
```

**Step 2:** (Optional) Add transformation if needed

```yaml
transformations:
  my_data_to_chart:
    from_type: "my_data_type"
    to_type: "chart_data"
    strategies:
      default:
        source_path: "data.items"
        transform_logic: "dict_to_category_value_pairs"
```

### Adding a New Orchestration Rule / 添加新编排规则

Add rule in `orchestration_rules.yaml`:

```yaml
rules:
  my_new_workflow:
    name: "My New Workflow"
    priority: 90

    trigger:
      keywords_all:
        - group1: ["keyword1", "keyword2"]
        - group2: ["action_keyword"]

    tasks:
      - task_id: "step1"
        tool: "my_new_tool"
        parameters:
          param1:
            source: "query"
            extractor: "regex"
            pattern: "PATTERN"
        output:
          key: "step1_data"

      - task_id: "step2"
        tool: "generate_pie_chart"
        depends_on: ["step1"]
        parameters:
          data:
            source: "task_output"
            task_id: "step1"
            transform:
              from_type: "my_data_type"
              to_type: "chart_data"
        output:
          key: "chart"

    output_format:
      template: |
        {step1_data.formatted_report}
        Chart: {chart.chart_url}
```

**That's it!** No code changes required. Restart the server and the new workflow is active.

---

## Usage Examples / 使用示例

### Example 1: JIRA + Pie Chart / JIRA + 饼图

**Query:**
```
"Show S65 open JIRA issues from 2025 and create a pie chart"
```

**Workflow:**
1. Match rule: `jira_issues_pie_chart`
2. Task 1: `query_jira_issues(component="S65", status="Open", year="2025")`
3. Transform: JIRA data → Chart data (by_status strategy)
4. Task 2: `generate_pie_chart(data=transformed)`
5. Format output with template

**Result:**
```
📊 **JIRA Issues & Pie Chart**

Found S65 issues (15 total):
- Open: 10
- Closed: 5

📈 **Visualization:**
Pie chart generated successfully

Chart URL: http://example.com/chart.png
```

### Example 2: Statistics + Bar Chart / 统计 + 柱状图

**Query:**
```
"Get JIRA statistics for S12 and show bar chart"
```

**Workflow:**
1. Match rule: `jira_statistics_chart`
2. Task 1: `get_issue_statistics(component="S12")`
3. Transform: Statistics → Chart data
4. Task 2: `generate_column_chart(data=transformed)`

### Example 3: Trend Analysis / 趋势分析

**Query:**
```
"Show JIRA issue trend over time for S99"
```

**Workflow:**
1. Match rule: `jira_trend_analysis`
2. Task 1: Query issues
3. Transform: Issues → Time series data
4. Task 2: Generate line chart

---

## Extending the Framework / 扩展框架

### Adding Custom Transform Logic / 添加自定义转换逻辑

```python
# In your code
from transformer_registry import get_transformer_registry

registry = get_transformer_registry()

def my_custom_transform(data, **kwargs):
    # Your transformation logic
    return transformed_data

registry.register_custom_logic("my_custom_transform", my_custom_transform)
```

Then use it in `mcp_tools_metadata.yaml`:

```yaml
transformations:
  my_transformation:
    from_type: "source_type"
    to_type: "target_type"
    strategies:
      custom:
        transform_logic: "my_custom_transform"
```

### Adding Custom Parameter Extractor / 添加自定义参数提取器

Extend `UniversalOrchestrator.extract_parameter()`:

```python
class CustomOrchestrator(UniversalOrchestrator):
    def extract_parameter(self, param_config, query, task_results):
        extractor = param_config.get("extractor")

        if extractor == "my_custom_extractor":
            # Your extraction logic
            return extracted_value

        # Fall back to parent
        return super().extract_parameter(param_config, query, task_results)
```

### Supporting Multi-Task Aggregation / 支持多任务聚合

Already supported! Use `source: "multi_task"`:

```yaml
parameters:
  data:
    source: "multi_task"
    task_ids: ["task1", "task2"]
    aggregation: "merge_by_status"  # or custom
```

---

## Testing / 测试

### Run All Tests / 运行所有测试

```bash
python tests/test_universal_framework.py
```

**Test Coverage:**
- ✅ Metadata loading
- ✅ Rules loading
- ✅ TransformerRegistry (dict_to_category_value_pairs, count_by_field, etc.)
- ✅ Rule matching (keywords, patterns, priority)
- ✅ Parameter extraction (regex, keyword_match, time_range)
- ✅ End-to-end orchestration

### Adding New Tests / 添加新测试

```python
def test_my_new_feature():
    orchestrator = UniversalOrchestrator(tools)
    orchestrator.load_metadata(...)
    orchestrator.load_rules(...)

    # Test your feature
    result = await orchestrator.orchestrate("My query")
    assert result['tasks_count'] == 2
```

---

## Troubleshooting / 故障排查

### Problem: Rule Not Matching / 规则不匹配

**Check:**
1. Verify keywords in query match those in `trigger.keywords_all`
2. Check rule priority - higher priority rules match first
3. Ensure `keywords_all` groups are all satisfied
4. Check logs for "Matched rule" or "No orchestration rule matched"

**Debug:**
```python
rule = orchestrator.match_rule("Your query")
if rule:
    print(f"Matched: {rule['rule_id']}")
else:
    print("No match")
```

### Problem: Parameter Extraction Fails / 参数提取失败

**Check:**
1. Verify regex pattern is correct
2. Check if parameter is marked as `required: true`
3. Review extractor configuration

**Debug:**
```python
param_config = {
    "source": "query",
    "extractor": "regex",
    "pattern": "S\\d+"
}
value = orchestrator.extract_parameter(param_config, "Show S65", None)
print(f"Extracted: {value}")
```

### Problem: Data Transformation Fails / 数据转换失败

**Check:**
1. Verify `from_type` matches tool's `output_type`
2. Check strategy exists in transformation definition
3. Ensure source_path exists in data

**Debug:**
```python
from transformer_registry import TransformerRegistry

registry = TransformerRegistry()
registry.load_from_metadata(metadata)

try:
    result = registry.transform(
        source_data=your_data,
        from_type="jira_issues",
        to_type="chart_data",
        strategy="by_status"
    )
except Exception as e:
    print(f"Transformation error: {e}")
```

### Problem: Orchestrator Not Initialized / 编排器未初始化

**Symptom:** `universal_orchestrator is None`

**Fix:**
1. Check `startup_event()` logs for initialization errors
2. Verify YAML files exist at correct paths
3. Check YAML syntax is valid

```python
# Manual initialization for debugging
orchestrator = UniversalOrchestrator(all_tools)
try:
    orchestrator.load_metadata("path/to/metadata.yaml")
    orchestrator.load_rules("path/to/rules.yaml")
except Exception as e:
    print(f"Failed: {e}")
```

---

## Migration Guide / 迁移指南

### Migrating from v1.0 (Hardcoded) to v2.0 (Universal)

**Step 1: Identify Your Hardcoded Patterns**

Old code (v1.0):
```python
if "jira" in query and "chart" in query:
    # Hardcoded logic
    jira_result = await query_jira()
    chart_data = transform_jira_to_chart(jira_result)  # Hardcoded
    chart_result = await create_chart(chart_data)
```

**Step 2: Define Rule in YAML**

```yaml
rules:
  jira_chart:
    trigger:
      keywords_all:
        - group1: ["jira"]
        - group2: ["chart"]
    tasks:
      - tool: "query_jira_issues"
        # ...
      - tool: "generate_pie_chart"
        # ...
```

**Step 3: Define Transformation**

```yaml
transformations:
  jira_to_chart:
    from_type: "jira_issues"
    to_type: "chart_data"
    strategies:
      by_status:
        source_path: "statistics.by_status"
        transform_logic: "dict_to_category_value_pairs"
```

**Step 4: Remove Hardcoded Code**

Replace with:
```python
if is_orchestration_query(query, orchestrator):
    result = await orchestrator.orchestrate(query)
```

**Step 5: Test**

Run tests to verify the new configuration works correctly.

---

## Performance Considerations / 性能考虑

### Current Implementation / 当前实现

- ✅ Serial task execution (suitable for dependent tasks)
- ✅ Individual error handling per task
- ✅ Clear execution logging

### Future Optimizations / 未来优化

- ⏳ Parallel execution for independent tasks
- ⏳ Result caching mechanism
- ⏳ Timeout control
- ⏳ Retry mechanism with exponential backoff

---

## Best Practices / 最佳实践

### 1. Rule Design / 规则设计

- ✅ Use specific keywords to avoid false matches
- ✅ Set appropriate priorities (100 = high, 50 = low)
- ✅ Test rules with various query variations
- ❌ Don't create overlapping rules with same priority

### 2. Tool Metadata / 工具元数据

- ✅ Define clear input/output schemas
- ✅ Use descriptive categories and tags
- ✅ Document all parameters
- ❌ Don't skip output_type - needed for transformations

### 3. Transformations / 转换

- ✅ Reuse existing transform logic when possible
- ✅ Name strategies descriptively (by_status, by_vendor)
- ✅ Handle missing data gracefully
- ❌ Don't create complex transformation chains

### 4. Testing / 测试

- ✅ Test each rule independently
- ✅ Test with edge cases (missing params, errors)
- ✅ Verify transformations with real data
- ✅ Run full integration tests

---

## Comparison: v1.0 vs v2.0

| Aspect | v1.0 (Hardcoded) | v2.0 (Universal) |
|--------|------------------|------------------|
| **Adding new scenario** | Modify code | Edit YAML only |
| **Trigger matching** | Hardcoded `if` statements | Dynamic rule matching |
| **Tool selection** | Hardcoded logic | Metadata-driven |
| **Parameter extraction** | Manual regex in code | Configured extractors |
| **Data transformation** | Single function | Pluggable registry |
| **Extensibility** | Low | High |
| **Maintainability** | Low | High |
| **Production readiness** | ⚠️ Temporary | ✅ Production |
| **Configuration** | None | YAML files |
| **Testing** | Manual | Comprehensive suite |

---

## Conclusion / 结论

The Universal MCP Orchestration Framework represents a significant improvement over the hardcoded v1.0 approach. It provides:

- **Flexibility**: Add new scenarios without code changes
- **Maintainability**: Clear separation of configuration and logic
- **Extensibility**: Easy to add new tools, rules, and transformations
- **Production-ready**: Comprehensive testing and error handling

通用MCP编排框架代表了相对于硬编码v1.0方法的重大改进。它提供了：

- **灵活性**：无需更改代码即可添加新场景
- **可维护性**：配置与逻辑清晰分离
- **可扩展性**：易于添加新工具、规则和转换
- **生产就绪**：全面的测试和错误处理

---

**Documentation Version:** 2.0
**Framework Version:** 2.0
**Last Updated:** 2025-11-04
**Status:** ✅ Complete & Production Ready
