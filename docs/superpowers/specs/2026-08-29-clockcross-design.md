# ClockCross Competition Design

**Date:** 2026-08-29  
**Repository:** `AKzar1el/clockcross`  
**Target event:** Alpaca AI Trading Agents Hackathon, 28 Aug-4 Sep 2026  
**Status:** Approved design, implementation not started

## 1. Objective

Build a small autonomous AI options-trading agent for Alpaca paper trading that tests a specific cross-market hypothesis:

> 24/7 crypto price discovery can sometimes leave a measurable, temporary residual in crypto-sensitive U.S. equities after premarket repricing. ClockCross should trade only when recent chronological evidence says that residual has predictive value after the U.S. open.

ClockCross is not a generic multi-agent trading platform. It is a competition-specific research-and-execution system optimized for verifiability, bounded risk, fast delivery, and honest rejection of weak signals.

The primary success condition is a valid hackathon submission whose trading decisions are autonomous, reproducible, risk-bounded, and auditable. Positive paper P&L matters because it is a judging criterion, but the implementation must not manufacture performance through look-ahead leakage, manual trade intervention, account resets, or unbounded 0DTE risk.

## 2. Competition constraints

The implementation must satisfy these project-wide constraints:

- Use Alpaca's Trading API for paper-trading execution.
- Use Alpaca MCP or Alpaca CLI as a real part of the project, not only as a development convenience.
- Incorporate options trading.
- Final judging account must be a new dedicated Alpaca paper account starting at exactly `$100,000`.
- Development and destructive smoke testing must occur on a separate development paper account.
- The final competition account must not contain arbitrary manual or smoke-test trades before the autonomous competition run starts.
- Submission repository must remain public and contain no credentials, account secrets, private keys, or copied proprietary code.
- Implementation must be original and MIT-compatible.
- The project must be demoable, with decision history and P&L visible without requiring judges to infer hidden behavior.
- Submission deadline is 2026-09-04 17:00 CEST. The system must therefore be operational before the first full U.S. trading session on Monday, 2026-08-31.

## 3. Naming and product statement

The canonical project name is **ClockCross**.

Working one-line description:

> ClockCross is an autonomous AI options agent that measures crypto-to-equity repricing gaps, validates them walk-forward, and expresses only evidence-backed signals through defined-risk Alpaca option spreads.

Avoid claims such as "predicts the market", "guaranteed alpha", "production-grade trading system", or "institutional grade" unless directly supported by evidence.

## 4. Core hypothesis

The naive hypothesis "BTC moved overnight, therefore buy a crypto-sensitive stock at the open" is explicitly rejected.

Crypto-sensitive equities such as COIN and MSTR can already reprice in premarket. ClockCross instead estimates the expected equity move from the current crypto move and recent cross-market relationship, then measures the unexplained residual.

For an underlying `u` and crypto driver `c`:

```text
expected_equity_return = rolling_beta(c, u) * crypto_return
residual = actual_premarket_equity_return - expected_equity_return
```

The exact regression implementation may include an intercept if chronological validation shows it improves out-of-sample behavior. The first implementation should prefer the simplest specification that survives validation.

A residual is not automatically a trade. It becomes only a candidate feature. ClockCross must determine whether residual magnitude and direction have historically predicted a post-open move over recent, strictly prior windows.

## 5. Initial market universe

Keep the research universe intentionally small.

### Crypto driver

- Primary: `BTC/USD`
- `ETH/USD` is excluded from the initial model and may only be added if an explicit out-of-sample ablation demonstrates incremental value.

### Equity underlyings

- Primary: `COIN`
- Secondary: `MSTR`
- Control / falsification series: `QQQ`

QQQ is not automatically a trading target. It exists partly to detect whether the purported signal is merely broad market beta rather than crypto-specific information.

No dynamic stock screener, broad ticker universe, or LLM-selected symbol list is part of the MVP.

## 6. Time semantics and leakage prevention

