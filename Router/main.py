

from typing import Annotated
from langchain_core.tools import tool
from typing_extensions import TypedDict
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command, interrupt
from ericai_llm_async import llm as create_llm
from langchain.globals import set_verbose
from langchain.globals import set_debug
from langchain_core.messages import SystemMessage
from typing import Literal
from langgraph.graph import END
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
import pprint
import asyncio
from fastapi import FastAPI, Request
import os
from langchain_openai import ChatOpenAI
import subprocess
import httpx
from MCP_Client import create_mcp_client
import re
from fastapi.middleware.cors import CORSMiddleware
from langchain_mcp_adapters.client import MultiServerMCPClient
import json
from operator import xor
import time
import requests
import json
from Azure import llm as create_llm2
from microsoft_token import get_MS_access_token
from message_trimmer  import MessageTrimmer

# === Universal Orchestrator imports ========================================
from universal_orchestrator import UniversalOrchestrator, is_orchestration_query
# ============================================================================

# === helper imports for tool output ========================================
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
from utils.tool_output import process_tool_message, sanitise_text_field, get_summary_strategy
# ============================================================================


file_path = "/mnt/openai_key/shared_token.txt"
subgraph_processing=False
thread_state = {}
universal_orchestrator = None  # Global orchestrator instance
class Json_Schema(TypedDict):
    operation: str
    hardware_name: str
    UP_version: str
    Tags: str | None
    Scenario_for_tags: str | None
    Netconf: str | None
    Post_step: str | None

global_log = {
    "AI_Response": [],
    "Thinking": [],
    "Human in the Loop": [],
    "subgraph": [],
    "Tool Message": [],
    "Tool Images": [],
}
subgraph_processing_dictionary= {"default_id":False}



