from datetime import datetime, timezone

from clockcross.ledger import Ledger


def test_latest_mark_payload_returns_latest_matching_mark(tmp_path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    episode = ledger.create_episode(datetime(2026, 9, 4).date(), "COIN")
    try:
        ledger.record_mark(
            episode.episode_id,
            marked_at=datetime(2026, 9, 4, 13, 55, tzinfo=timezone.utc),
            value="featherless_shadow",
            payload={"status": "unavailable", "attempt": 1},
        )
        ledger.record_mark(
            episode.episode_id,
            marked_at=datetime(2026, 9, 4, 13, 56, tzinfo=timezone.utc),
            value="other",
            payload={"ignore": True},
        )
        ledger.record_mark(
            episode.episode_id,
            marked_at=datetime(2026, 9, 4, 13, 57, tzinfo=timezone.utc),
            value="featherless_shadow",
            payload={"status": "ok", "attempt": 2},
        )

        assert ledger.get_latest_mark_payload(
            episode.episode_id, "featherless_shadow"
        ) == {"attempt": 2, "status": "ok"}
        assert ledger.get_latest_mark_payload(episode.episode_id, "missing") is None
    finally:
        ledger.close()
