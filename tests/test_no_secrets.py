from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_ASSIGNMENT = re.compile(
    r"(?m)^[ \t]*(ALPACA_API_KEY|ALPACA_SECRET_KEY|LLM_API_KEY)[ \t]*=[ \t]*([^#\r\n]*)$"
)
_OPENAI_KEY = re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")
_ALPACA_HEADER_LITERAL = re.compile(
    r'''(?i)["']APCA-API-(?:KEY-ID|SECRET-KEY)["']\s*:\s*["']([A-Za-z0-9_-]{16,})["']'''
)
_ALLOWED_VALUES = {
    "your-key-here",
    "your-secret-here",
    "your-model-key-here",
}
_TEXT_SUFFIXES = {
    ".cfg",
    ".html",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def _tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item for item in result.stdout.decode().split("\0") if item]


def _is_placeholder(value: str) -> bool:
    clean = value.strip().strip('"\'')
    return (
        clean in _ALLOWED_VALUES
        or clean == ""
        or (clean.startswith("${") and clean.endswith("}"))
        or (clean.startswith("<") and clean.endswith(">"))
        or clean.startswith("your-")
    )


def test_no_secret_bearing_artifacts_are_tracked() -> None:
    bad: list[str] = []
    for path in _tracked_files():
        relative = path.relative_to(ROOT)
        posix = relative.as_posix()
        if path.name == ".env" or path.suffix.lower() in {".key", ".pem"}:
            bad.append(posix)
        if posix.startswith("artifacts/raw/"):
            bad.append(posix)
    assert not bad, f"secret-bearing artifacts must not be tracked: {bad}"


def test_tracked_text_files_contain_no_literal_credentials() -> None:
    findings: list[str] = []
    for path in _tracked_files():
        if path.suffix.lower() not in _TEXT_SUFFIXES and path.name != ".env.example":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        relative = path.relative_to(ROOT).as_posix()
        for match in _ASSIGNMENT.finditer(text):
            if not _is_placeholder(match.group(2)):
                findings.append(f"{relative}: literal {match.group(1)} assignment")
        if _OPENAI_KEY.search(text):
            findings.append(f"{relative}: OpenAI-style key literal")
        if _ALPACA_HEADER_LITERAL.search(text):
            findings.append(f"{relative}: literal Alpaca auth-header value")

    assert not findings, "credential-like literals found:\n" + "\n".join(findings)
