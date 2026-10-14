from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from capybucks_mcp import __version__
from capybucks_mcp.server import build_server

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = Path(__file__).parent / "snapshots" / "tools.json"


def _tool_payload(tools: object) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for tool in tools:  # type: ignore[attr-defined]
        dumped = tool.model_dump(mode="json", by_alias=True, exclude_none=True)
        rows.append(
            {
                "name": dumped["name"],
                "title": dumped.get("title"),
                "description": dumped.get("description"),
                "inputSchema": dumped.get("inputSchema"),
                "annotations": dumped.get("annotations"),
            }
        )
    return rows


@pytest.mark.asyncio
async def test_tools_snapshot() -> None:
    server = build_server()
    listed = await server.list_tools()
    payload = _tool_payload(listed)
    actual = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if os.environ.get("UPDATE_SNAPSHOT") == "1":
        SNAPSHOT.write_text(actual, encoding="utf-8")
    assert SNAPSHOT.read_text(encoding="utf-8") == actual
    names = [row["name"] for row in payload]
    assert names == [
        "list_providers",
        "get_history",
        "get_quote",
        "get_financials",
        "get_dividends_and_splits",
        "get_option_expirations",
        "get_option_chain",
        "get_news",
        "compute_indicators",
        "check_trading_day",
    ]
    for row in payload:
        annotations = row["annotations"]
        assert isinstance(annotations, dict)
        assert annotations["readOnlyHint"] is True
        assert annotations["destructiveHint"] is False
        assert annotations["idempotentHint"] is True
        assert annotations["openWorldHint"] is True


def test_version_flag_does_not_start_the_server() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "capybucks_mcp", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == __version__
    assert "jsonrpc" not in completed.stdout


@pytest.mark.asyncio
async def test_stdio_protocol_and_secret_leak(tmp_path: Path) -> None:
    secret = "sk-test-123"
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "capybucks_mcp"],
        env={
            "CAPYBUCKS_MCP_TEST_MEMORY": "1",
            "CAPYBUCKS_NO_RATELIMIT": "1",
            "CAPYBUCKS_CACHE_DIR": str(tmp_path / "cache"),
            "CAPYBUCKS_MCP_LOG_LEVEL": "WARNING",
            "CAPYBUCKS_TWELVEDATA_KEY": secret,
        },
        cwd=ROOT,
    )
    err_path = tmp_path / "stderr.txt"
    texts: list[str] = []
    with err_path.open("w", encoding="utf-8") as errlog:
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                assert len(listed.tools) == 10
                for tool in listed.tools:
                    assert tool.annotations is not None
                    assert tool.annotations.read_only_hint is True
                history = await session.call_tool(
                    "get_history",
                    {"symbols": "AAPL", "start": "2024-01-01", "end": "2024-01-05"},
                )
                missing = await session.call_tool("get_history", {"symbols": "NOPE"})
                quote = await session.call_tool("get_quote", {"symbol": "MSFT"})
                providers = await session.call_tool("list_providers", {})
                for result in (history, missing, quote, providers):
                    assert result.content
                    text = result.content[0].text
                    assert isinstance(text, str)
                    texts.append(text)
                    parsed = json.loads(text)
                    assert "notice" in parsed
                    encoded = text.encode("utf-8")
                    assert len(encoded) < 60 * 1024
                    assert secret not in text
                assert history.is_error is False
                assert missing.is_error is True
                body = json.loads(texts[0])
                assert body["ok"] is True
                assert body["provenance"]["provider"] == "memory"
                assert json.loads(texts[1])["error"]["code"] == "symbol_not_found"
    stderr = err_path.read_text(encoding="utf-8")
    assert secret not in stderr
    assert secret not in "\n".join(texts)
