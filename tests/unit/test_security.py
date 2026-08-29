from pathlib import Path

from clockcross.security import scan_text_tree


def test_secret_scanner_flags_real_secret_assignments_but_allows_placeholders(tmp_path):
    (tmp_path / ".env.example").write_text("ALPACA_SECRET_KEY=your-secret-here\nLLM_API_KEY=\n")
    (tmp_path / "bad.env").write_text("ALPACA_SECRET_KEY=" + ("abc123" * 6) + "\n")
    findings = scan_text_tree(tmp_path)
    assert any("bad.env" in finding for finding in findings)
    assert not any(".env.example" in finding for finding in findings)


def test_secret_scanner_flags_openai_style_keys(tmp_path):
    (tmp_path / "oops.txt").write_text("token=" + "sk-" + ("abc123" * 6) + "\n")
    assert scan_text_tree(tmp_path)


def test_repository_tree_contains_no_obvious_secrets():
    root = Path(__file__).resolve().parents[2]
    assert scan_text_tree(root) == []
