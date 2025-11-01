from langchain_mcp_adapters.client import MultiServerMCPClient

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
                "url": "http://localhost:8005/mcp/",
                "transport": "streamable_http",
            }
    }
    return MultiServerMCPClient(config)
