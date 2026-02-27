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
    health_status: str
    consecutive_failures: int
    last_checked_at: datetime | None
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
    auto_disabled: bool
    source_template_id: int | None = None
    created_at: datetime
    updated_at: datetime


# --- Profile Templates ---


class ProfileTemplateCreate(BaseModel):
    name: str
    category: str
    description: str = ""
    interval_seconds: int = 60
    resolution_width: int | None = None
    resolution_height: int | None = None
    quality: int = 85
    hdr_enabled: bool = False


class ProfileTemplateUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    description: str | None = None
    interval_seconds: int | None = None
    resolution_width: int | None = None
    resolution_height: int | None = None
    quality: int | None = None
    hdr_enabled: bool | None = None


class ProfileTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    description: str
    interval_seconds: int
    resolution_width: int | None
    resolution_height: int | None
    quality: int
    hdr_enabled: bool
    is_system: bool
    created_at: datetime
    updated_at: datetime


class ApplyTemplateRequest(BaseModel):
    stream_id: int
    name: str | None = None


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


# --- Notifications ---


class NotificationURLCreate(BaseModel):
    label: str
    url: str


class NotificationURLUpdate(BaseModel):
    label: str | None = None
    enabled: bool | None = None


class NotificationURLRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    enabled: bool
    created_at: datetime


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    title: str
    body: str
    level: str
    read: bool
    created_at: datetime


# --- Settings ---


class HealthConfig(BaseModel):
    check_interval_seconds: int = 300
    failure_threshold: int = 3
    low_disk_threshold_percent: int = 10


class NotificationEventsConfig(BaseModel):
    capture_failure: bool = True
    stream_unhealthy: bool = True
    stream_recovered: bool = True
    timelapse_complete: bool = True
    timelapse_failure: bool = True
    retention_summary: bool = False
    low_disk_space: bool = True
