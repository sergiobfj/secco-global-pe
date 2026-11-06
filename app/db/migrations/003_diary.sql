-- Aditiva. Não altera nem remove registros ou migrações anteriores.
ALTER TABLE itinerary_items ADD COLUMN organizacao TEXT NOT NULL DEFAULT '' CHECK(length(organizacao)<=200);

CREATE TABLE diary_entries (
 id INTEGER PRIMARY KEY,
 mission_id INTEGER NOT NULL REFERENCES missions(id) ON DELETE RESTRICT,
 itinerary_item_id INTEGER UNIQUE,
 tipo TEXT NOT NULL CHECK(tipo IN ('reuniao_empresarial','visita_institucional','participacao_evento','networking_profissional','apresentacao_geocarbo','outra_profissional')),
 titulo TEXT NOT NULL DEFAULT '' CHECK(length(titulo)<=160),
 data TEXT CHECK(data IS NULL OR (date(data) IS NOT NULL AND data=date(data))),
 horario TEXT CHECK(horario IS NULL OR (length(horario)=5 AND time(horario) IS NOT NULL)),
 organizacao TEXT NOT NULL DEFAULT '' CHECK(length(organizacao)<=200),
 local TEXT NOT NULL DEFAULT '' CHECK(length(local)<=400),
 objetivo TEXT NOT NULL DEFAULT '' CHECK(length(objetivo)<=4000),
 descricao TEXT NOT NULL DEFAULT '' CHECK(length(descricao)<=8000),
 resultados TEXT NOT NULL DEFAULT '' CHECK(length(resultados)<=8000),
 proximos_passos TEXT NOT NULL DEFAULT '' CHECK(length(proximos_passos)<=4000),
 status TEXT NOT NULL DEFAULT 'rascunho' CHECK(status IN ('rascunho','realizada','cancelada')),
 version INTEGER NOT NULL DEFAULT 1,
 request_key TEXT UNIQUE,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 UNIQUE(id,mission_id),
 FOREIGN KEY(itinerary_item_id,mission_id) REFERENCES itinerary_items(id,mission_id) ON DELETE RESTRICT,
 CHECK(horario IS NULL OR data IS NOT NULL),
 CHECK(status!='realizada' OR (length(trim(titulo))>0 AND data IS NOT NULL AND length(trim(descricao))>0 AND length(trim(resultados))>0))
);
CREATE INDEX ix_diary_mission_date ON diary_entries(mission_id,data,status);
CREATE TABLE diary_participants (
 entry_id INTEGER NOT NULL,
 mission_id INTEGER NOT NULL,
 participant_id INTEGER NOT NULL,
 PRIMARY KEY(entry_id,participant_id),
 FOREIGN KEY(entry_id,mission_id) REFERENCES diary_entries(id,mission_id) ON DELETE RESTRICT,
 FOREIGN KEY(mission_id,participant_id) REFERENCES mission_participants(mission_id,participant_id) ON DELETE RESTRICT
);
CREATE TABLE diary_evidence (
 id INTEGER PRIMARY KEY,
 entry_id INTEGER NOT NULL,
 mission_id INTEGER NOT NULL,
 tipo TEXT NOT NULL CHECK(tipo IN ('fotografia','certificado','lista_presenca','documento','carta_intencao','confirmacao_institucional')),
 titulo TEXT NOT NULL CHECK(length(trim(titulo)) BETWEEN 1 AND 200),
 referencia_url TEXT NOT NULL DEFAULT '' CHECK(length(referencia_url)<=2000),
 referencia_chave TEXT NOT NULL DEFAULT '' CHECK(length(referencia_chave)<=400),
 status TEXT NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente','referencia_conferida','invalidada')),
 conferido_por TEXT NOT NULL DEFAULT '' CHECK(length(conferido_por)<=160),
 nota_conferencia TEXT NOT NULL DEFAULT '' CHECK(length(nota_conferencia)<=4000),
 conferido_em TEXT,
 version INTEGER NOT NULL DEFAULT 1,
 request_key TEXT UNIQUE,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 UNIQUE(id,entry_id,mission_id),
 FOREIGN KEY(entry_id,mission_id) REFERENCES diary_entries(id,mission_id) ON DELETE RESTRICT,
 CHECK(status!='referencia_conferida' OR (length(trim(referencia_url))>0 AND length(trim(referencia_chave))>0 AND length(trim(conferido_por))>0 AND length(trim(nota_conferencia))>0 AND conferido_em IS NOT NULL))
);
CREATE UNIQUE INDEX uq_evidence_reference ON diary_evidence(mission_id,referencia_chave) WHERE referencia_chave!='';
CREATE UNIQUE INDEX uq_evidence_url ON diary_evidence(mission_id,referencia_url) WHERE referencia_url!='';

