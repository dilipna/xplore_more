"""XploreMore MCP server over streamable HTTP.

Tools: find_problems, get_problem, search_stories.

Design choices
- A thin client of the public REST API, not a second path to the database. Auth, rate limits,
  ranking and the OpenAPI contract are enforced in one place.
- Streamable HTTP, stateless, JSON responses: no subprocess (Pro2Pro's stdio MCP server hung
  production runs, ADR-0011 there), and no session affinity is needed behind a load balancer.
- Token-lean results: agents resend tool output every turn, so tools return short fields and
  truncated excerpts, and state the evidence count instead of inlining everything.
- No LLM anywhere in this server; it only retrieves and formats.

Environment: XM_API_URL (required), XM_API_KEY, XM_MCP_HOST, XM_MCP_PORT, XM_MCP_ALLOWED_HOSTS
(comma-separated Host values accepted for DNS-rebinding protection).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

log = logging.getLogger("xm_mcp")

Category = Literal["bug_or_reliability", "cost_or_performance", "missing_capability", "workflow_friction"]
EXCERPT_CHARS = 200

INSTRUCTIONS = (
    "XploreMore discovers real problems people report on Hacker News, GitHub issues, Lobsters and "
    "Stack Exchange, clusters duplicates, and ranks them by demand (independent voices, sources, "
    "recency, engagement). Use find_problems first to discover validated pain points, get_problem for "
    "full evidence, and search_stories for recent technology news context. Evidence URLs are public "
    "posts; voice counts are distinct authors."
)


class XploreMoreClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        *,
        timeout: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {"User-Agent": "xploremore-mcp/0.1"}
        if api_key:
            headers["X-XM-Api-Key"] = api_key
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout, transport=transport
        )

    async def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        clean = {k: v for k, v in params.items() if v is not None}
        try:
            response = await self._http.get(path, params=clean)
        except httpx.HTTPError as exc:
            raise ToolError(f"XploreMore API unreachable: {type(exc).__name__}") from exc
        if response.status_code == 429:
            raise ToolError(
                f"XploreMore rate limit reached; retry after {response.headers.get('Retry-After', '60')}s"
            )
        if response.status_code == 404:
            raise ToolError("not found")
        if response.status_code in (401, 403):
            raise ToolError("XploreMore rejected the API key (check XM_API_KEY)")
        if response.status_code >= 400:
            raise ToolError(f"XploreMore API error {response.status_code}")
        return response.json()

    async def aclose(self) -> None:
        await self._http.aclose()


def _short(text: str, limit: int = EXCERPT_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def _problem(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": p["id"],
        "statement": _short(p["statement"], 240),
        "category": p["category"],
        "demand": round(p["demand_score"], 2),
        "voices": p["voice_count"],
        "sources": p["source_count"],
        "platforms": p["platforms"],
        "last_seen": p["last_seen"][:10],
        **({"relevance": round(p["relevance"], 2)} if p.get("relevance") is not None else {}),
        "evidence": [
            {"url": e["url"], "platform": e["platform"], "excerpt": _short(e["excerpt"])}
            for e in p["evidence"]
        ],
    }


def build_server(client: XploreMoreClient) -> MCPServer:
    server = MCPServer(name="xploremore", instructions=INSTRUCTIONS, version="0.1.0")

    @server.tool(
        description=(
            "Find real, clustered problems people report, ranked by demand. Optionally filter by topic "
            "(hybrid search over the evidence), category, recency (since_days) and minimum distinct voices."
        )
    )
    async def find_problems(
        topic: str | None = None,
        category: Category | None = None,
        since_days: int = 30,
        min_voices: int = 2,
        limit: int = 5,
    ) -> dict[str, Any]:
        data = await client.get(
            "/v1/problems",
            {
                "topic": topic,
                "category": category,
                "since_days": max(1, min(since_days, 90)),
                "min_voices": max(1, min(min_voices, 100)),
                "limit": max(1, min(limit, 10)),
                "evidence": 2,
            },
        )
        return {"ranker": data["ranker"], "problems": [_problem(p) for p in data["results"]]}

    @server.tool(description="Get one problem with its demand breakdown and up to `evidence` source posts.")
    async def get_problem(problem_id: int, evidence: int = 5) -> dict[str, Any]:
        data = await client.get(f"/v1/problems/{problem_id}", {"evidence": max(1, min(evidence, 10))})
        return {
            **_problem(data),
            "members": data["member_count"],
            "demand_factors": data["demand_factors"],
            "first_seen": data["first_seen"][:10],
        }

    @server.tool(description="Search recent technology news stories (deduplicated across sources).")
    async def search_stories(query: str, limit: int = 5) -> dict[str, Any]:
        data = await client.get("/v1/search", {"q": query, "limit": max(1, min(limit, 10))})
        return {
            "stories": [
                {
                    "id": s["id"],
                    "title": _short(s["title"], 160),
                    "url": s["url"],
                    "sources": s["source_count"],
                }
                for s in data["results"]
            ]
        }

    return server


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    base_url = os.environ["XM_API_URL"]
    server = build_server(XploreMoreClient(base_url, os.environ.get("XM_API_KEY")))
    allowed = [h.strip() for h in os.environ.get("XM_MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    security = TransportSecuritySettings(allowed_hosts=allowed) if allowed else None
    server.run(
        "streamable-http",
        host=os.environ.get("XM_MCP_HOST", "127.0.0.1"),
        port=int(os.environ.get("XM_MCP_PORT", "8766")),
        stateless_http=True,
        json_response=True,
        transport_security=security,
    )


if __name__ == "__main__":
    main()
