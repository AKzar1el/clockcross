# ClockCross Submission Package

<p align="center">
  <img src="../deploy/cloudflare-demo/public/hackathon-cover.png" alt="ClockCross hackathon cover" width="1000">
</p>

Canonical copy-and-asset handoff for the Alpaca AI Trading Agents Hackathon submission.

> Keep the project evidence-first. Do not replace `MUTATE` with a stronger claim, do not imply live-money trading, do not convert underlying-direction diagnostics into account returns, and do not invent historical option fills where Alpaca does not expose arbitrary-past snapshot BBO/Greeks.

## Project title

**ClockCross — Evidence-Gated Autonomous Options Agent**

## Short description

ClockCross turns BTC-to-COIN repricing gaps into bounded Alpaca option spreads only after chronological falsification, bounded AI adjudication, and deterministic risk gates.

## Long description

ClockCross is an autonomous AI options-trading agent built for the Alpaca AI Trading Agents Hackathon. It starts from a specific cross-market timing question: BTC trades continuously while U.S. equity options do not. Instead of blindly following overnight BTC direction, ClockCross estimates COIN's expected premarket move from prior-session BTC/COIN beta and trades only the unexplained residual that survives deterministic evidence gates.

The research process is deliberately falsification-first. The first real Alpaca historical run returned `MUTATE`, not `GO`: COIN retained useful out-of-sample evidence, MSTR weakened materially in 2026, QQQ remained a broad-market control, and the intentionally severe 100 bps underlying-friction gate failed. ClockCross preserved that negative evidence and narrowed execution to COIN instead of tuning until the broad thesis looked positive.

After the first autonomous competition episode, ClockCross ran a literal six-month chronological replay of the final decision policy over 128 actual Alpaca market days. It produced 39 signals, 36 AI trades, 3 AI abstentions, 6 data abstentions, and 83 threshold abstentions. The current AI finished 21-15 with a 58.3% directional hit rate and +50.7 bps mean chosen-direction 60-minute COIN return versus frozen continuation at 22-17 and +15.9 bps mean. June (-38.3 bps) and July (-57.1 bps) remained losing AI regimes and are shown explicitly rather than tuned away. These are underlying-return diagnostics, not compounded account returns.

The backtest also found a real production-selection defect. The existing net-delta/debit objective could prefer extremely far-OTM ~0.00-0.02-delta shorts, producing 50-60 point-wide spreads with weak historical short-leg print coverage. ClockCross promoted exactly one structural fix: a **0.10 minimum absolute short-leg delta** applied consistently to option feasibility and deterministic construction. It retained candidates on all five recent signal days, improved historical entry-print coverage from 40% to 80%, reduced mean width from 56.9 to 29.4 points, and preserved mean net delta near 0.370. A 12,000-trial post-fix indicative-surface stress produced zero risk-invariant violations. Signal threshold, beta, AI prompt/model, risk budget, decision window, and 10:55 exit remained frozen.

Before the final competition session, ClockCross also used Featherless to test whether a second model provider could improve the trading policy. Phase 1 surfaced an apparent +11.74 bps improvement from a GLM-5.3 consensus filter, but the result failed a fresh frozen replication: Phase 2 measured the same policy at -3.31 bps versus the incumbent. A broader predeclared Phase-2 search across Qwen, Kimi, GPT-OSS, Gemma, Fin-R1, GLM-5.3 and additional contract-screen candidates produced **zero policies that beat the incumbent and clear the robustness/multiple-testing promotion gates**. ClockCross therefore did not promote a more exciting-looking model after seeing the result. Featherless remains a non-blocking GLM-5.3 shadow observer that records model agreement/disagreement but cannot create, veto, reverse, resize, or delay trades.

A live episode checks the cross-market signal, opening confirmation, and a current 7–21 DTE COIN option chain, gathers read-only Alpaca MCP context, and asks a schema-bounded Cloudflare-hosted AI adjudicator for exactly one of three outputs: `continuation`, `reversion`, or `abstain`. The model cannot choose symbols, contracts, DTE, sizing, order prices, or exits. A deterministic spread constructor enforces approximately 0.45–0.65 absolute long delta, at least 0.10 absolute short delta, at least 0.30 absolute net directional delta, defined-risk debit economics, and the existing risk-derived one-contract budget.

