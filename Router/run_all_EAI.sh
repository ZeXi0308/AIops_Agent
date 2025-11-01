#!/bin/bash
# 执行三个 Python 脚本并实时显示输出

echo "========== Running script1.py =========="
python3 router_collect2_EAI.py > /proc/1/fd/1 2>&1 &

echo "========== Running script2.py =========="
python3 AD_graph_EAI.py > /proc/1/fd/1 2>&1 &

echo "========== Running script3.py =========="
python3 moshell_agent_EAI.py > /proc/1/fd/1 2>&1 &


wait