app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本地调试用，部署时需指定
    allow_methods=["*"],
    allow_headers=["*"]
)
template=(
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

class State(TypedDict):
    messages: Annotated[list, add_messages]
    subgraph: str
    AI_Response: str
    Thinking: str
    human_in_the_loop: str
    json_result: Json_Schema
    session_id: str
    tool_images: list[dict[str, str]]
    
graph_builder = StateGraph(State)

def get_state(state: State) -> Literal["human_window", "subgraph_node", "info", "__end__","tools"]:
    messages = state["messages"]
    print("subgraph in get stats1,",state["subgraph"])
    
    if state.get("subgraph") in ["true", "Trace_Agent"]:
        print("subgraph in get stats2,",state["subgraph"])
        return "subgraph_node"
    if not messages:
        return "info"
    if isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
        ai_message = next((m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None)
        calls = ai_message.tool_calls
        tool_names = [c['name'] for c in calls]
        base_auto_tools = {
            "get_latest_UP_version",
            "check_UP_number",
            "DU_Name_IP_Mapping",
            "extract_rrc_msgs",
            "query_jira_issues",
            "get_issue_statistics",
        }

        def _is_auto_tool(name: str) -> bool:
            if name in base_auto_tools:
                return True
            try:
                return get_summary_strategy(name) == "none"
            except Exception:
                return False

        if any(_is_auto_tool(name) for name in tool_names):
            print("Approved Tools No HIL")
            return "tools"
        else:
            return "human_window"

    elif not isinstance(messages[-1], HumanMessage):
        return "info"
    return "info"


def get_state_sub(state: State) -> Literal["human_approve_sub", "call_subgraph_sec","info"]:
    human_status = state["human_in_the_loop"]
    ai_message=state["AI_Response"]
    print("ai_message in get_state_sub",ai_message)
    keywords = [
    "Jenkins",
    "Seems you reject the request, Please tell me if everything I can do for you"
]
    if human_status:
        print("human_status is",human_status)
        return "human_approve_sub"

    if isinstance(ai_message, str) and any(keyword in ai_message for keyword in keywords):
        return "info"
    else:
        return "call_subgraph_sec"


def human_approve_sub(state: State):
    subgraph_port_map = {
            "Trace_Agent": "1111",
            "true": "7107"
        }
    subgraph_value = state.get("subgraph")
    port = subgraph_port_map.get(subgraph_value, None)
    print("port in human_approve_sub " ,port)
    session_id = state["session_id"]
    resume_data  = interrupt(
                {
                    "question": "Is this correct?",
                }
            )
    resume_type = resume_data.get("type")
    print("resume type is",resume_type)
    if resume_type == "accept":  
        payload = {
        "input": "accept",
        "session_id": session_id
    }
        url = f"http://0.0.0.0:{port}/modify/"
        try:
            final_response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                stream=True
            )
            print("final_response is",final_response)
            content = final_response.text
            print(content)
            data = json.loads(content)
            ai_response = data.get("AI_Response", "")
            thinking = data.get("Thinking", "")
            human_in_the_loop = data.get("human_in_the_loop", "")
    
            state["Thinking"]=state.get("Thinking", "") + thinking
            state["AI_Response"]=ai_response
            state["human_in_the_loop"]=human_in_the_loop
            state["subgraph"]=""
            print("[debug]state in info node", state)

            return Command(update={"AI_Response": state["AI_Response"], "Thinking": state["Thinking"], "human_in_the_loop": state["human_in_the_loop"],"subgraph": state["subgraph"]})

        except Exception as e:
            print("请求出错:", e)
    elif resume_type == "reject":
        payload = {
        "input": "reject",
        "session_id": session_id
    }
        url = f"http://0.0.0.0:{port}/modify/"
        try:
            final_response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                stream=True
            )
            print("final_response is",final_response)
            content = final_response.text
            print(content)
            data = json.loads(content)
            ai_response = data.get("AI_Response", "")
            thinking = data.get("Thinking", "")
            human_in_the_loop = data.get("human_in_the_loop", "")
    
            state["Thinking"]=thinking
            state["AI_Response"]=ai_response
            state["subgraph"]=""
            state["human_in_the_loop"]=human_in_the_loop
            print("[debug]state in info node", state)
            return Command(update={"AI_Response": state["AI_Response"], "Thinking": state["Thinking"], "human_in_the_loop": state["human_in_the_loop"],"subgraph": state["subgraph"]})
        except Exception as e:
            print("请求出错:", e)
            ai_response = "Seems something wrong when reject the request,back to the receptionist and you can post your request  "
            state["AI_Response"]=ai_response
            print("[debug]state in info node", state)
            return Command(update={"AI_Response": state["AI_Response"], "Thinking": "", "subgraph": ""},  goto="info")
    else:
        return Command(goto="info")


