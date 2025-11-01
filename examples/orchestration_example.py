"""
Complete example demonstrating MCP Multi-Server Orchestration

This example shows how to:
1. Query JIRA issues
2. Transform the data
3. Create charts from the results
All in a single orchestrated flow.
"""

import sys
import asyncio
from pathlib import Path

# Add Router to path
ROUTER_PATH = Path(__file__).resolve().parent.parent / "Router"
sys.path.insert(0, str(ROUTER_PATH))

from mcp_orchestrator import MCPOrchestrator, detect_and_orchestrate, is_orchestration_query


async def example_1_basic_orchestration():
    """
    Example 1: Basic JIRA + Chart orchestration
    Query: "Show me open S65 JIRA issues and create a pie chart"
    """
    print("\n" + "=" * 80)
    print("📊 Example 1: JIRA Issues + Pie Chart")
    print("=" * 80)

    query = "Show me open S65 JIRA issues from 2025 and create a pie chart"
    print(f"\n🔍 Query: {query}")

    # Simulate orchestration flow
    print("\n📋 Orchestration Plan:")
    print("  Step 1: Call JIRA tool (query_jira_issues)")
    print("    └─ Parameters: component=S65, status=Open, year=2025")
    print("  Step 2: Transform JIRA data to chart format")
    print("    └─ Extract status counts from issues")
    print("  Step 3: Call Chart tool (generate_pie_chart)")
    print("    └─ Parameters: data=[{category, value}], title='JIRA Issues'")

    # Expected result structure
    expected_result = {
        "orchestration_executed": True,
        "tasks_count": 2,
        "results": {
            "jira_data": {
                "success": True,
                "summary": {"total_issues": 15},
                "issues": [
                    {"No.": "IODTIT-123", "Status": "Open", "Feature": "5G NR"},
                    {"No.": "IODTIT-124", "Status": "Open", "Feature": "LTE"}
                ],
                "formatted_report": "JIRA Query Results: 15 issues found..."
            },
            "chart_result": {
                "success": True,
                "chart_url": "http://localhost:3000/chart/abc123",
                "chart_type": "pie"
            }
        }
    }

    print("\n✅ Expected Output:")
    print("  - JIRA formatted report with 15 issues")
    print("  - Pie chart showing issue distribution by status")
    print("  - Chart URL for embedding/viewing")


async def example_2_statistics_orchestration():
    """
    Example 2: Statistics + Visualization
    Query: "Get JIRA statistics and visualize with a bar chart"
    """
    print("\n" + "=" * 80)
    print("📈 Example 2: Statistics + Bar Chart")
    print("=" * 80)

    query = "Get JIRA statistics for S12 component and visualize with bar chart"
    print(f"\n🔍 Query: {query}")

    print("\n📋 Orchestration Plan:")
    print("  Step 1: Call JIRA statistics tool (get_issue_statistics)")
    print("    └─ Parameters: component=S12, days_updated=30")
    print("  Step 2: Transform statistics to chart format")
    print("    └─ Extract by_status or by_vendor counts")
    print("  Step 3: Call Chart tool (generate_bar_chart)")
    print("    └─ Parameters: data=[{category, value}], title='Statistics'")

    print("\n✅ Expected Output:")
    print("  - Statistics report with counts by status and vendor")
    print("  - Bar chart showing distribution")


async def example_3_custom_pattern():
    """
    Example 3: Custom orchestration pattern
    Demonstrates how to add new orchestration patterns
    """
    print("\n" + "=" * 80)
    print("🔧 Example 3: Custom Orchestration Pattern")
    print("=" * 80)

    print("\n📝 How to add a new orchestration pattern:")
    print("\n1. Identify the pattern in mcp_orchestrator.py:")
    print("   ```python")
    print("   # In parse_orchestration_query()")
    print("   if 'device' in query_lower and 'trend' in query_lower:")
    print("       # First task: Get device data")
    print("       tasks.append({")
    print("           'tool_name': 'DU_Name_IP_Mapping',")
    print("           'parameters': {},")
    print("           'output_key': 'device_data'")
    print("       })")
    print("       # Second task: Create trend chart")
    print("       tasks.append({")
    print("           'tool_name': 'generate_line_chart',")
    print("           'parameters': {'data_source': 'device_data'},")
    print("           'depends_on': ['device_data']")
    print("       })")
    print("   ```")

    print("\n2. Test the new pattern:")
    print("   Query: 'Show device information and create a trend chart'")

    print("\n3. The orchestrator will:")
    print("   - Detect the pattern")
    print("   - Execute tasks sequentially")
    print("   - Pass data between tasks")
    print("   - Return combined results")


async def example_4_data_transformation():
    """
    Example 4: Understanding data transformation between MCP servers
    """
    print("\n" + "=" * 80)
    print("🔄 Example 4: Data Transformation Flow")
    print("=" * 80)

    print("\n📊 JIRA Output Format:")
    jira_output = {
        "success": True,
        "statistics": {
            "total_issues": 25,
            "by_status": {
                "Open": 10,
                "Closed": 12,
                "In Progress": 3
            },
            "by_vendor": {
                "S65": 15,
                "S12": 10
            }
        }
    }
    print(f"  {jira_output}")

    print("\n🔄 Transformation to Chart Format:")
    chart_input = [
        {"category": "Open", "value": 10},
        {"category": "Closed", "value": 12},
        {"category": "In Progress", "value": 3}
    ]
    print(f"  {chart_input}")

    print("\n📈 Chart MCP receives transformed data and generates visualization")
    print("\nKey transformation function:")
    print("  _transform_data_for_chart() in mcp_orchestrator.py")
    print("  - Converts JIRA statistics to chart-compatible format")
    print("  - Handles different data structures (issues list, statistics, etc.)")
    print("  - Can be extended for custom transformations")


