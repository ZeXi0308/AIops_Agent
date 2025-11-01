# 单Query多MCP Server顺序调用实施方案

## 📋 方案概述

**目标：** 让系统能够处理单个query中包含的多个有依赖关系的子任务，自动顺序调用多个MCP server。

**核心机制：** Prompt引导任务识别 + State支持数据缓存 + 节点自动上下文传递

**工作量：** 约6-7小时（1个工作日）

---

## 🎯 改动点总览

| 改动位置 | 改动内容 | 工作量 |
|---------|---------|--------|
| `State` 结构 | 新增3个字段 | 10分钟 |
| `template` (System Prompt) | 增加多步任务处理协议 | 30分钟 |
| `result_processing_node` | 实现数据缓存和进度追踪 | 2小时 |
| `info_node` | 实现上下文自动注入 | 1.5小时 |
| 测试验证 | 端到端测试 | 2小时 |
| 文档编写 | 技术文档和使用说明 | 1小时 |

---

## 1. State结构扩展

### 当前State
```python
class State(TypedDict):
    messages: Annotated[list, add_messages]
    subgraph: str
    AI_Response: str
    Thinking: str
    human_in_the_loop: str
    json_result: Json_Schema
    session_id: str
    tool_images: list[dict[str, str]]
```

### 新增字段

```python
class State(TypedDict):
    # ... 现有字段 ...
    
    # 新增字段
    intermediate_results: dict       # 缓存每个工具的执行结果
    task_progress: dict              # 追踪任务执行进度
    context_summary: str             # 提供给LLM的简化上下文
```

### 字段说明

#### `intermediate_results: dict`
**作用：** 缓存每个工具的执行结果，供后续步骤使用

**数据结构：**
```python
{
    "tool_name": {
        "content": "完整的工具返回内容",
        "key_data": {
            # 提取的关键字段
            "field1": value1,
            "field2": value2
        },
        "timestamp": 1234567890.123
    }
}
```

**示例：**
```python
{
    "query_jira_issues": {
        "content": "{\"success\": true, \"issues\": [...], \"total\": 23}",
        "key_data": {
            "total_issues": 23,
            "fault_distribution": {
                "NW": 12,
                "UE": 8,
                "LAB": 3
            },
            "component": "S12",
            "status": "Open"
        },
        "timestamp": 1703123456.789
    }
}
```

#### `task_progress: dict`
**作用：** 追踪任务执行进度

**数据结构：**
```python
{
    "total": 2,              # 总任务数
    "current": 1,            # 当前执行到第几个
    "status": "in_progress"  # 状态：in_progress/completed
}
```

#### `context_summary: str`
**作用：** 人类可读的上下文摘要，注入给LLM

**示例：**
```
=== Available Data from Previous Steps ===

query_jira_issues completed:
- Total issues: 23
- Fault distribution: NW=12, UE=8, LAB=3
- Component: S12, Status: Open

You can use this data to call visualization tools.
============================================
```

---

## 2. System Prompt 增强要点

### 需要添加的核心概念

**在 `template` 中增加一个完整的"多步任务处理协议"部分：**

#### 2.1 任务识别规则
- 识别标志词："and", "then", "based on", "after"
- 检测多个动作词
- 判断是否有数据依赖

#### 2.2 执行规范
- 在 `[Thinking]` 中明确列出所有子任务
- 在 `[FinalAnswer]` 中说明当前进度："Executing Task 1/2..."
- 每次只调用一个工具（对于有依赖的任务）
- 等待结果后再决定下一步

#### 2.3 数据使用规则
- 系统会自动提供 "Available Data" 上下文
- 可以直接引用这些数据
- 提取需要的字段传给下一个工具

#### 2.4 完成判断
- 所有子任务执行完毕
- 在 `[FinalAnswer]` 中总结所有结果
- 明确说明 "All tasks completed"

### 关键规则强调

