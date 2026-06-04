ALTER TABLE streams ADD COLUMN auth_type TEXT NOT NULL DEFAULT 'none';
ALTER TABLE streams ADD COLUMN auth_username TEXT;
ALTER TABLE streams ADD COLUMN auth_secret TEXT;
ALTER TABLE streams ADD COLUMN auth_header_name TEXT;
