import os
import re
import threading
from copy import deepcopy
from uuid import uuid4

from elasticsearch import ConflictError, Elasticsearch, NotFoundError, helpers
from opentelemetry import trace

from .data import seed_sessions
from .models import Agenda, Session

tracer = trace.get_tracer("detour")
# Fixed names ensure a public demo reset can never target another application's data.
INDICES = {name: f"detour-demo-{name}-v1" for name in ("sessions", "agendas", "disruptions")}


class ConcurrentWrite(Exception):
    pass


class MemoryStore:
    """Explicit test/local preview mode. No persistence or semantic inference."""
    mode = "memory"
    inference_id = None

    def __init__(self):
        self.lock = threading.RLock()
        self.initialize()

    def initialize(self):
        self.reset()

    def ready(self):
        return True

    def close(self):
        pass

    def reset(self):
        self.generation = uuid4().hex
        self.sessions = {s.id: s for s in seed_sessions()}
        self.agendas = {}
        self.events = []

    def all_sessions(self):
        return [s.model_copy(deep=True) for s in self.sessions.values()]

    def search(self, query: str, mode: str = "hybrid") -> list[tuple[Session, float]]:
        if mode == "semantic":
            raise ValueError("Semantic search requires Elasticsearch; local preview is keyword only")
        terms = set(re.findall(r"[a-z0-9]+", query.lower())) - {"a", "the", "and", "or", "about", "for", "with", "how", "do", "i", "something"}
        scored = [(s.model_copy(deep=True), float(sum(t in s.description.lower() for t in terms))) for s in self.sessions.values()]
        return sorted([x for x in scored if not terms or x[1] > 0], key=lambda x: (-x[1], x[0].start, x[0].id))

    def get_agenda(self, token: str):
        item = self.agendas.get(token)
        return (Agenda(generation=self.generation), None) if item is None else (item[0].model_copy(deep=True), item[1])

    def save_agenda(self, token: str, agenda: Agenda, version):
        current = self.agendas.get(token)
        if (current[1] if current else None) != version:
            raise ConcurrentWrite
        self.agendas[token] = (agenda.model_copy(deep=True), (version or 0) + 1)

    def record_disruption(self, session: Session, event: dict):
        self.events.append(deepcopy(event))
        self.sessions[session.id] = session.model_copy(deep=True)

    def disruptions(self):
        return deepcopy(self.events[-100:][::-1])


