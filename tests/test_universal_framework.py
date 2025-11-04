"""
Comprehensive Tests for Universal MCP Orchestration Framework
通用MCP编排框架的综合测试

Tests coverage:
1. Metadata loading
2. Rules loading
3. Rule matching
4. Parameter extraction
5. Data transformation
6. End-to-end orchestration

Run with: python tests/test_universal_framework.py
"""

import sys
from pathlib import Path
import asyncio

# Add Router to path
ROUTER_PATH = Path(__file__).resolve().parent.parent / "Router"
sys.path.insert(0, str(ROUTER_PATH))

from transformer_registry import TransformerRegistry, TransformationError
from universal_orchestrator import UniversalOrchestrator, is_orchestration_query
import yaml


# ============================================================================
# Mock Tools for Testing
# ============================================================================

class MockTool:
    """Mock MCP tool for testing"""

    def __init__(self, name: str):
        self.name = name

    async def ainvoke(self, params: dict):
        """Simulate tool execution"""
        print(f"  📞 Mock tool '{self.name}' called with params: {params}")

        if "jira" in self.name.lower():
            # Mock JIRA response
            return {
                "success": True,
                "statistics": {
                    "by_status": {
                        "Open": 10,
                        "Closed": 12,
                        "In Progress": 3
                    },
                    "by_vendor": {
                        "S65": 15,
                        "S12": 10
                    }
                },
                "issues": [
                    {"Key": "BUG-1", "Status": "Open", "Component": "S65"},
                    {"Key": "BUG-2", "Status": "Open", "Component": "S65"},
                    {"Key": "BUG-3", "Status": "Closed", "Component": "S65"},
                ],
                "formatted_report": f"Found {params.get('component', 'all')} issues"
            }

        elif "statistics" in self.name.lower():
            # Mock statistics response
            return {
                "success": True,
                "statistics": {
                    "by_status": {"Open": 8, "Closed": 15},
                    "by_vendor": {"Vendor A": 10, "Vendor B": 13}
                },
                "formatted_report": "Statistics summary"
            }

        elif "chart" in self.name.lower():
            # Mock chart response
            chart_type = "pie" if "pie" in self.name.lower() else "bar"
            return {
                "success": True,
                "chart_url": f"http://example.com/{chart_type}_chart.png",
                "message": f"{chart_type.capitalize()} chart generated successfully"
            }

        elif "device" in self.name.lower() or "du" in self.name.lower():
            # Mock device response
            return {
                "success": True,
                "mappings": [
                    {"device_name": "DU-1", "ip_address": "192.168.1.1", "status": "active"},
                    {"device_name": "DU-2", "ip_address": "192.168.1.2", "status": "inactive"},
                ]
            }

        return {"success": True, "message": "Mock tool executed"}


# ============================================================================
# Test 1: TransformerRegistry Tests
# ============================================================================

def test_transformer_registry():
    """Test TransformerRegistry functionality"""
    print("\n" + "=" * 70)
    print("TEST 1: TransformerRegistry")
    print("=" * 70)

    # Load metadata
    metadata_path = ROUTER_PATH / "mcp_tools_metadata.yaml"
    with open(metadata_path, 'r') as f:
        metadata = yaml.safe_load(f)

    # Create registry
    registry = TransformerRegistry()
    registry.load_from_metadata(metadata)

    print(f"✅ Loaded {len(registry.list_transformations())} transformations")

    # Test 1.1: dict_to_category_value_pairs
    print("\n📋 Test 1.1: dict_to_category_value_pairs")
    jira_data = {
        "statistics": {
            "by_status": {
                "Open": 10,
                "Closed": 5
            }
        }
    }

    result = registry.transform(
        source_data=jira_data,
        from_type="jira_issues",
        to_type="chart_data",
        strategy="by_status"
    )

    expected = [
        {"category": "Open", "value": 10},
        {"category": "Closed", "value": 5}
    ]

    result_sorted = sorted(result, key=lambda x: x["category"])
    expected_sorted = sorted(expected, key=lambda x: x["category"])

    assert result_sorted == expected_sorted, f"Expected {expected_sorted}, got {result_sorted}"
    print(f"✅ PASS: Transformation successful")
    print(f"   Result: {result}")

    # Test 1.2: count_by_field
    print("\n📋 Test 1.2: count_by_field")
    issue_list_data = {
        "issues": [
            {"Status": "Open"},
            {"Status": "Open"},
            {"Status": "Closed"}
        ]
    }

    result = registry.transform(
        source_data=issue_list_data,
        from_type="jira_issues",
        to_type="chart_data",
        strategy="issue_list"
    )

    # Sort for comparison
    result_sorted = sorted(result, key=lambda x: x["category"])
    expected = sorted([
        {"category": "Open", "value": 2},
        {"category": "Closed", "value": 1}
    ], key=lambda x: x["category"])

    assert result_sorted == expected, f"Expected {expected}, got {result_sorted}"
    print(f"✅ PASS: count_by_field successful")
    print(f"   Result: {result}")

    print("\n✅ All TransformerRegistry tests passed!")
    return True