```
CRITICAL RULES:
- ONE tool call per turn for dependent tasks
- WAIT for result before calling next tool
- USE cached data from previous steps
- INDICATE progress in [FinalAnswer]: "Task X/Y: ..."
```

---

## 3. result_processing_node 改造

### 核心功能

**在处理工具执行结果时，自动完成以下操作：**

### 3.1 数据提取

**为常用工具定义提取规则：**

```python
TOOL_KEY_FIELDS = {
    "query_jira_issues": [
        "total_issues",
        "fault_distribution",  # 需要从issues中统计
        "component",
        "status"
    ],
    "DU_Name_IP_Mapping": [
        "sitelan_ip",
        "device_name"
    ],
    "check_UP_number": [
        "count",
        "versions"
    ]
}

def extract_key_data(tool_name: str, raw_content: str) -> dict:
    """从工具返回内容中提取关键字段"""
    data = json.loads(raw_content)
    
    if tool_name == "query_jira_issues":
        issues = data.get("issues", [])
        fault_dist = {}
        for issue in issues:
            fault = issue.get("fault_on", "Unknown")
            fault_dist[fault] = fault_dist.get(fault, 0) + 1
        
        return {
            "total_issues": len(issues),
            "fault_distribution": fault_dist,
            "component": data.get("component"),
            "status": data.get("status")
        }
    
    elif tool_name == "DU_Name_IP_Mapping":
        return {
            "sitelan_ip": data.get("sitelan_ip"),
            "device_name": data.get("device_name")
        }
    
    # ... 其他工具的提取规则
    
    return {}
```

### 3.2 缓存机制

```python
# 在result_processing_node中添加

# 初始化intermediate_results（如果不存在）
if "intermediate_results" not in state:
    state["intermediate_results"] = {}

# 提取关键数据
key_data = extract_key_data(tool_name, sanitised_content)

# 存入缓存
state["intermediate_results"][tool_name] = {
    "content": sanitised_content,
    "key_data": key_data,
    "timestamp": time.time()
}
```

### 3.3 进度判断

```python
def detect_task_progress(ai_response: str) -> dict:
    """从AI_Response中检测任务进度"""
    # 匹配 "Task X/Y" 模式
    match = re.search(r'Task\s+(\d+)/(\d+)', ai_response)
    if match:
        current = int(match.group(1))
        total = int(match.group(2))
        return {
            "total": total,
            "current": current,
            "status": "completed" if current == total else "in_progress"
        }
    return {"status": "unknown"}

# 在result_processing_node中使用
progress = detect_task_progress(state.get("AI_Response", ""))
state["task_progress"] = progress
```

### 3.4 生成上下文摘要

```python
def generate_context_summary(intermediate_results: dict) -> str:
    """生成人类可读的上下文摘要"""
    if not intermediate_results:
        return ""
    
    lines = ["=== Available Data from Previous Steps ===", ""]
    
    for tool_name, result in intermediate_results.items():
        key_data = result.get("key_data", {})
        lines.append(f"{tool_name} completed:")
        
        # 格式化关键数据
        for key, value in key_data.items():
            if isinstance(value, dict):
                # 处理字典类型（如fault_distribution）
                items = ", ".join([f"{k}={v}" for k, v in value.items()])
                lines.append(f"- {key}: {items}")
            else:
                lines.append(f"- {key}: {value}")
        
        lines.append("")
    
    lines.append("You can use this data to call the next tool.")
    lines.append("=" * 50)
    
    return "\n".join(lines)

# 在result_processing_node中生成
state["context_summary"] = generate_context_summary(state["intermediate_results"])
```

### 3.5 添加进度提示

```python
# 根据进度添加提示
hint = ""
progress = state.get("task_progress", {})

if progress.get("status") == "in_progress":
    current = progress.get("current", 0)
    total = progress.get("total", 0)
    hint = f"\n\n💡 Task {current}/{total} completed. Data is ready for the next step."
elif progress.get("status") == "completed":
    hint = "\n\n✅ All tasks completed successfully."

# 添加到AI_Response
state["AI_Response"] = final_answer_to_log + hint
```

