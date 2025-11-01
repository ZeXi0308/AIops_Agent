# ==================== 导入部分 ====================
# LangGraph 和 LangChain 核心组件
from typing import Annotated
from langchain_core.tools import tool
from typing_extensions import TypedDict
from langgraph.checkpoint.memory import InMemorySaver  # 内存状态保存器
from langgraph.graph import StateGraph, START, END  # 状态图构建器
from langgraph.graph.message import add_messages  # 消息累加器
from langgraph.prebuilt import ToolNode, tools_condition  # 预构建的工具节点
from langgraph.types import Command, interrupt  # 流程控制命令和中断功能
from ericai_llm_async import llm as create_llm  # 自定义的异步 LLM 创建器
from langchain.globals import set_verbose, set_debug  # 日志控制
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage, ToolMessage
from typing import Literal
from langchain_openai import ChatOpenAI

# Web 服务和通信相关
from fastapi import FastAPI, Request  # Web 框架
from fastapi.middleware.cors import CORSMiddleware  # 跨域支持
import httpx
import requests

# MCP (Model Context Protocol) 客户端
from MCP_Client import create_mcp_client
from langchain_mcp_adapters.client import MultiServerMCPClient

# 子图相关
from AD_subgraph import build_subgraph  # AutoDeploy 子图构建器

# 工具函数
import pprint
import asyncio
import os
import subprocess
import re
import json
from operator import xor
import time
import sys
from pathlib import Path

# === 自定义工具输出处理模块 ========================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
# 从 utils 导入工具输出处理函数
from utils.tool_output import process_tool_message, sanitise_text_field, get_summary_strategy
# ============================================================================

# ==================== 全局配置 ====================
file_path = "/mnt/openai_key/shared_token.txt"  # OpenAI 密钥文件路径
subgraph_processing = False  # 子图处理标志（未使用）
thread_state = {}  # 线程状态字典，记录每个 session 是否首次运行

# JSON 结构定义（用于特定操作的参数模式）
class Json_Schema(TypedDict):
    operation: str  # 操作类型
    hardware_name: str  # 硬件名称
    UP_version: str  # UP 版本
    Tags: str | None  # 标签（可选）
    Scenario_for_tags: str | None  # 标签场景（可选）
    Netconf: str | None  # 网络配置（可选）
    Post_step: str | None  # 后续步骤（可选）

# 全局日志字典，记录每轮对话的各类信息
global_log = {
    "AI_Response": [],  # AI 的最终回复
    "Thinking": [],  # AI 的思考过程
    "Human in the Loop": [],  # 人工干预记录
    "subgraph": [],  # 子图调用记录
    "Tool Message": [],  # 工具消息
    "Tool Images": [],  # 工具生成的图片
}

# 子图处理字典（未深度使用）
subgraph_processing_dictionary = {"default_id": False}

# ==================== FastAPI 应用初始化 ====================
app = FastAPI()
# 添加 CORS 中间件，允许所有来源访问（生产环境需限制）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（开发用，生产需指定域名）
    allow_methods=["*"],  # 允许所有 HTTP 方法
    allow_headers=["*"]  # 允许所有请求头
)

# ==================== System Prompt 模板 ====================
# 这是 Agent Router 的核心指令，定义了如何处理用户请求
template = (
"""Firstly, you are a receptionist. Please respond kindly and politely to the user's casual greetings.
Secondly, you are an Agent Router. Your role is to decide whether to invoke a tool or route the request, following the rules below:
 
1) Tool usage rules:  
   1 You MUST list all required parameters and their values **inside the [FinalAnswer] section and made it readable**.  
   2 Do NOT place any parameter names or values in [Thinking].  
   3 Do NOT assign values to parameters on your own; if anything is unclear or missing, explicitly ask the user for clarification **within [FinalAnswer]**.
 
 
2) Special case: DU or Baseband (GNB/ENB) installation, configuration, or upgrade
   - Do NOT analyze or explain the workflow (that will be handled later)!!  This case is not relate to any Tools! Just do the below steps!!!! 
   - Ask the user if they want to route to the **AutoDeploy** function.  
   - If the user explicitly confirms, then set [FinalAnswer] to the single word: `subgraph`.  
 
3) Special case: Trace Config or setting. user may descript as "BB trace setting"
   - Do NOT analyze or explain the workflow (that will be handled later)!!  This case is not relate to any Tools! Just do the below steps!!!! 
   - Ask the user if they want to route to the **Trace Agent** function.  
   - If the user explicitly confirms, then set [FinalAnswer] to the single word: `Trace_Agent`.  
 


4) It is **preferred** that you include your internal thought process. Use the label [Thinking] to provide it. However, [Thinking] is optional — **the [FinalAnswer] is mandatory** and must always be present.
 
IMPORTANT — Output format (MUST follow exactly):
The assistant's entire reply must contain **only** these two sections (in this order).  
- [FinalAnswer]  ← **mandatory**, must contain meaningful text (at least one sentence)
- [Thinking]     ← optional, you may include useful step-by-step thoughts here. If absent, it's OK.
 
Exact format example (both fields present):
[FinalAnswer]
I will call tools for your  
 
[Thinking]
I considered A, B, C. A lacks parameter p1 so I asked the user...
 
Example when you omit Thinking:
[FinalAnswer]
I need the user's credentials to proceed.
 
Do not include anything outside these two labeled sections. If rule (2) applies, [FinalAnswer] must be exactly: subgraph

""")

