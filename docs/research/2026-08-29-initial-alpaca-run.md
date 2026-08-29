# ClockCross Initial Alpaca Run Analysis

Run date: 2026-08-29  
Research window: 2025-01-02 through 2026-08-28  
Historical equity feed: SIP  
Live equity feed design: delayed SIP  
Overall harness verdict: `MUTATE`

## Integrity

Uploaded research ZIP SHA-256:

`6299444d518b592c11a5fb47c5fbd8a9a41e962e39fdce1d6d4646723d2f7a69`

No Alpaca credential markers or obvious key-shaped strings were found in the six uploaded research artifacts before this summary was published.

## What survived

Both COIN and MSTR passed every promotion check except the deliberately severe 100 bps underlying-friction check:

- multiple positive chronological folds: pass
- enough out-of-sample episodes: pass
- positive aggregate signed test return: pass
- not driven by one episode: pass
- QQQ control materially weaker: pass
- 100 bps underlying friction: fail

COIN produced 82 chronological signals with +27.46 bps mean signed test return. MSTR produced 65 signals with +31.40 bps. QQQ control mean was -1.56 bps.

At 25 bps simple underlying friction, both remain slightly positive (+2.46 bps COIN, +6.40 bps MSTR). At 50 bps both become negative. This must not be treated as an options backtest: option-spread economics require their own execution feasibility gate.

## Regime split

The aggregate means conceal material non-stationarity:

- COIN 2025 test episodes: 44 signals, -21.44 bps mean.
- COIN 2026 test episodes: 38 signals, +84.07 bps mean; 4 positive and 2 negative recent folds.
- MSTR 2025 test episodes: 31 signals, +90.75 bps mean; all six signal-bearing folds positive.
- MSTR 2026 test episodes: 34 signals, -22.72 bps mean.

The clean interpretation is not "both tickers have stable alpha." The evidence instead supports a ticker- and regime-specific cross-market response: COIN recently behaves primarily as a continuation candidate, while the historical MSTR reversion effect has weakened or reversed in the current regime.

## Proposed mutation (requires explicit approval before Tasks 6+)

1. Promote **COIN only** to the competition live candidate.
2. Keep MSTR as a negative/rejection research surface rather than forcing a trade.
3. Preserve QQQ as the broad-market falsification control.
4. Freeze the directional family around recent COIN continuation behavior; do not loosen thresholds merely to create more trades.
5. Replace the generic 100 bps underlying-friction promotion question with an **options-aware feasibility gate** before any live order: actual 7-21 DTE chain, bid/ask quality, maximum debit, expected delta exposure, and paper-executable spread structure. The original 100 bps result remains published; it is not erased or reclassified.
6. Keep the deterministic evidence gate and allow the AI only to choose `continuation`, `reversion`, or `abstain` within the approved candidate context.
7. Treat MSTR's current deterioration as public negative evidence in the submission rather than hiding it.

This mutation preserves the original cross-market hypothesis while narrowing the live universe to the part of the hypothesis that is currently supported. It does not weaken chronology, control, or risk rules.

## Why the harness did not return GO

The harness defines `friction_survives` against the strongest configured friction value (100 bps). COIN's +27.46 bps and MSTR's +31.40 bps aggregate underlying moves cannot pass that threshold. The appropriate next question is therefore not whether to waive friction; it is whether recent COIN signals can be expressed economically through a defined-risk option spread using Alpaca's actual option-chain data.
