from typing import Annotated
from langchain_core.tools import tool
from typing_extensions import TypedDict
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command, interrupt
#from ericai_llm_async import llm as create_llm
from Azure import llm as create_llm
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

from langchain_core.utils.function_calling import convert_to_openai_function
from pydantic import BaseModel
thread_state = {}
global_log = {
    "AI_Response": [],
    "Thinking": [],
    "Human in the Loop": [],
    "subgraph": [],
    "Tool Message": [],
}


file_path = "/mnt/openai_key/shared_token.txt"

template=('''你是一个智能信息收集 Agent，任务是根据用户需求收集信息，并整理为 JSON 格式返回。你有以下能力：

1. 可以向用户提问以澄清需求。
请严格遵循以下 **React-style 循环格式**：

----------------------------
Step 1: Thought
首先你需要阅读用户的最近几次记录（我会将历史信息贴在最后，标签是：用户的最近几次记录如下：），然后你需要先思考下一步做什么，例如是否需要提问用户、调用工具或整理信息。。[在finish前不要包括“The Information are collected”]

Step 2: Action
这部分内容是直接返回给用户的，是你要执行的操作，例如和用户澄清需求，确定信息等。 用英语回答！ 一定要询问用户是否apply IODT-recommended parameters。[在finish前不要包括“The Information are collected”],,使用MarkDown格式回复！

Step 3: Observation
根据执行动作的结果，记录观察到的信息。你可以用它来指导下一步 Thought。 [在finish前不要包括“The Information are collected”]





当你收集完所有信息后,你需要执行以下步骤，
第一步,先和用户确认一下 你获得的信息， 是否需要二次修改。
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
2. hardware_name： IP address or the real name which usually starts with "cnbj" or "seki" or a .put the device name into the field of "hardware_name".  This item is mandatory 
3. UP_version: the software version the user needs. It usually starts with "CXP", 可以询问用户是否想用最新的UP（Latest UP）， 如果是的，不要任何其他行动，只需要将UP_version：latest

4. Netconf: the required netconf from the user. (This is optional for upgrade and configuration operations, but recommended for installation.)Netconf list is [nr_scenario_1LB_C1_plus_2MB_C2_Radio_3cell_1F2T，nr_scenario_HB_8cell_TDD，nr_scenario_LB_3cell_FDD，nr_scenario_MB_AIR_AAS_C2_Radio_3cell_TDD，nr_scenario_MB_RUS_C1_Radio_3cell_TDD，nr_scenario_MultiSec_MB_RUS_C1_3Cells_TDD，scenario_lte_FDDESS_scenario_ESS_3cell_FDD]

5. Scenario_for_tags:必须询问用户是否apply IODT-recommended parameters.If the user wants to apply IODT-recommended parameters, they can provide a Netconf file. The system will automatically extract the relevant tags from it to apply the recommended parameters.Netconf list is [nr_scenario_1LB_C1_plus_2MB_C2_Radio_3cell_1F2T，nr_scenario_HB_8cell_TDD，nr_scenario_LB_3cell_FDD，nr_scenario_MB_AIR_AAS_C2_Radio_3cell_TDD，nr_scenario_MB_RUS_C1_Radio_3cell_TDD，nr_scenario_MultiSec_MB_RUS_C1_3Cells_TDD，scenario_lte_FDDESS_scenario_ESS_3cell_FDD]

6. Tags: 必须询问用户是否apply IODT-recommended parameters。If the user wants to apply IODT-recommended parameters, they can provide a tag combination (comma-separated, e.g., NR_SA_MB, NR_SA_MB_C1). Only one of Tags or Scenario_for_tags is required.

7. Post_step: any additional installation scripts. (Not mandatory, but confirm with the user whether such scripts are needed. list are:initial_configuration, CUCP_CUUP_DU_5Qi_table,iodt_recomm_netconfig,VONR_Configuration)

--------------------------------------------------------------------------
Rules:
1,如果用户需要apply IODT-recommended parameters，必须其提供tags，或者选择一个Scenario_for_tags。如果是pply IODT-recommended parameters请将Operation设置为 none

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
    Scenario_for_netconf: str | None
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
    AI_Response:str
    Thinking:str
    human_in_the_loop:str
    json_result: Json_Schema
    session_id:str



graph_builder = StateGraph(Collect_State)

def get_state_collect(state: Collect_State) -> Literal["human_approval", "info", "__end__","json_gen_node"]:
    messages = state["messages"]

    
    last_msg = messages[-1].content if hasattr(messages[-1], "content") else str(messages[-1])
    
    if "The Information are collected" in last_msg:
        return "json_gen_node"
    if not messages:
        return "info"
    if isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
        return "human_approval"
    elif not isinstance(messages[-1], HumanMessage):
        return "info"
    return "info"








def human_approval(state: Collect_State) -> Command[Literal["jenkins", "info",END]]:

    content= state["json_result"]
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
        return Command(goto="jenkins")
    elif resume_type == "reject":
        print("User Reject")
        state["AI_Response"]="Seems you reject the request, Please tell me if everything I can do for you"
        #global_log["Tool Message"].append("Seems you reject the request, Please tell me if everything I can do for you")
        #return {            
            #"AI_Response": state["AI_Response"], }
        #return Command(goto="info")
        return Command(update={"AI_Response": state["AI_Response"]},goto="info")
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
    async def jenkins_excute_command(state: Collect_State) -> Collect_State:
        import time
        info_dict=state['json_result']
        command=['curl', '-i','http://iodt.gic.ericsson.se:8443/job/Test_Display/buildWithParameters',
                '-H','Jenkins-Crumb: 559d7bb61411b0bd9d440f345cc028ddf3206e04fc0dd7c833dd4913a04f6cc2',
                '-u','exekixl:11c848d84dd182a977f18e9f10f81b60f8'
                ]
        du_str=f'DU_Name="{info_dict.get("hardware_name","")}"' 
        command.extend(['--form', du_str])
        up_str=f'UP_version="{info_dict.get("UP_version","")}"' 
        command.extend(['--form', up_str])
        op_str=f'Operation="{info_dict.get("operation","")}"' #在上游给一个特殊标记表示是无操作，如none
        command.extend(['--form', op_str])
        netc_str=f'Scenario_for_netconf="{info_dict.get("Netconf","")}"' 
        command.extend(['--form', netc_str])
        sce_str=f'Scenario_for_tags="{info_dict.get("Scenario_for_tags","")}"' 
        command.extend(['--form', sce_str])
        tags_str=f'Tags="{info_dict.get("Tags","")}"' 
        command.extend(['--form', tags_str])
        post_str=f'Post_step="{info_dict.get("Post_step","")}"'
        command.extend(['--form', post_str])
        command = [s.replace('"None"', '""') for s in command]
        command = [s.replace('"NULL"', '""') for s in command]
        #command = [s.replace('"none"', '""') for s in command]
        print("[debug]command 1 in execution node:"+ str(command))
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True
            )

            output = result.stdout
            print(str(output))
            pattern = r'Location:\s*([a-zA-Z0-9]+://[^\s]+)'
            
            match = re.search(pattern,output)
            url1=match.group(1)
            x = str(url1).split("/")
            num=x[-2]
            cmd2=['curl','-i']
            url_str=f'http://iodt.gic.ericsson.se:8443//queue/item/{num}/api/json'
            cmd2.extend([url_str,'-H',
                            "\"Jenkins-Crumb: 559d7bb61411b0bd9d440f345cc028ddf3206e04fc0dd7c833dd4913a04f6cc2\"",
                            '-u','exekixl:11c848d84dd182a977f18e9f10f81b60f8'])
            cmd_str='curl -i '+url_str+' -H "Jenkins-Crumb: 559d7bb61411b0bd9d440f345cc028ddf3206e04fc0dd7c833dd4913a04f6cc2" -u exekixl:11c848d84dd182a977f18e9f10f81b60f8'
            time.sleep(10)
            res = subprocess.run(cmd_str, shell=True, capture_output=True, text=True)
            res2=str(res.stdout)
            arr=res2.split("\n")
            dict1=json.loads(arr[-1])
            dict2=dict1.get('executable',"")
            #这个url是直接需要拿到的东西
            url=dict2.get('url',"nothing")
            print("[debug]url:"+str(url))
            url_ret_str=f"[Jenkins link]({url}pipeline/)"
            print("url is", url_ret_str)
            state["AI_Response"]=url_ret_str
            #final_result = f"\nurl: {url_ret_str}"
           # global_log["AI_Response"].append(f"\nurl: {url_ret_str}")
            return {         
                "AI_Response": state["AI_Response"],        
            }

        except subprocess.CalledProcessError as e:
            print(f"请求失败! 错误信息: {e.stderr}")
            return None
        except Exception as e:
            print(f"发生未知错误: {str(e)}")
        return

        
    async def use_tools(state: Collect_State) -> Collect_State | Command[Literal["__end__"]]:
        """
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
            json_result: Json_Schema
            session_id:str
                """
        json_template=state.get("json_result")
        '''
        json_template: Json_Schema ={
            "operation": "install",
            "hardware_name": "CNBJITDUS01236",
            "UP_version":"None",
            "Tags": "NR_SA_MB,NR_SA_MB_C1",
            "Scenario_for_tags":None,
            "Netconf": "nr_scenario_MultiSec_MB_RUS_C1_3Cells_TDD",
            "Post_step": "initial_configuration"
        }'''
        print("[debug]json temp is:"+str(json_template))
        
        for tool in mcp_tools:
            if tool.name == "DU_Name_IP_Mapping":  #tool name
                    MCP_result = await tool.ainvoke({"query_key":json_template.get("hardware_name","")})
                    print("aaaaaaa is",MCP_result)

        data = json.loads(MCP_result)
        json_template["hardware_name"]=data.get("sitelan_ip",None)
        if json_template["hardware_name"]==None:
            print("[debug]TOOLS INFO:ip does not exist. Try another.")
            return Command(goto="__end__")

        up_version_str = json_template.get("UP_version") or "None"
        ''''''
        if up_version_str != "None":
            version_str = up_version_str.lower()
            if "latest" in version_str:
                for tool in mcp_tools:
                    if tool.name == "get_latest_UP_version":
                        MCP_result = await tool.ainvoke({"number_versions": "3", "confidence_level": "3"})
                        print("aaaaaaa is", MCP_result)

                        data = json.loads(MCP_result)
                        print("[debug] tool parsed result:", data)

                        if isinstance(data, dict):
                            version_str = data.get("1") or next(iter(data.values()), None)
                        elif isinstance(data, list) and data:
                            version_str = data[0]
                        elif isinstance(data, str):
                            version_str = data
                        else:
                            version_str = None
        else:
            version_str=up_version_str
        json_template["UP_version"]=version_str

        if json_template["operation"].lower()=="upgrade":
            for tool in mcp_tools:
                if tool.name =="check_UP_number":  #tool name
                    MCP_result = await tool.ainvoke({"du_ip":json_template["hardware_name"]}) 
                    print("bbbbbb is",MCP_result)
            data = json.loads(MCP_result)
            number=data["count"]
            if number>3:
                print("[debug]too many up versions, delete some!")
                return Command(goto="__end__")
            print("[debug]final json:\n"+str(json_template))
        #把json放回state
        state["json_result"]=json_template

        
        return state
    async def info_node(state: Collect_State) -> Collect_State | Command:
        global global_log
        global final_template
        AI_Response=''
        with open(file_path, "r", encoding="utf-8") as f:
	        JWT_TOKEN = f.read().strip()

        llm = await create_llm(JWT_TOKEN)
        #llm_with_tools = llm.bind_tools(all_tools)
        if not any(isinstance(m, SystemMessage) for m in state["messages"]):
            messages = [SystemMessage(content=final_template)] + state["messages"]
            state["messages"].insert(0, SystemMessage(content=final_template))
        else:
            messages = state["messages"]
        last_ai_message = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        if last_ai_message is None or last_ai_message.content.strip() == "":
        # ✅ 第一次调用：没有 AI 响应，直接调 LLM
            response = await llm.ainvoke(state["messages"])
        else:
        # ✅ 第二次调用：已有 AI 响应 → 打断点等待用户输入
            value = interrupt({
                "text_to_revise": "请输入需要补充的用户输入"
            })
            if not any(isinstance(m, SystemMessage) for m in state["messages"]):
                state["messages"].insert(0, SystemMessage(content=final_template))
            # 用户输入回来以后，把它直接作为 HumanMessage 追加到消息历史
            state["messages"].append(HumanMessage(content=str(value)))

            # 用历史消息（含用户输入）调用 LLM
            response = await llm.ainvoke(state["messages"])
            #print("response in second is",response)

        if hasattr(response, "content"):
            response_text = response.content
        else:
            response_text = str(response)   
        #global_log["AI_Response"].append(f"{response}")
        match_step1 = re.search(r"(Step 1: Thought.*?)(?=\nStep 2:)", response_text, re.S)
        reasoning_match = match_step1.group(1).strip() if match_step1 else None
        match_action = re.search(r"Step 2: Action(.*?)(?=\nStep 3[:\s]|$)", response_text, re.S)

        if match_action:
            action_content = match_action.group(1).strip()
        else:
            action_content = response_text.strip()

        state["Thinking"]=reasoning_match
        state["AI_Response"]=action_content
        print("[debug]state in info node", state)

        return {
            "messages": state["messages"] + [response], 
            "Thinking": state["Thinking"],              
            "AI_Response": state["AI_Response"],        
        }
    async def result_processing_node(Collect_State):
        global global_log
        with open(file_path, "r", encoding="utf-8") as f:
	        JWT_TOKEN = f.read().strip()

        llm = await create_llm(JWT_TOKEN)
        llm_with_tools = llm.bind_tools(mcp_tools)
        messages = state.get("messages", [])

        analysis_message = {
        "role": "user", 
        "content": "Analyze the tool execution result. Rewrite it to make it more readable and concise while preserving all important details. "

        }
        response =await llm.ainvoke(messages + [analysis_message])
        global_log["AI_Response"].append(f"{response}")
        return {"messages": messages + [analysis_message, response]}
    
    async def json_gen_node(state:Collect_State) -> Collect_State:
        last_msg = state["messages"][-1].content if hasattr(state["messages"][-1], "content") else str(state["messages"][-1])
        print("[debug]last message in gen node", last_msg)
        with open(file_path, "r", encoding="utf-8") as f:
	        JWT_TOKEN = f.read().strip()
        llm_instance = await create_llm(JWT_TOKEN)

        llm_structured = llm_instance.with_structured_output(Json_Schema_2,
    method="json_mode" )  # 如果底层支持 JSON Mode，就启用)
        prompt_text = f"""
你是一个严格的JSON生成器。请只输出符合 JSON Schema 的结果，不要返回解释或文字。
Schema:
{Json_Schema_2.schema_json(indent=2)}

下面是提取的信息，请转换为合法 JSON:
{last_msg}
"""
        
        response: Json_Schema_2 = await llm_structured.ainvoke(prompt_text)
        print("response in gen node",response)
        
        if isinstance(response, dict):
            json_output = response
        elif hasattr(response, "json"):
            json_output = response.json()
        else:
            json_output = json.loads(str(response))

        if isinstance(json_output, str):
            try:
                json_output = json.loads(json_output)
            except Exception as e:
                print("JSON decode error:", e)

        state["json_result"] = json_output
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
        state["AI_Response"]=state.get("AI_Response")
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
        parsed = json.loads(json_str)
        pretty_json = json.dumps(parsed, indent=2, ensure_ascii=False)
        state["human_in_the_loop"] = f"🔍 **Please confirm the parameters**\n```json\n{pretty_json}\n```"
        #state["human_in_the_loop"]=f"please confirm the parameters {json_str}"
        return {"human_in_the_loop": state["human_in_the_loop"],"AI_Response": state["AI_Response"],  }




    graph_builder.add_node("info", info_node)
    tool_node = ToolNode(tools=all_tools)
    graph_builder.add_node("human_approval", human_approval)
    graph_builder.add_node("tools", tool_node)
    graph_builder.add_node("result_processing", result_processing_node)
    graph_builder.add_node("json_gen_node", json_gen_node)
    graph_builder.add_node("save_json_node", save_json_node)

    graph_builder.add_node("mcp_tools",use_tools)
    graph_builder.add_node("jenkins",jenkins_excute_command)

    graph_builder.add_edge(START, "info")
    graph_builder.add_conditional_edges("info", get_state_collect)
    graph_builder.add_edge("tools", "result_processing")
    #graph_builder.add_edge("json_gen_node", "save_json_node")
    graph_builder.add_edge("json_gen_node", "mcp_tools")
    graph_builder.add_edge("mcp_tools", "save_json_node")
    #graph_builder.add_edge("save_json_node","jenkins")
    graph_builder.add_edge("save_json_node","human_approval")
    #graph_builder.add_edge("human_approval","jenkins")
    graph_builder.add_edge("jenkins","info")
    graph_builder.add_edge("result_processing", END) 

    memory = InMemorySaver()
    graph = graph_builder.compile(checkpointer=memory)


@app.post("/run/")
async def execute_2(plan: dict):
    global subgraph_processing
    global final_template
    #global subgraph_processing_dictionary
    global graph
    #global global_log
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


@app.post("/modify/")
async def execute_hil(plan: dict):
    #global subgraph_processing_dictionary
    dynamic_vars = {}
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
    uvicorn.run("AD_graph:app", host="0.0.0.0", port=7107, reload=True)
