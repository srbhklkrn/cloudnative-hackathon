from datetime import timedelta

from opentelemetry import trace

from .models import Agenda, CONFERENCE_TZ, Preferences, Session

tracer = trace.get_tracer("detour")


def travel_minutes(a: Session, b: Session, preferences: Preferences) -> int:
    # Synthetic venue transfer times, never a claim about the real hackathon venue.
    if a.room == b.room and a.building == b.building:
        return 0
    if a.building == b.building:
        return 3
    return 12 if "step_free" in preferences.accessibility else 8


def conflict(a: Session, b: Session, preferences: Preferences) -> bool:
    if a.start < b.end and a.end > b.start:
        return True
    earlier, later = sorted([a, b], key=lambda s: s.start)
    return earlier.end + timedelta(minutes=travel_minutes(a, b, preferences)) > later.start


def conflict_reason(session: Session, saved: list[Session], preferences: Preferences) -> str | None:
    for other in saved:
        if other.id != session.id and conflict(session, other, preferences):
            return f'Overlaps “{other.title}” or leaves insufficient transfer time'
    return None


def unavailable(session: Session, preferences: Preferences) -> str | None:
    if session.status == "canceled":
        return "Session canceled by the demo organizer"
    if session.capacity_state == "full":
        return "Room marked full for this demo session"
    if preferences.accessibility and not session.accessibility_verified_demo:
        return "Accessibility metadata is unverified"
    missing = [x.replace("_", " ") for x in preferences.accessibility if session.accessibility.get(x) is not True]
    return f"Does not meet: {', '.join(missing)}" if missing else None


def affected(agenda: Agenda, sessions: dict[str, Session]) -> list[dict]:
    result = []
    with tracer.start_as_current_span("detour.detect_disruption"):
        saved = [sessions[x] for x in agenda.session_ids if x in sessions]
        for sid in agenda.session_ids:
            s = sessions.get(sid)
            reason = "Session is no longer in the demo program" if s is None else unavailable(s, agenda.preferences)
            if s and not reason and agenda.saved_revisions.get(sid) != s.revision:
                reason = "The organizer changed this session's time, location or availability"
            if s and not reason and any(conflict(s, other, agenda.preferences) for other in saved if other.id != sid):
                reason = "Conflicts with another saved session or its transfer time"
            if reason:
                result.append({"session_id": sid, "session": s, "reason": reason})
    return result


def rank_replacements(original: Session, candidates: list[tuple[Session, float]],
                      agenda: Agenda, sessions: dict[str, Session]) -> list[dict]:
    with tracer.start_as_current_span("detour.rank_recommendations"):
        keep = [sessions[x] for x in agenda.session_ids if x != original.id and x in sessions]
        rejected = agenda.rejected.get(f"{original.id}:{original.revision}", [])
        scored = []
        for s, relevance in candidates:
            if s.id == original.id or s.id in agenda.session_ids or s.id in rejected:
                continue
            if unavailable(s, agenda.preferences) or any(conflict(s, other, agenda.preferences) for other in keep):
                continue
            # A replacement belongs on the original conference day and cannot start before it.
            if s.start < original.start or s.start.astimezone(CONFERENCE_TZ).date() != original.start.astimezone(CONFERENCE_TZ).date():
                continue
            shared = sorted(set(original.topics) & set(s.topics))
            preferred = len(set(agenda.preferences.topics) & set(s.topics))
            distance = abs((s.start - original.start).total_seconds()) / 60
            transfer = travel_minutes(original, s, agenda.preferences)
            explanation = [f"Shares {', '.join(shared)}" if shared else "Retrieved from the original session description",
                           "Fits your agenda, including transfer time",
                           "Same time slot" if s.start == original.start else f"Starts {int(distance)} minutes later",
                           f"{s.building} · {s.room}"]
            if agenda.preferences.accessibility:
                explanation.append("Meets your accessibility filters in the fictional demo metadata")
            scored.append((( -relevance, -preferred, distance, transfer, s.start, s.id),
                           {"session": s, "relevance": round(relevance, 6), "explanation": explanation,
                            "accessibility": "compatible_demo_metadata" if agenda.preferences.accessibility else "no_requirements_specified"}))
        scored.sort(key=lambda x: x[0])
        return [item for _, item in scored[:3]]
