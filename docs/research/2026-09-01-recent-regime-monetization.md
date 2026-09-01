# Recent-Regime Monetization Pass — 2026-09-01

## Scope

This pass was intentionally restricted to the most recent market regime: the prior trading week (2026-08-24 through 2026-08-28) plus 2026-08-31 and 2026-09-01.

The objective was **not** to make those dates profitable retrospectively. The objective was to look for an execution or option-expression improvement that could have helped the recent dates **without degrading the broader six-month evidence or undoing the previously accepted constructor hardening**.

No production policy was changed during this pass.

## Recent-window reality

Under the frozen 1.00% residual gate, only two dates in the requested window were signal dates:

- 2026-08-24;
- 2026-09-01.

2026-08-25 through 2026-08-28 and 2026-08-31 were threshold/no-signal dates. Creating trades on those dates would require weakening or changing the signal gate. The existing boundary study already found the 0.90%-1.00% shell materially poor, so no lower-threshold experiment was promoted.

Both recent signal dates were **directionally correct AI reversions** in the existing chronological replay. Therefore this pass did not reopen the signal direction, model, prompt, residual threshold, or the 60-minute research horizon.

## September 1 exact competition economics

A read-only Alpaca order query recovered the actual parent and leg fills for the first competition episode.

Opening vertical:

- long: `COIN260918C00180000`;
- short: `COIN260918C00192500`;
- submitted parent limit: **$5.23 debit**;
- actual parent fill: **$5.05 debit**;
- long fill: **$10.65**;
- short fill: **$5.60**.

Closing vertical:

- submitted parent minimum credit: **$4.55**;
- actual parent fill: **$4.70 credit**;
- long close: **$11.00**;
- short close: **$6.30**.

Approximate one-contract realized spread economics before any external fees:

`($4.70 - $5.05) × 100 = -$35`

This is materially better than the `-$68` implied by comparing the persisted submitted limits. Alpaca supplied about **$33 of aggregate price improvement** versus those limits, so poor limit execution is not supported as the primary loss mechanism.

The long call itself improved by $0.35 while the short call became $0.70 more expensive to buy back. The vertical therefore lost despite the correct bullish COIN move. This reinforces the existing conclusion that correct underlying direction does not guarantee profitable one-hour option-spread expression.

## Early-exit hypothesis — rejected

A read-only historical option-bar diagnostic inspected the exact September 1 spread from 09:55 through 10:55 ET.

Findings:

- long-leg one-minute bars in the queried window: **24**;
- short-leg one-minute bars: **3**;
- minutes with a trade bar for both legs between 09:55 and 10:55: **1**;
- the only same-minute spread proxy occurred around 10:00 ET at approximately **$4.75**;
- relative to the live $5.05 fill, that proxy was still about **-$30** per contract before additional friction.

There is therefore no evidence that a fixed 15-, 30-, or 45-minute profit-taking exit would have rescued the exact September 1 trade. The broader exit-horizon study already favored 60 minutes, so the exit horizon remains frozen.

## Pre-entry activity gate — rejected

The September 1 live spread displayed a real activity asymmetry:

- long leg: 20 historical trades in the 35-minute pre-entry lookback; latest pre-entry trade about 6.8 minutes old;
- short leg: 2 historical trades; latest pre-entry trade about 18.0 minutes old;
- after entry through 10:55, the long leg printed 25 times while the short printed only 5 times.

Because Alpaca Basic's indicative option trades are delayed, the retrospective sweep then used only option bars timestamped **09:10-09:40 ET**, which are knowable by the 09:55 decision boundary.

An independent control set from the earlier five-signal width-family replay was used so the gate was not judged on September 1 alone. Requiring at least three active minutes for each leg would have blocked the exact September 1 live spread, but it also:

- rejected a historical **+$45** proxy winner from 2026-08-21;
- retained both priced 2026-08-24 proxy losses (**-$17** and **-$6**);
- reduced the control-set proxy sum from **+$321** to **+$276**;
- reduced the control-set proxy hit rate from **75.0%** to about **72.7%**.

Stricter activity thresholds sacrificed still more positive cases. The activity gate therefore fails the robustness requirement and is not promoted.

## Entry-price patience / replacement — not promoted

ClockCross currently submits the constructed conservative natural debit as a limit order. Alpaca supports replacing multi-leg limit orders, so a staged price-improvement policy is technically possible.

However, the exact September 1 fill already improved from a $5.23 submitted debit to $5.05, and the exit improved from a $4.55 minimum credit to $4.70. There is no historical BBO surface available to prove that a more aggressive staged replacement policy would systematically retain fills while improving economics.

Changing the current bounded 180-second entry lifecycle on this evidence would therefore introduce fill-risk and new parameters without a robust expected-value case. It is not promoted.

## Width / strike-family mining — not reopened

The older transparent width-family proxy contains some September 1 spread variants with small positive raw trade-bar outcomes, but those advantages largely disappear under modest friction stress and the proxy cannot reconstruct the historical 09:55 bid/ask/Greek surface used by the live constructor.

A hard width cap was already rejected because it removed valid candidates on two of five recent signal days. This pass does not reopen width, DTE, delta-band, or strike-grid optimization from a single losing live episode.

## External market context

Late August and September 1 were macro-sensitive crypto sessions, with BTC consolidating after a strong move and renewed rates/yields pressure around the start of September. That context is consistent with why a bounded reversion decision can be reasonable, but it is **not** being turned into a deterministic macro rule from this sample.

## Decision

**No production trading change is accepted from this recent-regime pass.**

Keep the already-validated policy intact:

- 1.00% raw residual gate;
- beta-40 residual construction;
- 09:55 ET decision boundary;
- current bounded AI continuation/reversion/abstain authority;
- COIN-only execution;
- 7-21 DTE defined-risk verticals;
- 0.45-0.65 absolute long delta;
- at least 0.10 absolute short delta;
- at least 0.30 absolute net directional delta;
- one-contract sizing under the 1% / 5% defined-loss envelope;
- deterministic 10:55 ET research-horizon exit;
- idempotent Alpaca paper MLeg lifecycle.

The pass found a useful diagnostic observation — **recent option-expression risk remains dominated by spread/leg microstructure, not signal direction** — but none of the tested recent fixes improved that layer without sacrificing prior winners, weakening evidence discipline, or adding unvalidated parameters.

The correct next evidence is prospective competition episodes. For those episodes, engineering should additionally persist Alpaca `filled_avg_price` for parent and leg fills so future option-expression analysis uses exact realized economics without a separate retrospective order query.
