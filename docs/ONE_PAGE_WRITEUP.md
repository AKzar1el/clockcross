# ClockCross — AI Logic, Risk Gates, and Alpaca Infrastructure

## Thesis

ClockCross tests whether 24/7 BTC price discovery leaves a temporary, measurable residual in Coinbase (`COIN`) after U.S. premarket repricing. It does **not** assume that an overnight BTC move is unpriced. At 09:25 ET it estimates COIN's expected premarket return from a rolling BTC/COIN beta and computes:

`residual = actual COIN premarket return - beta × BTC return`

Research uses chronological windows only. Current-day observations never enter the beta used for that day. The first real Alpaca run (2025-01-02 to 2026-08-28) returned `MUTATE`: COIN had 82 OOS signals at +27.46 bps mean signed underlying return, while QQQ control was -1.56 bps. The decisive regime split was COIN's 2026 subset (+84.07 bps over 38 signals) versus MSTR's deterioration (-22.72 bps in 2026). Both failed the deliberately severe 100 bps underlying-friction gate, so that failure remains published.

The approved mutation makes **COIN the only execution candidate**. MSTR remains negative/rejection evidence and QQQ remains a control. The live policy is frozen at the modal recent configuration: 40-session beta, raw residual, 1% threshold. There is no live hyperparameter search.

After the first real competition episode, ClockCross ran a literal chronological replay of the final policy over 128 actual Alpaca market days from March 2 through September 1, 2026. It generated 39 signals, 36 AI trades, 3 AI abstentions, 6 data abstentions, and 83 threshold abstentions. The current AI finished 21-15 (58.3%) with +50.7 bps mean chosen-direction 60-minute COIN return versus frozen continuation at 22-17 with +15.9 bps mean. June (-38.3 bps) and July (-57.1 bps) remained negative AI regimes and were intentionally preserved rather than tuned away. These are directional underlying-return diagnostics, not compounded account returns or exact historical options P&L.

## Autonomous AI logic

At approximately 09:55 ET, ClockCross has only information that would have been available under Alpaca Basic's delayed consolidated-data boundary. A signal must first pass deterministic cross-market evidence and current 7–21 DTE option-chain feasibility.

Only then does ClockCross collect read-only Alpaca MCP context and send a bounded structured context to an authenticated Cloudflare Workers AI gateway. The gateway fixes the underlying model to Llama 3.3 70B fast and asks Workers AI for the exact five-field ClockCross JSON schema. The Worker validates that schema before returning an OpenAI-compatible response; the Python adjudicator validates it again with Pydantic.

The model may choose exactly `continuation`, `reversion`, or `abstain`. If company-specific COIN news plausibly explains the residual, context is ambiguous, the response is malformed, or the model/provider fails, ClockCross abstains.

The model cannot choose symbols or contracts, change risk limits, bypass quote freshness, choose order prices or exits, or place an order. Client requests also cannot change the gateway's underlying model or output schema.

A 69-call replay of all 23 recent-quarter signal contexts produced 23/23 unanimous action contexts and zero action-flip contexts. Confidence/reason text could vary, but the bounded action did not. That evidence rejected adding majority voting or changing the model merely to make the backtest look more stable.

## Option and risk gates

ClockCross permits only 1:1 defined-risk COIN vertical debit spreads with 7–21 DTE. The option surface must have non-zero, non-crossed, sufficiently fresh quotes and acceptable relative spreads. The long leg must have approximately **0.45–0.65 absolute delta**. For that long leg, the constructor evaluates quote-eligible farther-OTM shorts at the same expiration, requires the short leg to retain at least **0.10 absolute delta**, requires at least **0.30 absolute net directional delta**, rejects any debit above the one-contract budget implied by the existing risk envelope, and deterministically ranks surviving verticals by net directional delta per debit. If no structure provides meaningful directional exposure safely, ClockCross abstains. The constructor uses conservative executable economics: long-leg ask minus short-leg bid, and rejects net debit that is non-positive or reaches/exceeds spread width.

The 0.10 short-delta floor is the only production change promoted from the post-episode backtest. Historical reconstruction exposed an optimizer pathology that could prefer ~0.00–0.02-delta lottery shorts and 50–60 point-wide spreads. The floor retained candidates on all five recent signal days, improved historical entry-print coverage from 40% to 80%, improved exit-print coverage from 20% to 40%, reduced mean width from 56.9 to 29.4 points, and preserved mean net delta near 0.370. A 12,000-trial post-fix live indicative-surface stress remained constructible in both directions with zero risk-invariant violations.

