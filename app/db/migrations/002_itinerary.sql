-- Distribuição pública: nomes de participantes substituídos por fictícios.
-- Conteúdo e checksum diferem da migração 002 do projeto operacional.
-- Evolução aditiva: mantém as tabelas e dados da etapa anterior.
CREATE TABLE itinerary_items (
    id INTEGER PRIMARY KEY,
    mission_id INTEGER NOT NULL REFERENCES missions(id) ON DELETE RESTRICT,
    legacy_event_id INTEGER UNIQUE REFERENCES mission_events(id) ON DELETE RESTRICT,
    seed_key TEXT UNIQUE,
    titulo TEXT NOT NULL CHECK(length(trim(titulo)) BETWEEN 1 AND 160),
    descricao TEXT NOT NULL DEFAULT '' CHECK(length(descricao) <= 4000),
    categoria TEXT NOT NULL CHECK(categoria IN ('institucional','evento','turismo','alimentacao','transporte','descanso')),
    status TEXT NOT NULL CHECK(status IN ('sugestao','a_confirmar','confirmado','realizado','cancelado')),
    origem TEXT CHECK(origem IS NULL OR origem IN ('edital','proposta_aprovada','agenda_oficial','sugestao_viajantes')),
    data TEXT CHECK(data IS NULL OR (date(data) IS NOT NULL AND data=date(data))),
    horario_inicio TEXT CHECK(horario_inicio IS NULL OR (length(horario_inicio)=5 AND time(horario_inicio) IS NOT NULL)),
    horario_fim TEXT CHECK(horario_fim IS NULL OR (length(horario_fim)=5 AND time(horario_fim) IS NOT NULL)),
    inicio_utc TEXT CHECK(inicio_utc IS NULL OR datetime(inicio_utc) IS NOT NULL),
    fim_utc TEXT CHECK(fim_utc IS NULL OR datetime(fim_utc) IS NOT NULL),
    local TEXT NOT NULL DEFAULT '' CHECK(length(local) <= 200),
    endereco TEXT NOT NULL DEFAULT '' CHECK(length(endereco) <= 400),
    endereco_validado INTEGER NOT NULL DEFAULT 0 CHECK(endereco_validado IN (0,1)),
    observacoes TEXT NOT NULL DEFAULT '' CHECK(length(observacoes) <= 4000),
    link_externo TEXT NOT NULL DEFAULT '' CHECK(length(link_externo) <= 2000),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version>0),
    request_key TEXT UNIQUE,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(id,mission_id),
    CHECK(horario_inicio IS NULL OR data IS NOT NULL),
    CHECK(horario_fim IS NULL OR (horario_inicio IS NOT NULL AND horario_fim>horario_inicio)),
    CHECK(status NOT IN ('confirmado','realizado') OR data IS NOT NULL),
    CHECK(endereco_validado=0 OR length(trim(endereco))>0)
);
CREATE INDEX ix_itinerary_mission_date ON itinerary_items(mission_id,data,horario_inicio);
CREATE TABLE itinerary_participants (
    item_id INTEGER NOT NULL,
    mission_id INTEGER NOT NULL,
    participant_id INTEGER NOT NULL,
    PRIMARY KEY(item_id,participant_id),
    FOREIGN KEY(item_id,mission_id) REFERENCES itinerary_items(id,mission_id) ON DELETE RESTRICT,
    FOREIGN KEY(mission_id,participant_id) REFERENCES mission_participants(mission_id,participant_id) ON DELETE RESTRICT
);
CREATE TABLE itinerary_history (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES itinerary_items(id) ON DELETE RESTRICT,
    acao TEXT NOT NULL CHECK(acao IN ('criacao','edicao','cancelamento')),
    snapshot TEXT NOT NULL CHECK(json_valid(snapshot)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
-- Corrige o nome sem criar uma nova pessoa nem perder vínculos ou e-mail.
UPDATE participants SET nome='Alan Renato'
WHERE nome='Renato' AND NOT EXISTS(SELECT 1 FROM participants WHERE nome='Alan Renato');
