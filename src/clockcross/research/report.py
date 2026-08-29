from __future__ import annotations

import json
from pathlib import Path

from clockcross.research.validation import ValidationResult


def write_research_report(result: ValidationResult, path_json: Path, path_md: Path) -> None:
    path_json.parent.mkdir(parents=True, exist_ok=True)
    path_md.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    path_json.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")

    lines = [
        "# ClockCross Research Verdict",
        "",
        f"**Verdict:** `{result.verdict.value}`",
        f"**Configuration hash:** `{result.metadata.get('config_hash', 'unknown')}`",
        f"**Chronological test signals:** {result.total_signals}",
        f"**Mean signed test return:** {result.mean_test_return:.6f}",
    ]
    if result.control_mean_return is not None:
        lines.append(f"**Control mean signed return:** {result.control_mean_return:.6f}")
    lines.extend(["", "## Promotion checks", ""])
    for name, passed in result.checks.items():
        lines.append(f"- [{'x' if passed else ' '}] `{name}`")
    lines.extend(["", "## Fold results", ""])
    for fold in result.folds:
        lines.append(
            "- "
            f"{fold.test_start.isoformat()} to {fold.test_end.isoformat()}: "
            f"n={fold.signal_count}, mean={fold.mean_return:.6f}, "
            f"median={fold.median_return:.6f}, hit={fold.hit_rate:.2%}, "
            f"{fold.selected_config.thesis}/{fold.selected_config.normalization}/"
            f"{fold.selected_config.threshold}/{fold.selected_config.horizon}"
        )
    path_md.write_text("\n".join(lines) + "\n")
