ALTER TABLE timelapse_schedules ADD COLUMN ha_overlay BOOLEAN DEFAULT 0;
ALTER TABLE timelapse_schedules ADD COLUMN ha_overlay_position TEXT DEFAULT 'top-left';
