# ClockCross Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, falsify, and if supported deploy an autonomous Alpaca paper-trading options agent that converts validated BTC-to-equity repricing residuals into defined-risk debit spreads with bounded AI authority and a complete decision ledger.

**Architecture:** A single Python application owns deterministic market-data normalization, leakage-safe research, signal generation, AI adjudication, option construction, risk validation, state persistence, scheduling, and a minimal FastAPI evidence console. Alpaca is wrapped behind typed adapters so research and tests can run with fakes while production uses paper-trading credentials. SQLite is the only durable store unless deployment proves it insufficient.

**Tech Stack:** Python 3.12, uv, pandas, numpy, pydantic v2, pydantic-settings, httpx, alpaca-py, FastAPI, Uvicorn, SQLite stdlib, pytest, pytest-asyncio, respx, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-08-29-clockcross-design.md`

## Global Constraints

- Alpaca paper trading only; startup must reject any non-paper base URL.
- Final competition account must be a new dedicated `$100,000` Alpaca paper account and must not receive smoke-test trades.
- Primary crypto driver is `BTC/USD`; initial equity universe is `COIN`, `MSTR`, with `QQQ` as a control.
- Premarket features freeze at `09:25 America/New_York`; earliest live decision is after the `09:30-09:40` opening confirmation window.
- Research must be chronological with no shuffled validation and no feature timestamp after the decision boundary.
- Initial options structures are only 1:1 vertical debit spreads, `7-21 DTE`, atomic multi-leg, limit orders, no 0DTE, no naked options.
- The LLM may choose `continuation`, `reversion`, or `abstain`; it may never override deterministic risk, symbol, contract, liquidity, freshness, or portfolio constraints.
- Fail closed on missing/stale/inconsistent data, malformed AI output, ambiguous order state, or risk-calculation failure.
- Keep the MVP single-process and single-store; no Redis, queues, user auth, billing, strategy marketplace, broad screener, or multi-agent architecture.
- All credentials are environment-only and must never appear in repository files, fixtures, logs, snapshots, or CI.

---

## File Structure

```text
clockcross/
├── pyproject.toml
├── README.md
├── LICENSE
├── .gitignore
├── .env.example
├── src/clockcross/
│   ├── __init__.py
│   ├── config.py                 # validated runtime configuration and competition guards
│   ├── time.py                   # ET/UTC market-session boundaries
│   ├── domain.py                 # Pydantic domain contracts shared across components
│   ├── alpaca/
│   │   ├── client.py             # typed Alpaca SDK/API facade
│   │   ├── historical.py         # historical stock/crypto retrieval
│   │   ├── options.py            # option-chain normalization and MLeg requests
│   │   └── mcp.py                # auditable Alpaca MCP invocation boundary
│   ├── research/
│   │   ├── episodes.py           # construct leakage-safe daily decision episodes
│   │   ├── residual.py           # rolling beta, expected move, residual calculations
│   │   ├── validation.py         # chronological walk-forward evaluation
│   │   ├── metrics.py            # simple robust research metrics/baselines
│   │   └── report.py             # JSON/Markdown research artifact generation
│   ├── agent/
│   │   ├── adjudicator.py        # schema-validated LLM decision boundary
│   │   └── prompts.py            # fixed compact system/user prompt builders
│   ├── trading/
│   │   ├── constructor.py        # deterministic vertical-spread selection
│   │   ├── risk.py               # deterministic risk governor
│   │   └── execution.py          # idempotent order submission/reconciliation
│   ├── ledger.py                 # SQLite schema/repository for episodes/transitions/orders
│   ├── state.py                  # explicit episode state machine
│   ├── scheduler.py              # daily orchestration and restart reconciliation
│   ├── api.py                    # FastAPI evidence-console API and health routes
│   └── main.py                   # CLI entry points: research, dry-run, serve, run-once
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── data/.gitkeep
├── artifacts/.gitkeep
└── docs/
    ├── research/
    └── superpowers/...
```

---

### Task 1: Bootstrap the safe Python application and domain contracts

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `LICENSE`
- Create: `src/clockcross/__init__.py`
- Create: `src/clockcross/config.py`
- Create: `src/clockcross/time.py`
- Create: `src/clockcross/domain.py`
- Create: `tests/unit/test_config.py`
- Create: `tests/unit/test_time.py`
- Create: `tests/unit/test_domain.py`

**Interfaces:**
- Produces: `Settings`, `MarketSession`, `DecisionEpisode`, `FeatureVector`, `AgentDecision`, `OptionLeg`, `SpreadCandidate`, `RiskDecision`, `EpisodeState`.
- Later tasks must import these types rather than defining duplicate dictionaries.

- [ ] **Step 1: Write failing configuration safety tests**

```python
from pydantic import ValidationError
import pytest

from clockcross.config import Settings


