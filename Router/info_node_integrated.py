# 这是集成了 MCP Orchestration 的 info_node 完整代码
# 供你参考对比

async def info_node(state: State) -> State | Command:
    global global_log
    session_id = state.get("session_id", "unknown")
    start_time = time.time()
    session_logger.log(session_id, "INFO", "info_node", "start", "Start infor node")

    # 清空旧图片：每次进入 info_node 准备生成新的 AI 响应
    state["tool_images"] = []

    # ============================================================
    # 1. 初始化 LLM（提前到编排检测之前）
    # ============================================================
    print("Thinking in the info nodem,",state["Thinking"])
    JWT_TOKEN=get_MS_access_token()
    llm = await create_llm2(JWT_TOKEN)
    try:
        print("Health check of the LLM")
        response = await llm.ainvoke("ping")
        session_logger.log(session_id, "DEBUG", "info_node", "llm_health_check", "Using GPT")
    except Exception as e:
        llm = await create_llm()
        session_logger.log(session_id, "WARNING", "info_node", "llm_fallback", "Using ERICAI", error_info=str(e))

    # ============================================================
    # 2. 🎭 MCP Multi-Server Orchestration Detection
    # ============================================================
    human_msgs = [m for m in state["messages"] if isinstance(m, HumanMessage)]

    # 只在用户首次输入时检测（不在interrupt后检测）
    last_ai_message = next((m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None)
    is_first_input = last_ai_message is None or last_ai_message.content.strip() == ""

    if human_msgs and is_first_input:
        latest_query = human_msgs[-1].content

        # 检测是否需要多MCP编排
        if is_orchestration_query(latest_query):
            session_logger.log(session_id, "INFO", "info_node", "orchestration_detected", f"Query: {latest_query[:50]}...")

            try:
                # 执行编排
                orchestration_result = await detect_and_orchestrate(
                    query=latest_query,
                    available_tools=all_tools,
                    llm=llm
                )

                if orchestration_result and orchestration_result.get("orchestration_executed"):
                    session_logger.log(
                        session_id,
                        "INFO",
                        "info_node",
                        "orchestration_success",
                        f"Executed {orchestration_result['tasks_count']} tasks"
                    )

                    formatted_output = orchestration_result["formatted_output"]

                    # 更新 global_log
                    global_log["AI_Response"].append(formatted_output)
                    global_log["Thinking"].append(f"🎭 Multi-MCP Orchestration: {orchestration_result['tasks_count']} tasks executed")

                    # 构造响应消息
                    response_message = AIMessage(content=formatted_output)

                    # 返回结果（不修改 State 结构，只返回现有字段）
                    return {
                        "messages": state["messages"] + [response_message],
                        "subgraph": state.get("subgraph", "false"),
                        "Thinking": f"🎭 Orchestration executed {orchestration_result['tasks_count']} tasks",
                        "AI_Response": formatted_output,
                        "tool_images": state.get("tool_images", []),
                    }

            except Exception as e:
                session_logger.log(
                    session_id,
                    "WARNING",
                    "info_node",
                    "orchestration_failed",
                    "Falling back to normal LLM flow",
                    error_info=str(e)
                )
                # 如果编排失败，继续正常流程

    # ============================================================
    # 3. 正常的 LLM 流程（原有逻辑保持不变）
    # ============================================================
    llm_with_tools = llm.bind_tools(all_tools)

    # 添加 System Message（如果还没有）
    if not any(isinstance(m, SystemMessage) for m in state["messages"]):
        messages = [SystemMessage(content=template)] + state["messages"]
        state["messages"].insert(0, SystemMessage(content=template))
    else:
        messages = state["messages"]

    last_ai_message = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)

    # Message trimming
    print("Debug message befor trim",state["messages"])
    print("---------------------------------------------------------------------------")
    trimmer = MessageTrimmer()
    state["messages"] = trimmer.trim_messages_of_llm(state["messages"], "gpt-4")
    print("Debug message after trim",state["messages"])

    # LLM 推理
    if last_ai_message is None or last_ai_message.content.strip() == "":
        response = await llm_with_tools.ainvoke(state["messages"])
    else:
        value = interrupt({ "text_to_revise": "interrup in Info" })
        if not any(isinstance(m, SystemMessage) for m in state["messages"]):
            state["messages"].insert(0, SystemMessage(content=template))
        state["messages"].append(HumanMessage(content=str(value)))
        print("message before sent do LLM", state["messages"])
        response = await llm_with_tools.ainvoke(state["messages"])

    # 解析响应
    response.content = response.content if hasattr(response, "content") else str(response)
    reasoning_match = re.search(r"\[(?:Reasoning|Thinking)\]\s*(.*?)\s*(?=\[FinalAnswer\]|\Z)", response.content, re.S | re.I)
    reasoning = reasoning_match.group(1).strip() if reasoning_match else ""
    end_time = time.time()
    print(f"⏱ get AI () response: {end_time - start_time:.3f} 秒")
    final_answer_match = re.search(r'\[FinalAnswer\]\s*(.*?)(?=\n\[\w+\]|\Z)', response.content, re.S | re.I)
    final_answer = final_answer_match.group(1).strip() if final_answer_match and final_answer_match.group(1).strip() else response.content.strip()

    reasoning = "\n".join(line.strip() for line in reasoning.splitlines() if line.strip())
    final_answer = "\n".join(line.strip() for line in final_answer.splitlines() if line.strip())

    cleaned_answer, answer_images = sanitise_text_field(final_answer)

    # 直接赋值本轮图片，不累加
    tool_images = answer_images if answer_images else []

    final_answer_to_log = cleaned_answer or final_answer
    global_log["AI_Response"].append(final_answer_to_log)
    global_log["Thinking"].append(reasoning)

    contains_subgraph = "subgraph" in (response.content or "").lower()
    subgraph_flag = "true" if contains_subgraph else state.get("subgraph", "false")
    if "Trace_Agent" in final_answer_to_log:
        subgraph_flag = "Trace_Agent"

    print("Global log in infor node is,",global_log)
    if reasoning:
        state["Thinking"] = state.get("Thinking", "") + f"\n\n🤔Thinking:\n\n{reasoning}\n"
    state["AI_Response"]=final_answer_to_log
    print("Thinking in the info nodem,",state["Thinking"])

    # Session logging
    dialogue = session_logger.last_messages(state.get("messages", []), "HumanMessage", "AIMessage")
    session_logger.log(
        session_id,
        "INFO",
        "Info_node",
        "Finish",
        "Complete communication with LLM",
        data={"dialogue_sequence": dialogue}
    )

    # 返回更新后的 State
    return {
        "messages": state["messages"] + [response],
        "subgraph": subgraph_flag,
        "Thinking": state["Thinking"],
        "AI_Response": state["AI_Response"],
        "tool_images": tool_images,
    }
