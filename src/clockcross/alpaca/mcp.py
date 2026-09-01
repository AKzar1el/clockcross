from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

_READ_ONLY_TOOLS = {
    "get_account_info",
    "get_account_config",
    "get_portfolio_history",
    "get_account_activities",
    "get_clock",
    "get_stock_snapshot",
    "get_crypto_snapshot",
    "get_option_chain",
    "get_option_snapshot",
    "get_option_latest_quote",
    "get_news",
}
_SECRET_FRAGMENTS = ("key", "secret", "token", "password", "authorization")


def sanitize_arguments(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if any(fragment in text_key.lower() for fragment in _SECRET_FRAGMENTS):
                sanitized[text_key] = "[REDACTED]"
            else:
                sanitized[text_key] = sanitize_arguments(item)
        return sanitized
    if isinstance(value, (list, tuple)):
        return [sanitize_arguments(item) for item in value]
    return value


class McpToolRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class McpContextRequest(BaseModel):
    calls: tuple[McpToolRequest, ...]


class McpEvidenceItem(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    invoked_at: datetime
    success: bool
    result_sha256: str = ""
    error_code: str | None = None
    content: Any | None = Field(default=None, exclude=True)


class McpEvidence(BaseModel):
    items: list[McpEvidenceItem]

    @property
    def complete(self) -> bool:
        return bool(self.items) and all(item.success for item in self.items)


class AlpacaMcpGateway:
    """Auditable read-only boundary around Alpaca MCP tool calls."""

    def __init__(self, *, runner: Callable[[str, dict[str, Any]], Any]) -> None:
        self._runner = runner

    def collect_context(self, request: McpContextRequest) -> McpEvidence:
        items: list[McpEvidenceItem] = []
        for call in request.calls:
            invoked_at = datetime.now(timezone.utc)
            safe_arguments = sanitize_arguments(call.arguments)
            if call.name not in _READ_ONLY_TOOLS:
                items.append(
                    McpEvidenceItem(
                        tool_name=call.name,
                        arguments=safe_arguments,
                        invoked_at=invoked_at,
                        success=False,
                        error_code="tool_not_allowed",
                    )
                )
                continue
            try:
                result = self._runner(call.name, call.arguments)
                canonical = json.dumps(result, sort_keys=True, default=str, separators=(",", ":"))
                digest = hashlib.sha256(canonical.encode()).hexdigest()
                items.append(
                    McpEvidenceItem(
                        tool_name=call.name,
                        arguments=safe_arguments,
                        invoked_at=invoked_at,
                        success=True,
                        result_sha256=digest,
                        content=result,
                    )
                )
            except Exception:
                items.append(
                    McpEvidenceItem(
                        tool_name=call.name,
                        arguments=safe_arguments,
                        invoked_at=invoked_at,
                        success=False,
                        error_code="tool_failure",
                    )
                )
        return McpEvidence(items=items)


class DefaultAlpacaMcpRunner:
    """Launch Alpaca's official MCP server with read-only toolsets over stdio."""

    def __init__(
        self,
        *,
        api_key: str,
        secret_key: str,
        command: str = "uvx",
        args: Sequence[str] = (
            "--with",
            "fastmcp==3.4.7",
            "--from",
            "alpaca-mcp-server==2.2.0",
            "alpaca-mcp-server",
        ),
    ) -> None:
        self._command = command
        self._args = tuple(args)
        self._env = {
            **os.environ,
            "ALPACA_API_KEY": api_key,
            "ALPACA_SECRET_KEY": secret_key,
            "ALPACA_PAPER_TRADE": "true",
            "ALPACA_TOOLSETS": "account,assets,stock-data,crypto-data,options-data,news",
        }

    def __call__(self, name: str, arguments: dict[str, Any]) -> Any:
        return asyncio.run(self._call(name, arguments))

    async def _call(self, name: str, arguments: dict[str, Any]) -> Any:
        try:
            from mcp import Client
            from mcp.client.stdio import StdioServerParameters, stdio_client
        except ImportError as exc:  # pragma: no cover - integration environment only
            raise RuntimeError("mcp Python SDK is required for Alpaca MCP access") from exc

        server = StdioServerParameters(
            command=self._command,
            args=list(self._args),
            env=self._env,
        )
        async with Client(stdio_client(server)) as client:
            result = await client.call_tool(name, arguments)
        structured = getattr(result, "structured_content", None)
        if structured is not None:
            return structured
        content = getattr(result, "content", [])
        normalized: list[Any] = []
        for block in content:
            if hasattr(block, "model_dump"):
                normalized.append(block.model_dump(mode="json"))
            else:
                normalized.append(str(block))
        return normalized
