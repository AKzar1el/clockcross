# ClockCross Competition Runtime Hardening

**Date:** 2026-08-31  
**Applies to:** `AKzar1el/clockcross`  
**Status:** Approved design for implementation before the first Monday competition session  
**Scope:** Competition orchestration, order lifecycle, deterministic exits, persistence, and operational safeguards only. The frozen signal policy and approved COIN-only mutation are not changed.

## Objective

ClockCross already has a validated one-shot autonomous decision pipeline and an idempotent Alpaca paper MLeg opening path. The remaining production gap is the lifecycle around that pipeline: starting a competition episode without manual intervention, bounding the lifetime of an opening order, managing a filled spread through a deterministic exit, recovering safely after process failure, and preserving the resulting evidence for judging.

This hardening must make ClockCross capable of operating the dedicated Alpaca competition account from signal through terminal position closure without changing the research hypothesis, thresholds, universe, or AI authority.

## Non-goals

This change must not:

- retune the beta lookback, residual threshold, continuation thesis, or 09:25/09:40/09:55 information boundaries;
- add MSTR, QQQ, crypto, stock, 0DTE, naked options, or new strategy families to execution;
- introduce discretionary or loss-driven parameter changes during the competition;
- let the LLM choose contracts, sizing, order prices, exit policy, or risk limits;
- use live capital or any Alpaca endpoint other than paper trading;
- reset or smoke-test the dedicated competition account;
- weaken quote freshness, spread-quality, buying-power, or defined-risk gates merely to force a trade.

## Current constraints to preserve

The canonical execution universe remains COIN only. Entry structures remain 1:1 same-expiration 7–21 DTE call or put debit spreads. Opening decisions remain evidence gate -> current option-chain feasibility -> read-only Alpaca MCP context -> bounded AI (`continuation`, `reversion`, `abstain`) -> deterministic spread construction -> deterministic risk governor -> Alpaca paper MLeg execution.

The research horizon is `forward_60m_return`, measured from the 09:55 ET decision boundary to 10:55 ET. The competition runtime therefore uses 10:55 ET as the deterministic target exit boundary rather than inventing a new take-profit/stop-loss optimization after the research was frozen.

## Architecture

### 1. Competition session command

Add a dedicated competition orchestration command that owns one session from startup through terminal state. It must be safe to invoke repeatedly for the same date and must reuse the durable SQLite episode/order identities rather than creating duplicate actions.

The command is responsible for:

1. running the existing external preflight before any competition action;
2. executing or resuming the 09:55 ET entry episode;
3. reconciling an existing opening order instead of blindly re-submitting;
4. enforcing a bounded opening-order fill window;
5. canceling an unfilled opening order and proving the cancellation;
6. monitoring a filled position until the deterministic 10:55 ET exit boundary;
7. submitting and reconciling the closing MLeg;
8. marking the episode terminal only after the remote order/position state is proven;
9. emitting machine-readable JSON suitable for GitHub Actions logs and later evidence capture.

The existing `run-once`, `reconcile`, `preflight`, and `smoke-mleg` commands remain useful development/debug surfaces. The new competition command composes existing primitives rather than replacing them.

### 2. GitHub Actions scheduler

Add one narrowly-scoped scheduled workflow for the dedicated competition runtime. GitHub Actions is chosen for the four-day contest because it provides auditable execution logs and avoids introducing an additional always-on service immediately before the competition session.

The workflow must:

- run only on weekdays during the event window;
- run at a conservative UTC time after the 09:55 ET decision boundary;
- also support `workflow_dispatch` for controlled manual recovery;
- use an Actions `environment` named `competition` so credentials can be isolated from development settings;
- consume encrypted repository/environment secrets for the fresh competition Alpaca key, Alpaca secret, and ClockCross AI gateway bearer;
- set `CLOCKCROSS_ACCOUNT_ROLE=competition` and force `CLOCKCROSS_ALLOW_DEV_ORDER=false`;
- never print secret values;
- upload only sanitized logs/evidence artifacts if artifacts are needed;
- use `concurrency` to prevent two competition runs for the same ref/session from overlapping.

Because scheduled GitHub Actions may begin several minutes late, ClockCross itself remains the source of truth for market/session-time validation. The scheduler may trigger execution; it cannot bypass ClockCross timing gates.

### 3. Opening-order lifecycle

Opening MLeg submission remains a single deterministic limit order with the existing deterministic `client_order_id` and no blind retries.

After submission:

