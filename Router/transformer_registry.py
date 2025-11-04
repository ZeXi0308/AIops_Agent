"""
Transformer Registry for MCP Universal Orchestration
MCP通用编排的转换器注册表

Provides a pluggable system for data transformations between MCP tools.
提供MCP工具之间数据转换的可插拔系统。

Usage:
    registry = TransformerRegistry()
    registry.load_from_metadata(metadata)

    # Transform data
    chart_data = registry.transform(
        source_data=jira_result,
        from_type="jira_issues",
        to_type="chart_data",
        strategy="by_status"
    )
"""

from typing import Any, Dict, List, Callable, Optional
from collections import Counter
import logging

logger = logging.getLogger(__name__)


class TransformationError(Exception):
    """Exception raised when data transformation fails"""
    pass


class TransformerRegistry:
    """
    Registry for data transformers with pluggable transformation functions.
    可插拔转换函数的数据转换器注册表。
    """

    def __init__(self):
        """Initialize the transformer registry"""
        self._transformers: Dict[str, Dict[str, Any]] = {}
        self._logic_functions: Dict[str, Callable] = {}

        # Register built-in transform logic functions
        self._register_builtin_logic()

    def _register_builtin_logic(self):
        """Register built-in transformation logic functions"""

        # dict_to_category_value_pairs
        def dict_to_category_value_pairs(data: Dict[str, Any]) -> List[Dict[str, Any]]:
            """
            Convert dict {key: value} to [{category: key, value: value}]

            Example:
                {"Open": 10, "Closed": 5} -> [{"category": "Open", "value": 10}, ...]
            """
            if not isinstance(data, dict):
                return []

            return [
                {"category": str(k), "value": v}
                for k, v in data.items()
            ]

        # count_by_field
        def count_by_field(items: List[Dict], field: str) -> List[Dict[str, Any]]:
            """
            Count occurrences of field values in a list of items

            Example:
                items = [{"Status": "Open"}, {"Status": "Open"}, {"Status": "Closed"}]
                field = "Status"
                -> [{"category": "Open", "value": 2}, {"category": "Closed", "value": 1}]
            """
            if not isinstance(items, list):
                return []

            # Extract field values
            field_values = []
            for item in items:
                if isinstance(item, dict) and field in item:
                    field_values.append(str(item[field]))

            # Count occurrences
            counts = Counter(field_values)

            return [
                {"category": category, "value": count}
                for category, count in counts.items()
            ]

        # extract_metric_values
        def extract_metric_values(
            items: List[Dict],
            metric_field: str,
            value_key: str = "value"
        ) -> List[Dict[str, Any]]:
            """
            Extract metric values from nested objects

            Example:
                items = [
                    {"du_name": "DU1", "metrics": {"value": 100}},
                    {"du_name": "DU2", "metrics": {"value": 200}}
                ]
                -> [{"category": "DU1", "value": 100}, {"category": "DU2", "value": 200}]
            """
            if not isinstance(items, list):
                return []

            result = []
            for item in items:
                if not isinstance(item, dict):
                    continue

                if metric_field in item:
                    metrics = item[metric_field]
                    if isinstance(metrics, dict) and value_key in metrics:
                        result.append({
                            "category": str(item.get("du_name", item.get("name", "Unknown"))),
                            "value": metrics[value_key]
                        })

            return result

        # Register all built-in functions
        self._logic_functions["dict_to_category_value_pairs"] = dict_to_category_value_pairs
        self._logic_functions["count_by_field"] = count_by_field
        self._logic_functions["extract_metric_values"] = extract_metric_values

    def load_from_metadata(self, metadata: Dict[str, Any]):
        """
        Load transformation definitions from metadata
        从元数据加载转换定义

        Args:
            metadata: Tool metadata dict containing 'transformations' key
        """
        if "transformations" not in metadata:
            logger.warning("No transformations found in metadata")
            return

        transformations = metadata["transformations"]

        for trans_name, trans_config in transformations.items():
            from_type = trans_config.get("from_type")
            to_type = trans_config.get("to_type")

            if not from_type or not to_type:
                logger.warning(f"Skipping transformation {trans_name}: missing from_type or to_type")
                continue

            # Create transformation key
            key = f"{from_type}->{to_type}"

            # Store transformation config
            self._transformers[key] = {
                "name": trans_name,
                "from_type": from_type,
                "to_type": to_type,
                "description": trans_config.get("description", ""),
                "strategies": trans_config.get("strategies", {})
            }

            logger.info(f"Registered transformation: {key} with {len(trans_config.get('strategies', {}))} strategies")

    def register_custom_logic(self, logic_name: str, logic_function: Callable):
        """
        Register a custom transformation logic function
        注册自定义转换逻辑函数

        Args:
            logic_name: Name of the logic function
            logic_function: Callable that performs the transformation
        """
        self._logic_functions[logic_name] = logic_function
        logger.info(f"Registered custom logic function: {logic_name}")

    def get_transformation(self, from_type: str, to_type: str) -> Optional[Dict[str, Any]]:
        """
        Get transformation configuration
        获取转换配置

        Args:
            from_type: Source data type
            to_type: Target data type

        Returns:
            Transformation config dict or None
        """
        key = f"{from_type}->{to_type}"
        return self._transformers.get(key)

    def list_transformations(self) -> List[Dict[str, str]]:
        """
        List all registered transformations
        列出所有已注册的转换

        Returns:
            List of transformation info dicts
        """
        return [
            {
                "key": key,
                "from_type": config["from_type"],
                "to_type": config["to_type"],
                "description": config["description"],
                "strategies": list(config["strategies"].keys())
            }
            for key, config in self._transformers.items()
        ]

    def transform(
        self,
        source_data: Any,
        from_type: str,
        to_type: str,
        strategy: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Transform data from one type to another
        将数据从一种类型转换为另一种类型

        Args:
            source_data: Source data to transform
            from_type: Source data type (e.g., "jira_issues")
            to_type: Target data type (e.g., "chart_data")
            strategy: Transformation strategy to use (e.g., "by_status")
            **kwargs: Additional parameters for transformation logic

        Returns:
            Transformed data

        Raises:
            TransformationError: If transformation fails
        """
        # Get transformation config
        trans_config = self.get_transformation(from_type, to_type)

        if not trans_config:
            raise TransformationError(
                f"No transformation found for {from_type} -> {to_type}"
            )

        strategies = trans_config["strategies"]

        # Auto-select strategy if not provided
        if not strategy:
            if len(strategies) == 1:
                strategy = list(strategies.keys())[0]
            else:
                # Try to infer strategy from source data
                strategy = self._infer_strategy(source_data, strategies)

        if strategy not in strategies:
            available = ", ".join(strategies.keys())
            raise TransformationError(
                f"Strategy '{strategy}' not found. Available: {available}"
            )

        strategy_config = strategies[strategy]

        # Extract source path
        source_path = strategy_config.get("source_path")
        if source_path:
            data_to_transform = self._extract_by_path(source_data, source_path)
        else:
            data_to_transform = source_data

        # Get transformation logic
        transform_logic = strategy_config.get("transform_logic")
        if not transform_logic:
            raise TransformationError(
                f"No transform_logic specified for strategy '{strategy}'"
            )

        # Get logic function
        logic_func = self._logic_functions.get(transform_logic)
        if not logic_func:
            raise TransformationError(
                f"Transform logic '{transform_logic}' not registered"
            )

        # Execute transformation
        try:
            # Pass additional params from strategy config
            params = {}
            if "field" in strategy_config:
                params["field"] = strategy_config["field"]
            if "metric_field" in strategy_config:
                params["metric_field"] = strategy_config["metric_field"]

            # Merge with kwargs
            params.update(kwargs)

            # Call logic function
            if params:
                result = logic_func(data_to_transform, **params)
            else:
                result = logic_func(data_to_transform)

            logger.info(
                f"Successfully transformed {from_type} -> {to_type} "
                f"using strategy '{strategy}'"
            )

            return result

        except Exception as e:
            raise TransformationError(
                f"Transformation failed: {str(e)}"
            ) from e

    def _extract_by_path(self, data: Any, path: str) -> Any:
        """
        Extract data from nested structure using dot-notation path
        使用点表示法路径从嵌套结构中提取数据

        Args:
            data: Source data
            path: Dot-notation path (e.g., "statistics.by_status")

        Returns:
            Extracted data
        """
        parts = path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                logger.warning(f"Path '{path}' not found in data")
                return None

        return current

    def _infer_strategy(
        self,
        source_data: Dict[str, Any],
        strategies: Dict[str, Any]
    ) -> Optional[str]:
        """
        Infer the best strategy based on source data structure
        根据源数据结构推断最佳策略

        Args:
            source_data: Source data
            strategies: Available strategies

        Returns:
            Strategy name or None
        """
        # Try to match source_path in data
        for strategy_name, strategy_config in strategies.items():
            source_path = strategy_config.get("source_path")
            if source_path:
                data_at_path = self._extract_by_path(source_data, source_path)
                if data_at_path is not None:
                    logger.info(f"Auto-selected strategy: {strategy_name}")
                    return strategy_name

        # Default to first strategy
        first_strategy = list(strategies.keys())[0] if strategies else None
        if first_strategy:
            logger.info(f"Defaulting to first strategy: {first_strategy}")
        return first_strategy


# Singleton instance for global use
_global_registry: Optional[TransformerRegistry] = None


def get_transformer_registry() -> TransformerRegistry:
    """
    Get the global transformer registry instance
    获取全局转换器注册表实例

    Returns:
        TransformerRegistry singleton
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = TransformerRegistry()
    return _global_registry


# Example usage
if __name__ == "__main__":
    import yaml

    # Load metadata
    with open("mcp_tools_metadata.yaml", "r") as f:
        metadata = yaml.safe_load(f)

    # Create registry and load transformations
    registry = TransformerRegistry()
    registry.load_from_metadata(metadata)

    # Example: Transform JIRA data to chart format
    jira_data = {
        "success": True,
        "statistics": {
            "by_status": {
                "Open": 10,
                "Closed": 12,
                "In Progress": 3
            }
        }
    }

    chart_data = registry.transform(
        source_data=jira_data,
        from_type="jira_issues",
        to_type="chart_data",
        strategy="by_status"
    )

    print("Transformed data:")
    print(chart_data)
    # Output: [{"category": "Open", "value": 10}, {"category": "Closed", "value": 12}, ...]
