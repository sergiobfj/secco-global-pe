-- Captura exclusivamente sintética. Sem armazenamento durável ou aprovação financeira.
CREATE TABLE receipt_mission_config (
 mission_id INTEGER PRIMARY KEY REFERENCES missions(id) ON DELETE RESTRICT,
 processo TEXT CHECK(processo IS NULL OR length(trim(processo)) BETWEEN 1 AND 80)
);
CREATE TABLE expenses (
 id INTEGER PRIMARY KEY,
 mission_id INTEGER NOT NULL,
 participant_id INTEGER NOT NULL,
 created_by_user_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
 updated_by_user_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
 tipo TEXT NOT NULL CHECK(tipo IN ('passagem_aerea','diaria','inscricao_evento','aplicativo','taxi','intermunicipal','urbano','seguro_saude','outro')),
 rubrica TEXT NOT NULL DEFAULT '',
 data TEXT CHECK(data IS NULL OR (date(data) IS NOT NULL AND date(data)=data)),
 valor_centavos INTEGER CHECK(valor_centavos IS NULL OR (typeof(valor_centavos)='integer' AND valor_centavos>0 AND valor_centavos<=999999999999)),
 moeda TEXT NOT NULL CHECK(moeda IN ('EUR','ARS','BRL','USD')),
 descricao TEXT NOT NULL DEFAULT '',
 complemento TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(complemento)),
 status TEXT NOT NULL CHECK(status IN ('rascunho','pendente_comprovante','pendente_revisao','pronto_revisao','validado_manualmente')),
 synthetic_only INTEGER NOT NULL DEFAULT 1 CHECK(synthetic_only=1),
 request_key TEXT NOT NULL UNIQUE,
 payload_hash TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1 CHECK(version>0),
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 CHECK(status!='validado_manualmente'),
 UNIQUE(id,mission_id),
 FOREIGN KEY(mission_id,participant_id) REFERENCES mission_participants(mission_id,participant_id) ON DELETE RESTRICT
);
CREATE INDEX ix_expenses_owner_mission ON expenses(created_by_user_id,mission_id,data);
CREATE TABLE expense_checklists (
 expense_id INTEGER PRIMARY KEY REFERENCES expenses(id) ON DELETE RESTRICT,
 revision INTEGER NOT NULL,
 definition TEXT NOT NULL CHECK(json_valid(definition)),
 answers TEXT NOT NULL CHECK(json_valid(answers))
);
CREATE TABLE expense_attachments (
 id TEXT PRIMARY KEY,
 expense_id INTEGER NOT NULL,
 mission_id INTEGER NOT NULL,
 original_name TEXT NOT NULL,
 extension TEXT NOT NULL CHECK(extension IN ('png','jpg','pdf')),
 mime TEXT NOT NULL CHECK(mime IN ('image/png','image/jpeg','application/pdf')),
 size_bytes INTEGER NOT NULL CHECK(size_bytes>0 AND size_bytes<=5242880),
 checksum TEXT NOT NULL CHECK(length(checksum)=64),
 storage_session TEXT NOT NULL,
 storage_status TEXT NOT NULL CHECK(storage_status IN ('recebido_temporario','falha','indisponivel')),
 sync_status TEXT NOT NULL DEFAULT 'pendente' CHECK(sync_status='pendente'),
 official_name TEXT,
 name_status TEXT NOT NULL CHECK(name_status IN ('pendente','preparado')),
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 UNIQUE(expense_id,checksum),
 FOREIGN KEY(expense_id,mission_id) REFERENCES expenses(id,mission_id) ON DELETE RESTRICT
);
CREATE TABLE expense_history (
 id INTEGER PRIMARY KEY,
 expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE RESTRICT,
 actor_user_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
 acao TEXT NOT NULL,
 snapshot TEXT NOT NULL CHECK(json_valid(snapshot)),
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE expense_submissions (
 request_key TEXT PRIMARY KEY,
 expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE RESTRICT,
 actor_user_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE RESTRICT,
 payload_hash TEXT NOT NULL
);
