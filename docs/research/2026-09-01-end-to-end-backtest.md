# ClockCross chronological end-to-end backtest — 2026-09-01

## Why this pass exists

The earlier research established a chronological COIN/BTC signal and several robustness properties, but it was not a literal day-by-day replay of the final live policy and it was not an exact historical options-fill backtest. This pass closes that gap as far as the available Alpaca data permits.

The replay uses the final strategy timing and production context:

- COIN driven by a BTC/USD cross-market residual;
- beta lookback: 40 completed sessions;
- raw residual gate: 1.00%;
- decision: 09:55 ET;
- fixed exit: 10:55 ET;
- frozen live research mean supplied to the AI: `0.002745696957097104`;
- current deployed `clockcross-cloudflare-llama-3.3-70b` adjudicator;
- historical stock data: SIP;
- timestamp-capped historical COIN news through 09:55 ET;
- current option structure vocabulary exposed to the AI.

No order endpoint was used in any historical diagnostic.

## One-month replay: August 3 through September 1

The first requested daily pass replayed 22 business days. Five days crossed the 1% residual gate, 16 abstained at the threshold, and one day failed closed because the required historical feature set was unavailable.

The five signal dates were August 7, August 18, August 21, August 24, and September 1.

Raw continuation performed poorly in this recent regime: 1 win / 4 losses, 20% hit rate, approximately **-32.8 bps average directional 60-minute COIN return**.

Replaying the current AI with the exact frozen research mean used by production produced:

- August 7: continuation / bullish — correct;
- August 18: reversion / bullish — correct;
- August 21: reversion / bullish — correct;
- August 24: reversion / bullish — correct;
- September 1: reversion / bullish — correct.

That is **5/5 directionally correct**, with approximately **+111.6 bps average chosen-direction 60-minute COIN return**. This does not mean all five option spreads would necessarily have been profitable; the option-price replay below shows why.

## Recent-quarter replay: June 1 through September 1

Using Alpaca's actual U.S. market calendar produced 65 trading days and 23 signal episodes.

The quarter exposed a real regime problem:

| Policy | Signals/trades | W-L | Hit rate | Mean directional 60m return |
| --- | ---: | ---: | ---: | ---: |
| Frozen continuation | 23 | 12-11 | 52.2% | **-7.8 bps** |
| Current AI | 22 | 11-11 | 50.0% | **-11.0 bps** |

The monthly split matters more than the quarter aggregate. June strongly favored continuation, while August strongly favored AI reversion:

- June continuation: 7-2, **+82.6 bps mean**;
- June AI: 4-5, **-38.3 bps mean**;
- August continuation: 1-3, **-16.5 bps mean**;
- August AI: 4-0, **+115.0 bps mean**;
- September 1 AI reversion: **+98.0 bps** underlying-direction return versus approximately -98.0 bps for continuation.

This was the evidence that prevented us from simply declaring the recent 5/5 AI result universally superior.

## Six-month replay: March 2 through September 1

The broader chronological pass used 128 actual Alpaca market days. It generated 39 signals, 36 AI trades, 3 AI abstentions, 6 data abstentions, and 83 threshold abstentions.

| Policy | Signals/trades | W-L | Hit rate | Mean directional 60m return | Median | Sum of diagnostic directional returns |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Frozen continuation | 39 | 22-17 | 56.4% | **+15.9 bps** | +57.0 bps | +6.21% |
| Current AI | 36 | 21-15 | 58.3% | **+50.7 bps** | +57.3 bps | +18.26% |

The AI remained regime-sensitive, but over the larger six-month sample it materially outperformed raw continuation rather than merely fitting August.

Monthly AI mean chosen-direction return:

- March: +67.9 bps;
- April: +105.0 bps;
- May: +254.5 bps;
- June: -38.3 bps;
- July: -57.1 bps;
- August: +115.0 bps;
- September 1: +98.0 bps.

Therefore the negative June/July pocket is real, but it is not sufficient evidence to remove AI reversion authority after seeing the broader chronology.

## AI replay stability

To make sure the quarter result was not an accident of a single model call, all 23 quarter signal contexts were replayed three times against the deployed gateway: **69 calls total**.

- unanimous action contexts: 23 / 23;
- action-flip contexts: 0;
- all three complete quarter replays reproduced the same 11-11 AI outcome and approximately -11.0 bps mean directional return.

Free-text reasons and confidence values can vary; the action did not. This is evidence against adding majority voting or changing the model merely to stabilize the backtest.