### 3.6 返回更新后的State

```python
return {
    "messages": state["messages"],
    "Thinking": state["Thinking"],
    "AI_Response": state["AI_Response"],
    "tool_images": tool_images,
    "intermediate_results": state["intermediate_results"],  # 新增
    "task_progress": state["task_progress"],                # 新增
    "context_summary": state["context_summary"],            # 新增
}
```

---

## 4. info_node 增强

### 核心功能

**在LLM推理前，自动注入上下文信息**

### 4.1 检查中间结果

```python
async def info_node(state: State) -> State | Command:
    # ... 现有逻辑 ...
    
    # 检查是否有中间结果
    has_intermediate_data = bool(state.get("intermediate_results"))
```

### 4.2 构建增强的System Message

```python
# 如果有中间结果，增强template
if has_intermediate_data:
    context_text = state.get("context_summary", "")
    enhanced_template = template + "\n\n" + context_text
else:
    enhanced_template = template

# 注入System Message
if not any(isinstance(m, SystemMessage) for m in state["messages"]):
    state["messages"].insert(0, SystemMessage(content=enhanced_template))
```

### 4.3 判断是否需要清理

```python
# 在LLM返回响应后，检查是否完成所有任务
def should_clear_cache(response_content: str, progress: dict) -> bool:
    """判断是否应该清空缓存"""
    # 方法1：检测关键词
    completion_keywords = [
        "all tasks completed",
        "all tasks finished",
        "completed successfully"
    ]
    content_lower = response_content.lower()
    if any(kw in content_lower for kw in completion_keywords):
        return True
    
    # 方法2：检查进度状态
    if progress.get("status") == "completed":
        return True
    
    # 方法3：检测是否没有新的tool_calls
    # （如果没有工具调用且已有中间结果，说明已完成）
    return False

# 在info_node中使用
final_answer = ...  # 提取的FinalAnswer
progress = state.get("task_progress", {})

if should_clear_cache(final_answer, progress):
    # 清空缓存
    state["intermediate_results"] = {}
    state["task_progress"] = {}
    state["context_summary"] = ""
```

### 4.4 返回更新后的State

```python
return {
    "messages": messages + [response],
    "subgraph": subgraph_flag,
    "Thinking": state["Thinking"],
    "AI_Response": state["AI_Response"],
    "tool_images": tool_images,
    "intermediate_results": state.get("intermediate_results", {}),  # 保持或清空
    "task_progress": state.get("task_progress", {}),
    "context_summary": state.get("context_summary", ""),
}
```

---

## 5. 完整执行流程示例

### 场景：用户输入 "show S12 open issues and generate fault distribution chart"

```
【第1轮 - info_node】
输入：
- messages: [HumanMessage("show S12 open issues and...")]
- intermediate_results: {} (空)

LLM分析：
- 检测到2个任务
- Task 1: Query JIRA
- Task 2: Generate chart (依赖Task 1)

输出：
- tool_calls: [query_jira_issues(...)]
- AI_Response: "Executing Task 1/2: Querying JIRA..."

↓

【第2轮 - tools】
执行：query_jira_issues
返回：ToolMessage(content="{issues: [...], total: 23, ...}")

↓

【第3轮 - result_processing_node】
处理：
1. 提取关键数据：
   - total_issues: 23
   - fault_distribution: {NW: 12, UE: 8, LAB: 3}

2. 存入intermediate_results

3. 生成context_summary:
   "query_jira_issues completed: 23 issues, fault: NW=12, UE=8, LAB=3"

4. 检测进度：Task 1/2 → in_progress

5. 添加提示："💡 Task 1/2 completed. Data ready for Task 2."

输出：
- intermediate_results: {query_jira_issues: {...}}
- context_summary: "=== Available Data ===..."
- AI_Response: "Found 23 issues. Task 1/2 completed..."

↓

【第4轮 - info_node】
输入：
- intermediate_results: {query_jira_issues: {...}}

系统自动注入上下文：
enhanced_template = template + context_summary

LLM看到：
"=== Available Data ===
query_jira_issues: 23 issues, fault: NW=12, UE=8, LAB=3
====================="

LLM推理：
- 有了数据，可以生成图表
- 格式化数据：[{category: "NW", value: 12}, ...]

输出：
- tool_calls: [generate_pie_chart(data=[...], title="...")]
- AI_Response: "Executing Task 2/2: Generating chart..."

↓

【第5轮 - tools】
执行：generate_pie_chart
返回：ToolMessage(content="data:image/png;base64,...")

↓

【第6轮 - result_processing_node】
处理：
1. 提取图片
2. 检测进度：Task 2/2 → completed
3. 添加提示："✅ All tasks completed."

↓

【第7轮 - info_node】
LLM生成最终总结

系统检测到"All tasks completed"：
- 清空intermediate_results
- 清空task_progress
- 清空context_summary

输出：最终结果返回给用户
```

