from langchain.callbacks.base import BaseCallbackHandler
from langchain.callbacks.stdout import StdOutCallbackHandler
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
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
import sqlite3
import json
from langchain_core.utils.function_calling import convert_to_openai_function
from pydantic import BaseModel
import pexpect

import json
import os
import time
import pexpect
HISTORY_FILE = "/Router/Trace/History/history.json"
global_log = {
    "AI_Response": [],
    "Thinking": [],
    "Human in the Loop": [],
    "subgraph": [],
    "Tool Message": [],
}


class DebugHandler(BaseCallbackHandler):
    def on_llm_start(self, serialized, prompts, **kwargs):
        print("[DEBUG] LLM Start:", prompts)

    def on_llm_end(self, response, **kwargs):
        print("[DEBUG] LLM End:", response)

    def on_tool_start(self, serialized, input_str, **kwargs):
        print("[DEBUG] Tool Start:", serialized, input_str)

    def on_tool_end(self, output, **kwargs):
        print("[DEBUG] Tool End:", output)

template=('''你是一个智能的设置Trace（本质上是登录硬件，发送命令）的agent， 首先你需要了解用户需要设置什么trace，然后通过调用工具完成命令的发送。命令的结构是  bbte @N log e * {Trace ID}你有以下能力：

1. 可以向用户提问以澄清需求。如果用户询问历史记录，你可以调用load_history工具来查询历史记录。ID
2. 将用户的多条Trace组成一个list。
3. 当你了解用户的想设置的trace以后，你首先调用save_history，将本次执行记录。
4， 调用工具：Trace_Config 当你组成好Trace 的list后，可以使用这个工具设置trace（发送命令），带入IP地址。

背景：

如果用户提及到Golden Trace， 那么是指下列的Trace ID：
UPCUEULNR.206   
UPCUEULNR.155   
UPCUEULNR.156   
UPCUEULNR.291   
UPCUEULNR.292   
UPCUEULNR.293   
DRAULMDBFNR.103 
DRAULMDBFNR.87  
UPCUEDLNR.119   
UPCUEDLNR.193   
DRACTRLMDBFNR.66
DRACTRLMDBFNR.69
DRACTRLMDBFNR.65
DRADLMDBFNR.73  
DRADLMDBFNR.74  
DRADLMDBFNR.71  
DRADLMDBFNR.72  
UPCUEDLNR.172   
UPCUEDLNR.102   


'''
)



class Collect_State(TypedDict):
    messages: Annotated[list, add_messages]
graph_builder = StateGraph(Collect_State)

def get_state_collect(state: Collect_State) -> Literal["human_approval", "info", "__end__",]:
    messages = state["messages"]
    if not messages:
        return "__end__"
    if isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
        return "human_approval"
    elif not isinstance(messages[-1], HumanMessage):
        return "__end__"
    return "info"

def human_approval(state: Collect_State) -> Command[Literal["tools", "info"]]:

    ai_message = next((m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None)

    if ai_message is None:
        raise ValueError("No AIMessage found in state['messages'].")
    if ai_message.tool_calls:
        calls = ai_message.tool_calls
        llm_output = "\n".join([f"Please approve the execution of function : {c['name']} using ({c['args']})" for c in calls])
    else:
        llm_output = "<no tool calls found>"
    global global_log
    global_log["Human in the Loop"].append(llm_output)
    print("Global log in approval",global_log)
    state["human_in_the_loop"]=llm_output
    resume_data  = interrupt(
                {
                    "question": "Is this correct?",
                    # Surface the output that should be
                    # reviewed and approved by the human.
                    "llm_output": llm_output
                }
            )
    resume_type = resume_data.get("type")
    print("resume type is",resume_type)
    if resume_type == "accept":   
        return Command(goto="tools")
    elif resume_type == "reject":
        global_log["Tool Message"].append("Seems you reject the request, Please tell me if everything I can do for you")
        return Command(goto="info")
    else:

        return Command(goto="info")






app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_methods=["*"],
    allow_headers=["*"]
)


def Trace_Config(ip: str, cmds: list, prompt="ok"):
    """
    根据用户提供的IP信息，moshell 到设备，然后 设置Trace（发送命令）
    """
    child = pexpect.spawn(f'./moshell/moshell -v username=muser,password=muser {ip} ', encoding='utf-8', echo=False)
    child.sendline("lt all")
    results = []
    for cmd in cmds:
        print(f"\n[Agent] 执行命令: {cmd}")
        child.sendline(cmd)
        output = []
        last_output_time = time.time()
        error="No valid XBM were found!"
        while True:
            try:
                line = child.readline().strip()
                if line:
                    last_output_time = time.time()
                    output.append(line)
                    print(line)  # 实时打印
                    if (prompt and prompt in line) or (error and error in line):
                        break

                if time.time() - last_output_time > 60:
                    print("⏳ 超过 15s 无新输出，结束本命令")
                    break
 

            except pexpect.EOF:
                print("❌ 子进程退出")
                break
            except pexpect.TIMEOUT:
                continue

        results.append({cmd: output})

    return results

def save_history(ip: str, cmds: list):
    
    """
    保存执行历史 (IP + 命令) 到 JSON 文件
    - 如果文件不存在会创建
    - 如果已有记录会追加，不会清空
    """
    history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            try:
                history = json.load(f)
            except json.JSONDecodeError:
                history = []

    history.append({
        "ip": ip,
        "cmds": cmds,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    })

    # 确保目录存在
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4, ensure_ascii=False)