ClockCross must use explicit market-time boundaries. All timestamps are stored in UTC internally; market-session logic uses `America/New_York`.

A daily decision episode has these phases:

1. **Overnight / premarket feature collection**
   - Crypto observations are available continuously.
   - Equity premarket observations stop at a deterministic feature-freeze time before the regular session.
2. **Feature freeze**
   - Target default: `09:25 ET`.
   - No feature whose timestamp is after the freeze may enter the premarket residual calculation.
3. **Opening confirmation window**
   - Observe regular-session equity behavior from `09:30 ET` through a target default of `09:40 ET`.
4. **Decision time**
   - Earliest live order decision: approximately `09:40 ET`.
5. **Execution and monitoring**
   - Use bounded limit orders and deterministic risk checks.

Research code must reproduce these same information boundaries historically. Any result that uses future candles, future news, future option prices, revised values unavailable at decision time, or random train/test shuffling is invalid.

## 7. Research and falsification harness

The research harness is milestone one and has authority to kill the initial thesis.

### 7.1 Required outputs

For each chronological decision episode, persist at least:

- session date
- BTC overnight return
- equity prior close
- equity premarket reference price
- actual premarket equity return
- rolling beta estimate
- expected equity return
- residual
- first-10-minute regular-session return
- forward target return(s)
- signal direction, if any
- training-window boundaries
- any gate result

### 7.2 Validation rules

- Chronological splits only.
- No shuffled cross-validation.
- Every fitted beta, threshold, or model parameter for date `D` must use data strictly before `D`.
- Parameters chosen while viewing one evaluation window must be re-tested on untouched chronological windows before adoption.
- Costs and realistic spread assumptions must be represented when translating underlying edge into trade viability.
- Results must include negative windows, not only the best period.
- QQQ control results must be reported alongside COIN/MSTR where enough data exists.

### 7.3 Promotion gate

The initial residual strategy is promoted to live competition execution only if the weekend research pass finds a stable, non-trivial chronological effect that is not obviously explained by one isolated period or a single ticker.

Minimum evidence package before promotion:

- directionally consistent performance across more than one chronological validation slice;
- enough qualifying episodes to make the result more than a handful of anecdotes;
- no obvious look-ahead or timestamp leakage;
- no collapse after adding conservative transaction/spread assumptions at the underlying-signal level;
- control comparison that does not show the same apparent effect indiscriminately across QQQ;
- a simple baseline comparison, such as unconditional post-open return or residual-sign-only behavior.

The project must **not** hard-code a numerical Sharpe, win-rate, p-value, threshold, or minimum trade count before inspecting the available Alpaca history because the attainable sample size and data coverage must first be measured. The research artifact must make the chosen promotion threshold explicit after data inspection and explain why it is reasonable.

### 7.4 Kill criteria

Kill or materially mutate the initial strategy if any of the following occurs:

- apparent edge disappears under chronological validation;
- signal exists only because of a few extreme days;
- premarket equity already absorbs nearly all useful crypto information;
- QQQ shows the same behavior, undermining the crypto-specific thesis;
- realistic option execution constraints make the underlying effect economically unusable;
- required historical timestamps cannot be reconstructed without leakage.

Killing the hypothesis is an acceptable engineering outcome. In that case, retain the research harness and pivot to another narrowly defined signal family rather than layering indicators onto a failed idea.

## 8. Signal engine

The MVP signal engine is deterministic and small.

Required features:

- BTC overnight / premarket return
- rolling BTC-to-equity beta
- premarket equity return
- cross-market residual
- opening-window confirmation return
- simple realized-volatility / regime context if needed for normalization

RSI divergence may be evaluated as an optional feature because an existing tested implementation exists elsewhere in the owner's portfolio, but it must not be copied blindly or included merely to increase feature count. It is admitted only if an ablation improves chronological validation.

No large indicator zoo, sentiment ensemble, genetic optimization, reinforcement learning, or unrestricted feature search belongs in the MVP.

