"""Pydantic v2 request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


# --- Streams ---


class StreamCreate(BaseModel):
    name: str
    url: str


class StreamUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    enabled: bool | None = None


class StreamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


# --- Profiles ---


class ProfileCreate(BaseModel):
    name: str
    interval_seconds: int = 60
    resolution_width: int | None = None
    resolution_height: int | None = None
    quality: int = 85
    hdr_enabled: bool = False


class ProfileUpdate(BaseModel):
    name: str | None = None
    interval_seconds: int | None = None
    resolution_width: int | None = None
    resolution_height: int | None = None
    quality: int | None = None
    hdr_enabled: bool | None = None
    enabled: bool | None = None


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stream_id: int
    name: str
    interval_seconds: int
    resolution_width: int | None
    resolution_height: int | None
    quality: int
    hdr_enabled: bool
    enabled: bool
    created_at: datetime
    updated_at: datetime


# --- Captures ---


class CaptureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    file_size: int | None
    width: int | None
    height: int | None
    is_hdr: bool
    captured_at: datetime


# --- Timelapses ---


class TimelapseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    file_size: int | None
    format: str
    fps: int
    frame_count: int | None
    duration_seconds: float | None
    period_type: str | None
    period_start: datetime | None
    period_end: datetime | None
    created_at: datetime


class TimelapseGenerate(BaseModel):
    period_start: datetime | None = None
    period_end: datetime | None = None
    fps: int = 24
    format: str = "mp4"
    timestamp_overlay: bool = False
