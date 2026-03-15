import asyncio
import json
import sys
from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession
from mcp import StdioServerParameters

async def main():
    server_params = StdioServerParameters(
        command="m:\\Coding\\MCP_Server\\.venv\\Scripts\\python.exe",
        args=["-m", "mcp_docs_server.main"],
        env={"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONPATH": "m:\\Coding\\MCP_Server\\src"}
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Call tool
            try:
                result = await session.call_tool("scrape_page", arguments={"url": "https://magicui.design/docs/components/light-rays"})
                print("Result:", result)
            except Exception as e:
                print("Error:", repr(e))

if __name__ == "__main__":
    asyncio.run(main())
