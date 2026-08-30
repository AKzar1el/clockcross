# ClockCross

**An autonomous AI options agent that measures crypto-to-equity repricing gaps, validates them chronologically, and expresses only evidence-backed COIN signals through defined-risk Alpaca spreads.**

ClockCross was built for the **Alpaca AI Trading Agents Hackathon**. It uses Alpaca's paper-trading stack, Alpaca MCP, and an OpenAI-compatible Featherless model while keeping trade construction, risk, and order idempotency deterministic.

> Paper trading is a simulation. Nothing in this repository is investment advice, and the research results do not imply future performance.

## Why ClockCross

BTC trades continuously while U.S. equity options do not. The naive idea — “BTC moved overnight, so buy a crypto-sensitive stock at the open” — is rejected because COIN and MSTR already reprice before the regular session.

ClockCross instead estimates the expected equity move from recent BTC/equity beta, measures the **unexplained premarket residual**, and asks whether that residual is large enough to enter a bounded decision pipeline.

```text
BTC 24/7 data
  -> rolling BTC/COIN beta
  -> 09:25 ET COIN premarket residual
  -> chronological evidence gate
  -> 09:30–09:40 opening confirmation
  -> current 7–21 DTE COIN option-chain feasibility
  -> read-only Alpaca MCP context/news
  -> bounded AI: continuation | reversion | abstain
  -> deterministic vertical-spread constructor
  -> deterministic risk governor
  -> idempotent Alpaca paper MLeg execution
  -> durable SQLite decision ledger
```

## What the research actually found

The first real Alpaca historical run covered **2025-01-02 through 2026-08-28** using consolidated SIP equity data and returned **`MUTATE`**, not `GO`.

| Surface | OOS signals | Mean signed underlying return | Current interpretation |
| --- | ---: | ---: | --- |
| COIN | 82 | +27.46 bps | **Live candidate after mutation** |
| MSTR | 65 | +31.40 bps | Negative/rejection evidence: 2026 weakened |
| QQQ | control | -1.56 bps | Broad-market falsification control |

The important regime split was COIN: its 2026 test episodes averaged approximately **+84.07 bps across 38 signals**, while MSTR's 2026 episodes deteriorated to approximately **-22.72 bps**. Both tickers failed the intentionally severe **100 bps underlying-friction** gate. ClockCross does not erase or relabel that failure.

The approved mutation therefore makes **COIN the only execution-eligible underlying** and replaces the generic friction question with a live **options-feasibility gate** using the actual Alpaca chain. The frozen live signal policy is the modal recent continuation configuration: beta-40, raw residual, 1% threshold.

Evidence is committed under [`artifacts/research/`](artifacts/research/) and [`docs/research/`](docs/research/).

## AI authority is deliberately narrow

The model sees a schema-bounded context only after deterministic evidence and option-chain feasibility pass. It may return:

- `continuation`
- `reversion`
- `abstain`

It cannot choose a new symbol, invent a contract, change DTE, change position sizing, bypass stale quotes, override buying power, exceed portfolio risk, or submit an order directly. Malformed output, transport errors, company-specific news, or ambiguous context fail closed to `abstain`.

Alpaca MCP is also **read-only inside ClockCross**: trading toolsets are disabled. Atomic multi-leg execution uses Alpaca's Trading REST API because deterministic request validation and `client_order_id` reconciliation are easier to audit there.

## Risk and execution

The MVP permits only:

- COIN;
- 7–21 DTE call or put debit spreads;
- 1:1 same-expiration verticals;
- positive bounded net debit;
- limit MLeg orders;
- no 0DTE;
- no uncovered short options;
- one active COIN structure at a time.

Default risk caps are **1% of starting equity per position** and **5% aggregate defined loss**. Every irreversible order has a deterministic client order ID. A timeout triggers reconciliation by that ID; if the outcome cannot be proven, the episode becomes **indeterminate** and ClockCross does not blindly re-submit.

## Run locally

Requires Python 3.12+ and `uv`.

```bash
uv sync --extra dev
cp .env.example .env
```

Set development-paper Alpaca credentials and your Featherless/OpenAI-compatible model configuration in `.env`. Never use the final hackathon account for destructive integration tests.

Research:

```bash
uv run clockcross research --start 2025-01-02 --end 2026-08-28 \
  --output-dir artifacts/research
```

Read-only external preflight — safe to run while markets are closed and does **not** create a ledger episode or call an order endpoint:

```bash
uv run clockcross preflight
```

It checks the paper account state, Level-3 options permission, parseability of the current 7–21 DTE COIN chain, read-only Alpaca MCP `get_clock`, and the configured AI provider/schema. Exit code is `0` only when all five checks pass.

One autonomous dry run:

```bash
uv run clockcross run-once --date 2026-08-31 --mode dry-run
```

Development-account paper execution requires the explicit environment opt-in:

```text
CLOCKCROSS_ACCOUNT_ROLE=development
CLOCKCROSS_ALLOW_DEV_ORDER=true
```

Competition mode uses a fresh dedicated `$100,000` paper account and **must not** set the development-order flag:

```text
CLOCKCROSS_ACCOUNT_ROLE=competition
CLOCKCROSS_ALLOW_DEV_ORDER=false
```

Crash recovery is intentionally separate and cannot compute or submit a new signal:

```bash
uv run clockcross reconcile --date 2026-08-31
```

Read-only evidence console:

```bash
uv run clockcross serve --host 0.0.0.0 --port 8000
```

See [`docs/OPERATIONS.md`](docs/OPERATIONS.md) before any paper execution.

## Tests

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src/clockcross
```

The suite covers leakage boundaries, option-chain normalization, AI fail-closed behavior, risk caps, state-machine legality, SQLite idempotency, uncertain-order reconciliation, public API redaction, live-signal freezing, account-role safeguards, read-only external preflight, and repository secret scanning.

## Project documents

- [`docs/ONE_PAGE_WRITEUP.md`](docs/ONE_PAGE_WRITEUP.md) — hackathon technical summary
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md) — runbook and account discipline
- [`docs/SUBMISSION_CHECKLIST.md`](docs/SUBMISSION_CHECKLIST.md) — final submission gate
- [`docs/research/2026-08-29-initial-alpaca-run.md`](docs/research/2026-08-29-initial-alpaca-run.md) — immutable first-run interpretation
- [`docs/research/2026-08-29-live-signal-policy.json`](docs/research/2026-08-29-live-signal-policy.json) — frozen live policy

## License

MIT. See [`LICENSE`](LICENSE).
