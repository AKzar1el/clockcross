# ClockCross Competition Runtime Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ClockCross operate the dedicated Alpaca paper competition account autonomously from the frozen 09:55 ET decision through a bounded opening order and deterministic 10:55 ET spread exit, with restart-safe reconciliation and scheduled GitHub Actions execution.

**Architecture:** Preserve the existing frozen research/signal path and add lifecycle orchestration around it. Extend the durable SQLite state machine for an explicit exit phase, keep all broker mutations behind the paper-only execution adapter, add a competition orchestrator that polls/cancels/reconciles exact deterministic order identities, and schedule that orchestrator from GitHub Actions with state artifact restoration between runs. Alpaca remains the remote source of truth for orders/positions; SQLite remains the local audit trail and recovery context.

**Tech Stack:** Python 3.12, Pydantic 2, httpx, SQLite, pytest, mypy strict, Ruff, Alpaca Trading/Data APIs, Alpaca MCP, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-31-competition-runtime-hardening.md`

## Global Constraints

- Keep the frozen live policy `coin-continuation-beta40-raw1pct-2026-08-29` unchanged.
- Keep the approved mutation `coin-options-2026-08-29` unchanged.
- Execution universe remains `COIN` only.
- Entry remains a 1:1 same-expiration 7–21 DTE call/put debit spread.
- AI authority remains exactly `continuation | reversion | abstain`; it cannot choose symbols, contracts, prices, sizing, exits, or risk limits.
- Alpaca execution remains hard-pinned to `https://paper-api.alpaca.markets`.
- Competition starting equity remains exactly `$100,000` before the first competition episode.
- `CLOCKCROSS_ACCOUNT_ROLE=competition` must always imply `CLOCKCROSS_ALLOW_DEV_ORDER=false`.
- Entry decision boundary remains 09:55 ET; competition runtime must refuse a new entry after 10:05 ET rather than trading a materially delayed signal.
- Deterministic exit target is 10:55 ET because the frozen research horizon is `forward_60m_return` from 09:55 ET to 10:55 ET.
- Opening order fill window is fixed at 180 seconds; no adaptive chasing.
- Close policy uses exact opening contracts, 1:1 quantity, deterministic identities, and at most one cancel/reprice replacement. No LLM-directed exits.
- Never blind-retry an uncertain Alpaca POST. Reconcile by deterministic `client_order_id` first.
- Do not upload or print credentials, environment dumps, API headers, or bearer tokens.
- Do not change MSTR/QQQ research evidence, the original `MUTATE` verdict, or the 100 bps friction failure.

---

### Task 1: Extend the episode state machine and ledger for exit lifecycle persistence

**Files:**
- Modify: `src/clockcross/domain.py`
- Modify: `src/clockcross/state.py`
- Modify: `src/clockcross/ledger.py`
- Modify: `tests/unit/test_state.py`
- Modify: `tests/unit/test_ledger.py`

**Interfaces:**
- Produces: `EpisodeState.EXIT_SUBMITTED`.
- Produces: `Ledger.get_unresolved_episode(underlying: str) -> EpisodeRecord | None`.
- Produces: `Ledger.get_orders_for_episode(episode_id: str) -> list[OrderRecord]`.
- Produces: `Ledger.get_latest_order_for_phase(episode_id: str, phase: str) -> OrderRecord | None` where phase is persisted in `payload_json`.
- Preserves: existing `Ledger.record_order`, `Ledger.update_order`, and all current schema/table names.

- [ ] **Step 1: Write failing state-machine tests**

Add tests proving the legal filled-position path is explicit and that exit submission is non-terminal:

```python
def test_filled_position_requires_explicit_exit_submission_before_close():
    machine = EpisodeMachine(EpisodeState.ORDER_FILLED)
    assert machine.advance(EpisodeState.MONITORING) is EpisodeState.MONITORING
    assert machine.advance(EpisodeState.EXIT_SUBMITTED) is EpisodeState.EXIT_SUBMITTED
    assert machine.advance(EpisodeState.CLOSED) is EpisodeState.CLOSED


def test_monitoring_cannot_jump_directly_to_closed():
    machine = EpisodeMachine(EpisodeState.MONITORING)
    with pytest.raises(InvalidTransition):
        machine.advance(EpisodeState.CLOSED)
```

- [ ] **Step 2: Run the focused state tests and verify RED**

Run:

```bash
uv run pytest tests/unit/test_state.py -q
```

Expected: FAIL because `EpisodeState.EXIT_SUBMITTED` does not exist and `MONITORING -> CLOSED` is currently legal.

- [ ] **Step 3: Add the minimal state enum and transition changes**

Implement exactly:

```python
class EpisodeState(StrEnum):
    ...
    MONITORING = "MONITORING"
    EXIT_SUBMITTED = "EXIT_SUBMITTED"
    CLOSED = "CLOSED"
```

and change `_ALLOWED` so:

