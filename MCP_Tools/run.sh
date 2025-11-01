#!/bin/bash
# --------------------------------------
# 并行运行多个 Python 脚本（后台执行）
# --------------------------------------

# 要运行的 Python 脚本列表（根据实际修改）
scripts=(
    "check_up_tool.py"
    "mcp_curl_tool.py"
    "mcp_deviceinfo_tool.py"
    "mcp_rrc_tool.py"
    "mcp_jira_tool_jinshuo.py"
)

# 循环启动每个脚本（后台运行）
for script in "${scripts[@]}"; do
    echo "启动脚本: $script"
    python3 "$script" >/dev/null 2>&1 & disown
done

echo "✅ 所有脚本已后台运行完成。"
echo "可使用 'ps aux | grep python' 或 'tail -f xxx.log' 查看运行情况。"
