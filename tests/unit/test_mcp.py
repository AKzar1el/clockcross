from __future__ import annotations

from clockcross.alpaca.mcp import (
    AlpacaMcpGateway,
    DefaultAlpacaMcpRunner,
    McpContextRequest,
    McpToolRequest,
    sanitize_arguments,
)


def test_sanitize_arguments_redacts_secret_like_fields_recursively():
    sanitized = sanitize_arguments({
        "symbol": "COIN",
        "api_key": "abc",
        "nested": {"access_token": "def", "safe": 3},
    })
    assert sanitized["symbol"] == "COIN"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["access_token"] == "[REDACTED]"
    assert sanitized["nested"]["safe"] == 3


def test_gateway_records_hash_and_sanitized_arguments():
    calls = []

    def runner(name, args):
        calls.append((name, args))
        return {"news": [{"headline": "COIN headline"}]}

    gateway = AlpacaMcpGateway(runner=runner)
    evidence = gateway.collect_context(
        McpContextRequest(
            calls=(McpToolRequest(name="get_news", arguments={"symbols": "COIN"}),)
        )
    )
    assert len(evidence.items) == 1
    item = evidence.items[0]
    assert item.success is True
    assert item.tool_name == "get_news"
    assert item.arguments == {"symbols": "COIN"}
    assert len(item.result_sha256) == 64
    assert calls == [("get_news", {"symbols": "COIN"})]


def test_gateway_turns_tool_failure_into_typed_failed_evidence():
    def runner(name, args):
        raise RuntimeError("provider down")

    evidence = AlpacaMcpGateway(runner=runner).collect_context(
        McpContextRequest(
            calls=(McpToolRequest(name="get_option_chain", arguments={"underlying_symbol": "COIN"}),)
        )
    )
    assert evidence.items[0].success is False
    assert evidence.items[0].error_code == "tool_failure"
    assert evidence.complete is False


def test_gateway_rejects_trading_tools_before_runner():
    called = False

    def runner(name, args):
        nonlocal called
        called = True
        return {}

    evidence = AlpacaMcpGateway(runner=runner).collect_context(
        McpContextRequest(calls=(McpToolRequest(name="place_option_order", arguments={}),))
    )
    assert called is False
    assert evidence.items[0].success is False
    assert evidence.items[0].error_code == "tool_not_allowed"


def test_default_mcp_runner_pins_compatible_alpaca_and_fastmcp_versions():
    runner = DefaultAlpacaMcpRunner(api_key="key", secret_key="secret")

    assert runner._command == "uvx"
    assert runner._args == (
        "--with",
        "fastmcp==3.4.7",
        "--from",
        "alpaca-mcp-server==2.2.0",
        "alpaca-mcp-server",
    )