Competition entries are restricted to 09:55–10:05 ET. An opening Alpaca MLeg gets a fixed 180-second fill window and is canceled only when cancellation can be proven. A filled position exits at 10:55 ET using the exact opening contracts in a deterministic closing MLeg. Lifecycle state is persisted in SQLite so restarts reconcile known order identities instead of recomputing a signal or blindly retrying an ambiguous order.

The first real competition episode ran on **2026-09-01**: the dedicated account passed preflight, the opening MLeg filled, the deterministic research-horizon close filled on its first close attempt, and the persisted lifecycle finished `CLOSED`. No unresolved opening/closing order remained and no undocumented manual trade-selection intervention occurred. This remains paper trading; final competition equity/P&L must come from the dedicated event account rather than from research diagnostics or proxy returns.

The repository also contains an independent final-session launcher design: a one-purpose Cloudflare Worker scheduled for Sep 4 at 09:30 ET that dispatches the GitHub competition workflow. GitHub retains 09:35 ET and 09:45 ET schedule fallbacks, plus path-scoped push and manual `workflow_dispatch` recovery. The Worker code has an exact-date guard and no-retry behavior, but deployment and secret configuration are external operational state and must be verified separately rather than inferred from source control.

The public judge demo is deliberately static and zero-secret. It exposes the falsification record, six-month replay, losing regimes, backtest-discovered constructor defect, bounded fix, Featherless non-promotion evidence, Alpaca integration, deterministic risk envelope, and verified competition lifecycle without exposing trading controls, credentials, or a live account connection.

## Historical option proxy — disclosure wording

Alpaca historical option bars/trades do not reproduce arbitrary-past snapshot BBO/Greeks, so ClockCross does **not** claim an exact historical options-fill backtest. Historical trade prints are used only as a transparent price/liquidity proxy.

After the 0.10 short-delta fix, two recent signal days had enough prints on both selected legs for a full 09:55–10:55 proxy:

- **2026-08-18:** +$120 raw / +$100 after a $0.20 spread-friction stress.
- **2026-08-21:** +$59 raw / +$39 after the same stress.
- **2026-08-07, 2026-08-24, 2026-09-01:** insufficient prints on both selected legs; label **unobservable**, never win/loss.

## Featherless disclosure wording

Use this wording if judges ask what Featherless changed:

> Featherless did not replace the production trading model. We used it to run a predeclared model-selection and replication study before the final session. An initial GLM-5.3 result looked better, but it failed the frozen replication and broader robustness gates. We preserved that negative result and kept GLM-5.3 as a non-blocking shadow observer for model-risk evidence only.

Do **not** claim Featherless improved P&L or trading accuracy. The research conclusion is the opposite: no tested Featherless-hosted policy earned production authority.

## Suggested technology / category tags

- AI Agents
- Algorithmic Trading
- Options Trading
- FinTech
- Alpaca
- Alpaca MCP
- Featherless AI
- Python
- FastAPI
- Cloudflare Workers AI
- Cloudflare Workers
- Llama 3.3 70B
- GLM-5.3
- SQLite

## Required links

- **Public GitHub repository:** https://github.com/AKzar1el/clockcross
- **Judge demo platform:** Cloudflare Workers Static Assets
- **Judge demo URL:** https://clockcross-demo.tomi-seregi99.workers.dev
- **Six-month chronological replay:** `docs/research/2026-09-01-end-to-end-backtest.md`
- **Featherless Phase-2 verdict:** `docs/research/2026-09-04-featherless-phase2.md`
- **One-page technical write-up:** `docs/ONE_PAGE_WRITEUP.md`
- **Operations / account discipline:** `docs/OPERATIONS.md`
- **Submission gate:** `docs/SUBMISSION_CHECKLIST.md`

## Image placement map

### Lablab cover image

Use **`hackathon-cover.png`** — 1600×900 PNG.

