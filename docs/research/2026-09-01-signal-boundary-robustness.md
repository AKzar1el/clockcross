# 2026-09-01 — Frozen 1% signal-boundary robustness

## Decision

**Keep the frozen 1.00% raw COIN residual threshold unchanged.**

The threshold is not a local knife edge under the predeclared ±10% perturbation test. Both immediate neighbors retain positive mean and median signed returns, hit rates above 50%, sufficient sample size, and more than half of the 1.00% baseline mean return.

This study is explicitly **not** a retrospective threshold optimization. The fact that 1.10% has the highest mean on this same sample does not authorize changing the live gate. Further threshold sweeping after observing these results would increase data-snooping risk rather than improve evidence quality.

## What was frozen before evaluation

The comparison changed only the residual gate. It kept:

- COIN only;
- full 40-session beta history;
- raw residual;
- continuation direction for the retrospective research comparison;
- exact 60-minute 09:55 → 10:55 ET underlying return;
- research collection window 2025-01-02 through 2026-08-28;
- September 1 excluded from boundary assessment.

The predeclared threshold grid was:

- 0.80%
- 0.90%
- **1.00% incumbent**
- 1.10%
- 1.20%

Only the immediate 0.90% and 1.10% neighbors determined local robustness. Each needed at least 20 signals, positive mean, positive median, hit rate at least 50%, and mean return at least half of the 1.00% baseline mean. The 0.80% and 1.20% points were descriptive stress only.

## Result

The full-history research frame contained 341 eligible beta-40 episodes before thresholding.

| Residual gate | Signals | Mean signed 60m return | Median | Hit rate | Interpretation |
| ---: | ---: | ---: | ---: | ---: | --- |
| 0.80% | 158 | +24.80 bps | +32.01 bps | 55.06% | descriptive |
| **0.90%** | **133** | **+32.35 bps** | **+35.76 bps** | **55.64%** | local gate passes |
| **1.00%** | **117** | **+42.39 bps** | **+47.44 bps** | **58.12%** | frozen incumbent |
| **1.10%** | **106** | **+48.16 bps** | **+53.29 bps** | **58.49%** | local gate passes |
| 1.20% | 91 | +38.76 bps | +47.44 bps | 56.04% | descriptive |

Both local neighbors also remained positive in each calendar-year regime represented in the sample.

### 2025

- 0.90%: +32.24 bps mean, 52.70% hit rate
- 1.00%: +38.18 bps mean, 54.41% hit rate
- 1.10%: +35.86 bps mean, 53.23% hit rate

### 2026

- 0.90%: +32.49 bps mean, 59.32% hit rate
- 1.00%: +48.22 bps mean, 63.27% hit rate
- 1.10%: +65.49 bps mean, 65.91% hit rate

The predeclared local robustness result is therefore **PASS**, with no warnings.

## Marginal-shell evidence

The episodes immediately around the 1% boundary are weaker than the higher-residual population:

| Residual shell | Episodes | Mean signed return | Median | Hit rate |
| --- | ---: | ---: | ---: | ---: |
| 0.90–1.00% | 16 | **-41.03 bps** | -78.70 bps | 37.50% |
| 1.00–1.10% | 11 | **-13.26 bps** | +30.44 bps | 54.55% |

This is useful negative evidence. It indicates that the strongest residuals contribute disproportionately to the aggregate effect and that lowering the gate indiscriminately adds weak observations.

It still does **not** justify raising the live gate to 1.10% after seeing the same historical sample. The 1.20% aggregate mean falls back to +38.76 bps, so the retrospective relationship is not a monotonic instruction to keep increasing the threshold. Choosing the best threshold from this grid now would be exactly the type of post-hoc tuning ClockCross is intended to avoid.

## September 1 external check

September 1 was excluded from the threshold assessment. Its full-beta40 absolute residual was approximately **1.7118%**, so it passes every tested gate from 0.80% through 1.20%.

Therefore none of these nearby threshold choices would have prevented or materially changed the Sep 1 competition episode. This reinforces the earlier diagnosis that Sep 1 exposed the old spread-expression weakness rather than a residual-threshold failure.

## Final interpretation

The evidence supports three conclusions:

1. the 1.00% gate is **not locally fragile** under a ±10% boundary perturbation;
2. sub-1% marginal signals are materially weaker, so loosening the gate to manufacture more trades is not justified;
3. retrospectively moving the gate upward because 1.10% happens to have the highest mean on this sample would be data snooping, not a clean promotion decision.

**Live threshold remains 1.00%. No further threshold search is recommended before new prospective competition evidence exists.**

This is an underlying-return robustness study rather than an options-spread P&L backtest. Machine-readable evidence is preserved in `artifacts/research/signal-boundary-robustness-2026-09-01.json`.
