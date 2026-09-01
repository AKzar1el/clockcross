# 2026-09-01 — Indicative option-surface robustness

## Decision

**Keep the current directional spread constructor unchanged.**

A live, read-only robustness study on the competition account's current Alpaca Basic `indicative` COIN option surface found no evidence that small quote/Greek perturbations make the constructor unsafe or materially unconstructible.

The study is deliberately a sensitivity analysis around one observed snapshot. The perturbation bands are stress envelopes; they are **not** claims about the actual probability distribution or magnitude of Alpaca indicative-feed errors.

## Why this was tested

ClockCross selects contracts from Alpaca Basic's `indicative` option snapshot feed. Alpaca documents that the indicative feed uses modified quotes and delayed trades, whereas OPRA is the official options feed. The new constructor ranks safe verticals by usable net directional delta per debit, so it was necessary to test whether small changes to observed quotes and Greeks could cause unsafe behavior or excessive structural instability.

No order client was instantiated by this diagnostic and no order submission endpoint was called.

## Predeclared perturbation bands

Before reading the live result, three deterministic sensitivity envelopes were fixed:

| Band | Midpoint perturbation | Half-spread perturbation | Delta perturbation |
| --- | ---: | ---: | ---: |
| micro | ±0.25% | ±10% | ±0.005 |
| small | ±0.50% | ±20% | ±0.010 |
| moderate | ±1.00% | ±40% | ±0.020 |

Each direction was evaluated for 2,000 trials per band, for **12,000 total constructor trials**.

The predeclared interpretation gates were:

- any risk-invariant violation is a hard failure;
- micro candidate rate below 95% is a constructibility concern;
- small candidate rate below 90% is a constructibility concern;
- micro same-long rate below 70% is a structural-churn warning;
- moderate-band results are descriptive stress only;
- exact short-leg/pair churn alone is not a defect when the long leg, expiration, net directional exposure, and risk remain stable.

## Observed snapshot

- Feed: `indicative`
- Contracts in the 7–21 DTE COIN window: **416**
- Existing one-contract risk-derived maximum debit: **$10.00**
- Existing maximum defined loss implied by that debit cap: **$1,000**
- Snapshot retrieval: 2026-09-01T17:21:46.450750+00:00

Baseline bullish construction:

- long: `COIN260911C00180000`
- short: `COIN260911C00217500`
- expiration: 2026-09-11
- net delta: **0.4205**
- net debit: **$6.13**
- max loss: **$613**

Baseline bearish construction:

- long: `COIN260911P00177500`
- short: `COIN260911P00140000`
- expiration: 2026-09-11
- net delta: **0.4523**
- net debit: **$6.83**
- max loss: **$683**

## Results

### Bullish

| Band | Candidate rate | Same long | Same pair | Net delta p05–p95 | Max loss p05–p95 | Risk violations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| micro | **100%** | **100%** | 97.75% | 0.4134–0.4273 | $611–$615 | **0** |
| small | **100%** | **99.95%** | 83.75% | 0.3987–0.4340 | $583–$617 | **0** |
| moderate | **100%** | 90.15% | 47.30% | 0.3797–0.4875 | $559.95–$720 | **0** |

Expiration remained the same in 100% of selected bullish candidates across every band.

### Bearish

| Band | Candidate rate | Same long | Same pair | Net delta p05–p95 | Max loss p05–p95 | Risk violations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| micro | **100%** | **100%** | 82.00% | 0.4460–0.4591 | $681–$685 | **0** |
| small | **100%** | **100%** | 68.70% | 0.4410–0.4659 | $679–$686 | **0** |
| moderate | **100%** | **100%** | 49.10% | 0.4279–0.4836 | $656.95–$690 | **0** |

Expiration remained the same in 100% of selected bearish candidates across every band.

## Interpretation

All predeclared hard and concern gates passed:

- **0 risk-invariant violations out of 12,000 trials**;
- **100% constructibility in both directions at every perturbation band**;
- micro/small constructibility remained well above the 95%/90% concern thresholds;
- micro same-long rate was 100% in both directions, well above the 70% warning threshold;
- the selected expiration was unchanged in every accepted trial;
- even the 5th percentile net directional delta remained well above the live 0.30 floor in the moderate band.

The short leg does churn as perturbations become larger, especially on the bearish side. That is expected from a score that searches many farther-OTM shorts and chooses the best net-delta/debit ratio. The key result is that this churn did **not** produce fragility in the long leg, expiration, constructibility, directional-exposure floor, or max-loss envelope.

Therefore there is no evidence-based justification for adding a robustness penalty, widening/narrowing the delta window, changing the 0.30 net-delta floor, or modifying the risk budget after this snapshot.

## Limitation

This study does not prove that the Basic indicative feed is equivalent to OPRA, nor does it model actual NBBO execution error. It tests a narrower question: whether bounded perturbations around the observed indicative snapshot destabilize the deterministic constructor.

The answer on this live surface is **no** under the predeclared bands.

Machine-readable evidence is preserved in `artifacts/research/indicative-surface-robustness-2026-09-01.json`.
