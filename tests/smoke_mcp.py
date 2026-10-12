"""用官方 MCP 客户端启动真实 stdio 服务，验证工具发现和本地调用。"""
import asyncio
import json
import os
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    project = Path(__file__).resolve().parents[1]
    params = StdioServerParameters(command=sys.executable,
                                    args=[str(project / "mcp_server.py")],
                                    env={**{k:v for k,v in os.environ.items() if k != "UNPAYWALL_EMAIL"}, "PYTHONIOENCODING": "utf-8"})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(tool.name for tool in tools.tools)
            expected = sorted(["search_papers", "lookup_paper", "locate_open_access",
                               "download_open_access", "zju_access_guide", "import_local_pdf",
                               "prepare_reading_list", "open_paper_access", "collect_paper"])
            assert names == expected, names
            guide = await session.call_tool("zju_access_guide", {"doi": "10.3390/metrology5040071"})
            assert not guide.isError
            data = guide.structuredContent
            assert data and data["status"] == "MANUAL_INSTITUTIONAL_ACCESS", data
            access = await session.call_tool("open_paper_access", {"doi": "10.1000/test", "open_browser": False})
            assert not access.isError and access.structuredContent["authentication"] == "UNKNOWN"
            assert "browser" not in access.structuredContent
            collection = await session.call_tool("collect_paper", {"identifier": "10.1000/test", "open_browser": False})
            assert not collection.isError and collection.structuredContent["status"] == "USER_BROWSER_ACTION_REQUIRED"
            invalid_query = await session.call_tool("prepare_reading_list", {"query": "", "open_browser": False})
            assert invalid_query.isError
            rejected = await session.call_tool("download_open_access", {"identifier": "file:///secret"})
            assert rejected.isError
            print(json.dumps({"status": "PASS", "transport": "stdio", "tools": names,
                              "guide_call": "PASS", "manual_access_call": "PASS", "collection_fallback": "PASS", "invalid_reading_list": "REJECTED", "invalid_download": "REJECTED",
                              "note": "本项未测试校园登录或真实下载；真实下载由单独验收记录"}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
