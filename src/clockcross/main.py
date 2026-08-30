from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Sequence

import pandas as pd

from clockcross.alpaca.historical import (
    AlpacaRestHistoryClient,
    HistoricalDataGateway,
)
from clockcross.config import Settings
from clockcross.research.episodes import build_episode_frame
from clockcross.research.report import write_research_report
from clockcross.research.validation import (
    EvaluationConfig,
    ResearchVerdict,
    evaluate_residual_strategy,
)
from clockcross.runtime_cli import execute_runtime_command, register_runtime_subcommands


def _utc_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def _utc_end(day: date) -> datetime:
    return datetime.combine(day, time.max, tzinfo=timezone.utc)


def _business_dates(start: date, end: date) -> list[date]:
    return [ts.date() for ts in pd.date_range(start=start, end=end, freq="B")]


def _promotion_signal_floor(valid_sessions: int) -> tuple[int, str]:
    # Chosen only after coverage is measured. Ten percent of the valid sample,
    # with a small anti-anecdote floor, is explicit and recorded in the artifact.
    floor = max(8, int(round(valid_sessions * 0.10)))
    return floor, f"max(8, round(10% of {valid_sessions} valid sessions))"


def _build_episode_family(
    btc: pd.DataFrame,
    equity: pd.DataFrame,
    sessions: Sequence[date],
    lookbacks: tuple[int, ...],
) -> dict[int, pd.DataFrame]:
    return {
        lookback: build_episode_frame(
            btc,
            equity,
            sessions=sessions,
            beta_lookback=lookback,
        )
        for lookback in lookbacks
    }


def _aggregate_symbol_verdicts(verdicts: dict[str, ResearchVerdict]) -> ResearchVerdict:
    required = {"COIN", "MSTR"}
    if set(verdicts) != required:
        return ResearchVerdict.KILL
    values = [verdicts[symbol] for symbol in sorted(required)]
    if all(value is ResearchVerdict.GO for value in values):
        return ResearchVerdict.GO
    if all(value is ResearchVerdict.KILL for value in values):
        return ResearchVerdict.KILL
    return ResearchVerdict.MUTATE


def _family_valid_capacity(family: dict[int, pd.DataFrame]) -> int:
    return min(int(frame["residual"].notna().sum()) for frame in family.values())


def _has_enough_history(valid_sessions: int, config: EvaluationConfig) -> bool:
    return valid_sessions >= config.min_train + config.test_size