```python
EpisodeState.MONITORING: frozenset({EpisodeState.EXIT_SUBMITTED}),
EpisodeState.EXIT_SUBMITTED: frozenset({EpisodeState.CLOSED}),
```

Do not add extra exit states unless a later failing test proves they are needed.

- [ ] **Step 4: Run the focused state tests and verify GREEN**

Run:

```bash
uv run pytest tests/unit/test_state.py -q
```

Expected: PASS.

- [ ] **Step 5: Write failing ledger recovery tests**

Add tests that create multiple orders with payload phases and verify cross-session unresolved lookup:

```python
def test_ledger_finds_unresolved_coin_episode_across_dates(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    old = ledger.create_episode(date(2026, 8, 31), "COIN")
    ledger.transition(old.episode_id, EpisodeState.FEATURES_FROZEN, event="x")
    unresolved = ledger.get_unresolved_episode("COIN")
    assert unresolved is not None
    assert unresolved.episode_id == old.episode_id


def test_ledger_returns_latest_order_for_phase(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    episode = ledger.create_episode(date(2026, 8, 31), "COIN")
    ledger.record_order(
        episode.episode_id,
        client_order_id="open-1",
        alpaca_order_id="a1",
        status="filled",
        payload={"phase": "open"},
    )
    ledger.record_order(
        episode.episode_id,
        client_order_id="close-1",
        alpaca_order_id="a2",
        status="accepted",
        payload={"phase": "close", "attempt": 0},
    )
    assert ledger.get_latest_order_for_phase(episode.episode_id, "open").client_order_id == "open-1"
    assert ledger.get_latest_order_for_phase(episode.episode_id, "close").client_order_id == "close-1"
```

- [ ] **Step 6: Run the focused ledger tests and verify RED**

Run:

```bash
uv run pytest tests/unit/test_ledger.py -q
```

Expected: FAIL because the recovery query helpers do not exist.

- [ ] **Step 7: Implement minimal ledger query helpers**

Implement `get_unresolved_episode` by selecting the oldest/newest non-terminal episode for the underlying with state not in `ABSTAINED`/`CLOSED`. Implement phase lookup without schema migration by reading `payload_json` from the episode's ordered rows and choosing the latest row whose decoded payload has the requested `phase`.

Do not add a new database column for phase during this competition hardening pass.

- [ ] **Step 8: Run focused ledger + state tests**

Run:

```bash
uv run pytest tests/unit/test_state.py tests/unit/test_ledger.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit Task 1**

```bash
git add src/clockcross/domain.py src/clockcross/state.py src/clockcross/ledger.py tests/unit/test_state.py tests/unit/test_ledger.py
git commit -m "feat: persist competition exit lifecycle"
```

---

### Task 2: Add deterministic close-order construction and paper-only MLeg close execution

**Files:**
- Modify: `src/clockcross/trading/execution.py`
- Create: `src/clockcross/trading/exit.py`
- Modify: `tests/unit/test_execution.py`
- Create: `tests/unit/test_exit.py`

**Interfaces:**
- Produces: `CloseInstruction(BaseModel)` with `long_symbol`, `short_symbol`, `limit_price`, `quote_timestamp`, `attempt`.
- Produces: `build_close_client_order_id(episode_id: str, attempt: int) -> str`.
- Produces: `build_close_instruction(chain: OptionChainSnapshot, *, long_symbol: str, short_symbol: str, now: datetime, attempt: int = 0) -> CloseInstruction`.
- Produces: `AlpacaPaperTradingRestClient.submit_close_vertical(instruction: CloseInstruction, *, client_order_id: str) -> dict[str, Any]`.
- Produces: `ExecutionService.submit_close(episode_id: str, instruction: CloseInstruction) -> ExecutionResult` with the same pre-reconcile / timeout-reconcile / no-blind-retry semantics as entry.
- Alpaca semantics: opening long leg closes with `sell_to_close`; opening short leg closes with `buy_to_close`; `order_class=mleg`, `qty=1`, `type=limit`, `time_in_force=day`.

- [ ] **Step 1: Write failing close payload and identity tests**

Add:

```python
def test_close_client_order_id_is_deterministic_per_attempt():
    one = build_close_client_order_id("episode-abc", 0)
    two = build_close_client_order_id("episode-abc", 0)
    replacement = build_close_client_order_id("episode-abc", 1)
    assert one == two
    assert one != replacement
    assert one.startswith("clockcross-close-")
    assert len(one) <= 64


