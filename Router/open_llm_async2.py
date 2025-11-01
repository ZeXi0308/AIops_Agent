from langgraph.prebuilt import create_react_agent
import asyncio
import httpx
from langchain_openai import ChatOpenAI
import httpx
import subprocess
import os
from langchain_openai import AzureChatOpenAI

JWT_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6IkpZaEFjVFBNWl9MWDZEQmxPV1E3SG4wTmVYRSIsImtpZCI6IkpZaEFjVFBNWl9MWDZEQmxPV1E3SG4wTmVYRSJ9.eyJhdWQiOiJlZWNjYTc0Ni05MTlkLTQ5OGMtOGI1YS0zYzBkZGQwMzZkYWYiLCJpc3MiOiJodHRwczovL3N0cy53aW5kb3dzLm5ldC85MmU4NGNlYi1mYmZkLTQ3YWItYmU1Mi0wODBjNmI4Nzk1M2YvIiwiaWF0IjoxNzU2NDUwNTA1LCJuYmYiOjE3NTY0NTA1MDUsImV4cCI6MTc1NjQ1NDQwNSwiYWlvIjoiazJSZ1lGZzA2eTduMjdaTFVvRzNJeHJlM0t4UkFnQT0iLCJhcHBpZCI6ImVlY2NhNzQ2LTkxOWQtNDk4Yy04YjVhLTNjMGRkZDAzNmRhZiIsImFwcGlkYWNyIjoiMSIsImlkcCI6Imh0dHBzOi8vc3RzLndpbmRvd3MubmV0LzkyZTg0Y2ViLWZiZmQtNDdhYi1iZTUyLTA4MGM2Yjg3OTUzZi8iLCJvaWQiOiJmYWRjYTBlOS05MzdlLTQ2YTctODQ0Yi03MjdmN2I0ZTE5MmUiLCJyaCI6IjEuQVJFQTYwem9rdjM3cTBlLVVnZ01hNGVWUDBhbnpPNmRrWXhKaTFvOERkMERiYThSQUFBUkFBLiIsInN1YiI6ImZhZGNhMGU5LTkzN2UtNDZhNy04NDRiLTcyN2Y3YjRlMTkyZSIsInRpZCI6IjkyZTg0Y2ViLWZiZmQtNDdhYi1iZTUyLTA4MGM2Yjg3OTUzZiIsInV0aSI6IjU4eERkMW91WjBLTzg4Sno0YnBKQUEiLCJ2ZXIiOiIxLjAiLCJ4bXNfZnRkIjoiOVFvMHZzcnVJN2ZfbXA5TmdoSmN0c0ZPUmdSTkpiS0p5NVd4Q1prbFZ4a0JaWFZ5YjNCbGQyVnpkQzFrYzIxeiJ9.gw77iN8CFcX9lqh2gOESS2uIsfPOYmz1bGPgx2bdkTcN45m03T95U24JpZ0cjl2Ux34VZgImqCclW0m1Wd2z8t-TRPvSQ0C1B4szBy6ZUSgyUcK-18UpPC5qqVqflZb-gFpZb8dilckg33WdQmK808jQoxucFGzWCun26l-iTPV0ShCRzJVBIKYs0tSZ4R6pqFQG7sV6dymJ08LKgyD79fbErCDFMLudcyHD1xovAQ8LFgLqIyutDUw-aaaqcvYY5nOlbWWCCzIsgotOqNk5ynIikpe0pjOfQmQFIBFXkiUhlO_ndKITZIvcU-llYqOWklrOcHkjWioQxU_7f2nwIQ"
# 可切换模型
SELECTED_MODEL = "global-gpt-4.1"
SELECTED_MODE = "Lse-gpt-5"
# endpoint 拼接
CHAT_ENDPOINT  = f"https://apigwy.ericsson.net/generativeai-model/v1/azure/text/deployments/{SELECTED_MODEL}/chat/completions?api-version=2023-07-01-preview"



llm = AzureChatOpenAI(
    deployment_name="Lse-gpt-5",
    api_version="2023-07-01-preview",
    azure_endpoint="https://apigwy.net/generativeai-model/v1/azure/text",
    api_key="dummy-key",
    default_headers={
        "Authorization": f"Bearer {JWT_TOKEN}",
    }
)

# --- hack: 强行去掉 /openai ---
# 1. 拿到真实 client 对象
client = llm.client

# 2. 修改 base_url （去掉 /openai）
if "openai" in str(client._client_params.base_url):
    client._client_params.base_url = str(client._client_params.base_url).replace("/openai", "")

print("最终 base_url:", client._client_params.base_url)

# --- 测试调用 ---
response = llm.invoke("你好，可以帮我总结一下 LangGraph 吗？")
print(response.content)