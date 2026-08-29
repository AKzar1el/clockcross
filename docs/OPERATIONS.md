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

Start from `.env.example`. Required runtime secrets:

- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`
- `LLM_API_KEY`
- `LLM_MODEL`

Recommended hackathon partner provider:

- `LLM_BASE_URL=https://api.featherless.ai/v1`

Do not commit `.env`, credentials, account IDs, API response headers, or raw market caches.

## 3. Preflight

Before every paper run:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src/clockcross
```

Verify the frozen artifacts exist:

- `artifacts/research/verdict.json`
- `docs/research/2026-08-29-live-signal-policy.json`
- `docs/superpowers/specs/2026-08-29-coin-options-mutation.md`

Competition startup additionally verifies:

- paper endpoint only;
- account `ACTIVE` and not trading-blocked;
- options trading level >= 3;
- maximum options level >= 3;
- exactly `$100,000` equity before the first episode;
- no existing positions before the first episode.

## 4. Daily decision boundary

All market semantics use `America/New_York`.

- 09:25 ET — feature freeze.
- 09:30–09:40 ET — opening confirmation.
- 09:55 ET — earliest autonomous decision.

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

## 5. Restart / uncertain order

If a run ends at `ORDER_SUBMITTED` or reports `order_indeterminate`, **do not run a new episode for that date**.

Use:

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

ClockCross blocks new competition entries at 10:20 ET on 2026-09-04, leaving buffer before the 17:00 CEST submission deadline. Before submission:

1. reconcile every non-terminal episode;
2. inspect account positions/orders in Alpaca;
3. document any emergency manual intervention;
4. capture final account P&L/equity evidence;
5. ensure the submitted account ID is the dedicated competition paper account;
6. rotate development credentials after testing and never publish the competition keys.

## 8. Change discipline after competition start

Allowed: correctness/safety fixes with commit + changelog/ledger note.

Not allowed: manual trade selection, loss-driven threshold retuning, account resets, silently changing the live policy, adding MSTR/QQQ execution, or weakening risk gates to create trades.
