ALTER TABLE profiles ADD COLUMN weather_enabled BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE captures ADD COLUMN weather_temp REAL;
ALTER TABLE captures ADD COLUMN weather_code INTEGER;
