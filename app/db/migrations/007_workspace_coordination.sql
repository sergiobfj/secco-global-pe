-- Puramente aditiva. Nenhum participante, usuário ou vínculo financeiro é alterado.
-- O modelo legado mantém participant_id obrigatório; coordenação não ocupa essa tabela.
CREATE TABLE coordination_accounts (
 id INTEGER PRIMARY KEY,
 account_key TEXT NOT NULL UNIQUE CHECK(account_key='coordenacao_secco'),
 nome TEXT NOT NULL CHECK(length(trim(nome))>0),
 google_sub TEXT UNIQUE CHECK(google_sub IS NULL OR length(google_sub) BETWEEN 1 AND 255),
 email_allowlist TEXT NOT NULL UNIQUE COLLATE NOCASE,
 email_current TEXT NOT NULL DEFAULT '',
 workspace_domain TEXT NOT NULL DEFAULT '',
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 last_login_at TEXT,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE UNIQUE INDEX uq_coord_current_email ON coordination_accounts(email_current COLLATE NOCASE) WHERE email_current!='';
CREATE TABLE coordination_sessions (
 id TEXT PRIMARY KEY NOT NULL,
 user_id INTEGER NOT NULL REFERENCES coordination_accounts(id) ON DELETE RESTRICT,
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
CREATE INDEX ix_coord_sessions_user ON coordination_sessions(user_id,expires_at);
ALTER TABLE auth_events ADD COLUMN coordinator_id INTEGER REFERENCES coordination_accounts(id) ON DELETE RESTRICT;
CREATE TRIGGER auth_event_single_identity BEFORE INSERT ON auth_events
WHEN NEW.user_id IS NOT NULL AND NEW.coordinator_id IS NOT NULL
BEGIN SELECT RAISE(ABORT,'Identidade de auditoria ambigua'); END;
CREATE TRIGGER coord_identity_exclusive_insert BEFORE INSERT ON coordination_accounts
WHEN EXISTS(SELECT 1 FROM app_users u WHERE (NEW.google_sub IS NOT NULL AND u.google_sub=NEW.google_sub)
 OR u.email_allowlist=NEW.email_allowlist COLLATE NOCASE OR (NEW.email_current!='' AND u.email_current=NEW.email_current COLLATE NOCASE))
BEGIN SELECT RAISE(ABORT,'Identidade ja associada'); END;
CREATE TRIGGER coord_identity_exclusive_update BEFORE UPDATE ON coordination_accounts
WHEN EXISTS(SELECT 1 FROM app_users u WHERE (NEW.google_sub IS NOT NULL AND u.google_sub=NEW.google_sub)
 OR u.email_allowlist=NEW.email_allowlist COLLATE NOCASE OR (NEW.email_current!='' AND u.email_current=NEW.email_current COLLATE NOCASE))
BEGIN SELECT RAISE(ABORT,'Identidade ja associada'); END;
CREATE TRIGGER traveler_identity_exclusive_insert BEFORE INSERT ON app_users
WHEN EXISTS(SELECT 1 FROM coordination_accounts c WHERE (NEW.google_sub IS NOT NULL AND c.google_sub=NEW.google_sub)
 OR c.email_allowlist=NEW.email_allowlist COLLATE NOCASE OR (NEW.email_current!='' AND c.email_current=NEW.email_current COLLATE NOCASE))
BEGIN SELECT RAISE(ABORT,'Identidade ja associada'); END;
CREATE TRIGGER traveler_identity_exclusive_update BEFORE UPDATE ON app_users
WHEN EXISTS(SELECT 1 FROM coordination_accounts c WHERE (NEW.google_sub IS NOT NULL AND c.google_sub=NEW.google_sub)
 OR c.email_allowlist=NEW.email_allowlist COLLATE NOCASE OR (NEW.email_current!='' AND c.email_current=NEW.email_current COLLATE NOCASE))
BEGIN SELECT RAISE(ABORT,'Identidade ja associada'); END;