- poll/reconcile the exact client order identity;
- if `filled`, transition into active position monitoring;
- if `partially_filled`, fail closed and require explicit reconciliation rather than submitting another structure;
- if `rejected`, `expired`, or confirmed `canceled`, close the episode without a position;
- if the order remains open beyond a fixed fill deadline, cancel the parent MLeg and poll until cancellation is proven;
- if cancellation cannot be proven, leave the episode indeterminate/open and do not create another order.

The fill deadline must be fixed before competition trading and must not be changed based on observed wins/losses. The implementation should choose the shortest practical window that gives a reasonable paper fill opportunity while avoiding stale intraday orders; this value is configuration with a checked-in default and test coverage, not an AI decision.

### 4. Deterministic 60-minute exit

A filled ClockCross opening structure is held only until the research-aligned 10:55 ET exit boundary unless an earlier exchange/broker terminal condition makes the position unavailable.

At or after 10:55 ET, the runtime builds a closing MLeg for the exact open spread:

- long opening leg (`buy_to_open`) becomes `sell_to_close`;
- short opening leg (`sell_to_open`) becomes `buy_to_close`;
- ratio remains 1:1;
- same contracts and quantity are used;
- closing order is a paper-only MLeg limit order with its own deterministic close `client_order_id` derived from the episode/open-order identity;
- the close path performs pre-submit remote reconciliation exactly as the opening path does.

The initial close limit is based on a fresh current quote for those exact contracts. The code may use a deterministic conservative executable price derived from the current bid/ask surface; it may not ask the LLM for a price.

For this hackathon hardening, avoid adaptive profit-taking, stop-loss optimization, or model-directed exits. The 60-minute time exit is the canonical strategy exit because it matches the frozen research measurement horizon.

### 5. Close-order boundedness and recovery

A close order must not remain indefinitely unresolved.

The close service must:

- reconcile before submit;
- submit once with deterministic identity;
- poll for terminal state;
- if a transport failure creates uncertainty, look up the deterministic identity before any further action;
- never duplicate a close POST while the previous close state is unknown;
- expose an indeterminate state requiring the same reconciliation path after restart.

If a close limit remains open, the runtime may cancel and replace it only according to a deterministic, pre-declared policy using fresh quotes and the same contracts/quantity. Any replacement must have a deterministic sequence identity and must first prove the prior order is canceled. Keep the replacement count small and fixed. If terminal closure still cannot be proven, fail closed and surface the condition rather than improvising.

### 6. Durable state and ledger

The existing episode state machine/SQLite ledger must become sufficient to recover the complete lifecycle after a process restart.

Persist enough information to reconstruct without recomputing the signal:

- opening candidate contract symbols, expiration, direction/structure, quantity, submitted debit, and opening client/alpaca order IDs;
- opening terminal status and fill information available from Alpaca;
- deterministic exit timestamp;
- closing order identity/identities, prices, statuses, and reconciliation events;
- final terminal reason;
- sanitized P&L/equity marks used for the public evidence surface.

Recovery must use persisted order/position identity. It must never rerun the model or generate a second daily signal merely because the process restarted.

### 7. State-machine semantics

Retain current states where possible, but make `MONITORING` operational rather than terminal-by-omission. If new states are needed, prefer explicit names such as `EXIT_DUE`, `EXIT_SUBMITTED`, and `EXIT_INDETERMINATE` over encoding lifecycle meaning only in order payloads.

Required legal path examples:

```text
COLLECTING
  -> ...
  -> RISK_APPROVED
  -> ORDER_SUBMITTED
  -> ORDER_FILLED
  -> MONITORING
  -> EXIT_SUBMITTED
  -> CLOSED
```

Unfilled opening order:

```text
ORDER_SUBMITTED
  -> ORDER_CANCELLED
  -> CLOSED
```

Uncertain opening or closing order remains recoverable and must never transition to `CLOSED` until the remote outcome is known or an explicitly documented operator intervention resolves it.

### 8. Portfolio and risk consistency

The current one-COIN-structure rule remains. A new daily entry must be refused while a prior COIN structure is still open or an opening/closing order is unresolved.

Aggregate defined-risk accounting must stop assuming zero once positions can survive across process invocations. Build current risk from actual open option positions/orders where practical, or conservatively block new entries whenever an earlier ClockCross COIN lifecycle is unresolved. For the four-day competition, correctness and fail-closed behavior are preferred over sophisticated portfolio netting.

