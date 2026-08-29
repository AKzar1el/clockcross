# ClockCross COIN-Only Mutation Implementation Notes

**Approved:** 2026-08-29

This note amends `2026-08-29-clockcross-implementation.md` after the real Task 5 Alpaca run returned an explicitly approved `MUTATE`.

## Task-order amendment

Insert **Task 5A: COIN option-chain feasibility** before Task 6.

Task 5A must:

1. add typed option-chain contracts and normalization for Alpaca's chain response;
2. accept only `COIN` for live-feasibility evaluation;
3. enforce 7-21 DTE, non-zero bid/ask, timestamp freshness, 1:1 same-expiration vertical compatibility, and bounded positive debit;
4. record `indicative` versus `opra` feed and quote timestamps;
5. return a typed abstention/failure when no executable candidate exists;
6. include deterministic tests for malformed/missing Greeks, crossed/zero quotes, stale quotes, 0DTE, wrong underlying, and no candidate;
7. remain read-only: no order submission in Task 5A.

Task 6 then collects MCP/news context and performs bounded AI adjudication only after Task 5A has shown that the episode has at least one feasible COIN spread surface.

Task 7 consumes the Task 5A normalized chain/feasibility types rather than creating a duplicate option-chain model. It remains responsible for final strike selection and the complete deterministic risk governor.

## Live-universe amendment

For Tasks 6-12:

- execution-eligible underlying: `COIN` only;
- `MSTR`: research/rejection evidence only;
- `QQQ`: control only;
- any scheduler/prompt/constructor/executor path receiving another live underlying fails closed.

## Research-verdict semantics

Scheduler paper mode must accept the original `MUTATE` only when the approved mutation document `docs/superpowers/specs/2026-08-29-coin-options-mutation.md` is present and the active configuration identifies that mutation. It must never rewrite the original research artifact to `GO`.

## Verification order

1. Task 5A unit tests.
2. Task 6 AI/MCP tests.
3. Task 7 constructor/risk tests.
4. Full existing unit suite after each task.
5. Development-account read-only option-chain probe when credentials/network are available.
6. Development-account order smoke test remains blocked until Task 9 and its explicit opt-in guards.
