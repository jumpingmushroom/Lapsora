-- Add codec, output resolution, and quality preset to timelapse_schedules
ALTER TABLE timelapse_schedules ADD COLUMN codec TEXT DEFAULT 'auto';
ALTER TABLE timelapse_schedules ADD COLUMN output_width INTEGER;
ALTER TABLE timelapse_schedules ADD COLUMN output_height INTEGER;
ALTER TABLE timelapse_schedules ADD COLUMN quality_preset TEXT DEFAULT 'medium';