---

## 6. 实施步骤清单

```
□ Step 1: 修改State定义（10分钟）
   ├─ 在State class中添加3个新字段
   └─ 更新类型注解

□ Step 2: 优化System Prompt（30分钟）
   ├─ 添加"多步任务处理协议"部分
   ├─ 提供示例（JIRA+Chart、Device+UP等）
   └─ 强调关键规则

□ Step 3: 实现数据提取函数（30分钟）
   ├─ 创建TOOL_KEY_FIELDS配置
   ├─ 实现extract_key_data函数
   └─ 为主要工具添加提取规则

□ Step 4: 改造result_processing_node（1.5小时）
   ├─ 添加intermediate_results初始化
   ├─ 调用extract_key_data提取数据
   ├─ 实现缓存逻辑
   ├─ 实现detect_task_progress函数
   ├─ 实现generate_context_summary函数
   ├─ 添加进度提示
   └─ 更新返回的State

□ Step 5: 增强info_node（1.5小时）
   ├─ 检查intermediate_results
   ├─ 构建enhanced_template
   ├─ 注入上下文到System Message
   ├─ 实现should_clear_cache函数
   ├─ 在适当时机清空缓存
   └─ 更新返回的State

□ Step 6: 端到端测试（2小时）
   ├─ 准备测试用例
   ├─ 测试JIRA+Chart场景
   ├─ 测试Device+UP场景
   ├─ 测试3步链路
   ├─ 测试错误处理
   └─ 性能测试

□ Step 7: 文档编写（1小时）
   ├─ 编写使用说明
   ├─ 整理技术文档
   └─ 记录已知限制
```

---

## 7. 测试用例

### 7.1 基本场景（2步链路）

#### Test Case 1: JIRA + Chart
```
输入：
"show S12 open issues and generate a fault distribution pie chart"

期望：
- 第1步：成功查询JIRA
- 第2步：基于fault_on生成饼图
- 返回：issues摘要 + 图表

验证点：
✓ intermediate_results正确缓存JIRA数据
✓ 图表调用使用了正确的fault分布数据
✓ 最终清空了缓存
```

#### Test Case 2: Device + UP Check
```
输入：
"get IP of CNBJITDUS01236 and check how many UP versions are on it"

期望：
- 第1步：查询设备IP
- 第2步：使用该IP检查UP数量
- 返回：设备信息 + UP统计

验证点：
✓ IP地址正确传递给第二个工具
✓ 中间结果包含sitelan_ip字段
```

### 7.2 复杂场景（3步链路）

#### Test Case 3: Multi-step Analysis
```
输入：
"get latest 5 UP versions, then check which one is on CNBJITDUS01236, 
and show me a comparison chart"

期望：
- 第1步：获取最新5个UP版本
- 第2步：检查设备当前UP
- 第3步：生成对比图表

验证点：
✓ 每一步的结果都被缓存
✓ 上下文累积传递
```

### 7.3 边界情况