def test_rest_client_closes_exact_vertical_with_close_intents():
    http = FakeHttp()
    client = AlpacaPaperTradingRestClient("key", "secret", http_client=http)
    instruction = CloseInstruction(
        long_symbol="COIN260911C00300000",
        short_symbol="COIN260911C00310000",
        limit_price=Decimal("-1.25"),
        quote_timestamp=datetime(2026, 8, 31, 14, 55, tzinfo=timezone.utc),
        attempt=0,
    )
    client.submit_close_vertical(instruction, client_order_id="clockcross-close-test")
    body = http.posts[0][2]
    assert body["limit_price"] == "-1.25"
    assert body["legs"] == [
        {"symbol": instruction.long_symbol, "ratio_qty": "1", "side": "sell", "position_intent": "sell_to_close"},
        {"symbol": instruction.short_symbol, "ratio_qty": "1", "side": "buy", "position_intent": "buy_to_close"},
    ]
```

- [ ] **Step 2: Run focused execution tests and verify RED**

```bash
uv run pytest tests/unit/test_execution.py -q
```

Expected: FAIL because close instruction/ID/REST methods do not exist.

- [ ] **Step 3: Implement close ID and REST payload minimally**

Use a SHA-256 digest of `{"episode_id": ..., "phase": "close", "attempt": ...}` and prefix with `clockcross-close-`. Do not include prices in the close identity; one deterministic identity exists per fixed attempt.

The REST request must be exactly:

```python
body = {
    "order_class": "mleg",
    "qty": "1",
    "type": "limit",
    "limit_price": _decimal_text(instruction.limit_price),
    "time_in_force": "day",
    "client_order_id": client_order_id,
    "legs": [
        {"symbol": instruction.long_symbol, "ratio_qty": "1", "side": "sell", "position_intent": "sell_to_close"},
        {"symbol": instruction.short_symbol, "ratio_qty": "1", "side": "buy", "position_intent": "buy_to_close"},
    ],
}
```

A negative MLeg limit price is a credit under Alpaca's documented convention; a positive value is a debit.

- [ ] **Step 4: Run close payload tests and verify GREEN**

```bash
uv run pytest tests/unit/test_execution.py -q
```

Expected: PASS for the new payload tests and all previous opening execution tests.

- [ ] **Step 5: Write failing quote-to-close instruction tests**

Construct a two-contract `OptionChainSnapshot` and assert the exact contracts are reused. Initial attempt 0 asks for the conservative natural close credit, floored at one cent of credit; attempt 1 is the fixed final replacement at one cent credit:

```python
def test_close_instruction_uses_exact_contracts_and_natural_credit():
    instruction = build_close_instruction(
        chain_with(long_bid="3.10", long_ask="3.20", short_bid="1.70", short_ask="1.80"),
        long_symbol=LONG,
        short_symbol=SHORT,
        now=NOW,
        attempt=0,
    )
    assert instruction.limit_price == Decimal("-1.30")


def test_close_replacement_uses_fixed_one_cent_credit_floor():
    instruction = build_close_instruction(
        chain_with(long_bid="0.05", long_ask="0.10", short_bid="0.05", short_ask="0.10"),
        long_symbol=LONG,
        short_symbol=SHORT,
        now=NOW,
        attempt=1,
    )
    assert instruction.limit_price == Decimal("-0.01")
```

Also test stale quotes, missing exact symbols, crossed/zero quotes, and `attempt > 1` fail closed.

- [ ] **Step 6: Run `test_exit.py` and verify RED**

```bash
uv run pytest tests/unit/test_exit.py -q
```

Expected: FAIL because `build_close_instruction` is missing.

- [ ] **Step 7: Implement minimal deterministic close pricing**

For attempt 0:

```python
natural_credit = long_leg.bid - short_leg.ask
credit = max(Decimal("0.01"), natural_credit.quantize(Decimal("0.01"), rounding=ROUND_DOWN))
limit_price = -credit
```

Require both exact contracts, fresh timestamps within 60 seconds, positive/non-crossed bid/ask, same expiration, and correct call/put vertical ordering inherited from the opening symbols. For attempt 1, use exactly `Decimal("-0.01")`. Never submit a debit to close a long debit spread in this hardening pass; if a sane credit quote cannot be built, fail closed and retry with fresh quotes later.

- [ ] **Step 8: Write failing `ExecutionService.submit_close` timeout/idempotency tests**

Mirror opening tests but assert phase payload preservation:

```python
def test_close_timeout_reconciles_without_second_post(tmp_path):
    ...
    result = service.submit_close(episode.episode_id, instruction)
    assert result.reconciled is True
    assert trading.close_submit_count == 1


def test_close_timeout_without_remote_proof_is_indeterminate(tmp_path):
    ...
    with pytest.raises(IndeterminateOrderError):
        service.submit_close(episode.episode_id, instruction)
    assert trading.close_submit_count == 1
    stored = ledger.get_latest_order_for_phase(episode.episode_id, "close")
    assert stored is not None and stored.status == "indeterminate"
