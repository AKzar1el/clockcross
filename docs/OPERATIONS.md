# ClockCross Operations

ClockCross is paper-only. Never point it at Alpaca's live trading endpoint.

## Development account

Use the development paper account for preflight, dry runs, and the single controlled MLeg smoke test.

```bash
export CLOCKCROSS_ACCOUNT_ROLE=development
export CLOCKCROSS_ALLOW_DEV_ORDER=false
uv run clockcross preflight
uv run clockcross run-once --date YYYY-MM-DD --mode dry-run
```

The MLeg smoke test is a separate, explicit command. It is restricted to the development account, requires options Level 3, requires the U.S. market to be open, submits one deliberately non-marketable `$0.01` COIN debit vertical, immediately cancels the parent MLeg order, and fails unless cancellation is confirmed.

```bash
export CLOCKCROSS_ACCOUNT_ROLE=development
export CLOCKCROSS_ALLOW_DEV_ORDER=true
uv run clockcross smoke-mleg
```

Do not leave `CLOCKCROSS_ALLOW_DEV_ORDER=true` set after the smoke test.

## Competition account

Create a brand-new Alpaca paper account for the hackathon with exactly `$100,000` starting equity. Do not reuse the development account and do not execute a smoke order on the competition account.

```bash
export CLOCKCROSS_ACCOUNT_ROLE=competition
export CLOCKCROSS_ALLOW_DEV_ORDER=false
uv run clockcross preflight
```

Before the first autonomous competition session, verify the account is ACTIVE, unblocked, options Level 3, has exactly `$100,000` equity, and has no open positions. Read-only preflight checks are allowed; order smoke tests are not.

## Sunday 2026-08-30 status

Completed against the encrypted development-paper credentials:

- Full cloud preflight passed all five checks: active/unblocked account, options Level 3, COIN option-chain availability, Alpaca MCP `get_clock`, and schema-valid AI output.
- The COIN 7–21 DTE indicative chain returned 416 parseable contracts during preflight.
- The Cloudflare Workers AI gateway is deployed and authenticated; it uses a fixed Llama 3.3 70B model with the exact ClockCross decision schema.
- Preflight is read-only and created no orders.

## Monday 2026-08-31 sequence

1. Repeat `uv run clockcross preflight` using the development account.
2. After the U.S. options market is open and opening spreads have settled, run the explicit development-account `uv run clockcross smoke-mleg` command once with `CLOCKCROSS_ALLOW_DEV_ORDER=true`.
3. Confirm the smoke result reports `final_status: canceled`; then immediately return `CLOCKCROSS_ALLOW_DEV_ORDER=false`.
4. Create/configure the fresh `$100,000` competition paper account. Do not smoke-test it.
5. Run competition preflight read-only.
6. Allow the autonomous competition session only after the configured 09:55 ET decision boundary and only if all signal, AI, option-feasibility, and deterministic risk gates approve a trade.

## Hard safety invariants

- Alpaca trading endpoint is always `https://paper-api.alpaca.markets`.
- Live execution is restricted to `COIN`.
- MLeg orders are defined-risk 1:1 vertical debit spreads and use limit prices.
- The competition account rejects the development-order opt-in flag.
- 0DTE is excluded; live option selection is 7–21 DTE.
- Missing/stale data, failed readiness, invalid AI output, risk rejection, or uncertain order state means abstain/fail closed.
