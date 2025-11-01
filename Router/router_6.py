from typing import Annotated
from langchain_core.tools import tool
from typing_extensions import TypedDict
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command, interrupt
from Azure import llm as create_llm
#from ericai_llm_async import llm as create_llm
from langchain.globals import set_verbose
from langchain.globals import set_debug
from langchain_core.messages import SystemMessage
import re
from typing import Literal
from langgraph.graph import END
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
import pprint
import asyncio

import os
from langchain_openai import ChatOpenAI
import subprocess
import httpx
from MCP_Client3 import create_mcp_client
from subgraph import build_subgraph

global_log: list[str] = []

template=(
"You are an Agent Router. Your role is to determine which tool to invoke or which route to take based on the user's request. Please follow these rules:"
"1 If a tool needs to be called, make sure that all required parameters are explicitly provided by the user. Do not assign values to parameters on your own. If anything is unclear or missing, ask the user for clarification."
"2 If the user's request is related to DU or Baseband(GNB/ENB) installation, configuration, or upgrade, respond with the single word: subgraph."
"3 In your response, include your reasoning process using the format: [Reasoning:] + your thought process."
"Most import:If a tool needs to be called, fetch the parameter required by tools and make sure those are explicitly provided by the user. Do not assign values to parameters on your own!! "
    )

'''
template2=(
"""Your task is to gather specific information from the user regarding DU(a kind of device) install, upgrade, or configuration.
You need to collect the following information from the user:

1. The operation the user wants to perform. Currently, three operations are supported: install, upgrade, and configuration.
All three operations can be done with some netconf, so carefully distinguish between the configuration operation and adding netconf for install or upgrade.
2. The device name or IP address. The name usually starts with "cnbj" or "seki".
    put the device name into the field of "DU_name".
3. UP version: the software version the user needs. It usually starts with "cxc", and "latest UP" is also supported.
4. Netconf: the required netconf from the user. (This is optional for upgrade and configuration operations, but recommended for installation.)Netconf list is [nr_scenario_1LB_C1_plus_2MB_C2_Radio_3cell_1F2T，nr_scenario_HB_8cell_TDD，nr_scenario_LB_3cell_FDD，nr_scenario_MB_AIR_AAS_C2_Radio_3cell_TDD，nr_scenario_MB_RUS_C1_Radio_3cell_TDD，nr_scenario_MultiSec_MB_RUS_C1_3Cells_TDD，scenario_lte_FDDESS_scenario_ESS_3cell_FDD]
5. Scenario_for_tags:If the user wants to apply IODT-recommended parameters, they can provide a Netconf file. The system will automatically extract the relevant tags from it to apply the recommended parameters.Netconf list is [nr_scenario_1LB_C1_plus_2MB_C2_Radio_3cell_1F2T，nr_scenario_HB_8cell_TDD，nr_scenario_LB_3cell_FDD，nr_scenario_MB_AIR_AAS_C2_Radio_3cell_TDD，nr_scenario_MB_RUS_C1_Radio_3cell_TDD，nr_scenario_MultiSec_MB_RUS_C1_3Cells_TDD，scenario_lte_FDDESS_scenario_ESS_3cell_FDD]
 
6. Tags: If the user wants to apply IODT-recommended parameters, they can provide a tag combination (comma-separated, e.g., NR_SA_MB, NR_SA_MB_C1). Only one of Tags or Scenario_for_tags is required.
7. Post_step: any additional installation scripts. (Not mandatory, but confirm with the user whether such scripts are needed. list are:initial_configuration, CUCP_CUUP_DU_5Qi_table,iodt_recomm_netconfig,VONR_Configuration)
Return only with the json format shown below. If unsure,** put a json null ** in the corresponfing field.
{operation:str
hardware_name:str
IP:str
UP_version:str
Tags:str
Scenario_for_tags:str
Netconf:str
Post_step:str
**Literally just return the json itself without any suffix or prefix.**
*Some special scenario need to focus:
1, if user want to use latest UP, you should call the MCP tool ,get_latest_UP_version with {"number_versions": "1", "confidence_level": "1"} *
2, if uese want to upgrade you should check the number of Upgrade Packages on the device first!
""" )

'''
template2=("""# 设备配置信息收集助手

## 角色定义
你是一个专业的通信设备信息收集助手，专门负责收集DU/GNB设备的安装、升级和参数配置所需信息。

## 核心任务
收集用户执行设备操作所需的完整信息，并以结构化JSON格式输出结果。

## 支持的操作类型
1. **install** - 设备安装
2. **upgrade** - 软件升级  
3. **apply_parameter** - 应用参数配置

## 信息收集流程

### 第一步：确定操作类型
询问用户需要执行的操作（install/upgrade/apply_parameter）

### 第二步：根据操作类型收集必需信息

#### 所有操作共同需要：
- **IP地址**：目标DU设备的IP地址

#### 升级操作特殊要求：
- 获取IP后，必须调用 `check_UP_number` 工具验证设备信息

#### 软件版本信息：
- **UP_version**：软件版本号（通常以"cxc"开头）
- 如用户要求"latest UP"，调用 `get_latest_UP_version`，参数：`{"number_versions": "1", "confidence_level": "1"}`

#### 参数配置（apply_parameter操作）：
用户必须提供以下之一：
- **Tags**：标签组合（逗号分隔，如：NR_SA_MB,NR_SA_MB_C1）
- **Scenario_for_tags**：场景标签字符串

#### 可选信息：
- **Netconf**：配置文件（安装时推荐，升级和参数应用时可选）
- **Post_step**：额外安装脚本（询问用户是否需要）

## 交互指南
1. 使用清晰的问题逐步收集信息
2. 对必填项进行验证确认
3. 主动询问可选项的需求
4. 不确定的信息用null填充

## 输出格式
严格按照以下JSON格式输出，不确定的字段使用null：

```json
{
  "operation": "string",
  "hardware_name": "string", 
  "IP": "string",
  "UP_version": "string",
  "Tags": "string",
  "Scenario_for_tags": "string",
  "Netconf": "string",
  "Post_step": "string"
}
```

## 工具调用规则
- 升级操作：收集到IP后调用 `check_UP_number`
- 最新版本需求：调用 `get_latest_UP_version` 获取版本信息

现在开始收集信息：请告诉我您需要执行什么操作？""")

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