class ElasticStore:
    mode = "elasticsearch"

    def __init__(self):
        endpoint, api_key = os.getenv("ELASTICSEARCH_URL"), os.getenv("ELASTICSEARCH_API_KEY")
        if not endpoint or not api_key:
            raise ValueError("Set ELASTICSEARCH_URL and ELASTICSEARCH_API_KEY in the local environment or Kubernetes Secret")
        self.client = Elasticsearch(endpoint, api_key=api_key, request_timeout=20, max_retries=1, retry_on_timeout=True)
        self.inference_id = os.getenv("ELASTICSEARCH_INFERENCE_ID", ".jina-embeddings-v5-text-small")
        self.lock = threading.RLock()

    def initialize(self):
        self.client.inference.get(inference_id=self.inference_id)
        properties = {
            "id": {"type": "keyword"}, "title": {"type": "text"}, "abstract": {"type": "text"},
            "speaker": {"type": "keyword"}, "topics": {"type": "keyword"}, "level": {"type": "keyword"},
            "start": {"type": "date"}, "end": {"type": "date"}, "room": {"type": "keyword"},
            "building": {"type": "keyword"}, "status": {"type": "keyword"}, "capacity_state": {"type": "keyword"},
            "accessibility": {"properties": {x: {"type": "boolean"} for x in ("step_free", "captions", "hearing_loop", "quiet_space")}},
            "accessibility_verified_demo": {"type": "boolean"}, "revision": {"type": "integer"},
            "demo": {"type": "boolean"},
            "semantic_text": {"type": "semantic_text", "inference_id": self.inference_id},
        }
        for name, index in INDICES.items():
            if not self.client.indices.exists(index=index):
                try:
                    mapping = {"dynamic": "strict", "properties": properties} if name == "sessions" else {
                        "dynamic": False, "properties": {"demo": {"type": "boolean"}, "timestamp": {"type": "date"}, "event_type": {"type": "keyword"}}}
                    self.client.indices.create(index=index, mappings=mapping)
                except Exception:
                    if not self.client.indices.exists(index=index):
                        raise
        try:
            self.client.get(index=INDICES["disruptions"], id="state")
        except NotFoundError:
            self._seed()

    def _seed(self):
        self.client.options(request_timeout=90).inference.get(inference_id=self.inference_id)
        documents = [{"_index": INDICES["sessions"], "_id": s.id,
                      "_source": {**s.model_dump(mode="json"), "semantic_text": s.description}} for s in seed_sessions()]
        helpers.bulk(self.client.options(request_timeout=90), documents, refresh="wait_for")
        self.client.index(index=INDICES["disruptions"], id="state",
                          document={"generation": uuid4().hex, "demo": True, "event_type": "state"}, refresh="wait_for")

    @property
    def generation(self):
        return self.client.get(index=INDICES["disruptions"], id="state")["_source"]["generation"]

    def ready(self):
        self.client.get(index=INDICES["disruptions"], id="state")
        return all(self.client.indices.exists(index=index) for index in INDICES.values())

    def close(self):
        self.client.close()

    def reset(self):
        for index in INDICES.values():
            self.client.delete_by_query(index=index, query={"term": {"demo": True}}, refresh=True, conflicts="abort")
        self._seed()

    def all_sessions(self):
        result = self.client.search(index=INDICES["sessions"], query={"term": {"demo": True}}, size=100, sort=[{"start": "asc"}, {"id": "asc"}], source_excludes=["semantic_text"])
        return [Session.model_validate(h["_source"]) for h in result["hits"]["hits"]]

    def search(self, query: str, mode: str = "hybrid") -> list[tuple[Session, float]]:
        with tracer.start_as_current_span("detour.semantic_search" if mode != "keyword" else "detour.keyword_search"):
            if not query.strip():
                return [(s, 0.0) for s in self.all_sessions()]
            queries = []
            if mode in ("hybrid", "keyword"):
                queries.append({"multi_match": {"query": query, "fields": ["title^3", "abstract", "topics^2"], "type": "best_fields"}})
            if mode in ("hybrid", "semantic"):
                queries.append({"match": {"semantic_text": {"query": query}}})
            scores, sessions = {}, {}
            for q in queries:
                result = self.client.search(index=INDICES["sessions"],
                    query={"bool": {"must": [q], "filter": [{"term": {"demo": True}}]}},
                    size=100, sort=["_score", {"start": "asc"}, {"id": "asc"}], source_excludes=["semantic_text"])
                if result.get("timed_out") or result.get("_shards", {}).get("failed", 0):
                    raise RuntimeError("Search returned partial results")
                for rank, hit in enumerate(result["hits"]["hits"], 1):
                    sid = hit["_id"]
                    scores[sid] = scores.get(sid, 0) + 1 / (60 + rank)
                    sessions[sid] = Session.model_validate(hit["_source"])
            return sorted([(sessions[sid], score) for sid, score in scores.items()], key=lambda x: (-x[1], x[0].start, x[0].id))

    def get_agenda(self, token: str):
        try:
            result = self.client.get(index=INDICES["agendas"], id=token)
        except NotFoundError:
            return Agenda(generation=self.generation), None
        agenda = Agenda.model_validate(result["_source"])
        version = (result["_seq_no"], result["_primary_term"])
        if agenda.generation != self.generation:
            agenda = Agenda(generation=self.generation)
        return agenda, version

    def save_agenda(self, token: str, agenda: Agenda, version):
        options = {"op_type": "create"} if version is None else {"if_seq_no": version[0], "if_primary_term": version[1]}
        try:
            self.client.index(index=INDICES["agendas"], id=token,
                document={**agenda.model_dump(mode="json"), "demo": True}, refresh="wait_for", **options)
        except ConflictError as exc:
            raise ConcurrentWrite from exc

    def record_disruption(self, session: Session, event: dict):
        # Persist the event before changing the searchable session; expose failures to the caller.
        self.client.index(index=INDICES["disruptions"], id=event["id"], document={**event, "demo": True}, refresh="wait_for")
        self.client.update(index=INDICES["sessions"], id=session.id, doc=session.model_dump(mode="json"), refresh="wait_for")

    def disruptions(self):
        result = self.client.search(index=INDICES["disruptions"], query={"bool": {"filter": [{"term": {"demo": True}}],
            "must_not": [{"term": {"event_type": "state"}}]}}, size=100, sort=[{"timestamp": "desc"}])
        return [h["_source"] for h in result["hits"]["hits"]]
