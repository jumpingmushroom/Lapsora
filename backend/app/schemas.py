"""Pydantic v2 request/response schemas."""

from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# --- Streams ---


class StreamCreate(BaseModel):
    name: str
    url: str | None = None
    source_type: Literal["rtsp", "go2rtc"] = "rtsp"
    go2rtc_name: str | None = None


class StreamUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    enabled: bool | None = None


class StreamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_type: str
    go2rtc_name: str | None
    enabled: bool
    health_status: str
    consecutive_failures: int
    last_checked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class Go2rtcConfig(BaseModel):
    url: str


class Go2rtcStreamInfo(BaseModel):
    name: str
    producers: list


# --- Profiles ---


class ProfileCreate(BaseModel):
    name: str
    interval_seconds: int = Field(default=60, ge=1)
    resolution_width: int | None = None
    resolution_height: int | None = None
    quality: int = Field(default=85, ge=1, le=100)
    hdr_enabled: bool = False
    capture_mode: Literal["always", "manual", "sun"] = "always"
    active_start_time: str | None = None
    active_end_time: str | None = None
    sun_offset_minutes: int = Field(default=0, ge=0, le=180)
    sun_events: str = ""
    weather_enabled: bool = False


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
    sun_events: str | None = None
    weather_enabled: bool | None = None


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
    sun_events: str
    weather_enabled: bool
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
    weather_temp: float | None = None
    weather_code: int | None = None
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
    thumbnail_path: str | None = None
    period_type: str | None
    period_start: datetime | None
    period_end: datetime | None
    created_at: datetime


class TimelapseGenerate(BaseModel):
    period_start: datetime | None = None
    period_end: datetime | None = None
    fps: int = Field(default=24, ge=1, le=120)
    format: str = "mp4"
    deflicker: str = "medium"
    timestamp_overlay: bool = False
    weather_overlay: bool = False
    weather_position: str = "bottom-right"
    weather_font_size: int = 24
    weather_unit: str = "C"
    heatmap_overlay: bool = False
    heatmap_mode: str = "cumulative"
    heatmap_colormap: str = "jet"
    heatmap_threshold: int = 10
    motion_blur: Literal["off", "low", "medium", "high"] = "off"
    codec: str = "auto"
    output_width: int | None = None
    output_height: int | None = None
    quality_preset: str = "medium"


# --- Timelapse Schedules ---


class TimelapseScheduleCreate(BaseModel):
    profile_id: int
    name: str = ""
    preset: str | None = None
    cron_expression: str | None = None
    fps: int = 24
    format: str = "mp4"
    deflicker: str = "medium"
    lookback_hours: int | None = None
    timestamp_overlay: bool = False
    weather_overlay: bool = False
    weather_position: str = "bottom-right"
    weather_font_size: int = 24
    weather_unit: str = "C"
    heatmap_overlay: bool = False
    heatmap_mode: str = "cumulative"
    heatmap_colormap: str = "jet"
    heatmap_threshold: int = 10
    motion_blur: Literal["off", "low", "medium", "high"] = "off"
    codec: str = "auto"
    output_width: int | None = None
    output_height: int | None = None
    quality_preset: str = "medium"
    enabled: bool = True


class TimelapseScheduleUpdate(BaseModel):
    name: str | None = None
    preset: str | None = None
    cron_expression: str | None = None
    fps: int | None = None
    format: str | None = None
    deflicker: str | None = None
    lookback_hours: int | None = None
    timestamp_overlay: bool | None = None
    weather_overlay: bool | None = None
    weather_position: str | None = None
    weather_font_size: int | None = None
    weather_unit: str | None = None
    heatmap_overlay: bool | None = None
    heatmap_mode: str | None = None
    heatmap_colormap: str | None = None
    heatmap_threshold: int | None = None
    motion_blur: Literal["off", "low", "medium", "high"] | None = None
    codec: str | None = None
    output_width: int | None = None
    output_height: int | None = None
    quality_preset: str | None = None
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
    deflicker: str
    lookback_hours: int | None
    timestamp_overlay: bool
    weather_overlay: bool
    weather_position: str
    weather_font_size: int
    weather_unit: str
    heatmap_overlay: bool
    heatmap_mode: str
    heatmap_colormap: str
    heatmap_threshold: int
    motion_blur: str
    codec: str
    output_width: int | None
    output_height: int | None
    quality_preset: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
    next_run: str | None = None


# --- Cleanup Schedules ---


class CleanupScheduleCreate(BaseModel):
    profile_id: int
    name: str = ""
    capture_retention_days: int = Field(default=32, ge=1)
    timelapse_retention_days: int = Field(default=90, ge=1)
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


class TimeFormatConfig(BaseModel):
    use_24h: bool = False


class HealthConfig(BaseModel):
    check_interval_seconds: int = Field(default=300, ge=30)
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


class CaptureGapUpdate(BaseModel):
    enabled: bool = True


class TimelapseFormatBreakdown(BaseModel):
    format: str
    count: int
    total_size_bytes: int
    total_duration_seconds: float


class TimelapseSummary(BaseModel):
    total_count: int
    total_size_bytes: int
    total_frames: int
    total_duration_seconds: float
    by_format: list[TimelapseFormatBreakdown]