def human_window(state: State):
    messages = state["messages"]
    if isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
        ai_message = next((m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None)
        calls = ai_message.tool_calls
        calling_output = "\n".join([f"Please approve the execution of function : {c['name']} using ({c['args']})" for c in calls])

        return { "AI_Response": "Tool Calling","human_in_the_loop": calling_output}


def human_approval(state: State) -> Command[Literal["tools", "info"]]:
    ai_message = next((m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None)
    if ai_message is None:
        raise ValueError("No AIMessage found in state['messages'].")
    if ai_message.tool_calls:
        calls = ai_message.tool_calls
        llm_output = "\n".join([f"Please approve the execution of function : {c['name']} using ({c['args']})" for c in calls])
    else:
        llm_output = "<no tool calls found>"

    resume_data  = interrupt({"question": llm_output})
    resume_type = resume_data.get("type")
    print("resume type is",resume_type)
    if resume_type == "accept":
        return Command(goto="tools")
    elif resume_type == "reject":
        state["AI_Response"]="Seems you reject the request, Please tell me if everything I can do for you"
        return Command(update={"AI_Response": state["AI_Response"]},goto="info")
    else:
        return Command(goto="info")

#client = create_mcp_client()
fault_tolerant_client = create_mcp_client()
@app.on_event("startup")
async def startup_event():
    global graph
    global subgraph
    global fault_tolerant_client
    global universal_orchestrator  # Add global orchestrator

    mcp_tools = await fault_tolerant_client.get_tools()
    all_tools = list(mcp_tools)

    # Initialize Universal Orchestrator
    try:
        base_path = Path(__file__).parent
        universal_orchestrator = UniversalOrchestrator(all_tools)
        universal_orchestrator.load_metadata(str(base_path / "mcp_tools_metadata.yaml"))
        universal_orchestrator.load_rules(str(base_path / "orchestration_rules.yaml"))
        print(f"✅ Universal Orchestrator initialized with {len(universal_orchestrator.rules)} rules")
    except Exception as e:
        print(f"⚠️  Universal Orchestrator initialization failed: {e}")
        universal_orchestrator = None 


    async def call_subgraph(state: State) -> State:
        subgraph_port_map = { "Trace_Agent": "1111", "true": "7107" }
        subgraph_value = state.get("subgraph")
        port = subgraph_port_map.get(subgraph_value, None)
        human_msgs = [m for m in state["messages"] if isinstance(m, HumanMessage)]
        print("human mes inall Sub",human_msgs)
        last_msg = human_msgs[-2].content if len(human_msgs) >= 2 else "what kind of information I should provide"
        session_id = state["session_id"]

        payload = { "input": last_msg, "session_id": session_id }
        url = f"http://0.0.0.0:{port}/run/"
        try:
            final_response = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(payload), stream=True)
            content = final_response.text
            print(content)
            data = json.loads(content)
            ai_response = data.get("AI_Response", "")
            thinking = data.get("Thinking", "")
            human_in_the_loop = data.get("human_in_the_loop", "")
            state["Thinking"]=state.get("Thinking", "") + thinking
            state["AI_Response"]=ai_response
            state["human_in_the_loop"]=human_in_the_loop
            print("[debug]state in info node", state)
            return {
                "Thinking": state["Thinking"], "AI_Response": state["AI_Response"], "human_in_the_loop": state["human_in_the_loop"],          
            }
        except Exception as e:
            print("请求出错:", e)


    async def call_subgraph_sec(state: State) -> State:
        subgraph_port_map = { "Trace_Agent": "1111", "true": "7107" }
        subgraph_value = state.get("subgraph")
        port = subgraph_port_map.get(subgraph_value, None)
        print("state in call_subgraph_sec",state)
        human_input = interrupt({ "text_to_revise": "call_subgraph_sec" })
        session_id = state["session_id"]
        payload = { "input": human_input, "session_id": session_id }
        url = f"http://0.0.0.0:{port}/run/"
        try:
            final_response = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(payload), stream=True)
            content = final_response.text
            print("response from AD",content)
            data = json.loads(content)
            ai_response = data.get("AI_Response", "")
            thinking = data.get("Thinking", "")
            human_in_the_loop = data.get("human_in_the_loop", "")
            state["Thinking"]=state.get("Thinking", "") + thinking
            state["AI_Response"]=ai_response
            state["human_in_the_loop"]=human_in_the_loop
            print("[debug]state in sec sub", state)
            return {
                "Thinking": state["Thinking"], "AI_Response": state["AI_Response"], "human_in_the_loop": state["human_in_the_loop"],          
            }
        except Exception as e:
            print("请求出错:", e)

    async def info_node(state: State) -> State | Command:
        global global_log
        global universal_orchestrator
        start_time = time.time()

        # 🔧 BUG FIX 1: 每次进入 info_node 清空旧图片
        state["tool_images"] = []

        print("Thinking in the info nodem,",state["Thinking"])
        #llm = await create_llm()
        JWT_TOKEN=get_MS_access_token()
        #print("API_Key:", JWT_TOKEN)
        llm = await create_llm2(JWT_TOKEN)
        #llm = await create_llm()
        try:
            print("Health check of the LLM")
            response = await llm.ainvoke("ping")
        except Exception as e:
            llm = await create_llm()

        # ============================================================
        # 🎭 Universal MCP Orchestration Detection
        # ============================================================
        human_msgs = [m for m in state["messages"] if isinstance(m, HumanMessage)]

        # Only detect on first user input (not after interrupt)
        last_ai_message = next((m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None)
        is_first_input = last_ai_message is None or last_ai_message.content.strip() == ""

        if human_msgs and is_first_input and universal_orchestrator:
            latest_query = human_msgs[-1].content

            # Check if orchestration is needed
            if is_orchestration_query(latest_query, universal_orchestrator):
                print(f"🎭 Orchestration detected for query: {latest_query[:50]}...")

                try:
                    # Execute orchestration
                    orchestration_result = await universal_orchestrator.orchestrate(
                        query=latest_query,
                        llm=llm
                    )

                    if orchestration_result and orchestration_result.get("orchestration_executed"):
                        print(f"✅ Orchestration completed: {orchestration_result['tasks_count']} tasks executed")

                        formatted_output = orchestration_result["formatted_output"]

                        # Update global_log
                        global_log["AI_Response"].append(formatted_output)
                        global_log["Thinking"].append(
                            f"🎭 Universal Orchestration: {orchestration_result['rule_matched']}, "
                            f"{orchestration_result['tasks_count']} tasks executed"
                        )

                        # Construct response message
                        response_message = AIMessage(content=formatted_output)

                        # Return orchestration result (no State structure changes)
                        return {
                            "messages": state["messages"] + [response_message],
                            "subgraph": state.get("subgraph", "false"),
                            "Thinking": state.get("Thinking", "") + f"\n\n🎭 Orchestration: {orchestration_result['rule_matched']}\n",
                            "AI_Response": formatted_output,
                            "tool_images": state.get("tool_images", []),
                        }

                except Exception as e:
                    print(f"⚠️  Orchestration failed: {e}, falling back to normal LLM flow")
                    # If orchestration fails, continue to normal flow

        # ============================================================
        # Normal LLM Flow (original logic)
        # ============================================================
        llm_with_tools = llm.bind_tools(all_tools)
        print("LLM Config:", llm_with_tools.dict())
        if not any(isinstance(m, SystemMessage) for m in state["messages"]):
            messages = [SystemMessage(content=template)] + state["messages"]
            state["messages"].insert(0, SystemMessage(content=template))
        else:
            messages = state["messages"]
        last_ai_message = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)


        print("Debug message befor trim",state["messages"])
        print("---------------------------------------------------------------------------")
        trimmer = MessageTrimmer()
        state["messages"] = trimmer.trim_messages_of_llm(state["messages"], "gpt-4")
        print("Debug message after trim",state["messages"])

        if last_ai_message is None or last_ai_message.content.strip() == "":
            response = await llm_with_tools.ainvoke(state["messages"])
        else:
            value = interrupt({ "text_to_revise": "interrup in Info" })
            if not any(isinstance(m, SystemMessage) for m in state["messages"]):
                state["messages"].insert(0, SystemMessage(content=template))
            state["messages"].append(HumanMessage(content=str(value)))
            response = await llm_with_tools.ainvoke(state["messages"])
        
        response.content = response.content if hasattr(response, "content") else str(response)
        reasoning_match = re.search(r"\[(?:Reasoning|Thinking)\]\s*(.*?)\s*(?=\[FinalAnswer\]|\Z)", response.content, re.S | re.I)
        reasoning = reasoning_match.group(1).strip() if reasoning_match else ""
        end_time = time.time()
        print(f"⏱ get AI () response: {end_time - start_time:.3f} 秒")
        final_answer_match = re.search(r'\[FinalAnswer\]\s*(.*?)(?=\n\[\w+\]|\Z)', response.content, re.S | re.I)
        final_answer = final_answer_match.group(1).strip() if final_answer_match and final_answer_match.group(1).strip() else response.content.strip()
        
        reasoning = "\n".join(line.strip() for line in reasoning.splitlines() if line.strip())
        final_answer = "\n".join(line.strip() for line in final_answer.splitlines() if line.strip())
        
        cleaned_answer, answer_images = sanitise_text_field(final_answer)
        
        # 🔧 BUG FIX 2: 直接赋值本轮图片，不累加
        tool_images = answer_images if answer_images else []
        
        print("Tool Images =>", tool_images)
        final_answer_to_log = cleaned_answer or final_answer
        global_log["AI_Response"].append(final_answer_to_log)
        global_log["Thinking"].append(reasoning)

        contains_subgraph = "subgraph" in (response.content or "").lower()
        subgraph_flag = "true" if contains_subgraph else state.get("subgraph", "false")
        if "Trace_Agent" in final_answer_to_log:
            subgraph_flag = "Trace_Agent"
        
        print("Global log in infor node is,",global_log)
        if reasoning:
            state["Thinking"] = state.get("Thinking", "") + f"\n\n🤔Thinking:\n\n{reasoning}\n"
        state["AI_Response"]=final_answer_to_log
        print("Thinking in the info nodem,",state["Thinking"])  
        return {
            "messages": messages + [response],
            "subgraph": subgraph_flag,
            "Thinking": state["Thinking"],
            "AI_Response": state["AI_Response"],
            "tool_images": tool_images,
        }

    async def result_processing_node(state):
        global global_log
        messages = state.get("messages", [])
        latest_tool_message = next((m for m in reversed(messages) if isinstance(m, ToolMessage)), None)

        # 🔧 BUG FIX 3: 不继承旧图，直接从零开始
        def _prepare_tool_payload(msg: ToolMessage | None) -> tuple[str, list[dict[str, str]], str | None]:
            if msg is None:
                return "", [], None
            tool_name = getattr(msg, "name", None)
            raw_content = msg.content or ""
            cleaned_text, images, _ = process_tool_message(tool_name, raw_content)
            if cleaned_text:
                sanitised = cleaned_text
            elif images:
                sanitised = "An image or chart has been generated."
            else:
                sanitised = raw_content or ""
            try:
                msg.content = sanitised
            except Exception:
                pass
            return sanitised, images, tool_name

        sanitised_content, payload_images, tool_name = _prepare_tool_payload(latest_tool_message)
        
        # 🔧 BUG FIX 4: 只保留本轮工具生成的图片
        tool_images = payload_images if payload_images else []

        if latest_tool_message is None:
            return {
                "messages": state["messages"],
                "Thinking": state.get("Thinking", ""),
                "AI_Response": state.get("AI_Response", ""),
                "human_in_the_loop": state.get("human_in_the_loop", ""),
                "tool_images": tool_images,
            }

        summary_strategy = get_summary_strategy(tool_name) if tool_name else "llm_default"

        if summary_strategy == "none":
            print(f"Skipping LLM summary for tool '{tool_name}' based on strategy.")

            final_answer_to_log = (
                "### 🛠️ Tool Execution Result\n\n"
                f"```json\n{sanitised_content}\n```"
            )

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

        sanitized_output = (
            "### 🛠️ Tool Execution Result\n"
            f"```json\n{sanitised_content}\n```"
        )
        print("latest_tool_message in result_processing_node is", sanitised_content)
        analysis_message = {
            "role": "user",
            "content": "Analyze the tool execution result. Rewrite it to make it more readable( (You can Prefix sentence with a decorative symbol such as ✨, 🌸, ➡, or ⭐. and use Markdonw) and concise while preserving all important details."
        }
        #llm = await create_llm()
        JWT_TOKEN=get_MS_access_token()
        #print("API_Key:", JWT_TOKEN)
        llm = await create_llm2(JWT_TOKEN)
        #llm = await create_llm()
        try:
            print("Health check of the LLM")
            response = await llm.ainvoke("ping")
        except Exception as e:
            llm = await create_llm()
        response = await llm.ainvoke(messages + [analysis_message])

        reasoning_match = re.search(r"\[(?:Reasoning|Thinking)\]\s*(.*?)\s*(?=\[FinalAnswer\]|\Z)", response.content, re.S | re.I)
        reasoning = reasoning_match.group(1).strip() if reasoning_match else ""
        final_answer_match = re.search(r"\[FinalAnswer\]\s*(.*?)(?=\n\[\w+\]|\Z)", response.content, re.S | re.I)
        final_answer = final_answer_match.group(1).strip() if final_answer_match and final_answer_match.group(1).strip() else response.content.strip()

        reasoning = "\n".join(line.strip() for line in reasoning.splitlines() if line.strip())
        final_answer = "\n".join(line.strip() for line in final_answer.splitlines() if line.strip())

        cleaned_answer, answer_images = sanitise_text_field(final_answer)
        
        # 🔧 BUG FIX 5: 如果 LLM 回复也有图片，合并；否则保持工具图片
        if answer_images:
            tool_images = tool_images + answer_images
        
        final_answer_to_log = cleaned_answer or final_answer

        global_log["AI_Response"].append(final_answer_to_log)
        global_log["Thinking"].append(reasoning)
        global_log["Human in the Loop"] = []

        cleaned_tool_text, _ = sanitise_text_field(sanitized_output)
        state["Thinking"] = state.get("Thinking", "") + cleaned_tool_text
        state["AI_Response"] = final_answer_to_log
        print("Thinking in result_processing_node is", state["Thinking"], state["AI_Response"])

        return {
            "messages": state["messages"] + [analysis_message, response],
            "Thinking": state["Thinking"],
            "AI_Response": state["AI_Response"],
            "human_in_the_loop": "",
            "tool_images": tool_images,
        }

    graph_builder.add_node("info", info_node)
    tool_node = ToolNode(tools=all_tools)
    graph_builder.add_node("tools", tool_node)
    graph_builder.add_node("subgraph_node", call_subgraph)
    graph_builder.add_node("call_subgraph_sec", call_subgraph_sec)
    graph_builder.add_node("human_approval", human_approval)
    graph_builder.add_node("human_window", human_window)
    graph_builder.add_node("result_processing", result_processing_node) 
    graph_builder.add_node("human_approve_sub", human_approve_sub) 
    graph_builder.add_edge(START, "info")
    graph_builder.add_conditional_edges("info", get_state)
    graph_builder.add_edge("human_window", "human_approval")
    graph_builder.add_edge("tools", "result_processing")
    graph_builder.add_conditional_edges("subgraph_node", get_state_sub)
    graph_builder.add_conditional_edges("call_subgraph_sec", get_state_sub)
    graph_builder.add_conditional_edges("human_approve_sub", get_state_sub)
    graph_builder.add_edge("result_processing", "info") 
    
    memory = InMemorySaver()
    graph = graph_builder.compile(checkpointer=memory)

