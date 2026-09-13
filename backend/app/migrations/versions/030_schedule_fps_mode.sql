-- Render length mode for scheduled renders, matching what profiles and
-- profile templates already carry. "fixed" keeps the stored fps;
-- "target_duration" derives fps from the frame count so the render lands at
-- ~render_target_seconds. Existing schedules keep their current behaviour.
ALTER TABLE timelapse_schedules ADD COLUMN fps_mode TEXT NOT NULL DEFAULT 'fixed';
ALTER TABLE timelapse_schedules ADD COLUMN render_target_seconds INTEGER NOT NULL DEFAULT 20;