```

- [ ] **Step 9: Run the new service tests and verify RED**

```bash
uv run pytest tests/unit/test_execution.py tests/unit/test_exit.py -q
```

Expected: FAIL on `submit_close`.

- [ ] **Step 10: Implement `submit_close` by reusing the existing reconcile-before-submit pattern**

Persist close order payload with at least:

```python
{
    "phase": "close",
    "attempt": instruction.attempt,
    "long_leg": instruction.long_symbol,
    "short_leg": instruction.short_symbol,
    "limit_price": format(instruction.limit_price, "f"),
    "quote_timestamp": instruction.quote_timestamp.isoformat(),
}
```

When updating an existing order after broker reconciliation, merge `provider_status` into the existing payload instead of replacing and losing phase/contract metadata.

- [ ] **Step 11: Run Task 2 tests and commit**

```bash
uv run pytest tests/unit/test_execution.py tests/unit/test_exit.py -q
git add src/clockcross/trading/execution.py src/clockcross/trading/exit.py tests/unit/test_execution.py tests/unit/test_exit.py
git commit -m "feat: add idempotent options spread exits"
```

---

### Task 3: Implement the autonomous competition session orchestrator

**Files:**
- Create: `src/clockcross/competition.py`
- Modify: `src/clockcross/runtime.py`
- Modify: `src/clockcross/scheduler.py`
- Create: `tests/unit/test_competition.py`
- Modify: `tests/unit/test_runtime_cli.py`

**Interfaces:**
- Produces: `CompetitionPolicy(open_fill_seconds=180, poll_seconds=5, exit_time_et=time(10,55), close_fill_seconds=120, max_close_attempts=2, latest_entry_time_et=time(10,5))`.
- Produces: `CompetitionSessionResult(BaseModel)` with `session_date`, `state`, `reason`, `entry_order_status`, `close_order_status`, `close_attempts`.
- Produces: `CompetitionOrchestrator.run(session_date: date) -> CompetitionSessionResult`.
- Consumes: existing `Scheduler.run_session(..., mode="paper")`, `Scheduler.reconcile_session`, `Ledger`, `AlpacaOptionChainGateway`, `ExecutionService`, and paper trading client cancellation/lookup methods.
- Produces: `build_competition_runtime(settings) -> CompetitionRuntimeBundle`.

- [ ] **Step 1: Write failing tests for unresolved prior state and entry polling**

Use fakes with an injected clock/sleeper; do not sleep in tests.

```python
def test_prior_unresolved_coin_episode_blocks_new_session(tmp_path):
    ...
    with pytest.raises(RuntimeError, match="unresolved COIN lifecycle"):
        orchestrator.run(date(2026, 9, 1))


def test_accepted_open_order_is_polled_until_filled_then_monitoring():
    ...
    result = orchestrator.run(date(2026, 8, 31))
    assert result.entry_order_status == "filled"
    assert ledger.get_open_episode(...).state in {EpisodeState.MONITORING, EpisodeState.EXIT_SUBMITTED}
```

- [ ] **Step 2: Run competition tests and verify RED**

```bash
uv run pytest tests/unit/test_competition.py -q
```

Expected: FAIL because no competition orchestrator exists.

- [ ] **Step 3: Implement minimal orchestrator startup and entry reconciliation**

Before a new date is created, inspect `Ledger.get_unresolved_episode("COIN")`. Permit the same-date episode to resume; reject an unresolved prior-date episode.

Call `Scheduler.run_session(session_date, mode="paper")` exactly once for a new session. If it returns `ABSTAINED`, `CLOSED`, or a dry terminal reason, return immediately. If it returns `ORDER_SUBMITTED`, poll only `Scheduler.reconcile_session(session_date)` using the existing deterministic order identity.

- [ ] **Step 4: Write failing bounded-opening cancellation tests**

```python
def test_unfilled_open_order_is_cancelled_after_180_seconds_and_proven_closed():
    ...
    result = orchestrator.run(date(2026, 8, 31))
    assert trading.cancel_count == 1
    assert result.state is EpisodeState.CLOSED
    assert result.reason == "opening_order_unfilled_cancelled"


def test_unproven_open_cancel_never_closes_episode():
    ...
    with pytest.raises(RuntimeError, match="cancellation"):
        orchestrator.run(date(2026, 8, 31))
    assert ledger.get_open_episode(...).state is EpisodeState.ORDER_SUBMITTED
```

- [ ] **Step 5: Verify RED, then implement bounded opening cancellation**

Run:

```bash
uv run pytest tests/unit/test_competition.py -q
```

Expected: FAIL on cancellation behavior.

Implementation rule: after 180 elapsed seconds without `filled`, call `cancel_order` on the proven Alpaca parent ID, then poll/reconcile until broker status is `canceled/cancelled`; only then allow the existing `ORDER_CANCELLED -> CLOSED` transition.

- [ ] **Step 6: Write failing 10:55 deterministic exit tests**

```python
def test_filled_open_waits_until_1055_then_submits_exact_close():
    ...
    result = orchestrator.run(date(2026, 8, 31))
    assert fake_clock.waited_until == datetime(2026, 8, 31, 10, 55, tzinfo=ET)
    assert execution.close_attempts[0].long_symbol == OPEN_LONG
    assert execution.close_attempts[0].short_symbol == OPEN_SHORT
    assert result.state is EpisodeState.CLOSED


