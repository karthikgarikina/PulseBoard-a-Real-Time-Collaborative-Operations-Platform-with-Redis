from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class LoginRequest(BaseModel):
    email: str = Field(..., examples=["ada@pulseboard.local"])
    user_id: str | None = Field(None, examples=["user_123"])
    name: str | None = Field(None, examples=["Ada Lovelace"])
    role: str = Field("member", examples=["member"])


class LoginResponse(BaseModel):
    session_token: str
    user_id: str
    ttl_seconds: int


class ProfileRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    role: str | None = None


class FeedEventRequest(BaseModel):
    type: str = Field(..., examples=["workspace.joined"])
    actor_id: str | None = None
    workspace_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class MessageRequest(BaseModel):
    content: str = Field(..., min_length=1)
    user_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TypingRequest(BaseModel):
    user_id: str | None = None
    is_typing: bool = True


class EventRequest(BaseModel):
    type: str = Field(..., examples=["workspace.member_added"])
    payload: dict[str, Any] = Field(default_factory=dict)


class JobRequest(BaseModel):
    type: str = Field(..., examples=["send_welcome_email"])
    payload: dict[str, Any] = Field(default_factory=dict)


class ScheduledJobRequest(JobRequest):
    run_at: datetime | None = None
    delay_seconds: int | None = Field(None, ge=0)

    @model_validator(mode="after")
    def require_time_target(self) -> "ScheduledJobRequest":
        if self.run_at is None and self.delay_seconds is None:
            raise ValueError("Either run_at or delay_seconds is required.")
        return self


class ReputationRequest(BaseModel):
    delta: float = Field(1.0)


class LockAcquireRequest(BaseModel):
    owner: str | None = None
    ttl_seconds: int | None = Field(None, ge=1)


class LockReleaseRequest(BaseModel):
    owner: str


class AttendanceRequest(BaseModel):
    date: str | None = Field(None, examples=["2026-05-30"])


class LocationRequest(BaseModel):
    longitude: float = Field(..., ge=-180, le=180)
    latitude: float = Field(..., ge=-85.05112878, le=85.05112878)


class WorkspaceInvitationRequest(BaseModel):
    actor_id: str | None = None
    note: str | None = None
