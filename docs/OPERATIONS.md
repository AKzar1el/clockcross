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

**Verified Sunday gate (2026-08-30):** full encrypted cloud preflight passed 5/5 against the development account: account active/unblocked, Level 3, 416 parseable COIN contracts in the 7–21 DTE window via indicative feed, Alpaca MCP `get_clock`, and a schema-valid bounded AI decision through the deployed Cloudflare gateway.

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

The read-only preflight does not replace those pristine competition-account checks; they remain mandatory immediately before the first competition paper episode.

### Development MLeg smoke

The one-purpose smoke test is separate from `run-once`. It is development-account only, requires explicit order opt-in, options Level 3, and an open U.S. market. Only after those gates pass does it inspect the COIN chain, construct a defined-risk 1:1 vertical, replace the displayed debit with a deliberately non-marketable `$0.01` limit, submit one parent MLeg order, and immediately cancel/poll that same parent order. Any fill, partial fill, duplicate identity, uncertain status, or unconfirmed cancellation fails closed.

```bash
export CLOCKCROSS_ACCOUNT_ROLE=development
export CLOCKCROSS_ALLOW_DEV_ORDER=true
uv run clockcross smoke-mleg
export CLOCKCROSS_ALLOW_DEV_ORDER=false
```

Never run `smoke-mleg` with competition credentials.

**Verified off-hours safety gate (2026-08-30):** the real development credentials were used with `CLOCKCROSS_ALLOW_DEV_ORDER=true`; the command reached Alpaca's live paper clock and refused with `U.S. market is not open; refusing MLeg smoke`. The refusal occurs before option-chain retrieval or order submission, so this proof created no smoke order. The real submit/cancel proof remains intentionally pending the Monday open market.

### Sunday / Monday sequence

**Sunday — complete:**

1. CI-equivalent checks passed;
2. full development-account preflight passed 5/5;
3. authenticated Cloudflare AI gateway deployed and smoke-tested;
4. explicit `smoke-mleg` command and dedicated runtime path are implemented;
5. real development credentials proved the closed-market gate fails before chain/order access;
6. no development or competition order was created by Sunday verification.

**Monday:**

1. repeat `clockcross preflight` before the U.S. session;
2. after the U.S. options market is open and opening spreads have settled, run `clockcross smoke-mleg` once on the development account and require `final_status: canceled`;
3. immediately return `CLOCKCROSS_ALLOW_DEV_ORDER=false`;
4. keep `CLOCKCROSS_ALLOW_DEV_ORDER=false` for competition credentials;
5. create/use the fresh competition account separately — do not smoke-test it;
6. after the 09:55 ET information boundary, let competition runtime enforce the pristine `$100,000`/empty-account gate before the first autonomous episode.

## 4. Daily decision boundary

All market semantics use `America/New_York`.

- 09:25 ET — feature freeze.
- 09:30–09:40 ET — opening confirmation.
- 09:55 ET — earliest autonomous decision.
- 10:05 ET — latest permitted new competition entry; materially delayed signals fail closed.
- 10:55 ET — deterministic research-aligned exit target for a filled spread.

At 09:55, stock historical reconstruction is capped at 09:40 SIP data. Never widen that end time to “now” on the Basic data plan.

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

Not allowed: manual trade selection, loss-driven threshold retuning, account resets, silently changing the live policy, adding MSTR/QQQ execution, or weakening risk gates to create trades.

## 9. Scheduled competition workflow

After merge, `.github/workflows/competition-runtime.yml` is the canonical autonomous launcher. GitHub scheduled workflows run from the default branch, so the file must exist on `main` before Monday's first competition session.

The workflow is intentionally event-bounded and timezone-aware:

- 2026-08-31 at 09:57 `America/New_York`;
- 2026-09-01 through 2026-09-04 at 09:57 `America/New_York`;
- optional `workflow_dispatch` recovery, still restricted to the five event dates and `main`.

Use a GitHub Actions environment named **`competition`** and add exactly these encrypted secrets there:

- `ALPACA_COMPETITION_API_KEY`
- `ALPACA_COMPETITION_SECRET_KEY`
- `CLOCKCROSS_AI_GATEWAY_BEARER`

The workflow maps them to the runtime's `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, and `LLM_API_KEY` variables. It hard-sets `CLOCKCROSS_ACCOUNT_ROLE=competition` and `CLOCKCROSS_ALLOW_DEV_ORDER=false`, runs `clockcross preflight` before the order-capable command, and never echoes an environment dump or literal credential.

Each run restores the newest completed prior `clockcross-state` artifact if present, then uploads the closed-run SQLite database (plus SQLite WAL/SHM companions if they exist) with 10-day retention. The absence of a previous artifact on the first run is valid. Concurrency prevents two competition-session jobs from overlapping.

Because scheduled GitHub Actions can start late, ClockCross itself remains the final time authority. A delayed job that reaches the strategy after 10:05 ET must fail closed rather than stretching the frozen signal window.