#### Test Case 4: 单工具调用（向下兼容）
```
输入：
"show S12 open issues"

期望：
- 只调用一个工具
- 不触发多步逻辑
- intermediate_results保持为空

验证点：
✓ 不影响现有单步功能
```

#### Test Case 5: 第一步失败
```
输入：
"show S99999 issues and generate chart"（不存在的component）

期望：
- 第1步失败后终止
- 返回错误信息
- 不尝试执行第2步

验证点：
✓ 错误优雅处理
✓ 用户收到清晰的错误提示
```

#### Test Case 6: 第二步失败
```
输入：
某种导致第2步失败的场景

期望：
- 返回第1步的结果
- 说明第2步失败原因
- 部分成功也算有价值

验证点：
✓ 至少返回了第1步的数据
```

---

## 8. 关键数据结构示例

### intermediate_results完整示例

```python
{
    "query_jira_issues": {
        "content": '{"success": true, "total": 23, "issues": [...]}',
        "key_data": {
            "total_issues": 23,
            "fault_distribution": {
                "NW": 12,
                "UE": 8,
                "LAB": 3
            },
            "component": "S12",
            "status": "Open"
        },
        "timestamp": 1703123456.789
    },
    "DU_Name_IP_Mapping": {
        "content": '{"sitelan_ip": "10.123.45.67", "device_name": "CNBJITDUS01236"}',
        "key_data": {
            "sitelan_ip": "10.123.45.67",
            "device_name": "CNBJITDUS01236"
        },
        "timestamp": 1703123460.123
    }
}
```

### task_progress示例

```python
# 执行中
{
    "total": 2,
    "current": 1,
    "status": "in_progress"
}

# 已完成
{
    "total": 2,
    "current": 2,
    "status": "completed"
}

# 未知（单步调用）
{
    "status": "unknown"
}
```

### context_summary示例

```
=== Available Data from Previous Steps ===

query_jira_issues completed:
- total_issues: 23
- fault_distribution: NW=12, UE=8, LAB=3
- component: S12
- status: Open

DU_Name_IP_Mapping completed:
- sitelan_ip: 10.123.45.67
- device_name: CNBJITDUS01236

You can use this data to call the next tool.
==================================================
```

---

## 9. 性能优化建议

### 9.1 缓存大小控制

```python
# 限制缓存条数（只保留最近2步）
MAX_CACHED_RESULTS = 2

def add_to_cache(cache: dict, tool_name: str, data: dict):
    if len(cache) >= MAX_CACHED_RESULTS:
        # 删除最旧的
        oldest = min(cache.items(), key=lambda x: x[1]["timestamp"])
        del cache[oldest[0]]
    
    cache[tool_name] = data
```

### 9.2 只缓存必要字段

```python
# 不要缓存完整的工具返回内容（可能很大）
# 只缓存提取的关键字段

state["intermediate_results"][tool_name] = {
    "key_data": key_data,  # 只保留这个
    "timestamp": time.time()
}
# 不保存 "content" 字段
```

### 9.3 设置过期时间

```python
# 超过5分钟的缓存自动失效
CACHE_EXPIRE_SECONDS = 300

def is_cache_valid(cached_time: float) -> bool:
    return (time.time() - cached_time) < CACHE_EXPIRE_SECONDS

# 在使用前检查
valid_results = {
    k: v for k, v in state["intermediate_results"].items()
    if is_cache_valid(v["timestamp"])
}
```

---

## 10. 错误处理策略

### 10.1 工具调用失败

```python
# 在result_processing_node中
if tool_message.content and "error" in tool_message.content.lower():
    # 工具执行失败
    state["AI_Response"] = f"❌ Task failed: {tool_message.content}"
    state["intermediate_results"] = {}  # 清空缓存
    return state
```

### 10.2 LLM解析失败

```python
# 提供更清晰的数据格式
# 在context_summary中使用简单格式，避免LLM误解
```

### 10.3 超时处理

```python
# 在工具调用时设置合理的timeout
# 超时后返回部分结果
```

---