def test_settings_default_to_paper_and_reject_live_url():
    settings = Settings(
        alpaca_api_key="x",
        alpaca_secret_key="y",
        alpaca_trading_base_url="https://paper-api.alpaca.markets",
    )
    assert settings.paper_trading is True

    with pytest.raises(ValidationError):
        Settings(
            alpaca_api_key="x",
            alpaca_secret_key="y",
            alpaca_trading_base_url="https://api.alpaca.markets",
        )
```

- [ ] **Step 2: Write failing time-boundary tests**

```python
from datetime import date

from clockcross.time import market_session


def test_market_session_freeze_and_decision_boundaries():
    session = market_session(date(2026, 8, 31))
    assert session.feature_freeze.isoformat().endswith("09:25:00-04:00")
    assert session.opening_start.isoformat().endswith("09:30:00-04:00")
    assert session.decision_earliest.isoformat().endswith("09:40:00-04:00")
```

- [ ] **Step 3: Write failing schema tests for agent decisions and option legs**

```python
import pytest
from pydantic import ValidationError

from clockcross.domain import AgentDecision, OptionLeg


def test_agent_decision_rejects_unsupported_action():
    with pytest.raises(ValidationError):
        AgentDecision(action="buy_everything", confidence=1.0, driver="unclear", reason="x")


def test_option_leg_requires_buy_or_sell():
    with pytest.raises(ValidationError):
        OptionLeg(symbol="COIN260918C00300000", side="hold", ratio=1)
```

- [ ] **Step 4: Run the new tests and verify they fail**

Run: `uv run pytest tests/unit/test_config.py tests/unit/test_time.py tests/unit/test_domain.py -q`
Expected: import/module failures because application code does not yet exist.

- [ ] **Step 5: Implement minimal project metadata and dependencies**

`pyproject.toml` must define Python `>=3.12,<3.13`, package source under `src`, console script `clockcross = "clockcross.main:app"` only when `main.py` exists later, and dev dependencies for pytest/Ruff/mypy. Do not add database ORMs or queue packages.

- [ ] **Step 6: Implement `Settings` with hard paper-trading guard**

Required fields:

```python
class Settings(BaseSettings):
    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_trading_base_url: str = "https://paper-api.alpaca.markets"
    alpaca_data_base_url: str = "https://data.alpaca.markets"
    stock_feed: Literal["iex", "sip"] = "iex"
    option_feed: Literal["indicative", "opra"] = "indicative"
    db_path: Path = Path("data/clockcross.sqlite3")
    artifacts_dir: Path = Path("artifacts")
    timezone: str = "America/New_York"
    feature_freeze_time: time = time(9, 25)
    opening_start_time: time = time(9, 30)
    decision_time: time = time(9, 40)
    paper_trading: Literal[True] = True
```

Validation must reject any trading base URL other than Alpaca's paper endpoint.

- [ ] **Step 7: Implement shared Pydantic domain models**

Use explicit enums for action/state/side. Store monetary values as `Decimal`, not binary floats, once they enter options/risk/order models. Research returns may use floats.

- [ ] **Step 8: Implement timezone-safe `market_session(session_date)`**

Return aware ET datetimes for feature freeze, opening start, decision earliest, and normal close. DST must come from `zoneinfo.ZoneInfo("America/New_York")`; never hard-code UTC offsets.

- [ ] **Step 9: Run tests and static checks**

Run:

```bash
uv run pytest tests/unit/test_config.py tests/unit/test_time.py tests/unit/test_domain.py -q
uv run ruff check .
uv run mypy src/clockcross
```

Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml .gitignore .env.example LICENSE src tests

git commit -m "chore: bootstrap safe ClockCross core"
```

---

### Task 2: Add typed historical Alpaca data retrieval with cacheable raw artifacts

**Files:**
- Create: `src/clockcross/alpaca/client.py`
- Create: `src/clockcross/alpaca/historical.py`
- Create: `tests/unit/test_historical.py`
- Create: `tests/integration/test_alpaca_historical_contract.py`
- Create: `tests/fixtures/stock_bars.json`
- Create: `tests/fixtures/crypto_bars.json`

**Interfaces:**
- Produces: `HistoricalDataGateway.fetch_stock_minutes(symbol, start, end) -> pd.DataFrame`
- Produces: `HistoricalDataGateway.fetch_crypto_minutes(symbol, start, end) -> pd.DataFrame`
- Every returned frame has UTC `DatetimeIndex` and columns exactly `open, high, low, close, volume`.

- [ ] **Step 1: Write frame-normalization tests using static fixtures**

```python
from clockcross.alpaca.historical import normalize_bars


def test_normalize_bars_returns_sorted_utc_index(stock_fixture):
    frame = normalize_bars(stock_fixture)
    assert str(frame.index.tz) == "UTC"
    assert frame.index.is_monotonic_increasing
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
```

- [ ] **Step 2: Write a failing extended-hours contract test**

