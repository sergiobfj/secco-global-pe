-- Journal remoto aditivo. Não altera os estados/constraints locais da 006.
CREATE TABLE receipt_drive_sync (
 attachment_id TEXT PRIMARY KEY REFERENCES expense_attachments(id) ON DELETE RESTRICT,
 object_key TEXT NOT NULL,
 volume_id TEXT NOT NULL REFERENCES receipt_storage_volumes(id) ON DELETE RESTRICT,
 mission_code TEXT NOT NULL CHECK(mission_code IN ('argentina','portugal')),
 category TEXT NOT NULL CHECK(category IN ('passagens','diarias','inscricoes','deslocamentos','contrapartida','eventos','atividades')),
 official_name TEXT NOT NULL,
 checksum TEXT NOT NULL CHECK(length(checksum)=64),
 drive_id TEXT NOT NULL,
 folder_id TEXT NOT NULL,
 idempotency_key TEXT NOT NULL UNIQUE CHECK(length(idempotency_key)=64),
 remote_id TEXT UNIQUE,
 state TEXT NOT NULL CHECK(state IN ('aguardando','enviando','verificado','erro')),
 error_code TEXT CHECK(error_code IN ('conexao','permissao','credenciais','resposta_invalida','integridade','destino','remoto','local','metadados_alterados')),
 attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts>=0),
 verified_at TEXT,
 updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 CHECK(state!='verificado' OR (remote_id IS NOT NULL AND verified_at IS NOT NULL AND error_code IS NULL))
);
CREATE INDEX ix_drive_sync_state ON receipt_drive_sync(state);
CREATE TABLE receipt_drive_events (
 id INTEGER PRIMARY KEY,
 attachment_id TEXT NOT NULL REFERENCES receipt_drive_sync(attachment_id) ON DELETE RESTRICT,
 state TEXT NOT NULL CHECK(state IN ('aguardando','enviando','verificado','erro')),
 error_code TEXT,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
