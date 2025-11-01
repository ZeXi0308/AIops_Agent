# MCP Chart Bug 修复 - 最终变更清单

## ✅ 所有修改已完成

### 📋 修改概览

| 位置 | 修改类型 | 状态 | 影响 |
|------|---------|------|------|
| `info_node` 第377-420行 | 逻辑优化 | ✅ 完成 | 关键修复 |
| `result_processing_node` 第491-492行 | 调试增强 | ✅ 完成 | 辅助诊断 |
| `execute_2` 第665-682行 | 逻辑修复 | ✅ 完成 | 重要修复 |
| `execute_hil` 第753-758行 | 逻辑修复 | ✅ 完成 | 重要修复 |

---

## 🔧 详细修改内容

### 1. info_node 函数 (第377-460行)

**修改前**：
```python
async def info_node(state: State) -> State | Command:
    global global_log
    start_time = time.time()
    
    # ❌ 错误：每次进入都清空
    state["tool_images"] = []
    
    # ... LLM 调用 ...
```

**修改后**：
```python
async def info_node(state: State) -> State | Command:
    global global_log
    start_time = time.time()
    
    # ✅ 不再在开头清空
    
    # ... 消息处理 ...
    
    if last_ai_message is None or last_ai_message.content.strip() == "":
        # ✅ 只在真正需要生成新响应时清空
        state["tool_images"] = []
        response = await llm_with_tools.ainvoke(state["messages"])
    else:
        value = interrupt({"text_to_revise": "interrup in Info"})
        state["messages"].append(HumanMessage(content=str(value)))
        # ✅ 只在真正需要生成新响应时清空
        state["tool_images"] = []
        response = await llm_with_tools.ainvoke(state["messages"])
```

**变更行数**：
- 删除：第382行（原来的无条件清空）
- 添加：第410行、第419行（条件清空）
- 添加：第439行（调试日志）

---

### 2. result_processing_node 函数 (第462-577行)

**修改前**：
```python
tool_images = payload_images if payload_images else []
```

**修改后**：
```python
tool_images = payload_images if payload_images else []

# 🔍 调试信息：检查工具和图片提取
print(f"[DEBUG] Tool: {tool_name}, Images extracted: {len(tool_images)}, Strategy: {get_summary_strategy(tool_name) if tool_name else 'N/A'}")
```

**变更行数**：
- 添加：第491-492行（调试日志）

---

### 3. execute_2 函数 (第600-689行)

**修改前**：
```python
for target in reversed(results):
    ai_response = find_value(target, "AI_Response")
    if ai_response:
        thinking = find_value(target, "Thinking")
        dynamic_vars[ai_field] = ai_response
        dynamic_vars[thinking_field] = thinking or ""
        break

# ❌ 错误：使用的是已经 break 后的 target
tool_images_value = find_value(target, "tool_images")
if tool_images_value is not None:
    dynamic_vars["tool_images"] = tool_images_value
```

**修改后**：
```python
for target in reversed(results):
    ai_response = find_value(target, "AI_Response")
    if ai_response:
        thinking = find_value(target, "Thinking")
        dynamic_vars[ai_field] = ai_response
        dynamic_vars[thinking_field] = thinking or ""
        break

# ✅ 修复：独立循环查找 tool_images
for result in reversed(results):
    tool_images_value = find_value(result, "tool_images")
    if tool_images_value is not None:
        dynamic_vars["tool_images"] = tool_images_value
        break

# 调试日志
print(f"[DEBUG execute_2] Returning {len(response_payload['tool_images'])} images to frontend")
```

**变更行数**：
- 修改：第665-670行（独立循环查找图片）
- 添加：第682行（调试日志）

---

### 4. execute_hil 函数 (第691-767行)

**修改内容**：与 `execute_2` 相同的修复

**变更行数**：
- 修改：第753-758行（独立循环查找图片）

---

## 🧪 测试验证步骤

### 步骤 1：启动服务
```bash
cd /Users/zhaozhenyu/Desktop/utils
python main.py
```

### 步骤 2：测试场景 1 - 直接生成图表
```bash
curl -X POST http://0.0.0.0:878/run_test/ \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test_chart_1",
    "input": "请生成一张折线图，展示2020到2024年的数据，数据你自己编"
  }'
```

**预期日志输出**：
```
[DEBUG info_node] Images from LLM response: 0, Will return: 0 images
[DEBUG] Tool: mcp_chart-local_generate_line_chart, Images extracted: 1, Strategy: none
[DEBUG execute_2] Returning 1 images to frontend
```

