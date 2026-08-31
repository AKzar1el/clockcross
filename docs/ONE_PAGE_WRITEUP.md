# ClockCross — AI Logic, Risk Gates, and Alpaca Infrastructure

## Thesis

ClockCross tests whether 24/7 BTC price discovery leaves a temporary, measurable residual in Coinbase (`COIN`) after U.S. premarket repricing. It does **not** assume that an overnight BTC move is unpriced. At 09:25 ET it estimates COIN's expected premarket return from a rolling BTC/COIN beta and computes:

`residual = actual COIN premarket return - beta × BTC return`

Research uses chronological windows only. Current-day observations never enter the beta used for that day. The first real Alpaca run (2025-01-02 to 2026-08-28) returned `MUTATE`: COIN had 82 OOS signals at +27.46 bps mean signed underlying return, while QQQ control was -1.56 bps. The decisive regime split was COIN's 2026 subset (+84.07 bps over 38 signals) versus MSTR's deterioration (-22.72 bps in 2026). Both failed the deliberately severe 100 bps underlying-friction gate, so that failure remains published.

The approved mutation makes **COIN the only execution candidate**. MSTR remains negative/rejection evidence and QQQ remains a control. The live policy is frozen at the modal recent continuation configuration: 40-session beta, raw residual, 1% threshold. There is no live hyperparameter search.

## Autonomous AI logic

At approximately 09:55 ET, ClockCross has only information that would have been available under Alpaca Basic's delayed consolidated-data boundary. A signal must first pass deterministic cross-market evidence and current 7–21 DTE option-chain feasibility.

Only then does ClockCross collect read-only Alpaca MCP context and send a bounded structured context to an authenticated Cloudflare Workers AI gateway. The gateway fixes the underlying model to Llama 3.3 70B fast and asks Workers AI for the exact five-field ClockCross JSON schema. The Worker validates that schema before returning an OpenAI-compatible response; the Python adjudicator validates it again with Pydantic.

The model may choose exactly `continuation`, `reversion`, or `abstain`. If company-specific COIN news plausibly explains the residual, context is ambiguous, the response is malformed, or the model/provider fails, ClockCross abstains.

The model cannot choose symbols or contracts, change risk limits, bypass quote freshness, choose order prices or exits, or place an order. Client requests also cannot change the gateway's underlying model or output schema.

## Option and risk gates

ClockCross permits only 1:1 defined-risk COIN vertical debit spreads with 7–21 DTE. The option surface must have non-zero, non-crossed, sufficiently fresh quotes and acceptable relative spreads. Delta-based selection targets roughly 0.55 absolute delta for the long leg and 0.35 for the short leg. The constructor uses conservative executable economics: long-leg ask minus short-leg bid. A candidate is rejected if net debit is non-positive or reaches/exceeds spread width.

The live constructor enforces only fields actually supplied by the normalized Alpaca snapshot path: quote freshness, positive/non-crossed bid/ask, relative-spread quality, available delta, vertical economics and downstream buying-power/max-loss limits. It does not claim open-interest or volume gates that are absent from that live snapshot.

The deterministic governor then checks approved underlying, one-position-per-underlying, quote freshness, buying power, entry window, final-event cutoff, maximum loss, and aggregate defined loss. Default caps are 1% of starting equity per new position and 5% aggregate. No 0DTE or naked short options are allowed. Competition entries are limited to 09:55–10:05 ET.

## Alpaca infrastructure and lifecycle

Alpaca provides the source market data, account state, current option chain, paper brokerage, and MCP context. Historical equities use SIP. At the live 09:55 decision, historical-bar reconstruction requests SIP only through 09:40 ET, reproducing the 15-minute-delayed information boundary without using future bars.

Alpaca MCP is deliberately configured without its trading toolset; it is an auditable context surface, not an execution backdoor. Opening execution uses the Alpaca Trading REST API with `order_class=mleg`, a positive debit limit price, and explicit `buy_to_open` / `sell_to_open` legs.

An opening order has a fixed 180-second fill window. If it does not fill, ClockCross cancels the exact parent order and requires cancellation to be proven. A filled spread is held to **10:55 ET**, matching the frozen `forward_60m_return` research horizon from the 09:55 decision. The exit reuses the exact two opening contracts in a closing MLeg with `sell_to_close` / `buy_to_close`. The close is deterministic, uses fresh quotes, and permits at most one fixed replacement attempt; the LLM has no authority over the exit.

Every episode is persisted in SQLite, including abstentions. Every opening and closing order gets a deterministic `client_order_id`. ClockCross queries that ID before submission. If a network timeout makes submission uncertain, it queries again; if the order still cannot be proven, no blind retry occurs. Restart recovery uses the persisted episode/order identity and does not recompute a new signal. An unresolved prior COIN lifecycle blocks a new competition entry.

The checked-in competition workflow restores the prior SQLite artifact, runs read-only preflight first, then launches the autonomous competition lifecycle at 09:57 America/New_York on the five event dates. Encrypted Alpaca/gateway credentials are scoped to the GitHub `competition` environment and are not stored in the repository.

## Verified external preflight

On 2026-08-30, the exact `clockcross preflight` command ran in an encrypted cloud job against the development paper account and passed all five external surfaces: account active/unblocked, options approved/trading Level 3, 416 COIN contracts in the 7–21 DTE window via the indicative feed, Alpaca MCP `get_clock`, and a schema-valid bounded AI decision through the deployed Cloudflare gateway. The preflight creates no episode and has no order path.

## Competition-account discipline

Development order tests use a separate Alpaca paper account and require an explicit opt-in flag. Competition mode rejects that flag. Before its first episode, the dedicated judging account must be active, unblocked, options Level 3, have no open positions, and have exactly `$100,000` equity. The original research verdict remains `MUTATE`; the approved mutation is tracked explicitly rather than rewriting history.

The open-market development MLeg submit/cancel proof and the first real competition episode remain external Monday checks; this document does not claim either has occurred before they actually do.