## 11. 监控和调试

### 11.1 日志记录

```python
# 在关键节点添加日志
logger.info(f"[Multi-step] Task progress: {state.get('task_progress')}")
logger.info(f"[Multi-step] Cached results: {list(state.get('intermediate_results', {}).keys())}")
logger.info(f"[Multi-step] Context summary length: {len(state.get('context_summary', ''))}")
```

### 11.2 Thinking可视化

```python
# 在State的Thinking中追加多步流程信息
state["Thinking"] += f"\n\n🔗 Multi-step Flow:\n"
state["Thinking"] += f"- Progress: {state.get('task_progress')}\n"
state["Thinking"] += f"- Cached: {list(state.get('intermediate_results', {}).keys())}\n"
```

---

## 12. 预期效果

### 成功指标
- **成功率**：80-85%（2-3步链路）
- **响应时间**：20-30秒（取决于工具耗时）
- **用户体验**：无需手动拆分query

### 典型支持场景
```
✅ JIRA查询 + 图表生成
✅ 设备查询 + UP检查
✅ 日志提取 + 分析汇总
✅ 数据查询 + 统计计算
✅ 版本查询 + 兼容性检查
```

### 已知限制
```
⚠️ 3步以上的复杂链路可能不稳定（依赖LLM能力）
⚠️ 存在5-10%失败率（LLM推理误差）
⚠️ 工具返回格式变化可能导致解析失败
⚠️ 大数据量可能导致State膨胀
```

---

## 13. 风险和应对

| 风险 | 概率 | 影响 | 应对策略 |
|-----|------|------|---------|
| LLM未识别多步任务 | 中 | 中 | Prompt增加更多示例，优化指导语 |
| 数据提取失败 | 低 | 高 | 标准化工具返回格式，测试覆盖 |
| 上下文过长 | 低 | 中 | 限制缓存条数和字段大小 |
| 某步超时 | 中 | 中 | 设置合理timeout，提供部分结果 |
| State膨胀 | 低 | 中 | 自动清理过期缓存，只保留关键字段 |
| 与现有功能冲突 | 低 | 高 | 充分回归测试，确保向下兼容 |

---

## 14. 后续优化方向

### 短期（完成基础实施后）
- [ ] 收集实际使用数据
- [ ] 分析失败case并优化Prompt
- [ ] 调整提取规则和缓存策略

### 中期（1-2周后）
- [ ] 为高频链路创建专用组合工具
- [ ] 优化数据提取逻辑（更智能的字段识别）
- [ ] 增加更多工具的提取规则

### 长期（持续优化）
- [ ] 支持更复杂的任务依赖（并行+串行混合）
- [ ] 引入任务DAG（有向无环图）规划
- [ ] 自动学习和优化工具组合模式

---

## 15. 参考资料

### 相关技术
- **LangChain Sequential Chain**: 类似的链式调用机制
- **LangGraph Conditional Edges**: 条件路由决策
- **OpenAI Function Calling**: 工具调用标准

### 内部文档
- `introduction.md`: 项目整体架构说明
- `utils/tool_output.py`: 工具输出处理策略
- `Router/AD_subgraph.py`: 子图实现参考

---

## 附录：快速检查清单

### 实施前检查
- [ ] 理解当前State结构
- [ ] 熟悉result_processing_node逻辑
- [ ] 熟悉info_node逻辑
- [ ] 准备测试环境和数据

### 实施中检查
- [ ] State新字段正确定义
- [ ] Prompt增强已完成
- [ ] 数据提取函数测试通过
- [ ] 缓存逻辑正确实现
- [ ] 上下文注入正确实现

### 实施后检查
- [ ] 单步调用仍然正常（回归测试）
- [ ] 2步链路成功率>80%
- [ ] 3步链路可以尝试
- [ ] 错误处理优雅
- [ ] 日志信息完整

---

**最后更新：** 2025-01-27  
**作者：** AI Assistant  
**版本：** v1.0  
**状态：** 待实施

