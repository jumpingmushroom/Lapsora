ALTER TABLE streams ADD COLUMN source_type TEXT NOT NULL DEFAULT 'rtsp';
ALTER TABLE streams ADD COLUMN go2rtc_name TEXT;
