-- Indexes for time-window statistics queries.
-- statistics.py filters captures/timelapses by timestamp alone (no profile_id),
-- which the existing (profile_id, *) composite indexes can't serve efficiently.
CREATE INDEX IF NOT EXISTS idx_captures_captured_at ON captures (captured_at);
CREATE INDEX IF NOT EXISTS idx_timelapses_created_at ON timelapses (created_at);
