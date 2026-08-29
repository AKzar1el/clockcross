# ClockCross — AI Logic, Risk Gates, and Alpaca Infrastructure

## Thesis

ClockCross tests whether 24/7 BTC price discovery leaves a temporary, measurable residual in Coinbase (`COIN`) after U.S. premarket repricing. It does **not** assume that an overnight BTC move is unpriced. At 09:25 ET it estimates COIN's expected premarket return from a rolling BTC/COIN beta and computes:

`residual = actual COIN premarket return - beta × BTC return`

Research uses chronological windows only. Current-day observations never enter the beta used for that day. The first real Alpaca run (2025-01-02 to 2026-08-28) returned `MUTATE`: COIN had 82 OOS signals at +27.46 bps mean signed underlying return, while QQQ control was -1.56 bps. The decisive regime split was COIN's 2026 subset (+84.07 bps over 38 signals) versus MSTR's deterioration (-22.72 bps in 2026). Both failed the deliberately severe 100 bps underlying-friction gate, so that failure remains published.

The approved mutation makes **COIN the only execution candidate**. MSTR remains negative/rejection evidence and QQQ remains a control. The live policy is frozen at the modal recent continuation configuration: 40-session beta, raw residual, 1% threshold. There is no live hyperparameter search.

## Autonomous AI logic

At approximately 09:55 ET, ClockCross has only information that would have been available under Alpaca Basic's delayed consolidated-data boundary. A signal must first pass deterministic cross-market evidence and current 7–21 DTE option-chain feasibility.

Only then does ClockCross collect read-only Alpaca MCP context (market clock/news) and send a bounded structured context to an OpenAI-compatible Featherless model. The model may choose exactly `continuation`, `reversion`, or `abstain`. If company-specific COIN news plausibly explains the residual, context is ambiguous, the response is malformed, or the model/provider fails, ClockCross abstains.

The model cannot choose symbols or contracts, change risk limits, bypass quote freshness, or place an order.

## Option and risk gates

ClockCross permits only 1:1 defined-risk COIN vertical debit spreads with 7–21 DTE. The option surface must have non-zero, non-crossed, sufficiently fresh quotes and acceptable relative spreads. Delta-based selection targets roughly 0.55 absolute delta for the long leg and 0.35 for the short leg. The constructor uses conservative executable economics: long-leg ask minus short-leg bid. A candidate is rejected if net debit is non-positive or reaches/exceeds spread width.

The deterministic governor then checks approved underlying, one-position-per-underlying, quote freshness, buying power, entry window, final-event cutoff, maximum loss, and aggregate defined loss. Default caps are 1% of starting equity per new position and 5% aggregate. No 0DTE or naked short options are allowed.

## Alpaca infrastructure

Alpaca provides the source market data, account state, current option chain, paper brokerage, and MCP context. Historical equities use SIP. At the live 09:55 decision, historical-bar reconstruction requests SIP only through 09:40 ET, reproducing the 15-minute-delayed information boundary without using future bars.

Alpaca MCP is deliberately configured without its trading toolset; it is an auditable context surface, not an execution backdoor. Multi-leg execution uses the Alpaca Trading REST API with `order_class=mleg`, a positive debit limit price, and explicit `buy_to_open` / `sell_to_open` legs.

Every episode is persisted in SQLite, including abstentions. Every order gets a deterministic `client_order_id`. ClockCross queries that ID before submission. If a network timeout makes submission uncertain, it queries again; if the order still cannot be proven, the episode becomes `indeterminate` and no blind retry occurs. Restart recovery reconciles the known order only and cannot recompute a new signal.

## Competition-account discipline

Development order tests use a separate Alpaca paper account and require an explicit opt-in flag. Competition mode rejects that flag. Before its first episode, the dedicated judging account must be active, unblocked, options Level 3, have no open positions, and have exactly `$100,000` equity. The original research verdict remains `MUTATE`; the approved mutation is tracked explicitly rather than rewriting history.
