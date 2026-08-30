# ClockCross Market-Data Timing Amendment

**Date:** 2026-08-29  
**Applies to:** `docs/superpowers/specs/2026-08-29-clockcross-design.md`  
**Reason:** Alpaca Basic-plan feed semantics discovered during implementation

## Status

This amendment supersedes the original live equity timing wherever the original design implies that a consolidated SIP observation through 09:40 ET can be consumed at 09:40 ET on the free Alpaca Basic plan. The core ClockCross hypothesis, universe, options constraints, account discipline, and research-first gate are unchanged.

## Verified Alpaca constraint

Alpaca's current documentation distinguishes the free Basic equity feed from consolidated real-time SIP. Basic includes real-time IEX and limits recent consolidated historical data; Alpaca also exposes `delayed_sip`, explicitly defined as SIP delayed by 15 minutes. The current latest-bar/quote/snapshot APIs list `delayed_sip` as a supported stock feed.

References:

- https://docs.alpaca.markets/us/v1.1/docs/about-market-data-api
- https://docs.alpaca.markets/us/reference/stocklatestbarsingle-1
- https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data

Using historical SIP for research but real-time IEX for live ClockCross decisions would introduce a venue-coverage mismatch into the signal. The free reproducible path therefore uses consolidated SIP on both sides of the experiment: historical `sip` for research and live `delayed_sip` for decision inputs.

## Corrected daily clock

The canonical Basic-plan schedule is:

```text
09:25 ET  freeze premarket residual inputs
09:30 ET  regular session opens
09:40 ET  end opening-confirmation window
09:55 ET  earliest autonomous decision
```

At 09:55 ET, a 15-minute delayed SIP feed can expose market data through 09:40 ET. The premarket feature freeze remains **09:25 ET**: moving it to 09:10 would unnecessarily discard fifteen minutes of premarket information because the 09:25 observation is already old enough to be available by the 09:55 decision.

Historical episode construction must reproduce the same boundaries:

- residual inputs end at 09:25 ET;
- opening confirmation is measured from 09:30 through 09:40 ET;
- the decision reference price is 09:55 ET;
- 30-minute forward evaluation is 09:55 -> 10:25 ET;
- 60-minute forward evaluation is 09:55 -> 10:55 ET.

## Feed policy

ClockCross configuration defaults are amended to:

```text
historical_stock_feed = sip
live_stock_feed = delayed_sip
option_feed = indicative
```

The selected feed must be recorded in research and live decision artifacts. If the competition account obtains OPRA or real-time SIP entitlement later, that is a configuration change requiring an explicit evidence note; it must not silently change the model's information set.

## Beta implementation clarification

The first research baseline estimates the rolling BTC-to-equity beta as the centered covariance/variance slope (the OLS slope with an intercept), returning no estimate when crypto returns have zero variance. The expected-move baseline remains deliberately beta-only:

```text
expected_equity_return = beta * crypto_return
residual = equity_premarket_return - expected_equity_return
```

The fitted intercept is not added to the expected move in this baseline. This avoids quietly mixing average equity drift into the cross-market response term. An intercept-inclusive forecast may only enter as an explicitly declared chronological ablation, never as an after-the-fact rescue of a weak result.

## Competition implication

This timing change reduces the exploitable live horizon by fifteen minutes but removes a more damaging research/live feed mismatch. ClockCross should prefer a slower defensible signal over a faster signal whose historical and live inputs come from materially different market coverage.