def _write_insufficient_history(
    output_dir: Path,
    *,
    coverage: dict[str, dict[int, int]],
    required_sessions: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "verdict": ResearchVerdict.MUTATE.value,
        "reason": "insufficient_history",
        "required_common_sessions": required_sessions,
        "coverage": {
            symbol: {str(lookback): count for lookback, count in family.items()}
            for symbol, family in coverage.items()
        },
    }
    (output_dir / "verdict.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )
    (output_dir / "initial-verdict.md").write_text(
        "# ClockCross Initial Research Verdict\n\n"
        "**Overall verdict:** `MUTATE`\n\n"
        "The available synchronized history cannot form one complete chronological "
        f"train/test fold. Required common sessions: {required_sessions}.\n"
    )


def run_research_from_api(start: date, end: date, output_dir: Path) -> int:
    settings = Settings()
    rest = AlpacaRestHistoryClient(
        settings.alpaca_api_key,
        settings.alpaca_secret_key,
        base_url=str(settings.alpaca_data_base_url),
    )
    gateway = HistoricalDataGateway(
        stock_fetcher=lambda symbol, begin, finish: rest.fetch_stock_bars(
            symbol,
            begin,
            finish,
            feed=settings.historical_stock_feed,
        ),
        crypto_fetcher=lambda symbol, begin, finish: rest.fetch_crypto_bars(
            symbol,
            begin,
            finish,
        ),
        cache_root=settings.artifacts_dir,
        stock_feed=settings.historical_stock_feed,
    )

    begin = _utc_start(start)
    finish = _utc_end(end)
    btc = gateway.fetch_crypto_minutes("BTC/USD", begin, finish)
    stock_frames = {
        symbol: gateway.fetch_stock_minutes(symbol, begin, finish)
        for symbol in ("COIN", "MSTR", "QQQ")
    }
    sessions = _business_dates(start, end)
    lookbacks = EvaluationConfig().beta_lookbacks
    episode_frames = {
        symbol: _build_episode_family(btc, frame, sessions, lookbacks)
        for symbol, frame in stock_frames.items()
    }

    base_config = EvaluationConfig()
    coverage = {
        symbol: {
            lookback: int(frame["residual"].notna().sum())
            for lookback, frame in family.items()
        }
        for symbol, family in episode_frames.items()
    }
    valid_capacity = min(
        _family_valid_capacity(episode_frames["COIN"]),
        _family_valid_capacity(episode_frames["MSTR"]),
        _family_valid_capacity(episode_frames["QQQ"]),
    )
    if not _has_enough_history(valid_capacity, base_config):
        _write_insufficient_history(
            output_dir,
            coverage=coverage,
            required_sessions=base_config.min_train + base_config.test_size,
        )
        return 2

    min_signals, rationale = _promotion_signal_floor(valid_capacity)
    config = EvaluationConfig(min_total_signals=min_signals)

    qqq = episode_frames["QQQ"]
    results = {
        symbol: evaluate_residual_strategy(family, config, control_frame=qqq)
        for symbol, family in episode_frames.items()
        if symbol in {"COIN", "MSTR"}
    }

    overall = _aggregate_symbol_verdicts(
        {symbol: result.verdict for symbol, result in results.items()}
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    for symbol, result in results.items():
        write_research_report(
            result,
            output_dir / f"{symbol.lower()}-verdict.json",
            output_dir / f"{symbol.lower()}-verdict.md",
        )

    overall_payload = {
        "verdict": overall.value,
        "coverage": {
            symbol: {str(lookback): count for lookback, count in family.items()}
            for symbol, family in coverage.items()
        },
        "min_total_signals": min_signals,
        "min_total_signals_rationale": rationale,
        "historical_stock_feed": settings.historical_stock_feed,
        "live_stock_feed": settings.live_stock_feed,
        "feature_freeze_et": settings.feature_freeze_time.isoformat(),
        "confirmation_end_et": settings.confirmation_end_time.isoformat(),
        "decision_time_et": settings.decision_time.isoformat(),
        "symbols": {symbol: result.to_dict() for symbol, result in results.items()},
    }
    (output_dir / "verdict.json").write_text(
        json.dumps(overall_payload, indent=2, sort_keys=True, default=str) + "\n"
    )
    lines = [
        "# ClockCross Initial Research Verdict",
        "",
        f"**Overall verdict:** `{overall.value}`",
        f"**Historical equity feed:** `{settings.historical_stock_feed}`",
        f"**Live equity feed:** `{settings.live_stock_feed}`",
        f"**Promotion sample floor:** `{min_signals}` ({rationale})",
        "",
        "## Coverage",
        "",
    ]
    for symbol, family in episode_frames.items():
        coverage_text = ", ".join(
            f"beta{lookback}={int(frame['residual'].notna().sum())}"
            for lookback, frame in sorted(family.items())
        )
        lines.append(f"- {symbol}: {coverage_text}")
    lines.extend(["", "## Symbol verdicts", ""])
    lines.extend(
        f"- {symbol}: `{result.verdict.value}`"
        for symbol, result in results.items()
    )
    (output_dir / "initial-verdict.md").write_text("\n".join(lines) + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clockcross")
    subparsers = parser.add_subparsers(dest="command", required=True)
    research = subparsers.add_parser("research")
    research.add_argument("--start", required=True, type=date.fromisoformat)
    research.add_argument("--end", required=True, type=date.fromisoformat)
    research.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/research"),
    )
    register_runtime_subcommands(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "research":
        return run_research_from_api(args.start, args.end, args.output_dir)
    runtime_rc = execute_runtime_command(args)
    if runtime_rc is not None:
        return runtime_rc
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