# ==================== 状态定义 ====================
# 定义整个 Agent 的状态结构
class State(TypedDict):
    messages: Annotated[list, add_messages]  # 消息列表，使用 add_messages 累加器
    subgraph: str  # 子图路由标志（"true" 表示 AutoDeploy，"Trace_Agent" 表示 Trace Agent）
    AI_Response: str  # AI 的最终回复
    Thinking: str  # AI 的思考过程
    human_in_the_loop: str  # 人工干预的提示信息
    json_result: Json_Schema  # 结构化结果（未深度使用）
    session_id: str  # 会话 ID
    tool_images: list[dict[str, str]]  # 工具生成的图片列表

# ==================== 状态图构建器 ====================
graph_builder = StateGraph(State)

# ==================== 路由决策函数 ====================
# 根据当前状态决定下一步流程
def get_state(state: State) -> Literal["human_window", "subgraph_node", "info", "__end__", "tools"]:
    """
    核心路由逻辑：
    1. 如果 subgraph 标志为 "true" 或 "Trace_Agent"，路由到子图节点
    2. 如果 AI 调用了工具：
       - 自动批准的工具（免人工干预）→ 直接执行工具
       - 其他工具 → 需要人工批准
    3. 其他情况 → 返回 info 节点（LLM 推理）
    """
    messages = state["messages"]
    print("subgraph in get stats1,", state["subgraph"])
    
    # 检查是否需要路由到子图
    if state.get("subgraph") in ["true", "Trace_Agent"]:
        print("subgraph in get stats2,", state["subgraph"])
        return "subgraph_node"
    
    # 空消息列表，返回 info
    if not messages:
        return "info"
    
    # 检查最后一条消息是否是 AI 调用工具
    if isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
        # 获取最近的 AI 消息和工具调用
        ai_message = next((m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None)
        calls = ai_message.tool_calls
        tool_names = [c['name'] for c in calls]
        
        # 定义自动批准的工具（无需人工干预）
        base_auto_tools = {
            "get_latest_UP_version",
            "check_UP_number",
            "DU_Name_IP_Mapping",
            "extract_rrc_msgs",
            "query_jira_issues",
            "get_issue_statistics",
        }

        def _is_auto_tool(name: str) -> bool:
            """判断工具是否自动批准"""
            if name in base_auto_tools:
                return True
            try:
                # 根据工具的汇总策略判断（"none" 表示无需 LLM 汇总，可自动执行）
                return get_summary_strategy(name) == "none"
            except Exception:
                return False

        # 如果所有工具都是自动批准的，直接执行
        if any(_is_auto_tool(name) for name in tool_names):
            print("Approved Tools No HIL")
            return "tools"
        else:
            # 否则需要人工批准
            return "human_window"

    # 如果最后一条消息不是人类消息，返回 info
    elif not isinstance(messages[-1], HumanMessage):
        return "info"
    
    return "info"

# ==================== 子图路由决策函数 ====================
# 在子图执行后，决定下一步流程
def get_state_sub(state: State) -> Literal["human_approve_sub", "call_subgraph_sec", "info"]:
    """
    子图路由逻辑：
    1. 如果有人工干预标志 → 需要人工批准
    2. 如果 AI 回复包含特定关键词（Jenkins、拒绝提示）→ 返回 info
    3. 其他情况 → 继续调用子图的第二阶段
    """
    human_status = state["human_in_the_loop"]
    ai_message = state["AI_Response"]
    print("ai_message in get_state_sub", ai_message)
    
    # 定义特殊关键词（表示流程结束或异常）
    keywords = [
        "Jenkins",
        "Seems you reject the request, Please tell me if everything I can do for you"
    ]
    
    # 如果有人工干预标志，需要人工批准
    if human_status:
        print("human_status is", human_status)
        return "human_approve_sub"

    # 如果 AI 回复包含结束关键词，返回 info
    if isinstance(ai_message, str) and any(keyword in ai_message for keyword in keywords):
        return "info"
    else:
        # 继续子图流程
        return "call_subgraph_sec"

# ==================== 子图人工批准节点 ====================
def human_approve_sub(state: State):
    """
    处理子图的人工批准逻辑：
    1. 根据子图类型（AutoDeploy 或 Trace_Agent）选择对应端口
    2. 中断流程，等待用户响应（accept/reject）
    3. 将用户响应转发给子图服务
    4. 更新状态并返回
    """
    # 子图到端口的映射
    subgraph_port_map = {
        "Trace_Agent": "1111",
        "true": "7107"
    }
    subgraph_value = state.get("subgraph")
    port = subgraph_port_map.get(subgraph_value, None)
    print("port in human_approve_sub ", port)
    session_id = state["session_id"]
    
    # 中断流程，等待用户批准
    resume_data = interrupt(
        {
            "question": "Is this correct?",
        }
    )
    resume_type = resume_data.get("type")
    print("resume type is", resume_type)
    
    # 用户接受
    if resume_type == "accept":
        payload = {
            "input": "accept",
            "session_id": session_id
        }
        url = f"http://0.0.0.0:{port}/modify_test/"
        try:
            # 调用子图的修改接口
            final_response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                stream=True
            )
            print("final_response is", final_response)
            content = final_response.text
            print(content)
            data = json.loads(content)
            
            # 提取子图返回的信息
            ai_response = data.get("AI_Response", "")
            thinking = data.get("Thinking", "")
            human_in_the_loop = data.get("human_in_the_loop", "")
    
            # 更新状态（累加 Thinking）
            state["Thinking"] = state.get("Thinking", "") + thinking
            state["AI_Response"] = ai_response
            state["human_in_the_loop"] = human_in_the_loop
            state["subgraph"] = ""  # 清空子图标志
            print("[debug]state in info node", state)

            return Command(update={
                "AI_Response": state["AI_Response"],
                "Thinking": state["Thinking"],
                "human_in_the_loop": state["human_in_the_loop"],
                "subgraph": state["subgraph"]
            })

        except Exception as e:
            print("请求出错:", e)
    
    # 用户拒绝
    elif resume_type == "reject":
        payload = {
            "input": "reject",
            "session_id": session_id
        }
        url = f"http://0.0.0.0:{port}/modify_test/"
        try:
            # 调用子图的修改接口
            final_response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                stream=True
            )
            print("final_response is", final_response)
            content = final_response.text
            print(content)
            data = json.loads(content)
            
            # 提取子图返回的信息
            ai_response = data.get("AI_Response", "")
            thinking = data.get("Thinking", "")
            human_in_the_loop = data.get("human_in_the_loop", "")
    
            # 更新状态
            state["Thinking"] = thinking
            state["AI_Response"] = ai_response
            state["subgraph"] = ""
            state["human_in_the_loop"] = human_in_the_loop
            print("[debug]state in info node", state)
            
            return Command(update={
                "AI_Response": state["AI_Response"],
                "Thinking": state["Thinking"],
                "human_in_the_loop": state["human_in_the_loop"],
                "subgraph": state["subgraph"]
            })
        except Exception as e:
            print("请求出错:", e)
            ai_response = "Seems something wrong when reject the request,back to the receptionist and you can post your request  "
            state["AI_Response"] = ai_response
            print("[debug]state in info node", state)
            return Command(update={"AI_Response": state["AI_Response"], "Thinking": "", "subgraph": ""}, goto="info")
    else:
        # 其他情况，返回 info 节点
        return Command(goto="info")