def load_history(ip: str):
    """
    读取某个 IP 的最后一次历史记录
    """
    if not os.path.exists(HISTORY_FILE):
        print("⚠️ 暂无历史记录")
        return None, None

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)

    if not history:
        print("⚠️ 历史为空")
        return None, None

    # 筛选该 IP 的所有历史
    filtered = [h for h in history if h.get("ip") == ip]
    if not filtered:
        print(f"⚠️ 没有找到 IP {ip} 的历史记录")
        return None, None

    # 取最后一条
    record = filtered[-1]
    return record["ip"], record["cmds"]



@app.on_event("startup")
async def startup_event():
    global graph

    tools = [Trace_Config,save_history,load_history]
    
    async def info_node(state: Collect_State) -> Collect_State | Command:
        global global_log
        global final_template
        llm = await create_llm()
        llm.callbacks = [DebugHandler(), StdOutCallbackHandler()]
        llm_with_tools = llm.bind_tools(tools)
        print("LLM Config:", llm_with_tools.dict())
        if not any(isinstance(m, SystemMessage) for m in state["messages"]):
            messages = [SystemMessage(content=template)] + state["messages"]
        else:
            messages = state["messages"]
        response = llm_with_tools.invoke(messages)
        global_log["AI_Response"].append(f"{response}")
        return {
            "messages": messages + [response],
        }
    async def result_processing_node(state: Collect_State):
        global global_log
        llm = await create_llm()
        messages = state.get("messages", [])
        analysis_message = {
        "role": "user", 
        "content": "Analyze the tool execution result. Rewrite it to make it more readable and concise while preserving all important details. "

        }
        response = llm.invoke(messages + [analysis_message])
        global_log["AI_Response"].append(f"{response}")
        return {"messages": messages + [analysis_message, response]}





    graph_builder.add_node("info", info_node)
    tool_node = ToolNode(tools=tools)
    graph_builder.add_node("human_approval", human_approval)
    graph_builder.add_node("tools", tool_node)
    graph_builder.add_node("result_processing", result_processing_node)


    graph_builder.add_edge(START, "info")
    graph_builder.add_conditional_edges("info", get_state_collect)
    graph_builder.add_edge("tools", "result_processing")


    memory = InMemorySaver()
    graph = graph_builder.compile(checkpointer=memory)


@app.post("/run/")
async def execute_2(plan: dict):
    global subgraph_processing
    global final_template
    #global subgraph_processing_dictionary
    global graph
    global global_log
    global_log = {
        "AI_Response": [],
        "Thinking": [],
        "Human in the Loop": [],
        "subgraph": [],
        "Tool Message": [],
    }
    set_debug(True)
    print("\n=== Received from frontend ===")
    print(plan)
    thread_id = plan.get("session_id", "default_thread")
    user_input = plan.get("input", "").strip()
    config = {"configurable": {"thread_id": thread_id}}


    #subgraph_processing=subgraph_processing_dictionary.get(str(thread_id),False)
    #print(f"{thread_id}\n[debug] subgraph indicator is :{subgraph_processing}")
    #print(str(subgraph_processing_dictionary))
    results = []
    # 只处理普通新对话

    initial_state = {
        "messages": [HumanMessage(content=user_input)],
        "subgraph": "false",
        "log": [],
        "human_in_the_loop":"",
        "session_id":{thread_id},
        
        }

    stream = graph.astream(initial_state, config=config, stream_mode="final")

    #subgraph_processing_dictionary.update({str(thread_id): subgraph_processing})
    #print(f"[debug] {thread_id}\nsubgraph indicator modified to:{subgraph_processing}")
    async for output in stream:
        if output:
            results.append(output)
            # 如果输出里有 tools 消息
            if "tools" in output and "messages" in output["tools"] and len(output["tools"]["messages"]) > 0:
                toolmessage = output["tools"]["messages"][0].content
                if toolmessage:
                    global_log["Tool Message"].append(toolmessage)
    
    print("global_log to front end is", global_log)
    return {
        "session_id": thread_id,
        "global_log": global_log
    }


@app.post("/modify/")
async def execute_hil(plan: dict):
    #global subgraph_processing_dictionary
    
    global graph
    global global_log
    global_log = {
        "AI_Response": [],
        "Thinking": [],
        "Human in the Loop": [],
        "subgraph": [],
        "Tool Message": [],
    }
    set_debug(True)
    print("\n=== Human in the Loop ===")
    print(plan)
    thread_id = plan.get("session_id", "default_thread")
    user_input = plan.get("input", "").strip()
    config = {"configurable": {"thread_id": thread_id}}
    
    #subgraph_processing=subgraph_processing_dictionary.get(str(thread_id),False)
    #print(f"{thread_id}\n[debug] subgraph indicator is:{subgraph_processing}")
    #print(str(subgraph_processing_dictionary))

    # 只处理 resume 指令
    command = None
    if user_input.lower() == "accept":
        command = Command(resume={"type": "accept"})
    elif user_input.lower().startswith("edit"):
        new_name = user_input.split("=", 1)[-1].strip()
        command = Command(resume={"type": "edit", "args": {"hotel_name": new_name}})
    elif user_input.lower() == "reject":
        command = Command(resume={"type": "reject"})
    
    results = []
    if command:
        stream = graph.astream(command, config=config)
        async for output in stream:
            if output:
                results.append(output)
                if "tools" in output and "messages" in output["tools"] and len(output["tools"]["messages"]) > 0:
                    toolmessage = output["tools"]["messages"][0].content
                    if toolmessage:
                        global_log["Tool Message"].append(toolmessage)
    
    #subgraph_processing_dictionary.update({str(thread_id): subgraph_processing})
    #print(f"[debug]{thread_id}\n subgraph indicator modified to:{subgraph_processing}")
    #print(str(subgraph_processing_dictionary))
    print("global_log to front end is", global_log)
    return {
        "session_id": thread_id,
        "global_log": global_log
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("moshell_agent0901:app", host="0.0.0.0", port=1111, reload=True)