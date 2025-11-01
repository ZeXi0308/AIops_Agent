from langchain_mcp_adapters.client import MultiServerMCPClient
import asyncio
import httpx
import logging

logger = logging.getLogger(__name__)

async def check_service_health(url: str, timeout: float = 3.0) -> bool:
    """Check if MCP service is available"""
    try:
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        host, port = parsed.hostname, parsed.port
        
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        return True
    except:
        return False

class FaultTolerantMCPClient:
    def __init__(self, config):
        self.config = config
        self.healthy_services = {}
        self.client = None
        
    async def _check_all_services(self):
        """Check health status of all services"""
        tasks = []
        for name, service_config in self.config.items():
            task = asyncio.create_task(
                self._check_service(name, service_config["url"])
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
    async def _check_service(self, name: str, url: str):
        """Check individual service health"""
        is_healthy = await check_service_health(url)
        self.healthy_services[name] = is_healthy
        if not is_healthy:
            logger.warning(f"MCP service {name} at {url} is not available")
        
    async def get_tools(self):
        """Get available tools, skip unhealthy services"""
        await self._check_all_services()
        
        # Print all MCP server status
        self._print_server_status()
        
        # Only use healthy services to create client
        healthy_config = {
            name: config for name, config in self.config.items() 
            if self.healthy_services.get(name, False)
        }
        
        if not healthy_config:
            logger.error("No healthy MCP services available")
            return []
            
        logger.info(f"Using healthy services: {list(healthy_config.keys())}")
        
        try:
            self.client = MultiServerMCPClient(healthy_config)
            return await self.client.get_tools()
        except Exception as e:
            logger.error(f"Failed to get tools from healthy services: {e}")
            return []
    
    def _print_server_status(self):
        """Print status of all MCP servers"""
        print("\n=== MCP Server Status ===")
        for name, config in self.config.items():
            status = "✅ AVAILABLE" if self.healthy_services.get(name, False) else "❌ UNAVAILABLE"
            url = config.get("url", "Unknown")
            print(f"{name:25} {status:15} {url}")
        print("=" * 50)

def create_mcp_client():
    config = {
        "get_latest_UP_version": {
            "url": "http://localhost:8000/mcp/",
            "transport": "streamable_http",
        },
        "UpgradePackageChecker": {
            "url": "http://localhost:8002/mcp/",
            "transport": "streamable_http",
        },
        "DeviceInfoLookup": {
            "url": "http://localhost:8001/mcp/",
            "transport": "streamable_http",
        },
        "RRCMsgExtractor": {
            "url": "http://localhost:8003/mcp/",
            "transport": "streamable_http",
        },
        "JIRAExtractor": {
            "url": "http://localhost:8004/mcp/",
            "transport": "streamable_http",
        },
        "Chart": {
            "url": "http://localhost:8005/mcp/",
            "transport": "streamable_http",
        }
    }
    return FaultTolerantMCPClient(config)
