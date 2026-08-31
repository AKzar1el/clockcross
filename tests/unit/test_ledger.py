from datetime import date

from clockcross.domain import AgentAction, AgentDecision, AgentDriver, EpisodeState, RiskDecision
from clockcross.ledger import Ledger


def test_create_episode_is_idempotent_for_session_and_underlying(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    one = ledger.create_episode(date(2026, 8, 31), "COIN")
    two = ledger.create_episode(date(2026, 8, 31), "COIN")
    assert one.episode_id == two.episode_id
    assert ledger.count_rows("episodes") == 1
    ledger.close()


def test_transition_persists_state_and_history(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    episode = ledger.create_episode(date(2026, 8, 31), "COIN")
    updated = ledger.transition(
        episode.episode_id,
        EpisodeState.FEATURES_FROZEN,
        event="features_frozen",
        payload={"freeze": "09:25"},
    )
    assert updated.state is EpisodeState.FEATURES_FROZEN
    assert ledger.count_rows("transitions") == 1
    ledger.close()


def test_duplicate_client_order_id_returns_existing_order(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    episode = ledger.create_episode(date(2026, 8, 31), "COIN")
    first = ledger.record_order(
        episode.episode_id,
        client_order_id="clockcross-20260831-COIN-abcd",
        alpaca_order_id="alpaca-1",
        status="accepted",
        payload={"status": "accepted"},
    )
    second = ledger.record_order(
        episode.episode_id,
        client_order_id="clockcross-20260831-COIN-abcd",
        alpaca_order_id="alpaca-2",
        status="accepted",
        payload={"status": "accepted"},
    )
    assert first.order_id == second.order_id
    assert second.alpaca_order_id == "alpaca-1"
    assert ledger.count_rows("orders") == 1
    ledger.close()


def test_decision_and_risk_are_one_record_per_episode(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    episode = ledger.create_episode(date(2026, 8, 31), "COIN")
    decision = AgentDecision(
        action=AgentAction.CONTINUATION,
        confidence=0.7,
        driver=AgentDriver.CRYPTO_CROSS_MARKET,
        reason="evidence aligns",
    )
    risk = RiskDecision(approved=True, max_loss="250", aggregate_defined_loss="250")
    ledger.record_decision(episode.episode_id, decision)
    ledger.record_decision(episode.episode_id, decision)
    ledger.record_risk(episode.episode_id, risk)
    ledger.record_risk(episode.episode_id, risk)
    assert ledger.count_rows("agent_decisions") == 1
    assert ledger.count_rows("risk_decisions") == 1
    ledger.close()


def test_reopen_preserves_episode_and_order_identity(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    first = Ledger(path)
    episode = first.create_episode(date(2026, 8, 31), "COIN")
    first.transition(episode.episode_id, EpisodeState.FEATURES_FROZEN, event="freeze")
    order = first.record_order(
        episode.episode_id,
        client_order_id="clockcross-20260831-COIN-abcd",
        alpaca_order_id="alpaca-1",
        status="accepted",
    )
    first.close()

    second = Ledger(path)
    loaded = second.get_episode(episode.episode_id)
    loaded_order = second.get_order_by_client_id(order.client_order_id)
    assert loaded is not None and loaded.state is EpisodeState.FEATURES_FROZEN
    assert loaded_order is not None and loaded_order.alpaca_order_id == "alpaca-1"
    second.close()


def test_get_open_episode_excludes_closed_and_abstained(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    open_ep = ledger.create_episode(date(2026, 8, 31), "COIN")
    found = ledger.get_open_episode(date(2026, 8, 31), "COIN")
    assert found is not None and found.episode_id == open_ep.episode_id
    ledger.transition(open_ep.episode_id, EpisodeState.ABSTAINED, event="no_trade")
    assert ledger.get_open_episode(date(2026, 8, 31), "COIN") is None
    ledger.close()


def test_get_latest_order_for_episode(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    episode = ledger.create_episode(date(2026, 8, 31), "COIN")
    assert ledger.get_latest_order_for_episode(episode.episode_id) is None
    ledger.record_order(
        episode.episode_id,
        client_order_id="clockcross-one",
        alpaca_order_id="alpaca-one",
        status="accepted",
    )
    latest = ledger.get_latest_order_for_episode(episode.episode_id)
    assert latest is not None and latest.client_order_id == "clockcross-one"
    ledger.close()


def test_ledger_finds_unresolved_coin_episode_across_dates(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    old = ledger.create_episode(date(2026, 8, 31), "COIN")
    ledger.transition(old.episode_id, EpisodeState.FEATURES_FROZEN, event="freeze")
    unresolved = ledger.get_unresolved_episode("COIN")
    assert unresolved is not None
    assert unresolved.episode_id == old.episode_id
    ledger.close()


def test_ledger_returns_orders_and_latest_order_for_phase(tmp_path):
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
    orders = ledger.get_orders_for_episode(episode.episode_id)
    assert [order.client_order_id for order in orders] == ["open-1", "close-1"]
    latest_open = ledger.get_latest_order_for_phase(episode.episode_id, "open")
    latest_close = ledger.get_latest_order_for_phase(episode.episode_id, "close")
    assert latest_open is not None and latest_open.client_order_id == "open-1"
    assert latest_close is not None and latest_close.client_order_id == "close-1"
    ledger.close()
