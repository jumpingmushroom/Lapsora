ALTER TABLE timelapse_schedules ADD COLUMN logo_overlay BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE timelapse_schedules ADD COLUMN logo_position TEXT NOT NULL DEFAULT 'bottom-right';
ALTER TABLE timelapse_schedules ADD COLUMN logo_size REAL NOT NULL DEFAULT 0.12;
ALTER TABLE timelapse_schedules ADD COLUMN logo_opacity REAL NOT NULL DEFAULT 0.8;
