CREATE TABLE missions (
    id INTEGER PRIMARY KEY,
    codigo TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    pais TEXT NOT NULL,
    data_inicio TEXT NOT NULL CHECK(date(data_inicio) IS NOT NULL AND data_inicio = date(data_inicio)),
    data_fim TEXT NOT NULL CHECK(date(data_fim) IS NOT NULL AND data_fim = date(data_fim) AND data_fim >= data_inicio),
    timezone TEXT NOT NULL,
    edital TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planejada' CHECK(status IN ('planejada','cancelada')),
    cidades TEXT NOT NULL CHECK(json_valid(cidades)),
    atividades_previstas TEXT NOT NULL CHECK(json_valid(atividades_previstas)),
    observacoes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TRIGGER missions_updated_at AFTER UPDATE ON missions
BEGIN
    UPDATE missions SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = NEW.id;
END;
CREATE TABLE participants (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL UNIQUE CHECK(length(trim(nome)) > 0),
    email TEXT UNIQUE,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE mission_participants (
    id INTEGER PRIMARY KEY,
    mission_id INTEGER NOT NULL REFERENCES missions(id) ON DELETE RESTRICT,
    participant_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE RESTRICT,
    papel TEXT NOT NULL,
    financiado_pela_subvencao INTEGER NOT NULL CHECK(financiado_pela_subvencao IN (0,1)),
    UNIQUE(mission_id, participant_id)
);
CREATE INDEX ix_mp_participant ON mission_participants(participant_id);
CREATE UNIQUE INDEX ix_one_funded_participant ON mission_participants(mission_id)
    WHERE financiado_pela_subvencao = 1;
CREATE TABLE mission_goals (
    id INTEGER PRIMARY KEY,
    mission_id INTEGER NOT NULL REFERENCES missions(id) ON DELETE RESTRICT,
    tipo_meta TEXT NOT NULL CHECK(tipo_meta IN ('reuniao_qualificada','loi','manifestacao_interesse')),
    quantidade_alvo INTEGER NOT NULL CHECK(quantidade_alvo > 0),
    UNIQUE(mission_id, tipo_meta)
);
-- Estruturas de leitura dos dashboards. Nenhum registro fictício é inserido.
CREATE TABLE mission_events (
    id INTEGER PRIMARY KEY,
    mission_id INTEGER NOT NULL REFERENCES missions(id) ON DELETE RESTRICT,
    titulo TEXT NOT NULL CHECK(length(trim(titulo)) > 0),
    inicio_utc TEXT NOT NULL CHECK(datetime(inicio_utc) IS NOT NULL),
    fim_utc TEXT CHECK(fim_utc IS NULL OR (datetime(fim_utc) IS NOT NULL AND fim_utc >= inicio_utc)),
    local TEXT
);
CREATE INDEX ix_events_mission_start ON mission_events(mission_id, inicio_utc);
CREATE TABLE mission_results (
    id INTEGER PRIMARY KEY,
    mission_id INTEGER NOT NULL,
    tipo_meta TEXT NOT NULL,
    descricao TEXT NOT NULL CHECK(length(trim(descricao)) > 0),
    ocorrido_em TEXT NOT NULL CHECK(date(ocorrido_em) IS NOT NULL),
    FOREIGN KEY(mission_id, tipo_meta) REFERENCES mission_goals(mission_id, tipo_meta) ON DELETE RESTRICT
);
CREATE INDEX ix_results_mission_type ON mission_results(mission_id, tipo_meta);
CREATE TABLE mission_tasks (
    id INTEGER PRIMARY KEY,
    mission_id INTEGER NOT NULL REFERENCES missions(id) ON DELETE RESTRICT,
    titulo TEXT NOT NULL CHECK(length(trim(titulo)) > 0),
    concluida INTEGER NOT NULL DEFAULT 0 CHECK(concluida IN (0,1))
);
CREATE INDEX ix_tasks_mission ON mission_tasks(mission_id, concluida);