# ==================== 人工批准窗口节点 ====================
def human_window(state: State):
    """
    展示工具调用信息，等待人工批准
    返回格式化的工具调用信息供前端展示
    """
    messages = state["messages"]
    if isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
        # 获取最近的 AI 消息
        ai_message = next((m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None)
        calls = ai_message.tool_calls
        # 格式化工具调用信息
        calling_output = "\n".join([f"Please approve the execution of function : {c['name']} using ({c['args']})" for c in calls])

        return {
            "AI_Response": "Tool Calling",
            "human_in_the_loop": calling_output
        }

# ==================== 人工批准决策节点 ====================
def human_approval(state: State) -> Command[Literal["tools", "info"]]:
    """
    处理工具调用的人工批准：
    1. 提取工具调用信息
    2. 中断流程，等待用户批准（accept/reject）
    3. 根据用户响应决定下一步
    """
    # 获取最近的 AI 消息
    ai_message = next((m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None)
    if ai_message is None:
        raise ValueError("No AIMessage found in state['messages'].")
    
    # 提取工具调用信息
    if ai_message.tool_calls:
        calls = ai_message.tool_calls
        llm_output = "\n".join([f"Please approve the execution of function : {c['name']} using ({c['args']})" for c in calls])
    else:
        llm_output = "<no tool calls found>"

    # 中断流程，等待用户批准
    resume_data = interrupt({"question": llm_output})
    resume_type = resume_data.get("type")
    print("resume type is", resume_type)
    
    # 用户接受 → 执行工具
    if resume_type == "accept":
        return Command(goto="tools")
    # 用户拒绝 → 返回 info 节点
    elif resume_type == "reject":
        state["AI_Response"] = "Seems you reject the request, Please tell me if everything I can do for you"
        return Command(update={"AI_Response": state["AI_Response"]}, goto="info")
    else:
        return Command(goto="info")

# ==================== MCP 客户端初始化 ====================
client = create_mcp_client()

# ==================== 应用启动事件 ====================
@app.on_event("startup")
async def startup_event():
    """
    应用启动时初始化：
    1. 创建 MCP 客户端并获取工具列表
    2. 构建 AutoDeploy 子图
    3. 定义所有节点函数（info、工具、子图等）
    4. 构建状态图并编译
    """
    global graph
    global subgraph
    
    # 初始化 MCP 客户端并获取工具
    client = create_mcp_client()
    mcp_tools = await client.get_tools()
    all_tools = list(mcp_tools)
    
    # 构建 AutoDeploy 子图
    subgraph = await build_subgraph()
    print("building subgraph")
    print(type(subgraph))

    # ==================== 子图调用节点 ====================
    async def call_subgraph(state: State) -> State:
        """
        调用子图（AutoDeploy 或 Trace_Agent）：
        1. 根据子图类型选择端口
        2. 提取用户的倒数第二条消息作为输入
        3. 发送请求到子图服务
        4. 更新状态
        """
        # 子图到端口的映射
        subgraph_port_map = {"Trace_Agent": "1111", "true": "7107"}
        subgraph_value = state.get("subgraph")
        port = subgraph_port_map.get(subgraph_value, None)
        
        # 获取人类消息列表
        human_msgs = [m for m in state["messages"] if isinstance(m, HumanMessage)]
        print("human mes inall Sub", human_msgs)
        
        # 提取倒数第二条消息作为输入（最后一条可能是系统消息）
        last_msg = human_msgs[-2].content if len(human_msgs) >= 2 else "what kind of information I should provide"
        session_id = state["session_id"]

        # 构造请求
        payload = {"input": last_msg, "session_id": session_id}
        url = f"http://0.0.0.0:{port}/run_test/"
        try:
            # 调用子图服务
            final_response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                stream=True
            )
            content = final_response.text
            print(content)
            data = json.loads(content)
            
            # 提取子图返回的信息
            ai_response = data.get("AI_Response", "")
            thinking = data.get("Thinking", "")
            human_in_the_loop = data.get("human_in_the_loop", "")
            
            # 更新状态（累加 Thinking）
            state["Thinking"] = state.get("Thinking", "") + thinking
            state["AI_Response"] = ai_response
            state["human_in_the_loop"] = human_in_the_loop
            print("[debug]state in info node", state)
            
            return {
                "Thinking": state["Thinking"],
                "AI_Response": state["AI_Response"],
                "human_in_the_loop": state["human_in_the_loop"],
            }
        except Exception as e:
            print("请求出错:", e)

    # ==================== 子图第二阶段调用节点 ====================
    async def call_subgraph_sec(state: State) -> State:
        """
        子图的第二次调用（用户提供额外信息后）：
        1. 中断流程，等待用户输入
        2. 将用户输入发送给子图
        3. 更新状态
        """
        # 子图到端口的映射
        subgraph_port_map = {"Trace_Agent": "1111", "true": "7107"}
        subgraph_value = state.get("subgraph")
        port = subgraph_port_map.get(subgraph_value, None)
        print("state in call_subgraph_sec", state)
        
        # 中断流程，等待用户输入
        human_input = interrupt({"text_to_revise": "call_subgraph_sec"})
        session_id = state["session_id"]
        
        # 构造请求
        payload = {"input": human_input, "session_id": session_id}
        url = f"http://0.0.0.0:{port}/run_test/"
        try:
            # 调用子图服务
            final_response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                stream=True
            )
            content = final_response.text
            print("response from AD", content)
            data = json.loads(content)
            
            # 提取子图返回的信息
            ai_response = data.get("AI_Response", "")
            thinking = data.get("Thinking", "")
            human_in_the_loop = data.get("human_in_the_loop", "")
            
            # 更新状态（累加 Thinking）
            state["Thinking"] = state.get("Thinking", "") + thinking
            state["AI_Response"] = ai_response
            state["human_in_the_loop"] = human_in_the_loop
            print("[debug]state in sec sub", state)
            
            return {
                "Thinking": state["Thinking"],
                "AI_Response": state["AI_Response"],
                "human_in_the_loop": state["human_in_the_loop"],
            }
        except Exception as e:
            print("请求出错:", e)

    # ==================== 核心 LLM 推理节点 ====================
    async def info_node(state: State) -> State | Command:
        """
        核心 LLM 推理节点：
        1. 清空旧图片
        2. 调用 LLM 进行推理
        3. 解析 LLM 输出（提取 [Thinking] 和 [FinalAnswer]）
        4. 清洗输出中的图片链接
        5. 更新状态
        """
        global global_log
        start_time = time.time()
        
        # 🔧 每次进入 info_node 清空旧图片
        state["tool_images"] = []
        
        print("Thinking in the info nodem,", state["Thinking"])
        
        # 创建 LLM 实例并绑定工具
        llm = await create_llm()
        llm_with_tools = llm.bind_tools(all_tools)
        print("LLM Config:", llm_with_tools.dict())
        
        # 如果消息列表中没有系统消息，添加系统提示
        if not any(isinstance(m, SystemMessage) for m in state["messages"]):
            messages = [SystemMessage(content=template)] + state["messages"]
            state["messages"].insert(0, SystemMessage(content=template))
        else:
            messages = state["messages"]
        
        # 检查最后一条 AI 消息是否为空
        last_ai_message = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        if last_ai_message is None or last_ai_message.content.strip() == "":
            # 直接调用 LLM
            response = await llm_with_tools.ainvoke(state["messages"])
        else:
            # 中断流程，等待用户输入
            value = interrupt({"text_to_revise": "interrup in Info"})
            if not any(isinstance(m, SystemMessage) for m in state["messages"]):
                state["messages"].insert(0, SystemMessage(content=template))
            state["messages"].append(HumanMessage(content=str(value)))
            response = await llm_with_tools.ainvoke(state["messages"])
        
        # 确保 response 有 content 属性
        response.content = response.content if hasattr(response, "content") else str(response)
        
        # 使用正则提取 [Thinking] 内容
        reasoning_match = re.search(
            r"\[(?:Reasoning|Thinking)\]\s*(.*?)\s*(?=\[FinalAnswer\]|\Z)",
            response.content,
            re.S | re.I
        )
        reasoning = reasoning_match.group(1).strip() if reasoning_match else ""
        
        end_time = time.time()
        print(f"⏱ get AI () response: {end_time - start_time:.3f} 秒")
        
        # 使用正则提取 [FinalAnswer] 内容
        final_answer_match = re.search(
            r'\[FinalAnswer\]\s*(.*?)(?=\n\[\w+\]|\Z)',
            response.content,
            re.S | re.I
        )
        final_answer = final_answer_match.group(1).strip() if final_answer_match and final_answer_match.group(1).strip() else response.content.strip()
        
        # 清理多余空行
        reasoning = "\n".join(line.strip() for line in reasoning.splitlines() if line.strip())
        final_answer = "\n".join(line.strip() for line in final_answer.splitlines() if line.strip())
        
        # 清洗文本，提取图片链接
        cleaned_answer, answer_images = sanitise_text_field(final_answer)
        
        # 🔧 直接赋值本轮图片，不累加
        tool_images = answer_images if answer_images else []
        
        print("Tool Images =>", tool_images)
        final_answer_to_log = cleaned_answer or final_answer
        
        # 记录到全局日志
        global_log["AI_Response"].append(final_answer_to_log)
        global_log["Thinking"].append(reasoning)

        # 检查是否需要路由到子图
        contains_subgraph = "subgraph" in (response.content or "").lower()
        subgraph_flag = "true" if contains_subgraph else state.get("subgraph", "false")
        if "Trace_Agent" in final_answer_to_log:
            subgraph_flag = "Trace_Agent"
        
        print("Global log in infor node is,", global_log)
        
        # 累加 Thinking 内容
        if reasoning:
            state["Thinking"] = state.get("Thinking", "") + f"\n\n🤔Thinking:\n\n{reasoning}\n"
        state["AI_Response"] = final_answer_to_log
        print("Thinking in the info nodem,", state["Thinking"])
        
        # 返回更新后的状态
        return {
            "messages": messages + [response],
            "subgraph": subgraph_flag,
            "Thinking": state["Thinking"],
            "AI_Response": state["AI_Response"],
            "tool_images": tool_images,
        }

    # ==================== 工具结果处理节点 ====================
    async def result_processing_node(state):
        """
        处理工具执行结果：
        1. 提取最新的工具消息
        2. 清洗工具输出，提取图片
        3. 根据工具的汇总策略决定是否调用 LLM 进行汇总
        4. 更新状态
        """
        global global_log
        messages = state.get("messages", [])
        
        # 从消息列表中提取最新的工具消息
        latest_tool_message = next((m for m in reversed(messages) if isinstance(m, ToolMessage)), None)

        # 🔧 工具消息处理函数：清洗内容并提取图片
        def _prepare_tool_payload(msg: ToolMessage | None) -> tuple[str, list[dict[str, str]], str | None]:
            """
            处理工具消息：
            - 清洗文本内容
            - 提取图片链接
            - 返回：(清洗后的文本, 图片列表, 工具名称)
            """
            if msg is None:
                return "", [], None
            
            tool_name = getattr(msg, "name", None)
            raw_content = msg.content or ""
            
            # 调用工具输出处理函数
            cleaned_text, images, _ = process_tool_message(tool_name, raw_content)
            
            # 如果没有清洗后的文本但有图片，设置默认提示
            if cleaned_text:
                sanitised = cleaned_text
            elif images:
                sanitised = "An image or chart has been generated."
            else:
                sanitised = raw_content or ""
            
            # 尝试更新消息内容
            try:
                msg.content = sanitised
            except Exception:
                pass
            
            return sanitised, images, tool_name

        # 处理工具消息
        sanitised_content, payload_images, tool_name = _prepare_tool_payload(latest_tool_message)
        
        # 🔧 只保留本轮工具生成的图片
        tool_images = payload_images if payload_images else []

        # 如果没有工具消息，直接返回
        if latest_tool_message is None:
            return {
                "messages": state["messages"],
                "Thinking": state.get("Thinking", ""),
                "AI_Response": state.get("AI_Response", ""),
                "human_in_the_loop": state.get("human_in_the_loop", ""),
                "tool_images": tool_images,
            }

        # 获取工具的汇总策略
        summary_strategy = get_summary_strategy(tool_name) if tool_name else "llm_default"

        # 如果策略是 "none"，跳过 LLM 汇总
        if summary_strategy == "none":
            print(f"Skipping LLM summary for tool '{tool_name}' based on strategy.")

            # 格式化工具结果
            final_answer_to_log = (
                "### 🛠️ Tool Execution Result\n\n"
                f"```json\n{sanitised_content}\n```"
            )

            # 更新状态和全局日志
            state["AI_Response"] = final_answer_to_log
            global_log["AI_Response"].append(final_answer_to_log)
            global_log["Human in the Loop"] = []
            state["Thinking"] = state.get("Thinking", "") + "\n\nSkipped LLM summary based on strategy.\n"

            return {
                "messages": state["messages"],
                "Thinking": state["Thinking"],
                "AI_Response": state["AI_Response"],
                "human_in_the_loop": "",
                "tool_images": tool_images,
            }

        # 格式化工具结果供 LLM 分析
        sanitized_output = (
            "### 🛠️ Tool Execution Result\n"
            f"```json\n{sanitised_content}\n```"
        )
        print("latest_tool_message in result_processing_node is", sanitised_content)
        
        # 构造分析请求消息
        analysis_message = {
            "role": "user",
            "content": "Analyze the tool execution result. Rewrite it to make it more readable( (You can Prefix sentence with a decorative symbol such as ✨, 🌸, ➡, or ⭐. and use Markdonw) and concise while preserving all important details."
        }
        
        # 调用 LLM 分析工具结果
        llm = await create_llm()
        response = await llm.ainvoke(messages + [analysis_message])

        # 解析 LLM 响应
        reasoning_match = re.search(
            r"\[(?:Reasoning|Thinking)\]\s*(.*?)\s*(?=\[FinalAnswer\]|\Z)",
            response.content,
            re.S | re.I
        )
        reasoning = reasoning_match.group(1).strip() if reasoning_match else ""
        
        final_answer_match = re.search(
            r"\[FinalAnswer\]\s*(.*?)(?=\n\[\w+\]|\Z)",
            response.content,
            re.S | re.I
        )
        final_answer = final_answer_match.group(1).strip() if final_answer_match and final_answer_match.group(1).strip() else response.content.strip()

        # 清理多余空行
        reasoning = "\n".join(line.strip() for line in reasoning.splitlines() if line.strip())
        final_answer = "\n".join(line.strip() for line in final_answer.splitlines() if line.strip())

        # 清洗 LLM 回复，提取图片
        cleaned_answer, answer_images = sanitise_text_field(final_answer)
        
        # 🔧 如果 LLM 回复也有图片，合并；否则保持工具图片
        if answer_images:
            tool_images = tool_images + answer_images
        
        final_answer_to_log = cleaned_answer or final_answer

        # 更新全局日志
        global_log["AI_Response"].append(final_answer_to_log)
        global_log["Thinking"].append(reasoning)
        global_log["Human in the Loop"] = []

        # 清洗工具输出并累加到 Thinking
        cleaned_tool_text, _ = sanitise_text_field(sanitized_output)
        state["Thinking"] = state.get("Thinking", "") + cleaned_tool_text
        state["AI_Response"] = final_answer_to_log
        print("Thinking in result_processing_node is", state["Thinking"], state["AI_Response"])

        # 返回更新后的状态
        return {
            "messages": state["messages"] + [analysis_message, response],
            "Thinking": state["Thinking"],
            "AI_Response": state["AI_Response"],
            "human_in_the_loop": "",
            "tool_images": tool_images,
        }

    # ==================== 构建状态图 ====================
    # 添加所有节点
    graph_builder.add_node("info", info_node)  # 核心 LLM 推理节点
    tool_node = ToolNode(tools=all_tools)  # 工具执行节点
    graph_builder.add_node("tools", tool_node)
    graph_builder.add_node("subgraph_node", call_subgraph)  # 子图第一次调用
    graph_builder.add_node("call_subgraph_sec", call_subgraph_sec)  # 子图第二次调用
    graph_builder.add_node("human_approval", human_approval)  # 工具调用人工批准
    graph_builder.add_node("human_window", human_window)  # 展示工具调用信息
    graph_builder.add_node("result_processing", result_processing_node)  # 工具结果处理
    graph_builder.add_node("human_approve_sub", human_approve_sub)  # 子图人工批准
    
    # 添加边（定义节点之间的流转）
    graph_builder.add_edge(START, "info")  # 起点 → info 节点
    graph_builder.add_conditional_edges("info", get_state)  # info 节点根据状态路由
    graph_builder.add_edge("human_window", "human_approval")  # 展示工具信息 → 等待人工批准
    graph_builder.add_edge("tools", "result_processing")  # 工具执行 → 结果处理
    graph_builder.add_conditional_edges("subgraph_node", get_state_sub)  # 子图节点根据状态路由
    graph_builder.add_conditional_edges("call_subgraph_sec", get_state_sub)  # 子图第二阶段路由
    graph_builder.add_conditional_edges("human_approve_sub", get_state_sub)  # 子图人工批准路由
    graph_builder.add_edge("result_processing", "info")  # 结果处理 → 返回 info 节点
    
    # 编译状态图（添加内存检查点）
    memory = InMemorySaver()
    graph = graph_builder.compile(checkpointer=memory)

