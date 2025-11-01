from langchain_openai import ChatOpenAI
import httpx
import os
import time
import asyncio
from typing import Optional
from dataclasses import dataclass
import logging
from ericai_key_manager.ericai_key_manager import get_api_key_manager 

logger = logging.getLogger(__name__)

@dataclass
class EricAIConfig:
    """Configuration for EricAI client with auto-refresh capabilities."""
    
    base_url: str = "https://ray.sero.gic.ericsson.se/backendsso/v1/"
    model: str = "Qwen/Qwen2.5-32B-Instruct"
    # model: str = "Qwen/Qwen2.5-14B-Instruct-1M"
    # model: str ="openai/gpt-oss-20b"
    #model: str ="Qwen/Qwen2.5-14B-Instruct-1M"
    #model: str ="deepseek-ai/DeepSeek-R1-0528"
    #model: str ="Qwen/Qwen3-235B-A22B-Thinking-2507-FP8"
    #model: str="mistralai/Mistral-Nemo-Instruct-2407"
    key_valid_minutes: int = 60
    refresh_buffer_minutes: int = 3
    
    @property
    def refresh_interval_seconds(self) -> int:
        return (self.key_valid_minutes - self.refresh_buffer_minutes) * 60


class AutoRefreshEricAIClient:
    
    def __init__(self, config: Optional[EricAIConfig] = None):
        self.config = config or EricAIConfig()
        self._llm_client: Optional[ChatOpenAI] = None
        self._http_client: Optional[httpx.Client] = None
        self._last_key_refresh = 0.0
        self._current_token: Optional[str] = None
        self._key_manager = get_api_key_manager() 
        
    async def _get_ericai_key(self) -> str:
        try:

            def get_key():
                return self._key_manager.get_ericai_apikey()
            
            token = await asyncio.to_thread(get_key)
            if not token:
                raise RuntimeError("did not get valid access token")
                
            return token
        except Exception as e:
            logger.error(f"获取EricAI密钥时发生错误: {str(e)}")
            raise RuntimeError(f"获取EricAI密钥时发生错误: {str(e)}") from e

    async def _create_llm_client(self) -> ChatOpenAI:
        try:
            api_key = await self._get_ericai_key()
            self._current_token = api_key
            if self._http_client:
                await self._http_client.aclose()
            
            self._http_client = httpx.AsyncClient(verify=False, timeout=30.0)
            os.environ["OPENAI_API_KEY"] = api_key
            
            llm_client = ChatOpenAI(
                base_url=self.config.base_url,
                api_key=api_key,
                model=self.config.model,
                http_async_client=self._http_client,
                http_client=httpx.Client(verify=False),
                default_headers={"User-Agent": "EricAI-Client"},
            )
            
            llm_client._client = httpx.Client(verify=False, timeout=30.0)
            
            self._last_key_refresh = time.time()
            logger.info("EricAI客户端密钥已更新")
            return llm_client
            
        except Exception as e:
            logger.error(f"Creating EricAI Client failed: {str(e)}")
            raise

    def _should_refresh_key(self) -> bool:
        if self._llm_client is None:
            return True
            
        try:
        
            return self._key_manager.key_is_expired()
        except Exception as e:
            logger.warning(f"检查密钥过期状态失败，使用备用逻辑: {str(e)}")

            if self._last_key_refresh == 0:
                return True 
            elapsed_time = time.time() - self._last_key_refresh
            return elapsed_time >= self.config.refresh_interval_seconds

    async def check_and_refresh(self) -> None:

        if self._should_refresh_key():
            logger.info("EricAI key refreshing") 
            try:
                self._llm_client = await self._create_llm_client()
                logger.info("EricAI key refresh successfully!")
            except Exception as e:
                logger.error(f"刷新EricAI客户端失败: {str(e)}")
                self._llm_client = None  
                raise  
    
    async def get_llm_client(self) -> ChatOpenAI:
        await self.check_and_refresh()
        
        if self._llm_client is None:
            raise RuntimeError("无法创建EricAI客户端实例")
            
        return self._llm_client
    
    async def cleanup(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        logger.info("EricAI client resources cleared")

    def get_current_token(self) -> Optional[str]:
        return self._current_token


_global_ericai_client: Optional[AutoRefreshEricAIClient] = None

async def get_auto_refresh_llm(config: Optional[EricAIConfig] = None) -> ChatOpenAI:
    global _global_ericai_client
    
    if _global_ericai_client is None:
        _global_ericai_client = AutoRefreshEricAIClient(config)
    
    return await _global_ericai_client.get_llm_client()

async def cleanup_global_client():
    global _global_ericai_client
    if _global_ericai_client:
        await _global_ericai_client.cleanup()
        _global_ericai_client = None
async def get_ericai_key() -> str:
    key_manager = get_api_key_manager()
    return await asyncio.to_thread(key_manager.get_ericai_apikey)
async def llm() -> ChatOpenAI:
    return await get_auto_refresh_llm()