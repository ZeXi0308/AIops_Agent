import os
import re
import asyncio
import contextlib
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from jira import JIRA
from mcp.server.fastmcp import FastMCP
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("JIRAExtractor")
mcp = FastMCP(name="JIRAExtractor")

JIRA_SERVER = os.getenv("JIRA_SERVER", "https://eteamproject.internal.ericsson.com")
JIRA_USERNAME = os.getenv("JIRA_USERNAME", "TATXOBMMBS")
JIRA_PASSWORD = os.getenv("JIRA_PASSWORD", "IoDt20254IoDt20254")
DEFAULT_PROJECT = "IODTIT"


DEFAULT_STATUS = None

jira_client = None

async def get_jira_client():
    global jira_client
    if jira_client is None:
        options = {'server': JIRA_SERVER}
        jira_client = JIRA(options, basic_auth=(JIRA_USERNAME, JIRA_PASSWORD))
    return jira_client

def parse_jira_datetime(dt_str):
    if '+' in dt_str:
        dt_str = dt_str[:dt_str.rfind('+')]
    try:
        return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError:
        return dt_str

def format_jira_date(jira_date_str):
    if jira_date_str:
        return jira_date_str.split("T")[0]
    return ''

# In JIRAExtractor.py

def parse_natural_query(query_text: str) -> Dict[str, Any]:
    query_lower = query_text.lower()
    params = {}
    
    # --- 1. 解析 Component ---
    component_match = re.search(r's\d+', query_lower)
    if component_match:
        params['component'] = component_match.group().upper()
    
    # --- 2. 解析 Status ---
    if "open" in query_lower:
        params['status'] = "Open"
    elif "closed" in query_lower:
        params['status'] = "Closed"
    elif "done" in query_lower:
        params['status'] = "Done"
    
    # --- 3. 解析 Year ---
    year_match = re.search(r'\b(20\d{2})\b', query_text)
    if year_match:
        params['year'] = year_match.group(1)
        
    # --- 4. 解析 TC Number ---
    # 这个更灵活的正则表达式寻找'tc'相关的词，并捕获后面的数字
    tc_match = re.search(r'tc(?:[#_\s]*number)?\s*(?:is\s*)?(\d{5,})', query_lower)
    if tc_match:
        params['tc_number'] = tc_match.group(1)

    # # --- 5. 解析 Fault On ---
    fault_on_values = [
        'NW', 'UE', 'LAB', 'Core NW', 'Configuration', 
        'Documentation', 'Under investigation'
    ]
    
    # 构建正则表达式匹配所有可能的值
    pattern = r'\b(' + '|'.join(re.escape(v) for v in fault_on_values) + r')\b'
    fault_on_match = re.search(pattern, query_text, re.IGNORECASE)
    
    if fault_on_match:
        # 找到匹配的原始值（保持正确的大小写）
        matched_value = fault_on_match.group(1)
        for original_value in fault_on_values:
            if original_value.lower() == matched_value.lower():
                params['fault_on'] = original_value
                break
        
    return params
    # # 这个解析逻辑现在完全独立，不再受前面匹配的影响
    # fault_on_values = [
    #     'NW', 'UE', 'LAB', 'Core NW', 'Configuration', 
    #     'Documentation', 'Under investigation'
    # ]
    # # 构建一个能匹配 "fault on is VALUE" 或 "fault on VALUE" 的模式
    # # 将所有可能的值用'|'连接起来，这使得正则表达式可以一次性检查所有可能性
    # pattern = r'fault[_\s]+on\s*(?:is\s*)?(' + '|'.join(v.replace(" ", r'\s+') for v in fault_on_values) + r')'
    # fault_on_match = re.search(pattern, query_lower, re.IGNORECASE)
    
    # if fault_on_match:
    #     # group(1) 捕获的是括号内的值
    #     matched_value_from_regex = fault_on_match.group(1).lower().replace(' ', '')
    #     # 需要从原始列表中找到正确的大小写格式
    #     for original_value in fault_on_values:
    #         if original_value.lower().replace(' ', '') == matched_value_from_regex:
    #             params['fault_on'] = original_value
    #             break
        