def get_state(state: State) -> Literal["human_approval", "collect", "info", "__end__"]:
    global global_log
    global_log.append(f"get state")
    messages = state["messages"]
    #print("messages in get stats,",messages)
    
    if state.get("subgraph") == "true":
        return "collect"
    if not messages:
        print("not message end")
        return "__end__"
    if isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
        return "human_approval"
    elif not isinstance(messages[-1], HumanMessage):
        print("not human message end")
        return "__end__"
    return "info"


def get_state_collect(state: State) -> Literal["human_approval", "collect", "info", "__end__"]:
    global global_log
    global_log.append(f"get state")
    messages = state["messages"]
    #print("messages in get stats,",messages)  
    if not messages:
        print("not message end")
        return "__end__"
    if isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
        return "human_approval"
    elif not isinstance(messages[-1], HumanMessage):
        print("not human message end")
        return "__end__"
    return "collect"


def human_approval(state: State) -> Command[Literal["tools", "info"]]:

    ai_message = next((m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None)

    if ai_message is None:
        raise ValueError("No AIMessage found in state['messages'].")
    if ai_message.content:
        llm_output = ai_message.content
    elif ai_message.tool_calls:
        calls = ai_message.tool_calls
        llm_output = "\n".join([f"[Tool Call] {c['name']}({c['args']})" for c in calls])
    else:
        llm_output = "<no content>"
    global global_log
    global_log.append(f"[tool call]: {llm_output}")
    print("Global log in approval",global_log)
    is_approved = interrupt(
                {
                    "question": "Is this correct?",
                    # Surface the output that should be
                    # reviewed and approved by the human.
                    "llm_output": llm_output
                }
            )
    if is_approved:
        return Command(goto="tools")
    else:
        return Command(goto="info")

def subgraph_handler(state: State):
        return Command(update={
        "messages": [{
            "role": "assistant",
            "content": "Entering Subgraph..."
        }],
        "subgraph": "entered"
    })



    
client = create_mcp_client()
async def main():
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
        contains_subgraph = "subgraph" in (response.content or "").lower()
        subgraph_flag = "true" if contains_subgraph else state.get("subgraph", "false")
        
        #print("subgraph_flag is", subgraph_flag)
        #print(messages)
        '''old_log = state.get("log", [])
        print("111old log is",old_log)
        new_log_entry = f"[info_node] AI: {response.content}"
        updated_log = old_log + [new_log_entry]'''
        global_log.append(f"[info_node] AI: {response.content}")
        print("Global log is,",global_log)
        return {
        "messages": messages + [response],
        "subgraph": subgraph_flag, 
    }
    async def collect(state: State) -> State | Command:
        global global_log
        non_system_messages = [m for m in state["messages"] if not isinstance(m, SystemMessage)]
        messages = [SystemMessage(content=template2)] + non_system_messages
        response = llm_with_tools.invoke(messages)
        print("response in collect is",response)
        global_log.append(f"[info_node] AI: {response.content}")
        print("Global log is,",global_log)
        return {
        "messages": messages + [response],
    }

    mcp_tools = await client.get_tools()
    custom_tools = [get_weather, get_house_price, book_hotel]
    all_tools = list(mcp_tools) + custom_tools
    llm = await create_llm()
    llm_with_tools = llm.bind_tools(all_tools)
    print("LLM Config:", llm_with_tools.dict())

# Graph Setting:
    graph_builder.add_node("info", info_node)
    tool_node = ToolNode(tools=all_tools)
    graph_builder.add_node("tools", tool_node)
    graph_builder.add_node("subgraph_handler", subgraph_handler)
    graph_builder.add_node("subgraph_node", call_subgraph)
    graph_builder.add_node("human_approval", human_approval)
    graph_builder.add_node("collect", collect)
    



    graph_builder.add_edge(START, "info")
    graph_builder.add_conditional_edges("info", get_state)
    graph_builder.add_conditional_edges("collect", get_state_collect)
    graph_builder.add_edge("tools", END)

    graph_builder.add_conditional_edges(
    "human_approval",
    tools_condition,
    )

    #graph_builder.add_edge("collect", "collect")
    graph_builder.add_edge("subgraph_node", "info")
    memory = InMemorySaver()
    graph = graph_builder.compile(checkpointer=memory)
    config = {"configurable": {"thread_id": "2"}}
    subgraph = build_subgraph()

    set_debug(True)
    while True:
        user = input("User (q/Q to quit): ")
        if user.lower() in {"q", "quit"}:
            print("AI: Bye bye!")
            break

        # 构造 initial_state 和 config
        initial_state = {
            "messages": [HumanMessage(content=user)],
            "subgraph": "false"
        }

        # 根据输入判断是否 resume
        if user.lower() == "accept":
            command = Command(resume={"type": "accept"})
        elif user.lower().startswith("edit"):
            new_name = user.split("=", 1)[-1].strip()
            command = Command(resume={"type": "edit", "args": {"hotel_name": new_name}})
        elif user.lower() == "reject":
            command = Command(resume={"type": "reject"})
        else:
            command = None

        # ✅ 调用 graph（resume 或 fresh）
        if command:
            stream = graph.astream(command, config=config)
        else:
            stream = graph.astream(initial_state, config=config, stream_mode="final")

        # ✅ 打印消息（无论来源是 resume 还是 user 输入）

        async for output in stream:
            if output and 'tools' in output and \
            'messages' in output['tools'] and \
            len(output['tools']['messages']) > 0:

                toolmessage = output['tools']['messages'][0].content
                if toolmessage:
                    print("\nTool message content:")
                    global_log.append(f"[tool message3333]: {toolmessage}")
                    print(global_log)

    '''while True:
        user = input("User (q/Q to quit): ")
        if user in {"q", "Q"}:
            print("AI: Byebye")
            break
        initial_state = {
            "messages": [HumanMessage(content=user)],
            "subgraph": "false"
        }
        if user.lower() == "accept":
            resume_cmd = Command(resume={"type": "accept"})
            async for chunk in graph.astream(resume_cmd, config=config):
                pprint.pprint(chunk)
                if "messages" in chunk:
                    chunk["messages"][-1].pretty_print()
        elif user.lower().startswith("edit"):
            new_name = user.split("=", 1)[-1].strip()
            resume_cmd = Command(resume={"type": "edit", "args": {"hotel_name": new_name}})
        elif user.lower() == "reject":
            resume_cmd = Command(resume={"type": "reject"})
        else:
            resume_cmd = None


        
        async for output in graph.astream(initial_state, config=config, stream_mode="final"):
            print("\n📦 Output from graph.astream:")
            pprint.pprint(output)  # 关键：查看到底返回了什么

            # 尝试打印 messages
            messages = output.get("messages", [])
            print(f"\n🔍 Extracted messages ({len(messages)}):")
            for msg in messages:
                print(f"[{type(msg).__name__}] {msg.content}")
'''

if __name__ == "__main__":
    asyncio.run(main())












