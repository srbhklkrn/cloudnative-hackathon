"""Use the official MCP client. Credentials are read from environment, never argv.

uv run --with mcp --env-file /secure/path/credentials.env python -m scripts.dash0_mcp list
uv run --with mcp --env-file /secure/path/credentials.env python -m scripts.dash0_mcp call TOOL '{"argument":"value"}'
"""
import asyncio
import json
import os
import sys
from urllib.parse import urlparse

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from backend.telemetry import export_headers


async def main():
    url = os.getenv("DASH0_MCP_URL")
    if not url:
        host = urlparse(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")).hostname or ""
        if not host.startswith("ingress.") or not host.endswith(".dash0.com"):
            raise ValueError("Set DASH0_MCP_URL to the endpoint from Dash0 Settings → Endpoints")
        url = f"https://api.{host.removeprefix('ingress.')}/mcp"
    headers = {"Authorization": "Bearer " + os.environ["DASH0_AUTH_TOKEN"]} if os.getenv("DASH0_AUTH_TOKEN") else export_headers()
    async with httpx.AsyncClient(headers=headers, timeout=90) as client:
        async with streamable_http_client(url, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                if sys.argv[1:2] == ["call"]:
                    result = await session.call_tool(sys.argv[2], json.loads(sys.argv[3]))
                    print(result.model_dump_json(indent=2))
                else:
                    result = await session.list_tools()
                    print(json.dumps([{"name": tool.name, "description": tool.description,
                                       "inputSchema": tool.inputSchema} for tool in result.tools], indent=2))


if __name__ == "__main__":
    asyncio.run(main())
