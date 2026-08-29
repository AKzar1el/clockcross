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


def test_build_episode_family_materializes_all_planned_beta_lookbacks(monkeypatch) -> None:
    calls: list[int] = []

    def fake_build(btc, equity, *, sessions, beta_lookback):
        calls.append(beta_lookback)
        return {"lookback": beta_lookback}

    monkeypatch.setattr(cli, "build_episode_frame", fake_build)
    family = cli._build_episode_family(object(), object(), [], (10, 20, 40))

    assert calls == [10, 20, 40]
    assert set(family) == {10, 20, 40}


def test_overall_go_requires_both_crypto_sensitive_tickers_to_go() -> None:
    from clockcross.research.validation import ResearchVerdict

    assert cli._aggregate_symbol_verdicts(
        {"COIN": ResearchVerdict.GO, "MSTR": ResearchVerdict.GO}
    ) is ResearchVerdict.GO
    assert cli._aggregate_symbol_verdicts(
        {"COIN": ResearchVerdict.GO, "MSTR": ResearchVerdict.KILL}
    ) is ResearchVerdict.MUTATE
    assert cli._aggregate_symbol_verdicts(
        {"COIN": ResearchVerdict.KILL, "MSTR": ResearchVerdict.KILL}
    ) is ResearchVerdict.KILL


def test_research_capacity_requires_one_complete_train_and_test_fold() -> None:
    from clockcross.research.validation import EvaluationConfig

    config = EvaluationConfig(min_train=60, test_size=20)
    assert cli._has_enough_history(79, config) is False
    assert cli._has_enough_history(80, config) is True
