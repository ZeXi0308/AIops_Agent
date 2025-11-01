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
from subgraph import build_subgraph
import re
from fastapi.middleware.cors import CORSMiddleware



global_log = {
    "AI_Response": [],
    "Thinking": [],
    "Human in the Loop": [],
    "subgraph": [],
    "Tool Message": [],
}
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本地调试用，部署时需指定
    allow_methods=["*"],
    allow_headers=["*"]
)
template=(
"""You are an Agent Router. Your role is to determine which tool to invoke or which route to take based on the user's request. Please follow these rules:

1) If a tool needs to be called:  
   - You MUST list all required parameters and their values **inside the [FinalAnswer] section**.  
   - Do NOT place any parameter names or values in [Thinking].  
   - Do NOT assign values to parameters on your own; if anything is unclear or missing, explicitly ask the user for clarification **within [FinalAnswer]**.

2) If the user's request is related to DU or Baseband (GNB/ENB) installation, configuration, or upgrade, set the [FinalAnswer] to the single word:
subgraph

3) It is **preferred** that you include your internal thought process. Use the label [Thinking] to provide it. However, [Thinking] is optional — **the [FinalAnswer] is mandatory** and must always be present.

IMPORTANT — Output format (MUST follow exactly):
The assistant's entire reply must contain **only** these two sections (in this order).  
- [FinalAnswer]  ← **mandatory**, must contain meaningful text (at least one sentence).  Including parameters and its vaule you want to check with user for Tool Calling.
- [Thinking]     ← optional, you may include useful step-by-step thoughts here. If absent, it's OK.

Exact format example (both fields present):
[FinalAnswer]
I will call tool X next; please confirm the parameters.

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
    log: list[str]

graph_builder = StateGraph(State)

@tool
def get_weather(location: str) -> str:
    """Get weather of specify city,ask user for the city if they don't provide"""
    response = interrupt(  
        f"Trying to get_weather with args {{'hotel_name': {location}}}. "
        "Please approve or suggest edits."
    )
    if response["type"] == "accept":
        pass
    weather=f"The weather in {location} is sunny."
    return weather
@tool
def get_house_price(location: str) -> str:
    """Get house price of specify city,ask user for the city if they don't provide"""
    price=f"The housee price in {location} is 500CNY."
    return price
@tool
def book_hotel(hotel_name: str):
    """Book a hotel"""
    response = interrupt(  
        f"Trying to call `book_hotel` with args {{'hotel_name': {hotel_name}}}. "
        "Please approve or suggest edits."
    )
    if response["type"] == "accept":
        print("123213213123112213132")
        pass
    elif response["type"] == "edit":
        hotel_name = response["args"]["hotel_name"]
    else:
        raise ValueError(f"Unknown response type: {response['type']}")
    
    return f"Successfully booked a stay at {hotel_name}."




def get_state(state: State) -> Literal["human_approval", "subgraph_node", "info", "__end__"]:
    messages = state["messages"]
    print("subgraph in get stats,",state["subgraph"])
    
    if state.get("subgraph") == "true":
        return "subgraph_node"
    if not messages:
        return "__end__"
    if isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
        return "human_approval"
    elif not isinstance(messages[-1], HumanMessage):
        return "__end__"
    return "info"

def human_approval(state: State) -> Command[Literal["tools", "info"]]:

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
        # 无法识别的指令
        return Command(goto="info")




    
client = create_mcp_client()
@app.on_event("startup")
async def startup_event():
    global graph
    global subgraph
    client = create_mcp_client()
    mcp_tools = await client.get_tools()
    custom_tools = [get_weather, get_house_price, book_hotel]
    all_tools = list(mcp_tools) + custom_tools
    llm = await create_llm()
    llm_with_tools = llm.bind_tools(all_tools)
    '''  Test execute MCP tools
    for tool in mcp_tools:
        if tool.name == "get_latest_UP_version":
            MCP_result = await tool.ainvoke({"number_versions": "3", "confidence_level": "3"})
            print("aaaaaaa is",MCP_result)
'''
    def call_subgraph(state: State) -> State:
        last_msg = state["messages"][-1].content if state["messages"] else ""
        response = subgraph.invoke({
            "submessage": last_msg,
            "user_input": ""
        })
        return {
            "messages": state["messages"] + [AIMessage(content=response["submessage"])],
            "subgraph": "done"
        }

    async def info_node(state: State) -> State | Command:
        global global_log
        if not any(isinstance(m, SystemMessage) for m in state["messages"]):
            messages = [SystemMessage(content=template)] + state["messages"]
        else:
            messages = state["messages"]
        response = llm_with_tools.invoke(messages)
        print("🧠 AI Response:", response.content)
        reasoning_match = re.search(
            r'\[(?:Reasoning|Thinking)\]\s*(.*?)\s*(?=\[FinalAnswer\]|\Z)',
            response.content,
            re.S | re.I
        )
        reasoning = reasoning_match.group(1).strip() if reasoning_match else ""

        # 匹配 FinalAnswer（必须有）
        final_answer_match = re.search(
            r'\[FinalAnswer\]\s*(.*?)(?=\n\[\w+\]|\Z)', 
            response.content, 
            re.S | re.I
        )
        if final_answer_match and final_answer_match.group(1).strip():
            final_answer = final_answer_match.group(1).strip()
        else:
            final_answer = response.content.strip()

        # 去掉多余空行
        reasoning = "\n".join(line.strip() for line in reasoning.splitlines() if line.strip())
        final_answer = "\n".join(line.strip() for line in final_answer.splitlines() if line.strip())
        
        contains_subgraph = "subgraph" in (response.content or "").lower()
        subgraph_flag = "true" if contains_subgraph else state.get("subgraph", "false")
        global_log["AI_Response"].append(f"{final_answer}")
        global_log["Thinking"].append(f"{reasoning}")
        print("Global log in infor node is,",global_log)
        return {
            "messages": messages + [response],
            "subgraph": subgraph_flag
        }

    graph_builder.add_node("info", info_node)
    tool_node = ToolNode(tools=all_tools)
    graph_builder.add_node("tools", tool_node)
    graph_builder.add_node("subgraph_node", call_subgraph)
    graph_builder.add_node("human_approval", human_approval)

    graph_builder.add_edge(START, "info")
    graph_builder.add_conditional_edges("info", get_state)
    graph_builder.add_edge("tools", END)

    memory = InMemorySaver()
    graph = graph_builder.compile(checkpointer=memory)

    subgraph = build_subgraph()

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
    config = {"configurable": {"thread_id": thread_id}}

    # 判断是否是 resume 指令
    command = None
    if user_input.lower() == "accept":
        command = Command(resume={"type": "accept"})
    elif user_input.lower().startswith("edit"):
        new_name = user_input.split("=", 1)[-1].strip()
        command = Command(resume={"type": "edit", "args": {"hotel_name": new_name}})
    elif user_input.lower() == "reject":
        command = Command(resume={"type": "reject"})

    results = []
    #global_log.clear()

    if command:
        # 流式处理 resume 情况
        stream = graph.astream(command, config=config)
    else:
        # 普通新对话
        initial_state = {
            "messages": [HumanMessage(content=user_input)],
            "subgraph": "false",
            "log": []
        }
        stream = graph.astream(initial_state, config=config, stream_mode="final")

    async for output in stream:
        if output:
            results.append(output)
            # 如果输出里有 tools 消息
            if "tools" in output and "messages" in output["tools"] and len(output["tools"]["messages"]) > 0:
                toolmessage = output["tools"]["messages"][0].content
                if toolmessage:
                    global_log["Tool Message"].append(toolmessage)
    print("global_log to front end is",global_log)
    return {
        "session_id": thread_id,
        "global_log": global_log
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("router_6_app:app", host="0.0.0.0", port=7771, reload=True)










