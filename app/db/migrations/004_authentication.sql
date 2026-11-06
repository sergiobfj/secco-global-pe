-- Aditiva. Participantes, subvenção e migrações anteriores permanecem intactos.
CREATE TABLE app_users (
 id INTEGER PRIMARY KEY,
 participant_id INTEGER NOT NULL UNIQUE REFERENCES participants(id) ON DELETE RESTRICT,
 google_sub TEXT UNIQUE CHECK(google_sub IS NULL OR length(google_sub) BETWEEN 1 AND 255),
 email_allowlist TEXT NOT NULL UNIQUE COLLATE NOCASE,
 email_current TEXT NOT NULL DEFAULT '',
 workspace_domain TEXT NOT NULL DEFAULT '',
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 role TEXT NOT NULL DEFAULT 'traveler' CHECK(role IN ('traveler','admin')),
 default_mission_id INTEGER NOT NULL REFERENCES missions(id) ON DELETE RESTRICT,
 last_login_at TEXT,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE UNIQUE INDEX uq_user_current_email ON app_users(email_current COLLATE NOCASE) WHERE email_current!='';
CREATE TABLE user_mission_permissions (
 user_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
 mission_id INTEGER NOT NULL REFERENCES missions(id) ON DELETE RESTRICT,
 can_edit INTEGER NOT NULL DEFAULT 0 CHECK(can_edit IN (0,1)),
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 PRIMARY KEY(user_id,mission_id)
);
CREATE TABLE user_sessions (
 id TEXT PRIMARY KEY NOT NULL,
 user_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
 token_hash TEXT NOT NULL UNIQUE,
 previous_hash TEXT UNIQUE,
 previous_valid_until REAL,
 csrf_secret TEXT NOT NULL,
 config_hash TEXT NOT NULL,
 created_at REAL NOT NULL,
 last_seen_at REAL NOT NULL,
 rotated_at REAL NOT NULL,
 expires_at REAL NOT NULL,
 revoked_at REAL,
 CHECK(expires_at>created_at)
);
CREATE INDEX ix_sessions_user ON user_sessions(user_id,expires_at);
CREATE TABLE oauth_transactions (
 state_hash TEXT PRIMARY KEY NOT NULL,
 browser_hash TEXT NOT NULL,
 nonce_hash TEXT NOT NULL,
 code_verifier TEXT NOT NULL CHECK(length(code_verifier) BETWEEN 43 AND 128),
 expires_at REAL NOT NULL
);
CREATE TABLE auth_events (
 id INTEGER PRIMARY KEY,
 user_id INTEGER REFERENCES app_users(id) ON DELETE RESTRICT,
 event TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
ALTER TABLE itinerary_items ADD COLUMN created_by_user_id INTEGER REFERENCES app_users(id) ON DELETE RESTRICT;
ALTER TABLE itinerary_items ADD COLUMN updated_by_user_id INTEGER REFERENCES app_users(id) ON DELETE RESTRICT;
ALTER TABLE itinerary_history ADD COLUMN actor_user_id INTEGER REFERENCES app_users(id) ON DELETE RESTRICT;
ALTER TABLE diary_entries ADD COLUMN created_by_user_id INTEGER REFERENCES app_users(id) ON DELETE RESTRICT;
ALTER TABLE diary_entries ADD COLUMN updated_by_user_id INTEGER REFERENCES app_users(id) ON DELETE RESTRICT;
ALTER TABLE diary_evidence ADD COLUMN created_by_user_id INTEGER REFERENCES app_users(id) ON DELETE RESTRICT;
ALTER TABLE diary_evidence ADD COLUMN updated_by_user_id INTEGER REFERENCES app_users(id) ON DELETE RESTRICT;
ALTER TABLE diary_goal_claims ADD COLUMN created_by_user_id INTEGER REFERENCES app_users(id) ON DELETE RESTRICT;
ALTER TABLE diary_goal_claims ADD COLUMN updated_by_user_id INTEGER REFERENCES app_users(id) ON DELETE RESTRICT;
ALTER TABLE diary_history ADD COLUMN actor_user_id INTEGER REFERENCES app_users(id) ON DELETE RESTRICT;
