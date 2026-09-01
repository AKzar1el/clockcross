# 2026-09-01 — Frozen COIN exit-horizon sensitivity

## Decision

**Keep the 60-minute research horizon and the deterministic 10:55 ET exit unchanged.**

No tested alternative satisfied the predeclared promotion criteria. The corrected study uses only episodes with the full 40 prior sessions required by the live beta-40 policy.

This is a sensitivity study of the COIN underlying return. It is not an options-spread backtest and is not sufficient by itself to change the live options exit policy.

## What was frozen before evaluation

The comparison changed only the exit horizon. It kept the approved live research family fixed:

- underlying: COIN;
- beta lookback: 40 prior sessions;
- normalization: raw residual;
- signal threshold: 1%;
- research direction: continuation;
- decision timestamp: 09:55 ET;
- incumbent horizon: 60 minutes.

The predeclared comparison grid was 15, 30, 45, 60, 90, and 120 minutes after 09:55 ET.

A challenger could replace 60 minutes only if, on one common complete episode sample, it had all of the following:

1. positive paired mean improvement over 60 minutes;
2. a positive 95% paired-bootstrap lower bound;
3. positive leave-one-out minimum paired improvement;
4. median return not worse;
5. hit rate not worse;
6. no worse calendar-year regime.

September 1 was excluded from promotion decisions and inspected only afterward as an external sanity check.

## Methodology correction before acceptance

The first diagnostic run was **invalidated before being accepted** because the generic episode builder allowed early beta-40 rows to be computed from fewer than 40 prior sessions. The live signal gateway does not: it refuses to produce a feature until 40 prior sessions exist.

The corrected study therefore:

- records `training_count` for every research episode;
- requires `training_count >= 40`;
- fetches prehistory beginning 2024-10-01;
- evaluates promotion only over the original 2025-01-02 through 2026-08-28 research window;
- uses a common complete sample across every tested horizon.

The first 116-episode diagnostic is not evidence for policy selection and must not be cited as the accepted result.

## Corrected result

The corrected common sample contains **117 frozen-policy signal episodes**. The latest eligible signal in the common sample is 2026-08-24; the research collection boundary remains 2026-08-28.

| Horizon | Mean signed return | Median | Hit rate | Paired mean vs 60m | Promotion eligible |
| ---: | ---: | ---: | ---: | ---: | :---: |
| 15m | +6.42 bps | +10.40 bps | 53.85% | -35.97 bps | No |
| 30m | +19.41 bps | +15.63 bps | 57.26% | -22.98 bps | No |
| 45m | +27.84 bps | +34.88 bps | 58.97% | -14.55 bps | No |
| **60m** | **+42.39 bps** | **+47.44 bps** | **58.12%** | **baseline** | **Keep** |
| 90m | +27.64 bps | +38.52 bps | 55.56% | -14.74 bps | No |
| 120m | +31.95 bps | +50.83 bps | 54.70% | -10.43 bps | No |

Every challenger had a negative paired mean improvement versus the 60-minute incumbent. None satisfied the predeclared robustness gates.

The 30-minute alternative, despite a superficially reasonable hit rate, had a paired-bootstrap interval entirely below zero versus 60 minutes. The 45-, 90-, and 120-minute intervals crossed zero but had negative paired means and failed additional robustness criteria. The 15-minute alternative was clearly inferior on both central tendency and robustness.

## September 1 external sanity check

September 1 was not part of the promotion sample. Its beta computation used the full 40-session history.

The frozen residual was negative, while the AI chose `reversion`, making the live directional view bullish. From the 09:55 decision price, COIN's underlying return was approximately:

| Horizon | Bullish / reversion signed return |
| ---: | ---: |
| 15m | +1.0323% |
| 30m | +1.1211% |
| 45m | +1.0795% |
| 60m | +0.9796% |
| 90m | +0.0555% |
| 120m | +0.1082% |

The underlying was still materially positive at the frozen 60-minute exit. This is consistent with the Sep 1 postmortem: the observed loss was not evidence that the 60-minute horizon killed a correct directional call; the weak old vertical expression was the structural issue exposed by that episode.

## Scope and limitation

ClockCross selects live option structures from Alpaca option snapshots, while the historical study above evaluates the COIN underlying. Historical options data does not reproduce the exact live constructor state, including the same point-in-time snapshot Greeks and execution information available to the live selection path. The Basic option feed is also `indicative`, not paid OPRA.

Therefore:

- this study is strong evidence **against changing the 60-minute research horizon**;
- it is not an options P&L backtest;
- it does not justify changing quantity, DTE, signal threshold, AI authority, or risk limits;
- the 10:55 ET deterministic exit remains frozen.

Machine-readable corrected evidence is preserved in `artifacts/research/exit-horizon-sensitivity-2026-09-01.json`.
