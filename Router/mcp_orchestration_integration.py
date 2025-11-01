"""
Integration guide for MCP Orchestration into main.py

This file shows how to integrate the MCP orchestrator into the existing Router/main.py.
"""

from mcp_orchestrator import MCPOrchestrator, detect_and_orchestrate, is_orchestration_query
from langchain_core.messages import AIMessage, HumanMessage
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# STEP 1: Add orchestration detection in info_node
# ============================================================================

async def info_node_with_orchestration(state, all_tools, llm):
    """
    Modified info_node that detects and handles orchestration queries.

    Add this logic at the beginning of your existing info_node function.
    """

    # Extract the latest user message
    human_msgs = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    if not human_msgs:
        # Fall back to normal flow
        return await original_info_node(state, all_tools, llm)

    latest_query = human_msgs[-1].content

    # Check if orchestration is needed
    if is_orchestration_query(latest_query):
        logger.info("🎭 Orchestration query detected")

        # Execute orchestration
        orchestration_result = await detect_and_orchestrate(
            query=latest_query,
            available_tools=all_tools,
            llm=llm
        )

        if orchestration_result:
            # Format the result
            formatted_output = orchestration_result["formatted_output"]

            # Update state
            state["AI_Response"] = formatted_output
            state["Thinking"] = (
                state.get("Thinking", "") +
                f"\n\n🎭 Multi-MCP Orchestration:\n"
                f"Executed {orchestration_result['tasks_count']} sequential tasks\n"
            )

            # Create AI message with the result
            response_message = AIMessage(content=formatted_output)

            return {
                "messages": state["messages"] + [response_message],
                "AI_Response": formatted_output,
                "Thinking": state["Thinking"],
                "subgraph": state.get("subgraph", "false"),
                "tool_images": state.get("tool_images", [])
            }

    # If not an orchestration query, fall back to normal flow
    return await original_info_node(state, all_tools, llm)


# ============================================================================
# STEP 2: Example integration pattern for existing info_node
# ============================================================================

def integrate_orchestration_in_existing_code():
    """
    Example showing where to add orchestration logic in existing info_node.
    """

    # In your existing startup_event() in main.py, after getting all_tools:
    '''
    async def startup_event():
        global fault_tolerant_client
        mcp_tools = await fault_tolerant_client.get_tools()
        all_tools = list(mcp_tools)

        # Add orchestrator initialization here
        orchestrator = MCPOrchestrator(all_tools)

        async def info_node(state: State) -> State | Command:
            # ... existing code ...

            # Add this before llm.ainvoke()
            messages = state["messages"]
            human_msgs = [m for m in messages if isinstance(m, HumanMessage)]

            if human_msgs:
                latest_query = human_msgs[-1].content

                # Try orchestration first
                if is_orchestration_query(latest_query):
                    orchestration_result = await detect_and_orchestrate(
                        query=latest_query,
                        available_tools=all_tools,
                        llm=llm
                    )

                    if orchestration_result:
                        formatted_output = orchestration_result["formatted_output"]
                        state["AI_Response"] = formatted_output
                        response = AIMessage(content=formatted_output)

                        return {
                            "messages": messages + [response],
                            "AI_Response": formatted_output,
                            "Thinking": state.get("Thinking", "") + "\n\n🎭 Orchestration executed",
                            "subgraph": state.get("subgraph", "false"),
                            "tool_images": state.get("tool_images", [])
                        }

            # ... continue with existing LLM flow ...
            response = await llm_with_tools.ainvoke(state["messages"])
            # ... rest of existing code ...
    '''
    pass


# ============================================================================
# STEP 3: Alternative - Create a dedicated orchestration node
# ============================================================================

async def orchestration_detection_node(state):
    """
    A separate node that can be added to the LangGraph to detect orchestration.
    """
    messages = state["messages"]
    human_msgs = [m for m in messages if isinstance(m, HumanMessage)]

    if human_msgs and is_orchestration_query(human_msgs[-1].content):
        return {
            "orchestration_needed": True,
            "query": human_msgs[-1].content
        }

    return {
        "orchestration_needed": False
    }


async def orchestration_execution_node(state, all_tools, llm):
    """
    Execute the orchestration.
    """
    query = state.get("query")

    if not query:
        return state

    result = await detect_and_orchestrate(
        query=query,
        available_tools=all_tools,
        llm=llm
    )

    if result:
        return {
            "messages": state["messages"] + [AIMessage(content=result["formatted_output"])],
            "AI_Response": result["formatted_output"],
            "Thinking": f"Executed {result['tasks_count']} orchestrated tasks"
        }

    return state


# ============================================================================
# STEP 4: Usage examples and patterns
# ============================================================================

ORCHESTRATION_EXAMPLES = {
    "jira_and_chart": {
        "query": "Show me open S65 JIRA issues from 2025 and create a pie chart",
        "expected_flow": [
            "1. Call query_jira_issues with component=S65, status=Open, year=2025",
            "2. Transform JIRA results into chart data",
            "3. Call generate_pie_chart with transformed data",
            "4. Return both JIRA report and chart"
        ]
    },
    "statistics_and_visualization": {
        "query": "Get JIRA statistics for S12 component and visualize it",
        "expected_flow": [
            "1. Call get_issue_statistics with component=S12",
            "2. Extract status/vendor counts",
            "3. Call generate_column_chart with statistics",
            "4. Return formatted statistics and chart"
        ]
    },
    "custom_orchestration": {
        "query": "Fetch device information and create a trend chart",
        "expected_flow": [
            "1. Call DU_Name_IP_Mapping to get device info",
            "2. Transform device data into time series",
            "3. Call generate_line_chart",
            "4. Return device info and trend chart"
        ]
    }
}


def print_usage_examples():
    """Print usage examples for orchestration."""
    print("\n" + "=" * 70)
    print("🎭 MCP Multi-Server Orchestration - Usage Examples")
    print("=" * 70)

    for name, example in ORCHESTRATION_EXAMPLES.items():
        print(f"\n📌 Example: {name}")
        print(f"Query: \"{example['query']}\"")
        print("\nExpected flow:")
        for step in example["expected_flow"]:
            print(f"  {step}")

    print("\n" + "=" * 70)


# ============================================================================
# STEP 5: Testing helper
# ============================================================================

async def test_orchestration(query: str, available_tools):
    """
    Test orchestration with a specific query.

    Args:
        query: Test query
        available_tools: List of available MCP tools
    """
    print(f"\n🧪 Testing orchestration for: {query}")
    print("-" * 70)

    # Check detection
    is_orchestration = is_orchestration_query(query)
    print(f"Is orchestration query: {is_orchestration}")

    if is_orchestration:
        # Execute
        result = await detect_and_orchestrate(
            query=query,
            available_tools=available_tools
        )

        if result:
            print(f"\n✅ Orchestration executed successfully")
            print(f"Tasks executed: {result['tasks_count']}")
            print(f"\nFormatted output:\n{result['formatted_output']}")
        else:
            print("❌ Orchestration failed")
    else:
        print("ℹ️  Query does not require orchestration")


if __name__ == "__main__":
    print_usage_examples()