def build_jql_query(project: str = DEFAULT_PROJECT, status: str = None, component: str = None, 
                   year: str = None, days_updated: int = None, tc_number: str = None, fault_on: str = None, custom_conditions: str = None) -> str:
    query_parts = [f'project = {project}']
    
    if status:
        query_parts.append(f'status = "{status}"')
    else:
        query_parts.append('status IN ("Open", "Closed", "Done")')
    
    if component:
        query_parts.append(f'component = "{component}"')
    
    if year:
        query_parts.append(f'created >= "{year}-01-01" AND created <= "{year}-12-31"')
    
    if days_updated:
        query_parts.append(f'updated >= -{days_updated}d')

    
    # 如果 tc_number 存在，就把它添加到JQL查询中
    if tc_number:
        # cf[20005] 是 TC# 字段的ID。
        query_parts.append(f'cf[20005] ~ "{tc_number}"')

   
    # 如果 fault_on 存在，就把它添加到JQL查询中
    if fault_on:
        query_parts.append(f'cf[13410] = "{fault_on}"')
    
    if custom_conditions:
        query_parts.append(custom_conditions)
    
    return ' AND '.join(query_parts)


#在get_issue_statistics调用生成统计数据
def generate_stats_formatted_output(stats: Dict[str, Any], query: str) -> str:
    output_lines = []
    output_lines.append("JIRA Issues Statistics Report")
    output_lines.append("=" * 50)
    output_lines.append("")
    output_lines.append(f"Total Issues: {stats['total_issues']}")
    output_lines.append(f"Open Issues: {stats['open_issues']}")
    output_lines.append(f"Closed Issues: {stats['closed_issues']}")
    output_lines.append("")
    
    output_lines.append("Issues by Status:")
    output_lines.append("-" * 20)
    for status, count in stats['by_status'].items():
        output_lines.append(f"  {status}: {count}")
    output_lines.append("")
    
    output_lines.append("Issues by Vendor/Component:")
    output_lines.append("-" * 30)
    for vendor, count in stats['by_vendor'].items():
        output_lines.append(f"  {vendor}: {count}")
    output_lines.append("")
    
    output_lines.append("=" * 50)
    output_lines.append(f"Query executed: {query}")
    
    return "\n".join(output_lines)



def generate_formatted_output(issues_data: List[Dict[str, Any]], summary: Dict[str, Any]) -> str:
    if not issues_data:
        return f"No issues found matching the query criteria.\n\nQuery executed: {summary['query_executed']}"
    
    output_lines = []
    output_lines.append(f"JIRA Query Results: {summary['total_issues']} issues found")
    output_lines.append("=" * 80)
    output_lines.append("")
    
    # for i, issue in enumerate(issues_data, 1):
    #     output_lines.append(f"Issue #{i}")
    #     output_lines.append("-" * 40)
    #     output_lines.append(f"Vendor: {issue.get('Vendor', 'N/A')}")
    #     output_lines.append(f"Issue No: {issue.get('No.', 'N/A')}")
    #     output_lines.append(f"Feature: {issue.get('Feature', 'N/A')}")
    #     output_lines.append(f"TC#: {issue.get('TC#', 'N/A')}")
    #     output_lines.append(f"TC Group or TC Tag: {issue.get('TC Group or TC Tag', 'N/A')}")
    #     output_lines.append(f"Issue Description: {issue.get('Issue Description', 'N/A')}")
    #     output_lines.append(f"Status: {issue.get('Status', 'N/A')}")
    #     output_lines.append(f"Created Date: {issue.get('Created Date', 'N/A')}")
    #     output_lines.append(f"Found by: {issue.get('Found by:', 'N/A')}")
        
    #     fault_on = issue.get('Fault on:', 'N/A')
    #     if fault_on and fault_on != 'N/A':
    #         output_lines.append(f"Fault on: {fault_on}")
        
    #     tr_number = issue.get('TR#', '')
    #     if tr_number:
    #         output_lines.append(f"TR#: {tr_number}")
        
    #     duplex_mode = issue.get('Duplex mode', '')
    #     if duplex_mode:
    #         output_lines.append(f"Duplex mode: {duplex_mode}")
        
    #     closed_date = issue.get('Closed Date', '')
    #     if closed_date:
    #         output_lines.append(f"Closed Date: {closed_date}")
        
    #     output_lines.append("")
    
    # output_lines.append("=" * 80)
    output_lines.append(f"Query executed: {summary['query_executed']}")
    
    return "\n".join(output_lines)