def test_restart_from_monitoring_does_not_invoke_signal_or_llm():
    ...
    orchestrator.run(date(2026, 8, 31))
    assert scheduler.run_session_calls == 0
    assert scheduler.reconcile_calls == 0
    assert close_execution_calls == 1
```

- [ ] **Step 7: Run the exit orchestration tests and verify RED**

```bash
uv run pytest tests/unit/test_competition.py -q
```

Expected: FAIL because monitoring/close lifecycle is not implemented.

- [ ] **Step 8: Implement monitoring -> exit submission -> close reconciliation**

For a `MONITORING` episode, obtain the persisted opening order payload, wait using the injected sleeper until 10:55 ET, fetch a fresh chain, build attempt 0 `CloseInstruction`, transition `MONITORING -> EXIT_SUBMITTED`, and call `ExecutionService.submit_close`.

Poll the exact close `client_order_id`. When status is `filled`, transition `EXIT_SUBMITTED -> CLOSED` with event `exit_filled`.

If close attempt 0 remains open after 120 seconds: cancel it, prove cancellation, fetch fresh quotes, build attempt 1 at the fixed one-cent-credit floor, and submit attempt 1. Never submit attempt 1 until attempt 0 cancellation is proven. If attempt 1 does not fill within its fixed 120-second window, cancel/prove status and raise an operational error while leaving the episode non-terminal for explicit recovery.

- [ ] **Step 9: Write failing recovery-from-EXIT_SUBMITTED tests**

```python
def test_restart_from_exit_submitted_reconciles_only_existing_close():
    ...
    result = orchestrator.run(date(2026, 8, 31))
    assert execution.submit_close_count == 0
    assert trading.lookup_count >= 1
    assert result.state is EpisodeState.CLOSED
```

- [ ] **Step 10: Implement recovery path without recomputing signal**

If current episode state is `EXIT_SUBMITTED`, inspect `Ledger.get_latest_order_for_phase(..., "close")` and reconcile that deterministic order. If it is filled, close the episode. If open, continue only the declared poll/cancel/replacement policy using the persisted attempt number. If status is indeterminate, perform lookup only; do not call `Scheduler.run_session` or the LLM path.

- [ ] **Step 11: Add runtime bundle assembly**

`build_competition_runtime(settings)` must construct one shared `Ledger`, account client, chain gateway, paper trading client, `ExecutionService`, and existing full `Scheduler`, then inject them into `CompetitionOrchestrator`. It must reject non-competition role or `CLOCKCROSS_ALLOW_DEV_ORDER=true` before network/order behavior.

- [ ] **Step 12: Run Task 3 tests and commit**

```bash
uv run pytest tests/unit/test_competition.py tests/unit/test_runtime_cli.py -q
git add src/clockcross/competition.py src/clockcross/runtime.py src/clockcross/scheduler.py tests/unit/test_competition.py tests/unit/test_runtime_cli.py
git commit -m "feat: orchestrate autonomous competition sessions"
```

---

### Task 4: Add competition CLI/config timing and exact account safeguards

**Files:**
- Modify: `src/clockcross/config.py`
- Modify: `src/clockcross/runtime_cli.py`
- Modify: `src/clockcross/runtime.py`
- Modify: `src/clockcross/trading/risk.py`
- Modify: `tests/unit/test_config.py`
- Modify: `tests/unit/test_runtime_cli.py`
- Modify: `tests/unit/test_risk.py`

**Interfaces:**
- Produces CLI: `clockcross competition-session --date YYYY-MM-DD`.
- Produces checked-in settings: `competition_open_fill_seconds=180`, `competition_close_fill_seconds=120`, `competition_poll_seconds=5`, `competition_latest_entry_time=time(10,5)`, `competition_exit_time=time(10,55)`, `competition_max_close_attempts=2`.
- Keeps existing `run-once`, `reconcile`, `preflight`, `smoke-mleg`, and `serve` commands unchanged.

- [ ] **Step 1: Write failing parser/dispatch tests**

```python
def test_runtime_cli_registers_competition_session():
    args = parser().parse_args(["competition-session", "--date", "2026-08-31"])
    assert args.command == "competition-session"
    assert args.date == date(2026, 8, 31)


def test_competition_session_builds_competition_runtime_and_closes_it(capsys):
    ...
    assert calls == [("competition", date(2026, 8, 31)), ("close",)]
```

- [ ] **Step 2: Verify RED**

```bash
uv run pytest tests/unit/test_runtime_cli.py -q
```

Expected: FAIL because command is absent.

- [ ] **Step 3: Implement CLI registration/dispatch minimally**

Add `competition-session` parser and an optional `competition_builder` injection to `execute_runtime_command`. Print only `_jsonable(result)`.

- [ ] **Step 4: Write failing timing/risk tests**

```python
def test_competition_risk_window_ends_at_1005_et():
    policy = RiskPolicy(entry_end_et=time(10, 5))
    ...
    assert governor.evaluate(candidate, portfolio, now=at_1006_et).approved is False
    assert "outside_entry_window" in decision.reasons
