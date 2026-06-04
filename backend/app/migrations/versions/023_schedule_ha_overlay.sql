ALTER TABLE timelapse_schedules ADD COLUMN ha_overlay BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE timelapse_schedules ADD COLUMN ha_overlay_position TEXT NOT NULL DEFAULT 'top-left';
