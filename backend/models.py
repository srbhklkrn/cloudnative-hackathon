from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

Accessibility = Literal["step_free", "captions", "hearing_loop", "quiet_space"]
TOPICS = ["kubernetes", "networking", "ebpf", "security", "observability", "ai", "platform", "gitops"]
BUILDINGS = ["Summit", "Canyon"]
CONFERENCE_TZ = ZoneInfo("America/Denver")


class Session(BaseModel):
    id: str
    title: str
    abstract: str
    speaker: str
    topics: list[str]
    level: Literal["beginner", "intermediate", "advanced"]
    start: AwareDatetime
    end: AwareDatetime
    room: str
    building: Literal["Summit", "Canyon"]
    status: Literal["scheduled", "canceled"] = "scheduled"
    capacity_state: Literal["available", "full"] = "available"
    accessibility: dict[str, bool | None]
    accessibility_verified_demo: bool = True
    revision: int = 1
    demo: Literal[True] = True

    @field_validator("start", "end")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def interval(self):
        if self.end <= self.start:
            raise ValueError("Session end must be after start")
        return self

    @property
    def description(self) -> str:
        return f"{self.title}. {self.abstract} Topics: {', '.join(self.topics)}. Level: {self.level}."


class Preferences(BaseModel):
    topics: list[Literal["kubernetes", "networking", "ebpf", "security", "observability", "ai", "platform", "gitops"]] = Field(default_factory=list, max_length=8)
    accessibility: list[Accessibility] = Field(default_factory=list, max_length=4)


class Agenda(BaseModel):
    session_ids: list[str] = Field(default_factory=list)
    saved_revisions: dict[str, int] = Field(default_factory=dict)
    preferences: Preferences = Field(default_factory=Preferences)
    accepted_alternatives: list[dict] = Field(default_factory=list)
    rejected: dict[str, list[str]] = Field(default_factory=dict)
    generation: str = ""


class AgendaChange(BaseModel):
    action: Literal["save", "remove", "preferences", "accept", "reject"]
    session_id: str = Field(default="", max_length=80, pattern=r"^[a-z0-9-]*$")
    replacement_id: str = Field(default="", max_length=80, pattern=r"^[a-z0-9-]*$")
    preferences: Preferences | None = None


class DisruptionChange(BaseModel):
    session_id: str = Field(max_length=80, pattern=r"^[a-z0-9-]+$")
    event_type: Literal["room_full", "cancel", "update", "reopen"]
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    room: str | None = Field(default=None, min_length=1, max_length=60)
    building: Literal["Summit", "Canyon"] | None = None
