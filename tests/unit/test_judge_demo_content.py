from pathlib import Path


DEMO = Path("deploy/cloudflare-demo/public/index.html")
SUBMISSION = Path("docs/SUBMISSION_PACKAGE.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_judge_demo_reports_verified_competition_lifecycle() -> None:
    html = _text(DEMO)

    assert "Competition status</span><strong>Episode verified</strong>" in html
    assert "2026-09-01" in html
    assert "terminal state <strong>CLOSED</strong>" in html
    assert "Competition account not started" not in html
    assert "Competition status</span><strong>Not started</strong>" not in html


def test_judge_demo_exposes_six_month_replay_and_constructor_fix() -> None:
    html = _text(DEMO)

    assert "36 AI trades" in html
    assert "3 AI abstentions" in html
    assert "21-15" in html
    assert "58.3%" in html
    assert "+50.7 bps" in html
    assert "June: -38.3 bps" in html
    assert "July: -57.1 bps" in html
    assert "0.10 short-delta floor" in html
    assert "29.4 points" in html


def test_judge_links_and_submission_copy_point_to_main() -> None:
    html = _text(DEMO)
    submission = _text(SUBMISSION)

    assert "blob/feat/clockcross-core" not in html
    assert "blob/main/docs/ONE_PAGE_WRITEUP.md" in html
    assert "blob/main/docs/research/2026-09-01-end-to-end-backtest.md" in html
    assert "six-month" in submission.lower()
    assert "0.10" in submission
