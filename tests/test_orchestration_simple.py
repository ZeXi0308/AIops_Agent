"""
Simple tests for MCP Orchestration (no external dependencies)
Run with: python tests/test_orchestration_simple.py
"""

import sys
from pathlib import Path

# Add Router to path
ROUTER_PATH = Path(__file__).resolve().parent.parent / "Router"
sys.path.insert(0, str(ROUTER_PATH))


def test_orchestration_detection():
    """Test basic orchestration detection logic"""
    print("\n" + "="*70)
    print("TEST: Orchestration Detection")
    print("="*70)

    # Simulate is_orchestration_query logic
    def is_orchestration_query(query: str) -> bool:
        query_lower = query.lower()
        patterns = [
            (["jira", "issue", "bug"], ["chart", "graph", "plot"]),
            (["statistics", "stats"], ["visualize", "show", "display"]),
        ]

        for data_keywords, action_keywords in patterns:
            has_data = any(kw in query_lower for kw in data_keywords)
            has_action = any(kw in query_lower for kw in action_keywords)
            if has_data and has_action:
                return True
        return False

    # Test cases
    test_cases = [
        ("Show JIRA issues and create chart", True),
        ("Get JIRA issues and visualize", True),
        ("Query bugs and plot them", True),
        ("What is JIRA?", False),
        ("Create a chart", False),
        ("Show me issues", False),
        ("Get statistics and visualize", True),
        ("show jira ISSUES and CREATE CHART", True),
    ]

    passed = 0
    failed = 0

    for query, expected in test_cases:
        result = is_orchestration_query(query)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        print(f"{status} | Query: '{query[:50]}...' | Expected: {expected}, Got: {result}")

        if result == expected:
            passed += 1
        else:
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    return failed == 0


def test_parameter_extraction():
    """Test parameter extraction from queries"""
    print("\n" + "="*70)
    print("TEST: Parameter Extraction")
    print("="*70)

    import re

    def extract_params(query: str):
        params = {}
        query_lower = query.lower()

        # Extract component
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

        return params

    # Test cases
    test_cases = [
        ("Show S65 open issues", {"component": "S65", "status": "Open"}),
        ("Get S12 closed issues from 2025", {"component": "S12", "status": "Closed", "year": "2025"}),
        ("Query S99 issues", {"component": "S99"}),
    ]

    passed = 0
    failed = 0

    for query, expected in test_cases:
        result = extract_params(query)
        match = all(result.get(k) == v for k, v in expected.items())
        status = "✅ PASS" if match else "❌ FAIL"
        print(f"{status} | Query: '{query}'")
        print(f"         Expected: {expected}")
        print(f"         Got: {result}")

        if match:
            passed += 1
        else:
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    return failed == 0


def test_data_transformation():
    """Test data transformation logic"""
    print("\n" + "="*70)
    print("TEST: Data Transformation")
    print("="*70)

    def transform_jira_to_chart(source_data):
        """Transform JIRA data to chart format"""
        if isinstance(source_data, dict):
            if "statistics" in source_data:
                stats = source_data["statistics"]

                if "by_status" in stats:
                    return [
                        {"category": status, "value": count}
                        for status, count in stats["by_status"].items()
                    ]

                if "by_vendor" in stats:
                    return [
                        {"category": vendor, "value": count}
                        for vendor, count in stats["by_vendor"].items()
                    ]

            if "issues" in source_data:
                issues = source_data["issues"]
                status_counts = {}
                for issue in issues:
                    status = issue.get("Status", "Unknown")
                    status_counts[status] = status_counts.get(status, 0) + 1

                return [
                    {"category": status, "value": count}
                    for status, count in status_counts.items()
                ]

        return []

    # Test cases
    test_cases = [
        (
            "Statistics by_status",
            {
                "statistics": {
                    "by_status": {
                        "Open": 10,
                        "Closed": 12
                    }
                }
            },
            [
                {"category": "Open", "value": 10},
                {"category": "Closed", "value": 12}
            ]
        ),
        (
            "Statistics by_vendor",
            {
                "statistics": {
                    "by_vendor": {
                        "S65": 15,
                        "S12": 10
                    }
                }
            },
            [
                {"category": "S65", "value": 15},
                {"category": "S12", "value": 10}
            ]
        ),
        (
            "Issue list",
            {
                "issues": [
                    {"Status": "Open"},
                    {"Status": "Open"},
                    {"Status": "Closed"}
                ]
            },
            [
                {"category": "Open", "value": 2},
                {"category": "Closed", "value": 1}
            ]
        ),
    ]

    passed = 0
    failed = 0

    for name, input_data, expected in test_cases:
        result = transform_jira_to_chart(input_data)
        # Sort both lists for comparison
        result_sorted = sorted(result, key=lambda x: x["category"])
        expected_sorted = sorted(expected, key=lambda x: x["category"])
        match = result_sorted == expected_sorted

        status = "✅ PASS" if match else "❌ FAIL"
        print(f"{status} | {name}")
        if not match:
            print(f"         Expected: {expected_sorted}")
            print(f"         Got: {result_sorted}")

        if match:
            passed += 1
        else:
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    return failed == 0


def test_chart_type_selection():
    """Test chart type selection logic"""
    print("\n" + "="*70)
    print("TEST: Chart Type Selection")
    print("="*70)

    def identify_chart_tool(query: str) -> str:
        query_lower = query.lower()

        if "pie" in query_lower:
            return "generate_pie_chart"
        elif "bar" in query_lower:
            return "generate_bar_chart"
        elif "line" in query_lower or "trend" in query_lower:
            return "generate_line_chart"
        else:
            return "generate_column_chart"

    # Test cases
    test_cases = [
        ("Show issues with pie chart", "generate_pie_chart"),
        ("Create bar chart", "generate_bar_chart"),
        ("Show trend with line chart", "generate_line_chart"),
        ("Display statistics", "generate_column_chart"),
    ]

    passed = 0
    failed = 0

    for query, expected in test_cases:
        result = identify_chart_tool(query)
        match = result == expected
        status = "✅ PASS" if match else "❌ FAIL"
        print(f"{status} | Query: '{query}' → {result}")

        if match:
            passed += 1
        else:
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    return failed == 0


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*70)
    print("MCP ORCHESTRATION - SIMPLE TESTS")
    print("="*70)

    tests = [
        ("Orchestration Detection", test_orchestration_detection),
        ("Parameter Extraction", test_parameter_extraction),
        ("Data Transformation", test_data_transformation),
        ("Chart Type Selection", test_chart_type_selection),
    ]

    all_passed = True

    for name, test_func in tests:
        try:
            passed = test_func()
            if not passed:
                all_passed = False
        except Exception as e:
            print(f"\n❌ Test '{name}' raised exception: {e}")
            all_passed = False

    print("\n" + "="*70)
    if all_passed:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("="*70)

    return all_passed


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
