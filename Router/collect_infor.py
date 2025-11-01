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

global_log = {
    "AI_Response": [],
    "Thinking": [],
    "Human in the Loop": [],
    "subgraph": [],
    "Tool Message": [],
}


template=('''Bellow is background, please translate to English for your understand:
你是一个智能信息收集 Agent，任务是根据用户需求收集信息，并整理为 JSON 格式返回。你有以下能力：

1. 可以向用户提问以澄清需求。
请严格遵循以下 **React-style 循环格式**：

----------------------------
Step 1: Thought
首先你需要阅读用户的最近几次记录（我会将历史信息贴在最后，标签是：用户的最近几次记录如下：），然后你需要先思考下一步做什么，例如是否需要提问用户、调用工具或整理信息。。[在finish前不要包括“The Information are collected”]

Step 2: Action
这部分内容是直接返回给用户的，是你要执行的操作，例如和用户澄清需求，确定信息等。 用英语回答！ 一定要询问用户是否apply IODT-recommended parameters。[在finish前不要包括“The Information are collected”]

Step 3: Observation
根据执行动作的结果，记录观察到的信息。你可以用它来指导下一步 Thought。 [在finish前不要包括“The Information are collected”]



Step 4: Finish

当你收集完所有信息后,执行以下步骤：
第一步,和用户确认一下 你获得的信息， 是否需要二次修改。
第二步，当获得用户肯定的回答后，返回按照 ：“The Information are collected：” + 你收集信息的JSON格式。 
参照：

The Information are collected

	{operation:str
     hardware_name:str
     UP_version:str
     Tags:str
     Scenario_for_tags:str
     Netconf:str
     Post_step:str}
  ]
}

------------------------------------------------------------------

关于你要收集的参数的解释如下：
1. The operation the user wants to perform. Currently, three operations are supported: install, upgrade, and configuration.
2. hardware_name： The name usually starts with "cnbj" or "seki".
put the device name into the field of "hardware_name".
3. UP_version: the software version the user needs. It usually starts with "CXP", 可以询问用户是否想用最新的UP（Latest UP）， 如果是的，不要任何其他行动，只需要将UP_version：latest

4. Netconf: the required netconf from the user. (This is optional for upgrade and configuration operations, but recommended for installation.)Netconf list is [nr_scenario_1LB_C1_plus_2MB_C2_Radio_3cell_1F2Tï¼Œnr_scenario_HB_8cell_TDDï¼Œnr_scenario_LB_3cell_FDDï¼Œnr_scenario_MB_AIR_AAS_C2_Radio_3cell_TDDï¼Œnr_scenario_MB_RUS_C1_Radio_3cell_TDDï¼Œnr_scenario_MultiSec_MB_RUS_C1_3Cells_TDDï¼Œscenario_lte_FDDESS_scenario_ESS_3cell_FDD]

5. Scenario_for_tags:必须询问用户是否apply IODT-recommended parameters。 If the user wants to apply IODT-recommended parameters, they can provide a Netconf file. The system will automatically extract the relevant tags from it to apply the recommended parameters.Netconf list is [nr_scenario_1LB_C1_plus_2MB_C2_Radio_3cell_1F2Tï¼Œnr_scenario_HB_8cell_TDDï¼Œnr_scenario_LB_3cell_FDDï¼Œnr_scenario_MB_AIR_AAS_C2_Radio_3cell_TDDï¼Œnr_scenario_MB_RUS_C1_Radio_3cell_TDDï¼Œnr_scenario_MultiSec_MB_RUS_C1_3Cells_TDDï¼Œscenario_lte_FDDESS_scenario_ESS_3cell_FDD]

6. Tags: 必须询问用户是否apply IODT-recommended parameters。If the user wants to apply IODT-recommended parameters, they can provide a tag combination (comma-separated, e.g., NR_SA_MB, NR_SA_MB_C1). Only one of Tags or Scenario_for_tags is required.

7. Post_step: any additional installation scripts. (Not mandatory, but confirm with the user whether such scripts are needed. list are:initial_configuration, CUCP_CUUP_DU_5Qi_table,iodt_recomm_netconfig,VONR_Configuration)
--------------------------------------------------------------------------

----------------------------
用户的最近几次记录如下：
{用户历史记录}
----------------------------

注意事项：
- 每次输出必须遵循 Thought/Action/Action Input/Observation 结构，除 Finish 外不允许直接输出 JSON。
- JSON 结构必须完整且可解析。
- 如果信息缺失，可以用 null 填充，但 JSON 结构保持一致。
- 每次 Thought 都要判断是否需要调用工具或提问用户。
- 根据用户的输入，选择语言！如果用户使用英语，则用英语回答！！！

'''
)

class Json_Schema_2(BaseModel):
    operation: str
    hardware_name: str
    UP_version: str
    Tags: str | None
    Scenario_for_tags: str | None
    netconf: str | None
    Post_step: str | None



class Json_Schema(TypedDict):
    operation: str
    hardware_name: str
    UP_version: str
    Tags: str | None
    Scenario_for_tags: str | None
    Netconf: str | None
    Post_step: str | None

class Collect_State(TypedDict):
    messages: Annotated[list, add_messages]
    subgraph:str
    human_in_the_loop:str
    json_result: list[Json_Schema]
    session_id:str



graph_builder = StateGraph(Collect_State)

def get_state_collect(state: Collect_State) -> Literal["human_approval", "info", "__end__","json_gen_node"]:
    messages = state["messages"]

    
    last_msg = messages[-1].content if hasattr(messages[-1], "content") else str(messages[-1])
    
    if "The Information are collected" in last_msg:
        return "json_gen_node"
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



