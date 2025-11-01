"""
MCP Multi-Server Orchestration Module

This module provides a common function to support multiple MCP server orchestration.
It allows sequential execution of tools from different MCP servers, passing data between them.

Example use case:
- Query: "Show me JIRA issues and create a chart"
- Orchestration:
  1. Call JIRA MCP server to get issues
  2. Call Chart MCP server to create visualization with JIRA data
"""

import logging
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


class MCPOrchestrator:
    """
    Orchestrates multiple MCP server tool calls in sequence.
    Manages data flow between different MCP tools.
    """

    def __init__(self, available_tools: List[BaseTool]):
        """
        Initialize the orchestrator with available MCP tools.

        Args:
            available_tools: List of tools from all MCP servers
        """
        self.available_tools = available_tools
        self.tool_map = {tool.name: tool for tool in available_tools}

        # Define tool categories and their typical outputs
        self.tool_categories = {
            "data_retrieval": [
                "query_jira_issues",
                "get_issue_statistics",
                "get_latest_UP_version",
                "DU_Name_IP_Mapping"
            ],
            "visualization": [
                "generate_line_chart",
                "generate_pie_chart",
                "generate_column_chart",
                "generate_bar_chart"
            ],
            "analysis": [
                "extract_rrc_msgs"
            ]
        }

    def parse_orchestration_query(self, query: str) -> List[Dict[str, Any]]:
        """
        Parse a user query to identify required tool executions.

        Args:
            query: Natural language query from user

        Returns:
            List of task definitions with tool names and parameters
        """
        tasks = []
        query_lower = query.lower()

        # Pattern 1: JIRA/Issue + Chart
        if any(keyword in query_lower for keyword in ["jira", "issue", "bug", "ticket"]):
            # First task: Get JIRA data
            jira_task = {
                "tool_name": self._identify_jira_tool(query),
                "parameters": self._extract_jira_params(query),
                "output_key": "jira_data"
            }
            tasks.append(jira_task)

            # Check if visualization is needed
            if any(keyword in query_lower for keyword in ["chart", "graph", "visualize", "plot", "show"]):
                chart_task = {
                    "tool_name": self._identify_chart_tool(query),
                    "parameters": {
                        "data_source": "jira_data",  # Reference to previous task output
                        "title": "JIRA Issues Analysis"
                    },
                    "output_key": "chart_result",
                    "depends_on": ["jira_data"]
                }
                tasks.append(chart_task)

        # Pattern 2: Statistics + Chart
        elif "statistics" in query_lower or "stats" in query_lower:
            stats_task = {
                "tool_name": "get_issue_statistics",
                "parameters": self._extract_jira_params(query),
                "output_key": "stats_data"
            }
            tasks.append(stats_task)

            if any(keyword in query_lower for keyword in ["chart", "graph", "visualize"]):
                chart_task = {
                    "tool_name": "generate_pie_chart",  # Stats work well with pie charts
                    "parameters": {
                        "data_source": "stats_data",
                        "title": "Issue Statistics"
                    },
                    "output_key": "chart_result",
                    "depends_on": ["stats_data"]
                }
                tasks.append(chart_task)

        return tasks

    def _identify_jira_tool(self, query: str) -> str:
        """Determine which JIRA tool to use based on query."""
        if "statistics" in query.lower() or "stats" in query.lower():
            return "get_issue_statistics"
        return "query_jira_issues"

    def _identify_chart_tool(self, query: str) -> str:
        """Determine which chart type to use based on query."""
        query_lower = query.lower()

        if "pie" in query_lower:
            return "generate_pie_chart"
        elif "bar" in query_lower:
            return "generate_bar_chart"
        elif "line" in query_lower or "trend" in query_lower:
            return "generate_line_chart"
        else:
            return "generate_column_chart"  # Default

    def _extract_jira_params(self, query: str) -> Dict[str, Any]:
        """Extract JIRA query parameters from natural language."""
        params = {}
        query_lower = query.lower()

        # Extract component (e.g., S65, S12)
        component_match = re.search(r's\d+', query_lower)
        if component_match:
            params['component'] = component_match.group().upper()

        # Extract status
        if "open" in query_lower:
            params['status'] = "Open"
        elif "closed" in query_lower:
            params['status'] = "Closed"

        # Extract year
        year_match = re.search(r'\b(20\d{2})\b', query)
        if year_match:
            params['year'] = year_match.group(1)

        # Extract time range
        if "last week" in query_lower:
            params['days_updated'] = 7
        elif "last month" in query_lower:
            params['days_updated'] = 30

        return params

    async def execute_orchestration(
        self,
        tasks: List[Dict[str, Any]],
        llm=None
    ) -> Dict[str, Any]:
        """
        Execute a sequence of MCP tool calls with data flow management.

        Args:
            tasks: List of task definitions
            llm: Optional LLM instance for intelligent data transformation

        Returns:
            Dictionary containing all task results
        """
        results = {}

        for i, task in enumerate(tasks):
            tool_name = task["tool_name"]
            parameters = task["parameters"].copy()
            output_key = task.get("output_key", f"result_{i}")
            depends_on = task.get("depends_on", [])

            logger.info(f"Executing task {i+1}/{len(tasks)}: {tool_name}")

            # Resolve dependencies
            if depends_on:
                parameters = self._resolve_dependencies(parameters, results, depends_on)

            # Execute the tool
            try:
                tool = self.tool_map.get(tool_name)
                if not tool:
                    logger.error(f"Tool {tool_name} not found")
                    results[output_key] = {"error": f"Tool {tool_name} not available"}
                    continue

                # Invoke the tool
                result = await tool.ainvoke(parameters)
                results[output_key] = result

                logger.info(f"Task {i+1} completed successfully")

            except Exception as e:
                logger.error(f"Task {i+1} failed: {str(e)}")
                results[output_key] = {"error": str(e)}

                # Decide whether to continue or stop
                if task.get("critical", True):
                    break

        return results

    def _resolve_dependencies(
        self,
        parameters: Dict[str, Any],
        previous_results: Dict[str, Any],
        dependencies: List[str]
    ) -> Dict[str, Any]:
        """
        Resolve parameter dependencies from previous task results.

        Args:
            parameters: Current task parameters
            previous_results: Results from previous tasks
            dependencies: List of dependency keys

        Returns:
            Updated parameters with resolved dependencies
        """
        resolved = parameters.copy()

        for key, value in parameters.items():
            # Check if this parameter references a previous result
            if isinstance(value, str) and value in dependencies:
                # Get the data from previous result
                if value in previous_results:
                    resolved[key] = self._transform_data_for_chart(
                        previous_results[value]
                    )

        return resolved

    def _transform_data_for_chart(self, source_data: Any) -> List[Dict[str, Any]]:
        """
        Transform JIRA/data results into chart-compatible format.

        Args:
            source_data: Data from JIRA or other data source

        Returns:
            Chart-compatible data format
        """
        # Handle JIRA statistics output
        if isinstance(source_data, dict):
            if "statistics" in source_data:
                stats = source_data["statistics"]

                # Transform by_status into chart data
                if "by_status" in stats:
                    return [
                        {"category": status, "value": count}
                        for status, count in stats["by_status"].items()
                    ]

                # Transform by_vendor into chart data
                if "by_vendor" in stats:
                    return [
                        {"category": vendor, "value": count}
                        for vendor, count in stats["by_vendor"].items()
                    ]

            # Handle issue list
            if "issues" in source_data:
                issues = source_data["issues"]
                # Count by status
                status_counts = {}
                for issue in issues:
                    status = issue.get("Status", "Unknown")
                    status_counts[status] = status_counts.get(status, 0) + 1

                return [
                    {"category": status, "value": count}
                    for status, count in status_counts.items()
                ]

        return []

    def format_orchestration_result(self, results: Dict[str, Any]) -> str:
        """
        Format orchestration results for user display.

        Args:
            results: All task results

        Returns:
            Formatted string output
        """
        output_lines = []
        output_lines.append("🎭 Multi-MCP Orchestration Results")
        output_lines.append("=" * 60)
        output_lines.append("")

        for key, result in results.items():
            output_lines.append(f"📊 {key}:")
            output_lines.append("-" * 40)

            if isinstance(result, dict):
                if "error" in result:
                    output_lines.append(f"❌ Error: {result['error']}")
                elif "formatted_report" in result:
                    output_lines.append(result["formatted_report"])
                else:
                    output_lines.append(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                output_lines.append(str(result))

            output_lines.append("")

        return "\n".join(output_lines)


# Orchestration utility functions for integration with main.py

async def detect_and_orchestrate(
    query: str,
    available_tools: List[BaseTool],
    llm=None
) -> Optional[Dict[str, Any]]:
    """
    Detect if a query requires orchestration and execute if needed.

    Args:
        query: User query
        available_tools: Available MCP tools
        llm: Optional LLM instance

    Returns:
        Orchestration results if applicable, None otherwise
    """
    orchestrator = MCPOrchestrator(available_tools)

    # Check if query needs orchestration
    query_lower = query.lower()
    needs_orchestration = (
        # Pattern: Data + Visualization
        any(data_keyword in query_lower for data_keyword in ["jira", "issue", "statistics"]) and
        any(viz_keyword in query_lower for viz_keyword in ["chart", "graph", "visualize", "plot"])
    )

    if not needs_orchestration:
        return None

    logger.info(f"Orchestration detected for query: {query}")

    # Parse and execute
    tasks = orchestrator.parse_orchestration_query(query)

    if not tasks:
        return None

    results = await orchestrator.execute_orchestration(tasks, llm)

    return {
        "orchestration_executed": True,
        "tasks_count": len(tasks),
        "results": results,
        "formatted_output": orchestrator.format_orchestration_result(results)
    }


def is_orchestration_query(query: str) -> bool:
    """
    Quick check if a query might need orchestration.

    Args:
        query: User query

    Returns:
        True if orchestration might be needed
    """
    query_lower = query.lower()

    # Check for multi-step patterns
    patterns = [
        # Data retrieval + visualization
        (["jira", "issue", "bug"], ["chart", "graph", "plot"]),
        (["statistics", "stats"], ["visualize", "show", "display"]),
        # Future patterns can be added here
    ]

    for data_keywords, action_keywords in patterns:
        has_data = any(kw in query_lower for kw in data_keywords)
        has_action = any(kw in query_lower for kw in action_keywords)
        if has_data and has_action:
            return True

    return False
