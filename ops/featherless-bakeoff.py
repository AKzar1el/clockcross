from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from featherless_bakeoff.experiment import run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/research/featherless-bakeoff-live-2026-09-03.json"),
    )
    args = parser.parse_args()
    try:
        result = run(args.output)
    except Exception as exc:
        print(f"featherless bakeoff failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "conclusion": result["conclusion"],
                "actual_accounted_spend_usd": result["budget"]["actual_accounted_spend_usd"],
                "eligible_candidates_before_holdout": result["eligible_candidates_before_holdout"],
                "holdout": result["holdout"],
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
