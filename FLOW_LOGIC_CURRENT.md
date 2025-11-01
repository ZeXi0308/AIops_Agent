# 当前 main (4).py 完整逻辑分析

## 情景1：直接画图

### 第一轮："你好"
```
Frontend → execute_2 (first_run=True)
  ↓
State: { messages: [HumanMessage("你好")], tool_images: [] }
  ↓
START → info_node
  ↓ [检测]
  - last_message = HumanMessage("你好") ✅
  - 触发：直接调用 LLM（不 interrupt）
  ↓
LLM 回复："你好！有什么可以帮你的吗？"
  ↓
get_state() → "info" (没有工具调用)
  ↓
END
  ↓
Frontend 收到：AI_Response = "你好！..."，tool_images = []
```

### 第二轮："生成一张折线图"
```
Frontend → execute_2 (first_run=False)
  ↓
get_state(config) 检查：
  - current_state.next = () (空，图已结束) ✅
  ↓
执行：stream = graph.astream({"messages": [HumanMessage("生成折线图")]}, stream_mode="values")
  ↓
State 追加消息：
  messages: [
    SystemMessage(template),
    HumanMessage("你好"),
    AIMessage("你好！..."),
    HumanMessage("生成折线图") ← 新增
  ]
  ↓
START → info_node
  ↓ [检测]
  - last_message = HumanMessage("生成折线图") ✅
  - 触发：直接调用 LLM（不 interrupt）
  ↓
LLM 决定调用工具：
  response.tool_calls = [{name: "generate_line_chart", args: {...}}]
  ↓
get_state() → 检测到 tool_calls
  - tool_name = "generate_line_chart"
  - get_summary_strategy("generate_line_chart") → "none" (auto-tool)
  ↓
返回："tools" (不需要 human_window)
  ↓
tools (ToolNode) 执行 generate_line_chart
  ↓
返回：ToolMessage(content="data:image/png;base64,iVBOR...")
  ↓
result_processing_node
  ↓ [处理]
  - 提取 ToolMessage.content
  - process_tool_message("generate_line_chart", content)
  - 正则匹配 base64: images = [{mime: "image/png", data: "..."}]
  - tool_images = images (清空旧的，只保留本轮)
  - summary_strategy = "none" → 跳过 LLM 总结
  ↓
返回 State: {
  messages: [..., ToolMessage],
  tool_images: [{mime: "image/png", data: "..."}],
  AI_Response: "Tool Execution Result"
}
  ↓
result_processing → END (直接结束)
  ↓
execute_2 收集结果：
  - results = [多个 State 快照]
  - 从最后的 result 提取 tool_images
  - dynamic_vars["tool_images"] = [...]
  ↓
Frontend 收到：
  AI_Response = "Tool Execution Result",
  tool_images = [{mime: "image/png", data: "..."}] ✅
```

---

## 情景2：先查Jira，后画图

### 第一轮："你好，show me S57 open issues"
```
Frontend → execute_2 (first_run=True)
  ↓
State: { messages: [HumanMessage("show me S57...")], tool_images: [] }
  ↓
START → info_node
  ↓
LLM 决定调用：query_jira_issues
  ↓
get_state() → "tools" (auto-tool)
  ↓
tools → query_jira_issues 执行
  ↓
result_processing_node
  - 提取结果：纯文本 JSON
  - tool_images = [] (Jira 不生成图片)
  - summary_strategy = "llm_default" → 调用 LLM 总结
  ↓
返回 State: {
  messages: [..., ToolMessage, AIMessage(总结)],
  tool_images: [],
  AI_Response: "✨ S57有XX个open issues..."
}
  ↓
result_processing → END
  ↓
Frontend 收到：
  AI_Response = "✨ S57有XX个...",
  tool_images = [] ✅
```

