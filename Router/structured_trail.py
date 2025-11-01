from pydantic import BaseModel
import asyncio
from ericai_llm_async2 import llm as create_llm

class WeatherResponse(BaseModel):
    city: str
    temperature_celsius: float
    conditions: str

async def main():
    # 获取 LLM 实例
    llm_instance = await create_llm()
    
    # 包装结构化输出
    llm_structured = llm_instance.with_structured_output(WeatherResponse)
    
    # 调用 LLM
    response: WeatherResponse = await llm_structured.ainvoke(
        "What is the weather in San Francisco?"
    )
    print("response is",response)
    # 强制输出 JSON
    json_output = response.json()
    print(json_output)

if __name__ == "__main__":
    asyncio.run(main())
