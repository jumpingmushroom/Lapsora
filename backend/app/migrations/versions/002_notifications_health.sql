-- Notification URLs (Apprise targets)
CREATE TABLE notification_urls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    url TEXT NOT NULL,
    enabled BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Notification history (in-app panel)
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    level TEXT DEFAULT 'info',
    read BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_notifications_read ON notifications (read, created_at);

-- Stream health columns
ALTER TABLE streams ADD COLUMN health_status TEXT DEFAULT 'unknown';
ALTER TABLE streams ADD COLUMN consecutive_failures INTEGER DEFAULT 0;
ALTER TABLE streams ADD COLUMN last_checked_at TIMESTAMP NULL;

-- Track auto-disabled profiles
ALTER TABLE profiles ADD COLUMN auto_disabled BOOLEAN DEFAULT 0;
