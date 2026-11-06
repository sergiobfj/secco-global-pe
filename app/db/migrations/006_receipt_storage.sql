-- Aditiva. A recepção legada da 005 é preservada; persistência tem estado próprio.
CREATE TABLE receipt_storage_volumes (
 id TEXT PRIMARY KEY CHECK(length(id)=48),
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE receipt_local_objects (
 attachment_id TEXT PRIMARY KEY REFERENCES expense_attachments(id) ON DELETE RESTRICT,
 volume_id TEXT NOT NULL REFERENCES receipt_storage_volumes(id) ON DELETE RESTRICT,
 object_key TEXT NOT NULL UNIQUE CHECK(length(object_key)=64),
 local_state TEXT NOT NULL CHECK(local_state IN ('armazenado','erro','exclusao_pendente','excluido')),
 sync_state TEXT NOT NULL DEFAULT 'pendente' CHECK(sync_state='pendente'),
 remote_reference TEXT CHECK(remote_reference IS NULL),
 delete_requested_by INTEGER REFERENCES app_users(id) ON DELETE RESTRICT,
 deleted_at TEXT,
 updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE receipt_storage_events (
 id INTEGER PRIMARY KEY,
 attachment_id TEXT REFERENCES expense_attachments(id) ON DELETE RESTRICT,
 object_key TEXT,
 actor_user_id INTEGER REFERENCES app_users(id) ON DELETE RESTRICT,
 action TEXT NOT NULL,
 source TEXT NOT NULL CHECK(source IN ('usuario','recuperacao')),
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX ix_storage_events_attachment ON receipt_storage_events(attachment_id,id);
CREATE UNIQUE INDEX ix_recovery_event_once ON receipt_storage_events(object_key,action) WHERE source='recuperacao' AND object_key IS NOT NULL;
