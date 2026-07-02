-- Render config on profiles + templates, and seed 3D-printing templates.

ALTER TABLE profiles ADD COLUMN fps_mode TEXT NOT NULL DEFAULT 'fixed';
ALTER TABLE profiles ADD COLUMN render_target_seconds INTEGER NOT NULL DEFAULT 20;
ALTER TABLE profiles ADD COLUMN render_fps INTEGER NOT NULL DEFAULT 24;
ALTER TABLE profiles ADD COLUMN render_format TEXT NOT NULL DEFAULT 'mp4';

ALTER TABLE profile_templates ADD COLUMN fps_mode TEXT NOT NULL DEFAULT 'fixed';
ALTER TABLE profile_templates ADD COLUMN render_target_seconds INTEGER NOT NULL DEFAULT 20;
ALTER TABLE profile_templates ADD COLUMN render_fps INTEGER NOT NULL DEFAULT 24;
ALTER TABLE profile_templates ADD COLUMN render_format TEXT NOT NULL DEFAULT 'mp4';

INSERT OR IGNORE INTO profile_templates
    (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system, fps_mode, render_target_seconds, render_fps, render_format) VALUES
    ('3D Print - Standard', '3D Printing', 'General-purpose print timelapse, renders to ~20s regardless of print length. Bind the resulting profile to PrusaLink.', 10, NULL, NULL, 90, 0, 1, 'target_duration', 20, 24, 'mp4');
INSERT OR IGNORE INTO profile_templates
    (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system, fps_mode, render_target_seconds, render_fps, render_format) VALUES
    ('3D Print - Long / Overnight', '3D Printing', 'Multi-hour prints: 30s interval keeps frame count and storage down, renders to ~25s.', 30, NULL, NULL, 90, 0, 1, 'target_duration', 25, 24, 'mp4');
INSERT OR IGNORE INTO profile_templates
    (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system, fps_mode, render_target_seconds, render_fps, render_format) VALUES
    ('3D Print - Short / Detail', '3D Printing', 'Small/fast prints: 4s interval so the result is not a blink, renders to ~15s.', 4, NULL, NULL, 90, 0, 1, 'target_duration', 15, 24, 'mp4');