The test must assert that a fixture containing an `08:45 ET` COIN bar remains present after normalization; this prevents accidentally dropping premarket data.

- [ ] **Step 3: Run tests and verify failure**

Run: `uv run pytest tests/unit/test_historical.py -q`
Expected: missing module/function.

- [ ] **Step 4: Implement `AlpacaClients` factory**

Create stock, crypto, trading, and options clients lazily from `Settings`. No module-level network clients and no logging of credentials.

- [ ] **Step 5: Implement normalization and retrieval**

Use Alpaca minute bars, preserve extended-hours bars, sort/dedupe by timestamp, reject duplicate timestamps with conflicting OHLC values, and fail if returned timestamps are naive.

- [ ] **Step 6: Add raw-cache support**

For research commands, write provider responses normalized to Parquet or CSV under `artifacts/raw/<symbol>/...` using date-range and feed in the filename. Cache metadata must include retrieval time, provider, feed, requested start/end, and row count.

- [ ] **Step 7: Run fixture tests**

Run: `uv run pytest tests/unit/test_historical.py -q`
Expected: pass.

- [ ] **Step 8: Run the real contract test only when development credentials exist**

Run: `CLOCKCROSS_INTEGRATION=1 uv run pytest tests/integration/test_alpaca_historical_contract.py -q`
Expected: the test skips without credentials; with credentials it verifies non-empty BTC/USD and COIN data plus timezone/feed metadata. It must never submit an order.

- [ ] **Step 9: Commit**

```bash
git add src/clockcross/alpaca tests

git commit -m "feat: add Alpaca historical data gateway"
```

---

### Task 3: Build leakage-safe daily episodes and residual features

**Files:**
- Create: `src/clockcross/research/episodes.py`
- Create: `src/clockcross/research/residual.py`
- Create: `tests/unit/test_episodes.py`
- Create: `tests/unit/test_residual.py`

**Interfaces:**
- Consumes: normalized UTC minute bars from Task 2.
- Produces: `build_episode_frame(btc, equity, sessions, beta_lookback) -> pd.DataFrame`.
- Output columns: `session_date, btc_return, prior_close, premarket_price, equity_premarket_return, beta, expected_return, residual, open_10m_return, forward_30m_return, forward_60m_return, training_start, training_end`.

- [ ] **Step 1: Write explicit leakage tests**

Create synthetic bars where the only giant price jump occurs at `09:26 ET`. Assert that the premarket reference price for that day still uses the last timestamp `<=09:25 ET`.

- [ ] **Step 2: Write rolling-beta tests**

```python
import numpy as np
from clockcross.research.residual import rolling_beta


def test_rolling_beta_recovers_known_linear_relationship():
    x = np.array([0.01, -0.02, 0.03, 0.00, 0.02])
    y = 1.5 * x
    assert rolling_beta(x, y) == pytest.approx(1.5)
```

Also test zero crypto variance returns `None` rather than infinity.

- [ ] **Step 3: Write a prior-data-only beta test**

Construct three sessions so the current session would radically alter beta if included. Assert day `D` beta is fitted strictly from sessions `< D`.

- [ ] **Step 4: Run tests and verify failure**

Run: `uv run pytest tests/unit/test_episodes.py tests/unit/test_residual.py -q`
Expected: missing implementation.

- [ ] **Step 5: Implement deterministic session extraction**

Definitions:

```text
prior_close = last regular-session close before D
premarket_price = last equity close timestamp <= D 09:25 ET and after 04:00 ET
btc_reference_start = BTC close nearest prior equity regular close timestamp
btc_reference_end = BTC close nearest D 09:25 ET
open_10m_return = equity 09:40 close / 09:30 open - 1
forward_30m_return = equity 10:10 close / 09:40 close - 1
forward_60m_return = equity 10:40 close / 09:40 close - 1
```

If a required timestamp cannot be reconstructed within a documented tolerance, mark the episode invalid instead of forward-filling across arbitrary gaps.

- [ ] **Step 6: Implement beta and residual calculation**

Start with no-intercept OLS beta on the prior `20` valid sessions as the initial research baseline. Make `beta_lookback` configurable. The validator in Task 4, not this function, decides whether another lookback is promoted.

- [ ] **Step 7: Run tests and quality checks**

Run: `uv run pytest tests/unit/test_episodes.py tests/unit/test_residual.py -q`
Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add src/clockcross/research tests/unit/test_episodes.py tests/unit/test_residual.py