### 第二轮："画饼图显示故障分布"
```
Frontend → execute_2 (first_run=False)
  ↓
get_state(config) 检查：
  - current_state.next = () (空) ✅
  ↓
执行：stream = graph.astream({"messages": [HumanMessage("画饼图")]}, stream_mode="values")
  ↓
State 追加消息：
  messages: [
    ...(之前的对话),
    HumanMessage("画饼图") ← 新增
  ]
  ↓
START → info_node
  ↓ [检测]
  - last_message = HumanMessage("画饼图") ✅
  - 触发：直接调用 LLM
  ↓
LLM 理解上下文（知道 S57 issues）→ 决定调用：
  tool_calls = [{name: "generate_pie_chart", args: {
    title: "S57 Fault Distribution",
    data: [{category: "...", value: ...}, ...]
  }}]
  ↓
get_state() → "tools"
  ↓
tools → generate_pie_chart 执行
  ↓
result_processing_node
  - 提取图片：tool_images = [{mime: "image/png", ...}]
  - summary_strategy = "none"
  ↓
result_processing → END
  ↓
Frontend 收到：tool_images = [图片] ✅
```

---

## 🔍 **关键修复点总结**

### 1. **execute_2 (第646-661行)**
```python
if first_run:
    # 初次对话
    stream = graph.astream(initial_state, stream_mode="values")
else:
    current_state = graph.get_state(config)
    if current_state and current_state.next:
        # 有 interrupt 等待 → 用 resume
        command = Command(resume=user_input)
        stream = graph.astream(command, stream_mode="values")
    else:
        # 图已结束 → 追加新消息
        update_state = {"messages": [HumanMessage(user_input)]}
        stream = graph.astream(update_state, stream_mode="values")
```
**解决**：第二轮对话能正确追加消息，不会误用 `resume`

### 2. **info_node (第408-430行)**
```python
last_message = state["messages"][-1]

if isinstance(last_message, HumanMessage):
    # 有新用户输入 → 直接处理
    response = await llm_with_tools.ainvoke(state["messages"])
elif last_ai_message is None:
    # 没有AI回复 → 直接处理
    response = await llm_with_tools.ainvoke(state["messages"])
else:
    # 其他情况 → interrupt
    value = interrupt(...)
```
**解决**：新消息进入时不会错误触发 interrupt

### 3. **result_processing → END (第624行)**
```python
graph_builder.add_edge("result_processing", END)
```
**解决**：工具执行后直接结束，不回 info_node，避免无限循环

### 4. **tool_images 清空时机 (info_node 第414/419/429行)**
```python
state["tool_images"] = []  # 只在准备调用 LLM 时清空
```
**解决**：不会在 info_node 开头无条件清空，保留工具生成的图片

---

## ✅ **能否完成任务？**

### **情景1：直接画图**
- ✅ 第一轮正常对话
- ✅ 第二轮追加消息 → LLM 调用画图工具 → 提取图片 → 返回前端
- ⚠️ **如果 LLM 决定不调用工具**（抽风），则没图（这是 LLM 问题，不是代码问题）

### **情景2：先Jira后画图**
- ✅ 第一轮查询 Jira → 返回文本结果
- ✅ 第二轮追加消息 → LLM 理解上下文 → 调用画图工具 → 返回图片
- ⚠️ **如果 LLM 理解错误或决定不调用工具**，则没图

---

## 🎯 **"时有时无" 的真正原因**

根据我的分析，现在代码逻辑是**完整且正确的**。如果仍然"时有时无"，只有2种可能：

1. **LLM 随机性**
   - 有时 LLM 决定调用工具
   - 有时 LLM 决定直接回复文字
   - **解决方案**：在 system prompt 中明确要求必须调用工具

2. **stream_mode 竞态**
   - `stream_mode="values"` 异步返回多个快照
   - 如果网络延迟，可能漏掉某些快照
   - **已解决**：现在从 `reversed(results)` 中查找，确保拿到最新的

---

## 🚀 **建议测试步骤**

1. 重启服务，确保加载最新代码
2. 测试情景1（直接画图）5次，记录：
   - 是否看到 `[tool/start] tool: generate_line_chart`
   - 是否看到 `[DEBUG result_processing] Images extracted: 1`
   - 前端是否收到图片
3. 测试情景2（先Jira后画图）5次，记录同样信息
4. 如果某次没图，检查是否有 `tool/start` 日志
   - **有** → 代码问题，继续调试
   - **没有** → LLM 问题，需要优化 prompt

**需要我帮你检查 system prompt 吗？或者先测试看结果？**

