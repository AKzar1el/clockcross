# ClockCross Hackathon Submission Checklist

## Eligibility / account

- [ ] lablab.ai enrollment complete.
- [ ] Fresh dedicated Alpaca paper account created for judging.
- [ ] Starting balance was exactly `$100,000` before first competition episode.
- [ ] Account is options Level 3.
- [ ] Competition account ID recorded for submission (never commit credentials).
- [ ] Development and competition credentials are different.

## Required technology

- [ ] Autonomous ClockCross episode demonstrated.
- [ ] Alpaca Trading API used for paper MLeg execution.
- [x] Alpaca MCP read-only context interaction demonstrated/logged.
- [ ] Options trading demonstrated through the competition episode.
- [x] Authenticated Cloudflare Workers AI gateway invoked with a schema-valid bounded decision.

## Evidence

- [x] `artifacts/research/verdict.json` matches the immutable real research run.
- [x] `MUTATE` result and 100 bps friction failure remain disclosed.
- [x] COIN-only mutation documented.
- [x] MSTR negative 2026 result disclosed.
- [x] QQQ control disclosed.
- [x] Live signal policy hash/artifact frozen before competition operation.
- [x] Static zero-secret judge demo deployed: `https://clockcross-demo.tomi-seregi99.workers.dev`.
- [ ] Trades **and abstentions** visible in the evidence console.
- [ ] Actual Alpaca account P&L/equity captured after competition run.

## Repository / quality

- [x] Public GitHub repository.
- [x] MIT license.
- [ ] `pytest -q` passes on final submission commit.
- [ ] Ruff passes on final submission commit.
- [ ] mypy passes on final submission commit.
- [ ] Repository secret scan passes on final submission commit.
- [x] No `.env`, raw API keys, account secrets, or raw market cache committed.
- [ ] CI green on submission commit.
- [x] AI gateway health and authenticated schema smoke test passed.
- [ ] Evidence-console deployment health/readiness returns success.

## Lablab submission

- [ ] Project title and short description.
- [ ] Long description.
- [ ] Technology/category tags.
- [ ] Cover image.
- [ ] Public GitHub URL.
- [x] Demo application URL: `https://clockcross-demo.tomi-seregi99.workers.dev`.
- [ ] Video presentation.
- [ ] Slide presentation.
- [ ] Alpaca paper trading account ID.
- [x] One-page AI logic / risk gates / Alpaca implementation write-up.

## Build in public

Up to five final links:

- [ ] Hypothesis / research methodology post.
- [ ] Negative result / MSTR mutation post.
- [ ] Alpaca MCP + defined-risk architecture post.
- [ ] First autonomous decision/trade-or-abstention post.
- [ ] Final evidence/P&L post.

Tag lablab.ai and Alpaca as required by the event page.

## Final operational gate

- [x] Development-account external preflight passed 5/5 on 2026-08-30.
- [ ] Development-account MLeg smoke/cancel test completed while U.S. options are open.
- [ ] Fresh competition account passes pristine startup gate without smoke trades.
- [ ] No unresolved `ORDER_SUBMITTED`/indeterminate episode.
- [ ] No undocumented manual intervention.
- [ ] Final-day account state captured before deadline.
- [ ] Submission completed before **2026-09-04 17:00 CEST**.
