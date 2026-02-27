-- Profile templates: reusable capture configuration blueprints

CREATE TABLE IF NOT EXISTS profile_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    interval_seconds INTEGER NOT NULL DEFAULT 60,
    resolution_width INTEGER,
    resolution_height INTEGER,
    quality INTEGER NOT NULL DEFAULT 85,
    hdr_enabled BOOLEAN NOT NULL DEFAULT 0,
    is_system BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Track which template a profile was created from
ALTER TABLE profiles ADD COLUMN source_template_id INTEGER REFERENCES profile_templates(id) ON DELETE SET NULL;

-- Seed system templates (INSERT OR IGNORE for idempotency on name+category)
INSERT OR IGNORE INTO profile_templates (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system) VALUES
    ('Slow Clouds (Cumulus)', 'Nature', '10-15s for slow-moving cumulus clouds', 10, 1920, 1080, 90, 0, 1);
INSERT OR IGNORE INTO profile_templates (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system) VALUES
    ('Fast Clouds (Cirrus/Storm)', 'Nature', '1-5s for fast-moving or wispy clouds', 3, 1920, 1080, 90, 0, 1);
INSERT OR IGNORE INTO profile_templates (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system) VALUES
    ('Sunrise & Sunset', 'Nature', '3-5s recommended for golden hour transitions', 5, 1920, 1080, 95, 1, 1);
INSERT OR IGNORE INTO profile_templates (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system) VALUES
    ('Plant Growth', 'Nature', '90-120s for fast growers, 10min for seedlings/blooms', 600, 1280, 720, 85, 0, 1);
INSERT OR IGNORE INTO profile_templates (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system) VALUES
    ('Tide & Waves', 'Nature', '3-5s captures wave motion well', 5, 1920, 1080, 85, 0, 1);
INSERT OR IGNORE INTO profile_templates (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system) VALUES
    ('Storm Tracking', 'Weather', '1-3s for rapidly transforming storm clouds', 3, 1920, 1080, 90, 0, 1);
INSERT OR IGNORE INTO profile_templates (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system) VALUES
    ('Snow Accumulation', 'Weather', '1-2min to show gradual buildup', 120, 1280, 720, 85, 0, 1);
INSERT OR IGNORE INTO profile_templates (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system) VALUES
    ('Vehicle Traffic (Day)', 'Traffic', '1-2s for daytime traffic flow', 2, 1920, 1080, 80, 0, 1);
INSERT OR IGNORE INTO profile_templates (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system) VALUES
    ('Vehicle Traffic (Night)', 'Traffic', '2-3s creates light trail streaks', 3, 1920, 1080, 85, 0, 1);
INSERT OR IGNORE INTO profile_templates (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system) VALUES
    ('Parking Lot', 'Traffic', '30s captures turnover without excess frames', 30, 1280, 720, 75, 0, 1);
INSERT OR IGNORE INTO profile_templates (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system) VALUES
    ('Construction Site', 'Construction', '5-15min standard for long-running projects', 600, 1920, 1080, 90, 0, 1);
INSERT OR IGNORE INTO profile_templates (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system) VALUES
    ('Demolition', 'Construction', '3-5s for fast-paced demolition action', 5, 1920, 1080, 85, 0, 1);
INSERT OR IGNORE INTO profile_templates (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system) VALUES
    ('City Skyline', 'Urban', '5-8s for cityscape day-to-night transitions', 8, 1920, 1080, 90, 1, 1);
INSERT OR IGNORE INTO profile_templates (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system) VALUES
    ('Street Activity', 'Urban', '2-5s for pedestrian & street-level motion', 3, 1920, 1080, 80, 0, 1);
INSERT OR IGNORE INTO profile_templates (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system) VALUES
    ('Star Trails', 'Astro', '15-30s, under 30s avoids motion-blurred stars', 20, 1920, 1080, 95, 1, 1);
INSERT OR IGNORE INTO profile_templates (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system) VALUES
    ('Light & Shadow', 'Creative', '30-60s tracks shifting indoor/outdoor shadows', 60, 1920, 1080, 90, 1, 1);
INSERT OR IGNORE INTO profile_templates (name, category, description, interval_seconds, resolution_width, resolution_height, quality, hdr_enabled, is_system) VALUES
    ('Seasonal Change', 'Creative', '1hr+ for week/month-scale landscape evolution', 3600, 1920, 1080, 90, 0, 1);
