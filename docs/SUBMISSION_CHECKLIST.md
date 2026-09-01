# ClockCross Hackathon Submission Checklist

## Eligibility / account

- [ ] lablab.ai enrollment complete.
- [x] Fresh dedicated Alpaca paper account created for judging.
- [x] Starting balance was exactly `$100,000` before first competition episode.
- [x] Account is options Level 3.
- [ ] Competition account ID recorded for submission (never commit credentials).
- [ ] Development and competition credentials are different.

## Required technology

- [x] Autonomous ClockCross competition episode demonstrated on the dedicated judging account.
- [x] Alpaca Trading API paper MLeg execution demonstrated against the open market.
- [x] Alpaca MCP read-only context interaction demonstrated/logged.
- [x] Options trading demonstrated through the competition episode.
- [x] Authenticated Cloudflare Workers AI gateway invoked with a schema-valid bounded decision.
- [x] Competition lifecycle code implements bounded entry fill/cancel, persisted recovery, deterministic 10:55 ET exit, and exact-contract closing MLegs.
- [x] Event-bounded GitHub Actions launcher is checked in with competition-only role, encrypted-secret references, concurrency, preflight-before-trade ordering, and durable state restoration.

## Evidence

- [x] `artifacts/research/verdict.json` matches the immutable real research run.
- [x] `MUTATE` result and 100 bps friction failure remain disclosed.
- [x] COIN-only mutation documented.
- [x] MSTR negative 2026 result disclosed.
- [x] QQQ control disclosed.
- [x] Live signal policy hash/artifact frozen before competition operation.
- [x] Static zero-secret judge demo deployed: `https://clockcross-demo.tomi-seregi99.workers.dev`.
- [ ] Trades **and abstentions** visible in the evidence console.
- [ ] Final competition account P&L/equity captured for submission.

## Repository / quality

- [x] Public GitHub repository.
- [x] MIT license.
- [x] Complete static brand asset set prepared (mark, wordmark, favicons, app icons, social preview, manifest).
- [x] Hackathon cover displayed at the top of the README.
- [x] Canonical submission copy + image placement map prepared in `docs/SUBMISSION_PACKAGE.md`.
- [ ] GitHub repository social preview uploaded in repository Settings after final merge.
- [ ] `pytest -q` passes on final submission commit.
- [ ] Ruff passes on final submission commit.
- [ ] mypy passes on final submission commit.
- [ ] Repository secret scan passes on final submission commit.
- [x] No `.env`, raw API keys, account secrets, or raw market cache committed.
- [ ] CI green on final submission commit.
- [x] AI gateway health and authenticated schema smoke test passed.
- [ ] Evidence-console deployment health/readiness returns success.

## Lablab submission

- [x] Project title and short-description copy prepared.
- [x] Long-description copy prepared.
- [x] Technology/category tags prepared.
- [x] 16:9 cover image asset prepared: `deploy/cloudflare-demo/public/hackathon-cover.png`.
- [x] Public HTTPS cover URL available: `https://clockcross-demo.tomi-seregi99.workers.dev/hackathon-cover.png`.
- [ ] Project title / descriptions / tags entered on Lablab.
- [ ] Cover image uploaded to Lablab.
- [ ] Public GitHub URL entered on Lablab.
- [x] Demo application URL prepared: `https://clockcross-demo.tomi-seregi99.workers.dev`.
- [ ] Demo application URL entered on Lablab.
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

Software readiness and external-market proof are deliberately separate. Do not mark an external item complete because its code path is tested.

- [x] Development-account external preflight passed 5/5 on 2026-08-30.
- [ ] Development-account non-marketable MLeg smoke/cancel test completed while U.S. options are open with `final_status: canceled`.
- [x] GitHub `competition` environment exists with the judging-account Alpaca key/secret and ClockCross gateway bearer.
- [x] Fresh competition account passed pristine startup gate before its first autonomous episode.
- [x] 2026-09-01 `competition-session` completed with opening MLeg `filled`, closing MLeg `filled`, and terminal state `CLOSED`.
- [x] No unresolved opening/closing order remained after the 2026-09-01 episode.
- [x] No undocumented manual trade-selection intervention occurred in the 2026-09-01 autonomous episode.
- [ ] Post-episode directional spread-constructor correction merged to `main` with full CI green.
- [ ] Final-day account state and P&L/equity captured before deadline.
- [ ] Video presentation completed.
- [ ] Slide presentation completed.
- [ ] Final Lablab submission completed before **2026-09-04 17:00 CEST**.