## 9. AI authority boundary

ClockCross must be a genuine autonomous AI agent rather than a deterministic bot with an LLM-generated explanation.

The LLM receives a bounded structured context after deterministic evidence gates have produced a candidate episode. Inputs may include:

- residual magnitude and sign
- BTC regime / volatility summary
- opening-window confirmation
- historical reliability of the current signal bucket
- current position and portfolio state
- relevant recent Alpaca news for the underlying and crypto driver

The LLM returns schema-validated structured output:

```json
{
  "action": "continuation | reversion | abstain",
  "confidence": 0.0,
  "idiosyncratic_news_detected": false,
  "driver": "crypto_cross_market | company_specific | macro | unclear",
  "reason": "short auditable explanation"
}
```

The LLM has meaningful authority to choose between a continuation thesis, a reversion thesis, or abstention when deterministic evidence permits a candidate.

The LLM may **not**:

- choose arbitrary symbols outside the approved universe;
- invent option contract identifiers;
- bypass data-freshness checks;
- modify portfolio risk limits;
- choose uncovered short options;
- place 0DTE trades in the MVP;
- exceed DTE, liquidity, spread, buying-power, or duplicate-position constraints;
- submit an order directly without deterministic validation.

If model output fails schema validation, times out, contains an unsupported action, or conflicts with deterministic risk rules, the episode becomes `abstain` and is logged.

## 10. Options expression

The MVP expresses approved directional theses with defined-risk vertical debit spreads.

Allowed structures:

- bullish call debit spread
- bearish put debit spread

Initial structural constraints:

- target expiration range: `7-21 DTE`;
- no 0DTE contracts;
- one long leg and one short leg, same underlying and expiration;
- ratio `1:1`;
- atomic Alpaca multi-leg order (`mleg`);
- limit orders only;
- maximum debit must be known before submission;
- no naked short-option exposure;
- no position whose expiration is inside a period that creates unavoidable post-submission risk.

Exact strike-selection rules, target deltas, spread width, quote freshness, and maximum acceptable bid/ask width must be determined from available option-chain data and validated during implementation. They must be deterministic and documented.

Because Alpaca Basic options data uses the indicative feed while subscribed users can access OPRA, the system must explicitly record the feed used and treat quote freshness/spread quality as risk inputs. It must never silently assume indicative quotes are identical to consolidated OPRA.

## 11. Risk governor

Risk policy is deterministic and cannot be overridden by the LLM.

The first implementation should encode configurable limits with conservative defaults, then freeze competition values after paper dry-runs.

Required gates:

- paper trading only;
- approved underlying only;
- approved strategy type only;
- valid two-leg contract relationship;
- expiration within allowed range;
- fresh enough market data;
- acceptable quoted spread / liquidity;
- defined maximum loss;
- sufficient buying power;
- per-position maximum-loss limit;
- portfolio-level simultaneous maximum-loss limit;
- no duplicate or conflicting position unless explicitly supported;
- one active structure per underlying in the MVP;
- market-hours / decision-window check;
- final-event liquidation rule.

Target competition envelope to validate before freezing:

- roughly `1-2%` of starting equity maximum loss per new position;
- roughly `5-6%` aggregate simultaneous defined loss.

These are design targets rather than immutable values. Final values must be justified by observed option prices and dry-run behavior and then recorded in configuration before the competition account starts trading.

## 12. Alpaca integration

ClockCross should use Alpaca as the primary external platform rather than introducing unnecessary providers.

Required Alpaca capabilities:

- account/configuration state
- market clock/calendar
- BTC market data
- stock bars/quotes/snapshots
- option contracts and option chain
- option quotes/snapshots/Greeks where available
- recent news
- paper-order submission and position state

### MCP requirement

Alpaca MCP must be exercised as a genuine system surface. At minimum, the repository and demo must show an MCP-backed autonomous/research workflow for Alpaca context or operations. The production scheduler may use the official SDK/API where it provides better deterministic control, but the project must not reduce MCP usage to a screenshot or unused dependency.

