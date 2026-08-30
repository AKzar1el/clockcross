import json
from pathlib import Path

from clockcross.research.report import write_research_report
from clockcross.research.validation import ResearchVerdict, ValidationResult


def test_write_research_report_emits_json_and_markdown(tmp_path: Path) -> None:
    result = ValidationResult(
        verdict=ResearchVerdict.KILL,
        checks={"multiple_positive_folds": False},
        folds=[],
        selected_configs=[],
        total_signals=0,
        mean_test_return=0.0,
        control_mean_return=None,
        metadata={"config_hash": "abc123"},
    )
    json_path = tmp_path / "verdict.json"
    md_path = tmp_path / "verdict.md"

    write_research_report(result, json_path, md_path)

    payload = json.loads(json_path.read_text())
    assert payload["verdict"] == "KILL"
    assert "# ClockCross Research Verdict" in md_path.read_text()
    assert "abc123" in md_path.read_text()
