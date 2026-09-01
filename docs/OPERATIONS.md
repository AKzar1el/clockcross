# ClockCross Operations Runbook

## 1. Account separation

Use two distinct Alpaca paper accounts.

**Development account**
- API/MCP probes, option-chain tests, order smoke tests, cancellations, failure testing.
- `CLOCKCROSS_ACCOUNT_ROLE=development`.
- Paper order submission is disabled unless `CLOCKCROSS_ALLOW_DEV_ORDER=true` is explicitly set.

**Competition account**
- Create fresh specifically for the hackathon.
- Starting equity must be exactly `$100,000` before the first ClockCross episode.
- No manual/smoke trades before autonomous operation.
- `CLOCKCROSS_ACCOUNT_ROLE=competition`.
- `CLOCKCROSS_ALLOW_DEV_ORDER=false` always.
- Do not reset the account once competition operation begins.

Never reuse development credentials for the final competition account.

## 2. Required environment

Start from `.env.example`.

Required secrets:

- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`
- `LLM_API_KEY` — bearer for the authenticated ClockCross AI gateway

Non-secret defaults:

- `LLM_BASE_URL=https://clockcross-ai-gateway.tomi-seregi99.workers.dev/v1`
- `LLM_MODEL=clockcross-cloudflare-llama-3.3-70b`

The gateway is deployed from `deploy/cloudflare-ai-gateway/`. It fixes the underlying provider model to Cloudflare Workers AI Llama 3.3 70B fast, requests the exact ClockCross JSON schema from Workers AI, validates it again, and exposes only an authenticated OpenAI-compatible `/v1/chat/completions` adapter plus a read-only `/health` route.

The current hackathon bootstrap derives the gateway bearer only inside the encrypted cloud runner and stores the matching value as Cloudflare Worker secret `CLOCKCROSS_AI_AUTH`. The bearer is never committed or printed. After the event, replace this bootstrap coupling with a dedicated random gateway bearer when rotating the temporary Cloudflare credential.

Do not commit `.env`, credentials, account IDs, API response headers, raw market caches, or gateway bearer values.

## 3. Preflight