async def extract_jira_data(jql_query: str, max_results: int = 1000) -> List[Dict[str, Any]]:
    jira = await get_jira_client()
    
    fields = "summary,status,components,comment,created,resolutiondate,updated,reporter,customfield_19338,customfield_20005,customfield_12926,customfield_13410,customfield_22252,customfield_46610,customfield_46612"
    
    issues = jira.search_issues(jql_query, maxResults=max_results, fields=fields)
    
    issue_list = []
    
    for issue in issues:
        issue_number = issue.key
        
        if issue_number == 'IODTIT-506':
            continue
        
        comments = getattr(issue.fields, 'comment', None)
        comment_entries = []
        if comments and comments.comments:
            sorted_comments = sorted(
                comments.comments,
                key=lambda c: parse_jira_datetime(c.created)
            )
            for c in sorted_comments:
                created_dt = parse_jira_datetime(c.created)
                created_str = created_dt.strftime("%Y-%m-%d %H:%M:%S") if isinstance(created_dt, datetime) else c.created
                comment_entries.append(f"[{created_str}] {c.author.displayName}: {c.body.strip()}")
        all_comments_str = "\n\n".join(comment_entries)
        
        vendor = issue.fields.components[0].name if issue.fields.components else 'Unknown'
        feature = getattr(issue.fields, 'customfield_19338', None)
        tc_number = getattr(issue.fields, 'customfield_20005', None)
        tc_group_tag = getattr(issue.fields, 'customfield_12926', None)
        issue_description = issue.fields.summary
        status = str(issue.fields.status)
        created_date = format_jira_date(getattr(issue.fields, 'created', ''))
        closed_date = format_jira_date(getattr(issue.fields, 'resolutiondate', ''))
        fault_on = getattr(issue.fields, 'customfield_13410', None)
        tr_number = getattr(issue.fields, 'customfield_22252', None)
        updated = format_jira_date(getattr(issue.fields, 'updated', ''))
        found_by = str(getattr(issue.fields, 'reporter', ''))
        duplex_1 = getattr(issue.fields, 'customfield_46610', None)
        duplex_2 = getattr(issue.fields, 'customfield_46612', None)
        duplex_mode = f"{duplex_1}_{duplex_2}" if duplex_1 and duplex_2 else ""
        
        matches = re.findall(r'\d+', tc_number) if tc_number else []
        if matches:
            tol = '20' + matches[0][:2]
        elif created_date:
            tol = created_date.split('-')[0]
        else:
            tol = None
        
        if status in ['Done', 'Closed'] and not closed_date:
            closed_date = updated
        
        data = {
            'Vendor': vendor,
            'No.': issue_number,
            'Feature': feature,
            'TC#': tc_number,
            'TC Group or TC Tag': tc_group_tag,
            'Issue Description': issue_description,
            'Status': status,
            'Created Date': created_date,
            'Closed Date': closed_date,
            'Fault on:': str(fault_on),
            'Found by:': found_by,
            'Duplex mode': duplex_mode,
            'TR#': tr_number,
            'TOL': tol,
            'Comments': all_comments_str,
        }
        issue_list.append(data)
    
    return issue_list

