from __future__ import annotations

import argparse
import json
from pathlib import Path

from featherless_phase2.experiment import run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/research/featherless-phase2-live-2026-09-04.json"),
    )
    args = parser.parse_args()
    try:
        result = run(args.output)
    except Exception as exc:
        print(f"phase2 research failed: {type(exc).__name__}: {exc}")
        return 1
    print(
        json.dumps(
            {
                "conclusion": result["conclusion"],
                "accounted_spend_usd": result["budget"]["accounted_spend_usd"],
                "winner_before_holdout": result.get("selection", {}).get(
                    "winner_before_holdout"
                ),
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
