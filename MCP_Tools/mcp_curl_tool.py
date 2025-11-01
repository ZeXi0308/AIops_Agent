from typing import Dict
from mcp.server.fastmcp import FastMCP
import httpx

# 创建 FastMCP 实例
mcp = FastMCP(name="InfobankService")

@mcp.tool(
        name="get_latest_UP_version",
    description="""Retrieve the latest available Upgrade Package (UP) versions for product CXP2010174_2 from MIA.
    
    This tool queries the MIA API to get the most recent upgrade packages based on specified criteria.
    
    Parameters should be extracted from user query:
    - number_versions: Extract the number of versions requested, default to 5 if not specified
    - confidence_level: Extract confidence level (1-4), default to 3 if not specified
    
    Usage examples:
    - "Get latest 3 UP versions with CL 2" → number_versions=3, confidence_level=2
    - "Show me 10 UP recent versions, confidence level 4" → number_versions=10, confidence_level=4
    - "Latest versions" → number_versions=5, confidence_level=3 (defaults)"""
)
async def get_product_revisions(number_versions: int) -> Dict[int, str]:
    """
    Query InfoBank REST API to get the latest N versions for fixed product number CXP2010174_2.
    
    Parameters
    ----------
    number_versions : int, default=5
        Number of latest versions to return. Extract from user query or use default value 5
        if not explicitly specified.
        
    confidence_level : int, default=3
        Confidence level for the query (typically 1-4). Extract from user query terms like
        "CL", "confidence level", or use default value 3 if not mentioned.
        
    Returns
    -------
    Dict[int, str]
        Dictionary of version numbers, e.g., {1: "R40A10", 2: "R40A09", ...}
    """
    # 固定查询参数
    product_number = "CXP2010174_2"
    confidence_level = 3
    confidence_level_depth = 0

    url = "https://infobank.npee.gic.ericsson.se/infobank/rest/v2/product/revision"
    params = {
        "product_number": product_number,
        "latest": number_versions,
        "confidence_level": confidence_level,
        "confidence_level_depth": confidence_level_depth
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    product_number = "CXP2010174_2-"
    versions = {
        idx + 1: f"{product_number}{item.get('version').replace(' ', '')}"
        for idx, item in enumerate(data)
        if item.get("version")
    }
    return versions

if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
    )
