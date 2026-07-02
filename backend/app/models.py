"""SQLAlchemy ORM models."""

from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import decrypt


class Base(DeclarativeBase):
    pass


class Stream(Base):
    __tablename__ = "streams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, default="rtsp", server_default="rtsp")
    go2rtc_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_type: Mapped[str] = mapped_column(Text, default="none", server_default="none")
    auth_username: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_secret: Mapped[str | None] = mapped_column(Text, nullable=True)  # encrypted
    auth_header_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    health_status: Mapped[str] = mapped_column(Text, default="unknown")
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_checked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    profiles: Mapped[list["Profile"]] = relationship(
        back_populates="stream", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def has_auth(self) -> bool:
        """Whether an auth secret is stored for this (HTTP) source."""
        return bool(self.auth_secret)

    @property
    def url_masked(self) -> str | None:
        """Stream URL with the password redacted, for display. None for go2rtc
        streams or if the stored URL cannot be decrypted. Applies to RTSP and
        HTTP snapshot/MJPEG sources (which may embed credentials in the URL)."""
        if self.source_type == "go2rtc":
            return None
        try:
            raw = decrypt(self.url)
        except Exception:
            return None
        if not raw:
            return None
        try:
            parts = urlsplit(raw)
            if parts.password:
                netloc = f"{parts.username or ''}:•••@{parts.hostname or ''}"
                if parts.port:
                    netloc += f":{parts.port}"
                return urlunsplit(
                    (parts.scheme, netloc, parts.path, parts.query, parts.fragment)
                )
        except Exception:
            return raw
        return raw


class ProfileTemplate(Base):
    __tablename__ = "profile_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    resolution_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality: Mapped[int] = mapped_column(Integer, default=85)
    hdr_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    fps_mode: Mapped[str] = mapped_column(Text, default="fixed", server_default="fixed")
    render_target_seconds: Mapped[int] = mapped_column(Integer, default=20, server_default="20")
    render_fps: Mapped[int] = mapped_column(Integer, default=24, server_default="24")
    render_format: Mapped[str] = mapped_column(Text, default="mp4", server_default="mp4")
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    resolution_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality: Mapped[int] = mapped_column(Integer, default=85)
    hdr_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    capture_mode: Mapped[str] = mapped_column(Text, default="always", server_default="always")
    active_start_time: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_end_time: Mapped[str | None] = mapped_column(Text, nullable=True)
    sun_offset_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sun_events: Mapped[str] = mapped_column(Text, default="", server_default="")
    ir_only: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    ir_chroma_threshold: Mapped[float] = mapped_column(
        Float, default=10.0, server_default="10.0"
    )
    fps_mode: Mapped[str] = mapped_column(Text, default="fixed", server_default="fixed")
    render_target_seconds: Mapped[int] = mapped_column(Integer, default=20, server_default="20")
    render_fps: Mapped[int] = mapped_column(Integer, default=24, server_default="24")
    render_format: Mapped[str] = mapped_column(Text, default="mp4", server_default="mp4")
    weather_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ha_sensors: Mapped[str | None] = mapped_column(Text, nullable=True)
    managed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("profile_templates.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    stream: Mapped["Stream"] = relationship(back_populates="profiles")
    source_template: Mapped["ProfileTemplate | None"] = relationship()
    captures: Mapped[list["Capture"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", passive_deletes=True
    )
    timelapses: Mapped[list["Timelapse"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", passive_deletes=True
    )
    timelapse_schedules: Mapped[list["TimelapseSchedule"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", passive_deletes=True
    )
    cleanup_schedules: Mapped[list["CleanupSchedule"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", passive_deletes=True
    )


class TimelapseSchedule(Base):
    __tablename__ = "timelapse_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(Text, default="")
    preset: Mapped[str | None] = mapped_column(Text, nullable=True)
    cron_expression: Mapped[str] = mapped_column(Text, nullable=False)
    fps: Mapped[int] = mapped_column(Integer, default=24)
    format: Mapped[str] = mapped_column(String, default="mp4")
    deflicker: Mapped[str] = mapped_column(Text, default="medium", server_default="medium")
    lookback_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp_overlay: Mapped[bool] = mapped_column(Boolean, default=False)
    weather_overlay: Mapped[bool] = mapped_column(Boolean, default=False)
    weather_position: Mapped[str] = mapped_column(Text, default="bottom-right")
    weather_font_size: Mapped[int] = mapped_column(Integer, default=24)
    weather_unit: Mapped[str] = mapped_column(Text, default="C")
    weather_style: Mapped[str] = mapped_column(Text, default="glass")
    ha_overlay: Mapped[bool] = mapped_column(Boolean, default=False)
    ha_overlay_position: Mapped[str] = mapped_column(Text, default="top-left")
    heatmap_overlay: Mapped[bool] = mapped_column(Boolean, default=False)
    heatmap_mode: Mapped[str] = mapped_column(Text, default="cumulative")
    heatmap_colormap: Mapped[str] = mapped_column(Text, default="jet")
    heatmap_threshold: Mapped[int] = mapped_column(Integer, default=10)
    logo_overlay: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    logo_position: Mapped[str] = mapped_column(Text, default="bottom-right", server_default="bottom-right")
    logo_size: Mapped[float] = mapped_column(Float, default=0.12, server_default="0.12")
    logo_opacity: Mapped[float] = mapped_column(Float, default=0.8, server_default="0.8")
    motion_blur: Mapped[str] = mapped_column(Text, default="off", server_default="off")
    codec: Mapped[str] = mapped_column(Text, default="auto", server_default="auto")
    output_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_preset: Mapped[str] = mapped_column(Text, default="medium", server_default="medium")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    profile: Mapped["Profile"] = relationship(back_populates="timelapse_schedules")


class CleanupSchedule(Base):
    __tablename__ = "cleanup_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(Text, default="")
    capture_retention_days: Mapped[int] = mapped_column(Integer, default=32)
    timelapse_retention_days: Mapped[int] = mapped_column(Integer, default=90)
    cron_expression: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    profile: Mapped["Profile"] = relationship(back_populates="cleanup_schedules")


class Capture(Base):
    __tablename__ = "captures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE")
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_hdr: Mapped[bool] = mapped_column(Boolean, default=False)
    weather_temp: Mapped[float | None] = mapped_column(Float, nullable=True)
    weather_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weather_is_day: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sensor_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    profile: Mapped["Profile"] = relationship(back_populates="captures")


class Timelapse(Base):
    __tablename__ = "timelapses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE")
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    format: Mapped[str] = mapped_column(String, default="mp4")
    fps: Mapped[int] = mapped_column(Integer, default=24)
    frame_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    period_type: Mapped[str | None] = mapped_column(String, nullable=True)
    period_start: Mapped[datetime | None] = mapped_column(nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    profile: Mapped["Profile"] = relationship(back_populates="timelapses")


class PrintJob(Base):
    """One 3D print detected via PrusaLink. An open row (status='printing') is
    the source of truth for an in-flight print and survives app restarts."""

    __tablename__ = "print_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prusalink_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gcode_name: Mapped[str] = mapped_column(Text, default="")
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(Text, default="printing")  # printing|finished|cancelled
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    estimated_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timelapse_id: Mapped[int | None] = mapped_column(
        ForeignKey("timelapses.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    timelapse: Mapped["Timelapse | None"] = relationship()


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class NotificationURL(Base):
    __tablename__ = "notification_urls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(Text, default="info")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