<p align="center">
  <img src="../deploy/cloudflare-demo/public/hackathon-cover.png" alt="ClockCross 16:9 hackathon cover" width="900">
</p>

- Repository source: `deploy/cloudflare-demo/public/hackathon-cover.png`
- Public HTTPS asset: https://clockcross-demo.tomi-seregi99.workers.dev/hackathon-cover.png
- SVG master: `deploy/cloudflare-demo/public/hackathon-cover.svg`

### Website / link preview image

Use **`og-image.png`** — 1200×630 PNG.

<p align="center">
  <img src="../deploy/cloudflare-demo/public/og-image.png" alt="ClockCross social and Open Graph preview" width="800">
</p>

- Repository source: `deploy/cloudflare-demo/public/og-image.png`
- Public HTTPS asset: https://clockcross-demo.tomi-seregi99.workers.dev/og-image.png
- SVG master: `deploy/cloudflare-demo/public/og-image.svg`

### GitHub social preview

Recommended asset: `deploy/cloudflare-demo/public/og-image.png`.

Upload manually under **Repository → Settings → Social preview → Edit → Upload an image**. The tracked 1200×630 PNG is suitable for the repository preview.

### Logo / application identity

<p align="center">
  <img src="../deploy/cloudflare-demo/public/logo-wordmark.svg" alt="ClockCross wordmark" width="420">
</p>

- Wordmark: `deploy/cloudflare-demo/public/logo-wordmark.svg`
- Mark: `deploy/cloudflare-demo/public/logo-mark.svg`
- Browser favicon: `deploy/cloudflare-demo/public/favicon.svg`
- Multi-size favicon: `deploy/cloudflare-demo/public/favicon.ico`
- Apple touch icon: `deploy/cloudflare-demo/public/apple-touch-icon.png`
- PWA icons: `deploy/cloudflare-demo/public/icon-192.png`, `deploy/cloudflare-demo/public/icon-512.png`
- Manifest: `deploy/cloudflare-demo/public/site.webmanifest`

## Video presentation structure

Lablab's current submission guidance requires a working prototype URL, public GitHub repository, pitch deck, and a video presentation no longer than five minutes. Keep ClockCross around **4:15–4:40** so the evidence is clear without rushing.

The differentiation is not “another AI trading dashboard.” It is a system that repeatedly tried to falsify its own strategy, found and fixed one structural execution defect, rejected an attractive model result when it failed replication, and still executed autonomously inside deterministic risk boundaries.

1. **0:00–0:25 — Hook / thesis**  
   BTC trades 24/7; COIN options do not. ClockCross measures the unexplained repricing gap rather than blindly following BTC.
2. **0:25–0:55 — The system was allowed to say no**  
   Show the first Alpaca run returning `MUTATE`, MSTR deterioration, QQQ control, and the failed 100 bps gate.
3. **0:55–1:30 — Literal six-month replay**  
   Show 128 market days, 39 signals, 36 AI trades, 21-15, 58.3%, +50.7 bps mean chosen-direction return, and explicitly show June/July losing regimes.
4. **1:30–2:05 — The backtest found a production bug**  
   Show the near-zero-delta lottery-short defect, the narrow 0.10 short-delta correction, coverage/width improvement, and 12,000-trial post-fix stress.
5. **2:05–2:35 — We tried to replace the AI and rejected the apparent winner**  
   Show Featherless Phase 1: GLM-5.3 consensus +11.74 bps apparent improvement. Then Phase 2: -3.31 bps replication, zero promoted candidates. One sentence: “Featherless became a shadow model-risk observer, not the trader.”
6. **2:35–3:15 — Bounded autonomous pipeline**  
   Residual → confirmation → option feasibility → read-only Alpaca MCP → bounded Cloudflare AI → deterministic constructor/risk → Alpaca MLeg → durable lifecycle. Explicitly show that neither AI can directly submit an order.
7. **3:15–3:45 — Real competition episode**  
   Show 2026-09-01 preflight, opening MLeg fill, deterministic 10:55 exact-contract close, and terminal `CLOSED` state.
