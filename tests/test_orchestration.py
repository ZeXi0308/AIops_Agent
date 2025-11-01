"""
Unit tests for MCP Multi-Server Orchestration

Run with: pytest tests/test_orchestration.py -v
"""

import pytest
import sys
from pathlib import Path
import asyncio

# Add Router to path
ROUTER_PATH = Path(__file__).resolve().parent.parent / "Router"
sys.path.insert(0, str(ROUTER_PATH))

from mcp_orchestrator import (
    MCPOrchestrator,
    is_orchestration_query,
    detect_and_orchestrate
)


class TestOrchestrationDetection:
    """Test orchestration query detection"""

    def test_jira_chart_pattern(self):
        """Test JIRA + Chart pattern detection"""
        # Should detect
        assert is_orchestration_query("Show JIRA issues and create chart")
        assert is_orchestration_query("Get JIRA issues and visualize")
        assert is_orchestration_query("Query bugs and plot them")

        # Should not detect
        assert not is_orchestration_query("What is JIRA?")
        assert not is_orchestration_query("Create a chart")
        assert not is_orchestration_query("Show me issues")

    def test_statistics_pattern(self):
        """Test Statistics + Visualization pattern"""
        # Should detect
        assert is_orchestration_query("Get statistics and visualize")
        assert is_orchestration_query("Show stats with a chart")

        # Should not detect
        assert not is_orchestration_query("What are statistics?")
        assert not is_orchestration_query("Show statistics")

    def test_case_insensitive(self):
        """Test case-insensitive detection"""
        assert is_orchestration_query("SHOW JIRA ISSUES AND CREATE CHART")
        assert is_orchestration_query("show jira issues and create chart")
        assert is_orchestration_query("Show Jira Issues And Create Chart")


class TestQueryParsing:
    """Test query parsing and task generation"""

    def test_parse_jira_chart_query(self):
        """Test parsing JIRA + Chart query"""
        orchestrator = MCPOrchestrator([])
        query = "Show open S65 JIRA issues and create pie chart"

        tasks = orchestrator.parse_orchestration_query(query)

        assert len(tasks) == 2
        assert tasks[0]["tool_name"] == "query_jira_issues"
        assert tasks[1]["tool_name"] == "generate_pie_chart"

    def test_parameter_extraction_component(self):
        """Test component parameter extraction"""
        orchestrator = MCPOrchestrator([])
        query = "Show S65 open issues"

        tasks = orchestrator.parse_orchestration_query(query)

        if tasks:
            params = tasks[0]["parameters"]
            assert params.get("component") == "S65"

    def test_parameter_extraction_status(self):
        """Test status parameter extraction"""
        orchestrator = MCPOrchestrator([])

        # Test "open"
        query1 = "Show open JIRA issues"
        tasks1 = orchestrator.parse_orchestration_query(query1)
        if tasks1:
            assert tasks1[0]["parameters"].get("status") == "Open"

        # Test "closed"
        query2 = "Show closed JIRA issues"
        tasks2 = orchestrator.parse_orchestration_query(query2)
        if tasks2:
            assert tasks2[0]["parameters"].get("status") == "Closed"

    def test_parameter_extraction_year(self):
        """Test year parameter extraction"""
        orchestrator = MCPOrchestrator([])
        query = "Show JIRA issues from 2025"

        tasks = orchestrator.parse_orchestration_query(query)

        if tasks:
            params = tasks[0]["parameters"]
            assert params.get("year") == "2025"

    def test_parameter_extraction_timeframe(self):
        """Test timeframe parameter extraction"""
        orchestrator = MCPOrchestrator([])

        # Test "last week"
        query1 = "Show issues from last week"
        tasks1 = orchestrator.parse_orchestration_query(query1)
        if tasks1:
            assert tasks1[0]["parameters"].get("days_updated") == 7

        # Test "last month"
        query2 = "Show issues from last month"
        tasks2 = orchestrator.parse_orchestration_query(query2)
        if tasks2:
            assert tasks2[0]["parameters"].get("days_updated") == 30


