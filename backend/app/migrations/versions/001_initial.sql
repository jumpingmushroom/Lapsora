-- Initial schema for Lapsora

CREATE TABLE streams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    enabled BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stream_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    interval_seconds INTEGER DEFAULT 60,
    resolution_width INTEGER NULL,
    resolution_height INTEGER NULL,
    quality INTEGER DEFAULT 85,
    hdr_enabled BOOLEAN DEFAULT 0,
    enabled BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (stream_id) REFERENCES streams (id) ON DELETE CASCADE
);

CREATE TABLE captures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER,
    width INTEGER,
    height INTEGER,
    is_hdr BOOLEAN DEFAULT 0,
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (profile_id) REFERENCES profiles (id) ON DELETE CASCADE
);

CREATE TABLE timelapses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER,
    format TEXT DEFAULT 'mp4',
    fps INTEGER DEFAULT 24,
    frame_count INTEGER,
    duration_seconds REAL,
    period_type TEXT CHECK (period_type IN ('daily', 'weekly', 'monthly', 'yearly', 'custom')),
    period_start TIMESTAMP,
    period_end TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (profile_id) REFERENCES profiles (id) ON DELETE CASCADE
);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX idx_streams_enabled ON streams (enabled);
CREATE INDEX idx_profiles_stream_enabled ON profiles (stream_id, enabled);
CREATE INDEX idx_captures_profile_captured ON captures (profile_id, captured_at);
CREATE INDEX idx_timelapses_profile_period ON timelapses (profile_id, period_type);