8. **3:45–4:10 — Reliability**  
   Show the checked-in independent Cloudflare Cron launcher design, GitHub scheduled fallbacks, durable SQLite restoration, idempotent client IDs, and deterministic recovery. Only call the Cloudflare trigger “deployed” in the video if deployment/secret state has been verified externally.
9. **4:10–4:30 — Close**  
   “ClockCross is designed to reject weak evidence, expose losing regimes, and keep AI inside a deterministic defined-risk envelope—even when the more exciting model result looks better at first.”

### Video capture priority

Judges should see these screens/artifacts, in roughly this order:

- public judge demo hero + architecture;
- `MUTATE` / COIN-MSTR-QQQ evidence;
- six-month replay summary with losing regimes visible;
- constructor defect + 0.10 short-delta correction;
- Featherless Phase-2 no-promotion result;
- autonomous architecture / bounded AI authority;
- Sep 1 `CLOSED` competition evidence;
- final competition account/trade evidence if available before recording/export.

Avoid spending video time on source-code scrolling unless a single file proves an important authority boundary. The public demo and committed research artifacts are stronger judge-facing evidence.

## Slide-deck content map

Keep the deck concise; the video should do most of the storytelling.

1. **ClockCross** — one-line thesis + cover visual.
2. **The timing problem** — BTC 24/7 vs U.S. option hours; residual rather than naive overnight following.
3. **Research can reject the thesis** — frozen `MUTATE`, COIN/MSTR/QQQ, failed 100 bps gate.
4. **Six-month chronological replay** — 128 market days, 36 AI trades, 3 AI abstentions, 21-15, 58.3%, +50.7 bps; June/July negative regimes visible.
5. **The backtest found a production bug** — near-zero-delta shorts and the 0.10 structural correction.
6. **Featherless replication test** — apparent Phase-1 GLM edge, failed Phase-2 replication, no promotion, shadow-only model-risk observer.
7. **Autonomous system** — end-to-end architecture diagram including Cloudflare authoritative AI and Featherless shadow-only path.
8. **AI is bounded** — continuation / reversion / abstain; deterministic authority boundaries.
9. **Defined-risk lifecycle** — 7–21 DTE COIN debit spreads, delta gates, risk caps, bounded fill, 10:55 exit, idempotency/recovery.
10. **Alpaca + competition proof** — historical/market data, read-only MCP, Trading API MLegs, Sep 1 `CLOSED` lifecycle, independent-launcher design, final account equity/P&L when available.

## Submission-media constraints

Current general Lablab submission guidance says a complete project submission should include:

- a working prototype accessible by URL;
- a public GitHub repository;
- a pitch video **no longer than 5 minutes**;
- a slide deck / pitch deck;
- the project cover and descriptive fields.

The Lablab hackathon-guidelines article additionally says the video upload/link should be **under 300 MB**. Export with comfortable margin below both limits.

## Final fields still pending external/user evidence

- Dedicated competition Alpaca paper account identifier for the submission form.
- Final competition account P&L/equity after the event run is complete.
- Final selected competition trade/abstention screenshots.
- Video URL.
- Slide-deck URL/file.
- Lablab submission URL.

## Final repository handoff

The production trading policy is frozen. The Featherless studies did not earn a trading-authority change; GLM-5.3 remains shadow-only. The 0.10 short-delta floor remains the only promoted structural constructor correction from the post-episode replay. Signal, AI action set, COIN-only universe, 7–21 DTE window, one-contract sizing, 1%/5% defined-loss envelope, 09:55–10:05 decision window, MLeg lifecycle, and 10:55 ET exit remain unchanged.

The repository contains the intended final-session scheduling topology: **Cloudflare Cron primary design → GitHub `workflow_dispatch`**, with GitHub 09:35/09:45 ET schedules retained as fallback triggers. Path-scoped `ops/competition-run-now` push and manual dispatch remain recovery paths. Do not claim the Cloudflare Worker is live unless its deployment and secret configuration have been verified outside Git.

From this point, stop strategy/model engineering unless an actual correctness defect is discovered. The remaining competition work is presentation and submission: capture final evidence, record/export the video, build the pitch deck, enter the Lablab fields, and submit before the recorded competition deadline.