@mcp.tool(
    name="query_jira_issues",
    description=(
    '''
    **Tool Name: query_jira_issues**

    **Function:** Search and query JIRA issues from the IODTIT project. Use this tool when users ask about JIRA issues, or want to find/search/list issues by status (open/closed/done), component (S65/S12), TC number, feature, or any other criteria. Supports natural language queries like 'show me open issues' or 'show S65 issues'.

    ---

    ### AI AGENT INSTRUCTIONS
    1. Your primary task is to understand the user's natural language query.
    2. If the query can be parsed by the built-in parser, normal flow applies. **1. The Fast Path (Attempt Structured Parsing First):**
    Your first priority is to be fast and reliable. Examine the user's query and see if their entire request can be satisfied by extracting values for the following simple, known parameters:
    - `component` (e.g., S65, S12)
    - `status` (e.g., Open, Closed)
    - `year` (e.g., 2025)
    - `tc_number` (e.g., 24426)
    
    * **IF** you can map the user's query cleanly to one or more of these parameters, you **SHOULD** call the `query_jira_issues` tool by passing these structured parameters directly. This is the preferred, most efficient method.
    * **Example for the Fast Path:**
        * **User:** "show me s65 open issues with tc# 12345"
        * **Your Reasoning:** This query can be broken down perfectly into `component='S65'`, `status='Open'`, and `tc_number='12345'`. I will use the structured parameter call.
        * **Your Action:** Call the tool like this: `query_jira_issues(component='S65', status='Open', tc_number='12345')`
        

    3. If the query cannot be parsed, you MUST translate the query into a precise JQL string using the field documentation below, and call this tool using **ONLY the `custom_jql` parameter**.


    ---

    ### JQL FIELD DOCUMENTATION

    **1. Feature (特性):**
    - **JQL Field:** `cf[19338]`
    - **Operator:** `~` (CONTAINS, fuzzy match)
    - **Instruction: ** Always wrap user input with * before and after.
    - **Example:** User says "feature is 7865-SP1 or 7865-SP1 feature or ", generate:  
    `cf[19338] ~ "*7865-SP1*"`

    ---

    **2. Created Date (创建日期):**
    - **JQL Field:** `created`
    - **Operators:** `=`, `>`, `<`, `>=`, `<=`
    - **Value Format:**  
    - Absolute: `YYYY-MM-DD`  
    - Relative: `-30d` (last 30 days), `-1w` (last week), `startOfMonth()`  
    - **Example:** User says *"created in the last month"*, generate:  
    `created >= -30d`

    ---

    **3. Closed Date / Resolution Date (关闭日期):**
    - **JQL Field:** `resolutiondate`
    - **Operators:** `=`, `>`, `<`, `>=`, `<=`
    - **Value Format:** Same as Created Date
    - **Example:** User says *"closed this week"*, generate:  
    `resolutiondate >= startOfWeek()`

    ---

    **4. TR Number (TR#):**
    - **JQL Field:** `cf[22252]`
    - **Operator:** `=` (EXACT MATCH, after trimming whitespace)
    - **Example:** User says *"TR number is 12345"*, generate:  
    `cf[22252] = "12345"`

    ---
    '''
    )
)
async def query_jira_issues(
    query_text: str = None,
    project: str = DEFAULT_PROJECT,
    status: str = DEFAULT_STATUS,
    component: str = None,
    tc_number: str = None,
    fault_on: str = None,
    year: str = None,
    days_updated: int = None,
    custom_jql: str = None,
    max_results: int = 1000
) -> Dict[str, Any]:
    try:
        if query_text:
            parsed_params = parse_natural_query(query_text)
            component = component or parsed_params.get('component')
            status = status or parsed_params.get('status')
            tc_number = tc_number or parsed_params.get('tc_number')
            fault_on = fault_on or parsed_params.get('fault_on')
            year = year or parsed_params.get('year')
            days_updated = days_updated or parsed_params.get('days_updated')
        
        if custom_jql:
            jql_query = custom_jql
        else:
            jql_query = build_jql_query(
                project=project,
                status=status,
                component=component,
                year=year,
                tc_number=tc_number,
                fault_on=fault_on,
                days_updated=days_updated
                
            )
        
        logger.info(f"Executing JQL query: {jql_query}")
        
        issues_data = await extract_jira_data(jql_query, max_results)
        
        summary = {
            "total_issues": len(issues_data),
            "query_executed": jql_query,
            "filters_applied": {
                "project": project,
                "status": status,
                "component": component,
                "year": year,
                "days_updated": days_updated
            }
        }
        
        formatted_output = generate_formatted_output(issues_data, summary)
        
        return {
            "tool_name": "query_jira_issues",
            "success": True,
            "summary": summary,
            "issues": issues_data,
            "formatted_report": formatted_output
        }
    
    except Exception as e:
        error_msg = f"JIRA query failed: {str(e)}"
        logger.error(error_msg)
        return {
            "tool_name": "query_jira_issues",
            "success": False,
            "error": error_msg,
            "issues": [],
            "formatted_report": f"Error occurred while querying JIRA: {error_msg}"
        }