async def example_5_error_handling():
    """
    Example 5: Error handling in orchestration
    """
    print("\n" + "=" * 80)
    print("⚠️  Example 5: Error Handling")
    print("=" * 80)

    print("\n🔍 Scenario 1: First tool fails")
    print("  - JIRA query returns no results")
    print("  - Orchestrator checks for empty data")
    print("  - Skips chart generation or generates empty state message")

    print("\n🔍 Scenario 2: Second tool fails")
    print("  - JIRA data retrieved successfully")
    print("  - Chart generation fails (service down)")
    print("  - Orchestrator returns JIRA results with error note about chart")

    print("\n🔍 Scenario 3: Data transformation fails")
    print("  - JIRA returns unexpected format")
    print("  - Transformation catches exception")
    print("  - Orchestrator attempts fallback or reports error")

    print("\n💡 Error handling features:")
    print("  - Each task wrapped in try/except")
    print("  - 'critical' flag to control flow on failures")
    print("  - Partial results returned when possible")
    print("  - Clear error messages in results")


async def example_6_extending_orchestration():
    """
    Example 6: How to extend orchestration for new MCP servers
    """
    print("\n" + "=" * 80)
    print("🚀 Example 6: Extending Orchestration")
    print("=" * 80)

    print("\n📝 Steps to add a new MCP server to orchestration:")
    print("\n1. Register tool category in MCPOrchestrator.__init__():")
    print("   ```python")
    print("   self.tool_categories = {")
    print("       'data_retrieval': ['query_jira_issues', 'your_new_tool'],")
    print("       'processing': ['your_processing_tool'],")
    print("       'visualization': ['generate_pie_chart', ...]")
    print("   }")
    print("   ```")

    print("\n2. Add detection pattern in parse_orchestration_query():")
    print("   ```python")
    print("   if 'your_keyword' in query_lower:")
    print("       tasks.append({")
    print("           'tool_name': 'your_new_tool',")
    print("           'parameters': {...},")
    print("           'output_key': 'your_data'")
    print("       })")
    print("   ```")

    print("\n3. Add data transformation in _transform_data_for_chart():")
    print("   ```python")
    print("   if 'your_data_format' in source_data:")
    print("       return transform_to_chart_format(source_data)")
    print("   ```")

    print("\n4. Test the new orchestration pattern")
    print("\n5. Add to is_orchestration_query() for automatic detection")


def print_orchestration_architecture():
    """
    Print the orchestration architecture diagram
    """
    print("\n" + "=" * 80)
    print("🏗️  MCP Multi-Server Orchestration Architecture")
    print("=" * 80)

    print("""
┌─────────────────────────────────────────────────────────────────────┐
│                         User Query                                  │
│              "Show JIRA issues and create chart"                    │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Orchestration Detection                           │
│              (is_orchestration_query)                               │
│    • Checks for multi-step patterns                                │
│    • Identifies data + action combinations                          │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Query Parsing                                     │
│          (parse_orchestration_query)                                │
│    • Extracts parameters                                            │
│    • Identifies required tools                                      │
│    • Creates task sequence                                          │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Task Execution                                    │
│           (execute_orchestration)                                   │
│                                                                     │
│    ┌──────────────────────────────────────────────┐               │
│    │  Step 1: JIRA MCP Server (Port 8004)        │               │
│    │  Tool: query_jira_issues                    │               │
│    │  Output: JIRA issues data                   │               │
│    └────────────────┬─────────────────────────────┘               │
│                     │                                               │
│                     ▼                                               │
│    ┌──────────────────────────────────────────────┐               │
│    │  Data Transformation                         │               │
│    │  Function: _transform_data_for_chart        │               │
│    │  Output: Chart-compatible format            │               │
│    └────────────────┬─────────────────────────────┘               │
│                     │                                               │
│                     ▼                                               │
│    ┌──────────────────────────────────────────────┐               │
│    │  Step 2: Chart MCP Server (Port 8005)       │               │
│    │  Tool: generate_pie_chart                   │               │
│    │  Output: Chart URL/Image                    │               │
│    └──────────────────────────────────────────────┘               │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Result Formatting                                 │
│          (format_orchestration_result)                              │
│    • Combines all task results                                      │
│    • Formats for user display                                       │
│    • Includes JIRA report + Chart                                   │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     User Output                                     │
│    📊 JIRA Report: 15 issues found                                 │
│    📈 Chart: Pie chart showing status distribution                 │
└─────────────────────────────────────────────────────────────────────┘
""")


async def run_all_examples():
    """Run all examples in sequence"""
    print("\n" + "=" * 80)
    print("🎭 MCP Multi-Server Orchestration - Complete Examples")
    print("=" * 80)

    print_orchestration_architecture()

    await example_1_basic_orchestration()
    await asyncio.sleep(0.5)

    await example_2_statistics_orchestration()
    await asyncio.sleep(0.5)

    await example_3_custom_pattern()
    await asyncio.sleep(0.5)

    await example_4_data_transformation()
    await asyncio.sleep(0.5)

    await example_5_error_handling()
    await asyncio.sleep(0.5)

    await example_6_extending_orchestration()

    print("\n" + "=" * 80)
    print("✅ All examples completed!")
    print("=" * 80)
    print("\n📚 Next steps:")
    print("  1. Review the orchestration code in Router/mcp_orchestrator.py")
    print("  2. Check integration guide in Router/mcp_orchestration_integration.py")
    print("  3. Test with your own queries")
    print("  4. Extend with custom patterns for your use cases")
    print("\n")


if __name__ == "__main__":
    asyncio.run(run_all_examples())