Before every paper run, verify the code first:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src/clockcross
```

Then run the external read-only preflight:

```bash
uv run clockcross preflight
```

`preflight` is safe to run while U.S. markets are closed. It does **not** open the SQLite decision ledger, create an episode, instantiate the trading execution service, or call an Alpaca order endpoint. It checks exactly five external surfaces:

1. Alpaca paper account is `ACTIVE` and unblocked;
2. account-approved and current options trading levels both permit Level 3 spreads; if Alpaca also reports a configuration maximum, that value must permit Level 3 too;
3. the current COIN option chain is parseable and contains at least one 7–21 DTE contract;
4. read-only Alpaca MCP `get_clock` succeeds;
5. the configured AI provider returns a schema-valid bounded decision.

The command exits `0` only when all five checks pass and exits `2` when any check fails. Do not start paper mode after a failed preflight; inspect the named failed check first.

**Verified external gates:**

- **2026-08-30 development account:** encrypted cloud preflight passed 5/5 — account active/unblocked, Level 3, 416 parseable COIN contracts in the 7–21 DTE window via indicative feed, Alpaca MCP `get_clock`, and a schema-valid bounded AI decision through the deployed Cloudflare gateway.
- **2026-09-01 competition account:** the same five preflight surfaces passed immediately before the first real competition episode; that episode subsequently filled its opening MLeg and deterministic research-horizon close and finished `CLOSED`.

**Closed-market note:** weekend/pre-open option quotes are expected to be old. The read-only preflight deliberately checks chain coverage and parseability, not the live 60-second quote-freshness rule. The actual 09:55 ET decision pipeline still enforces live quote freshness before a spread can be constructed or submitted.

The Alpaca MCP server may emit a FastMCP protocol-discovery validation warning during startup. Treat it as non-fatal only when the requested `get_clock` call itself succeeds; the preflight check remains fail-closed on an actual MCP tool failure.

Verify the frozen artifacts exist:

- `artifacts/research/verdict.json`
- `docs/research/2026-08-29-live-signal-policy.json`
- `docs/superpowers/specs/2026-08-29-coin-options-mutation.md`

Competition startup additionally verifies at the paper-run gate:

- paper endpoint only;
- account `ACTIVE` and not trading-blocked;
- account-approved options level >= 3;
- current options trading level >= 3;
- configuration max >= 3 when Alpaca reports that optional field;
- exactly `$100,000` equity before the first episode;
- no existing positions before the first episode.

The read-only preflight does not replace those pristine competition-account checks; they remain mandatory for a fresh competition account.

### Development MLeg smoke

The one-purpose smoke test is separate from `run-once`. It is development-account only, requires explicit order opt-in, options Level 3, and an open U.S. market. Only after those gates pass does it inspect the COIN chain, construct a defined-risk 1:1 vertical, replace the displayed debit with a deliberately non-marketable `$0.01` limit, submit one parent MLeg order, and immediately cancel/poll that same parent order. Any fill, partial fill, duplicate identity, uncertain status, or unconfirmed cancellation fails closed.

```bash
export CLOCKCROSS_ACCOUNT_ROLE=development
export CLOCKCROSS_ALLOW_DEV_ORDER=true
uv run clockcross smoke-mleg
export CLOCKCROSS_ALLOW_DEV_ORDER=false
```

Never run `smoke-mleg` with competition credentials.

**Verified off-hours safety gate (2026-08-30):** the real development credentials were used with `CLOCKCROSS_ALLOW_DEV_ORDER=true`; the command reached Alpaca's live paper clock and refused with `U.S. market is not open; refusing MLeg smoke`. The refusal occurs before option-chain retrieval or order submission, so this proof created no smoke order.

A separate open-market development-account submit/cancel smoke is useful as a safety proof, but it is no longer a prerequisite for claiming that the competition MLeg lifecycle executed: the 2026-09-01 competition episode independently proved an opening fill and exact-contract closing fill. Never smoke-test the competition account.

## 4. Daily decision boundary

All market semantics use `America/New_York`.

- 09:25 ET — feature freeze.
- 09:30–09:40 ET — opening confirmation.
- 09:55 ET — earliest autonomous decision.
- 10:05 ET — latest permitted new competition entry; materially delayed signals fail closed.
- 10:55 ET — deterministic research-aligned exit target for a filled spread.

At 09:55, stock historical reconstruction is capped at 09:40 SIP data. Never widen that end time to “now” on the Basic data plan.

The spread constructor is also frozen operationally:

- COIN only;
- 7–21 DTE;
- 1:1 defined-risk call/put debit verticals;
- long leg approximately 0.45–0.65 absolute delta;
- all quote-eligible farther-OTM same-expiration shorts may be considered;
- candidate must retain at least 0.30 absolute net directional delta;
- candidate debit must fit the existing one-contract budget implied by 1% per-position, 5% aggregate and buying-power limits;
- rank surviving candidates by net directional delta per debit with deterministic tie-breakers;
- abstain if no candidate satisfies the envelope.

Do not lower the net-delta floor, widen the risk budget, change quantity, add 0DTE, or alter the signal threshold in response to an individual competition result.

Run one episode:

```bash
uv run clockcross run-once --date YYYY-MM-DD --mode dry-run
```

When development smoke testing has been explicitly approved:

```bash
uv run clockcross run-once --date YYYY-MM-DD --mode paper
```

A dry run may reach `RISK_APPROVED` but never calls Alpaca order submission.

For the dedicated competition lifecycle, use:

```bash
uv run clockcross competition-session --date YYYY-MM-DD
```

`competition-session` owns entry reconciliation, a fixed 180-second opening fill window, proven cancellation of an unfilled entry, monitoring of a filled position, the 10:55 ET exit, and at most one deterministic close replacement. It never recomputes a signal after the episode has moved beyond the entry decision state.

## 5. Restart / uncertain order

If a run ends at `ORDER_SUBMITTED`, `EXIT_SUBMITTED`, or reports an indeterminate order, **do not start a new daily signal**.

The competition runtime resumes the persisted lifecycle by exact deterministic order identity. The lower-level recovery command remains available for opening-order inspection:

```bash
uv run clockcross reconcile --date YYYY-MM-DD
```

`reconcile` does not load the model or signal stack and cannot submit a new order. It only looks up the persisted deterministic Alpaca `client_order_id` and updates the existing state.

If reconciliation still cannot prove the order state, stop and inspect Alpaca manually. Do not retry the POST.

## 6. Evidence console

```bash
uv run clockcross serve --host 0.0.0.0 --port 8000
```

Public routes are read-only. The console strips account identifiers, credential-like keys, and provider payloads. It shows rounded account status, episode/abstention history, and compact research evidence.

## 7. Final-day controls

ClockCross applies the same **10:05 ET latest-entry gate on every competition day**. The older September 4 10:20 ET hard cutoff remains an independent backstop, but the stricter 10:05 gate wins in normal operation. Before the 17:00 CEST submission deadline:

1. reconcile every non-terminal episode;
2. inspect account positions/orders in Alpaca;
3. document any emergency manual intervention;
4. capture final account P&L/equity evidence;
5. ensure the submitted account ID is the dedicated competition paper account;
6. rotate development Alpaca, Cloudflare, GitHub, npm, and gateway credentials after testing and never publish the competition keys.

## 8. Change discipline after competition start

Allowed: correctness/safety fixes with commit + changelog/ledger note.

Not allowed: manual trade selection, loss-driven threshold retuning, account resets, silently changing the live policy, adding MSTR/QQQ execution, weakening the net-delta floor/risk gates to create trades, or changing the research-horizon exit based on one observed session.

## 9. Competition workflow

`.github/workflows/competition-runtime.yml` is the canonical launcher on `main`.

GitHub cron scheduling was removed after delayed/dropped scheduled runs proved unreliable for a narrow intraday decision boundary. The supported triggers are now:

- a path-scoped push to `main` that changes `ops/competition-run-now` — the primary competition trigger;
- `workflow_dispatch` — recovery/manual launch path.

The workflow itself accepts only these competition dates:

- 2026-08-31;
- 2026-09-01 through 2026-09-04.

Triggering the workflow does **not** grant permission to stretch the signal window. ClockCross remains the final time authority: if the job reaches the strategy after 10:05 ET, the runtime must fail closed rather than create a delayed entry.

Use a GitHub Actions environment named **`competition`** with exactly these encrypted secrets:

- `ALPACA_COMPETITION_API_KEY`
- `ALPACA_COMPETITION_SECRET_KEY`
- `CLOCKCROSS_AI_GATEWAY_BEARER`

The workflow maps them to the runtime's `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, and `LLM_API_KEY` variables. It hard-sets `CLOCKCROSS_ACCOUNT_ROLE=competition` and `CLOCKCROSS_ALLOW_DEV_ORDER=false`, runs `clockcross preflight` before the order-capable command, and never echoes an environment dump or literal credential.

Each run restores the newest completed prior `clockcross-state` artifact if present, then uploads the SQLite database with 10-day retention. The absence of a previous artifact on the first run is valid. Concurrency prevents two competition-session jobs from overlapping.

**Verified 2026-09-01 runtime:** the path-scoped push trigger launched the competition workflow at approximately 09:54 ET. Read-only preflight passed, the autonomous episode ran, the opening MLeg filled, the deterministic 10:55 close filled, the episode finished `CLOSED`, and the resulting SQLite state artifact was uploaded successfully.
