from langchain_openai import ChatOpenAI
import httpx
import asyncio
import json
# 固定的 JWT token
JWT_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6IkpZaEFjVFBNWl9MWDZEQmxPV1E3SG4wTmVYRSIsImtpZCI6IkpZaEFjVFBNWl9MWDZEQmxPV1E3SG4wTmVYRSJ9.eyJhdWQiOiJlZWNjYTc0Ni05MTlkLTQ5OGMtOGI1YS0zYzBkZGQwMzZkYWYiLCJpc3MiOiJodHRwczovL3N0cy53aW5kb3dzLm5ldC85MmU4NGNlYi1mYmZkLTQ3YWItYmU1Mi0wODBjNmI4Nzk1M2YvIiwiaWF0IjoxNzU2Mzc0OTAyLCJuYmYiOjE3NTYzNzQ5MDIsImV4cCI6MTc1NjM3ODgwMiwiYWlvIjoiazJSZ1lQaFNXeDR5OFV0NTBQN01tS1k1aSsrcEFBQT0iLCJhcHBpZCI6ImVlY2NhNzQ2LTkxOWQtNDk4Yy04YjVhLTNjMGRkZDAzNmRhZiIsImFwcGlkYWNyIjoiMSIsImlkcCI6Imh0dHBzOi8vc3RzLndpbmRvd3MubmV0LzkyZTg0Y2ViLWZiZmQtNDdhYi1iZTUyLTA4MGM2Yjg3OTUzZi8iLCJvaWQiOiJmYWRjYTBlOS05MzdlLTQ2YTctODQ0Yi03MjdmN2I0ZTE5MmUiLCJyaCI6IjEuQVJFQTYwem9rdjM3cTBlLVVnZ01hNGVWUDBhbnpPNmRrWXhKaTFvOERkMERiYThSQUFBUkFBLiIsInN1YiI6ImZhZGNhMGU5LTkzN2UtNDZhNy04NDRiLTcyN2Y3YjRlMTkyZSIsInRpZCI6IjkyZTg0Y2ViLWZiZmQtNDdhYi1iZTUyLTA4MGM2Yjg3OTUzZiIsInV0aSI6IktGcHlpRU1GWGtHc1EwVVA1STBlQUEiLCJ2ZXIiOiIxLjAiLCJ4bXNfZnRkIjoiRnZ2MGZSTnpEOEEtSTFhOE9fMWhzcllJbWJrRmdvQUVwbHo0TGtSdXZhQUJabkpoYm1ObFl5MWtjMjF6In0.hqMC47SaZesoPCSOsW7IKjHDiQHxdFq9ZKJNqGTAnNk5_HWht9iEH_5XoxmBl_OHLMhg6XadEHRjfUOWKYHGpS94sUwzSGpQ9N3ynECo7CIgU3m46CRW2hgP462DhEnRa4Ov_Qa1RIMK1uE7MLMKQJrYl5kVz0DEuysVG89FZqhm3Zdvm7956wGusZbpU84V-dDHByNMR5YCzDowMY7Cn8YK8JS5zXZc3-FBFwuvj6AbOD_Vx-HJUFZIXn2BG2a_SSu5-_GNZ-s1rrydlPzZ3UcX8lkyzPaivdiUo_0KXwqP72e1WFAvJaSK0btVIimjpLvFTFT-iVk_TbHRb9_D1g"

# 可切换模型
SELECTED_MODEL = "global-gpt-4.1"
SELECTED_MODE = "Lse-gpt-5"
# endpoint 拼接
CHAT_ENDPOINT  = f"https://apigwy.ericsson.net/generativeai-model/v1/azure/text/deployments/{SELECTED_MODEL}/chat/completions?api-version=2023-07-01-preview"
async def ask_llm(messages):
    headers = {
        "Authorization": f"Bearer {JWT_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": SELECTED_MODEL,
        "messages": messages,
        "temperature": 1,
        "stream": False  # True 如果需要流式
    }

    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.post(CHAT_ENDPOINT, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()

async def main():
    messages = [{"role": "user", "content": "Hello, can you introduce yourself in one sentence?"}]
    response = await ask_llm(messages)
    print(json.dumps(response, indent=2))

if __name__ == "__main__":
    asyncio.run(main())


