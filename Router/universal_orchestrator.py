"""
Universal MCP Orchestrator
通用MCP编排器

A metadata-driven, configurable orchestration framework for multi-MCP server workflows.
基于元数据、可配置的多MCP服务器工作流编排框架。

Key Features / 核心特性:
- Dynamic rule matching (no hardcoded logic) / 动态规则匹配（无硬编码逻辑）
- Metadata-driven tool definitions / 元数据驱动的工具定义
- Pluggable transformers / 可插拔转换器
- Configurable workflows / 可配置工作流
- Template-based output formatting / 基于模板的输出格式化

Usage:
    orchestrator = UniversalOrchestrator(available_tools)
    orchestrator.load_metadata("mcp_tools_metadata.yaml")
    orchestrator.load_rules("orchestration_rules.yaml")

    result = await orchestrator.orchestrate(query="Show S65 issues and create chart")
"""

from typing import Any, Dict, List, Optional, Callable
from langchain_core.tools import BaseTool
import yaml
import re
import logging
from pathlib import Path
from transformer_registry import TransformerRegistry, TransformationError

logger = logging.getLogger(__name__)


class OrchestrationError(Exception):
    """Exception raised during orchestration"""
    pass


class UniversalOrchestrator:
    """
    Universal orchestrator with metadata-driven configuration
    基于元数据配置的通用编排器
    """

    def __init__(self, available_tools: List[BaseTool]):
        """
        Initialize the universal orchestrator

        Args:
            available_tools: List of available MCP tools
        """
        self.available_tools = available_tools
        self.tool_map = {tool.name: tool for tool in available_tools}

        # Metadata and configuration
        self.tools_metadata: Dict[str, Any] = {}
        self.rules: List[Dict[str, Any]] = []
        self.extractors: Dict[str, Any] = {}
        self.transform_strategies: Dict[str, Any] = {}

        # Transformer registry
        self.transformer_registry = TransformerRegistry()

        logger.info(f"UniversalOrchestrator initialized with {len(available_tools)} tools")

    def load_metadata(self, metadata_path: str):
        """
        Load tool metadata from YAML file
        从YAML文件加载工具元数据

        Args:
            metadata_path: Path to mcp_tools_metadata.yaml
        """
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = yaml.safe_load(f)

            self.tools_metadata = metadata.get("tools", {})

            # Load transformations into transformer registry
            self.transformer_registry.load_from_metadata(metadata)

            logger.info(
                f"Loaded metadata for {len(self.tools_metadata)} tools, "
                f"{len(self.transformer_registry.list_transformations())} transformations"
            )

        except Exception as e:
            logger.error(f"Failed to load metadata: {e}")
            raise OrchestrationError(f"Metadata loading failed: {e}") from e

    def load_rules(self, rules_path: str):
        """
        Load orchestration rules from YAML file
        从YAML文件加载编排规则

        Args:
            rules_path: Path to orchestration_rules.yaml
        """
        try:
            with open(rules_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            rules_dict = config.get("rules", {})
            self.extractors = config.get("extractors", {})
            self.transform_strategies = config.get("transform_strategies", {})

            # Convert rules dict to sorted list (by priority)
            self.rules = []
            for rule_id, rule_config in rules_dict.items():
                rule_config["rule_id"] = rule_id
                self.rules.append(rule_config)

            # Sort by priority (higher first)
            self.rules.sort(key=lambda r: r.get("priority", 0), reverse=True)

            logger.info(f"Loaded {len(self.rules)} orchestration rules")

        except Exception as e:
            logger.error(f"Failed to load rules: {e}")
            raise OrchestrationError(f"Rules loading failed: {e}") from e

    def match_rule(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Match query to orchestration rule dynamically
        动态匹配查询到编排规则

        Args:
            query: User query

        Returns:
            Matched rule config or None
        """
        query_lower = query.lower()

        for rule in self.rules:
            trigger = rule.get("trigger", {})

            # Check keywords_all (all groups must match)
            keywords_all = trigger.get("keywords_all", [])
            if keywords_all:
                all_matched = True
                for group in keywords_all:
                    if isinstance(group, dict):
                        # Format: {group1: [keywords]}
                        group_keywords = list(group.values())[0]
                    else:
                        # Format: [keywords]
                        group_keywords = group

                    group_matched = any(kw in query_lower for kw in group_keywords)
                    if not group_matched:
                        all_matched = False
                        break

                if not all_matched:
                    continue

            # Check keywords_any (at least one must match)
            keywords_any = trigger.get("keywords_any", [])
            if keywords_any:
                any_matched = False
                for keyword_list in keywords_any:
                    if any(kw in query_lower for kw in keyword_list):
                        any_matched = True
                        break
                if not any_matched:
                    continue

            # Check keywords_none (none should match)
            keywords_none = trigger.get("keywords_none", [])
            if keywords_none:
                none_matched = True
                for keyword in keywords_none:
                    if keyword in query_lower:
                        none_matched = False
                        break
                if not none_matched:
                    continue

            # Check regex patterns
            patterns = trigger.get("patterns", [])
            if patterns:
                patterns_matched = all(
                    re.search(pattern, query, re.IGNORECASE)
                    for pattern in patterns
                )
                if not patterns_matched:
                    continue

            # All conditions met - rule matched
            logger.info(f"Matched rule: {rule.get('name')} (priority={rule.get('priority')})")
            return rule

        logger.info("No orchestration rule matched")
        return None

    def extract_parameter(
        self,
        param_config: Dict[str, Any],
        query: str,
        task_results: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Extract parameter value using configured extractor
        使用配置的提取器提取参数值

        Args:
            param_config: Parameter configuration from rule
            query: User query
            task_results: Results from previous tasks (for dependencies)

        Returns:
            Extracted parameter value
        """
        source = param_config.get("source")

        # Static value
        if source == "static":
            return param_config.get("value")

        # Extract from query
        if source == "query":
            extractor = param_config.get("extractor")

            if extractor == "regex":
                pattern = param_config.get("pattern")
                matches = re.findall(pattern, query, re.IGNORECASE)

                if not matches:
                    return param_config.get("default")

                # Get specific index if specified
                index = param_config.get("index", 0)
                if index >= len(matches):
                    return param_config.get("default")

                value = matches[index]

                # Apply transform
                transform = param_config.get("transform")
                if transform == "uppercase":
                    value = value.upper()
                elif transform == "lowercase":
                    value = value.lower()

                return value

            elif extractor == "keyword_match":
                keywords = param_config.get("keywords", [])
                query_lower = query.lower()

                for keyword_list_and_value in keywords:
                    for keyword_list, mapped_value in keyword_list_and_value.items():
                        if any(kw in query_lower for kw in keyword_list):
                            return mapped_value

                return param_config.get("default")

            elif extractor == "time_range":
                patterns = param_config.get("patterns", [])
                for pattern_dict in patterns:
                    for pattern_list, value in pattern_dict.items():
                        for pattern_str in pattern_list:
                            match = re.search(pattern_str, query, re.IGNORECASE)
                            if match:
                                if value == "extract_number":
                                    # Extract number from match
                                    num_match = re.search(r'\d+', match.group(0))
                                    if num_match:
                                        return int(num_match.group(0))
                                elif value == "extract_days":
                                    # Extract days from pattern
                                    num_match = re.search(r'(\d+)', match.group(0))
                                    if num_match:
                                        return int(num_match.group(1))
                                elif value == "extract_weeks":
                                    # Extract weeks and convert to days
                                    num_match = re.search(r'(\d+)', match.group(0))
                                    if num_match:
                                        return int(num_match.group(1)) * 7
                                else:
                                    return value

                return param_config.get("default")

        # Extract from task output
        if source == "task_output":
            if not task_results:
                return None

            task_id = param_config.get("task_id")
            task_output = task_results.get(task_id)

            if not task_output:
                return None

            # Apply transformation if needed
            transform_config = param_config.get("transform")
            if transform_config:
                from_type = transform_config.get("from_type")
                to_type = transform_config.get("to_type")
                strategy = transform_config.get("strategy")

                try:
                    transformed = self.transformer_registry.transform(
                        source_data=task_output,
                        from_type=from_type,
                        to_type=to_type,
                        strategy=strategy
                    )
                    return transformed
                except TransformationError as e:
                    logger.warning(f"Transformation failed: {e}")
                    return None

            return task_output

        # Multi-task aggregation
        if source == "multi_task":
            if not task_results:
                return None

            task_ids = param_config.get("task_ids", [])
            aggregation = param_config.get("aggregation")

            # Collect results from multiple tasks
            results = []
            for task_id in task_ids:
                if task_id in task_results:
                    results.append(task_results[task_id])

            if not results:
                return None

            # Apply aggregation logic
            if aggregation == "merge_by_status":
                # Merge statistics by status
                merged = {}
                for result in results:
                    if isinstance(result, dict) and "statistics" in result:
                        by_status = result["statistics"].get("by_status", {})
                        for status, count in by_status.items():
                            merged[status] = merged.get(status, 0) + count

                return [{"category": k, "value": v} for k, v in merged.items()]

            elif aggregation == "concat_lists":
                # Concatenate lists
                combined = []
                for result in results:
                    if isinstance(result, list):
                        combined.extend(result)
                return combined

        return param_config.get("default")

    async def execute_task(
        self,
        task_config: Dict[str, Any],
        query: str,
        task_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a single task
        执行单个任务

        Args:
            task_config: Task configuration
            query: Original user query
            task_results: Results from previous tasks

        Returns:
            Task execution result
        """
        task_id = task_config.get("task_id")
        tool_name = task_config.get("tool")

        logger.info(f"Executing task '{task_id}' with tool '{tool_name}'")

        # Get tool
        tool = self.tool_map.get(tool_name)
        if not tool:
            raise OrchestrationError(f"Tool '{tool_name}' not found")

        # Extract parameters
        params_config = task_config.get("parameters", {})
        params = {}

        for param_name, param_config in params_config.items():
            param_value = self.extract_parameter(param_config, query, task_results)

            # Check if required
            if param_config.get("required", False) and param_value is None:
                raise OrchestrationError(
                    f"Required parameter '{param_name}' not found for task '{task_id}'"
                )

            if param_value is not None:
                params[param_name] = param_value

        logger.debug(f"Task '{task_id}' parameters: {params}")

        # Execute tool
        try:
            result = await tool.ainvoke(params)
            logger.info(f"Task '{task_id}' completed successfully")
            return result
        except Exception as e:
            logger.error(f"Task '{task_id}' failed: {e}")
            raise OrchestrationError(f"Task '{task_id}' execution failed: {e}") from e

    async def orchestrate(
        self,
        query: str,
        llm: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Main orchestration method - match rule and execute tasks
        主编排方法 - 匹配规则并执行任务

        Args:
            query: User query
            llm: LLM instance (optional, for future extensions)

        Returns:
            Orchestration result dict with:
            - orchestration_executed: bool
            - rule_matched: str
            - tasks_count: int
            - task_results: Dict[task_id, result]
            - formatted_output: str
            - raw_results: Dict
        """
        # Match rule
        rule = self.match_rule(query)

        if not rule:
            logger.info("No rule matched - orchestration not needed")
            return None

        rule_id = rule.get("rule_id")
        rule_name = rule.get("name")

        logger.info(f"Starting orchestration with rule '{rule_name}' ({rule_id})")

        # Execute tasks
        tasks = rule.get("tasks", [])
        task_results = {}

        for task_config in tasks:
            task_id = task_config.get("task_id")

            # Check dependencies
            depends_on = task_config.get("depends_on", [])
            for dep_task_id in depends_on:
                if dep_task_id not in task_results:
                    raise OrchestrationError(
                        f"Task '{task_id}' depends on '{dep_task_id}' which hasn't been executed"
                    )

            # Execute task
            try:
                result = await self.execute_task(task_config, query, task_results)

                # Store result with output key
                output_key = task_config.get("output", {}).get("key", task_id)
                task_results[output_key] = result

            except Exception as e:
                logger.error(f"Task '{task_id}' failed: {e}")
                # Continue with partial results
                task_results[task_id] = {
                    "success": False,
                    "error": str(e)
                }

        # Format output
        output_format = rule.get("output_format", {})
        template = output_format.get("template", "")

        formatted_output = self.format_output(template, task_results)

        # Build result
        result = {
            "orchestration_executed": True,
            "rule_matched": rule_name,
            "rule_id": rule_id,
            "tasks_count": len(tasks),
            "task_results": task_results,
            "formatted_output": formatted_output,
            "raw_results": task_results
        }

        logger.info(
            f"Orchestration completed: {len(tasks)} tasks executed, "
            f"rule='{rule_name}'"
        )

        return result

    def format_output(
        self,
        template: str,
        task_results: Dict[str, Any]
    ) -> str:
        """
        Format output using template and task results
        使用模板和任务结果格式化输出

        Args:
            template: Output template string with placeholders
            task_results: Results from executed tasks

        Returns:
            Formatted output string
        """
        if not template:
            # Default formatting
            output_parts = []
            for key, result in task_results.items():
                if isinstance(result, dict):
                    if "formatted_report" in result:
                        output_parts.append(result["formatted_report"])
                    elif "message" in result:
                        output_parts.append(result["message"])
                    elif "chart_url" in result:
                        output_parts.append(f"Chart: {result['chart_url']}")
            return "\n\n".join(output_parts)

        # Simple template substitution
        output = template

        # Replace placeholders like {jira_data.formatted_report}
        for key, result in task_results.items():
            if isinstance(result, dict):
                for field, value in result.items():
                    placeholder = f"{{{key}.{field}}}"
                    if placeholder in output:
                        output = output.replace(placeholder, str(value))

            # Handle list length filter {data.items|length}
            placeholder_with_length = f"{{{key}.mappings|length}}"
            if placeholder_with_length in output:
                if isinstance(result, dict) and "mappings" in result:
                    length = len(result["mappings"])
                    output = output.replace(placeholder_with_length, str(length))

        return output


# Convenience functions for backward compatibility and easy integration
# 为了向后兼容和易于集成的便捷函数


def is_orchestration_query(
    query: str,
    orchestrator: Optional[UniversalOrchestrator] = None,
    rules_path: Optional[str] = None
) -> bool:
    """
    Check if query needs orchestration (backward compatible with old API)
    检查查询是否需要编排（与旧API向后兼容）

    Args:
        query: User query
        orchestrator: UniversalOrchestrator instance (optional)
        rules_path: Path to rules file (optional)

    Returns:
        True if orchestration needed, False otherwise
    """
    if not orchestrator:
        # Lightweight check without full orchestrator
        # For production, should use proper orchestrator instance
        query_lower = query.lower()

        # Basic patterns
        patterns = [
            (["jira", "issue", "bug"], ["chart", "graph", "plot", "visualize"]),
            (["statistics", "stats"], ["visualize", "chart"]),
            (["device", "du"], ["chart", "visualize"]),
            (["compare", "comparison"], ["jira", "component"]),
        ]

        for data_keywords, action_keywords in patterns:
            has_data = any(kw in query_lower for kw in data_keywords)
            has_action = any(kw in query_lower for kw in action_keywords)
            if has_data and has_action:
                return True

        return False

    # Use orchestrator to match rule
    rule = orchestrator.match_rule(query)
    return rule is not None


async def detect_and_orchestrate(
    query: str,
    available_tools: List[BaseTool],
    llm: Any,
    orchestrator: Optional[UniversalOrchestrator] = None
) -> Optional[Dict[str, Any]]:
    """
    One-stop orchestration function (backward compatible with old API)
    一站式编排函数（与旧API向后兼容）

    Args:
        query: User query
        available_tools: Available MCP tools
        llm: LLM instance
        orchestrator: Pre-configured orchestrator (optional)

    Returns:
        Orchestration result or None
    """
    # Create or use provided orchestrator
    if not orchestrator:
        base_path = Path(__file__).parent
        orchestrator = UniversalOrchestrator(available_tools)

        # Load metadata and rules
        metadata_path = base_path / "mcp_tools_metadata.yaml"
        rules_path = base_path / "orchestration_rules.yaml"

        if metadata_path.exists():
            orchestrator.load_metadata(str(metadata_path))
        else:
            logger.warning(f"Metadata file not found: {metadata_path}")
            return None

        if rules_path.exists():
            orchestrator.load_rules(str(rules_path))
        else:
            logger.warning(f"Rules file not found: {rules_path}")
            return None

    # Check if orchestration needed
    if not is_orchestration_query(query, orchestrator):
        return None

    # Execute orchestration
    try:
        result = await orchestrator.orchestrate(query, llm)
        return result
    except Exception as e:
        logger.error(f"Orchestration failed: {e}")
        return None


# Example usage
if __name__ == "__main__":
    import asyncio

    async def example():
        # Mock tools for testing
        class MockTool:
            def __init__(self, name):
                self.name = name

            async def ainvoke(self, params):
                if "jira" in self.name.lower():
                    return {
                        "success": True,
                        "statistics": {
                            "by_status": {"Open": 10, "Closed": 5}
                        },
                        "formatted_report": "Found 15 issues"
                    }
                elif "chart" in self.name.lower():
                    return {
                        "success": True,
                        "chart_url": "http://example.com/chart.png",
                        "message": "Chart generated"
                    }
                return {"success": True}

        tools = [
            MockTool("query_jira_issues"),
            MockTool("generate_pie_chart"),
        ]

        # Create orchestrator
        orchestrator = UniversalOrchestrator(tools)

        # Load configurations
        base_path = Path(__file__).parent
        orchestrator.load_metadata(str(base_path / "mcp_tools_metadata.yaml"))
        orchestrator.load_rules(str(base_path / "orchestration_rules.yaml"))

        # Test query
        query = "Show S65 open JIRA issues and create a pie chart"

        # Execute orchestration
        result = await orchestrator.orchestrate(query)

        if result:
            print("\n✅ Orchestration Result:")
            print(f"Rule: {result['rule_matched']}")
            print(f"Tasks: {result['tasks_count']}")
            print(f"\nFormatted Output:\n{result['formatted_output']}")
        else:
            print("\n❌ No orchestration rule matched")

    asyncio.run(example())