The exact division between MCP and SDK/API is:

- **MCP:** agent-facing context and auditable structured Alpaca tool interaction;
- **SDK/API:** deterministic scheduled data retrieval and order execution where reproducibility, retries, and typed validation are clearer.

If implementation shows a simpler reliable architecture using MCP for additional operations, it may expand, but only without weakening deterministic risk controls.

## 13. Account discipline

Use two logically separate environments.

### Development paper account

Permitted:

- order smoke tests
- failed-order tests
- option-chain experiments
- MLeg tests
- cancellation tests
- retries
- destructive integration tests

### Competition paper account

Required:

- new account created specifically for the event;
- starting balance exactly `$100,000`;
- fresh API credentials;
- no arbitrary manual trades before autonomous operation begins;
- no resets after competition operation begins;
- no manual intervention intended to alter P&L;
- any emergency manual intervention must be documented in the decision ledger and submission write-up.

Secrets must be environment-only and never committed.

## 14. Decision ledger and auditability

Every scheduled episode produces a durable record even when no trade occurs.

Minimum ledger fields:

- unique episode ID
- decision timestamp
- feature-freeze timestamp
- underlying
- crypto driver
- raw feature values
- training / evidence window identifier
- deterministic evidence-gate result
- news/context references or identifiers
- LLM model identifier
- validated LLM response
- every deterministic risk-gate result
- candidate contracts
- selected spread
- quote timestamps and feed
- intended maximum debit / maximum loss
- submitted order ID
- fill/cancel/reject state
- later mark-to-market and realized P&L when available
- explicit rejection/abstention reason

The system should make rejected decisions as visible as executed ones. "No trade" is a first-class result.

## 15. Scheduler and state machine

Daily competition operation should be modeled as an idempotent state machine, not a loose cron script.

Suggested states:

```text
COLLECTING
  -> FEATURES_FROZEN
  -> OPENING_CONFIRMATION
  -> CANDIDATE_READY
  -> AI_REVIEWED
  -> RISK_APPROVED | ABSTAINED
  -> ORDER_SUBMITTED
  -> ORDER_FILLED | ORDER_CANCELLED | ORDER_REJECTED
  -> MONITORING
  -> CLOSED
```

Re-running a job after a process crash must not create duplicate orders. Persist state transitions before irreversible actions and reconcile submitted Alpaca order IDs on restart.

## 16. Error handling and fail-closed behavior

ClockCross must prefer abstention over uncertain execution.

Fail closed on:

- missing required market data;
- stale timestamps;
- market calendar ambiguity;
- incomplete option chain;
- unavailable or malformed AI response;
- inconsistent account state;
- duplicate episode execution;
- Alpaca API authentication failure;
- order status that cannot be reconciled;
- risk-limit calculation failure.

Transient data/API failures may be retried with bounded exponential backoff. Order submission retries require idempotency/reconciliation logic so a timeout cannot produce a duplicate trade.

## 17. User-facing demo

The UI is deliberately small. It is a judge-facing evidence console, not a consumer trading terminal.

Required surfaces:

1. **Current status**
   - competition account equity/P&L
   - active positions
   - latest scheduler state
2. **Latest decision episode**
   - BTC move
   - expected equity move
   - premarket move
   - residual
   - opening confirmation
   - evidence gate
   - AI action/reason
   - risk result
3. **Decision history**
   - trades and abstentions
   - P&L / outcome when available
4. **Research evidence**
   - compact chronological validation summary
   - baseline/control comparison
   - limitations

Avoid account-management screens, strategy builders, auth systems, social features, billing, mobile apps, or decorative dashboards.

## 18. Testing strategy

The implementation must be test-first for decision logic and risk gates.

Required test categories:

