"""MCP tools against a mocked XploreMore API, in memory and over real streamable HTTP.

Mock API responses are validated against the committed OpenAPI contract, so these tests
cannot drift into testing a shape the real API never returns.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from jsonschema import Draft202012Validator
from mcp.client.client import Client
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from xm_mcp.server import XploreMoreClient, build_server

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = json.loads((ROOT / "contracts/api/problems.v1.openapi.json").read_text(encoding="utf-8"))

PROBLEM = {
    "id": 7,
    "statement": "Streaming tool calls get dropped when emitted inside reasoning blocks",
    "category": "bug_or_reliability",
    "demand_score": 3.14159,
    "voice_count": 4,
    "source_count": 2,
    "platforms": ["github", "hn"],
    "first_seen": "2026-09-01T10:00:00Z",
    "last_seen": "2026-09-12T10:00:00Z",
    "entities": ["vllm"],
    "relevance": 0.91,
    "evidence": [
        {
            "source_id": "github-issues-ai",
            "platform": "github",
            "url": "https://github.com/o/r/issues/1",
            "excerpt": "x " * 140,
            "engagement": {"points": 12, "comments": 30, "reactions": 40},
            "date": "2026-09-10T00:00:00Z",
            "p_problem": 0.93,
        }
    ],
}
LISTING = {"as_of": "2026-09-13T00:00:00Z", "ranker": "demand-v0+rrf", "degraded": [], "results": [PROBLEM]}
DETAIL = {
    **PROBLEM,
    "relevance": None,
    "member_count": 5,
    "effective_voices": 3.6,
    "scorer_version": "problem-prior-2026-09-13c",
    "demand_factors": {"voices": 1.5, "sources": 1.55, "recency": 0.9, "engagement": 1.8, "category": 1.0},
}


def _schema_validator(name: str) -> Draft202012Validator:
    resource = Resource(contents={"components": CONTRACT["components"]}, specification=DRAFT202012)
    registry = Registry().with_resource("contract", resource)
    return Draft202012Validator({"$ref": f"contract#/components/schemas/{name}"}, registry=registry)


def test_mock_responses_conform_to_the_contract() -> None:
    _schema_validator("ProblemsResponse").validate(LISTING)
    _schema_validator("ProblemDetail").validate(DETAIL)


def api(requests: list[httpx.Request], *, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if status != 200:
            return httpx.Response(status, headers={"Retry-After": "17"}, json={"detail": "x"})
        if request.url.path == "/v1/problems":
            return httpx.Response(200, json=LISTING)
        if request.url.path == "/v1/problems/7":
            return httpx.Response(200, json=DETAIL)
        if request.url.path == "/v1/search":
            return httpx.Response(200, json={"query": "q", "degraded": [], "results": []})
        return httpx.Response(404, json={"detail": "not found"})

    return httpx.MockTransport(handler)


def structured(result: Any) -> dict[str, Any]:
    assert not result.is_error, result.content
    return result.structured_content


async def test_tools_are_listed_with_descriptions() -> None:
    server = build_server(XploreMoreClient("http://api.test", transport=api([])))
    async with Client(server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {"find_problems", "get_problem", "search_stories"}
    assert all(t.description for t in tools.values())


async def test_find_problems_is_compact_and_forwards_key_and_bounds() -> None:
    seen: list[httpx.Request] = []
    server = build_server(XploreMoreClient("http://api.test", "xm_secret", transport=api(seen)))
    async with Client(server) as client:
        out = structured(
            await client.call_tool("find_problems", {"topic": "tool calling", "limit": 50, "since_days": 400})
        )
    request = seen[0]
    assert request.headers["X-XM-Api-Key"] == "xm_secret"
    assert request.url.params["limit"] == "10" and request.url.params["since_days"] == "90"
    assert "category" not in request.url.params  # unset filters are not sent
    problem = out["problems"][0]
    assert problem["demand"] == 3.14 and problem["voices"] == 4 and problem["last_seen"] == "2026-09-12"
    assert len(problem["evidence"][0]["excerpt"]) <= 200
    assert "engagement" not in problem["evidence"][0]  # token budget: dropped from list output


async def test_get_problem_includes_demand_factors() -> None:
    server = build_server(XploreMoreClient("http://api.test", transport=api([])))
    async with Client(server) as client:
        out = structured(await client.call_tool("get_problem", {"problem_id": 7}))
    assert out["members"] == 5 and out["demand_factors"]["recency"] == 0.9


async def test_rate_limit_becomes_a_readable_tool_error() -> None:
    server = build_server(XploreMoreClient("http://api.test", transport=api([], status=429)))
    async with Client(server) as client:
        result = await client.call_tool("find_problems", {})
    assert result.is_error
    assert "retry after 17s" in result.content[0].text


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def http_server():
    server = build_server(XploreMoreClient("http://api.test", transport=api([])))
    app = server.streamable_http_app(stateless_http=True, json_response=True)
    port = _free_port()
    uv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not uv.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert uv.started, "MCP HTTP server did not start"
    yield f"http://127.0.0.1:{port}/mcp"
    uv.should_exit = True
    thread.join(timeout=5)


async def test_streamable_http_transport_end_to_end(http_server: str) -> None:
    async with Client(http_server) as client:
        tools = await client.list_tools()
        out = structured(await client.call_tool("find_problems", {"topic": "tool calling"}))
    assert {t.name for t in tools.tools} == {"find_problems", "get_problem", "search_stories"}
    assert out["problems"][0]["id"] == 7
