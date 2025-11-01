import os
import asyncio
from langchain_azure_ai.chat_models import AzureAIChatCompletionsModel


SELECTED_MODEL = "global-gpt-4.1"   # 换成你们内部部署的模型名称

file_path = "/mnt/openai_key/shared_token.txt"

with open(file_path, "r", encoding="utf-8") as f:
    JWT_TOKEN = f.read().strip()


print("API_Key:", JWT_TOKEN)
#JWT_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6IkpZaEFjVFBNWl9MWDZEQmxPV1E3SG4wTmVYRSIsImtpZCI6IkpZaEFjVFBNWl9MWDZEQmxPV1E3SG4wTmVYRSJ9.eyJhdWQiOiJlZWNjYTc0Ni05MTlkLTQ5OGMtOGI1YS0zYzBkZGQwMzZkYWYiLCJpc3MiOiJodHRwczovL3N0cy53aW5kb3dzLm5ldC85MmU4NGNlYi1mYmZkLTQ3YWItYmU1Mi0wODBjNmI4Nzk1M2YvIiwiaWF0IjoxNzU2OTUwOTAyLCJuYmYiOjE3NTY5NTA5MDIsImV4cCI6MTc1Njk1NDgwMiwiYWlvIjoiazJSZ1lPam12djdWT2I3TlJFcnl6bTVPcjlwdkFBPT0iLCJhcHBpZCI6ImVlY2NhNzQ2LTkxOWQtNDk4Yy04YjVhLTNjMGRkZDAzNmRhZiIsImFwcGlkYWNyIjoiMSIsImlkcCI6Imh0dHBzOi8vc3RzLndpbmRvd3MubmV0LzkyZTg0Y2ViLWZiZmQtNDdhYi1iZTUyLTA4MGM2Yjg3OTUzZi8iLCJvaWQiOiJmYWRjYTBlOS05MzdlLTQ2YTctODQ0Yi03MjdmN2I0ZTE5MmUiLCJyaCI6IjEuQVJFQTYwem9rdjM3cTBlLVVnZ01hNGVWUDBhbnpPNmRrWXhKaTFvOERkMERiYThSQUFBUkFBLiIsInN1YiI6ImZhZGNhMGU5LTkzN2UtNDZhNy04NDRiLTcyN2Y3YjRlMTkyZSIsInRpZCI6IjkyZTg0Y2ViLWZiZmQtNDdhYi1iZTUyLTA4MGM2Yjg3OTUzZiIsInV0aSI6IkdCQ0VScG5oRVV1em82aDVzVV8wQUEiLCJ2ZXIiOiIxLjAiLCJ4bXNfZnRkIjoiUW5FWEptSk1mLTZYcU0zNmFHbHVhZHNEc0FneURiYTFaa19tSXhqd0ZaQUJaWFZ5YjNCbGJtOXlkR2d0WkhOdGN3In0.R0dHkCxQ2hCU4tgwzb4NBTtxQndULZRm-MO77LxjTpumIfclvca1Ynt5AmUwbYxBPE9hWZnBg5CBIFN8EcLLACHf16XXnU-aXrjGMnd1y1utfiBAqJB1YWMNUF5k6SdcD8W5Ewh69XZ1CHg0ygZ6SmKhos-bMebPgcBCY_gKGc6TJesd-o_nktuGfQBbu1e1dDQT6DiFRi2q8UBeZ2Yyj51uAH80fyKQUFgfYFRFzT-pFedH7DyqRybCL62QmpjfVukBuUd2GN77fjT79MvHyFsI02YRXhm5mELB27VAigsVMRdiOLJxBWKTLlQwCQRjCF4qdpca1ahaSoU-4FWoxw"


#
CHAT_ENDPOINT = f"https://apigwy.ericsson.net/generativeai-model/v1/azure/text/deployments/{SELECTED_MODEL}/?api-version=2023-07-01-preview"
#const CHAT_ENDPOINT = `https://apigwy.ericsson.net/generativeai-model/v1/azure/text/deployments/${SELECTED_MODEL}/chat/completions?api-version=2023-07-01-preview`;

os.environ["AZURE_INFERENCE_ENDPOINT"] = CHAT_ENDPOINT
os.environ["AZURE_INFERENCE_CREDENTIAL"] = JWT_TOKEN

async def llm(jwt_token: str):
    llm = AzureAIChatCompletionsModel(
        endpoint=os.getenv("AZURE_INFERENCE_ENDPOINT"),
        credential=jwt_token,
        model=SELECTED_MODEL,
        temperature=0.2,
        max_tokens=500,
        max_retries=2
    )
    return llm


async def main():
    llm = await init_llm()

    messages = [
        {"role": "system", "content": "你是一个友好的助手。"},
        {"role": "user", "content": "请用中文介绍一下LangChain和AzureChatCompletions的区别。"}
    ]

    response = await llm.ainvoke(messages)
    print("=== Azure LLM Async Response ===")
    print(response)

# ==========================
# 运行异步函数
# ==========================
if __name__ == "__main__":
    asyncio.run(main())