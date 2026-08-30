# ClockCross COIN-Only Options Feasibility Mutation

**Date:** 2026-08-29  
**Applies to:** `docs/superpowers/specs/2026-08-29-clockcross-design.md`  
**Evidence source:** `docs/research/2026-08-29-initial-alpaca-run.md`  
**Status:** Explicitly approved after the first real Alpaca historical run

## Why this amendment exists

The first real chronological Alpaca run returned `MUTATE`, not `KILL`.

Both COIN and MSTR passed chronology, sample-size, outlier-sensitivity, positive-mean, and QQQ-control checks, but neither passed the deliberately severe 100 bps underlying-friction hurdle. The regime split was materially different by ticker:

- COIN 2026 test episodes were strongly positive in aggregate.
- MSTR 2026 test episodes were negative in aggregate despite stronger 2025 behavior.

The approved interpretation is therefore ticker- and regime-specific rather than a claim that all crypto-sensitive equities share stable alpha.

## Canonical live universe

From this amendment onward:

- **COIN** is the only equity permitted to become a live options candidate.
- **MSTR** remains a research/rejection surface and must never be promoted to execution without a new explicit chronological amendment.
- **QQQ** remains the broad-market falsification/control series and is not a live trade target.
- **BTC/USD** remains the primary cross-market driver.

The scheduler, prompt, option constructor, risk governor, and execution service must all fail closed if a live candidate underlying is not `COIN`.

## Directional family

The live candidate family is narrowed around the recent COIN continuation behavior found in the real run.

This does **not** mean every positive or negative residual becomes a continuation trade. Deterministic evidence gates still decide whether an episode is eligible, and the AI may still return `reversion` or `abstain` for contextual reasons. However, live configuration must not introduce unrelated strategy families or broaden the symbol universe to manufacture more trades.

MSTR deterioration is retained as negative evidence in the public research story rather than hidden.

## Options-aware feasibility gate

The original 100 bps underlying-friction result remains immutable evidence. It is not reclassified as a pass.

Before any live COIN episode reaches the AI/order path, ClockCross must determine whether the signal can be expressed through an actually available defined-risk vertical spread.

The gate uses the current Alpaca option chain for COIN and requires:

- expiration between 7 and 21 DTE;
- non-zero bid and ask on both legs;
- quote timestamps within the configured freshness window;
- no 0DTE contracts;
- available Greeks when delta-based selection is used;
- 1:1 same-expiration vertical structure;
- positive bounded net debit;
- maximum loss known before submission;
- candidate debit within the per-position risk budget;
- relative bid/ask quality inside the configured cap;
- deterministic leg ordering appropriate to call or put debit spreads.

Alpaca's current option-chain endpoint exposes latest quote, latest trade, and Greeks for each contract. On accounts without OPRA entitlement, the free `indicative` feed may contain delayed trades and modified quotes. The active feed and quote timestamps must therefore be recorded in every feasibility decision.

References:

- https://docs.alpaca.markets/us/reference/optionchain
- https://docs.alpaca.markets/us/docs/market-data-faq
- https://docs.alpaca.markets/us/docs/options-trading
- https://docs.alpaca.markets/us/docs/options-trading-overview

## Gate ordering

The canonical live decision order becomes:

```text
cross-market evidence
  -> COIN-only eligibility
  -> current option-chain feasibility
  -> Alpaca MCP/news context
  -> bounded AI adjudication
  -> deterministic spread construction
  -> deterministic risk governor
  -> idempotent Alpaca paper execution
```

This ordering prevents LLM calls and order preparation for signals that cannot be expressed economically or safely with the available option chain.

## Alpaca MCP role

Alpaca MCP remains a genuine project surface. Its read-only toolsets may supply auditable account/stock/crypto/options/news context, including option chain and Greeks. Deterministic execution may continue to use the typed API/SDK boundary where idempotency and exact request validation are clearer.

The MCP cannot override symbol restrictions, option-feasibility results, risk decisions, or order idempotency.

## Promotion semantics

The live strategy is an **explicitly approved `MUTATE`**, not a retroactive `GO`.

Paper mode may start only when all of the following are true:

1. the immutable research artifact is present;
2. this mutation document is present and its identifier is part of the active configuration;
3. live candidate underlying is `COIN`;
4. option-chain feasibility passes for that episode;
5. all downstream AI/risk/execution gates pass.

A failed options-feasibility check is a first-class abstention and must be visible in the decision ledger/demo.