Historical option bars/trades do not reproduce arbitrary past snapshot BBO/Greeks. Accordingly, ClockCross does not claim an exact options-fill backtest. On the two recent days with prints on both selected legs, the post-fix 09:55–10:55 proxy was +$120 raw / +$100 after a $0.20 spread-friction stress on August 18 and +$59 raw / +$39 after the same stress on August 21. August 7, August 24, and September 1 remain unobservable at the full-spread historical-print level and are not labeled wins or losses.

The live constructor enforces only fields actually supplied by the normalized Alpaca snapshot path: quote freshness, positive/non-crossed bid/ask, relative-spread quality, available delta, vertical economics and downstream buying-power/max-loss limits. It does not claim open-interest or volume gates that are absent from that live snapshot. The chosen candidate's long delta, short delta, net delta, net debit and delta-per-debit are written to the durable ledger.

The deterministic governor then checks approved underlying, one-position-per-underlying, quote freshness, buying power, entry window, final-event cutoff, maximum loss, and aggregate defined loss. Default caps remain 1% of starting equity per new position and 5% aggregate. No 0DTE or naked short options are allowed. Competition entries are limited to 09:55–10:05 ET.

## Alpaca infrastructure and lifecycle

Alpaca provides the source market data, account state, current option chain, paper brokerage, and MCP context. Historical equities use SIP. At the live 09:55 decision, historical-bar reconstruction requests SIP only through 09:40 ET, reproducing the 15-minute-delayed information boundary without using future bars.

On Alpaca Basic, ClockCross's option-chain selection input is the `indicative` feed rather than paid OPRA. That is treated as a known information-quality limitation: the constructor uses the current indicative snapshots/Greeks for bounded structure selection, while the risk envelope and fail-closed execution logic do not assume those quotes are equivalent to official OPRA/NBBO execution data.

Alpaca MCP is deliberately configured without its trading toolset; it is an auditable context surface, not an execution backdoor. Opening execution uses the Alpaca Trading REST API with `order_class=mleg`, a positive debit limit price, and explicit `buy_to_open` / `sell_to_open` legs.

An opening order has a fixed 180-second fill window. If it does not fill, ClockCross cancels the exact parent order and requires cancellation to be proven. A filled spread is held to **10:55 ET**, matching the frozen `forward_60m_return` research horizon from the 09:55 decision. The exit reuses the exact two opening contracts in a closing MLeg with `sell_to_close` / `buy_to_close`. The close is deterministic, uses fresh quotes, and permits at most one fixed replacement attempt; the LLM has no authority over the exit.

Every episode is persisted in SQLite, including abstentions. Every opening and closing order gets a deterministic `client_order_id`. ClockCross queries that ID before submission. If a network timeout makes submission uncertain, it queries again; if the order still cannot be proven, no blind retry occurs. Restart recovery uses the persisted episode/order identity and does not recompute a new signal. An unresolved prior COIN lifecycle blocks a new competition entry.

The checked-in competition workflow restores the prior SQLite artifact and runs read-only preflight before the autonomous competition lifecycle. The canonical launcher is a path-scoped push on `main` (`ops/competition-run-now`) with `workflow_dispatch` as a recovery trigger. The workflow and runtime reject non-event dates, and ClockCross itself enforces the 09:55–10:05 ET entry boundary. Encrypted Alpaca/gateway credentials are scoped to the GitHub `competition` environment and are not stored in the repository.

## Verified external evidence

On 2026-08-30, the exact `clockcross preflight` command ran in an encrypted cloud job against the development paper account and passed all five external surfaces: account active/unblocked, options approved/trading Level 3, 416 COIN contracts in the 7–21 DTE window via the indicative feed, Alpaca MCP `get_clock`, and a schema-valid bounded AI decision through the deployed Cloudflare gateway. The preflight creates no episode and has no order path.

On 2026-09-01, the same external preflight passed against the dedicated competition account immediately before the first real autonomous competition episode. The opening MLeg filled; the deterministic 10:55 research-horizon exit filled on its first close attempt; and the persisted lifecycle finished `CLOSED` with reason `research_horizon_exit_filled`. No unresolved opening/closing order remained and no undocumented manual trade-selection intervention occurred.

## Competition-account discipline

Development order tests use a separate Alpaca paper account and require an explicit opt-in flag. Competition mode rejects that flag. Before its first episode, the dedicated judging account had to be active, unblocked, options Level 3, have no open positions, and have exactly `$100,000` equity. The original research verdict remains `MUTATE`; the approved mutation and the later 0.10 short-delta structural correction are tracked explicitly rather than rewriting history.

The first real competition episode is externally proven. Final event account equity/P&L is captured from the dedicated competition account before submission and is kept distinct from underlying-direction diagnostics and historical option-print proxies.
