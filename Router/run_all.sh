#!/bin/bash
# 执行三个 Python 脚本并实时显示输出

echo "========== Running script1.py =========="
python3 router_collect2.py &

echo "========== Running script2.py =========="
python3 AD_graph.py &

echo "========== Running script3.py =========="
python3 moshell_agent.py &


wait
