-- PrusaLink dynamic per-print capture: print_jobs table, managed profiles,
-- timelapse names. Converts config from profile to stream binding and drops
-- the obsolete seeded 3D-printing templates and legacy state rows.

CREATE TABLE IF NOT EXISTS print_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prusalink_job_id INTEGER,
    gcode_name TEXT NOT NULL DEFAULT '',
    stream_id INTEGER NOT NULL REFERENCES streams(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'printing',
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    estimated_seconds REAL,
    interval_seconds INTEGER,
    timelapse_id INTEGER REFERENCES timelapses(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_print_jobs_status ON print_jobs(status);

ALTER TABLE profiles ADD COLUMN managed_by TEXT;
ALTER TABLE timelapses ADD COLUMN name TEXT;

-- Convert the stored PrusaLink config: profile binding -> that profile's stream.
UPDATE settings SET value = json_set(
    json_remove(value, '$.profile_id', '$.fps', '$.format'),
    '$.stream_id',
    (SELECT p.stream_id FROM profiles p
      WHERE p.id = json_extract(settings.value, '$.profile_id'))
) WHERE key = 'prusalink_config' AND json_valid(value);

-- Obsolete: nothing selects between templates any more.
DELETE FROM profile_templates WHERE is_system = 1 AND category = '3D Printing';

-- Replaced by the open print_jobs row.
DELETE FROM settings WHERE key IN ('prusalink_active', 'prusalink_print_started_at');
