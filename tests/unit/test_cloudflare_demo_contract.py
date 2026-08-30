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


def test_hero_visual_field_is_full_bleed_with_constrained_inner_content() -> None:
    html = (DEMO / "public" / "index.html").read_text(encoding="utf-8")
    css = (DEMO / "public" / "styles.css").read_text(encoding="utf-8")

    assert '<header class="hero">' in html
    assert 'class="hero-inner shell"' in html
    assert 'class="hero shell"' not in html
    assert ".hero-inner" in css


def test_demo_wires_complete_brand_and_social_asset_set() -> None:
    public = DEMO / "public"
    html = (public / "index.html").read_text(encoding="utf-8")
    manifest = json.loads((public / "site.webmanifest").read_text(encoding="utf-8"))

    required_files = (
        "logo-mark.svg",
        "logo-wordmark.svg",
        "favicon.svg",
        "favicon.ico",
        "apple-touch-icon.png",
        "icon-192.png",
        "icon-512.png",
        "og-image.png",
        "hackathon-cover.png",
        "site.webmanifest",
    )
    missing = [name for name in required_files if not (public / name).is_file()]
    assert not missing, f"judge demo is missing brand assets: {missing}"

    required_head_fragments = (
        'rel="icon" href="/favicon.svg" type="image/svg+xml"',
        'rel="icon" href="/favicon.ico" sizes="any"',
        'rel="apple-touch-icon" href="/apple-touch-icon.png"',
        'rel="manifest" href="/site.webmanifest"',
        'property="og:image" content="https://clockcross-demo.tomi-seregi99.workers.dev/og-image.png"',
        'name="twitter:card" content="summary_large_image"',
        'name="twitter:image" content="https://clockcross-demo.tomi-seregi99.workers.dev/og-image.png"',
    )
    absent = [fragment for fragment in required_head_fragments if fragment not in html]
    assert not absent, f"judge demo is missing brand metadata: {absent}"

    assert manifest["name"] == "ClockCross"
    assert manifest["short_name"] == "ClockCross"
    assert manifest["display"] == "standalone"
    assert {icon["src"] for icon in manifest["icons"]} == {"/icon-192.png", "/icon-512.png"}


def test_raster_brand_assets_have_expected_file_signatures() -> None:
    public = DEMO / "public"
    for name in ("apple-touch-icon.png", "icon-192.png", "icon-512.png", "og-image.png", "hackathon-cover.png"):
        assert (public / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), name

    assert (public / "favicon.ico").read_bytes()[:4] == b"\x00\x00\x01\x00"