@app.post("/run_test/")
async def execute_2(plan: dict):
    global graph
    global global_log
    global_log = {
        "AI_Response": [], "Thinking": [], "Human in the Loop": [], "subgraph": [], "Tool Message": [], "Tool Images": [],
    }
    set_debug(True)
    print("\n=== Received from frontend ===")
    print(plan)
    thread_id = plan.get("session_id", "default_thread")
    user_input = plan.get("input", "").strip()
    print("user input after plan",user_input)
    config = {"configurable": {"thread_id": thread_id}}
    print("config is",config)
    results = []   
    first_run = thread_id not in thread_state

    if first_run:
        initial_state = { "messages": [HumanMessage(content=user_input)], "AI_Response":"", "Thinking": "", "human_in_the_loop":"", "session_id":thread_id, "tool_images": [] }
        stream = graph.astream(initial_state, config=config, stream_mode="values")
        thread_state[thread_id] = True
    else:
        print("run into second ")
        command = Command(resume=user_input)
        stream = graph.astream(command, config=config)
    
    dynamic_vars = {"tool_images": []}
    ai_field = f"{thread_id}_AI_Response"
    thinking_field = f"{thread_id}_Thinking"
    human_in_the_loop_field=f"{thread_id}_human_in_the_loop"
    results = []
    
    def find_value(d, key):
        if isinstance(d, dict):
            if key in d: return d[key]
            for v in d.values():
                result = find_value(v, key)
                if result is not None: return result
        elif isinstance(d, list):
            for item in d:
                result = find_value(item, key)
                if result is not None: return result
        return None
    
    async for output in stream:
        if output: results.append(output)
    
    print("=== Current results ===")
    for idx, item in enumerate(results, start=1):
        dynamic_vars[ai_field] = ""
        dynamic_vars[thinking_field] = ""
        dynamic_vars[human_in_the_loop_field] = ""
    
    for target in reversed(results):
        ai_response = find_value(target, "AI_Response")
        human_in_the_loop_content=find_value(target, "human_in_the_loop")
        if ai_response:
            thinking = find_value(target, "Thinking")
            dynamic_vars[ai_field] = ai_response
            dynamic_vars[thinking_field] = thinking or ""
            dynamic_vars[human_in_the_loop_field] = human_in_the_loop_content
            break
    
    tool_images_value = find_value(target, "tool_images")
    if tool_images_value is not None:
        dynamic_vars["tool_images"] = tool_images_value

    print("dynamic_vars[thinking_field] inCurrent results 1",dynamic_vars[thinking_field])
    response_payload = {
        "session_id": thread_id,
        "AI_Response": dynamic_vars[ai_field],
        "Thinking": dynamic_vars[thinking_field],
        "human_in_the_loop": dynamic_vars[human_in_the_loop_field],
        "tool_images": dynamic_vars.get("tool_images", []),
    }
    print("[run response]", json.dumps(response_payload, ensure_ascii=False))
    return response_payload
    
