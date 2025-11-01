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
from AD_subgraph import build_subgraph
import requests
import json
from langchain_core.messages.utils import (trim_messages,count_tokens_approximately)
file_path = "/mnt/openai_key/shared_token.txt"
subgraph_processing=False
thread_state = {}
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
}
subgraph_processing_dictionary= {"default_id":False}



app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # æœ¬åœ°è°ƒè¯•ç”¨ï¼Œéƒ¨ç½²æ—¶éœ€æŒ‡å®š
    allow_methods=["*"],
    allow_headers=["*"]
)
template=(
"""Firstly, you are a receptionist. Please respond kindly and politely to the user’s casual greetings.
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
- [FinalAnswer]  ← **mandatory**, must contain meaningful text (at least one sentence).  
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
    subgraph:str
    AI_Response:str
    Thinking:str
    human_in_the_loop:str
    json_result: Json_Schema
    session_id:str
    
graph_builder = StateGraph(State)

def get_state(state: State) -> Literal["F", "subgraph_node", "info", "__end__","tools"]:
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
        #calling_output = "\n".join([f"Please approve the execution of function : {c['name']} using ({c['args']})" for c in calls])
        tool_names = [c['name'] for c in calls]
        #state["human_in_the_loop"]=calling_output
        Approved_tools = ["get_latest_UP_version", "check_UP_number", "DU_Name_IP_Mapping","extract_rrc_msgs","query_jira_issues","get_issue_statistics"]
        if any(name in Approved_tools for name in tool_names):
            print("Approved Tools No HIL")
            return  "tools"

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
                    # Surface the output that should be
                    # reviewed and approved by the human.
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
                stream=True  # 支持流式输出
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
            state["human_in_the_loop"]=human_in_the_loop
            state["subgraph"]=""
            print("[debug]state in info node", state)

            #return Command(update={"AI_Response": state["AI_Response"], "Thinking": state["Thinking"],},   goto="call_subgraph_sec")
            return Command(update={"AI_Response": state["AI_Response"], "Thinking": state["Thinking"], "human_in_the_loop": state["human_in_the_loop"],"subgraph": state["subgraph"]})
            #return new_state

                    

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
                stream=True  # 支持流式输出
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
            return Command(update={"AI_Response": state["AI_Response"], "Thinking": "", "subgraph": ""},   goto="info")
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
    """global global_log
    global_log["Human in the Loop"].append(llm_output)
    print("Global log in approval",global_log)"""
    resume_data  = interrupt(
                {
                    "question": llm_output,
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
        # æ— æ³•è¯†åˆ«çš„æŒ‡ä»¤
        return Command(goto="info")



app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)



 


client = create_mcp_client()
@app.on_event("startup")
async def startup_event():
    global graph
    global subgraph
    client = create_mcp_client()
    mcp_tools = await client.get_tools()
    #custom_tools = [get_weather, get_house_price, book_hotel]
    all_tools = list(mcp_tools) 
    #llm = await create_llm()
    #llm_with_tools = llm.bind_tools(all_tools)
    subgraph = None
    #subgraph = build_subgraph()
    subgraph = await build_subgraph() 
    print("building subgraph")
    print(type(subgraph))

    async def call_subgraph(state: State) -> State:
        subgraph_port_map = {
            "Trace_Agent": "1111",
            "true": "7107"
        }
        
        subgraph_value = state.get("subgraph")
        port = subgraph_port_map.get(subgraph_value, None)
        
        human_msgs = [m for m in state["messages"] if isinstance(m, HumanMessage)]
        print("human mes inall Sub",human_msgs)
        if len(human_msgs) >= 2:
            last_msg = human_msgs[-2].content
        else:
            last_msg="what kind of information I should provide"
       
        #last_msg1 = state["messages"][-5]
        #print("last message is,",last_msg1)
        
        session_id = state["session_id"]

        payload = {
        "input": last_msg,
        "session_id": session_id
    }
        url = f"http://0.0.0.0:{port}/run/"
        try:
            final_response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                stream=True  # 支持流式输出
            )
            #print("final_response is",final_response)
            content = final_response.text
            print(content)
            data = json.loads(content)
            ai_response = data.get("AI_Response", "")
            thinking = data.get("Thinking", "")
            human_in_the_loop = data.get("human_in_the_loop", "")
    
            state["Thinking"]=thinking
            state["AI_Response"]=ai_response
            state["human_in_the_loop"]=human_in_the_loop
            print("[debug]state in info node", state)

            return {
            "Thinking": state["Thinking"],              
            "AI_Response": state["AI_Response"], 
            "human_in_the_loop": state["human_in_the_loop"],       
        }


            #return new_state

                    

        except Exception as e:
            print("请求出错:", e)



        """
        response = await subgraph.ainvoke({
            "messages": last_msg,
            "session_id": state.get("session_id", "")
        })
        print(f"[debug] subgraph response: {response}")
        """


    async def call_subgraph_sec(state: State) -> State:
        subgraph_port_map = {
            "Trace_Agent": "1111",
            "true": "7107"
        }
        subgraph_value = state.get("subgraph")
        port = subgraph_port_map.get(subgraph_value, None)
        print("state in call_subgraph_sec",state)
        human_input = interrupt({
            "text_to_revise": "call_subgraph_sec"
        })
        #last_msg = state["messages"][-5]
        session_id = state["session_id"]
        #print(f"[debug]last message:{last_msg}")
        payload = {
        "input": human_input,
        "session_id": session_id
    }
        url = f"http://0.0.0.0:{port}/run/"
        try:
            final_response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                stream=True  # 支持流式输出
            )
            #print("final_response is",final_response)
            content = final_response.text
            print("response from AD",content)
            data = json.loads(content)
            ai_response = data.get("AI_Response", "")
            thinking = data.get("Thinking", "")
            human_in_the_loop = data.get("human_in_the_loop", "")
    
            state["Thinking"]=thinking
            state["AI_Response"]=ai_response
            state["human_in_the_loop"]=human_in_the_loop
            print("[debug]state in sec sub", state)
            return {
            "Thinking": state["Thinking"],              
            "AI_Response": state["AI_Response"], 
            "human_in_the_loop": state["human_in_the_loop"],       
        }
        except Exception as e:
            print("请求出错:", e)

    async def info_node(state: State) -> State | Command:
        global global_log
        start_time = time.time()        
        '''
        llm = await create_llm()
        llm_with_tools = llm.bind_tools(all_tools)
        print("Message in infor node :",state["messages"])
        if not any(isinstance(m, SystemMessage) for m in state["messages"]):
            messages = [SystemMessage(content=template)] + state["messages"]
        else:
            messages = state["messages"]
        #response = llm_with_tools.invoke(messages)
        response = await llm_with_tools.ainvoke(messages)'''
        llm = await create_llm()
        llm_with_tools = llm.bind_tools(all_tools)
        print("LLM Config:", llm_with_tools.dict())
        if not any(isinstance(m, SystemMessage) for m in state["messages"]):
            messages = [SystemMessage(content=template)] + state["messages"]
            state["messages"].insert(0, SystemMessage(content=template))
        else:
            messages = state["messages"]
        last_ai_message = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        if last_ai_message is None or last_ai_message.content.strip() == "":
        # ✅ 第一次调用：没有 AI 响应，直接调 LLM
            response = await llm.ainvoke(state["messages"])
        else:
        # ✅ 第二次调用：已有 AI 响应 → 打断点等待用户输入
            value = interrupt({
                "text_to_revise": "interrup in Info"
            })
            if not any(isinstance(m, SystemMessage) for m in state["messages"]):
                state["messages"].insert(0, SystemMessage(content=template))
            # 用户输入回来以后，把它直接作为 HumanMessage 追加到消息历史
            state["messages"].append(HumanMessage(content=str(value)))

            print("Debug message befor trim",state["messages"])
            print("---------------------------------------------------------------------------")
            state["messages"] = trim_messages(
                state["messages"],
                strategy="last",
                token_counter=count_tokens_approximately,
                max_tokens=5000,
                start_on="human",
                end_on=("human", "tool"),
            )
            print("Debug message after trim",state["messages"])

            response = await llm_with_tools.ainvoke(state["messages"])
            #print("response in second is",response)

        if hasattr(response, "content"):
            response.content = response.content
        else:
            response.content = str(response)   
        #print("AI Response:", response.content)
        reasoning_match = re.search(
            r'\[(?:Reasoning|Thinking)\]\s*(.*?)\s*(?=\[FinalAnswer\]|\Z)',
            response.content,
            re.S | re.I
        )
        reasoning = reasoning_match.group(1).strip() if reasoning_match else ""
        end_time = time.time()
        print(f"⏱ get AI () response: {end_time - start_time:.3f} 秒")
        # åŒ¹é… FinalAnswerï¼ˆå¿…é¡»æœ‰ï¼‰
        final_answer_match = re.search(
            r'\[FinalAnswer\]\s*(.*?)(?=\n\[\w+\]|\Z)', 
            response.content, 
            re.S | re.I
        )
        if final_answer_match and final_answer_match.group(1).strip():
            final_answer = final_answer_match.group(1).strip()
        else:
            final_answer = response.content.strip()

    
        reasoning = "\n".join(line.strip() for line in reasoning.splitlines() if line.strip())
        final_answer = "\n".join(line.strip() for line in final_answer.splitlines() if line.strip())
        
        contains_subgraph = "subgraph" in (response.content or "").lower()
        subgraph_flag = "true" if contains_subgraph else state.get("subgraph", "false")
        if "Trace_Agent" in final_answer:
            subgraph_flag = "Trace_Agent"
        global_log["AI_Response"].append(f"{final_answer}")
        global_log["Thinking"].append(f"{reasoning}")
        print("Global log in infor node is,",global_log)
        state["Thinking"]=reasoning
        state["AI_Response"]=final_answer
        return {
            "messages": messages + [response],
            "subgraph": subgraph_flag,
            "Thinking": state["Thinking"],              
            "AI_Response": state["AI_Response"], 
        }
    async def result_processing_node(state):
        global global_log
        llm = await create_llm()
        #llm = await create_llm()
        llm_with_tools = llm.bind_tools(mcp_tools)
        messages = state.get("messages", [])

        analysis_message = {
            "role": "user", 
           "content": "Analyze the tool execution result. Rewrite it to make it more readable( (You can Prefix sentence with at latest 4 decorative symbol such as ✨, 🌸, ➡, or ⭐. and use Markdonw) and concise while preserving all important details."

        }
        #response = llm.invoke(messages + [analysis_message])
        response = await llm.ainvoke(messages + [analysis_message])


        reasoning_match = re.search(
            r'\[(?:Reasoning|Thinking)\]\s*(.*?)\s*(?=\[FinalAnswer\]|\Z)',
            response.content,
            re.S | re.I
        )
        reasoning = reasoning_match.group(1).strip() if reasoning_match else ""
        final_answer_match = re.search(
            r'\[FinalAnswer\]\s*(.*?)(?=\n\[\w+\]|\Z)', 
            response.content, 
            re.S | re.I
        )
        if final_answer_match and final_answer_match.group(1).strip():
            final_answer = final_answer_match.group(1).strip()
        else:
            final_answer = response.content.strip()

        reasoning = "\n".join(line.strip() for line in reasoning.splitlines() if line.strip())
        final_answer = "\n".join(line.strip() for line in final_answer.splitlines() if line.strip())

        global_log["AI_Response"].append(f"{final_answer}")
        global_log["Thinking"].append(f"{reasoning}")
        global_log["Human in the Loop"] = []
        print("Global log in result_processing_node node is,",global_log)

        state["Thinking"]=reasoning
        state["AI_Response"]=final_answer
 

        return {
            "messages": state["messages"] + [analysis_message, response], 
            "Thinking": state["Thinking"],              
            "AI_Response": state["AI_Response"],    
            "human_in_the_loop": "",
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
    #graph_builder.add_edge("subgraph_node", "call_subgraph_sec")
    graph_builder.add_conditional_edges("subgraph_node", get_state_sub)
    graph_builder.add_conditional_edges("call_subgraph_sec", get_state_sub)
    graph_builder.add_conditional_edges("human_approve_sub", get_state_sub)
    #graph_builder.add_conditional_edges("subgraph_node", get_state)
    graph_builder.add_edge("result_processing", "info") 
    #graph_builder.add_edge("human_approve_sub", "info")

   
    
  
    
   
    memory = InMemorySaver()
    graph = graph_builder.compile(checkpointer=memory)
    


@app.post("/run/")
async def execute_2(plan: dict):

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
    print("user input after plan",user_input)
    config = {"configurable": {"thread_id": thread_id}}
    print("config is",config)
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
                toolmessage = output["tools"]["messages"][0].content
                if toolmessage:
                    global_log["Tool Message"].append(toolmessage)


    return {
        "session_id": thread_id,
        "AI_Response": dynamic_vars[ai_field],
        "Thinking":dynamic_vars[thinking_field],
        "human_in_the_loop":dynamic_vars[human_in_the_loop_field]
    }
    
    #subgraph_processing=subgraph_processing_dictionary.get(str(thread_id),False)
    #print(f"{thread_id}\n[debug] subgraph indicator is :{subgraph_processing}")
    #print(str(subgraph_processing_dictionary))
    


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


        return {
            "session_id": thread_id,
            "AI_Response": dynamic_vars[ai_field],
            "Thinking":dynamic_vars[thinking_field],
            "human_in_the_loop":dynamic_vars[human_in_the_loop_field]
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("router_collect3_EAI:app", host="0.0.0.0", port=777, reload=True)


