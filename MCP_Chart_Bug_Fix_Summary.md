# MCP Chart 图片显示问题 - Bug 修复总结

## 🔍 问题描述

在使用 MCP Chart 工具生成图表时，出现"时有时无"的显示问题：
- **情景1**：第一轮"你好"，第二轮"请生成折线图" → 时而有图，时而没图
- **情景2**：第一轮"show me S57 open issues"，第二轮"generate a pie chart" → 时而有图，时而没图

## 🐛 发现的核心 Bug

### Bug #1: 图片在节点流转中被过早清空 ⭐⭐⭐ (Critical)

**问题位置**: `info_node` 第 382 行

**问题描述**:
```python
# 原代码 - 在节点开头无脑清空
async def info_node(state: State) -> State | Command:
    state["tool_images"] = []  # ❌ 每次进入都清空！
    ...
```

**流程分析**:
1. 用户请求 "生成折线图"
2. `info_node` → LLM 决定调用 Chart 工具 → 路由到 `tools`
3. `tools` 执行工具 → 路由到 `result_processing_node`
4. `result_processing_node` 提取图片，设置 `tool_images = [图片数据]`
5. **关键问题**：通过边 `result_processing → info`，再次进入 `info_node`
6. `info_node` 第 382 行**立即清空** `state["tool_images"] = []` ❌
7. 图片丢失！即使后面触发 interrupt，图片已经被清空了

**修复方案**:
```python
# ✅ 只在真正调用 LLM 生成新响应时才清空
if last_ai_message is None or last_ai_message.content.strip() == "":
    state["tool_images"] = []  # 清空旧图片
    response = await llm_with_tools.ainvoke(state["messages"])
else:
    value = interrupt({"text_to_revise": "interrup in Info"})
    state["messages"].append(HumanMessage(content=str(value)))
    state["tool_images"] = []  # 清空旧图片
    response = await llm_with_tools.ainvoke(state["messages"])
```

---

### Bug #2: 图片提取逻辑错误 ⭐⭐ (High)

**问题位置**: `execute_2` 和 `execute_hil` 函数

**问题描述**:
```python
# 原代码 - 从错误的 target 中提取图片
for target in reversed(results):
    if ai_response:
        ...
        break  # target 指向第一个有 AI_Response 的 result

tool_images_value = find_value(target, "tool_images")  # ❌ target 可能不是最新的
```

**问题分析**:
- `target` 变量在找到第一个 `AI_Response` 后就 break 了
- 但 `tool_images` 可能在另一个（更新的）result 中
- 例如，`result_processing_node` 的输出包含图片，但可能不是第一个有 `AI_Response` 的

**修复方案**:
```python
# ✅ 独立循环，从最新的 result 中提取图片
for result in reversed(results):
    tool_images_value = find_value(result, "tool_images")
    if tool_images_value is not None:
        dynamic_vars["tool_images"] = tool_images_value
        break
```

---

## 🔧 具体修改清单

### 1. `info_node` 函数 (第 377-459 行)
- ✅ **删除**：第 382 行的 `state["tool_images"] = []`
- ✅ **添加**：在第 410 行（调用 LLM 前）和第 419 行（用户输入后调用 LLM 前）清空图片
- ✅ **添加**：第 439 行调试信息

### 2. `result_processing_node` 函数 (第 461-574 行)
- ✅ **添加**：第 491 行调试信息，打印工具名称、图片数量和策略

### 3. `execute_2` 函数 (第 596-685 行)
- ✅ **修复**：第 665-670 行，独立循环提取 `tool_images`
- ✅ **添加**：第 682 行调试信息，打印返回的图片数量

### 4. `execute_hil` 函数 (第 687-759 行)
- ✅ **修复**：第 745-750 行，独立循环提取 `tool_images`（与 execute_2 同样的修复）

---

## 🧪 测试建议