```

Also test 09:55 accepted and the existing Sep 4 10:20 final cutoff still independently rejects late entries.

- [ ] **Step 5: Verify RED then wire competition-only 10:05 entry end**

In `build_runtime`/competition assembly, development mode retains the existing broader risk window; competition mode constructs `RiskPolicy(entry_end_et=settings.competition_latest_entry_time, final_entry_cutoff=...)`.

- [ ] **Step 6: Add config validation tests and implementation**

Validate:

```python
@model_validator(mode="after")
def validate_competition_policy(self) -> Settings:
    if self.competition_exit_time <= self.decision_time:
        raise ValueError("competition exit must be after decision time")
    if self.competition_latest_entry_time < self.decision_time:
        raise ValueError("competition latest entry must not precede decision time")
    if self.competition_max_close_attempts != 2:
        raise ValueError("competition close attempts are frozen at two")
    return self
```

- [ ] **Step 7: Run Task 4 tests and commit**

```bash
uv run pytest tests/unit/test_config.py tests/unit/test_runtime_cli.py tests/unit/test_risk.py -q
git add src/clockcross/config.py src/clockcross/runtime_cli.py src/clockcross/runtime.py src/clockcross/trading/risk.py tests/unit/test_config.py tests/unit/test_runtime_cli.py tests/unit/test_risk.py
git commit -m "feat: freeze competition runtime timing"
```

---

### Task 5: Make live liquidity rules truthful and enforce only fields actually supplied by Alpaca snapshots

**Files:**
- Modify: `src/clockcross/trading/constructor.py`
- Modify: `tests/unit/test_constructor.py`
- Modify: `README.md`
- Modify: `docs/ONE_PAGE_WRITEUP.md`

**Interfaces:**
- Removes inactive live enforcement claims for `min_open_interest` and `min_volume` unless those fields are present in the chain payload.
- Preserves active controls: quote age <= 60 seconds, positive/non-crossed bid/ask, max relative spread 25%, required delta, 7–21 DTE, deterministic vertical ordering, positive entry debit below width.

- [ ] **Step 1: Write failing truthfulness test**

Add a constructor test proving an otherwise eligible Alpaca-normalized contract with `open_interest=None` and `volume=None` is accepted based only on the actually supplied quote/Greek controls. Add a contract test asserting `ConstructionPolicy` no longer advertises inactive hard minimums as live requirements.

- [ ] **Step 2: Run constructor tests and verify RED**

```bash
uv run pytest tests/unit/test_constructor.py -q
```

Expected: the policy-advertisement assertion fails against current fields/defaults.

- [ ] **Step 3: Remove inactive OI/volume policy knobs from live eligibility**

Delete `min_open_interest` and `min_volume` from `ConstructionPolicy` and the conditional checks. Do not touch quote, DTE, delta, spread, debit, or width gates.

- [ ] **Step 4: Update documentation precisely**

Replace any statement implying live OI/volume enforcement with the actual enforced controls. State that Alpaca's active option feed and quote timestamps are recorded and that no unsupported liquidity metric is claimed.

- [ ] **Step 5: Run constructor/docs contract tests and commit**

```bash
uv run pytest tests/unit/test_constructor.py tests/unit/test_cloudflare_demo_contract.py -q
git add src/clockcross/trading/constructor.py tests/unit/test_constructor.py README.md docs/ONE_PAGE_WRITEUP.md
git commit -m "fix: align live option liquidity claims"
```

---

### Task 6: Add the event-bounded GitHub Actions competition scheduler with state restoration

**Files:**
- Create: `.github/workflows/competition-runtime.yml`
- Create: `tests/unit/test_competition_workflow.py`
- Modify: `.gitignore` only if local restored-state paths need exclusion.
- Modify: `docs/OPERATIONS.md`

**Interfaces:**
- GitHub environment: `competition`.
- Required encrypted secrets: `ALPACA_COMPETITION_API_KEY`, `ALPACA_COMPETITION_SECRET_KEY`, `CLOCKCROSS_AI_GATEWAY_BEARER`.
- Runtime env mapping: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `LLM_API_KEY`, `CLOCKCROSS_ACCOUNT_ROLE=competition`, `CLOCKCROSS_ALLOW_DEV_ORDER=false`.
- Schedule: event dates only, at 09:57 America/New_York; plus `workflow_dispatch`.
- Persistence artifact name: `clockcross-state`, retention 10 days.

- [ ] **Step 1: Write failing workflow contract tests**

The test reads YAML as text (no new YAML dependency) and asserts exact safety strings:

```python
def test_competition_workflow_is_event_bounded_and_secret_backed():
    text = Path(".github/workflows/competition-runtime.yml").read_text()
    assert 'timezone: "America/New_York"' in text
    assert "57 9 31 8 *" in text
    assert "57 9 1-4 9 *" in text
    assert "environment: competition" in text
    assert "CLOCKCROSS_ACCOUNT_ROLE: competition" in text
    assert "CLOCKCROSS_ALLOW_DEV_ORDER: \"false\"" in text
    assert "ALPACA_COMPETITION_API_KEY" in text
    assert "ALPACA_COMPETITION_SECRET_KEY" in text
    assert "CLOCKCROSS_AI_GATEWAY_BEARER" in text
    assert "competition-session" in text
    assert "concurrency:" in text