git commit -m "feat: build leakage-safe cross-market episodes"
```

---

### Task 4: Implement chronological validation, baselines, and falsification report

**Files:**
- Create: `src/clockcross/research/metrics.py`
- Create: `src/clockcross/research/validation.py`
- Create: `src/clockcross/research/report.py`
- Create: `tests/unit/test_validation.py`
- Create: `tests/unit/test_metrics.py`
- Create: `docs/research/README.md`

**Interfaces:**
- Produces: `ValidationResult`, `FoldResult`, `ResearchVerdict` (`GO`, `MUTATE`, `KILL`).
- Produces: `evaluate_residual_strategy(frame, config) -> ValidationResult`.
- Produces: `write_research_report(result, path_json, path_md)`.

- [ ] **Step 1: Write chronological-fold tests**

```python
from clockcross.research.validation import expanding_folds


def test_expanding_folds_never_train_on_or_after_test_dates():
    folds = expanding_folds(dates, min_train=60, test_size=20)
    for fold in folds:
        assert max(fold.train_dates) < min(fold.test_dates)
```

- [ ] **Step 2: Write baseline and outlier-sensitivity tests**

Metrics must include count, mean/median forward return, hit rate, standard error, total signed return, worst/best episode, leave-one-out max impact, and comparison against unconditional same-window return.

- [ ] **Step 3: Write verdict tests using synthetic datasets**

Three fixtures:

1. persistent synthetic residual effect -> `GO`;
2. effect only in one fold -> `MUTATE` or `KILL`;
3. no effect / QQQ equally strong -> `KILL`.

Do not encode a financial-performance threshold that pretends statistical certainty. The verdict combines explicit evidence checks and records each check separately.

- [ ] **Step 4: Run tests and verify failure**

Run: `uv run pytest tests/unit/test_validation.py tests/unit/test_metrics.py -q`
Expected: missing implementation.

- [ ] **Step 5: Implement validation configuration**

Evaluate a deliberately small grid only:

```text
beta lookback: 10, 20, 40 sessions
residual normalization: raw and rolling z-score
thesis: continuation and reversion
minimum absolute residual z: 0.5, 1.0, 1.5
forward horizon: 30m, 60m
```

The grid is frozen in code before the first real run. Do not add candidates after inspecting performance unless a new research iteration is explicitly documented.

- [ ] **Step 6: Implement expanding-window evaluation and control series comparison**

Report COIN and MSTR separately and pooled only after separate results. Compare the same procedure on QQQ. Include all folds, including negative folds.

- [ ] **Step 7: Implement conservative friction sensitivity**

At signal level, subtract configurable round-trip return hurdles `0`, `25`, `50`, and `100` bps from each qualifying underlying move to answer whether tiny apparent effects disappear under plausible option friction. This is not an option backtest and must be labelled as such.

- [ ] **Step 8: Generate immutable JSON + Markdown report**

Include configuration hash, raw-data cache identifiers, code commit SHA when available, fold table, baseline/control comparison, leave-one-out sensitivity, and verdict checks.

- [ ] **Step 9: Run all research tests**

Run: `uv run pytest tests/unit/test_validation.py tests/unit/test_metrics.py -q`
Expected: pass.

- [ ] **Step 10: Commit**

```bash
git add src/clockcross/research tests/unit/test_validation.py tests/unit/test_metrics.py docs/research

git commit -m "feat: add chronological falsification harness"
```

---

### Task 5: Add a research CLI and perform the real weekend falsification pass

**Files:**
- Create: `src/clockcross/main.py`
- Create: `tests/unit/test_cli.py`
- Generate after execution: `artifacts/research/verdict.json`
- Generate after execution: `docs/research/initial-verdict.md`

**Interfaces:**
- Produces CLI: `clockcross research --start YYYY-MM-DD --end YYYY-MM-DD`.
- Produces a machine-readable `ResearchVerdict` consumed by scheduler startup.

- [ ] **Step 1: Write CLI tests using fake gateways**

Assert `research` exits non-zero on insufficient history, writes both report formats on valid fixtures, and never instantiates a trading client.

- [ ] **Step 2: Run test and verify failure**

Run: `uv run pytest tests/unit/test_cli.py -q`
Expected: CLI missing.

- [ ] **Step 3: Implement Typer-free minimal CLI with `argparse`**

Use stdlib `argparse` to avoid another dependency. Subcommands at this stage: `research` only.

- [ ] **Step 4: Run CLI unit tests**

Run: `uv run pytest tests/unit/test_cli.py -q`
Expected: pass.

- [ ] **Step 5: Run real historical pull against the development account/data entitlement**

Run a history window as far back as Alpaca reliably supplies synchronized BTC + extended-hours COIN/MSTR/QQQ minute data. Record the actual earliest complete date; do not invent it in advance.

Command pattern:

```bash
uv run clockcross research --start 2024-01-01 --end 2026-08-28
```

If provider coverage begins later, rerun from the earliest defensible complete date and record that limitation in the report.

- [ ] **Step 6: Inspect data-quality diagnostics before looking at performance**

Check missing sessions, missing 09:25 prices, suspicious duplicated timestamps, feed metadata, and coverage by ticker. If coverage is inadequate, stop and classify `MUTATE` rather than patching gaps with future data.

- [ ] **Step 7: Freeze the real verdict artifact**

`docs/research/initial-verdict.md` must say exactly one of:

```text
GO: residual family survives the predefined chronological checks.
MUTATE: some cross-market information exists but original residual formulation fails one or more promotion gates.
KILL: no defensible residual effect remains after chronology/control/friction checks.
```

List every failed and passed gate.

- [ ] **Step 8: Commit code plus non-secret research outputs**

```bash
git add src/clockcross/main.py tests/unit/test_cli.py docs/research/initial-verdict.md artifacts/research/verdict.json

