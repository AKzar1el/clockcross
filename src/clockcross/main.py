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


def _utc_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def _utc_end(day: date) -> datetime:
    return datetime.combine(day, time.max, tzinfo=timezone.utc)


def _business_dates(start: date, end: date) -> list[date]:
    return [ts.date() for ts in pd.date_range(start=start, end=end, freq="B")]


def _promotion_signal_floor(valid_sessions: int) -> tuple[int, str]:
    floor = max(8, int(round(valid_sessions * 0.10)))
    return floor, f"max(8, round(10% of {valid_sessions} valid sessions))"


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
        crypto_fetcher=lambda symbol, begin, finish: rest.fetch_crypto_bars(symbol, begin, finish),
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
    episode_frames = {
        symbol: build_episode_frame(btc, frame, sessions=sessions, beta_lookback=20)
        for symbol, frame in stock_frames.items()
    }

    valid_capacity = min(len(episode_frames["COIN"]), len(episode_frames["MSTR"]))
    min_signals, rationale = _promotion_signal_floor(valid_capacity)
    config = EvaluationConfig(min_total_signals=min_signals)

    qqq = episode_frames["QQQ"]
    results = {
        symbol: evaluate_residual_strategy(frame, config, control_frame=qqq)
        for symbol, frame in episode_frames.items()
        if symbol in {"COIN", "MSTR"}
    }

    verdicts = {result.verdict for result in results.values()}
    if ResearchVerdict.GO in verdicts:
        overall = ResearchVerdict.GO
    elif ResearchVerdict.MUTATE in verdicts:
        overall = ResearchVerdict.MUTATE
    else:
        overall = ResearchVerdict.KILL

    output_dir.mkdir(parents=True, exist_ok=True)
    for symbol, result in results.items():
        write_research_report(
            result,
            output_dir / f"{symbol.lower()}-verdict.json",
            output_dir / f"{symbol.lower()}-verdict.md",
        )

    overall_payload = {
        "verdict": overall.value,
        "coverage": {symbol: int(len(frame)) for symbol, frame in episode_frames.items()},
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
    lines.extend(f"- {symbol}: {len(frame)} valid episodes" for symbol, frame in episode_frames.items())
    lines.extend(["", "## Symbol verdicts", ""])
    lines.extend(f"- {symbol}: `{result.verdict.value}`" for symbol, result in results.items())
    (output_dir / "initial-verdict.md").write_text("\n".join(lines) + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clockcross")
    subparsers = parser.add_subparsers(dest="command", required=True)
    research = subparsers.add_parser("research")
    research.add_argument("--start", required=True, type=date.fromisoformat)
    research.add_argument("--end", required=True, type=date.fromisoformat)
    research.add_argument("--output-dir", type=Path, default=Path("artifacts/research"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "research":
        return run_research_from_api(args.start, args.end, args.output_dir)
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
