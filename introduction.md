# Agent 项目详细入门指南

> **项目概述**: 基于 LangGraph 和 FastAPI 构建的智能 Agent 路由系统，支持多工具调用、人工审批、子图协作等复杂工作流。

---

## 📑 目录

- [1. 项目架构概览](#1-项目架构概览)
- [2. 技术栈详解](#2-技术栈详解)
- [3. 核心概念与设计模式](#3-核心概念与设计模式)
- [4. 主路由 (Router) 详细解析](#4-主路由-router-详细解析)
- [5. 子图 (Subgraph) 系统](#5-子图-subgraph-系统)
- [6. MCP 工具系统](#6-mcp-工具系统)
- [7. 数据流转全流程](#7-数据流转全流程)
- [8. 关键实现细节](#8-关键实现细节)
- [9. API 接口设计](#9-api-接口设计)
- [10. 部署与运行](#10-部署与运行)
- [11. 扩展开发指南](#11-扩展开发指南)
- [12. 常见问题与调试](#12-常见问题与调试)

---

## 1. 项目架构概览

### 1.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend / User                          │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTP Request
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                   FastAPI Server (Port 878)                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Main Router Graph (LangGraph)                 │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │  info_node → get_state → [tools|subgraph|human]    │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
└───────────────┬─────────────────────────────┬───────────────────┘
                │                             │
    ┌───────────▼──────────┐      ┌──────────▼──────────┐
    │  MCP Tool Servers    │      │   Subgraph APIs     │
    │  ┌─────────────┐     │      │  ┌──────────────┐   │
    │  │Port 8000-05 │     │      │  │ AutoDeploy   │   │
    │  │- UP Version │     │      │  │  (Port 7107) │   │
    │  │- DeviceInfo │     │      │  │              │   │
    │  │- JIRA       │     │      │  │ Trace Agent  │   │
    │  │- RRC Extract│     │      │  │  (Port 1111) │   │
    │  │- Chart Gen  │     │      │  └──────────────┘   │
    │  └─────────────┘     │      └─────────────────────┘
    └──────────────────────┘
```

### 1.2 核心模块组成

| 模块 | 文件路径 | 职责 |
|------|---------|------|
| **主路由** | `router_collect2_EAI_zhenyu.py` | 请求分发、工具调用、人工审批 |
| **子图构建** | `Router/AD_subgraph.py` | AutoDeploy 子图逻辑 (信息收集、Jenkins执行) |
| **MCP 客户端** | `Router/MCP_Client.py` | 管理多个 MCP 工具服务器连接 |
| **LLM 封装** | `Router/ericai_llm_async.py` | EricAI 模型自动刷新、Token 管理 |
| **工具输出处理** | `utils/tool_output.py` | Base64图片提取、工具响应策略 |

---

## 2. 技术栈详解

### 2.1 核心框架

#### LangGraph
- **作用**: 状态机编排框架，构建多节点有向图工作流
- **核心概念**:
  - `StateGraph`: 状态图类，定义节点和边
  - `State`: 使用 `TypedDict` 定义共享状态
  - `add_messages`: 自动合并消息历史的 Reducer
  - `interrupt`: 人机交互打断点机制
  - `Command`: 控制流跳转和状态更新

#### FastAPI
- **作用**: 异步 Web 框架，提供 RESTful API
- **特性**: 自动文档生成、异步支持、类型验证
- **端点**:
  - `/run_test/`: 初始化或续接对话
  - `/modify_test/`: 人工审批接口

#### LangChain
- **作用**: LLM 应用开发框架
- **组件**:
  - `ChatOpenAI`: OpenAI 兼容的聊天模型接口
  - `ToolNode`: 自动化工具调用节点
  - `SystemMessage/HumanMessage/AIMessage`: 消息类型

### 2.2 依赖服务

```python
# MCP 工具服务器分布
MCP_SERVERS = {
    "get_latest_UP_version": "http://localhost:8000/mcp/",  # UP版本查询
    "UpgradePackageChecker": "http://localhost:8002/mcp/",   # UP检查
    "DeviceInfoLookup": "http://localhost:8001/mcp/",        # 设备信息
    "RRCMsgExtractor": "http://localhost:8003/mcp/",         # RRC消息提取
    "JIRAExtractor": "http://localhost:8004/mcp/",           # JIRA查询
    "Chart": "http://localhost:8005/mcp/",                   # 图表生成
}

# 子图服务器端口
SUBGRAPH_PORTS = {
    "AutoDeploy": 7107,      # 自动部署子图
    "Trace_Agent": 1111,     # Trace配置子图
}
```

---

## 3. 核心概念与设计模式

### 3.1 State 状态管理

#### 主路由 State 结构
```python
class State(TypedDict):
    messages: Annotated[list, add_messages]  # 对话历史 (自动合并)
    subgraph: str                            # 子图路由标识 ("true"/"Trace_Agent"/"")
    AI_Response: str                         # AI回复内容
    Thinking: str                            # 思考过程 (累积)
    human_in_the_loop: str                   # 人工审批提示
    json_result: Json_Schema                 # 结构化信息
    session_id: str                          # 会话ID
    tool_images: list[dict[str, str]]        # 工具生成的图片
```

**关键点**:
- `Annotated[list, add_messages]`: LangGraph 自动将新消息追加到历史
- `Thinking` 是累积字段，每个节点追加内容
- `tool_images` 每次进入 `info_node` 会清空，避免图片累积

#### 子图 State 结构
```python
class Collect_State(TypedDict):
    messages: Annotated[list, add_messages]
    AI_Response: str
    Thinking: str
    human_in_the_loop: str
    json_result: Json_Schema     # 收集的JSON参数
    session_id: str
```

### 3.2 节点与边设计模式

#### 节点 (Node)
节点是执行具体任务的函数，签名为:
```python
async def node_function(state: State) -> State | Command:
    # 1. 读取 state 中的数据
    # 2. 执行业务逻辑 (调用LLM、工具、子图等)
    # 3. 更新 state 并返回
    return {"key": new_value}  # 部分更新
    # 或
    return Command(goto="target_node", update={...})  # 跳转控制
```

#### 条件边 (Conditional Edges)
根据 state 动态决定下一个节点:
```python
def get_state(state: State) -> Literal["human_window", "subgraph_node", "info", "tools"]:
    if state.get("subgraph") in ["true", "Trace_Agent"]:
        return "subgraph_node"  # 路由到子图
    if isinstance(state["messages"][-1], AIMessage) and state["messages"][-1].tool_calls:
        if any(is_auto_approved_tool(call) for call in ai_message.tool_calls):
            return "tools"  # 自动执行工具
        else:
            return "human_window"  # 需要人工审批
    return "info"  # 回到信息节点
```

### 3.3 Interrupt 机制 (Human-in-the-Loop)

```python
# 在节点中打断点
resume_data = interrupt({
    "question": "Is this correct?",
    "data_to_review": {...}
})

# 用户通过 API 恢复执行
command = Command(resume={"type": "accept"})
stream = graph.astream(command, config=config)
```

**工作原理**:
1. 节点执行到 `interrupt()` 时，保存当前状态到 checkpointer
2. 返回特殊响应给前端，包含需要审批的内容
3. 用户做出决定后，通过 `/modify_test/` 发送 `accept/reject`
4. 后端调用 `Command(resume=...)` 继续执行

---

## 4. 主路由 (Router) 详细解析

### 4.1 图结构构建

```python
graph_builder = StateGraph(State)

# 添加节点
graph_builder.add_node("info", info_node)                    # 信息处理节点
graph_builder.add_node("tools", tool_node)                   # 工具执行节点
graph_builder.add_node("result_processing", result_processing_node)  # 结果处理
graph_builder.add_node("human_window", human_window)         # 人工审批窗口
graph_builder.add_node("human_approval", human_approval)     # 人工审批逻辑
graph_builder.add_node("subgraph_node", call_subgraph)       # 调用子图
graph_builder.add_node("call_subgraph_sec", call_subgraph_sec)  # 子图二次交互
graph_builder.add_node("human_approve_sub", human_approve_sub)  # 子图审批

# 添加边
graph_builder.add_edge(START, "info")                        # 起点
graph_builder.add_conditional_edges("info", get_state)       # 条件分发
graph_builder.add_edge("human_window", "human_approval")     # 审批流程
graph_builder.add_edge("tools", "result_processing")         # 工具结果处理
graph_builder.add_edge("result_processing", "info")          # 循环回info
graph_builder.add_conditional_edges("subgraph_node", get_state_sub)  # 子图条件
```

### 4.2 核心节点详解

#### 4.2.1 info_node - 信息处理节点

**职责**: 与 LLM 交互，解析用户意图，决定下一步动作

```python
async def info_node(state: State) -> State | Command:
    # 1. 清空图片缓存 (防止累积)
    state["tool_images"] = []
    
    # 2. 注入系统模板 (如果没有的话)
    if not any(isinstance(m, SystemMessage) for m in state["messages"]):
        state["messages"].insert(0, SystemMessage(content=template))
    
    # 3. 调用 LLM
    llm = await create_llm()
    llm_with_tools = llm.bind_tools(all_tools)  # 绑定工具
    
    # 首次调用 vs 后续调用
    last_ai_message = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    if last_ai_message is None or last_ai_message.content.strip() == "":
        response = await llm_with_tools.ainvoke(state["messages"])
    else:
        # 打断点等待用户输入
        value = interrupt({"text_to_revise": "interrupt in Info"})
        state["messages"].append(HumanMessage(content=str(value)))
        response = await llm_with_tools.ainvoke(state["messages"])
    
    # 4. 解析响应 (提取 [Thinking] 和 [FinalAnswer])
    reasoning_match = re.search(r"\[(?:Reasoning|Thinking)\]\s*(.*?)\s*(?=\[FinalAnswer\]|\Z)", 
                                response.content, re.S | re.I)
    reasoning = reasoning_match.group(1).strip() if reasoning_match else ""
    
    final_answer_match = re.search(r'\[FinalAnswer\]\s*(.*?)(?=\n\[\w+\]|\Z)', 
                                   response.content, re.S | re.I)
    final_answer = final_answer_match.group(1).strip() if final_answer_match else response.content
    
    # 5. 提取图片 (Base64)
    cleaned_answer, answer_images = sanitise_text_field(final_answer)
    
    # 6. 判断是否需要路由到子图
    subgraph_flag = "true" if "subgraph" in response.content.lower() else state.get("subgraph", "false")
    if "Trace_Agent" in final_answer:
        subgraph_flag = "Trace_Agent"
    
    # 7. 更新状态
    state["Thinking"] = state.get("Thinking", "") + f"\n\n🤔Thinking:\n\n{reasoning}\n"
    state["AI_Response"] = cleaned_answer or final_answer
    
    return {
        "messages": messages + [response],
        "subgraph": subgraph_flag,
        "Thinking": state["Thinking"],
        "AI_Response": state["AI_Response"],
        "tool_images": answer_images if answer_images else [],
    }
```

**关键技术点**:
- **图片清理策略**: 每次进入时清空 `tool_images`，避免旧图累积
- **正则解析**: 从 LLM 响应中提取 `[Thinking]` 和 `[FinalAnswer]` 区块
- **Base64 图片处理**: `sanitise_text_field()` 提取嵌入的 `data:image/...;base64,...`
- **子图路由判断**: 检测关键词 `subgraph` 或 `Trace_Agent`

#### 4.2.2 result_processing_node - 结果处理节点

**职责**: 处理工具执行结果，决定是否需要 LLM 总结

```python
async def result_processing_node(state):
    # 1. 获取最新的 ToolMessage
    latest_tool_message = next((m for m in reversed(messages) if isinstance(m, ToolMessage)), None)
    
    # 2. 处理工具消息
    tool_name = getattr(latest_tool_message, "name", None)
    raw_content = latest_tool_message.content or ""
    cleaned_text, images, _ = process_tool_message(tool_name, raw_content)
    
    # 3. 根据工具策略决定是否跳过 LLM
    summary_strategy = get_summary_strategy(tool_name)
    
    if summary_strategy == "none":
        # 直接返回工具结果，不调用 LLM
        final_answer_to_log = f"### 🛠️ Tool Execution Result\n\n```json\n{cleaned_text}\n```"
        state["AI_Response"] = final_answer_to_log
        return {
            "messages": state["messages"],
            "AI_Response": state["AI_Response"],
            "tool_images": images if images else [],
        }
    
    # 4. 需要 LLM 总结
    analysis_message = {
        "role": "user",
        "content": "Analyze the tool execution result. Rewrite it to make it more readable..."
    }
    llm = await create_llm()
    response = await llm.ainvoke(messages + [analysis_message])
    
    # 5. 解析 LLM 总结
    final_answer = extract_final_answer(response.content)
    cleaned_answer, answer_images = sanitise_text_field(final_answer)
    
    # 6. 合并图片
    tool_images = images if images else []
    if answer_images:
        tool_images = tool_images + answer_images
    
    # 7. 更新状态
    state["AI_Response"] = cleaned_answer or final_answer
    state["Thinking"] = state.get("Thinking", "") + sanitized_tool_output
    
    return {
        "messages": state["messages"] + [analysis_message, response],
        "AI_Response": state["AI_Response"],
        "tool_images": tool_images,
    }
```

**关键点**:
- **工具策略**: 通过 `get_summary_strategy()` 判断是否需要 LLM 总结
  - `"none"`: 直接返回原始结果 (如数据库查询)
  - `"llm_default"`: 需要 LLM 改写为可读格式
- **图片合并**: 工具图片 + LLM 回复图片合并

#### 4.2.3 human_approval - 人工审批节点

```python
def human_approval(state: State) -> Command[Literal["tools", "info"]]:
    # 1. 获取待审批的工具调用
    ai_message = next((m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None)
    calls = ai_message.tool_calls
    
    # 2. 格式化审批提示
    llm_output = "\n".join([
        f"Please approve the execution of function : {c['name']} using ({c['args']})" 
        for c in calls
    ])
    
    # 3. 打断点等待用户决定
    resume_data = interrupt({"question": llm_output})
    resume_type = resume_data.get("type")
    
    # 4. 根据用户决定跳转
    if resume_type == "accept":
        return Command(goto="tools")  # 执行工具
    elif resume_type == "reject":
        state["AI_Response"] = "Seems you reject the request, Please tell me..."
        return Command(update={"AI_Response": state["AI_Response"]}, goto="info")
    else:
        return Command(goto="info")
```

#### 4.2.4 call_subgraph - 子图调用节点

```python
async def call_subgraph(state: State) -> State:
    # 1. 确定子图端口
    subgraph_port_map = {"Trace_Agent": "1111", "true": "7107"}
    port = subgraph_port_map.get(state.get("subgraph"))
    
    # 2. 提取用户最后一条真实消息 (倒数第二条 HumanMessage)
    human_msgs = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    last_msg = human_msgs[-2].content if len(human_msgs) >= 2 else "what kind of information..."
    
    # 3. 构建请求
    payload = {"input": last_msg, "session_id": state["session_id"]}
    url = f"http://0.0.0.0:{port}/run_test/"
    
    # 4. 发送 HTTP 请求到子图
    final_response = requests.post(url, headers={"Content-Type": "application/json"}, 
                                   data=json.dumps(payload), stream=True)
    
    # 5. 解析子图响应
    data = json.loads(final_response.text)
    ai_response = data.get("AI_Response", "")
    thinking = data.get("Thinking", "")
    human_in_the_loop = data.get("human_in_the_loop", "")
    
    # 6. 累积 Thinking (不覆盖)
    state["Thinking"] = state.get("Thinking", "") + thinking
    state["AI_Response"] = ai_response
    state["human_in_the_loop"] = human_in_the_loop
    
    return {"Thinking": state["Thinking"], "AI_Response": state["AI_Response"], ...}
```

---

## 5. 子图 (Subgraph) 系统

### 5.1 AutoDeploy 子图架构

```
START → info_node → get_state_collect → [json_gen_node|human_approval|info]
                                             ↓
                                      mcp_tools (工具调用)
                                             ↓
                                      save_json_node (保存参数)
                                             ↓
                                      human_approval (用户确认)
                                             ↓
                                      jenkins_excute_command (触发Jenkins)
                                             ↓
                                           END
```

### 5.2 子图核心流程

#### 5.2.1 信息收集阶段

**info_node 提示模板**:
```python
template = """
你是一个智能信息收集 Agent，任务是根据用户需求收集信息，并整理为 JSON 格式返回。

请严格遵循 React-style 循环格式：

Step 1: Thought
首先思考下一步做什么，是否需要提问用户、调用工具或整理信息。

Step 2: Action
执行的操作，例如和用户澄清需求。一定要询问用户是否apply IODT-recommended parameters。

Step 3: Observation
记录观察到的信息。

当收集完所有信息后：
第一步，先和用户确认信息是否需要二次修改。
第二步，返回 "The Information are collected：" + JSON格式。

JSON Schema:
{
    operation: str            # install/upgrade/configuration
    hardware_name: str        # 设备名 (cnbj开头或seki开头)
    UP_version: str           # 软件版本 (CXP开头或"latest")
    Tags: str | None          # IODT参数标签 (逗号分隔)
    Scenario_for_tags: str | None  # 或者使用Netconf场景
    Netconf: str | None       # Netconf列表选项
    Post_step: str | None     # 后续脚本 (initial_configuration等)
}
"""
```

#### 5.2.2 JSON 生成节点

```python
async def json_gen_node(state: Collect_State) -> Collect_State:
    # 1. 获取最后一条消息 (包含 "The Information are collected")
    last_msg = state["messages"][-1].content
    
    # 2. 使用 Structured Output
    llm_instance = await create_llm()
    llm_structured = llm_instance.with_structured_output(Json_Schema_2, method="json_mode")
    
    # 3. 构建提示
    prompt_text = f"""
你是一个严格的JSON生成器。请只输出符合 JSON Schema 的结果。
Schema:
{Json_Schema_2.schema_json(indent=2)}

下面是提取的信息，请转换为合法 JSON:
{last_msg}
"""
    
    # 4. 调用 LLM 生成 JSON
    response: Json_Schema_2 = await llm_structured.ainvoke(prompt_text)
    dict_output = json.loads(response.json())
    state["json_result"] = dict_output
    
    return state
```

#### 5.2.3 MCP 工具调用节点

```python
async def use_tools(state: Collect_State) -> Collect_State | Command:
    json_template = state.get("json_result")
    
    # 1. 调用 DU_Name_IP_Mapping 工具 (获取IP地址)
    for tool in mcp_tools:
        if tool.name == "DU_Name_IP Mapping":
            MCP_result = await tool.ainvoke({"query_key": json_template.get("hardware_name")})
    
    data = json.loads(MCP_result)
    json_template["hardware_name"] = data.get("sitelan_ip", None)
    
    if json_template["hardware_name"] is None:
        return Command(goto="__end__")  # IP不存在，终止流程
    
    # 2. 如果是 "latest" UP版本，调用 get_latest_UP_version 工具
    up_version_str = json_template["UP_version"]
    if "latest" in up_version_str.lower():
        for tool in mcp_tools:
            if tool.name == "get_latest_UP_version":
                MCP_result = await tool.ainvoke({
                    "number_versions": "3", 
                    "confidence_level": "3"
                })
        data = json.loads(MCP_result)
        version_str = data["1"]  # 取第一个版本
        json_template["UP_version"] = version_str
    
    # 3. 如果是 upgrade 操作，检查 UP 数量
    if json_template["operation"].lower() == "upgrade":
        for tool in mcp_tools:
            if tool.name == "check_UP_number":
                MCP_result = await tool.ainvoke({"du_ip": json_template["hardware_name"]})
        
        data = json.loads(MCP_result)
        number = data["count"]
        if number > 3:
            return Command(goto="__end__")  # UP版本过多，需要清理
    
    # 4. 更新 state
    state["json_result"] = json_template
    return state
```

#### 5.2.4 Jenkins 执行节点

```python
async def jenkins_excute_command(state: Collect_State) -> Collect_State:
    info_dict = state['json_result']
    
    # 1. 构建 curl 命令
    command = [
        'curl', '-i',
        'http://iodt.gic.ericsson.se:8443/job/Test_Display/buildWithParameters',
        '-H', 'Jenkins-Crumb: ...',
        '-u', 'exekixl:...'
    ]
    
    # 2. 添加表单参数
    command.extend(['--form', f'DU_Name="{info_dict.get("hardware_name")}"'])
    command.extend(['--form', f'UP_version="{info_dict.get("UP_version")}"'])
    command.extend(['--form', f'Operation="{info_dict.get("operation")}"'])
    # ... 其他参数
    
    # 3. 替换 None 为空字符串
    command = [s.replace('"None"', '""') for s in command]
    
    # 4. 执行命令
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    
    # 5. 解析返回的队列URL
    pattern = r'Location:\s*([a-zA-Z0-9]+://[^\s]+)'
    match = re.search(pattern, result.stdout)
    url1 = match.group(1)
    num = url1.split("/")[-2]
    
    # 6. 轮询队列获取Job URL
    time.sleep(10)
    url_str = f'http://iodt.gic.ericsson.se:8443//queue/item/{num}/api/json'
    res = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
    dict1 = json.loads(res.stdout.split("\n")[-1])
    url = dict1.get('executable', {}).get('url', "nothing")
    
    # 7. 返回 Jenkins 链接
    url_ret_str = f"[Jenkins link]({url})"
    state["AI_Response"] = url_ret_str
    return {"AI_Response": state["AI_Response"]}
```

---

## 6. MCP 工具系统

### 6.1 MCP 客户端设计

**容错机制**: `FaultTolerantMCPClient`

```python
class FaultTolerantMCPClient:
    def __init__(self, config):
        self.config = config
        self.healthy_services = {}  # 健康状态缓存
        self.client = None
    
    async def _check_all_services(self):
        """并发检查所有服务健康状态"""
        tasks = [
            self._check_service(name, service_config["url"])
            for name, service_config in self.config.items()
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def get_tools(self):
        """只返回健康服务的工具"""
        await self._check_all_services()
        
        # 过滤健康的服务
        healthy_config = {
            name: config for name, config in self.config.items()
            if self.healthy_services.get(name, False)
        }
        
        if not healthy_config:
            return []  # 无可用服务
        
        # 创建多服务器客户端
        self.client = MultiServerMCPClient(healthy_config)
        return await self.client.get_tools()
```

### 6.2 工具输出处理策略

**策略配置** (`utils/tool_output.py`):

```python
# 默认策略
DEFAULT_POLICY = {
    "text_handler": "plain_text",       # 文本处理: 直接返回
    "summary_handler": "llm_default",   # 摘要策略: 需要LLM总结
    "log_bucket": "Tool Message",       # 日志分类
}

# 图片工具策略
IMAGE_TOOL_POLICY = {
    "text_handler": "strip_base64",     # 提取Base64图片
    "summary_handler": "none",          # 不需要LLM总结
    "log_bucket": "Tool Images",        # 归类到图片日志
}

# 静默工具策略
SILENT_TOOL_POLICY = {
    "text_handler": "suppress",         # 抑制输出
    "summary_handler": "none",          # 不需要总结
}

# 工具映射
MCP_POLICIES = {
    "generate_line_chart": IMAGE_TOOL_POLICY,
    "chartrenderer": IMAGE_TOOL_POLICY,
    "internal_logging_tool": SILENT_TOOL_POLICY,
}

# 正则模式匹配
MCP_POLICY_PATTERNS = [
    (re.compile(r"^(generate|render)_[\w-]+_(chart|map|diagram)$"), IMAGE_TOOL_POLICY),
    (re.compile(r"^gpt[\w-]*vis"), IMAGE_TOOL_POLICY),
]
```

**Base64 图片提取**:

```python
_DATA_URL_RE = re.compile(
    r"data:(?P<mime>image/[\w.+-]+);base64,(?P<data>[A-Za-z0-9+/=\r\n]+)",
    re.IGNORECASE,
)

def _handle_strip_base64(text: str) -> Tuple[str, List[Dict[str, str]]]:
    images = []
    
    def _repl(match: re.Match[str]) -> str:
        images.append({
            "mime": match.group("mime"),
            "data": match.group("data")
        })
        return ""  # 替换为空字符串
    
    cleaned = _DATA_URL_RE.sub(_repl, text or "")
    if not cleaned.strip() and images:
        cleaned = "An image or chart has been generated."
    
    return cleaned.strip(), images
```

---

## 7. 数据流转全流程

### 7.1 典型场景1: 工具调用流程

```
用户: "查询最新的UP版本"

1. /run_test/ 接收请求
   └─ thread_id = "session_001"
   └─ user_input = "查询最新的UP版本"

2. info_node 处理
   └─ 注入 SystemMessage (template)
   └─ 调用 LLM: llm_with_tools.ainvoke(messages)
   └─ LLM 决定调用工具: get_latest_UP_version
   └─ 返回 AIMessage (含 tool_calls)

3. get_state 条件判断
   └─ 检测到 tool_calls
   └─ 判断工具类型: get_latest_UP_version ∈ 自动批准工具
   └─ 返回 "tools"

4. tools 节点执行
   └─ ToolNode 自动调用 get_latest_UP_version MCP工具
   └─ 返回 ToolMessage: {"1": "CXP9024418_6-R73A05", "2": ...}

5. result_processing_node 处理
   └─ 提取 ToolMessage.content
   └─ process_tool_message("get_latest_UP_version", content)
   └─ get_summary_strategy() → "none" (无需LLM总结)
   └─ 直接格式化结果:
      "### 🛠️ Tool Execution Result\n```json\n{...}\n```"

6. 返回到 info_node
   └─ interrupt 打断点，等待用户下一步指令

7. /run_test/ 响应
   └─ 返回 JSON:
      {
        "AI_Response": "### 🛠️ Tool Execution Result...",
        "Thinking": "...",
        "tool_images": []
      }
```

### 7.2 典型场景2: 子图路由流程

```
用户: "我想在 CNBJITDUS01236 上安装最新的UP"

1. /run_test/ 接收请求

2. info_node 处理
   └─ LLM 识别为 AutoDeploy 任务
   └─ 根据 template 规则，询问用户:
      "Do you want to route to the AutoDeploy function?"
   └─ 返回 AIMessage (不含 tool_calls)

3. 用户确认: "yes"

4. info_node 再次处理
   └─ interrupt 恢复后，LLM 返回:
      [FinalAnswer]
      subgraph
   └─ state["subgraph"] = "true"

5. get_state 条件判断
   └─ state["subgraph"] == "true"
   └─ 返回 "subgraph_node"

6. call_subgraph 节点
   └─ 提取用户原始消息: "我想在 CNBJITDUS01236 上安装最新的UP"
   └─ 发送 POST 请求到 http://0.0.0.0:7107/run_test/
      payload = {"input": last_msg, "session_id": "session_001"}

7. AutoDeploy 子图处理 (Port 7107)
   └─ info_node: 收集参数信息
      - operation: install
      - hardware_name: CNBJITDUS01236
      - UP_version: latest
      - 询问 IODT 参数等
   └─ json_gen_node: 生成 JSON
   └─ use_tools: 调用 MCP 工具
      - DU_Name_IP_Mapping: 获取IP
      - get_latest_UP_version: 解析 "latest"
   └─ save_json_node: 保存到 SQLite
   └─ human_approval: 用户确认参数
   └─ jenkins_excute_command: 触发 Jenkins 任务
   └─ 返回 Jenkins 链接

8. 主路由接收子图响应
   └─ call_subgraph 解析响应
   └─ state["AI_Response"] = "[Jenkins link](...)"
   └─ state["Thinking"] += 子图的 Thinking

9. get_state_sub 条件判断
   └─ AI_Response 包含 "Jenkins" → 返回 "info"

10. /run_test/ 响应
    └─ 返回 JSON:
       {
         "AI_Response": "[Jenkins link](http://...)",
         "Thinking": "...",
         "human_in_the_loop": ""
       }
```

### 7.3 典型场景3: 人工审批流程

```
用户: "查询 JIRA 问题: IODT-1234"

1. info_node 处理
   └─ LLM 决定调用: query_jira_issues(issue_key="IODT-1234")

2. get_state 条件判断
   └─ tool_calls 存在，但 query_jira_issues ∉ 自动批准工具
   └─ 返回 "human_window"

3. human_window 节点
   └─ 格式化提示: "Please approve the execution of function : query_jira_issues using ({'issue_key': 'IODT-1234'})"
   └─ state["human_in_the_loop"] = 提示内容

4. human_approval 节点
   └─ interrupt 打断点，等待用户决定

5. /run_test/ 响应
   └─ 返回 JSON:
      {
        "AI_Response": "Tool Calling",
        "human_in_the_loop": "Please approve the execution..."
      }

6. 前端显示审批界面，用户点击 "Accept"

7. /modify_test/ 接收请求
   └─ input = "accept"
   └─ Command(resume={"type": "accept"})

8. human_approval 恢复执行
   └─ resume_type == "accept"
   └─ return Command(goto="tools")

9. tools 节点执行
   └─ 调用 query_jira_issues MCP工具
   └─ 返回 ToolMessage

10. result_processing_node → info_node → /modify_test/ 响应
```

---

## 8. 关键实现细节

### 8.1 图片处理机制

#### 问题背景
工具生成的 Base64 图片会累积在 state 中，导致后续响应包含旧图片。

#### 解决方案
```python
# BUG FIX 1: info_node 入口清空
async def info_node(state: State) -> State | Command:
    state["tool_images"] = []  # 每次清空
    # ... 处理逻辑
    return {
        "tool_images": answer_images if answer_images else [],  # 只保留本轮图片
    }

# BUG FIX 2: result_processing_node 不继承旧图
async def result_processing_node(state):
    # 直接从零开始
    tool_images = payload_images if payload_images else []
    
    # 如果 LLM 回复也有图片，才合并
    if answer_images:
        tool_images = tool_images + answer_images
    
    return {"tool_images": tool_images}  # 不使用 state["tool_images"]
```

### 8.2 Thinking 累积策略

```python
# Thinking 是累积字段，不会被清空
state["Thinking"] = state.get("Thinking", "") + f"\n\n🤔Thinking:\n\n{reasoning}\n"

# 子图的 Thinking 也会累积到主路由
state["Thinking"] = state.get("Thinking", "") + thinking  # 追加子图的 Thinking
```

### 8.3 会话状态管理

```python
# 第一次调用 (首轮对话)
if first_run:
    initial_state = {
        "messages": [HumanMessage(content=user_input)],
        "AI_Response": "",
        "Thinking": "",
        "human_in_the_loop": "",
        "session_id": thread_id,
        "tool_images": []
    }
    stream = graph.astream(initial_state, config=config, stream_mode="values")
    thread_state[thread_id] = True

# 后续调用 (续接对话或恢复 interrupt)
else:
    command = Command(resume=user_input)
    stream = graph.astream(command, config=config)
```

### 8.4 LLM Token 自动刷新

```python
class AutoRefreshEricAIClient:
    def __init__(self, config: Optional[EricAIConfig] = None):
        self.config = config or EricAIConfig()
        self._last_key_refresh = 0.0
        self._key_manager = get_api_key_manager()
    
    def _should_refresh_key(self) -> bool:
        # 优先使用 key_manager 的过期检测
        try:
            return self._key_manager.key_is_expired()
        except Exception:
            # 备用逻辑: 基于时间判断
            elapsed_time = time.time() - self._last_key_refresh
            return elapsed_time >= self.config.refresh_interval_seconds
    
    async def get_llm_client(self) -> ChatOpenAI:
        await self.check_and_refresh()  # 每次调用前检查
        return self._llm_client
```

**配置**:
```python
config = EricAIConfig(
    base_url="https://ray.sero.gic.ericsson.se/backendsso/v1/",
    model="Qwen/Qwen2.5-32B-Instruct",
    key_valid_minutes=60,         # Token 有效期 60 分钟
    refresh_buffer_minutes=3,     # 提前 3 分钟刷新
)
```

### 8.5 消息历史修剪

**问题**: 长对话会导致上下文溢出，超过 LLM 的 token 限制。

**解决方案** (需在项目中实现):
```python
from langchain_core.messages import trim_messages

async def info_node(state: State) -> State | Command:
    messages = state["messages"]
    
    # 保留系统消息 + 最近 10 轮对话
    trimmed_messages = trim_messages(
        messages,
        max_tokens=4000,
        strategy="last",
        token_counter=llm,
        include_system=True,
    )
    
    response = await llm_with_tools.ainvoke(trimmed_messages)
    # ...
```

---

## 9. API 接口设计

### 9.1 POST /run_test/

**用途**: 初始化对话或续接现有对话

**请求体**:
```json
{
  "session_id": "user_123",        // 必填: 会话标识
  "input": "查询最新的UP版本"      // 必填: 用户输入
}
```

**响应体**:
```json
{
  "session_id": "user_123",
  "AI_Response": "✨ Latest UP versions:\n1. CXP9024418_6-R73A05\n2. ...",
  "Thinking": "🤔Thinking:\n\nI need to call get_latest_UP_version tool...\n\n### 🛠️ Tool Execution Result\n...",
  "human_in_the_loop": "",         // 空字符串: 无需人工介入
  "tool_images": []                // 空数组: 无图片生成
}
```

**人工审批场景响应**:
```json
{
  "session_id": "user_123",
  "AI_Response": "Tool Calling",
  "Thinking": "",
  "human_in_the_loop": "Please approve the execution of function : query_jira_issues using ({'issue_key': 'IODT-1234'})",
  "tool_images": []
}
```

**图片生成场景响应**:
```json
{
  "session_id": "user_123",
  "AI_Response": "An image or chart has been generated.",
  "Thinking": "...",
  "human_in_the_loop": "",
  "tool_images": [
    {
      "mime": "image/png",
      "data": "iVBORw0KGgoAAAANSUhEUgAA..."  // Base64 编码
    }
  ]
}
```

### 9.2 POST /modify_test/

**用途**: 人工审批决策接口

**请求体**:
```json
{
  "session_id": "user_123",
  "input": "accept"  // 或 "reject" 或 "edit=new_value"
}
```

**响应体**: 同 `/run_test/`

### 9.3 前端集成示例

```javascript
// 初始化对话
async function sendMessage(userInput, sessionId) {
  const response = await fetch('http://0.0.0.0:878/run_test/', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      session_id: sessionId,
      input: userInput
    })
  });
  
  const data = await response.json();
  
  // 渲染 AI 回复
  renderMessage(data.AI_Response);
  
  // 如果需要人工审批
  if (data.human_in_the_loop) {
    showApprovalDialog(data.human_in_the_loop, sessionId);
  }
  
  // 渲染图片
  if (data.tool_images && data.tool_images.length > 0) {
    data.tool_images.forEach(img => {
      const imgElement = document.createElement('img');
      imgElement.src = `data:${img.mime};base64,${img.data}`;
      document.body.appendChild(imgElement);
    });
  }
}

// 人工审批处理
async function handleApproval(decision, sessionId) {
  const response = await fetch('http://0.0.0.0:878/modify_test/', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      session_id: sessionId,
      input: decision  // "accept" or "reject"
    })
  });
  
  const data = await response.json();
  renderMessage(data.AI_Response);
}
```

---

## 10. 部署与运行

### 10.1 环境准备

```bash
# 1. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 2. 安装依赖
cd /Users/zhaozhenyu/Desktop/utils/Router
pip install -r requirements.txt

# 主要依赖:
# - fastapi
# - uvicorn
# - langchain
# - langgraph
# - langchain-openai
# - langchain-mcp-adapters
# - httpx
# - pydantic
```

### 10.2 启动 MCP 工具服务器

```bash
# 启动所有 MCP 工具 (端口 8000-8005)
cd /Users/zhaozhenyu/Desktop/utils/MCP_Tools

# 方法1: 使用 run.sh 脚本
bash run.sh

# 方法2: 手动启动每个服务
python mcp_curl_tool.py &          # Port 8000
python mcp_deviceinfo_tool.py &    # Port 8001
python check_up_tool.py &          # Port 8002
python mcp_rrc_tool.py &           # Port 8003
python mcp_jira_tool_jinshuo.py &  # Port 8004
# Chart 服务...                    # Port 8005
```

### 10.3 启动子图服务

```bash
# AutoDeploy 子图 (Port 7107)
cd /Users/zhaozhenyu/Desktop/utils/Router
python router_collect2_EAI.py  # 或其他版本

# Trace Agent 子图 (Port 1111)
# python trace_agent.py
```

### 10.4 启动主路由

```bash
cd /Users/zhaozhenyu/Desktop/utils
python router_collect2_EAI_zhenyu.py

# 或使用 uvicorn
uvicorn router_collect2_EAI_zhenyu:app --host 0.0.0.0 --port 878 --reload
```

### 10.5 验证部署

```bash
# 检查主路由
curl http://localhost:878/docs  # FastAPI 自动文档

# 检查 MCP 工具
curl http://localhost:8000/mcp/  # 应返回工具列表

# 测试端到端
curl -X POST http://localhost:878/run_test/ \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test_001", "input": "hello"}'
```

### 10.6 生产部署建议

```bash
# 使用 Supervisor 管理进程
# /etc/supervisor/conf.d/router.conf
[program:router_main]
command=/path/to/venv/bin/python router_collect2_EAI_zhenyu.py
directory=/Users/zhaozhenyu/Desktop/utils
autostart=true
autorestart=true
stderr_logfile=/var/log/router_main.err.log
stdout_logfile=/var/log/router_main.out.log

[program:mcp_tools]
command=/bin/bash run.sh
directory=/Users/zhaozhenyu/Desktop/utils/MCP_Tools
autostart=true
autorestart=true

# 启动 Supervisor
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start all
```

---

## 11. 扩展开发指南

### 11.1 添加新的 MCP 工具

**步骤1**: 创建 MCP 服务器

```python
# /Users/zhaozhenyu/Desktop/utils/MCP_Tools/mcp_my_tool.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("MyTool")

@mcp.tool()
def my_custom_tool(param1: str, param2: int) -> str:
    """
    Tool description for LLM.
    
    Args:
        param1: Description of param1
        param2: Description of param2
    
    Returns:
        Result description
    """
    # 实现工具逻辑
    result = f"Processed {param1} with {param2}"
    return result

if __name__ == "__main__":
    mcp.run(transport="sse", port=8006)
```

**步骤2**: 在 MCP_Client.py 中注册

```python
def create_mcp_client():
    config = {
        # ... 现有工具
        "MyTool": {
            "url": "http://localhost:8006/mcp/",
            "transport": "streamable_http",
        }
    }
    return FaultTolerantMCPClient(config)
```

**步骤3**: 配置工具输出策略 (可选)

```python
# utils/tool_output.py
MCP_POLICIES["my_custom_tool"] = _merge_policy({
    "summary_handler": "none",  # 不需要 LLM 总结
})
```

**步骤4**: 配置自动批准 (可选)

```python
# router_collect2_EAI_zhenyu.py
def get_state(state: State) -> Literal[...]:
    base_auto_tools = {
        "get_latest_UP_version",
        "my_custom_tool",  # 添加到自动批准列表
        # ...
    }
```

### 11.2 添加新的子图

**步骤1**: 创建子图文件

```python
# /Users/zhaozhenyu/Desktop/utils/Router/my_subgraph.py
from langgraph.graph import StateGraph, START, END

class MySubgraphState(TypedDict):
    messages: Annotated[list, add_messages]
    result: str

async def build_my_subgraph():
    graph_builder = StateGraph(MySubgraphState)
    
    async def process_node(state: MySubgraphState):
        # 子图逻辑
        return {"result": "Processed"}
    
    graph_builder.add_node("process", process_node)
    graph_builder.add_edge(START, "process")
    graph_builder.add_edge("process", END)
    
    memory = InMemorySaver()
    return graph_builder.compile(checkpointer=memory)

# FastAPI 接口
app = FastAPI()

@app.post("/run_test/")
async def run_subgraph(plan: dict):
    # ... 类似 AutoDeploy 的接口实现
    pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)
```

**步骤2**: 在主路由中注册

```python
# router_collect2_EAI_zhenyu.py

# 更新端口映射
subgraph_port_map = {
    "Trace_Agent": "1111",
    "true": "7107",
    "my_subgraph": "8888",  # 新增
}

# 更新模板提示
template = """
...
3) Special case: My Custom Workflow
   - Ask the user if they want to route to the **MySubgraph** function.
   - If confirmed, set [FinalAnswer] to: `my_subgraph`.
...
"""

# 更新条件判断
def get_state(state: State) -> Literal[...]:
    if state.get("subgraph") in ["true", "Trace_Agent", "my_subgraph"]:
        return "subgraph_node"
    # ...
```

### 11.3 自定义消息格式

```python
# 扩展 State 定义
class ExtendedState(State):
    custom_metadata: dict  # 新增自定义字段

# 在节点中使用
async def info_node(state: ExtendedState) -> ExtendedState:
    state["custom_metadata"] = {"source": "web", "priority": "high"}
    # ...
```

---

## 12. 常见问题与调试

### 12.1 MCP 工具连接失败

**症状**:
```
❌ UNAVAILABLE http://localhost:8000/mcp/
```

**排查步骤**:
1. 检查端口是否被占用:
   ```bash
   lsof -i :8000
   ```

2. 检查 MCP 服务日志:
   ```bash
   tail -f /Users/zhaozhenyu/Desktop/utils/MCP_Tools/*.log
   ```

3. 手动测试连接:
   ```bash
   curl http://localhost:8000/mcp/
   ```

### 12.2 LLM Token 过期

**症状**:
```
RuntimeError: did not get valid access token
```

**解决方案**:
```python
# 检查 token 文件
cat /mnt/openai_key/shared_token.txt

# 手动触发刷新
from ericai_llm_async import cleanup_global_client, get_auto_refresh_llm
await cleanup_global_client()
llm = await get_auto_refresh_llm()
```

### 12.3 图片累积问题

**症状**: 响应中包含历史对话的旧图片

**检查点**:
```python
# info_node 入口是否清空
async def info_node(state: State):
    state["tool_images"] = []  # ✅ 必须有这行
    # ...

# result_processing_node 是否直接赋值
return {
    "tool_images": tool_images,  # ✅ 不要使用 state["tool_images"]
}
```

### 12.4 Interrupt 无法恢复

**症状**: 调用 `/modify_test/` 后图无响应

**排查**:
1. 检查 session_id 是否一致
   ```python
   # 前端必须传递相同的 session_id
   POST /run_test/     {"session_id": "user_123", ...}
   POST /modify_test/  {"session_id": "user_123", ...}  # ✅ 必须一致
   ```

2. 检查 Command 格式
   ```python
   # ✅ 正确
   command = Command(resume={"type": "accept"})
   
   # ❌ 错误
   command = Command(resume="accept")  # 应该是字典
   ```

3. 检查 checkpointer
   ```python
   # 确保使用了 InMemorySaver
   memory = InMemorySaver()
   graph = graph_builder.compile(checkpointer=memory)
   ```

### 12.5 调试技巧

#### 启用详细日志
```python
from langchain.globals import set_debug, set_verbose

set_debug(True)   # 打印所有 LLM 调用
set_verbose(True) # 打印工具执行详情
```

#### 打印状态快照
```python
async def info_node(state: State):
    print("[DEBUG] Current State:")
    print(f"  - messages: {len(state['messages'])} items")
    print(f"  - subgraph: {state.get('subgraph')}")
    print(f"  - AI_Response: {state.get('AI_Response')[:100]}...")
    # ...
```

#### 追踪图执行路径
```python
@app.post("/run_test/")
async def execute_2(plan: dict):
    # ...
    async for output in stream:
        # 打印每个节点的输出
        print(f"[GRAPH OUTPUT] {output}")
        results.append(output)
```

#### 使用 LangSmith
```python
import os
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = "your_api_key"
os.environ["LANGCHAIN_PROJECT"] = "router-agent"
```

### 12.6 性能优化建议

#### 1. 并发工具调用
```python
# 当前实现 (串行)
for tool in mcp_tools:
    if tool.name == "tool1":
        result1 = await tool.ainvoke(...)
    if tool.name == "tool2":
        result2 = await tool.ainvoke(...)

# 优化 (并行)
import asyncio

tasks = []
for tool in mcp_tools:
    if tool.name in ["tool1", "tool2"]:
        tasks.append(tool.ainvoke(...))

results = await asyncio.gather(*tasks)
```

#### 2. LLM 响应缓存
```python
from langchain.cache import InMemoryCache
from langchain.globals import set_llm_cache

set_llm_cache(InMemoryCache())
```

#### 3. 消息历史压缩
```python
from langchain_core.messages import trim_messages

trimmed = trim_messages(
    state["messages"],
    max_tokens=4000,
    strategy="last",
    include_system=True,
)
```

---

## 13. 项目架构最佳实践

### 13.1 代码组织建议

```
utils/
├── Router/                          # 主路由与子图
│   ├── router_collect2_EAI_zhenyu.py   # 主路由 ✅ 生产版本
│   ├── AD_subgraph.py                  # AutoDeploy 子图
│   ├── MCP_Client.py                   # MCP 客户端
│   ├── ericai_llm_async.py             # LLM 封装
│   └── ericai_key_manager/             # Token 管理
│
├── MCP_Tools/                       # 工具服务器
│   ├── mcp_curl_tool.py
│   ├── mcp_deviceinfo_tool.py
│   ├── check_up_tool.py
│   ├── mcp_rrc_tool.py
│   ├── mcp_jira_tool_jinshuo.py
│   └── run.sh                          # 批量启动脚本
│
├── utils/                           # 公共工具
│   ├── tool_output.py                  # 工具输出处理
│   └── __init__.py
│
├── tests/                           # 测试用例 (建议添加)
│   ├── test_router.py
│   ├── test_subgraph.py
│   └── test_mcp_client.py
│
└── docs/                            # 文档
    ├── introduction.md                 # 本文档
    ├── api_reference.md                # API 参考
    └── development.md                  # 开发指南
```

### 13.2 版本管理策略

```bash
# 生产版本命名规范
router_collect2_EAI.py           # 基础版本
router_collect2_EAI_zhenyu.py    # 个人开发分支
router_collect2_EAI_v1.0.py      # 正式版本标记

# 建议迁移到 Git 分支管理
git checkout -b feature/zhenyu-improvements
```

### 13.3 配置管理

**创建配置文件** (`config.py`):
```python
from pydantic import BaseSettings

class Settings(BaseSettings):
    # API 配置
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 878
    
    # LLM 配置
    ERICAI_BASE_URL: str = "https://ray.sero.gic.ericsson.se/backendsso/v1/"
    ERICAI_MODEL: str = "Qwen/Qwen2.5-32B-Instruct"
    TOKEN_VALID_MINUTES: int = 60
    
    # MCP 工具端口
    MCP_UP_VERSION_PORT: int = 8000
    MCP_DEVICE_INFO_PORT: int = 8001
    MCP_UP_CHECKER_PORT: int = 8002
    # ...
    
    # 子图端口
    AUTODEPLOY_PORT: int = 7107
    TRACE_AGENT_PORT: int = 1111
    
    class Config:
        env_file = ".env"

settings = Settings()
```

**在代码中使用**:
```python
from config import settings

app = FastAPI()

if __name__ == "__main__":
    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)
```

### 13.4 日志管理

```python
import logging
from logging.handlers import RotatingFileHandler

# 配置日志
def setup_logging():
    logger = logging.getLogger("router")
    logger.setLevel(logging.INFO)
    
    # 文件处理器 (自动轮转)
    file_handler = RotatingFileHandler(
        "router.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

# 在节点中使用
async def info_node(state: State):
    logger.info(f"Processing message for session {state['session_id']}")
    # ...
```

### 13.5 错误处理

```python
# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc),
            "session_id": request.state.session_id if hasattr(request.state, "session_id") else None
        }
    )

# 节点级错误处理
async def info_node(state: State) -> State | Command:
    try:
        # ... 正常逻辑
        response = await llm_with_tools.ainvoke(state["messages"])
        return {"messages": [response], ...}
    except httpx.TimeoutException:
        logger.error("LLM timeout")
        state["AI_Response"] = "Sorry, the request timed out. Please try again."
        return state
    except Exception as e:
        logger.error(f"Unexpected error in info_node: {e}", exc_info=True)
        state["AI_Response"] = "An unexpected error occurred."
        return state
```

---

## 14. 安全性考虑

### 14.1 认证与授权

```python
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    token = credentials.credentials
    # 验证 token 逻辑
    if not is_valid_token(token):
        raise HTTPException(status_code=401, detail="Invalid token")
    return token

@app.post("/run_test/")
async def execute_2(plan: dict, token: str = Depends(verify_token)):
    # ... 处理逻辑
```

### 14.2 输入验证

```python
from pydantic import BaseModel, Field, validator

class RunRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=100, regex=r'^[a-zA-Z0-9_-]+$')
    input: str = Field(..., min_length=1, max_length=5000)
    
    @validator('input')
    def sanitize_input(cls, v):
        # 过滤恶意字符
        dangerous_patterns = ['<script', 'javascript:', 'onerror=']
        for pattern in dangerous_patterns:
            if pattern.lower() in v.lower():
                raise ValueError('Potentially malicious input detected')
        return v

@app.post("/run_test/")
async def execute_2(plan: RunRequest):  # 使用 Pydantic 模型
    # ...
```

### 14.3 敏感信息脱敏

```python
def sanitize_logs(text: str) -> str:
    """从日志中移除敏感信息"""
    # 隐藏 IP 地址
    text = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '***.***.***.***, text)
    
    # 隐藏 Token
    text = re.sub(r'Bearer [A-Za-z0-9._-]+', 'Bearer ***', text)
    
    # 隐藏密码
    text = re.sub(r'"password":\s*"[^"]+"', '"password": "***"', text)
    
    return text

logger.info(sanitize_logs(f"User input: {user_input}"))
```

---

## 15. 监控与运维

### 15.1 健康检查端点

```python
@app.get("/health")
async def health_check():
    health_status = {
        "status": "healthy",
        "timestamp": time.time(),
        "mcp_services": {},
        "subgraphs": {}
    }
    
    # 检查 MCP 服务
    client = create_mcp_client()
    await client._check_all_services()
    health_status["mcp_services"] = client.healthy_services
    
    # 检查子图
    for name, port in [("AutoDeploy", 7107), ("Trace_Agent", 1111)]:
        try:
            response = requests.get(f"http://0.0.0.0:{port}/health", timeout=2)
            health_status["subgraphs"][name] = response.status_code == 200
        except:
            health_status["subgraphs"][name] = False
    
    # 如果有服务不健康，返回 503
    all_healthy = (
        all(health_status["mcp_services"].values()) and
        all(health_status["subgraphs"].values())
    )
    
    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content=health_status
    )
```

### 15.2 性能指标收集

```python
from prometheus_client import Counter, Histogram, generate_latest
from fastapi.responses import Response

# 定义指标
request_count = Counter('router_requests_total', 'Total requests', ['endpoint', 'status'])
request_duration = Histogram('router_request_duration_seconds', 'Request duration')

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    
    response = await call_next(request)
    
    duration = time.time() - start_time
    request_duration.observe(duration)
    request_count.labels(endpoint=request.url.path, status=response.status_code).inc()
    
    return response

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

### 15.3 告警配置

```python
# 使用 Sentry 进行错误追踪
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

sentry_sdk.init(
    dsn="your_sentry_dsn",
    integrations=[FastApiIntegration()],
    traces_sample_rate=1.0,
)

# 发送自定义告警
def alert_on_critical_error(error_msg: str, context: dict):
    sentry_sdk.capture_message(
        error_msg,
        level="error",
        extras=context
    )
    
    # 或使用邮件/Slack通知
    # send_slack_alert(error_msg)
```

---

## 16. 总结与进阶资源

### 16.1 核心概念回顾

| 概念 | 说明 | 关键文件 |
|-----|------|---------|
| **LangGraph 状态机** | 多节点工作流编排 | `router_collect2_EAI_zhenyu.py` |
| **Interrupt 机制** | 人工审批打断点 | `human_approval()` 函数 |
| **MCP 工具系统** | 微服务化工具调用 | `MCP_Client.py`, `MCP_Tools/` |
| **子图协作** | 独立子流程HTTP通信 | `AD_subgraph.py` |
| **工具输出策略** | Base64图片提取与总结控制 | `utils/tool_output.py` |
| **Token 自动刷新** | EricAI密钥管理 | `ericai_llm_async.py` |

### 16.2 架构优势

1. **模块化**: MCP 工具独立部署，易于扩展
2. **容错性**: 健康检查机制，服务降级
3. **可观测性**: 完整的日志和状态追踪
4. **灵活性**: 通过子图实现复杂业务逻辑隔离
5. **人机协同**: Interrupt 机制实现关键决策人工审批

### 16.3 后续优化方向

1. **持久化存储**: 将 `InMemorySaver` 替换为 Redis/PostgreSQL
2. **流式响应**: 使用 SSE (Server-Sent Events) 实现实时响应
3. **多租户支持**: 添加租户隔离和权限管理
4. **A/B测试**: 多模型对比测试框架
5. **自动化测试**: 集成单元测试和E2E测试

### 16.4 参考资源

- **LangGraph 官方文档**: https://langchain-ai.github.io/langgraph/
- **FastAPI 文档**: https://fastapi.tiangolo.com/
- **MCP 协议**: https://modelcontextprotocol.io/
- **LangChain 文档**: https://python.langchain.com/
- **Pydantic 文档**: https://docs.pydantic.dev/

---

## 附录 A: 系统模板 (Template) 详解

主路由的系统模板定义了 LLM 的行为规范:

```python
template = """
Firstly, you are a receptionist. Please respond kindly and politely to the user's casual greetings.
Secondly, you are an Agent Router. Your role is to decide whether to invoke a tool or route the request.

1) Tool usage rules:  
   - You MUST list all required parameters and their values inside the [FinalAnswer] section.
   - Do NOT place any parameter names or values in [Thinking].
   - Do NOT assign values to parameters on your own; if anything is unclear or missing, 
     explicitly ask the user for clarification within [FinalAnswer].

2) Special case: DU or Baseband (GNB/ENB) installation, configuration, or upgrade
   - Do NOT analyze or explain the workflow!
   - Ask the user if they want to route to the **AutoDeploy** function.
   - If the user explicitly confirms, then set [FinalAnswer] to: `subgraph`.

3) Special case: Trace Config or setting (e.g., "BB trace setting")
   - Do NOT analyze or explain the workflow!
   - Ask the user if they want to route to the **Trace Agent** function.
   - If the user explicitly confirms, then set [FinalAnswer] to: `Trace_Agent`.

4) It is preferred that you include your internal thought process using [Thinking]. 
   However, [Thinking] is optional — the [FinalAnswer] is mandatory.

IMPORTANT — Output format (MUST follow exactly):
The assistant's entire reply must contain only these two sections (in this order):
- [FinalAnswer]  ← mandatory, must contain meaningful text
- [Thinking]     ← optional

Example:
[FinalAnswer]
I will call the get_latest_UP_version tool for you.

[Thinking]
The user wants to query the latest UP version. I should call the get_latest_UP_version tool...
"""
```

**关键设计意图**:
- **[FinalAnswer]** 用于前端展示，必须包含
- **[Thinking]** 用于调试和审计，可选
- 特殊关键词 `subgraph` / `Trace_Agent` 触发子图路由
- 强调参数收集必须在 `[FinalAnswer]` 中，避免用户看不到

---

## 附录 B: 常用命令速查

```bash
# 启动主路由
cd /Users/zhaozhenyu/Desktop/utils
python router_collect2_EAI_zhenyu.py

# 启动所有 MCP 工具
cd /Users/zhaozhenyu/Desktop/utils/MCP_Tools
bash run.sh

# 启动 AutoDeploy 子图
cd /Users/zhaozhenyu/Desktop/utils/Router
python AD_subgraph.py  # 需要配置端口

# 查看日志
tail -f router_zhenyu.log
tail -f MCP_Tools/*.log

# 测试 API
curl -X POST http://localhost:878/run_test/ \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test", "input": "hello"}'

# 检查端口占用
lsof -i :878
lsof -i :8000-8005
lsof -i :7107
lsof -i :1111

# 杀死进程
kill -9 $(lsof -t -i:878)

# 查看 Python 进程
ps aux | grep python | grep router
```

---

## 附录 C: 故障排查决策树

```
问题: API 无响应
├─ 检查进程是否运行
│  ├─ 是 → 检查端口是否正确
│  └─ 否 → 启动服务
│
├─ 检查日志
│  ├─ LLM Token 错误 → 刷新 Token
│  ├─ MCP 工具连接失败 → 启动 MCP 服务
│  └─ 其他错误 → 查看堆栈信息
│
└─ 测试各组件
   ├─ curl http://localhost:878/health
   ├─ curl http://localhost:8000/mcp/
   └─ curl http://localhost:7107/health

问题: 工具调用失败
├─ 检查 MCP 服务状态
│  └─ curl http://localhost:800X/mcp/
│
├─ 检查工具参数
│  └─ 日志中查看 tool.ainvoke(args)
│
└─ 检查工具策略配置
   └─ utils/tool_output.py 中的策略

问题: 图片不显示
├─ 检查 tool_images 是否清空
│  └─ info_node 入口: state["tool_images"] = []
│
├─ 检查 Base64 提取
│  └─ sanitise_text_field() 是否正确调用
│
└─ 检查前端渲染
   └─ data:image/png;base64,... 格式是否正确
```

---

**文档版本**: v1.0  
**最后更新**: 2025-10-25  
**维护者**: zhaozhenyu  
**项目路径**: `/Users/zhaozhenyu/Desktop/utils`

---

📝 **备注**: 本文档涵盖了项目的核心架构、实现细节、部署运维和扩展开发指南。对于具体代码实现，请参考项目源码和注释。如有疑问，欢迎查阅相关技术文档或联系项目维护者。