**预期响应**：
```json
{
  "session_id": "test_chart_1",
  "AI_Response": "图表已生成...",
  "Thinking": "...",
  "human_in_the_loop": "",
  "tool_images": [
    {
      "mime": "image/png",
      "data": "iVBORw0KGgo..."
    }
  ]
}
```

### 步骤 3：测试场景 2 - 连续生成多个图表
```bash
# 第一个请求
curl -X POST http://0.0.0.0:878/run_test/ \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test_chart_2",
    "input": "生成一个柱状图"
  }'

# 第二个请求（同一个 session）
curl -X POST http://0.0.0.0:878/run_test/ \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test_chart_2",
    "input": "再生成一个饼图"
  }'
```

**预期结果**：
- 第一个响应应该只包含柱状图
- 第二个响应应该只包含饼图（不包含柱状图）

### 步骤 4：重复测试（验证稳定性）
```bash
# 运行 10 次，确保每次都能成功返回图片
for i in {1..10}; do
  echo "=== Test $i ==="
  curl -X POST http://0.0.0.0:878/run_test/ \
    -H "Content-Type: application/json" \
    -d "{\"session_id\": \"test_$i\", \"input\": \"生成一个折线图\"}" \
    | grep -o '"tool_images":\[.*\]' | grep -c "data"
done
```

**预期结果**：每次都应该输出 `1`（表示有一张图片）

---

## 📊 调试日志解读

### 正常流程的日志示例

```
# 1. 用户请求生成图表
Thinking in the info nodem, 

# 2. LLM 决定调用工具
Debug message after trim [...]
LLM Config: [...]

# 3. info_node 输出（此时还没有图片）
[DEBUG info_node] Images from LLM response: 0, Will return: 0 images

# 4. 工具执行并提取图片
[DEBUG] Tool: mcp_chart-local_generate_line_chart, Images extracted: 1, Strategy: none
Skipping LLM summary for tool 'mcp_chart-local_generate_line_chart' based on strategy.

# 5. result_processing 返回 info，info_node 再次执行
# （此时不应该清空图片，因为有 last_ai_message）

# 6. 最终返回给前端
[DEBUG execute_2] Returning 1 images to frontend
```

### 异常情况诊断

| 日志输出 | 问题诊断 | 解决方案 |
|---------|---------|---------|
| `Images extracted: 0` | 工具没返回图片或策略不匹配 | 检查 `tool_output.py` 策略配置 |
| `Returning 0 images` | 图片在流转中丢失 | 检查是否有其他节点清空了图片 |
| 没有 `[DEBUG]` 日志 | 代码可能被回退 | 重新检查代码修改 |

---

## ✅ 验证清单

- [ ] 修改 1：`info_node` 不再在开头清空图片
- [ ] 修改 2：`info_node` 在正确位置清空图片（调用 LLM 前）
- [ ] 修改 3：`result_processing_node` 添加调试日志
- [ ] 修改 4：`execute_2` 独立循环查找图片
- [ ] 修改 5：`execute_hil` 独立循环查找图片
- [ ] 测试 1：单次生成图表成功
- [ ] 测试 2：连续生成图表，图片不累积
- [ ] 测试 3：重复测试 10 次，100% 成功率

---

## 🎯 预期效果

### 修复前
- ❌ 图片显示"时有时无"
- ❌ 成功率约 50%
- ❌ 无法稳定复现

### 修复后
- ✅ 图片稳定显示
- ✅ 成功率 100%
- ✅ 行为可预测

---

## 📝 代码变更统计

- **文件数量**：1 个 (`main.py`)
- **新增行数**：~10 行（主要是调试日志和注释）
- **修改行数**：~15 行
- **删除行数**：1 行（原来的无条件清空）
- **影响函数**：4 个
- **风险等级**：低（只涉及图片处理逻辑，不影响其他功能）

---

## 🔒 回滚方案

如果出现问题，可以还原以下修改：

```bash
# 备份当前版本
cp main.py main.py.fixed

# 从 git 还原（如果有版本控制）
git checkout main.py

# 或手动还原关键行：
# 1. 在 info_node 第379行添加：state["tool_images"] = []
# 2. 删除第410行和第419行的清空操作
# 3. 还原 execute_2 和 execute_hil 的图片查找逻辑
```

---

**最终检查时间**：2025-10-28  
**修改状态**：✅ 全部完成  
**测试状态**：⏳ 等待验证  
**置信度**：95%