# @mcp.tool(
#     name="get_issue_statistics",
#     description="Get statistical analysis of JIRA issues from the IODTIT project including counts by status, component, and vendor. This tool connects to JIRA API to provide data analytics and summaries. Returns a 'formatted_report' field with a complete statistical overview. Use the formatted_report in your response for consistent output format."
# )
# async def get_issue_statistics(
#     query_text: str = None,
#     project: str = DEFAULT_PROJECT,
#     component: str = None,
#     days_updated: int = 30
# ) -> Dict[str, Any]:
#     try:
#         if query_text:
#             parsed_params = parse_natural_query(query_text)
#             component = component or parsed_params.get('component')
#             days_updated = days_updated or parsed_params.get('days_updated', 30)
        
#         jql_query = build_jql_query(
#             project=project,
#             component=component,
#             days_updated=days_updated
#         )
        
#         issues_data = await extract_jira_data(jql_query, max_results=10000)
        
#         stats = {
#             "total_issues": len(issues_data),
#             "by_status": {},
#             "by_vendor": {},
#             "by_component": {},
#             "open_issues": 0,
#             "closed_issues": 0
#         }
        
#         for issue in issues_data:
#             status = issue.get('Status', 'Unknown')
#             vendor = issue.get('Vendor', 'Unknown')
            
#             stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
#             stats["by_vendor"][vendor] = stats["by_vendor"].get(vendor, 0) + 1
            
#             if status.lower() in ['open', 'in progress', 'new']:
#                 stats["open_issues"] += 1
#             elif status.lower() in ['done', 'closed', 'resolved']:
#                 stats["closed_issues"] += 1
        
#         formatted_stats = generate_stats_formatted_output(stats, jql_query)
        
#         return {
#             "tool_name": "get_issue_statistics",
#             "success": True,
#             "query_executed": jql_query,
#             "statistics": stats,
#             "formatted_report": formatted_stats
#         }
    
#     except Exception as e:
#         error_msg = f"Statistics query failed: {str(e)}"
#         logger.error(error_msg)
#         return {
#             "success": False,
#             "error": error_msg,
#             "statistics": {},
#             "formatted_report": f"Error occurred while generating statistics: {error_msg}"
#         }

@contextlib.asynccontextmanager
async def lifespan(app):
    logger.info("JIRAExtractor server starting")
    
    async with mcp.session_manager.run():
        yield
    
    global jira_client
    if jira_client:
        jira_client = None
    
    logger.info("JIRAExtractor server shut down")

app = Starlette(
    routes=[Mount("/", mcp.streamable_http_app())],
    lifespan=lifespan,
)



if __name__ == "__main__":
    port = int(os.getenv("JIRA_TOOL_PORT", "8004"))
    
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="info"
    )
