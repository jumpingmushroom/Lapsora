"""SQLAlchemy ORM models."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Stream(Base):
    __tablename__ = "streams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, default="rtsp", server_default="rtsp")
    go2rtc_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    health_status: Mapped[str] = mapped_column(Text, default="unknown")
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_checked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    profiles: Mapped[list["Profile"]] = relationship(
        back_populates="stream", cascade="all, delete-orphan"
    )


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
    weather_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
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
        back_populates="profile", cascade="all, delete-orphan"
    )
    timelapses: Mapped[list["Timelapse"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    timelapse_schedules: Mapped[list["TimelapseSchedule"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    cleanup_schedules: Mapped[list["CleanupSchedule"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
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
    heatmap_overlay: Mapped[bool] = mapped_column(Boolean, default=False)
    heatmap_mode: Mapped[str] = mapped_column(Text, default="cumulative")
    heatmap_colormap: Mapped[str] = mapped_column(Text, default="jet")
    heatmap_threshold: Mapped[int] = mapped_column(Integer, default=10)
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
