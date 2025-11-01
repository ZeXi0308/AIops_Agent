from langchain.callbacks.base import BaseCallbackHandler
from langchain.callbacks.manager import CallbackManager
import os
import asyncio
from langchain_azure_ai.chat_models import AzureAIChatCompletionsModel
from langchain.schema import HumanMessage

SELECTED_MODEL = "global-gpt-4.1"   # 换成你们内部部署的模型名称

file_path = "/mnt/openai_key/shared_token.txt"
CHAT_ENDPOINT = f"https://apigwy.ericsson.net/generativeai-model/v1/azure/text/deployments/{SELECTED_MODEL}/?api-version=2023-07-01-preview"
os.environ["AZURE_INFERENCE_ENDPOINT"] = CHAT_ENDPOINT

with open(file_path, "r", encoding="utf-8") as f:
    jwt_token = f.read().strip()
    print(jwt_token)
# 自定义 handler

class MyTokenHandler(BaseCallbackHandler):
    def __init__(self):
        self.tokens = []

    def on_llm_new_token(self, token, **kwargs):
        print(token, end="", flush=True)  # 实时打印 token
        self.tokens.append(token)

async def create_llm(jwt_token: str):
    handler = MyTokenHandler()
    llm_instance = AzureAIChatCompletionsModel(
        endpoint=os.getenv("AZURE_INFERENCE_ENDPOINT"),
        credential=jwt_token,
        model=SELECTED_MODEL,
        temperature=0.2,
        max_tokens=500,
        max_retries=2,
        streaming=True,      # 开启流式
        callbacks=[handler]  # token 回调
    )
    return llm_instance, handler

async def main():
    jwt_token = "你的jwt_token"
    llm_instance, handler = await create_llm(jwt_token)

    prompt = "给我讲一个小笑话"

    # 使用 agenerate() 触发流式 token 回调
    await llm_instance.agenerate([[HumanMessage(content=prompt)]])

    # 获取完整文本
    full_text = "".join(handler.tokens)
    print("\n完整文本：", full_text)

    await llm_instance.aclose()

asyncio.run(main())