- pure unit tests for return/residual calculations;
- chronological split / leakage tests;
- feature-freeze timestamp tests;
- LLM schema and fail-closed tests;
- option-spread contract validation tests;
- max-loss and portfolio-risk tests;
- stale-quote rejection tests;
- state-machine idempotency tests;
- duplicate-order/reconciliation tests;
- Alpaca adapter tests using fakes/mocks;
- development-account integration smoke tests;
- one end-to-end dry-run that cannot send a live-money order.

No test suite may require real competition credentials in CI.

## 19. Deployment constraints

Deployment must be minimal and observable.

Requirements:

- a continuously reachable demo URL by submission time;
- one scheduler/worker process with durable state;
- structured logs;
- environment-based secrets;
- explicit paper-trading guard at startup;
- health/readiness endpoint;
- deterministic timezone handling;
- process restart must reconcile state before resuming.

Do not introduce PostgreSQL, Redis, queues, or a multi-service topology unless the simplest durable-state approach proves insufficient. SQLite or another small persistent store is acceptable for the competition if deployment semantics are reliable.

## 20. Scope exclusions

The following are explicitly out of scope for the MVP:

- live-money trading;
- 0DTE strategies;
- naked options;
- portfolio optimization across dozens of assets;
- broad stock screening;
- high-frequency trading;
- reinforcement learning;
- multi-agent debate architecture;
- user accounts/authentication;
- billing;
- strategy marketplace;
- copy trading;
- generic trading platform APIs;
- automated social posting;
- TrendPulse integration unless Alpaca news proves insufficient;
- ETH features unless ablation proves incremental value;
- large indicator libraries.

## 21. Implementation order

The implementation must proceed in this order:

1. Research/falsification harness and historical data contracts.
2. Decide GO / MUTATE / KILL for the residual hypothesis.
3. Freeze a minimal validated signal specification.
4. Implement Alpaca data adapters and typed domain models.
5. Implement AI adjudicator with schema validation.
6. Implement deterministic options constructor and risk governor.
7. Implement durable state machine and decision ledger.
8. Integrate development paper-account execution.
9. Build the minimal judge-facing dashboard.
10. Create and verify the fresh `$100,000` competition account.
11. Start autonomous competition operation.
12. Freeze trading logic except for correctness/safety fixes; document any post-start change.
13. Produce evidence-heavy README, one-page technical write-up, video, slides, and submission.

No dashboard work should begin before the core signal survives the falsification stage.

## 22. Decision-change policy during the competition

Once autonomous trading starts on the competition account:

- do not retune a model because a trade lost;
- do not manually choose trades;
- do not reset the account;
- do not silently change thresholds;
- correctness and safety fixes are allowed, but must be committed and described in the ledger/changelog;
- a strategy mutation based on newly accumulated evidence must be explicit, reproducible, and not retroactively applied to prior episodes.

This protects both judging credibility and the usefulness of the project after the hackathon.

## 23. Submission evidence package

By submission, the repository should contain enough evidence to answer these questions without hand-waving:

- What exactly is the cross-market hypothesis?
- What data existed at decision time?
- How was leakage prevented?
- What historical evidence promoted or rejected the signal?
- What meaningful decision did the AI make?
- What could the AI not override?
- Why was each option spread legal under the risk policy?
- Which Alpaca APIs/MCP tools were used?
- What trades and abstentions occurred on the dedicated account?
- What was actual paper P&L?
- What failed during development?
- What limitations remain?

Negative results and abstentions should be published where they improve credibility.

## 24. References used to freeze the design

- Alpaca Paper Trading: https://docs.alpaca.markets/us/docs/paper-trading
- Alpaca Options Trading: https://docs.alpaca.markets/us/docs/options-trading
- Alpaca Trading MCP Server: https://docs.alpaca.markets/us/docs/alpaca-mcp-server
- Alpaca Historical Option Data: https://docs.alpaca.markets/us/docs/historical-option-data
- Alpaca Option Chain API: https://docs.alpaca.markets/us/v1.1/reference/optionchain
- Alpaca AI Trading Agents Hackathon: https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon
