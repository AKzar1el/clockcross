from pathlib import Path

from clockcross import main as cli


def test_research_cli_writes_verdict_artifacts(monkeypatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    def fake_run(start, end, output_dir):
        called.update(start=start, end=end, output_dir=output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "verdict.json").write_text('{"verdict":"KILL"}\n')
        return 0

    monkeypatch.setattr(cli, "run_research_from_api", fake_run)
    exit_code = cli.main(
        [
            "research",
            "--start",
            "2025-01-01",
            "--end",
            "2026-08-28",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert (tmp_path / "verdict.json").exists()
    assert str(called["start"]) == "2025-01-01"
