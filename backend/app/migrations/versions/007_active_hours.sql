ALTER TABLE profiles ADD COLUMN capture_mode TEXT NOT NULL DEFAULT 'always';
ALTER TABLE profiles ADD COLUMN active_start_time TEXT;
ALTER TABLE profiles ADD COLUMN active_end_time TEXT;
ALTER TABLE profiles ADD COLUMN sun_offset_minutes INTEGER NOT NULL DEFAULT 0;
