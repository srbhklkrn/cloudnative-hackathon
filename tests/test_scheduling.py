from datetime import timedelta
from unittest.mock import Mock

import pytest
from elasticsearch import ApiError, ConflictError
from pydantic import ValidationError

from backend.data import seed_sessions
from backend.models import Agenda, Preferences, Session
from backend.scheduling import affected, conflict, rank_replacements, unavailable
from backend.store import ConcurrentWrite, ElasticStore, INDICES


def test_seed_is_utc_and_fictional():
    sessions = seed_sessions()
    assert len(sessions) == 30
    assert len({s.id for s in sessions}) == 30
    assert all(s.demo and s.start.utcoffset() == timedelta(0) for s in sessions)
    assert sessions[0].start.isoformat() == "2026-11-09T16:00:00+00:00"


def test_naive_datetimes_and_invalid_interval_rejected():
    data = seed_sessions()[0].model_dump()
    with pytest.raises(ValidationError):
        Session.model_validate({**data, "start": "2026-11-09T09:00:00"})
    with pytest.raises(ValidationError):
        Session.model_validate({**data, "end": data["start"]})


def test_overlap_boundary_and_transfer_time():
    a = seed_sessions()[0]
    b = a.model_copy(update={"id": "second", "start": a.end, "end": a.end + timedelta(minutes=45)})
    assert not conflict(a, b, Preferences())
    assert conflict(a, b.model_copy(update={"start": a.end - timedelta(seconds=1)}), Preferences())
    other_building = b.model_copy(update={"building": "Canyon", "room": "Willow", "start": a.end + timedelta(minutes=8)})
    assert not conflict(a, other_building, Preferences())
    assert conflict(a, other_building, Preferences(accessibility=["step_free"]))


@pytest.mark.parametrize("updates", [{"status": "canceled"}, {"capacity_state": "full"},
    {"accessibility": {"step_free": None}}, {"accessibility_verified_demo": False}])
def test_unavailable_and_unknown_accessibility_excluded(updates):
    s = seed_sessions()[0].model_copy(update=updates)
    assert unavailable(s, Preferences(accessibility=["step_free"]))


def test_stable_ranking_respects_preference_conflict_and_rejections():
    original, a, b, canceled = seed_sessions()[:4]
    canceled = canceled.model_copy(update={"status": "canceled"})
    agenda = Agenda(session_ids=[original.id], saved_revisions={original.id: 1}, preferences=Preferences(topics=["security"]))
    sessions = {s.id: s for s in [original, a, b, canceled]}
    candidates = [(b, 1.0), (a, 1.0), (canceled, 5.0), (original, 10.0)]
    ranked = rank_replacements(original, candidates, agenda, sessions)
    assert [x["session"].id for x in ranked] == [a.id, b.id]
    assert ranked == rank_replacements(original, list(reversed(candidates)), agenda, sessions)
    agenda.rejected[f"{original.id}:1"] = [a.id]
    assert rank_replacements(original, candidates, agenda, sessions)[0]["session"].id == b.id


def test_organizer_move_and_preference_change_are_disruptions():
    s = seed_sessions()[0]
    agenda = Agenda(session_ids=[s.id], saved_revisions={s.id: 1})
    assert not affected(agenda, {s.id: s})
    moved = s.model_copy(update={"revision": 2, "room": "New room"})
    assert affected(agenda, {s.id: moved})
    agenda.preferences = Preferences(accessibility=["quiet_space"])
    assert affected(agenda, {s.id: s})


def test_optimistic_concurrency(store):
    a, version = store.get_agenda("attendee")
    store.save_agenda("attendee", a, version)
    with pytest.raises(ConcurrentWrite):
        store.save_agenda("attendee", a, version)


def test_concurrent_organizer_change_is_rejected(store):
    first, version = store.get_session("session-01")
    stale, stale_version = store.get_session("session-01")
    first.status = "canceled"
    first.revision += 1
    store.record_disruption(first, {"id": "event-one"}, version)
    stale.room = "New room"
    stale.revision += 1
    with pytest.raises(ConcurrentWrite):
        store.record_disruption(stale, {"id": "event-two"}, stale_version)
    assert store.get_session("session-01")[0].status == "canceled"
    assert len(store.events) == 1


def test_elastic_disruption_write_failure_does_not_update_session():
    store = ElasticStore.__new__(ElasticStore)
    store.client = Mock()
    store.client.index.side_effect = RuntimeError("event write failed")

    with pytest.raises(RuntimeError, match="event write failed"):
        store.record_disruption(seed_sessions()[0], {"id": "event-one"}, (1, 1))

    store.client.bulk.assert_not_called()


def test_elastic_disruption_rolls_back_event_when_session_conflicts():
    store = ElasticStore.__new__(ElasticStore)
    store.client = Mock()
    store.client.bulk.side_effect = ConflictError("conflict", None, None)
    event = {"id": "event-one"}

    with pytest.raises(ConcurrentWrite):
        store.record_disruption(seed_sessions()[0], event, (1, 1))

    store.client.index.assert_called_once_with(index=INDICES["disruptions"], id=event["id"],
        document={**event, "demo": True}, op_type="create")
    store.client.options.assert_called_once_with(ignore_status=404)
    store.client.options.return_value.delete.assert_called_once_with(index=INDICES["disruptions"],
        id=event["id"], refresh="wait_for")


@pytest.mark.parametrize("status,error", [(409, ConcurrentWrite), (404, ApiError)])
def test_elastic_disruption_item_error_rolls_back_event(status, error):
    store = ElasticStore.__new__(ElasticStore)
    store.client = Mock()
    store.client.bulk.return_value = Mock(meta=Mock(),
        __getitem__=lambda self, key: {"items": [{"update": {"status": status}}]}[key])

    with pytest.raises(error):
        store.record_disruption(seed_sessions()[0], {"id": "event-one"}, (1, 1))

    store.client.options.return_value.delete.assert_called_once_with(index=INDICES["disruptions"],
        id="event-one", refresh="wait_for")


def test_elastic_disruption_rolls_back_event_on_session_failure_without_masking_it():
    store = ElasticStore.__new__(ElasticStore)
    store.client = Mock()
    store.client.bulk.side_effect = RuntimeError("session update failed")
    store.client.options.return_value.delete.side_effect = RuntimeError("rollback failed")
    event = {"id": "event-one"}

    with pytest.raises(RuntimeError, match="session update failed"):
        store.record_disruption(seed_sessions()[0], event, (1, 1))

    store.client.options.return_value.delete.assert_called_once_with(index=INDICES["disruptions"],
        id=event["id"], refresh="wait_for")


def test_elastic_session_bulk_update_reuses_embeddings_and_keeps_concurrency_guard():
    store = ElasticStore.__new__(ElasticStore)
    store.client = Mock()
    store.client.bulk.return_value = {"items": [{"update": {"status": 200}}]}
    session = seed_sessions()[0]
    store.record_disruption(session, {"id": "event-one"}, (7, 2))
    operations = store.client.bulk.call_args.kwargs["operations"]
    assert operations[0] == {"update": {"_index": INDICES["sessions"], "_id": session.id, "if_seq_no": 7, "if_primary_term": 2}}
    assert operations[1] == {"doc": session.model_dump(mode="json")}
    assert "semantic_text" not in operations[1]["doc"]