git commit -m "research: freeze initial ClockCross verdict"
```

**Checkpoint:** If verdict is `KILL`, do not execute Tasks 6-11 unchanged. Preserve the harness, create a new narrowly scoped design amendment for the next hypothesis, and re-plan the signal-specific tasks. If verdict is `MUTATE`, only proceed after the mutation is recorded in `docs/research/initial-verdict.md` and remains inside the approved cross-market thesis. `GO` proceeds directly.

---

### Task 6: Implement bounded AI adjudication and Alpaca MCP evidence capture

**Files:**
- Create: `src/clockcross/agent/prompts.py`
- Create: `src/clockcross/agent/adjudicator.py`
- Create: `src/clockcross/alpaca/mcp.py`
- Create: `tests/unit/test_adjudicator.py`
- Create: `tests/unit/test_mcp.py`

**Interfaces:**
- Produces: `Adjudicator.decide(context: AgentContext) -> AgentDecision`.
- Produces: `AlpacaMcpGateway.collect_context(request: McpContextRequest) -> McpEvidence`.
- Malformed/unavailable AI or MCP context returns a typed failure that downstream orchestration converts to abstention.

- [ ] **Step 1: Write fail-closed AI tests**

Test valid `continuation`, valid `reversion`, valid `abstain`, malformed JSON, unsupported action, confidence outside `[0,1]`, timeout, and company-specific news flag.

- [ ] **Step 2: Write prompt-snapshot tests**

Prompt text must explicitly state the approved symbols, allowed actions, inability to override risk, and instruction to abstain on unclear company-specific news. Keep the full prompt under a fixed character budget and assert it in tests.

- [ ] **Step 3: Run tests and verify failure**

Run: `uv run pytest tests/unit/test_adjudicator.py tests/unit/test_mcp.py -q`
Expected: missing modules.

- [ ] **Step 4: Implement an OpenAI-compatible HTTP adjudicator interface**

Configure `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` via environment so Featherless/OpenAI-compatible providers can be swapped without changing trading code. Request strict JSON and validate with `AgentDecision.model_validate_json`.

- [ ] **Step 5: Implement Alpaca MCP invocation as an auditable subprocess/stdio boundary**

The gateway must record tool name, sanitized arguments, invocation timestamp, success/failure, and a hash/identifier of the returned structured context. Never persist API keys or entire sensitive account payloads.

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/unit/test_adjudicator.py tests/unit/test_mcp.py -q`
Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add src/clockcross/agent src/clockcross/alpaca/mcp.py tests/unit/test_adjudicator.py tests/unit/test_mcp.py

git commit -m "feat: add bounded AI and Alpaca MCP context"
```

---

### Task 7: Build deterministic option-spread construction and risk governor

**Files:**
- Create: `src/clockcross/alpaca/options.py`
- Create: `src/clockcross/trading/constructor.py`
- Create: `src/clockcross/trading/risk.py`
- Create: `tests/unit/test_constructor.py`
- Create: `tests/unit/test_risk.py`

**Interfaces:**
- Produces: `construct_vertical(chain, thesis, policy) -> SpreadCandidate | None`.
- Produces: `RiskGovernor.evaluate(candidate, portfolio, now) -> RiskDecision`.
- `RiskDecision.approved` must be required by execution code; no boolean shortcuts.

- [ ] **Step 1: Write constructor tests with synthetic option chains**

Cover bullish call spread, bearish put spread, mismatched expirations, 0DTE rejection, wrong ratios, stale quotes, missing bid/ask, and no contract satisfying the policy.

- [ ] **Step 2: Write exact max-loss tests using Decimal**

For a debit spread with net debit `$2.35`, assert maximum loss is `$235` per spread before fees. Verify debit cannot be negative and short-leg strike ordering is correct for calls/puts.

- [ ] **Step 3: Write risk-envelope tests**

Test per-position max loss, aggregate max loss, one-position-per-underlying, buying power, allowed symbol, time window, stale quote, and final-event liquidation cutoff.

- [ ] **Step 4: Run and verify failure**

Run: `uv run pytest tests/unit/test_constructor.py tests/unit/test_risk.py -q`
Expected: missing implementation.

- [ ] **Step 5: Implement a deterministic initial strike policy**

Policy, configurable but frozen before competition-account start:

```text
DTE: 7-21
long-leg absolute delta target: nearest available to 0.55
short-leg absolute delta target: nearest available to 0.35
minimum open interest: 100 per leg when field is available
minimum volume: 1 per leg when field is available
maximum quote age: 60 seconds at decision time
maximum leg relative spread: 25%
maximum candidate net debit: risk-governor derived
```

If Greeks/open-interest fields are unavailable under the active feed, the constructor must not fabricate them. It should fall back only to explicitly documented deterministic strike-distance rules covered by tests, or return no candidate.

- [ ] **Step 6: Implement risk policy configuration**

Use starting-equity percentages but calculate dollar caps once per episode. Defaults for development: `1%` per-position max loss and `5%` aggregate defined loss; competition values remain configuration and are frozen after dry-runs.

- [ ] **Step 7: Run tests and checks**

Run: `uv run pytest tests/unit/test_constructor.py tests/unit/test_risk.py -q`
Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add src/clockcross/alpaca/options.py src/clockcross/trading tests/unit/test_constructor.py tests/unit/test_risk.py

git commit -m "feat: add defined-risk options construction"
```