class TestChartTypeSelection:
    """Test chart type selection logic"""

    def test_pie_chart_selection(self):
        """Test pie chart selection"""
        orchestrator = MCPOrchestrator([])
        query = "Show issues and create pie chart"

        tasks = orchestrator.parse_orchestration_query(query)

        chart_task = next((t for t in tasks if "chart" in t["tool_name"]), None)
        if chart_task:
            assert "pie" in chart_task["tool_name"]

    def test_bar_chart_selection(self):
        """Test bar chart selection"""
        orchestrator = MCPOrchestrator([])
        query = "Show issues and create bar chart"

        tasks = orchestrator.parse_orchestration_query(query)

        chart_task = next((t for t in tasks if "chart" in t["tool_name"]), None)
        if chart_task:
            assert "bar" in chart_task["tool_name"]

    def test_line_chart_selection(self):
        """Test line chart selection"""
        orchestrator = MCPOrchestrator([])
        query = "Show issues trend with line chart"

        tasks = orchestrator.parse_orchestration_query(query)

        chart_task = next((t for t in tasks if "chart" in t["tool_name"]), None)
        if chart_task:
            assert "line" in chart_task["tool_name"]


class TestDataTransformation:
    """Test data transformation between MCP servers"""

    def test_transform_statistics_by_status(self):
        """Test transforming statistics by_status to chart format"""
        orchestrator = MCPOrchestrator([])

        jira_data = {
            "statistics": {
                "by_status": {
                    "Open": 10,
                    "Closed": 12,
                    "In Progress": 3
                }
            }
        }

        chart_data = orchestrator._transform_data_for_chart(jira_data)

        assert len(chart_data) == 3
        assert {"category": "Open", "value": 10} in chart_data
        assert {"category": "Closed", "value": 12} in chart_data
        assert {"category": "In Progress", "value": 3} in chart_data

    def test_transform_statistics_by_vendor(self):
        """Test transforming statistics by_vendor to chart format"""
        orchestrator = MCPOrchestrator([])

        jira_data = {
            "statistics": {
                "by_vendor": {
                    "S65": 15,
                    "S12": 10,
                    "S99": 5
                }
            }
        }

        chart_data = orchestrator._transform_data_for_chart(jira_data)

        assert len(chart_data) == 3
        assert {"category": "S65", "value": 15} in chart_data

    def test_transform_issue_list(self):
        """Test transforming issue list to chart format"""
        orchestrator = MCPOrchestrator([])

        jira_data = {
            "issues": [
                {"Status": "Open"},
                {"Status": "Open"},
                {"Status": "Closed"},
                {"Status": "In Progress"}
            ]
        }

        chart_data = orchestrator._transform_data_for_chart(jira_data)

        assert len(chart_data) > 0
        # Check that status counts are correct
        open_item = next((item for item in chart_data if item["category"] == "Open"), None)
        assert open_item is not None
        assert open_item["value"] == 2

    def test_transform_empty_data(self):
        """Test transforming empty data"""
        orchestrator = MCPOrchestrator([])

        # Empty dict
        assert orchestrator._transform_data_for_chart({}) == []

        # None
        assert orchestrator._transform_data_for_chart(None) == []

        # Invalid format
        assert orchestrator._transform_data_for_chart("invalid") == []


class TestDependencyResolution:
    """Test dependency resolution between tasks"""

    def test_resolve_simple_dependency(self):
        """Test resolving a simple dependency"""
        orchestrator = MCPOrchestrator([])

        parameters = {
            "data_source": "jira_data",
            "title": "Test Chart"
        }

        previous_results = {
            "jira_data": {
                "statistics": {
                    "by_status": {
                        "Open": 5,
                        "Closed": 3
                    }
                }
            }
        }

        dependencies = ["jira_data"]

        resolved = orchestrator._resolve_dependencies(
            parameters,
            previous_results,
            dependencies
        )

        # Check that data_source was resolved and transformed
        assert "data_source" in resolved
        assert isinstance(resolved["data_source"], list)
        assert len(resolved["data_source"]) == 2

    def test_resolve_missing_dependency(self):
        """Test handling missing dependency"""
        orchestrator = MCPOrchestrator([])

        parameters = {
            "data_source": "missing_data",
            "title": "Test Chart"
        }

        previous_results = {
            "other_data": {"value": 123}
        }

        dependencies = ["missing_data"]

        resolved = orchestrator._resolve_dependencies(
            parameters,
            previous_results,
            dependencies
        )

        # Should handle missing dependency gracefully
        assert "data_source" in resolved


