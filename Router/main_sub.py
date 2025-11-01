import json
from typing import Dict, Any
import subgraph

SESSION_ID = "123"  # 固定 session_id


def get_status(resp: dict):
    """从子图返回的 resp 里提取 status"""
    if "status" in resp:  
        return resp["status"]
    # 如果 resp 是 {'NodeName': {...}}
    if len(resp) == 1 and isinstance(next(iter(resp.values())), dict):
        inner = next(iter(resp.values()))
        return inner.get("status")
    return None

def cli_demo():
    """
    命令行演示：
    - 直接调用子图
    - 中断时显示 message，让用户输入
    - 输入传回子图，LangGraph 自动从断点恢复
    """
    print(f"[主图] 使用 session_id={SESSION_ID}")

    # 初始输入可以是空 dict
    user_input: Dict[str, Any] = {}
    #user_input = {"text": "张三"}
    resp = subgraph.run(session_id=SESSION_ID, input_data=user_input)

    while True:
        # 判断子图是否中断

        status = get_status(resp)
        if status == "done":
            print("主图 Done",resp)
            print("[主图] 子图完成，结果：")
            # 同样取 result
            result = resp.get("AI_Response")
            if result is None and len(resp) == 1:
                result = next(iter(resp.values())).get("AI_Response")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            break
        if "__interrupt__" in resp:
            # 取第一个中断信息
            interrupt_info = resp["__interrupt__"][0]
            ai_message = interrupt_info.value.get("AI_Response", "需要用户输入")
            user_text = input(f"[主图] 子图请求输入: {ai_message}\n> ")
            # 把用户输入传给子图，LangGraph 会自动从断点恢复
            resp = subgraph.run(session_id=SESSION_ID, input_data={"text": user_text})
            print("主图 res after resume",resp)
        elif resp.get("status") == "done":
            print("[主图] 子图完成，结果：")
            print(json.dumps(resp["result"], ensure_ascii=False, indent=2))
            break
        else:
            print("[主图] 错误或未知状态：", resp)
            break



if __name__ == "__main__":
    cli_demo()