### 9. Option-liquidity consistency

The live option-chain adapter currently guarantees quote/Greeks fields used by ClockCross but does not populate the constructor's optional open-interest/volume fields. Do not present OI/volume as enforced live requirements unless the runtime actually fetches and validates them.

For this pass, the canonical enforced liquidity controls are:

- current quote timestamp within the configured freshness window;
- positive non-crossed bid/ask;
- maximum relative bid/ask spread;
- required delta availability and target/tolerance;
- positive debit below vertical width;
- current buying power and deterministic max-loss gates.

Remove or clearly mark inactive OI/volume defaults from the live policy unless a reliable Alpaca source is added and tested without increasing runtime fragility.

### 10. Final-day handling

The existing September 4 new-entry cutoff remains at 10:20 ET. The runtime must not open a new competition position at or after that boundary.

Any ClockCross position already open must still follow its deterministic exit/reconciliation policy. Before the 17:00 CEST submission deadline, the operator must capture account equity/P&L and verify there are no unknown opening/closing orders. If LabLab/Alpaca later publish an authoritative P&L freeze rule, documentation may be clarified without changing the strategy.

## Security and secret handling

The public repository remains secret-free. Competition credentials are stored only as encrypted GitHub Actions environment/repository secrets and injected at runtime.

Required safeguards:

- no competition API key, secret, account ID, or gateway bearer committed to git;
- no `set -x` or equivalent secret-echoing shell behavior;
- no raw environment dumps;
- keep existing repository secret-scan tests;
- paper endpoint remains hard-pinned in code;
- competition mode rejects the development order opt-in flag;
- credentials should be rotated after the event.

The Alpaca account ID required for judging may be entered into LabLab manually; it is not a credential and does not need to be committed.

## Testing strategy

Implementation follows TDD and adds focused tests before production code for at least:

1. deterministic close client-order identity;
2. correct MLeg close intents and exact-contract reuse;
3. no close duplicate after timeout/transport uncertainty;
4. opening-order fill polling and bounded cancellation;
5. cancellation must be proven before episode closure/replacement;
6. filled opening -> monitoring -> 10:55 exit -> closed state path;
7. restart from opening `ORDER_SUBMITTED` does not recompute the signal;
8. restart from `MONITORING` resumes exit management without LLM invocation;
9. restart from close-order uncertainty performs reconciliation only;
10. previous unresolved COIN lifecycle blocks a new entry;
11. competition mode rejects development-order opt-in;
12. September 4 final entry cutoff still blocks late entries;
13. GitHub Actions workflow contract contains competition role, disabled dev flag, concurrency, and no literal secrets;
14. public API/evidence output continues to redact identifiers/credentials;
15. full existing pytest suite, Ruff, mypy, and repository secret scan remain green.

After implementation, run the complete CI-equivalent command set and inspect the GitHub Actions result on the final branch commit before merging.

## Monday operational sequence

1. Merge only after full tests/CI pass.
2. Add fresh competition Alpaca credentials and AI gateway bearer to the GitHub `competition` environment; never put development credentials there.
3. Before the U.S. options session, run the development-account read-only `preflight` again.
4. After the market is open, run exactly one `smoke-mleg` on the development account and require a proven `final_status: canceled`.
5. Return `CLOCKCROSS_ALLOW_DEV_ORDER=false` immediately after the smoke.
6. Create/verify the fresh competition paper account at exactly `$100,000`, Level 3, with no positions and no manual/smoke orders.
7. Trigger/observe the first scheduled competition session after the 09:55 ET boundary.
8. A valid abstention is a successful autonomous episode; do not weaken gates to manufacture P&L.
9. Verify any opening fill reaches a deterministic 10:55 ET close and terminal reconciliation.
10. Preserve sanitized logs/evidence for the demo and final submission.

## Acceptance criteria

This hardening is complete only when all of the following are true:

- the full test/lint/type-check suite is green on the implementation commit;
- a dedicated scheduled competition workflow exists and cannot run with development account mode;
- a competition episode can reach a terminal state without human trade selection;
- unfilled opening orders are bounded and proven canceled;
- filled positions have a deterministic research-aligned exit path;
- restart/retry cannot duplicate an opening or closing order;
- unresolved prior COIN state blocks new trading;
- existing research/mutation artifacts and strategy constants remain unchanged;
- the public repository contains no secrets;
- the Monday development MLeg submit/cancel proof is the only remaining external destructive integration check before first competition trading.