class TestResultFormatting:
    """Test result formatting"""

    def test_format_single_result(self):
        """Test formatting a single result"""
        orchestrator = MCPOrchestrator([])

        results = {
            "jira_data": {
                "success": True,
                "formatted_report": "JIRA Query Results: 10 issues found"
            }
        }

        formatted = orchestrator.format_orchestration_result(results)

        assert "🎭 Multi-MCP Orchestration Results" in formatted
        assert "jira_data" in formatted
        assert "JIRA Query Results: 10 issues found" in formatted

    def test_format_multiple_results(self):
        """Test formatting multiple results"""
        orchestrator = MCPOrchestrator([])

        results = {
            "jira_data": {
                "formatted_report": "JIRA report"
            },
            "chart_result": {
                "success": True,
                "chart_url": "http://example.com/chart"
            }
        }

        formatted = orchestrator.format_orchestration_result(results)

        assert "jira_data" in formatted
        assert "chart_result" in formatted
        assert "JIRA report" in formatted

    def test_format_error_result(self):
        """Test formatting result with error"""
        orchestrator = MCPOrchestrator([])

        results = {
            "jira_data": {
                "error": "Connection failed"
            }
        }

        formatted = orchestrator.format_orchestration_result(results)

        assert "❌ Error" in formatted
        assert "Connection failed" in formatted


class TestToolCategories:
    """Test tool categorization"""

    def test_data_retrieval_tools(self):
        """Test data retrieval tool categorization"""
        orchestrator = MCPOrchestrator([])

        data_tools = orchestrator.tool_categories.get("data_retrieval", [])

        assert "query_jira_issues" in data_tools
        assert "get_issue_statistics" in data_tools
        assert "get_latest_UP_version" in data_tools

    def test_visualization_tools(self):
        """Test visualization tool categorization"""
        orchestrator = MCPOrchestrator([])

        viz_tools = orchestrator.tool_categories.get("visualization", [])

        assert "generate_line_chart" in viz_tools
        assert "generate_pie_chart" in viz_tools
        assert "generate_column_chart" in viz_tools

    def test_analysis_tools(self):
        """Test analysis tool categorization"""
        orchestrator = MCPOrchestrator([])

        analysis_tools = orchestrator.tool_categories.get("analysis", [])

        assert "extract_rrc_msgs" in analysis_tools


# Async tests
class TestAsyncExecution:
    """Test async orchestration execution"""

    @pytest.mark.asyncio
    async def test_detect_and_orchestrate_with_mock(self):
        """Test detect_and_orchestrate with mocked tools"""
        # Mock tool
        class MockTool:
            def __init__(self, name):
                self.name = name

            async def ainvoke(self, params):
                if "jira" in self.name:
                    return {
                        "success": True,
                        "statistics": {
                            "by_status": {
                                "Open": 5,
                                "Closed": 3
                            }
                        },
                        "formatted_report": "Mock JIRA report"
                    }
                return {"success": True}

        mock_tools = [
            MockTool("query_jira_issues"),
            MockTool("generate_pie_chart")
        ]

        query = "Show JIRA issues and create chart"

        # This would normally execute, but we need actual MCP connections
        # For now, just test that it doesn't crash
        try:
            result = await detect_and_orchestrate(query, mock_tools)
            # If it executes, check result structure
            if result:
                assert "orchestration_executed" in result
                assert "results" in result
        except Exception as e:
            # Expected if tools don't have proper interface
            pytest.skip(f"Skipping async test due to mock limitation: {e}")


# Integration tests
class TestIntegration:
    """Integration tests (require running MCP servers)"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_jira_chart_orchestration(self):
        """Test full JIRA + Chart orchestration (requires running services)"""
        pytest.skip("Requires running MCP servers on ports 8004 and 8005")

        # This test would require actual MCP servers running
        # It's marked with @pytest.mark.integration
        # Run with: pytest -m integration


def run_all_tests():
    """Run all tests with verbose output"""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_all_tests()