# ============================================================================
# Test 2: Rule Matching Tests
# ============================================================================

def test_rule_matching():
    """Test orchestration rule matching"""
    print("\n" + "=" * 70)
    print("TEST 2: Rule Matching")
    print("=" * 70)

    # Create mock tools
    tools = [
        MockTool("query_jira_issues"),
        MockTool("get_issue_statistics"),
        MockTool("generate_pie_chart"),
        MockTool("generate_bar_chart"),
    ]

    # Create orchestrator
    orchestrator = UniversalOrchestrator(tools)

    # Load metadata and rules
    base_path = ROUTER_PATH
    orchestrator.load_metadata(str(base_path / "mcp_tools_metadata.yaml"))
    orchestrator.load_rules(str(base_path / "orchestration_rules.yaml"))

    print(f"✅ Loaded {len(orchestrator.rules)} rules")

    # Test cases
    test_cases = [
        ("Show S65 JIRA issues and create pie chart", "jira_issues_pie_chart", True),
        ("Get JIRA issues for S12 and create bar chart", "jira_issues_bar_chart", True),
        ("Show statistics and visualize with chart", "jira_statistics_chart", True),
        ("What is JIRA?", None, False),
        ("Create a chart", None, False),
        ("Show me issues", None, False),
    ]

    passed = 0
    failed = 0

    for query, expected_rule_id, should_match in test_cases:
        rule = orchestrator.match_rule(query)

        if should_match:
            if rule and rule.get("rule_id") == expected_rule_id:
                print(f"✅ PASS: '{query[:50]}...' → {rule['rule_id']}")
                passed += 1
            else:
                print(f"❌ FAIL: '{query[:50]}...' → Expected {expected_rule_id}, got {rule.get('rule_id') if rule else None}")
                failed += 1
        else:
            if rule is None:
                print(f"✅ PASS: '{query[:50]}...' → No match (expected)")
                passed += 1
            else:
                print(f"❌ FAIL: '{query[:50]}...' → Matched {rule['rule_id']} (should not match)")
                failed += 1

    print(f"\nResults: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    return failed == 0


# ============================================================================
# Test 3: Parameter Extraction Tests
# ============================================================================

def test_parameter_extraction():
    """Test parameter extraction from queries"""
    print("\n" + "=" * 70)
    print("TEST 3: Parameter Extraction")
    print("=" * 70)

    tools = [MockTool("query_jira_issues")]
    orchestrator = UniversalOrchestrator(tools)

    base_path = ROUTER_PATH
    orchestrator.load_metadata(str(base_path / "mcp_tools_metadata.yaml"))
    orchestrator.load_rules(str(base_path / "orchestration_rules.yaml"))

    # Test cases
    test_cases = [
        {
            "query": "Show S65 open issues from 2025",
            "param_config": {
                "source": "query",
                "extractor": "regex",
                "pattern": "S\\d+",
                "transform": "uppercase"
            },
            "expected": "S65"
        },
        {
            "query": "Get closed issues for S12",
            "param_config": {
                "source": "query",
                "extractor": "keyword_match",
                "keywords": [
                    {["open", "opened"]: "Open"},
                    {["closed", "resolved"]: "Closed"}
                ]
            },
            "expected": "Closed"
        },
        {
            "query": "Show issues from 2025",
            "param_config": {
                "source": "query",
                "extractor": "regex",
                "pattern": "20\\d{2}"
            },
            "expected": "2025"
        },
    ]

    passed = 0
    failed = 0

    for test_case in test_cases:
        query = test_case["query"]
        param_config = test_case["param_config"]
        expected = test_case["expected"]

        result = orchestrator.extract_parameter(param_config, query)

        if result == expected:
            print(f"✅ PASS: '{query}' → {result}")
            passed += 1
        else:
            print(f"❌ FAIL: '{query}' → Expected {expected}, got {result}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    return failed == 0


# ============================================================================
# Test 4: End-to-End Orchestration Tests
# ============================================================================

async def test_end_to_end_orchestration():
    """Test complete orchestration workflow"""
    print("\n" + "=" * 70)
    print("TEST 4: End-to-End Orchestration")
    print("=" * 70)

    # Create mock tools
    tools = [
        MockTool("query_jira_issues"),
        MockTool("get_issue_statistics"),
        MockTool("generate_pie_chart"),
        MockTool("generate_bar_chart"),
        MockTool("generate_line_chart"),
        MockTool("generate_column_chart"),
    ]

    # Create orchestrator
    orchestrator = UniversalOrchestrator(tools)

    # Load configurations
    base_path = ROUTER_PATH
    orchestrator.load_metadata(str(base_path / "mcp_tools_metadata.yaml"))
    orchestrator.load_rules(str(base_path / "orchestration_rules.yaml"))

    # Test scenarios
    test_scenarios = [
        {
            "name": "JIRA + Pie Chart",
            "query": "Show S65 open JIRA issues from 2025 and create a pie chart",
            "expected_tasks": 2,
            "expected_rule": "JIRA Issues + Pie Chart"
        },
        {
            "name": "JIRA + Bar Chart",
            "query": "Get S12 JIRA issues and create bar chart",
            "expected_tasks": 2,
            "expected_rule": "JIRA Issues + Bar Chart"
        },
        {
            "name": "Statistics + Visualization",
            "query": "Show JIRA statistics and visualize",
            "expected_tasks": 2,
            "expected_rule": "JIRA Statistics + Chart"
        },
    ]

    passed = 0
    failed = 0

    for scenario in test_scenarios:
        print(f"\n📋 Scenario: {scenario['name']}")
        print(f"   Query: {scenario['query']}")

        try:
            result = await orchestrator.orchestrate(scenario['query'])

            if result:
                tasks_count = result.get("tasks_count")
                rule_matched = result.get("rule_matched")

                print(f"   ✅ Rule: {rule_matched}")
                print(f"   ✅ Tasks: {tasks_count}")
                print(f"   ✅ Output preview: {result['formatted_output'][:100]}...")

                if tasks_count == scenario['expected_tasks']:
                    print(f"   ✅ PASS: Tasks count correct ({tasks_count})")
                    passed += 1
                else:
                    print(f"   ❌ FAIL: Expected {scenario['expected_tasks']} tasks, got {tasks_count}")
                    failed += 1
            else:
                print(f"   ❌ FAIL: No orchestration result")
                failed += 1

        except Exception as e:
            print(f"   ❌ FAIL: Exception: {e}")
            failed += 1

    print(f"\n\nResults: {passed} passed, {failed} failed out of {len(test_scenarios)} scenarios")
    return failed == 0


# ============================================================================
# Test 5: is_orchestration_query Function Tests
# ============================================================================

def test_is_orchestration_query_function():
    """Test the convenience function is_orchestration_query"""
    print("\n" + "=" * 70)
    print("TEST 5: is_orchestration_query Function")
    print("=" * 70)

    # Test without orchestrator (lightweight check)
    test_cases = [
        ("Show JIRA issues and create chart", True),
        ("Get statistics and visualize", True),
        ("Query bugs and plot", True),
        ("What is JIRA?", False),
        ("Hello world", False),
    ]

    passed = 0
    failed = 0

    for query, expected in test_cases:
        result = is_orchestration_query(query)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        print(f"{status} | '{query}' → {result} (expected: {expected})")

        if result == expected:
            passed += 1
        else:
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    return failed == 0


# ============================================================================
# Main Test Runner
# ============================================================================

def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("🎯 UNIVERSAL MCP ORCHESTRATION FRAMEWORK - COMPREHENSIVE TESTS")
    print("=" * 70)

    results = []

    # Test 1: TransformerRegistry
    try:
        results.append(("TransformerRegistry", test_transformer_registry()))
    except Exception as e:
        print(f"\n❌ TransformerRegistry tests failed: {e}")
        results.append(("TransformerRegistry", False))

    # Test 2: Rule Matching
    try:
        results.append(("Rule Matching", test_rule_matching()))
    except Exception as e:
        print(f"\n❌ Rule Matching tests failed: {e}")
        results.append(("Rule Matching", False))

    # Test 3: Parameter Extraction
    try:
        results.append(("Parameter Extraction", test_parameter_extraction()))
    except Exception as e:
        print(f"\n❌ Parameter Extraction tests failed: {e}")
        results.append(("Parameter Extraction", False))

    # Test 4: End-to-End Orchestration (async)
    try:
        result = asyncio.run(test_end_to_end_orchestration())
        results.append(("End-to-End Orchestration", result))
    except Exception as e:
        print(f"\n❌ End-to-End Orchestration tests failed: {e}")
        results.append(("End-to-End Orchestration", False))

    # Test 5: is_orchestration_query Function
    try:
        results.append(("is_orchestration_query", test_is_orchestration_query_function()))
    except Exception as e:
        print(f"\n❌ is_orchestration_query tests failed: {e}")
        results.append(("is_orchestration_query", False))

    # Summary
    print("\n" + "=" * 70)
    print("📊 TEST SUMMARY")
    print("=" * 70)

    passed_count = sum(1 for _, result in results if result)
    failed_count = len(results) - passed_count

    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status} | {name}")

    print(f"\nTotal: {passed_count}/{len(results)} test suites passed")

    if failed_count == 0:
        print("\n🎉 ALL TESTS PASSED! Universal framework is working correctly.")
    else:
        print(f"\n⚠️  {failed_count} test suite(s) failed.")

    print("=" * 70)

    return failed_count == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
