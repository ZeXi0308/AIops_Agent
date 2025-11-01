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
#from Azure import llm as create_llm
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

file_path = "/mnt/openai_key/shared_token.txt"
thread_state = {}
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

上行吞吐量/速率测试相关的Trace ID：
ULL1COMMONNR.29
DRAULMDBFNR.103

下行DTX相关测试的Trace ID:

UPCUEDLNR.172
DRADLMDBFNR.73

'''
)


class DebugHandler(BaseCallbackHandler):
    def on_llm_start(self, serialized, prompts, **kwargs):
        print("[DEBUG] LLM Start:", prompts)

    def on_llm_end(self, response, **kwargs):
        print("[DEBUG] LLM End:", response)

    def on_tool_start(self, serialized, input_str, **kwargs):
        print("[DEBUG] Tool Start:", serialized, input_str)

    def on_tool_end(self, output, **kwargs):
        print("[DEBUG] Tool End:", output)

class Collect_State(TypedDict):
    messages: Annotated[list, add_messages]
    AI_Response:str
    human_in_the_loop:str

graph_builder = StateGraph(Collect_State)

def get_state_collect(state: Collect_State) -> Literal["human_window", "info", "__end__",]:
    messages = state["messages"]
    if not messages:
        return "info"
    if isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
        return "human_window"
    elif not isinstance(messages[-1], HumanMessage):
        return "info"
    return "info"

def human_window(state: Collect_State):
    messages = state["messages"]
    if isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
        ai_message = next((m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None)
        calls = ai_message.tool_calls
        calling_output = "\n".join([f"Please approve the execution of function : {c['name']} using ({c['args']})" for c in calls])

        return { "AI_Response": "Tool Calling","human_in_the_loop": calling_output}

def human_approval(state: Collect_State) -> Command[Literal["tools", "info"]]:

    ai_message = next((m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None)

    if ai_message is None:
        raise ValueError("No AIMessage found in state['messages'].")
    if ai_message.tool_calls:
        calls = ai_message.tool_calls
        llm_output = "\n".join([f"Please approve the execution of function : {c['name']} using ({c['args']})" for c in calls])
    else:
        llm_output = "<no tool calls found>"
    #global global_log
    #global_log["Human in the Loop"].append(llm_output)
    #print("Global log in approval",global_log)
    #state["human_in_the_loop"]=llm_output
    resume_data  = interrupt(
                {
                    "question": "HIL in Trace Agent?",
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
        state["AI_Response"]="Seems you reject the request, Please tell me if everything I can do for you"
        #global_log["Tool Message"].append("Seems you reject the request, Please tell me if everything I can do for you")
        #return {            
            #"AI_Response": state["AI_Response"], }
        #return Command(goto="info")
        return Command(update={"AI_Response": state["AI_Response"]},goto="info")
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
    child = pexpect.spawn(f'./moshell/moshell -v username=muser,password=muser {ip} ', encoding='utf-8', echo=False,timeout=None)
    child.sendline("lt all")
    results = []
    for cmd in cmds:
        print(f"\n[Agent] 执行命令: {cmd}")
        child.sendline(cmd)
        output = []
        last_output_time = time.time()
        error="No valid XBM were found!"
        '''
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
        while True:
            try:
                idx = child.expect([prompt, error, pexpect.TIMEOUT, pexpect.EOF], timeout=60)
                # 匹配到 prompt
                if idx == 0:
                    if child.before.strip():
                        output.append(child.before.strip())
                        print(child.before.strip())
                    break
                # 匹配到 error
                elif idx == 1:
                    if child.before.strip():
                        output.append(child.before.strip())
                        print(child.before.strip())
                    print("⚠️ 检测到错误信息")
                    break
                # 超时
                elif idx == 2:
                    print("⏳ 超过 60s 无输出，结束命令")
                    break
                # 子进程退出
                elif idx == 3:
                    print("❌ 子进程退出")
                    break

            except Exception as e:
                print(f"⚠️ 异常: {e}")
                break
        
        
        results.append({cmd: output})'''

        while True:
            try:
                # 🔹 匹配一行（带换行）
                idx = child.expect([prompt, error, r'.*\r\n', pexpect.TIMEOUT, pexpect.EOF], timeout=1)

                if idx == 0:  # prompt
                    if child.before.strip():
                        for line in child.before.strip().splitlines():
                            output.append(line)
                            print(line)
                    break

                elif idx == 1:  # error
                    if child.before.strip():
                        for line in child.before.strip().splitlines():
                            output.append(line)
                            print(line)
                    print("⚠️ 检测到错误信息")
                    break

                elif idx == 2:  # 普通输出 (逐行)
                    line = child.match.group(0).strip()
                    if line:
                        output.append(line)
                        print(line)  # 🔹 实时打印
                        last_output_time = time.time()

                elif idx == 3:  # TIMEOUT (1s 内无输出)
                    if time.time() - last_output_time > 60:
                        print("⏳ 超过 60s 无新输出，结束命令")
                        break
                    continue

                elif idx == 4:  # EOF
                    print("❌ 子进程退出")
                    break

            except Exception as e:
                print(f"⚠️ 异常: {e}")
                break
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

        llm = await create_llm()
        llm.callbacks = [DebugHandler(), StdOutCallbackHandler()]
        llm_with_tools = llm.bind_tools(tools)
        print("LLM Config:", llm_with_tools.dict())
        if not any(isinstance(m, SystemMessage) for m in state["messages"]):
            messages = [SystemMessage(content=template)] + state["messages"]
            state["messages"].insert(0, SystemMessage(content=template))
        else:
            messages = state["messages"]
        last_ai_message = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        if last_ai_message is None or last_ai_message.content.strip() == "":
            response = await llm_with_tools.ainvoke(state["messages"])
        else:
            value = interrupt({
                    "text_to_revise": "请输入需要补充的用户输入"
                })
            if not any(isinstance(m, SystemMessage) for m in state["messages"]):
                state["messages"].insert(0, SystemMessage(content=template))
                # 用户输入回来以后，把它直接作为 HumanMessage 追加到消息历史
            state["messages"].append(HumanMessage(content=str(value)))

                # 用历史消息（含用户输入）调用 LLM
            response = await llm_with_tools.ainvoke(state["messages"])
            print("response in second is",response)

        if hasattr(response, "content"):
            print("response dones not have content")
            
            response_text = response.content 
            print("response_text  befor extrace content ",response_text)

            '''match = re.search(r'content="(.*?)"\s+additional_kwargs=', response_text, re.DOTALL)
            if match:
                response_text = match.group(1)
                print("response_text after extract",response_text)
            else:
                print("Not match group")'''
        else:
            response_text = str(response)   
        state["AI_Response"]=response_text

        #global_log["AI_Response"].append(f"{response}")
        #state["AI_Response"]=response
        return {
            "messages": messages + [response],
            "AI_Response": state["AI_Response"], 
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
        if hasattr(response, "content"):
            print("response dones not have content")
            
            response_text = response.content 
            print("response_text  befor extrace content ",response_text)

            '''match = re.search(r'content="(.*?)"\s+additional_kwargs=', response_text, re.DOTALL)
            if match:
                response_text = match.group(1)
                print("response_text after extract",response_text)
            else:
                print("Not match group")'''
        else:
            response_text = str(response)   
        state["AI_Response"]=response_text

        #global_log["AI_Response"].append(f"{response}")
        return {
            "messages": state["messages"] + [analysis_message, response],           
            "AI_Response": state["AI_Response"],    
            "human_in_the_loop": "",
        }





    graph_builder.add_node("info", info_node)
    tool_node = ToolNode(tools=tools)
    graph_builder.add_node("human_approval", human_approval)
    graph_builder.add_node("tools", tool_node)
    graph_builder.add_node("result_processing", result_processing_node)
    graph_builder.add_node("human_window", human_window)

    graph_builder.add_edge(START, "info")
    graph_builder.add_conditional_edges("info", get_state_collect)
    graph_builder.add_edge("human_window", "human_approval")
    graph_builder.add_edge("tools", "result_processing")
    graph_builder.add_edge("result_processing", "info")

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
    first_run = thread_id not in thread_state

    if first_run:
        initial_state = {
            "messages": [HumanMessage(content=user_input)],
            "AI_Response":"",
            "Thinking": "",
            "human_in_the_loop":"",
            "session_id":thread_id,
            }
        stream = graph.astream(initial_state, config=config, stream_mode="values")
        thread_state[thread_id] = True  # 标记已经启动过
    else:
        print("run into second ")
        command = Command(resume=user_input)
        stream = graph.astream(command, config=config)
    #results = []
    #subgraph_processing_dictionary.update({str(thread_id): subgraph_processing})
    #print(f"[debug] {thread_id}\nsubgraph indicator modified to:{subgraph_processing}")
    dynamic_vars = {}

    # 动态 key
    ai_field = f"{thread_id}_AI_Response"
    thinking_field = f"{thread_id}_Thinking"
    human_in_the_loop_field=f"{thread_id}_human_in_the_loop"
    results = []
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
    async for output in stream:
  
        #print("output is ",output)
        if output:
            results.append(output)
        print("=== Current results ===")
        for idx, item in enumerate(results, start=1):
            #print(f"result{idx} =", item)
            print("=======================")
            # 默认取最后一条记录
            dynamic_vars[ai_field] = ""
            dynamic_vars[thinking_field] = ""
            dynamic_vars[human_in_the_loop_field] = ""

            # 遍历 results，从最新的开始找
            for target in reversed(results):
                ai_response = find_value(target, "AI_Response")
                thinking = find_value(target, "Thinking")
                human_in_the_loop_content=find_value(target, "human_in_the_loop")
                if ai_response:  # 找到就停止遍历
                    dynamic_vars[ai_field] = ai_response
                    dynamic_vars[thinking_field] = thinking or ""
                    dynamic_vars[human_in_the_loop_field] =human_in_the_loop_content
                    break

            # 如果输出里有 tools 消息
            if "tools" in output and "messages" in output["tools"] and len(output["tools"]["messages"]) > 0:
                print("toolmessage is,",toolmessage)
                toolmessage = output["tools"]["messages"][0].content
                if toolmessage:
                    global_log["Tool Message"].append(toolmessage)


    return {
        "session_id": thread_id,
        "AI_Response": dynamic_vars[ai_field],
        "Thinking":dynamic_vars[thinking_field],
        "human_in_the_loop":dynamic_vars[human_in_the_loop_field]
    }



@app.post("/modify/")
async def execute_hil(plan: dict):
    global subgraph_processing
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
    dynamic_vars = {}
    ai_field = f"{thread_id}_AI_Response"
    thinking_field = f"{thread_id}_Thinking"
    human_in_the_loop_field=f"{thread_id}_human_in_the_loop"
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
        async for output in stream:
    
            #print("output is ",output)
            if output:
                results.append(output)
            print("=== Current results ===")
            for idx, item in enumerate(results, start=1):
                print(f"result{idx} =", item)
                print("=======================")
                # 默认取最后一条记录
                dynamic_vars[ai_field] = ""
                dynamic_vars[thinking_field] = ""
                dynamic_vars[human_in_the_loop_field] = ""

                # 遍历 results，从最新的开始找
                for target in reversed(results):
                    ai_response = find_value(target, "AI_Response")
                    thinking = find_value(target, "Thinking")
                    human_in_the_loop_content=find_value(target, "human_in_the_loop")
                    if ai_response:  # 找到就停止遍历
                        dynamic_vars[ai_field] = ai_response
                        dynamic_vars[thinking_field] = thinking or ""
                        dynamic_vars[human_in_the_loop_field] =human_in_the_loop_content
                        break

                # 如果输出里有 tools 消息
                if "tools" in output and "messages" in output["tools"] and len(output["tools"]["messages"]) > 0:
                    toolmessage = output["tools"]["messages"][0].content
                    if toolmessage:
                        global_log["Tool Message"].append(toolmessage)

        print(dynamic_vars[ai_field])
        return {
            "session_id": thread_id,
            "AI_Response": dynamic_vars[ai_field],
            "Thinking":dynamic_vars[thinking_field],
            "human_in_the_loop":dynamic_vars[human_in_the_loop_field]
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("moshell_agent_EAI:app", host="0.0.0.0", port=1111, reload=True)