---

### Task 8: Implement SQLite decision ledger and idempotent state machine

**Files:**
- Create: `src/clockcross/ledger.py`
- Create: `src/clockcross/state.py`
- Create: `tests/unit/test_ledger.py`
- Create: `tests/unit/test_state.py`

**Interfaces:**
- Produces: `Ledger.create_episode`, `Ledger.transition`, `Ledger.record_decision`, `Ledger.record_risk`, `Ledger.record_order`, `Ledger.get_open_episode`.
- Produces: `EpisodeMachine.advance(event) -> EpisodeState`.

- [ ] **Step 1: Write state-transition tests**

Legal path must follow the spec. Assert direct `COLLECTING -> ORDER_SUBMITTED` raises `InvalidTransition`. `ABSTAINED` is terminal for that day's decision path.

- [ ] **Step 2: Write idempotency tests**

Creating the same `(session_date, underlying)` episode twice returns the existing episode; recording the same client order ID twice does not create a second order row.

- [ ] **Step 3: Write persistence/restart test**

Create an episode, close the connection, reopen the SQLite file, and assert state/order IDs survive.

- [ ] **Step 4: Run and verify failure**

Run: `uv run pytest tests/unit/test_ledger.py tests/unit/test_state.py -q`
Expected: missing implementation.

- [ ] **Step 5: Implement schema with stdlib `sqlite3`**

Tables: `episodes`, `transitions`, `features`, `agent_decisions`, `risk_decisions`, `orders`, `marks`. Enable foreign keys and WAL mode. Use JSON text for structured payloads but keep searchable core columns separate.

- [ ] **Step 6: Implement atomic transition + ledger writes**

Every irreversible state change must execute inside a DB transaction. Use unique constraints on episode identity and `client_order_id`.

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/unit/test_ledger.py tests/unit/test_state.py -q`
Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add src/clockcross/ledger.py src/clockcross/state.py tests/unit/test_ledger.py tests/unit/test_state.py

git commit -m "feat: add durable decision ledger"
```

---

### Task 9: Implement idempotent Alpaca paper execution and reconciliation

**Files:**
- Create: `src/clockcross/trading/execution.py`
- Create: `tests/unit/test_execution.py`
- Create: `tests/integration/test_development_paper_mleg.py`

**Interfaces:**
- Produces: `ExecutionService.submit(candidate, episode_id) -> OrderRecord`.
- Produces: `ExecutionService.reconcile(order_record) -> OrderRecord`.
- Client order ID format: `clockcross-YYYYMMDD-UNDERLYING-<episode-id-prefix>`.

- [ ] **Step 1: Write duplicate-submission test**

Simulate a timeout after Alpaca accepts the request. On retry, execution must query by client order ID and reconcile the existing order instead of submitting another.

- [ ] **Step 2: Write paper-only guard test**

Even if a fake client is configured with a live endpoint, `ExecutionService` must refuse to submit.

- [ ] **Step 3: Write exact MLeg request test**

Assert two legs, ratio `1`, correct buy/sell sides, `order_class=mleg`, `type=limit`, and positive debit limit price.

- [ ] **Step 4: Run and verify failure**

Run: `uv run pytest tests/unit/test_execution.py -q`
Expected: missing implementation.

- [ ] **Step 5: Implement submit/reconcile with bounded retries**

Only retry transport/5xx errors. Before each retry, query Alpaca for the deterministic client order ID. Persist order identity before polling fills.

- [ ] **Step 6: Run unit tests**

Run: `uv run pytest tests/unit/test_execution.py -q`
Expected: pass.

- [ ] **Step 7: Run development-account integration smoke test**

