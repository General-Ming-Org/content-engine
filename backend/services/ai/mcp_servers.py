"""
Helper for constructing the `mcp_servers` argument passed to Claude API calls.

When a generation task can benefit from on-demand context retrieval, it passes
a list of MCP server configs to claude_client.generate(). Claude decides whether
and how to call the exposed tools.

Server identifiers used in code:
  - "knowledge" — our custom knowledge MCP (search prior research / posts / articles)
  - "tavily"    — public-web search via Tavily MCP
"""
from typing import Any

from config import get_settings


def build_mcp_servers(names: list[str]) -> list[dict[str, Any]]:
    """Resolve logical MCP names to the format expected by anthropic.messages.create."""
    settings = get_settings()
    configs: list[dict[str, Any]] = []

    for name in names:
        if name == "knowledge":
            configs.append({
                "type": "url",
                "url": settings.mcp_knowledge_url,
                "name": "content-engine-knowledge",
                "authorization_token": settings.mcp_knowledge_token or None,
            })
        elif name == "tavily":
            configs.append({
                "type": "url",
                "url": settings.mcp_tavily_url,
                "name": "tavily-search",
                "authorization_token": settings.tavily_api_key or None,
            })
        else:
            raise ValueError(f"Unknown MCP server: {name}")

    return configs