```

Also assert no literal Alpaca-like secret markers are present.

- [ ] **Step 2: Run workflow test and verify RED**

```bash
uv run pytest tests/unit/test_competition_workflow.py -q
```

Expected: FAIL because workflow file does not exist.

- [ ] **Step 3: Create minimal secure scheduled workflow**

Use:

```yaml
name: Competition Runtime

on:
  schedule:
    - cron: "57 9 31 8 *"
      timezone: "America/New_York"
    - cron: "57 9 1-4 9 *"
      timezone: "America/New_York"
  workflow_dispatch:
    inputs:
      session_date:
        description: "US market session date (YYYY-MM-DD); blank uses New York date"
        required: false
        type: string

permissions:
  contents: read
  actions: read

concurrency:
  group: clockcross-competition
  cancel-in-progress: false

jobs:
  trade:
    runs-on: ubuntu-latest
    timeout-minutes: 90
    environment: competition
    env:
      ALPACA_API_KEY: ${{ secrets.ALPACA_COMPETITION_API_KEY }}
      ALPACA_SECRET_KEY: ${{ secrets.ALPACA_COMPETITION_SECRET_KEY }}
      LLM_API_KEY: ${{ secrets.CLOCKCROSS_AI_GATEWAY_BEARER }}
      CLOCKCROSS_ACCOUNT_ROLE: competition
      CLOCKCROSS_ALLOW_DEV_ORDER: "false"
```

Do not use `pull_request_target`, `set -x`, environment dumps, or write permissions.

- [ ] **Step 4: Add previous-run state restoration**

After checkout/setup and before executing ClockCross, use the built-in `gh` CLI with `GH_TOKEN: ${{ github.token }}` to locate the newest completed prior run of this workflow. If it has artifact `clockcross-state`, download it and restore `clockcross.sqlite3` into `data/`. Absence on the first run is valid.

Use a shell block equivalent to:

```bash
PREV_RUN_ID="$(gh run list --workflow competition-runtime.yml --branch "${GITHUB_REF_NAME}" --limit 20 --json databaseId,status --jq '[.[] | select(.status == "completed")][0].databaseId // empty')"
if [ -n "$PREV_RUN_ID" ]; then
  rm -rf .clockcross-state
  if gh run download "$PREV_RUN_ID" -n clockcross-state -D .clockcross-state; then
    mkdir -p data artifacts/competition
    [ ! -f .clockcross-state/clockcross.sqlite3 ] || cp .clockcross-state/clockcross.sqlite3 data/clockcross.sqlite3
    [ ! -d .clockcross-state/competition ] || cp -R .clockcross-state/competition/. artifacts/competition/
  fi
fi
```

Do not fail the first competition run just because no prior artifact exists.

- [ ] **Step 5: Run preflight then competition session**

Resolve session date with Python's `zoneinfo.ZoneInfo("America/New_York")` if workflow input is blank. Then run:

```bash
uv run clockcross preflight
uv run clockcross competition-session --date "$SESSION_DATE" | tee "artifacts/competition/${SESSION_DATE}.json"
```

The preflight remains read-only. The competition command is the only order-capable step.

- [ ] **Step 6: Upload sanitized durable state on `always()`**

Close the SQLite connection inside the CLI before the step ends, then upload:

```yaml
- name: Persist competition state
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: clockcross-state
    path: |
      data/clockcross.sqlite3
      artifacts/competition
    if-no-files-found: ignore
    retention-days: 10
