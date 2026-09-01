# ClockCross Submission Package

<p align="center">
  <img src="../deploy/cloudflare-demo/public/hackathon-cover.png" alt="ClockCross hackathon cover" width="1000">
</p>

Canonical copy-and-asset handoff for the Alpaca AI Trading Agents Hackathon submission.

> Keep the project evidence-first. Do not replace `MUTATE` with a stronger claim, do not imply live-money trading, and do not claim final competition P&L before the dedicated competition account's event run is complete.

## Project title

**ClockCross — Evidence-Gated Autonomous Options Agent**

## Short description

ClockCross turns BTC-to-COIN repricing gaps into bounded, defined-risk Alpaca option spreads only after chronological evidence, AI adjudication, and deterministic risk gates.

## Long description

ClockCross is an autonomous AI options-trading agent built for the Alpaca AI Trading Agents Hackathon. It looks for a specific cross-market timing effect: BTC trades continuously, while U.S. equity options do not. Rather than assuming that an overnight BTC move predicts COIN at the open, ClockCross estimates the expected COIN premarket move from prior-session BTC/COIN beta and measures the unexplained residual.

The research process is deliberately falsification-first. The initial real Alpaca historical run returned `MUTATE`, not `GO`: COIN retained useful out-of-sample evidence, MSTR weakened materially in 2026, QQQ remained a broad-market control, and the intentionally severe 100 bps underlying-friction gate failed. ClockCross preserved that negative evidence and narrowed the execution universe to COIN instead of tuning until everything looked positive.

A live episode freezes the cross-market feature set, checks opening confirmation, validates a current 7–21 DTE COIN option chain, gathers read-only Alpaca MCP context, and asks a schema-bounded AI adjudicator for one of three outputs: continuation, reversion, or abstain. The model cannot choose symbols, contracts, DTE, sizing, order prices, or exits. A deterministic spread constructor then evaluates defined-risk 1:1 verticals inside the existing risk budget: the long leg must be approximately 0.45–0.65 absolute delta, the spread must retain at least 0.30 absolute net directional delta, and surviving farther-OTM shorts are ranked by net directional delta per debit. The deterministic risk governor still enforces position and portfolio loss caps before any paper MLeg order can be submitted.

Competition entries are restricted to the frozen 09:55–10:05 ET decision window. An opening order gets a fixed 180-second fill window and is canceled only when cancellation can be proven. A filled position exits at 10:55 ET, matching the frozen 60-minute research horizon, using the exact opening contracts in a deterministic closing MLeg. Opening and closing lifecycle state is persisted in SQLite so a restart reconciles known order identities instead of recomputing a new signal.

The first real competition episode ran on 2026-09-01: read-only preflight passed, the opening MLeg filled, the deterministic research-horizon close filled on its first close attempt, and the persisted lifecycle finished `CLOSED`. This remains paper trading; final event P&L must be reported from the dedicated competition account rather than inferred from research or a single episode.

The public judge demo exposes the frozen research result, negative evidence, architecture, risk envelope, and verified development preflight without exposing trading controls, credentials, or a live account connection. ClockCross is paper-only and built around auditable abstention as much as trading.

## Suggested technology / category tags

- AI Agents
- Algorithmic Trading
- Options Trading
- FinTech
- Alpaca
- Alpaca MCP
- Python
- FastAPI
- Cloudflare Workers AI
- Llama 3.3 70B
- SQLite

## Required links

- **Public GitHub repository:** https://github.com/AKzar1el/clockcross
- **Judge demo platform:** Cloudflare Workers Static Assets
- **Judge demo URL:** https://clockcross-demo.tomi-seregi99.workers.dev
- **One-page technical write-up:** `docs/ONE_PAGE_WRITEUP.md`
- **Operations / account discipline:** `docs/OPERATIONS.md`
- **Submission gate:** `docs/SUBMISSION_CHECKLIST.md`

## Image placement map

### Lablab cover image

Use **`hackathon-cover.png`** — 1600×900 PNG, approximately 166 KB.

<p align="center">
  <img src="../deploy/cloudflare-demo/public/hackathon-cover.png" alt="ClockCross 16:9 hackathon cover" width="900">
</p>

- Repository source: `deploy/cloudflare-demo/public/hackathon-cover.png`
- Public HTTPS asset: https://clockcross-demo.tomi-seregi99.workers.dev/hackathon-cover.png
- SVG master: `deploy/cloudflare-demo/public/hackathon-cover.svg`

This is the primary submission cover and is also displayed at the top of the GitHub README.

### Website / link preview image