The integration test must require both `CLOCKCROSS_INTEGRATION=1` and `CLOCKCROSS_ALLOW_DEV_ORDER=1`. It verifies account endpoint is paper, constructs a tiny valid MLeg order only when market conditions permit, submits/cancels it, and records the result. The test must explicitly refuse to run when `CLOCKCROSS_ACCOUNT_ROLE=competition`.

- [ ] **Step 8: Commit**

```bash
git add src/clockcross/trading/execution.py tests/unit/test_execution.py tests/integration/test_development_paper_mleg.py

git commit -m "feat: add idempotent Alpaca paper execution"
```

---

### Task 10: Orchestrate one complete autonomous decision episode

**Files:**
- Create: `src/clockcross/scheduler.py`
- Modify: `src/clockcross/main.py`
- Create: `tests/unit/test_scheduler.py`
- Create: `tests/integration/test_episode_dry_run.py`

**Interfaces:**
- Produces: `Scheduler.run_session(session_date, mode="dry-run|paper") -> EpisodeSummary`.
- CLI adds `run-once --date YYYY-MM-DD --mode dry-run` and `reconcile`.

- [ ] **Step 1: Write orchestration happy-path test with fakes**

Assert call order: collect -> freeze -> opening confirmation -> evidence gate -> MCP context -> AI -> option chain -> constructor -> risk -> execution -> ledger.

- [ ] **Step 2: Write abstention-path tests**

Separate tests for failed evidence gate, AI abstention, stale chain, and risk rejection. Assert no execution call occurs in each case and a rejection reason is persisted.

- [ ] **Step 3: Write restart test**

Seed the ledger at `ORDER_SUBMITTED`, restart scheduler, and assert it reconciles rather than recomputing/reordering the episode.

- [ ] **Step 4: Run and verify failure**

Run: `uv run pytest tests/unit/test_scheduler.py tests/integration/test_episode_dry_run.py -q`
Expected: missing implementation.

- [ ] **Step 5: Implement scheduler as an explicit state-driven orchestrator**

No implicit background threads. `run_session` executes/reconciles one session deterministically and can be triggered externally by a deployment scheduler or cron.

- [ ] **Step 6: Gate production paper mode on frozen research verdict**

`mode="paper"` must refuse startup unless `artifacts/research/verdict.json` exists, its config hash matches the active signal config, and verdict is `GO` or an explicitly approved `MUTATE` specification.

- [ ] **Step 7: Run full dry-run tests**

Run: `uv run pytest tests/unit/test_scheduler.py tests/integration/test_episode_dry_run.py -q`
Expected: pass with no network dependency.

- [ ] **Step 8: Commit**

```bash
git add src/clockcross/scheduler.py src/clockcross/main.py tests/unit/test_scheduler.py tests/integration/test_episode_dry_run.py

git commit -m "feat: orchestrate autonomous ClockCross episodes"
```

---

### Task 11: Build the minimal judge-facing evidence console

**Files:**
- Create: `src/clockcross/api.py`
- Create: `src/clockcross/templates/index.html`
- Create: `tests/unit/test_api.py`

**Interfaces:**
- HTTP: `GET /health`, `GET /ready`, `GET /api/status`, `GET /api/episodes`, `GET /api/research`, `GET /`.
- No mutation/trade endpoints in the public demo.

- [ ] **Step 1: Write API contract tests**

Use FastAPI TestClient. `/health` returns process health; `/ready` fails if DB/research artifact is unavailable; `/api/status` exposes only sanitized account summary; `/api/episodes` includes abstentions.

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/unit/test_api.py -q`
Expected: missing implementation.

- [ ] **Step 3: Implement read-only API**

Never return account ID, API keys, raw headers, or full provider payloads. Round public account values sensibly but preserve actual P&L.

- [ ] **Step 4: Implement one static server-rendered evidence page**

Sections: current equity/P&L and state; latest residual equation inputs; AI decision; risk gates; position/order status; decision history including abstentions; research verdict/limitations. No frontend build chain.

- [ ] **Step 5: Add `serve` CLI subcommand**

Run Uvicorn using `clockcross.api:create_app`.

- [ ] **Step 6: Run tests and manual local smoke**

Run:

```bash
uv run pytest tests/unit/test_api.py -q
uv run clockcross serve --host 127.0.0.1 --port 8000
```

Expected: page loads and exposes no secret/account identifier.

- [ ] **Step 7: Commit**

```bash
git add src/clockcross/api.py src/clockcross/templates src/clockcross/main.py tests/unit/test_api.py

