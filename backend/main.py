import logging
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from elasticsearch import ApiError, TransportError
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from opentelemetry import trace
from pydantic import ValidationError

from .models import AgendaChange, CONFERENCE_TZ, DisruptionChange, Preferences, Session, TOPICS
from .scheduling import affected, conflict, rank_replacements, unavailable
from .store import ConcurrentWrite, ElasticStore, MemoryStore

logger = logging.getLogger("detour")
tracer = trace.get_tracer("detour")


def create_app(store=None):
    initialization_lock = threading.Lock()

    def initialize(app):
        try:
            if not getattr(app.state, "store", None):
                mode = os.getenv("DETOUR_STORE", "elasticsearch")
                if mode not in {"memory", "elasticsearch"}:
                    raise ValueError("Unknown datastore mode")
                app.state.store = MemoryStore() if mode == "memory" else ElasticStore()
            if app.state.store.mode == "elasticsearch":
                app.state.store.initialize()
            app.state.ready = True
        except Exception as exc:
            app.state.ready = False
            app.state.retry_after = time.monotonic() + 5
            logger.error("Datastore initialization failed (%s); readiness will retry", type(exc).__name__)

    @asynccontextmanager
    async def lifespan(app):
        app.state.ready, app.state.retry_after = False, 0
        if store is None:
            from starlette.concurrency import run_in_threadpool
            await run_in_threadpool(initialize, app)
        else:
            app.state.store, app.state.ready = store, True
        yield
        if getattr(app.state, "store", None):
            app.state.store.close()

    app = FastAPI(title="Detour", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def boundaries(request, call_next):
        if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
            origin = request.headers.get("origin")
            allowed = {str(request.base_url).rstrip("/"), os.getenv("DETOUR_PUBLIC_ORIGIN", "").rstrip("/")}
            if origin and origin not in allowed:
                return JSONResponse({"detail": "Cross-origin writes are not allowed"}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "Use application/json"}, status_code=415)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        context = trace.get_current_span().get_span_context()
        if context.is_valid:
            response.headers["X-Trace-Id"] = format(context.trace_id, "032x")
        return response

    def database():
        if not getattr(app.state, "ready", False) and time.monotonic() >= getattr(app.state, "retry_after", 0):
            if initialization_lock.acquire(blocking=False):
                try:
                    initialize(app)
                finally:
                    initialization_lock.release()
        if not getattr(app.state, "ready", False):
            raise HTTPException(503, "Elasticsearch is not ready. Check the endpoint, API key and inference model configuration.")
        return app.state.store

    def attendee(request: Request, response: Response):
        token = request.cookies.get("detour_attendee", "")
        if not re.fullmatch(r"[a-f0-9]{32}", token):
            token = uuid4().hex
            secure = request.url.scheme == "https" or os.getenv("DETOUR_PUBLIC_ORIGIN", "").startswith("https://")
            response.set_cookie("detour_attendee", token, httponly=True, samesite="lax", secure=secure, max_age=86400)
        return token

    @app.exception_handler(ConcurrentWrite)
    async def concurrent_error(request, exc):
        return JSONResponse({"detail": "Agenda changed in another request. Refresh and try again."}, status_code=409)

    async def datastore_error(request, exc):
        logger.warning("Datastore operation failed (%s)", type(exc).__name__)
        return JSONResponse({"detail": "Elasticsearch could not complete the request. Try again shortly."}, status_code=503)

    app.add_exception_handler(ApiError, datastore_error)
    app.add_exception_handler(TransportError, datastore_error)

    @app.get("/healthz")
    def health():
        return {"status": "ok", "version": os.getenv("APP_VERSION", "local")}

    @app.get("/readyz")
    def readiness(db=Depends(database)):
        if not db.ready():
            raise HTTPException(503, "Datastore is unavailable")
        return {"status": "ready", "store": db.mode, "version": os.getenv("APP_VERSION", "local")}

    @app.get("/api/meta")
    def metadata():
        db = getattr(app.state, "store", None)
        return {"name": "Detour", "version": os.getenv("APP_VERSION", "local"), "demo": True,
                "store": getattr(db, "mode", "unconfigured"), "ready": getattr(app.state, "ready", False),
                "semantic_search": getattr(db, "mode", None) == "elasticsearch" and getattr(app.state, "ready", False),
                "inference_id": getattr(db, "inference_id", None), "topics": TOPICS,
                "telemetry_configured": bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")),
                "conference_timezone": "America/Denver", "conference_date": "2026-11-09"}

    @app.get("/api/sessions")
    def list_sessions(db=Depends(database)):
        return {"sessions": db.all_sessions(), "disruptions": db.disruptions(), "demo": True}

    @app.get("/api/search")
    def search(q: str = Query(default="", max_length=500),
               mode: str = Query(default="hybrid", pattern="^(hybrid|keyword|semantic)$"),
               topic: str = Query(default="", max_length=40),
               after: datetime | None = None, before: datetime | None = None,
               accessibility: list[str] = Query(default=[]), level: str = Query(default="", pattern="^(|beginner|intermediate|advanced)$"),
               db=Depends(database)):
        if any(t is not None and t.tzinfo is None for t in [after, before]):
            raise HTTPException(422, "Time filters require an explicit UTC offset")
        try:
            preferences = Preferences(accessibility=accessibility)
        except ValidationError:
            raise HTTPException(422, "Unknown accessibility filter")
        if topic and topic not in TOPICS:
            raise HTTPException(422, "Unknown topic")
        with tracer.start_as_current_span("detour.search_sessions"):
            try:
                results = db.search(q, mode)
            except ValueError as exc:
                raise HTTPException(422, str(exc))
            results = [(s, score) for s, score in results if not unavailable(s, preferences)
                       and (not topic or topic in s.topics) and (not after or s.start >= after)
                       and (not before or s.end <= before) and (not level or s.level == level)]
            return {"results": [{"session": s, "score": score} for s, score in results],
                    "mode": mode if db.mode == "elasticsearch" else "keyword-preview", "store": db.mode, "demo": True}

    def agenda_payload(agenda, db):
        sessions = {s.id: s for s in db.all_sessions()}
        return {"agenda": agenda, "sessions": [sessions[x] for x in agenda.session_ids if x in sessions],
                "affected": affected(agenda, sessions), "demo": True}

    @app.get("/api/agenda")
    def get_agenda(token=Depends(attendee), db=Depends(database)):
        agenda, _ = db.get_agenda(token)
        return agenda_payload(agenda, db)

    @app.post("/api/agenda")
    def change_agenda(change: AgendaChange, token=Depends(attendee), db=Depends(database)):
        with db.lock:
            agenda, version = db.get_agenda(token)
            sessions = {s.id: s for s in db.all_sessions()}
            if change.action == "preferences":
                if change.preferences is None:
                    raise HTTPException(422, "Preferences are required")
                agenda.preferences = change.preferences
            elif change.action == "remove":
                agenda.session_ids = [sid for sid in agenda.session_ids if sid != change.session_id]
                agenda.saved_revisions.pop(change.session_id, None)
            elif change.action == "reject":
                original = sessions.get(change.session_id)
                if original is None or change.session_id not in agenda.session_ids or change.replacement_id not in sessions:
                    raise HTTPException(422, "Select a saved session and a valid alternative")
                key = f"{original.id}:{original.revision}"
                agenda.rejected[key] = list(dict.fromkeys(agenda.rejected.get(key, []) + [change.replacement_id]))[:100]
            else:
                sid = change.replacement_id if change.action == "accept" else change.session_id
                session = sessions.get(sid)
                if session is None:
                    raise HTTPException(404, "Session not found")
                if change.action == "accept":
                    if change.session_id not in {x["session_id"] for x in affected(agenda, sessions)}:
                        raise HTTPException(409, "The original session is no longer disrupted; refresh recommendations")
                    if sid == change.session_id or sid in agenda.session_ids:
                        raise HTTPException(409, "Choose a different session that is not already saved")
                reason = unavailable(session, agenda.preferences)
                retained = [sessions[x] for x in agenda.session_ids if x != change.session_id and x in sessions]
                if reason or any(conflict(session, other, agenda.preferences) for other in retained):
                    raise HTTPException(409, reason or "Session overlaps your agenda or leaves insufficient transfer time")
                if change.action == "accept":
                    original = sessions[change.session_id]
                    if session.start < original.start or session.start.astimezone(CONFERENCE_TZ).date() != original.start.astimezone(CONFERENCE_TZ).date():
                        raise HTTPException(409, "Replacement must be on the same conference day and start no earlier")
                    agenda.session_ids.remove(change.session_id)
                    agenda.saved_revisions.pop(change.session_id, None)
                    agenda.accepted_alternatives.append({"original_id": change.session_id, "replacement_id": sid,
                        "timestamp": datetime.now(UTC).isoformat()})
                if sid not in agenda.session_ids:
                    if len(agenda.session_ids) >= 30:
                        raise HTTPException(422, "The demo agenda is limited to 30 sessions")
                    agenda.session_ids.append(sid)
                agenda.saved_revisions[sid] = session.revision
                agenda.session_ids.sort(key=lambda x: (sessions[x].start, x))
            db.save_agenda(token, agenda, version)
            return agenda_payload(agenda, db)

    @app.post("/api/demo/disruptions")
    def disrupt(change: DisruptionChange, db=Depends(database)):
        with db.lock:
            session, version = db.get_session(change.session_id)
            if session is None:
                raise HTTPException(404, "Demo session not found")
            previous = session.model_dump(mode="json")
            updates = {"revision": session.revision + 1}
            if change.event_type == "room_full":
                updates["capacity_state"] = "full"
            elif change.event_type == "cancel":
                updates["status"] = "canceled"
            elif change.event_type == "reopen":
                updates.update(status="scheduled", capacity_state="available")
            else:
                values = change.model_dump(exclude_none=True, exclude={"session_id", "event_type"})
                if not values:
                    raise HTTPException(422, "Provide a new time or location")
                updates.update(values)
                if "building" in updates or "room" in updates:
                    # A new room's accessibility cannot inherit verification from the old room.
                    updates["accessibility_verified_demo"] = False
            try:
                session = Session.model_validate({**session.model_dump(), **updates})
            except ValidationError:
                raise HTTPException(422, "Invalid time interval or location")
            event = {"id": uuid4().hex, "session_id": session.id, "event_type": change.event_type,
                     "timestamp": datetime.now(UTC).isoformat(), "previous": previous, "current": session.model_dump(mode="json")}
            db.record_disruption(session, event, version)
            return {"session": session, "disruption": event, "demo": True}

    @app.post("/api/replan")
    def replan(token=Depends(attendee), db=Depends(database)):
        with tracer.start_as_current_span("detour.replan_agenda"):
            agenda, _ = db.get_agenda(token)
            sessions = {s.id: s for s in db.all_sessions()}
            disruptions = affected(agenda, sessions)
            # Replan one disruption at a time; accepting rechecks the current complete agenda.
            item = disruptions[0] if disruptions else None
            recommendations = []
            if item and item["session"]:
                original = item["session"]
                candidates = db.search(original.description, "hybrid")
                recommendations = rank_replacements(original, candidates, agenda, sessions)
            return {"disruption": item, "remaining_disruptions": len(disruptions), "recommendations": recommendations,
                    "message": "No compatible alternative is available. Try adjusting your preferences or removing a conflicting session." if item and not recommendations else None,
                    "mode": "hybrid" if db.mode == "elasticsearch" else "keyword-preview", "demo": True}

    @app.post("/api/demo/reset")
    def reset(db=Depends(database)):
        with db.lock:
            db.reset()
        return {"status": "reset", "demo": True}

    dist = Path(os.getenv("DETOUR_FRONTEND_DIR", "frontend/dist"))
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


app = create_app()