Use **`og-image.png`** — 1200×630 PNG, approximately 132 KB.

<p align="center">
  <img src="../deploy/cloudflare-demo/public/og-image.png" alt="ClockCross social and Open Graph preview" width="800">
</p>

- Repository source: `deploy/cloudflare-demo/public/og-image.png`
- Public HTTPS asset: https://clockcross-demo.tomi-seregi99.workers.dev/og-image.png
- SVG master: `deploy/cloudflare-demo/public/og-image.svg`

The judge demo already references this asset through Open Graph and Twitter-card metadata.

### GitHub social preview

Recommended asset: `deploy/cloudflare-demo/public/og-image.png`.

GitHub's repository social-preview control is a repository Settings UI upload rather than a tracked repository file. Upload this image manually under **Repository → Settings → Social preview → Edit → Upload an image**. The current 1200×630 solid-background PNG is above GitHub's documented 640×320 minimum and below the 1 MB limit.

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

These are already wired into the deployed judge demo.

## Video presentation structure

Aim for a compact judge-first recording rather than a feature tour.

1. **0:00–0:25 — Problem / thesis**  
   BTC trades 24/7; COIN options do not. ClockCross measures unexplained repricing rather than blindly following BTC.
2. **0:25–1:10 — Evidence**  
   Show the frozen `MUTATE` result, COIN evidence, MSTR deterioration, QQQ control, and failed 100 bps friction test.
3. **1:10–2:00 — Autonomous pipeline**  
   Residual → confirmation → option feasibility → Alpaca MCP context → bounded AI → deterministic spread selection/risk → Alpaca MLeg paper entry → bounded fill lifecycle → deterministic 10:55 exit.
4. **2:00–2:45 — Safety / AI authority**  
   Explain the three AI outputs, fail-closed abstention, COIN-only scope, 7–21 DTE debit spreads, deterministic sizing, deterministic exit and idempotency.
5. **2:45–3:35 — Demo**  
   Walk the judge demo and show the 2026-09-01 real competition episode plus its ledger/Alpaca evidence.
6. **3:35–4:15 — Alpaca integration**  
   Show MCP read-only context, current chain feasibility, paper MLeg entry/close execution, deterministic reconciliation, and competition-account discipline.
7. **4:15–4:30 — Close**  
   ClockCross is built to reject weak evidence, abstain when uncertain, and expose exactly why it acted or did not act.

## Slide-deck content map

1. **ClockCross** — one-line thesis + cover visual.
2. **The timing problem** — BTC 24/7 vs U.S. option hours; naive overnight-following thesis rejected.
3. **Research before execution** — chronological design and frozen `MUTATE` verdict.
4. **What survived** — COIN evidence, MSTR negative evidence, QQQ control, failed friction test.
5. **Autonomous system** — end-to-end architecture diagram.
6. **AI is bounded** — continuation / reversion / abstain; deterministic authority boundaries.
7. **Defined-risk lifecycle** — 7–21 DTE COIN debit spreads, directional spread selection, risk caps, bounded fill, 10:55 exit, idempotency and reconciliation.
8. **Alpaca integration** — historical/data feeds, MCP read-only context, Trading API MLeg paper entry and close.
9. **Evidence console** — judge-demo screenshot + verified preflight and first competition lifecycle.
10. **Competition proof** — final account equity/P&L, trades + abstentions, and submission links.

## Final fields still pending external/user evidence

- Dedicated competition Alpaca paper account ID for the submission form.
- Final competition account P&L/equity after the event run is complete.
- Final selected competition trade/abstention screenshots.
- Video URL.
- Slide-deck URL/file.
- Lablab submission URL.

## Final repository handoff

The competition lifecycle is already on `main` and the 2026-09-01 autonomous paper lifecycle is externally proven. The current post-episode correction is intentionally narrower: it changes only deterministic option-spread construction/observability so the selected vertical retains meaningful directional exposure under the **same** signal, AI action set, COIN-only universe, 7–21 DTE window, one-contract sizing, 1%/5% defined-loss envelope, decision window, MLeg lifecycle, and 10:55 ET exit.

GitHub cron scheduling is no longer part of the operational design. The checked-in competition workflow uses the path-scoped `ops/competition-run-now` push trigger on `main`, with `workflow_dispatch` as recovery, while the application itself remains the final timing gate.

Before any final submission, require the complete CI suite to be green on the merged commit, capture final competition account P&L/equity, add the real competition evidence to the demo/submission media, and complete the remaining Lablab/video/slide fields in `docs/SUBMISSION_CHECKLIST.md`.