### 测试场景 1: 直接生成图表
```
User: 你好
AI: 你好！有什么可以帮助你的吗？

User: 请生成一张折线图，展示 2020-2024 年的销售数据
Expected: ✅ 应该稳定地显示图表
Debug Output: 
  [DEBUG] Tool: mcp_chart-local_generate_line_chart, Images extracted: 1
  [DEBUG execute_2] Returning 1 images to frontend
```

### 测试场景 2: 工具链调用后生成图表
```
User: show me the S57 open issues
AI: [调用 query_jira 工具，返回结果]

User: generate a pie chart to show the fault distribution
Expected: ✅ 应该稳定地显示饼图
Debug Output:
  [DEBUG] Tool: mcp_chart-local_generate_pie_chart, Images extracted: 1
  [DEBUG execute_2] Returning 1 images to frontend
```

### 测试场景 3: 连续生成多个图表
```
User: 生成一张柱状图
AI: [显示柱状图]

User: 再生成一张折线图
Expected: ✅ 应该只显示折线图，不显示之前的柱状图
Debug Output:
  [DEBUG info_node] Images from LLM response: 0, Will return: 0 images (第一次)
  [DEBUG] Tool: generate_line_chart, Images extracted: 1 (工具执行)
  [DEBUG execute_2] Returning 1 images to frontend
```

---

## 📊 调试信息解读

运行后，在日志中查看以下调试信息：

1. **`[DEBUG info_node]`**: info_node 中从 LLM 响应提取的图片数量
2. **`[DEBUG] Tool:`**: result_processing_node 中从工具消息提取的图片数量和策略
3. **`[DEBUG execute_2]`**: 最终返回给前端的图片数量

### 正常流程的调试输出示例：
```
[DEBUG info_node] Images from LLM response: 0, Will return: 0 images
[DEBUG] Tool: mcp_chart-local_generate_pie_chart, Images extracted: 1, Strategy: none
[DEBUG execute_2] Returning 1 images to frontend
```

### 异常情况诊断：

#### 如果显示 `Images extracted: 0`
→ 问题：工具没有返回图片，或工具名称不匹配策略规则
→ 检查：`utils/tool_output.py` 中的 `MCP_POLICIES` 和 `MCP_POLICY_PATTERNS`

#### 如果显示 `Returning 0 images to frontend`
→ 问题：图片在节点流转或结果提取中丢失
→ 检查：是否有其他节点错误地清空了 `tool_images`

---

## 🎯 为什么之前"时有时无"？

可能的原因组合：

1. **主要原因 (Bug #1)**: 图片在 `info_node` 被过早清空
   - 当流程快速完成时，可能在清空前就已经被前端获取
   - 当流程慢一点时，清空操作先执行，导致图片丢失

2. **次要原因 (Bug #2)**: 图片提取位置错误
   - 有时 `AI_Response` 和 `tool_images` 在同一个 result 中 → 工作正常
   - 有时它们在不同的 result 中 → 提取失败

3. **LLM 的不确定性**:
   - LLM 可能调用不同名称的工具
   - 有些工具名称匹配策略规则（提取成功），有些不匹配（提取失败）

---

## ✅ 预期效果

修复后，MCP Chart 图片应该：
- ✅ **稳定显示**：每次调用 chart 工具都能正确显示图片
- ✅ **不累积**：每次只显示当前的图片，不会累积历史图片
- ✅ **不丢失**：在节点流转过程中正确保留图片
- ✅ **可追踪**：通过调试信息可以清晰地追踪图片的生成和传递过程

---

## 🚀 下一步建议

1. **运行测试**：按照上述测试场景验证修复效果
2. **观察日志**：查看调试信息，确认图片提取和传递正常
3. **如果仍有问题**：
   - 检查工具名称是否匹配策略规则
   - 确认 MCP Chart 工具返回的格式是否正确（base64 图片）
   - 检查前端是否正确处理 `tool_images` 字段

---

**修复日期**: 2025-10-28  
**修复人**: AI Assistant  
**影响文件**: `main.py`  
**严重程度**: Critical → Fixed

