-- Drop heatmap_opacity column (per-pixel alpha blending replaces global opacity)
ALTER TABLE timelapse_schedules DROP COLUMN heatmap_opacity;
