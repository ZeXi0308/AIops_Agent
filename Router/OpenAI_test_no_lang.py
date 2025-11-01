import requests

# ===== 配置部分 =====
SELECTED_MODEL = "global-gpt-4.1"   # 换成你们内部部署的模型名称
JWT_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6IkpZaEFjVFBNWl9MWDZEQmxPV1E3SG4wTmVYRSIsImtpZCI6IkpZaEFjVFBNWl9MWDZEQmxPV1E3SG4wTmVYRSJ9.eyJhdWQiOiJlZWNjYTc0Ni05MTlkLTQ5OGMtOGI1YS0zYzBkZGQwMzZkYWYiLCJpc3MiOiJodHRwczovL3N0cy53aW5kb3dzLm5ldC85MmU4NGNlYi1mYmZkLTQ3YWItYmU1Mi0wODBjNmI4Nzk1M2YvIiwiaWF0IjoxNzU2ODk3NjQyLCJuYmYiOjE3NTY4OTc2NDIsImV4cCI6MTc1NjkwMTU0MiwiYWlvIjoiazJSZ1lQaFNXeDR5OFV0NTBQN01tS1k1aSsrcEFBQT0iLCJhcHBpZCI6ImVlY2NhNzQ2LTkxOWQtNDk4Yy04YjVhLTNjMGRkZDAzNmRhZiIsImFwcGlkYWNyIjoiMSIsImlkcCI6Imh0dHBzOi8vc3RzLndpbmRvd3MubmV0LzkyZTg0Y2ViLWZiZmQtNDdhYi1iZTUyLTA4MGM2Yjg3OTUzZi8iLCJvaWQiOiJmYWRjYTBlOS05MzdlLTQ2YTctODQ0Yi03MjdmN2I0ZTE5MmUiLCJyaCI6IjEuQVJFQTYwem9rdjM3cTBlLVVnZ01hNGVWUDBhbnpPNmRrWXhKaTFvOERkMERiYThSQUFBUkFBLiIsInN1YiI6ImZhZGNhMGU5LTkzN2UtNDZhNy04NDRiLTcyN2Y3YjRlMTkyZSIsInRpZCI6IjkyZTg0Y2ViLWZiZmQtNDdhYi1iZTUyLTA4MGM2Yjg3OTUzZiIsInV0aSI6ImxscTRMMmxPREVHTm1yQXQ0dmVkQUEiLCJ2ZXIiOiIxLjAiLCJ4bXNfZnRkIjoiazdZenVicXkxY1hnczBrMFRQRVl3dVJ5RjB1bGJ2a1pkV24zRG1aa3k1b0JjM2RsWkdWdVl5MWtjMjF6In0.YrT8v9WuFE7aHkecobDOPjaaZ9L5AWHPFD4w5X01MyKgBkoDGw1z6JGoMPs81mLct2JKmh4XSF0lAGwCaCoBch1UAP60T8kXMq0tneSQOtyXEORrv_11HeW1AiJkHwqs9zDtiasx6ov7Y6GcFgh4tcw32oXEYpPnKz7omrxwZwOSaM_CSJYgyrZuzlnOdRr2aruP9k7cu7eyu1tr_5SfCyWBfz6oQwyRMtiW3fGTrzsnvk4j1v4yOuV--1Gnd_JIOwyKd8Gdr0hs-eFxPNo7mg8gEsp--hpPPjMvdEyF3H1qEbETu1h6USLRWoMJzMfYSZ4zy51XdNAinlpi7zAKSg"


CHAT_ENDPOINT = f"https://apigwy.ericsson.net/generativeai-model/v1/azure/text/deployments/{SELECTED_MODEL}/chat/completions?api-version=2023-07-01-preview"


def call_internal_gpt(messages, stream=False):
    print(JWT_TOKEN)
    payload = {
        "model": SELECTED_MODEL,
        "messages": messages,
        "temperature": 1,
        "stream": stream,
    }

    headers = {
        "Authorization": f"Bearer {JWT_TOKEN}",   # 固定 JWT
        "Content-Type": "application/json",
    }

    response = requests.post(
        CHAT_ENDPOINT,
        json=payload,
        headers=headers,
        stream=stream,
        timeout=30
    )
    response.raise_for_status()

    if stream:
        # 模拟流式输出
        for line in response.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                data = line[len("data: "):]
                if data.strip() != "[DONE]":
                    print("Stream chunk:", data)
    else:
        return response.json()


if __name__ == "__main__":
    # 构造一次对话
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "你好，请简单介绍一下JWT鉴权。"}
    ]

    # 测试非流式调用
    result = call_internal_gpt(messages, stream=False)
    print("Response JSON:", result)

    # 如果要测试流式
    # call_internal_gpt(messages, stream=True)

