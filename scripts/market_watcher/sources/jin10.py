"""Jin10 MCP API client — Streamable HTTP transport with session management."""

import json
import urllib.error
import urllib.request
from typing import Any


class Jin10Client:
    """MCP client for Jin10 financial data service (Streamable HTTP)."""

    def __init__(self, server_url: str, bearer_token: str, protocol_version: str = "2025-11-25"):
        self.server_url = server_url
        self.bearer_token = bearer_token
        self.protocol_version = protocol_version
        self._request_id = 0
        self._session_id: str | None = None
        self._initialized = False

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _post(self, payload: dict, capture_session: bool = False) -> dict:
        data = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.bearer_token}",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        req = urllib.request.Request(
            self.server_url, data=data, headers=headers, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if capture_session:
                    sid = resp.headers.get("Mcp-Session-Id")
                    if sid:
                        self._session_id = sid

                content_type = resp.headers.get("Content-Type", "")
                body = resp.read().decode()
                if not body.strip():
                    return {}
                if "text/event-stream" in content_type:
                    return self._parse_sse(body)
                return json.loads(body)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode(errors="replace")[:500]
            raise RuntimeError(f"Jin10 MCP HTTP {e.code}: {err_body}") from e

    @staticmethod
    def _parse_sse(body: str) -> dict:
        last_data = None
        for line in body.split("\n"):
            if line.startswith("data: "):
                last_data = line[6:]
        if last_data:
            return json.loads(last_data)
        return {}

    def initialize(self):
        if self._initialized:
            return
        self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": self.protocol_version,
                    "capabilities": {},
                    "clientInfo": {"name": "stock-advisor-watcher", "version": "1.0.0"},
                },
            },
            capture_session=True,
        )
        self._post({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })
        self._initialized = True

    def call_tool(self, tool_name: str, arguments: dict | None = None) -> dict | None:
        self.initialize()
        resp = self._post({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments or {},
            },
        })
        if "error" in resp:
            return None
        result = resp.get("result", {})
        if result.get("isError"):
            return None
        structured = result.get("structuredContent")
        if structured:
            return structured
        content = result.get("content", [])
        for item in content:
            if item.get("type") == "text":
                try:
                    return json.loads(item["text"])
                except (json.JSONDecodeError, KeyError):
                    return {"text": item["text"]}
        return None

    def list_flash(self, cursor: str | None = None) -> dict | None:
        args = {}
        if cursor:
            args["cursor"] = cursor
        return self.call_tool("list_flash", args)

    def search_flash(self, keyword: str) -> dict | None:
        return self.call_tool("search_flash", {"keyword": keyword})

    def list_news(self, cursor: str | None = None) -> dict | None:
        args = {}
        if cursor:
            args["cursor"] = cursor
        return self.call_tool("list_news", args)

    def search_news(self, keyword: str, cursor: str | None = None) -> dict | None:
        args = {"keyword": keyword}
        if cursor:
            args["cursor"] = cursor
        return self.call_tool("search_news", args)

    def get_news(self, news_id: str) -> dict | None:
        return self.call_tool("get_news", {"id": news_id})

    def get_quote(self, code: str) -> dict | None:
        return self.call_tool("get_quote", {"code": code})

    def list_calendar(self) -> dict | None:
        return self.call_tool("list_calendar", {})


def create_client(config: dict) -> Jin10Client:
    jin10_cfg = config["jin10"]
    return Jin10Client(
        server_url=jin10_cfg["server_url"],
        bearer_token=jin10_cfg["bearer_token"],
        protocol_version=jin10_cfg.get("protocol_version", "2025-11-25"),
    )