# ==================== API 端点：运行主流程 ====================
@app.post("/run_test/")
async def execute_2(plan: dict):
    """
    主 API 端点，处理用户请求：
    1. 接收用户输入和 session_id
    2. 判断是否首次运行
    3. 流式执行状态图
    4. 提取最终结果并返回
    """
    global graph
    global global_log
    
    # 重置全局日志
    global_log = {
        "AI_Response": [], "Thinking": [], "Human in the Loop": [], "subgraph": [], "Tool Message": [], "Tool Images": [],
    }
    
    set_debug(True)
    print("\n=== Received from frontend ===")
    print(plan)
    
    # 提取参数
    thread_id = plan.get("session_id", "default_thread")
    user_input = plan.get("input", "").strip()
    print("user input after plan", user_input)
    
    # 配置线程 ID
    config = {"configurable": {"thread_id": thread_id}}
    print("config is", config)
    
    results = []
    first_run = thread_id not in thread_state

    # 首次运行：初始化状态并开始流式执行
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
    else:
        # 后续运行：恢复流程
        print("run into second ")
        command = Command(resume=user_input)
        stream = graph.astream(command, config=config)
    
    # 动态变量存储（用于提取最终结果）
    dynamic_vars = {"tool_images": []}
    ai_field = f"{thread_id}_AI_Response"
    thinking_field = f"{thread_id}_Thinking"
    human_in_the_loop_field = f"{thread_id}_human_in_the_loop"
    results = []
    
    # 递归查找字典中的值
    def find_value(d, key):
        """在嵌套字典/列表中查找指定键的值"""
        if isinstance(d, dict):
            if key in d:
                return d[key]
            for v in d.values():
                result = find_value(v, key)
                if result is not None:
                    return result
        elif isinstance(d, list):
            for item in d:
                result = find_value(item, key)
                if result is not None:
                    return result
        return None
    
    # 流式执行状态图，收集所有输出
    async for output in stream:
        if output:
            results.append(output)
    
    print("=== Current results ===")
    
    # 初始化动态变量
    for idx, item in enumerate(results, start=1):
        dynamic_vars[ai_field] = ""
        dynamic_vars[thinking_field] = ""
        dynamic_vars[human_in_the_loop_field] = ""
    
    # 从最后一个结果反向查找最新的 AI 响应
    for target in reversed(results):
        ai_response = find_value(target, "AI_Response")
        human_in_the_loop_content = find_value(target, "human_in_the_loop")
        if ai_response:
            thinking = find_value(target, "Thinking")
            dynamic_vars[ai_field] = ai_response
            dynamic_vars[thinking_field] = thinking or ""
            dynamic_vars[human_in_the_loop_field] = human_in_the_loop_content
            break
    
    # 提取工具图片
    tool_images_value = find_value(target, "tool_images")
    if tool_images_value is not None:
        dynamic_vars["tool_images"] = tool_images_value

    print("dynamic_vars[thinking_field] inCurrent results 1", dynamic_vars[thinking_field])
    
    # 构造响应
    response_payload = {
        "session_id": thread_id,
        "AI_Response": dynamic_vars[ai_field],
        "Thinking": dynamic_vars[thinking_field],
        "human_in_the_loop": dynamic_vars[human_in_the_loop_field],
        "tool_images": dynamic_vars.get("tool_images", []),
    }
    print("[run response]", json.dumps(response_payload, ensure_ascii=False))
    return response_payload