client = create_mcp_client()


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_methods=["*"],
    allow_headers=["*"]
)


def load_json_for_prompt(db_path: str, prefix: str = "lkx") -> str:
    """
    从 SQLite 中读取所有 session_id 以 prefix 开头的记录，
    返回拼接好的 JSON 字符串，方便插入到 Prompt。
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT json_data FROM saved_json WHERE session_id LIKE ?", (f"{prefix}%",))
    rows = c.fetchall()

    conn.close()
    results = []
    for row in rows:
        try:
            results.append(json.loads(row[0]))
        except Exception:
            results.append(row[0])
    return json.dumps(results, ensure_ascii=False, indent=2)





@app.on_event("startup")
async def startup_event():
    global graph
    client = create_mcp_client()
    mcp_tools = await client.get_tools()
    #custom_tools = [get_weather, get_house_price, book_hotel]
    all_tools = list(mcp_tools)

    async def info_node(state: Collect_State) -> Collect_State | Command:
        global global_log
        global final_template
        llm = await create_llm()
        llm_with_tools = llm.bind_tools(all_tools)
        if not any(isinstance(m, SystemMessage) for m in state["messages"]):
            messages = [SystemMessage(content=final_template)] + state["messages"]
        else:
            messages = state["messages"]
        response = llm.invoke(messages)
        global_log["AI_Response"].append(f"{response}")
        return {
            "messages": messages + [response],
        }
    async def result_processing_node(Collect_State):
        global global_log
        llm = await create_llm()
        llm_with_tools = llm.bind_tools(mcp_tools)
        messages = state.get("messages", [])

        analysis_message = {
        "role": "user", 
        "content": "Analyze the tool execution result. Rewrite it to make it more readable and concise while preserving all important details. "

        }
        response = llm.invoke(messages + [analysis_message])
        global_log["AI_Response"].append(f"{response}")
        return {"messages": messages + [analysis_message, response]}

    async def json_gen_node(state: Collect_State):
        last_msg = state["messages"][-1].content if hasattr(state["messages"][-1], "content") else str(state["messages"][-1])

        llm_instance = await create_llm()

        llm_structured = llm_instance.with_structured_output(Json_Schema_2)
        prompt_text = f"""你是一个严格的JSON生成器。请直接输出 JSON，不要使用 ```json 包裹。
下面是你之前的输出，请提取并返回为合法JSON:
    {last_msg}"""
        
  
        response: Json_Schema_2 = await llm_structured.ainvoke(prompt_text)
        print("response in gen node",response)

        json_output = response.json()
        print("json in gen node", json_output)
        return state


        '''
        json_chain = prompt | llm | parser

        # 获取上一次消息
        last_msg = state["messages"][-1].content if hasattr(state["messages"][-1], "content") else str(state["messages"][-1])

        async def try_invoke_chain(raw_text):
            """调用 json_chain 并返回 dict，失败返回 None"""
            try:
                result = await json_chain.ainvoke({"raw_text": raw_text})
                if isinstance(result, dict):
                    return result
                else:
                    raise ValueError("LLM output is not a dict")
            except Exception as e:
                global_log["AI_Response"].append(f"LLM chain error: {e}")
                return None

        # 第一次尝试
        result = await try_invoke_chain(last_msg)
        if result is not None:
            global_log["AI_Response"].append(f"final result of chain is {result}")
            state["json_result"] = result
            return state

        # 重试一次
        global_log["AI_Response"].append("JSON parsing failed, retrying with LLM cleanup...")
        cleaned_result = await try_invoke_chain(last_msg)
        if cleaned_result is not None:
            global_log["AI_Response"].append(f"retry succeeded, final result is {cleaned_result}")
            state["json_result"] = cleaned_result
            return state

        # 两次都失败
        global_log["AI_Response"].append("retry failed, JSON result is None")
        state["json_result"] = None
        return state'''

    async def save_json_node(state: Collect_State) -> Collect_State:
        session_id = state.get("session_id")
        if isinstance(session_id, set):
            
            if len(session_id) == 1:
                session_id = list(session_id)[0]
            else:
                
                session_id = ",".join(session_id)

        
        json_result = state.get("json_result")
        if json_result is not None:
            json_str = json.dumps(json_result, ensure_ascii=False)
        else:
            json_str = None
        conn = sqlite3.connect("/Router/collect.db")  
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS saved_json (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                json_data TEXT
            )
        """)

        # 插入数据
        c.execute(
            "INSERT INTO saved_json (session_id, json_data) VALUES (?, ?)",
            (session_id, json_str)
        )

        conn.commit()
        conn.close()

        return state




    graph_builder.add_node("info", info_node)
    tool_node = ToolNode(tools=all_tools)
    graph_builder.add_node("human_approval", human_approval)
    graph_builder.add_node("tools", tool_node)
    graph_builder.add_node("result_processing", result_processing_node)
    graph_builder.add_node("json_gen_node", json_gen_node)
    graph_builder.add_node("save_json_node", save_json_node)

    graph_builder.add_edge(START, "info")
    graph_builder.add_conditional_edges("info", get_state_collect)
    graph_builder.add_edge("tools", "result_processing")
    graph_builder.add_edge("json_gen_node", "save_json_node")
    graph_builder.add_edge("result_processing", END) 

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
    db_path="/Router/collect.db"
    history = load_json_for_prompt(db_path, prefix="lkx")
    print("user history is",history)
    final_template = template.replace("{用户历史记录}", history)


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
    uvicorn.run("collect_infor:app", host="0.0.0.0", port=7777, reload=True)