```

The ledger must never contain API credentials or raw headers; retain the existing repository secret scan.

- [ ] **Step 7: Update operations runbook with exact environment-secret setup and recovery**

Document that scheduled workflows run on the default branch and can be delayed, so 09:57 ET deliberately avoids the top of the hour; ClockCross's own 10:05 competition risk cutoff remains authoritative. Document manual `workflow_dispatch` recovery only before that entry cutoff or for reconciliation/exit recovery.

- [ ] **Step 8: Run workflow/security tests and commit**

```bash
uv run pytest tests/unit/test_competition_workflow.py tests/test_no_secrets.py -q
git add .github/workflows/competition-runtime.yml tests/unit/test_competition_workflow.py docs/OPERATIONS.md .gitignore
git commit -m "ci: schedule competition trading runtime"
```

---

### Task 7: Update evidence/submission surfaces and perform full regression verification

**Files:**
- Modify: `docs/SUBMISSION_CHECKLIST.md`
- Modify: `docs/SUBMISSION_PACKAGE.md`
- Modify: `README.md` if needed for final runtime description.
- Modify: `docs/OPERATIONS.md` if verification reveals corrections.
- Tests: all existing tests.

**Interfaces:**
- Documentation must distinguish verified software behavior from the still-pending Monday open-market destructive smoke.
- No claim that P&L is guaranteed or that a trade will occur; abstention remains valid behavior.

- [ ] **Step 1: Update submission checklist without falsely checking external Monday items**

Mark code/runtime implementation items complete only after tests prove them. Leave these external items unchecked until actually performed:

```text
[ ] Development-account MLeg smoke/cancel completed while U.S. options are open.
[ ] Fresh competition account created at exactly $100,000 and Level 3.
[ ] Competition GitHub environment secrets configured.
[ ] First autonomous competition episode completed.
[ ] Actual Alpaca account P&L/equity captured.
[ ] Video presentation.
[ ] Slide presentation.
[ ] Final LabLab submission completed.
```

- [ ] **Step 2: Run focused lifecycle regression tests**

```bash
uv run pytest \
  tests/unit/test_state.py \
  tests/unit/test_ledger.py \
  tests/unit/test_execution.py \
  tests/unit/test_exit.py \
  tests/unit/test_competition.py \
  tests/unit/test_runtime_cli.py \
  tests/unit/test_risk.py \
  tests/unit/test_constructor.py \
  tests/unit/test_competition_workflow.py -q
```

Expected: all PASS.

- [ ] **Step 3: Run the complete test suite**

```bash
uv run pytest -q
```

Expected: zero failures.

- [ ] **Step 4: Run lint and type checking**

```bash
uv run ruff check .
uv run mypy src/clockcross
```

Expected: both exit 0.

- [ ] **Step 5: Run repository secret scan explicitly**

```bash
uv run pytest tests/test_no_secrets.py -q
```

Expected: PASS with no credential-shaped literals or committed secret files.

- [ ] **Step 6: Inspect git diff for scope creep**

```bash
git status --short
git diff --stat main...HEAD
git diff main...HEAD -- \
  docs/research/2026-08-29-live-signal-policy.json \
  artifacts/research/verdict.json \
  docs/superpowers/specs/2026-08-29-coin-options-mutation.md
```

Expected: the three frozen strategy/research artifacts have no diff.

- [ ] **Step 7: Commit final docs**

```bash
git add README.md docs/OPERATIONS.md docs/SUBMISSION_CHECKLIST.md docs/SUBMISSION_PACKAGE.md
git commit -m "docs: prepare ClockCross for competition sessions"
```

- [ ] **Step 8: Push branch and require GitHub CI green before merge**

Push `feat/competition-runtime-hardening`, inspect the workflow run for the branch commit, and require Install, Ruff, mypy, and pytest all to conclude `success` before merging.

- [ ] **Step 9: Post-merge default-branch verification**

Because GitHub `schedule` only runs workflows present on the default branch, verify after merge that `.github/workflows/competition-runtime.yml` exists on `main`. Do not wait for the scheduled order-capable workflow until the fresh competition secrets are configured.

---

## Plan self-review

### Spec coverage

- Autonomous scheduled invocation: Task 6.
- Bounded opening-order lifecycle: Task 3.
- Deterministic 10:55 research-aligned exit: Tasks 2–4.
- Exact close intents and MLeg order construction: Task 2.
- No blind retry / deterministic reconciliation: Tasks 2–3.
- Durable state/restart behavior: Tasks 1, 3, and 6.
- Unresolved prior lifecycle blocks new entry: Tasks 1 and 3.
- Competition account safeguards and fixed timing: Task 4.
- Truthful live liquidity enforcement: Task 5.
- Final-day existing cutoff preserved: Task 4 plus regression tests.
- Secret isolation and scheduled environment: Task 6.
- Monday runbook and submission checklist: Tasks 6–7.
- Full TDD/CI/secret verification: every task plus Task 7.

### Placeholder scan

No `TBD`, `TODO`, generic “add error handling,” or unspecified test steps remain. Every production behavior is paired with an explicit failing test and verification command.

### Type/interface consistency

- `EpisodeState.EXIT_SUBMITTED` is introduced once in Task 1 and used by Tasks 3–4.
- `CloseInstruction`, `build_close_client_order_id`, and `ExecutionService.submit_close` are introduced in Task 2 before Task 3 consumes them.
- `CompetitionOrchestrator` and `build_competition_runtime` are introduced in Task 3 before the CLI consumes them in Task 4.
- Workflow invokes only the `competition-session` command introduced in Task 4.
- All persisted close orders use payload phase `"close"`; opening orders use phase `"open"`.
