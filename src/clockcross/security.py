from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path

_TEXT_SUFFIXES = {"", ".py", ".md", ".json", ".toml", ".yaml", ".yml", ".txt", ".html", ".env", ".example", ".ini", ".cfg", ".sh", ".ps1"}
_SKIP_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
_ASSIGNMENT = re.compile(
    r"(?m)^[ \t]*(ALPACA_API_KEY|ALPACA_SECRET_KEY|LLM_API_KEY)[ \t]*=[ \t]*([^#\r\n]*)$"
)
_OPENAI_STYLE = re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")
_PLACEHOLDERS = {"", "your-key-here", "your-secret-here", "your-api-key", "changeme"}


def _iter_text_files(root: Path) -> Iterator[Path]:
    for path in root.rglob("*"):
        if not path.is_file() or any(part in _SKIP_PARTS for part in path.parts):
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if len(relative.parts) >= 2 and relative.parts[0] == "artifacts" and relative.parts[1] == "raw":
            continue
        if path.suffix.lower() in _TEXT_SUFFIXES:
            yield path


def scan_text_tree(root: str | Path) -> list[str]:
    """Return human-readable findings for obvious committed credential material."""
    root = Path(root)
    findings: list[str] = []
    active_values = {
        value
        for name in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "LLM_API_KEY")
        if (value := os.getenv(name)) and len(value) >= 8
    }
    for path in _iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        relative = path.relative_to(root).as_posix()
        for match in _ASSIGNMENT.finditer(text):
            value = match.group(2).strip().strip('"\'')
            if value.lower() in _PLACEHOLDERS or value.startswith("${"):
                continue
            findings.append(f"{relative}: non-placeholder {match.group(1)} assignment")
        if _OPENAI_STYLE.search(text):
            findings.append(f"{relative}: OpenAI-style secret-shaped token")
        for value in active_values:
            if value in text:
                findings.append(f"{relative}: active environment credential value")
    return sorted(set(findings))