# ==================== API 端点：处理人工干预 ====================
@app.post("/modify_test/")
async def execute_hil(plan: dict):
    """
    处理人工干预（Human-in-the-Loop）的 API 端点：
    1. 接收用户的批准/拒绝指令
    2. 恢复流程执行
    3. 返回最终结果
    """
    global graph
    global global_log
    
    # 重置全局日志
    global_log = {
        "AI_Response": [], "Thinking": [], "Human in the Loop": [], "subgraph": [], "Tool Message": [], "Tool Images": [],
    }
    
    set_debug(True)
    print("\n=== Human in the Loop ===")
    print(plan)
    
    # 提取参数
    thread_id = plan.get("session_id", "default_thread")
    user_input = plan.get("input", "").strip()
    config = {"configurable": {"thread_id": thread_id}}
    
    # 动态变量存储
    dynamic_vars = {"tool_images": []}
    ai_field = f"{thread_id}_AI_Response"
    thinking_field = f"{thread_id}_Thinking"
    human_in_the_loop_field = f"{thread_id}_human_in_the_loop"

    # 解析用户指令并构造 Command
    command = None
    user_input_lower = user_input.lower()
    if user_input_lower == "accept":
        command = Command(resume={"type": "accept"})
    elif user_input_lower.startswith("edit"):
        # 编辑模式（当前未使用）
        new_name = user_input.split("=", 1)[-1].strip()
        command = Command(resume={"type": "edit", "args": {"hotel_name": new_name}})
    elif user_input_lower == "reject":
        command = Command(resume={"type": "reject"})
    
    results = []
    if command:
        # 恢复流程执行
        stream = graph.astream(command, config=config)
        
        # 递归查找函数（同上）
        def find_value(d, key):
            if isinstance(d, dict):
                if key in d:
                    return d[key]
                for v in d.values():
                    result = find_value(v, key)
                    if result is not None:
                        return result
            elif isinstance(d, list):
                for item in d:
                    result = find_value(item, key)
                    if result is not None:
                        return result
            return None
        
        # 流式执行并收集结果
        async for output in stream:
            if output:
                results.append(output)
        
        print("=== Current results ===")
        for idx, item in enumerate(results, start=1):
            print(f"result{idx} =", item)
        print("=======================")
        
        # 初始化动态变量
        dynamic_vars[ai_field] = ""
        dynamic_vars[thinking_field] = ""
        dynamic_vars[human_in_the_loop_field] = ""

        # 从最后一个结果反向查找最新的 AI 响应
        for target in reversed(results):
            ai_response = find_value(target, "AI_Response")
            human_in_the_loop_content = find_value(target, "human_in_the_loop")
            if ai_response:
                thinking = find_value(target, "Thinking")
                dynamic_vars[ai_field] = ai_response
                dynamic_vars[thinking_field] = thinking or ""
                dynamic_vars[human_in_the_loop_field] = human_in_the_loop_content
                break
        
        # 提取工具图片
        tool_images_value = find_value(target, "tool_images")
        if tool_images_value is not None:
            dynamic_vars["tool_images"] = tool_images_value

    # 构造响应
    response_payload = {
        "session_id": thread_id,
        "AI_Response": dynamic_vars[ai_field],
        "Thinking": dynamic_vars[thinking_field],
        "human_in_the_loop": dynamic_vars[human_in_the_loop_field],
        "tool_images": dynamic_vars.get("tool_images", []),
    }
    print("[modify response]", json.dumps(response_payload, ensure_ascii=False))
    return response_payload

# ==================== 应用入口 ====================
if __name__ == "__main__":
    import uvicorn
    # 启动 FastAPI 应用
    # - host="0.0.0.0": 监听所有网络接口
    # - port=878: 监听 878 端口
    # - reload=True: 代码更改时自动重载
    uvicorn.run("router_collect2_EAI_zhenyu:app", host="0.0.0.0", port=878, reload=True)