@app.post("/modify_test/")
async def execute_hil(plan: dict):
    global graph
    global global_log
    global_log = {
        "AI_Response": [], "Thinking": [], "Human in the Loop": [], "subgraph": [], "Tool Message": [], "Tool Images": [],
    }
    set_debug(True)
    print("\n=== Human in the Loop ===")
    print(plan)
    thread_id = plan.get("session_id", "default_thread")
    user_input = plan.get("input", "").strip()
    config = {"configurable": {"thread_id": thread_id}}
    
    dynamic_vars = {"tool_images": []}
    ai_field = f"{thread_id}_AI_Response"
    thinking_field = f"{thread_id}_Thinking"
    human_in_the_loop_field=f"{thread_id}_human_in_the_loop"

    command = None
    user_input_lower = user_input.lower()
    if user_input_lower == "accept":
        command = Command(resume={"type": "accept"})
    elif user_input_lower.startswith("edit"):
        new_name = user_input.split("=", 1)[-1].strip()
        command = Command(resume={"type": "edit", "args": {"hotel_name": new_name}})
    elif user_input_lower == "reject":
        command = Command(resume={"type": "reject"})
    
    results = []
    if command:
        stream = graph.astream(command, config=config)
        def find_value(d, key):
            if isinstance(d, dict):
                if key in d: return d[key]
                for v in d.values():
                    result = find_value(v, key)
                    if result is not None: return result
            elif isinstance(d, list):
                for item in d:
                    result = find_value(item, key)
                    if result is not None: return result
            return None
            
        async for output in stream:
            if output: results.append(output)
        
        print("=== Current results ===")
        for idx, item in enumerate(results, start=1):
            print(f"result{idx} =", item)
        print("=======================")
        
        dynamic_vars[ai_field] = ""
        dynamic_vars[thinking_field] = ""
        dynamic_vars[human_in_the_loop_field] = ""

        for target in reversed(results):
            ai_response = find_value(target, "AI_Response")
            human_in_the_loop_content=find_value(target, "human_in_the_loop")
            if ai_response:
                thinking = find_value(target, "Thinking")
                dynamic_vars[ai_field] = ai_response
                dynamic_vars[thinking_field] = thinking or ""
                dynamic_vars[human_in_the_loop_field] = human_in_the_loop_content
                break
        
        tool_images_value = find_value(target, "tool_images")
        if tool_images_value is not None:
            dynamic_vars["tool_images"] = tool_images_value

    response_payload = {
        "session_id": thread_id,
        "AI_Response": dynamic_vars[ai_field],
        "Thinking": dynamic_vars[thinking_field],
        "human_in_the_loop": dynamic_vars[human_in_the_loop_field],
        "tool_images": dynamic_vars.get("tool_images", []),
    }
    print("[modify response]", json.dumps(response_payload, ensure_ascii=False))
    return response_payload



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=878, reload=True)