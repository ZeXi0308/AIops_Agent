from typing import List, Optional
from pydantic import BaseModel, Field
from langchain.chat_models.base import BaseChatModel
from langchain.schema import BaseMessage, AIMessage, ChatResult, HumanMessage
from langchain.schema import ChatGeneration, ChatResult
import requests

# ===== 配置部分 =====
SELECTED_MODEL = "global-gpt-4.1"   # 换成你们内部部署的模型名称
JWT_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6IkpZaEFjVFBNWl9MWDZEQmxPV1E3SG4wTmVYRSIsImtpZCI6IkpZaEFjVFBNWl9MWDZEQmxPV1E3SG4wTmVYRSJ9.eyJhdWQiOiJlZWNjYTc0Ni05MTlkLTQ5OGMtOGI1YS0zYzBkZGQwMzZkYWYiLCJpc3MiOiJodHRwczovL3N0cy53aW5kb3dzLm5ldC85MmU4NGNlYi1mYmZkLTQ3YWItYmU1Mi0wODBjNmI4Nzk1M2YvIiwiaWF0IjoxNzU2ODk3NjQyLCJuYmYiOjE3NTY4OTc2NDIsImV4cCI6MTc1NjkwMTU0MiwiYWlvIjoiazJSZ1lQaFNXeDR5OFV0NTBQN01tS1k1aSsrcEFBQT0iLCJhcHBpZCI6ImVlY2NhNzQ2LTkxOWQtNDk4Yy04YjVhLTNjMGRkZDAzNmRhZiIsImFwcGlkYWNyIjoiMSIsImlkcCI6Imh0dHBzOi8vc3RzLndpbmRvd3MubmV0LzkyZTg0Y2ViLWZiZmQtNDdhYi1iZTUyLTA4MGM2Yjg3OTUzZi8iLCJvaWQiOiJmYWRjYTBlOS05MzdlLTQ2YTctODQ0Yi03MjdmN2I0ZTE5MmUiLCJyaCI6IjEuQVJFQTYwem9rdjM3cTBlLVVnZ01hNGVWUDBhbnpPNmRrWXhKaTFvOERkMERiYThSQUFBUkFBLiIsInN1YiI6ImZhZGNhMGU5LTkzN2UtNDZhNy04NDRiLTcyN2Y3YjRlMTkyZSIsInRpZCI6IjkyZTg0Y2ViLWZiZmQtNDdhYi1iZTUyLTA4MGM2Yjg3OTUzZiIsInV0aSI6ImxscTRMMmxPREVHTm1yQXQ0dmVkQUEiLCJ2ZXIiOiIxLjAiLCJ4bXNfZnRkIjoiazdZenVicXkxY1hnczBrMFRQRVl3dVJ5RjB1bGJ2a1pkV24zRG1aa3k1b0JjM2RsWkdWdVl5MWtjMjF6In0.YrT8v9WuFE7aHkecobDOPjaaZ9L5AWHPFD4w5X01MyKgBkoDGw1z6JGoMPs81mLct2JKmh4XSF0lAGwCaCoBch1UAP60T8kXMq0tneSQOtyXEORrv_11HeW1AiJkHwqs9zDtiasx6ov7Y6GcFgh4tcw32oXEYpPnKz7omrxwZwOSaM_CSJYgyrZuzlnOdRr2aruP9k7cu7eyu1tr_5SfCyWBfz6oQwyRMtiW3fGTrzsnvk4j1v4yOuV--1Gnd_JIOwyKd8Gdr0hs-eFxPNo7mg8gEsp--hpPPjMvdEyF3H1qEbETu1h6USLRWoMJzMfYSZ4zy51XdNAinlpi7zAKSg"


CHAT_ENDPOINT = f"https://apigwy.ericsson.net/generativeai-model/v1/azure/text/deployments/{SELECTED_MODEL}/chat/completions?api-version=2023-07-01-preview"


class InternalGPT41(BaseChatModel):
    """内部 GPT-4.1 LLM，支持固定 JWT 和可选流式输出"""
    
    model: str = Field(default=SELECTED_MODEL)
    jwt_token: str = Field(default=JWT_TOKEN)
    stream: bool = Field(default=False)

    def _call(self, messages: List[BaseMessage], stop: Optional[List[str]] = None) -> AIMessage:
        openai_messages = []
        for msg in messages:
            role = "user"
            if msg.type == "system":
                role = "system"
            elif msg.type == "ai":
                role = "assistant"
            openai_messages.append({"role": role, "content": msg.content})

        payload = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": 1,
            "stream": self.stream,
        }

        headers = {
            "Authorization": f"Bearer {self.jwt_token}",
            "Content-Type": "application/json",
        }

        response = requests.post(
            CHAT_ENDPOINT,
            json=payload,
            headers=headers,
            stream=self.stream,
            timeout=30
        )
        response.raise_for_status()

        if self.stream:
            for line in response.iter_lines(decode_unicode=True):
                if line and line.startswith("data: "):
                    data = line[len("data: "):]
                    if data.strip() != "[DONE]":
                        print("Stream chunk:", data)
            return AIMessage(content="[STREAM OUTPUT DONE]")
        else:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return AIMessage(content=content)

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None) -> ChatResult:
        ai_msg = self._call(messages, stop=stop)

        # 正确方式：用一维 list
        generation = ChatGeneration(text=ai_msg.content, message=ai_msg)
        return ChatResult(generations=[generation])
        
    @property
    def _identifying_params(self):
        return {"model": self.model}

    @property
    def _llm_type(self) -> str:
        return "internal-gpt41"



if __name__ == "__main__":
    llm = InternalGPT41(stream=False)
    messages = [HumanMessage(content="请简单介绍JWT鉴权")]

    result = llm.invoke(messages)
    print("LLM Response:", result.content)