CREATE TABLE diary_goal_claims (
 id INTEGER PRIMARY KEY,
 entry_id INTEGER NOT NULL,
 mission_id INTEGER NOT NULL,
 tipo_meta TEXT NOT NULL,
 justificativa TEXT NOT NULL DEFAULT '' CHECK(length(justificativa)<=4000),
 criterio_referencia TEXT NOT NULL DEFAULT '' CHECK(length(criterio_referencia)<=4000),
 evidence_id INTEGER,
 evidence_version INTEGER,
 entry_version INTEGER NOT NULL DEFAULT 1,
 validacao_status TEXT NOT NULL DEFAULT 'pendente' CHECK(validacao_status IN ('pendente','aprovada','rejeitada')),
 validado_por TEXT NOT NULL DEFAULT '' CHECK(length(validado_por)<=160),
 validado_em TEXT,
 version INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 UNIQUE(entry_id,tipo_meta),
 FOREIGN KEY(entry_id,mission_id) REFERENCES diary_entries(id,mission_id) ON DELETE RESTRICT,
 FOREIGN KEY(mission_id,tipo_meta) REFERENCES mission_goals(mission_id,tipo_meta) ON DELETE RESTRICT,
 FOREIGN KEY(evidence_id,entry_id,mission_id) REFERENCES diary_evidence(id,entry_id,mission_id) ON DELETE RESTRICT,
 CHECK(validacao_status!='aprovada' OR (length(trim(justificativa))>0 AND length(trim(criterio_referencia))>0 AND evidence_id IS NOT NULL AND length(trim(validado_por))>0 AND validado_em IS NOT NULL))
);
CREATE UNIQUE INDEX uq_formal_evidence_once ON diary_goal_claims(mission_id,tipo_meta,evidence_id)
 WHERE tipo_meta IN ('loi','manifestacao_interesse') AND evidence_id IS NOT NULL;

CREATE TABLE diary_history (
 id INTEGER PRIMARY KEY,
 entry_id INTEGER NOT NULL REFERENCES diary_entries(id) ON DELETE RESTRICT,
 entidade TEXT NOT NULL CHECK(entidade IN ('registro','evidencia','classificacao')),
 entidade_id INTEGER NOT NULL,
 acao TEXT NOT NULL,
 snapshot TEXT NOT NULL CHECK(json_valid(snapshot)),
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE VIEW eligible_goal_claims AS
 SELECT c.id,c.entry_id,c.mission_id,c.tipo_meta
 FROM diary_goal_claims c
 JOIN diary_entries d ON d.id=c.entry_id AND d.mission_id=c.mission_id
 JOIN diary_evidence e ON e.id=c.evidence_id AND e.entry_id=d.id AND e.mission_id=d.mission_id
 WHERE d.status='realizada' AND c.validacao_status='aprovada' AND c.entry_version=d.version
 AND length(trim(c.justificativa))>0 AND length(trim(c.criterio_referencia))>0
 AND length(trim(c.validado_por))>0 AND c.validado_em IS NOT NULL
 AND c.evidence_version=e.version
 AND e.status='referencia_conferida' AND length(trim(e.referencia_url))>0
 AND length(trim(e.referencia_chave))>0 AND length(trim(e.conferido_por))>0
 AND length(trim(e.nota_conferencia))>0 AND e.conferido_em IS NOT NULL
 AND (
   (c.tipo_meta='reuniao_qualificada' AND d.tipo='reuniao_empresarial')
   OR (c.tipo_meta='loi' AND e.tipo='carta_intencao')
   OR (c.tipo_meta='manifestacao_interesse' AND e.tipo IN ('documento','carta_intencao','confirmacao_institucional'))
 );
