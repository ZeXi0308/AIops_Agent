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
subgraph_processing=False
class CompletedState(TypedDict):
    operation:str
    not_completed:bool
    UP_version_lookup:bool
    du_ip_look_up:bool
    up_count:int
    IP:str
class OverallState(TypedDict):
    operation:str
    hardware_name:str
    IP:str
    UP_version:str
    Tags:str
    Scenario_for_tags:str
    Netconf:str
    Post_step:str

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
"""You are an Agent Router. Your role is to determine which tool to invoke or which route to take based on the user's request. Please follow these rules:

1) If a tool needs to be called:  
   - You MUST list all required parameters and their values **inside the [FinalAnswer] section**.  
   - Do NOT place any parameter names or values in [Thinking].  
   - Do NOT assign values to parameters on your own; if anything is unclear or missing, explicitly ask the user for clarification **within [FinalAnswer]**.

2) If the user's request is related to DU or Baseband (GNB/ENB) installation, configuration, or upgrade,  ask them if they want to route to AutoDeploy function , and after receiving explicit confirmation then set the [FinalAnswer] to the single word:subgraph

3) It is **preferred** that you include your internal thought process. Use the label [Thinking] to provide it. However, [Thinking] is optional â€” **the [FinalAnswer] is mandatory** and must always be present.


IMPORTANT â€” Output format (MUST follow exactly):
The assistant's entire reply must contain **only** these two sections (in this order).  
- [FinalAnswer]  â† **mandatory**, must contain meaningful text (at least one sentence).  Including parameters and its vaule you want to check with user for Tool Calling.
- [Thinking]     â† optional, you may include useful step-by-step thoughts here. If absent, it's OK.

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

graph_builder = StateGraph(State,CompletedState,output_schema=OverallState)

def get_state(state: State) -> Literal["human_approval", "input_node", "info", "__end__"]:
    messages = state["messages"]
    print("subgraph in get stats,",state["subgraph"])
    
    if state.get("subgraph") == "true":
        return "input_node"
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
        # æ— æ³•è¯†åˆ«çš„æŒ‡ä»¤
        return Command(goto="info")

def is_valid_ip(ip_str):
    if isinstance(ip_str, str):
        ips=ip_str.replace(" ", "")
        parts = ips.split('.')
        if len(parts) != 4:
            return False
        
        for part in parts:
            if not part.isdigit():
                return False
            if len(part) > 1 and part[0] == '0':
                return False
            num = int(part)
            if num < 0 or num > 255:
                return False
        return True    

    return False

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)
def trigger_jenkins_build(
    jenkins_url,
    job_name,
    username,
    api_token,
    crumb,
    DU_name,
    UP_version,
    operation,
    scenario_for_netconf,
    scenario_for_tags,
    tags,
    post_step
        ):
    build_url = f"{jenkins_url}/job/{job_name}/buildWithParameters"
    headers = {
        "Jenkins-Crumb": crumb
    }

    params = {
        "DU_name": DU_name,
        "UP_version": UP_version,
        "Operation": operation,
        "Scenario_for_netconf": scenario_for_netconf,
        "Scenario_for_tags": scenario_for_tags,
        "Tags": tags,
        "Post_step": post_step
    }

    curl_cmd = f'curl {build_url} -H "Jenkins-Crumb: {crumb}" -u {username}:{api_token}'
    for k, v in params.items():
        curl_cmd += f" --form '{k}=\"{v}\"'"
    print(curl_cmd)
def extract_json_content(content: str) -> str:
    pattern = r"^```json\n(.*?)\n```\s*$"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1)
    else:
        return content


def into_subgraph() -> list[Command]:

    global_log["Human in the Loop"].append("do you really want to enter subgraph?[y/n]")

    value = interrupt({"text_to_revise": "subgraph"})
 
    if value.get("type") == "accept":

        return [Command(goto="input_node", update={"decision": "approved"})]

    else:

        return [Command(goto="info", update={"decision": "rejected"})]
 
def check_node(state: OverallState) ->CompletedState:
    #TODO:add more specific check rules
    print("[debug] this is check node")
    state_dict={"operation":None,"not_completed": False,
                    "UP_version_lookup": False,
                    "du_ip_look_up": False,         
                    "up_count": -1}
    valid_operations = ["install", "INSTALL","Install",
                     "Upgrade","UPGRADE","upgrade",
                     "configuration","Configuration","CONFIGURATION"]
    try:
        if state["operation"]=="upgared":
            state["operation"]="upgrade"
        if state["operation"] not in valid_operations:
            print(f"[debug]invalid operation:{state['operation']}")
            state["operation"]=None
        
        ip_str=state["IP"]
        if not is_valid_ip(ip_str):
            print(f"[debug]invalid IP address:{ip_str}")
            state["IP"]=None
        
        valid_DU_names = ["cnbj","CNBJ","seki","SEKI"]
        if state.get("hardware_name",None) is not None and not state["hardware_name"].startswith(tuple(valid_DU_names)):
            print("[debug]invalid hardware name")
            state["hardware_name"]=None

        if state["UP_version"] is None:
            print("[debug]UP_version is None")
            state_dict["UP_version_lookup"]=True
        else:
            if state["UP_version"].startswith("latest UP") or state["UP_version"].startswith("latest up"):
                print("[debug]UP_version is latest UP")
                state_dict["UP_version_lookup"]=True
            elif not (state["UP_version"].startswith("CXP") or state["UP_version"].startswith("cxp")) :
                print(f"[debug]invalid UP_version:{state['UP_version']}")
                state["UP_version"]=None
                state_dict["not_completed"]=True
                #TODO: examine this logic
        
        if (state["IP"] is None) and (state["hardware_name"] is None):
            print("[debug]IP and DU_name are both None")
            state_dict["not_completed"]=True
            state_dict["du_ip_look_up"]=False
        elif xor(state["IP"] is None , state["hardware_name"] is None):
            print("[debug]IP and DU_name are not both None")
            state_dict["du_ip_look_up"]=True
        else:
            state_dict["du_ip_look_up"]=False
            
        valid_post_steps = ["initial_configuration",
                            "CUCP_CUUP_DU_5Qi_table",
                            "iodt_recomm_netconfig",
                            "VONR_Configuration"]
        if state["Post_step"] is not None and state["Post_step"] not in valid_post_steps:
            state["Post_step"]=None
            print(f"[debug]invalid Post_step:{state['Post_step']}")
        
        valid_senario_for_tags=["nr_scenario_1LB_C1_plus_2MB_C2_Radio_3cell_1F2T",
                                "nr_scenario_HB_8cell_TDD",
                                "nr_scenario_LB_3cell_FDD",
                                "nr_scenario_MB_AIR_AAS_C2_Radio_3cell_TDD",
                                "nr_scenario_MB_RUS_C1_Radio_3cell_TDD",
                                "nr_scenario_MultiSec_MB_RUS_C1_3Cells_TDD",
                                "scenario_lte_FDDESS_scenario_ESS_3cell_FDD"]
        if state["Scenario_for_tags"] is not None and state["Scenario_for_tags"] not in valid_senario_for_tags:
            state["Scenario_for_tags"]=None
            print(f"[debug]invalid Scenario for tags:{state['Scenario for tags']}")
        
        valid_netconf=["nr_scenario_1LB_C1_plus_2MB_C2_Radio_3cell_1F2T",
                    "nr_scenario_HB_8cell_TDD",
                    "nr_scenario_LB_3cell_FDD",
                    "nr_scenario_MB_AIR_AAS_C2_Radio_3cell_TDD",
                    "nr_scenario_MB_RUS_C1_Radio_3cell_TDD",
                    "nr_scenario_MultiSec_MB_RUS_C1_3Cells_TDD",
                    "scenario_lte_FDDESS_scenario_ESS_3cell_FDD"]
        
        if state["Netconf"] is not None and state["Netconf"] not in valid_netconf:
            state["Netconf"]=None
            print(f"[debug]invalid netconf:{state['Netconf']}")
        
        state_dict["operation"]=state.get("operation",None)

        #TODO: this could be problematic 
        if state["operation"] in ["configuration","Configuration","CONFIGURATION"]\
            and state.get("Tags",None) is None\
                and state.get("Scenario_for_tags",None) is None:
            print("[debug]please provide tag or Scenario for tags for configuration")
            state_dict["not_completed"]=True

        state_dict["IP"]=state.get("IP",None)
    except KeyError as e:
        print("[debug] something is wrong with the graph routing")
        Command(goto="info")
    return state_dict


def should_continue(state: CompletedState):
    print("[debug]should_continue")
    print(state)
    if state["not_completed"]:
        print("[debug]makeup_node")
        return "makeup_node"
    if state["du_ip_look_up"]:
            print("[debug]look_up_du_ip_pair")
            return "look_up_du_ip_pair"
    if state["UP_version_lookup"]:
        print("[debug]latest_up")
        return "latest_up"
    
    if state["operation"]=="upgrade":
        print("[debug]check_up_number")
        return "check_up_number"
    else:
        print("[debug]final_confirmation")
        return "final_confirmation"


def final_confirmation(state: OverallState)-> Command[Literal["execution_node","modify_configuration"]]:
    global global_log
    memoryy_str="[debug]final confirmation\n"+"current configuration:\n"+str(state)
    if state["operation"] in ["install","INSTALL","Install"] and state.get("Netconf",None)==None:
        memoryy_str=memoryy_str+"\n[Warning]Installing without netconf is not recommended."
    if not state["Post_step"]:
        memoryy_str=memoryy_str+"\n[Warning]No post_step is selected."
    global_log["AI_Response"].append(f"{memoryy_str}")
    global_log["Human in the Loop"].append(memoryy_str)
    value = interrupt(  
        {
            "text_to_revise": state["operation"]  
        }
    )
    print(f"[debug]final confirm,received response {value}")
    try:
        if value.get("type",None)=="accept":
            return Command(goto="execution_node", update={"decision": "approved"})
        else:
            return Command(goto="modify_configuration", update={"decision": "rejected"})
    except:
        return Command(goto="modify_configuration", update={"decision": "rejected"})


def rewrite_sc(state:CompletedState):
    #TODO:add rewrite sc in OverallState
    memoryy_str="\ndo you want to rewrite sc?[y/n]"
    global global_log
    global_log["AI_Response"].append(f"{memoryy_str}")
    global_log["Human in the Loop"].append(memoryy_str)
    value = interrupt(  
        {
            "text_to_revise": state["operation"]  
        }
    )
    try:
        if value.get("type",None)=="accept":
            print("[debug]rewrite sc")
        else:
            print("[debug]do not rewrite sc")
    except:
        print("[debug]do not rewrite sc")
    return


async def execution_node(state: OverallState):
    import time
    global subgraph_processing
    subgraph_processing=False
    memoryy_str="[debug]I am executing this job."
    memoryy_str=memoryy_str+"Command executing, parameters shown as below:\n"+str(state)
    global_log["AI_Response"].append(f"{memoryy_str}")
    command=['curl', '-i','http://iodt.gic.ericsson.se:8443/job/Test_Display/buildWithParameters',
             '-H','Jenkins-Crumb: 559d7bb61411b0bd9d440f345cc028ddf3206e04fc0dd7c833dd4913a04f6cc2',
             '-u','exekixl:11c848d84dd182a977f18e9f10f81b60f8'
             ]
    du_str=f'DU_Name="{state.get("IP",state.get("hardware_name",""))}"' 
    command.extend(['--form', du_str])
    up_str=f'UP_version="{state.get("UP_version","")}"' 
    command.extend(['--form', up_str])
    op_str=f'Operation="{state.get("operation","")}"' 
    command.extend(['--form', op_str])
    netc_str=f'Scenario_for_netconf="{state.get("Netconf","")}"' 
    command.extend(['--form', netc_str])
    sce_str=f'Scenario_for_tags="{state.get("Scenario_for_tags","")}"' 
    command.extend(['--form', sce_str])
    tags_str=f'Tags="{state.get("Tags","")}"' 
    command.extend(['--form', tags_str])
    post_str=f'Post_step="{state.get("Post_step","")}"'
    command.extend(['--form', post_str])
    
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
        url=dict2.get('url',"nothing")
        print("[debug]url:"+str(url))
        url_ret_str=f"[Jenkins link]({url})"
        global_log["AI_Response"].append(f"\nurl: {url_ret_str}")

    except subprocess.CalledProcessError as e:
        print(f"请求失败! 错误信息: {e.stderr}")
        return None
    except Exception as e:
        print(f"发生未知错误: {str(e)}")
    return


def should_execute(state: CompletedState):
    if state["not_completed"]:
        return "modify_configuration"
    else:
        return "execution_node"
def should_upgrade(state: CompletedState):
    if state["up_count"] > 0 and state["up_count"] < 5:
        return "rewrite_sc"
    else:
        return END
    
""""""
def clear_message_node(state: OverallState) -> State:
    return {
            "messages":  ""
        }
    
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
    async def latest_up(state: OverallState)-> OverallState:
        for tool in mcp_tools:
            if tool.name == "get_latest_UP_version":  #tool name
                MCP_result = await tool.ainvoke({"number_versions": "3", "confidence_level": "3"}) #å‚æ•°åå’Œå€¼
                print("aaaaaaa is",MCP_result)

        data = json.loads(MCP_result)
        state["UP_version"]=data["1"]
        return state
    def call_subgraph(state: State) -> State:
        last_msg = state["messages"][-1].content if state["messages"] else ""
        print(f"[debug]last message:{last_msg}")
        
        response = subgraph.invoke({
            "submessage": last_msg,
            "user_input": ""
        })
        return {
            "messages": state["messages"] + [AIMessage(content=response["submessage"])],
            "subgraph": "done"
        }
    async def check_up_number(state:CompletedState)->CompletedState:
        #TODO:tool call
        for tool in mcp_tools:
            if tool.name =="check_UP_number":  #tool name
                MCP_result = await tool.ainvoke({"du_ip":state["IP"]}) 
        data = json.loads(MCP_result)
        state["up_count"]=data["count"]
        return state
    async def input_node(state: State) -> OverallState:
        
        global subgraph_processing
        subgraph_processing=True
        llm = await create_llm()
        set_verbose(True)
        set_debug(True)
        human_messages = [
        msg for msg in state["messages"] 
        if isinstance(msg, HumanMessage)
        ]
        if not human_messages:
            return
        last_human_msg = human_messages[-1]  
        prompt_hint= """Your task is to gather specific information from the user regarding DU(a kind of device) install, upgrade, or configuration.
        You need to collect the following information from the user:
        1. The operation the user wants to perform. Currently, three operations are supported: install, upgrade, and configuration.
        All three operations can be done with some netconf, so carefully distinguish between the configuration operation and adding netconf for install or upgrade.
        2. The device name or IP address. The name usually starts with "cnbj" or "seki".
            put the device name into the field of "hardware_name".
        3. UP version: the software version the user needs. It usually starts with "cxc", and "latest UP" is also supported.
        4. Netconf: the required netconf from the user. (This is optional for upgrade and configuration operations, but recommended for installation.)Netconf list is [nr_scenario_1LB_C1_plus_2MB_C2_Radio_3cell_1F2Tï¼Œnr_scenario_HB_8cell_TDDï¼Œnr_scenario_LB_3cell_FDDï¼Œnr_scenario_MB_AIR_AAS_C2_Radio_3cell_TDDï¼Œnr_scenario_MB_RUS_C1_Radio_3cell_TDDï¼Œnr_scenario_MultiSec_MB_RUS_C1_3Cells_TDDï¼Œscenario_lte_FDDESS_scenario_ESS_3cell_FDD]
        5. Scenario_for_tags:If the user wants to apply IODT-recommended parameters, they can provide a Netconf file. The system will automatically extract the relevant tags from it to apply the recommended parameters.Netconf list is [nr_scenario_1LB_C1_plus_2MB_C2_Radio_3cell_1F2Tï¼Œnr_scenario_HB_8cell_TDDï¼Œnr_scenario_LB_3cell_FDDï¼Œnr_scenario_MB_AIR_AAS_C2_Radio_3cell_TDDï¼Œnr_scenario_MB_RUS_C1_Radio_3cell_TDDï¼Œnr_scenario_MultiSec_MB_RUS_C1_3Cells_TDDï¼Œscenario_lte_FDDESS_scenario_ESS_3cell_FDD]
        
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
        Post_step:str}
        **Literally just return the json itself without any suffix or prefix.**
        """
        content=prompt_hint+"user input:"+last_human_msg.content
        response_str=llm.invoke(content)
        print("[debug]raw response="+response_str.content)
        try:
            response_dict = json.loads(response_str.model_dump_json())
        except json.JSONDecodeError:
            response_dict = {}
        print("[debug]response="+json.dumps(response_dict))
        response_content=response_dict["content"]
        if isinstance(response_content, dict):
            response=response_content
        else:
            print(f"[debug]the type is{type(response_content)}")
            try:
                response = json.loads(response_content)
            except json.JSONDecodeError as e:
                # æ‰“å°åŽŸå§‹å“åº”å¸®åŠ©è°ƒè¯•
                print(f"âš ï¸ JSONè§£æžå¤±è´¥! åŽŸå§‹å“åº”å†…å®¹:\n{response_content}")
                print(f"é”™è¯¯ä½ç½®: {e.pos} å­—ç¬¦, è¡Œ{e.lineno}åˆ—{e.colno}")
        operation_name = response.get("operation", None)
        DU_name=response.get("hardware_name", None)
        ip_address=response.get("IP", None)
        UP_version=response.get("UP_version", None)
        tags=response.get("Tags", None)
        configuration=response.get("Configuration", None)
        post_step=response.get("Post_step", None)
        netconf=response.get("Netconf", None)
        senario_for_tags=response.get("Scenario_for_tags", None)
        return {
            "operation": operation_name,
            "hardware_name": DU_name,
            "IP":ip_address,
            "UP_version": UP_version,
            "Tags":tags,
            "Scenario_for_tags":senario_for_tags,
            "Netconf":netconf,
            "Post_step":post_step
            }

    async def modify_configuration(state: OverallState) -> OverallState:
        memoryy_str="current configuration:\n"+str(state)
        memoryy_str=memoryy_str+"\nhow would you like to modify:"
        global global_log
        global_log["AI_Response"].append(f"{memoryy_str}")
        value = interrupt(  
            {
                "text_to_revise": state["operation"]  
            }
        )
        try:
            prompt_hint= """Your task is to gather specific information from the user regarding DU(a kind of device) install, upgrade, or configuration.
                
                You need to collect the following information from the user:
                
                1. The operation the user wants to perform. Currently, three operations are supported: install, upgrade, and configuration.
                All three operations can be done with some netconf, so carefully distinguish between the configuration operation and adding netconf for install or upgrade.
                ** the user is unlikely to change the operation.**
                ** the user is unlikely to change the operation.**
                ** the user is unlikely to change the operation.**
                ** if the user mentions specific configuration, please put it into the field of "Configuration". It has nothing to do with the operation.**
                ** if the user mentions specific configuration, please put it into the field of "Configuration". It has nothing to do with the operation.**
                ** if the user mentions specific configuration, please put it into the field of "Configuration". It has nothing to do with the operation.**
                2. The device name or IP address. The name usually starts with "cnbj" or "seki".
                    put the device name into the field of "hardware_name".
                3. UP version: the software version the user needs. It usually starts with "cxc", and "latest UP" is also supported.
                
                4. Netconf: the required netconf from the user. (This is optional for upgrade and configuration operations, but recommended for installation.)Netconf list is [nr_scenario_1LB_C1_plus_2MB_C2_Radio_3cell_1F2Tï¼Œnr_scenario_HB_8cell_TDDï¼Œnr_scenario_LB_3cell_FDDï¼Œnr_scenario_MB_AIR_AAS_C2_Radio_3cell_TDDï¼Œnr_scenario_MB_RUS_C1_Radio_3cell_TDDï¼Œnr_scenario_MultiSec_MB_RUS_C1_3Cells_TDDï¼Œscenario_lte_FDDESS_scenario_ESS_3cell_FDD]
                    
                5. Scenario_for_tags:If the user wants to apply IODT-recommended parameters, they can provide a Netconf file. The system will automatically extract the relevant tags from it to apply the recommended parameters.Netconf list is [nr_scenario_1LB_C1_plus_2MB_C2_Radio_3cell_1F2Tï¼Œnr_scenario_HB_8cell_TDDï¼Œnr_scenario_LB_3cell_FDDï¼Œnr_scenario_MB_AIR_AAS_C2_Radio_3cell_TDDï¼Œnr_scenario_MB_RUS_C1_Radio_3cell_TDDï¼Œnr_scenario_MultiSec_MB_RUS_C1_3Cells_TDDï¼Œscenario_lte_FDDESS_scenario_ESS_3cell_FDD]
 
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
                Post_step:str}
                **Literally just return the json itself without any suffix or prefix.**
                """
            prompt=prompt_hint+"user input:"+str(value)
            llm = await create_llm()
            response_str=llm.invoke(prompt)
            response_dict = json.loads(response_str.model_dump_json())
        except json.JSONDecodeError:
            response_dict = {}
        response_content=response_dict["content"]
        response=json.loads(extract_json_content(response_content))
        result_dict={}
        for key in state:
            print(f"[debug]the next key is:{key}")

            if not (response.get(key,None)==None or response.get(key,None)=="null" or response.get(key,None)=="None"):
                result_dict[key]=response.get(key,None)
            else:
                result_dict[key]=state.get(key,None)

        print(f"[debug]the full dictionary:{result_dict}")
        return result_dict
    async def look_up_du_ip_pair(state: OverallState)-> OverallState:
        if state["hardware_name"] is None:
            print("[debug]DU_name is None")
            for tool in mcp_tools:
                if tool.name == "DU_Name_IP Mapping":  #tool name
                    MCP_result = await tool.ainvoke({"query_key":state["IP"]})
                    print("aaaaaaa is",MCP_result)
            data = json.loads(MCP_result)
            state["hardware_name"]=data.get("DU_name",None)
            if state["hardware_name"]==None:
                state["IP"]=None
                global_log["AI_Response"].append("ip does not exist. Try another.")
        else:
            print("[debug]ip is None")
            for tool in mcp_tools:
                if tool.name == "DU_Name_IP Mapping":  #tool name
                    MCP_result = await tool.ainvoke({"query_key":state["hardware_name"]}) 
            data = json.loads(MCP_result)
            state["IP"]=data.get("sitelan_ip",None)
            if state["IP"]==None:
                state["hardware_name"]=None
                global_log["AI_Response"].append("hardware does not exist. Try another.")
        return state
    async def makeup_node(state: OverallState) -> OverallState:
        memoryy_str="the following elements are missing or incorrect,please make up:\n"+str(state)
        for key in state:
            if state.get(key,None) ==None:
                memoryy_str=memoryy_str+"\n"+key
        missing_elmt=[]
        global_log["AI_Response"].append(f"{memoryy_str}")
        value = interrupt(  
            {
                "make up incorrect info"
            }
        )
        print("the following elements are missing or incorrect,please make up:")
        for key in state:
            if state.get(key,None) ==None:
                missing_elmt.append(key)
                print(key)
        try:
            prompt_hint= """Your task is to gather specific information from the user regarding DU(a kind of device) install, upgrade, or configuration.
    
            You need to collect the following information from the user:
            
            1. The operation the user wants to perform. Currently, three operations are supported: install, upgrade, and configuration.
            
            2. The device name or IP address. The name usually starts with "cnbj" or "seki".
            put the device name into the field of "hardware_name".
            3. UP information: the software version the user needs. It usually starts with "cxc", and "latest UP" is also supported.
            
            4. Netconf: the required netconf from the user. (This is optional for upgrade and configuration operations, but recommended for installation.)Netconf list is [nr_scenario_1LB_C1_plus_2MB_C2_Radio_3cell_1F2Tï¼Œnr_scenario_HB_8cell_TDDï¼Œnr_scenario_LB_3cell_FDDï¼Œnr_scenario_MB_AIR_AAS_C2_Radio_3cell_TDDï¼Œnr_scenario_MB_RUS_C1_Radio_3cell_TDDï¼Œnr_scenario_MultiSec_MB_RUS_C1_3Cells_TDDï¼Œscenario_lte_FDDESS_scenario_ESS_3cell_FDD]
            
            5. Scenario_for_tags:If the user wants to apply IODT-recommended parameters, they can provide a Netconf file. The system will automatically extract the relevant tags from it to apply the recommended parameters.Netconf list is [nr_scenario_1LB_C1_plus_2MB_C2_Radio_3cell_1F2Tï¼Œnr_scenario_HB_8cell_TDDï¼Œnr_scenario_LB_3cell_FDDï¼Œnr_scenario_MB_AIR_AAS_C2_Radio_3cell_TDDï¼Œnr_scenario_MB_RUS_C1_Radio_3cell_TDDï¼Œnr_scenario_MultiSec_MB_RUS_C1_3Cells_TDDï¼Œscenario_lte_FDDESS_scenario_ESS_3cell_FDD]
 
            6. Tags: If the user wants to apply IODT-recommended parameters, they can provide a tag combination (comma-separated, e.g., NR_SA_MB, NR_SA_MB_C1). Only one of Tags or Scenario_for_tags is required.

            7. Post_step: any additional installation scripts. (Not mandatory, but confirm with the user whether such scripts are needed. list are:initial_configuration, CUCP_CUUP_DU_5Qi_table,iodt_recomm_netconfig,VONR_Configuration)
            
            Return only with the json format shown below. If unsure, **put a json null** in the corresponfing field

            {operation:str
            hardware_name:str
            IP:str
            UP_version:str
            Tags:str
            Scenario_for_tags:str
            Netconf:str
            Post_step:str}
            **Literally just return the json itself without any suffix or prefix.**"""
            

            prompt=prompt_hint+"user input:"+f"The missing elements are as follows: {missing_elmt}"+"put all and only the keys and values of missing elements into a json-formatted string."+value
            llm = await create_llm()
            response_str=llm.invoke(prompt)
            response_dict = json.loads(response_str.model_dump_json())
        except json.JSONDecodeError:
            response_dict = {}
        response_content=response_dict["content"]
        response=json.loads(extract_json_content(response_content))
        result_dict={}
        for key in state:
            if not state.get(key,None)==None:
                result_dict[key]=state.get(key,None)
            else:
                result_dict[key]=response.get(key,None)
        print(f"[debug]the full dictionary:{result_dict}")
        return result_dict

    async def info_node(state: State) -> State | Command:
        global global_log
        start_time = time.time()
        llm = await create_llm()
        llm_with_tools = llm.bind_tools(all_tools)
        print("Message in infor node :",state["messages"])
        if not any(isinstance(m, SystemMessage) for m in state["messages"]):
            messages = [SystemMessage(content=template)] + state["messages"]
        else:
            messages = state["messages"]
        response = llm_with_tools.invoke(messages)
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

        # åŽ»æŽ‰å¤šä½™ç©ºè¡Œ
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
    async def result_processing_node(state):
        global global_log
        llm = await create_llm()
        llm_with_tools = llm.bind_tools(mcp_tools)
        messages = state.get("messages", [])

        analysis_message = {
            "role": "user", 
           "content": "Analyze the tool execution result. Rewrite it to make it more readable and concise while preserving all important details. "

        }
        response = llm.invoke(messages + [analysis_message])


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

        return {"messages": messages + [analysis_message, response]}
    

    graph_builder.add_node("info", info_node)
    tool_node = ToolNode(tools=all_tools)
    graph_builder.add_node("tools", tool_node)
    graph_builder.add_node("subgraph_node", call_subgraph)
    graph_builder.add_node("human_approval", human_approval)
    graph_builder.add_node("result_processing", result_processing_node) 

    graph_builder.add_edge(START, "info")
    graph_builder.add_conditional_edges("info", get_state)
    graph_builder.add_edge("tools", "result_processing")
    graph_builder.add_edge("result_processing", END) 
    """"""#TODO:delete this in later versions
    graph_builder.add_node("into_subgraph", into_subgraph)
    graph_builder.add_node("check_node", check_node)
    graph_builder.add_node("input_node", input_node)
    graph_builder.add_node("makeup_node",makeup_node)
    graph_builder.add_node("execution_node",execution_node)
    graph_builder.add_node("rewrite_sc",rewrite_sc)
    graph_builder.add_node("check_up_number",check_up_number)
    graph_builder.add_node("latest_up",latest_up)
    graph_builder.add_node("look_up_du_ip_pair",look_up_du_ip_pair)
    graph_builder.add_node("final_confirmation",final_confirmation)
    graph_builder.add_node("modify_configuration",modify_configuration)
    graph_builder.add_node("clear_message_node",clear_message_node)
  
    
    graph_builder.add_edge("subgraph_node","input_node")
    graph_builder.add_edge("input_node", "check_node")
    graph_builder.add_edge("makeup_node", "check_node")
    graph_builder.add_edge("check_up_number", "rewrite_sc")
    graph_builder.add_edge("look_up_du_ip_pair","check_node")
    graph_builder.add_edge("rewrite_sc", "final_confirmation")
    graph_builder.add_edge("latest_up", "check_node")
    graph_builder.add_edge("modify_configuration","check_node")
    graph_builder.add_edge("execution_node","clear_message_node")#是这个吗？
    graph_builder.add_edge("clear_message_node","info")
    graph_builder.add_conditional_edges("clear_message_node", get_state)
    graph_builder.add_conditional_edges("check_node",should_continue,)
    graph_builder.add_conditional_edges("check_up_number", should_upgrade,)
    """"""
    memory = InMemorySaver()
    graph = graph_builder.compile(checkpointer=memory)
    


@app.post("/run/")
async def execute_2(plan: dict):
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
    if subgraph_processing:
        command = Command(resume=user_input)
        stream = graph.astream(command, config=config)
    else:
        initial_state = {
            "messages": [HumanMessage(content=user_input)],
            "subgraph": "false",
            "log": []
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
    uvicorn.run("router_8_app:app", host="0.0.0.0", port=777, reload=True)