## Historical options replay and its hard data boundary

Alpaca exposes historical option bars/trades from February 2024 onward, which allows real historical option-price and trade-print analysis. However, Alpaca's option snapshot surface is a latest-state snapshot; arbitrary-past snapshot bid/ask and Greeks are not exposed by that endpoint. The free `indicative` option feed is also not equivalent to actual OPRA BBO.

Accordingly, this study does **not** claim an exact historical recreation of the live constructor's old 09:55 quote/Greek surface.

Instead, we used two honest proxies:

1. option trade-bar families around the five recent signal days to test whether correct COIN direction necessarily translated into spread profit;
2. pre-09:55 historical option trades to infer transparent Black-Scholes delta proxies, followed by the actual production vertical-ranking code.

The first result is important: **correct underlying direction does not guarantee positive one-hour debit-spread P&L**. Historical trade-bar families included losing or friction-sensitive spread outcomes even on days when the AI chose the correct COIN direction.

## Constructor defect exposed by the backtest

The historical constructor proxy revealed a structural degeneracy in the current `net_delta / debit` objective. With no minimum short-leg delta, the optimizer could prefer extremely far-OTM shorts whose delta was almost zero. Examples from the five recent signals included widths around 50-60 points and short-delta proxies near 0.00-0.02.

Those structures looked mathematically efficient because the distant short reduced the debit without reducing much long-leg delta, but the selected short legs had poor historical trade-print coverage.

A RED regression test reproduced the problem with a valid quote: the old constructor chose a 0.02-absolute-delta lottery short over a 0.15-delta meaningful short for both calls and puts.

### Predeclared structural comparison

We compared three non-P&L-mined structural constraints against the current ranking:

- minimum short absolute delta of 0.10;
- hard width cap of 10% of COIN spot;
- both together.

The hard width cap was rejected because it removed valid candidates on 2 of the 5 recent signal days.

The **0.10 short-delta floor** retained candidates on all five days and materially improved the liquidity proxy:

| Metric | Old constructor | `|short delta| >= 0.10` |
| --- | ---: | ---: |
| Signal days with a candidate | 5/5 | 5/5 |
| Entry trade-print coverage | 40% | **80%** |
| Exit trade-print coverage | 20% | **40%** |
| Mean width | 56.9 points | **29.4 points** |
| Mean net delta | ~0.466 | **~0.370** |

The new floor preserves net directional delta well above the 0.30 invariant while avoiding the near-zero-delta short-leg pathology.

### Post-fix live-surface stress

The production default with `min_short_abs_delta = 0.10` was then run through the existing live indicative-surface perturbation simulator:

- 2 directions;
- 3 perturbation bands;
- 2,000 trials per band;
- **12,000 constructor trials total**;
- bullish constructibility: 100%;
- bearish constructibility: 100%;
- risk-invariant violations: **0**.

So the liquidity fix did not trade historical constructibility for live fragility.

## Rejected strategy changes

Two attempted AI authority guards were rejected rather than fitted to the sample.

### Opening-sign confirmation — rejected

Requiring the 09:30-09:40 COIN move to support an AI reversion made the quarter materially worse and would have blocked the correct September 1 reversion. It is not being implemented.

### Rolling five-signal regime gate — not promoted

Allowing AI reversion only when the last five completed continuation outcomes were negative improved one retrospective quarter, but it would have blocked correct August and September 1 reversions. Given the broader six-month evidence and data-snooping risk, it is not being promoted.

No z-score grid, alternate residual threshold, alternate exit horizon, or optimized regime-window search was opened in response.

## Final decision

The backtest supports exactly one new production change:

> **Require the vertical's short leg to have at least 0.10 absolute delta.**

Everything else remains frozen:

- 1.00% raw residual gate;
- beta-40 residual construction;
- 09:55 ET decision;
- 60-minute / 10:55 ET exit;
- current AI continuation/reversion/abstain policy;
- risk limits and one-contract bounded-loss construction.

This is the point to stop retrospective parameter mining. The next evidence should be prospective competition episodes, while engineering effort moves to submission quality and judge communication.

## Interpretation discipline

The directional-return metrics in this document are diagnostics, not compounded account returns and not exact historical option P&L. Historical option trade prints are a liquidity/price proxy, not proof of executable BBO fills. That limitation is preserved intentionally rather than hidden behind an artificially precise backtest number.
