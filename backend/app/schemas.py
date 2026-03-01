"""Pydantic v2 request/response schemas."""

from datetime import datetime

from typing import Literal

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
    capture_mode: Literal["always", "manual", "sun"] = "always"
    active_start_time: str | None = None
    active_end_time: str | None = None
    sun_offset_minutes: int = 0


class ProfileUpdate(BaseModel):
    name: str | None = None
    interval_seconds: int | None = None
    resolution_width: int | None = None
    resolution_height: int | None = None
    quality: int | None = None
    hdr_enabled: bool | None = None
    enabled: bool | None = None
    capture_mode: Literal["always", "manual", "sun"] | None = None
    active_start_time: str | None = None
    active_end_time: str | None = None
    sun_offset_minutes: int | None = None


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
    capture_mode: str
    active_start_time: str | None
    active_end_time: str | None
    sun_offset_minutes: int
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


# --- Timelapse Schedules ---


class TimelapseScheduleCreate(BaseModel):
    profile_id: int
    name: str = ""
    preset: str | None = None
    cron_expression: str | None = None
    fps: int = 24
    format: str = "mp4"
    lookback_hours: int | None = None
    enabled: bool = True


class TimelapseScheduleUpdate(BaseModel):
    name: str | None = None
    preset: str | None = None
    cron_expression: str | None = None
    fps: int | None = None
    format: str | None = None
    lookback_hours: int | None = None
    enabled: bool | None = None


class TimelapseScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    name: str
    preset: str | None
    cron_expression: str
    fps: int
    format: str
    lookback_hours: int | None
    enabled: bool
    created_at: datetime
    updated_at: datetime
    next_run: str | None = None


# --- Cleanup Schedules ---


class CleanupScheduleCreate(BaseModel):
    profile_id: int
    name: str = ""
    capture_retention_days: int = 32
    timelapse_retention_days: int = 90
    cron_expression: str
    enabled: bool = True


class CleanupScheduleUpdate(BaseModel):
    name: str | None = None
    capture_retention_days: int | None = None
    timelapse_retention_days: int | None = None
    cron_expression: str | None = None
    enabled: bool | None = None


class CleanupScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    name: str
    capture_retention_days: int
    timelapse_retention_days: int
    cron_expression: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
    next_run: str | None = None


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


class BulkDeleteRequest(BaseModel):
    ids: list[int]


class LocationConfig(BaseModel):
    latitude: float = 0.0
    longitude: float = 0.0


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
    capture_gap: bool = True


# --- Statistics ---


class StatsSummary(BaseModel):
    total_captures: int
    avg_captures_per_day: float
    avg_bytes_per_day: float
    days_until_full: float | None


class StorageTrendPoint(BaseModel):
    date: str
    bytes_added: int
    cumulative_bytes: int


class CaptureActivityPoint(BaseModel):
    profile_id: int
    date: str
    count: int


class ProfileStoragePoint(BaseModel):
    profile_id: int
    date: str
    bytes: int
    count: int
