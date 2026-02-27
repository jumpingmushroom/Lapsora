-- Configurable per-profile timelapse schedules
CREATE TABLE IF NOT EXISTS timelapse_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT '',
    preset TEXT,
    cron_expression TEXT NOT NULL,
    fps INTEGER NOT NULL DEFAULT 24,
    format TEXT NOT NULL DEFAULT 'mp4',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
