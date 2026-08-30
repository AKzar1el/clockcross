from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "deploy" / "cloudflare-demo"


def test_demo_uses_workers_static_assets() -> None:
    config = json.loads((DEMO / "wrangler.jsonc").read_text(encoding="utf-8"))
    assert config["name"] == "clockcross-demo"
    assert config["assets"]["directory"] == "./public"
    assert "main" not in config
    assert "site" not in config


def test_demo_exposes_frozen_evidence_and_negative_results() -> None:
    html = (DEMO / "public" / "index.html").read_text(encoding="utf-8")
    required = (
        "MUTATE",
        "82",
        "+27.46 bps",
        "+84.07 bps",
        "-22.72 bps",
        "-1.56 bps",
        "100 bps",
        "416",
        "Level 3",
        "Alpaca MCP",
        "U.S. market is not open; refusing MLeg smoke",
        "09:55 ET",
        "7-21 DTE",
        "1%",
        "5%",
        "continuation",
        "reversion",
        "abstain",
    )
    missing = [item for item in required if item not in html]
    assert not missing, f"judge demo is missing frozen evidence: {missing}"


def test_demo_is_static_read_only_and_contains_no_sensitive_surface() -> None:
    html = (DEMO / "public" / "index.html").read_text(encoding="utf-8")
    css = (DEMO / "public" / "styles.css").read_text(encoding="utf-8")
    combined = f"{html}\n{css}".lower()

    forbidden = (
        "alpaca_api_key",
        "alpaca_secret_key",
        "llm_api_key",
        "account_id",
        "apca-api-key-id",
        "apca-api-secret-key",
        "authorization:",
        "<form",
        "fetch(",
        "xmlhttprequest",
        "/api/",
        "paper-api.alpaca.markets",
    )
    found = [item for item in forbidden if item in combined]
    assert not found, f"judge demo exposes a forbidden surface: {found}"

    assert "<script" not in combined
    assert "contenteditable" not in combined
    assert "<input" not in combined
    assert "<button" not in combined