git commit -m "feat: add ClockCross evidence console"
```

---

### Task 12: Competition hardening, full verification, and handoff artifacts

**Files:**
- Modify: `README.md`
- Create: `docs/ONE_PAGE_WRITEUP.md`
- Create: `docs/OPERATIONS.md`
- Create: `docs/SUBMISSION_CHECKLIST.md`
- Create: `.github/workflows/ci.yml`
- Create: `tests/test_no_secrets.py`

**Interfaces:**
- Produces a reproducible public repository and deployment checklist.

- [ ] **Step 1: Write repository secret-regression test**

Scan tracked text fixtures/config examples for patterns including `APCA-API-KEY-ID`, `APCA-API-SECRET-KEY`, `sk-`, and known local credential values injected by test environment. Whitelist only literal placeholder names such as `your-key-here`.

- [ ] **Step 2: Add CI**

CI runs:

```bash
uv sync --frozen
uv run ruff check .
uv run mypy src/clockcross
uv run pytest -q
```

No real Alpaca/LLM credentials in CI; network integration tests remain skipped.

- [ ] **Step 3: Write evidence-first README**

README structure:

```text
What ClockCross tests
Why raw BTC->COIN is insufficient
Residual equation and time boundaries
Chronological evidence and verdict
Autonomous decision flow
AI authority vs deterministic gates
Alpaca MCP/API implementation
Actual competition account results
Run locally
Limitations and disclosures
```

Do not copy pre-hackathon performance claims from unrelated repos.

- [ ] **Step 4: Write required one-page logic/risk/infrastructure document**

`docs/ONE_PAGE_WRITEUP.md` must fit approximately one printed page and cover AI logic, risk gates, and Alpaca infrastructure per event requirement.

- [ ] **Step 5: Write operations procedure**

Explicitly distinguish development and competition accounts. Competition checklist:

```text
new Alpaca paper account
starting equity exactly $100,000
fresh credentials stored only in deployment secrets
CLOCKCROSS_ACCOUNT_ROLE=competition
paper endpoint verified
research verdict/config hash verified
no dev-order flag present
read-only preflight succeeds
```

- [ ] **Step 6: Run full verification before any competition-account start**

Run:

```bash
uv sync --frozen
uv run ruff check .
uv run mypy src/clockcross
uv run pytest -q
uv run clockcross research --start <recorded-earliest-complete-date> --end 2026-08-28
uv run clockcross run-once --date 2026-08-31 --mode dry-run
```

Expected: all static/unit tests pass, research artifact hash matches config, dry run either produces a valid hypothetical spread or an explicit abstention without sending an order.

- [ ] **Step 7: Verify Alpaca MCP visibly**

Run the documented MCP context call with the development environment and capture only sanitized evidence metadata in the ledger/demo. Confirm the project satisfies the event's MCP-or-CLI requirement before competition start.

- [ ] **Step 8: Freeze competition configuration**

Create a committed non-secret config fingerprint in the research/operations docs containing symbol universe, feature times, beta lookback, signal rule, DTE, strike policy, freshness limits, and risk percentages. Any later change requires a changelog entry with reason.

- [ ] **Step 9: Commit hardening artifacts**

```bash
git add README.md docs .github tests/test_no_secrets.py

git commit -m "docs: prepare ClockCross competition submission"
```

- [ ] **Step 10: Create competition account only after all development smoke tests pass**

This is an external account operation, not a repository change. Verify `$100,000`, paper endpoint, options permissions, and read-only data access. Do not place a smoke order.

- [ ] **Step 11: Start autonomous competition run**

Use the deployment scheduler to invoke `clockcross run-once --date <session> --mode paper` after the opening confirmation boundary. Preserve logs and ledger. Do not manually alter P&L.

---

## Plan Self-Review

### Spec coverage

- Research-before-build gate: Tasks 2-5.
- Explicit leakage/time boundaries: Tasks 1, 3, 4.
- GO/MUTATE/KILL falsification: Tasks 4-5.
- Meaningful bounded AI: Task 6.
- Alpaca MCP as real project surface: Tasks 6 and 12.
- Defined-risk option spreads and Basic/OPRA awareness: Task 7.
- Deterministic risk governor: Task 7.
- Durable ledger/state/idempotency: Tasks 8-10.
- Separate dev/competition account discipline: Tasks 9 and 12.
- Judge-facing evidence console: Task 11.
- Submission evidence, CI, secret safety: Task 12.

### Placeholder scan

The plan deliberately contains one command placeholder, `<recorded-earliest-complete-date>`, because Task 5 requires measuring the provider's actual synchronized-history boundary before it is knowable. The value is not an implementation TODO: Task 5 must record a concrete date in `docs/research/initial-verdict.md`, and Task 12 consumes that exact recorded value. No feature behavior is left undefined behind `TBD`/`TODO` language.

### Type/interface consistency

- Research produces a typed `ResearchVerdict` consumed by scheduler paper-mode guard.
- Agent output is always `AgentDecision`.
- Constructor output is always `SpreadCandidate | None`.
- Risk returns `RiskDecision`, which execution requires before order creation.
- Order idempotency uses a deterministic `client_order_id` persisted by `Ledger`.
- Scheduler is the only component orchestrating irreversible execution.
