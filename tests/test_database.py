import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.db.connection import connect
from app.db.migrate import migrate
from app.db.seed import seed
from app.repositories.missions import MissionRepository


def counts(location):
    with connect(location) as db:
        return {name: db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                for name in ["missions","participants","mission_participants","mission_goals",
                             "mission_events","mission_results","mission_tasks","schema_migrations"]}


def test_initial_data(database, repository):
    assert counts(database) == {
        "missions": 2, "participants": 4, "mission_participants": 4, "mission_goals": 4,
        "mission_events": 0, "mission_results": 0, "mission_tasks": 0, "schema_migrations": 7,
    }
    portugal, argentina = repository.list()
    assert portugal.codigo == "portugal" and portugal.edital == "26/2026"
    assert portugal.timezone == "Europe/Lisbon"
    assert portugal.cidades == ["Lisboa","Aveiro","Porto"]
    assert [p.nome for p in portugal.participantes] == ["Hugo Mendes","Alan Renato"]
    assert [p.nome for p in argentina.participantes] == ["Tiago Prado","Bruno de Castro"]
    assert [p.nome for p in portugal.participantes if p.financiado_pela_subvencao] == ["Hugo Mendes"]
    assert [p.nome for p in argentina.participantes if p.financiado_pela_subvencao] == ["Bruno de Castro"]
    assert all(p.email is None for m in repository.list() for p in m.participantes)
    assert [(g.tipo_meta,g.quantidade_alvo,g.realizado) for g in portugal.metas] == [
        ("reuniao_qualificada",10,0),("loi",3,0)]
    assert [(g.tipo_meta,g.quantidade_alvo) for g in argentina.metas] == [
        ("reuniao_qualificada",8),("manifestacao_interesse",3)]
    assert str(argentina.data_inicio) == "2026-11-16"
    assert str(argentina.data_fim) == "2026-11-23"


def test_repeat_initialization_preserves_records(database):
    before = counts(database)
    for _ in range(3):
        migrate(database)
        seed(database)
    assert counts(database) == before


def test_seed_preserves_user_changes(database, repository):
    with connect(database) as db:
        db.execute("UPDATE participants SET email='teste@example.org' WHERE nome='Alan Renato'")
        db.execute("UPDATE mission_goals SET quantidade_alvo=12 WHERE mission_id=1 AND tipo_meta='reuniao_qualificada'")
    seed(database)
    assert repository.get("portugal").participantes[1].email == "teste@example.org"
    assert repository.get("portugal").metas[0].quantidade_alvo == 12


def test_concurrent_seed_does_not_duplicate(database):
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(seed, [database]*3))
    assert counts(database)["participants"] == 4
    assert counts(database)["mission_goals"] == 4


@pytest.mark.parametrize("sql", [
    "INSERT INTO mission_participants(mission_id,participant_id,papel,financiado_pela_subvencao) VALUES (999,1,'Participante',0)",
    "INSERT INTO mission_participants(mission_id,participant_id,papel,financiado_pela_subvencao) VALUES (1,1,'Participante',0)",
    "INSERT INTO mission_goals(mission_id,tipo_meta,quantidade_alvo) VALUES (1,'loi',-1)",
    "UPDATE mission_goals SET quantidade_alvo=0 WHERE id=1",
    "UPDATE missions SET data_fim='2026-01-01' WHERE id=1",
    "UPDATE missions SET data_inicio='invalida' WHERE id=1",
    "UPDATE mission_participants SET financiado_pela_subvencao=2 WHERE id=1",
    "UPDATE mission_participants SET financiado_pela_subvencao=1 WHERE participant_id=2",
    "INSERT INTO mission_results(mission_id,tipo_meta,descricao,ocorrido_em) VALUES(2,'loi','Teste','2026-11-18')",
    "DELETE FROM missions WHERE id=1",
])
def test_constraints_and_foreign_keys(database, sql):
    with pytest.raises(sqlite3.IntegrityError):
        with connect(database) as db:
            assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            db.execute(sql)


def test_database_integrity(database):
    with connect(database) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert all(row["created_at"] and row["updated_at"] for row in db.execute("SELECT * FROM missions"))


def test_unknown_migration_is_rejected(database):
    with connect(database) as db:
        db.execute("INSERT INTO schema_migrations(version,checksum) VALUES('999_future.sql','x')")
    with pytest.raises(RuntimeError, match="desconhecidas"):
        migrate(database)


def test_changed_migration_is_rejected(database):
    with connect(database) as db:
        db.execute("UPDATE schema_migrations SET checksum='alterado'")
    with pytest.raises(RuntimeError, match="alterada"):
        migrate(database)


def test_failed_migration_is_atomic(database, tmp_path, monkeypatch):
    import app.db.migrate as module
    folder = tmp_path / "migrations"
    folder.mkdir()
    for initial in module.MIGRATIONS.glob("*.sql"):
        (folder / initial.name).write_text(initial.read_text(encoding="utf-8"),encoding="utf-8")
    (folder / "999_test.sql").write_text("CREATE TABLE temporary_test(id INTEGER); INVALID SQL;",encoding="utf-8")
    monkeypatch.setattr(module, "MIGRATIONS", folder)
    with pytest.raises(sqlite3.OperationalError):
        migrate(database)
    with connect(database) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='temporary_test'").fetchone() is None
        assert db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 7
    assert len(MissionRepository(database).list()) == 2


def test_queries_are_parameterized(repository):
    assert repository.get("' OR 1=1 --") is None
    assert repository.get("inexistente") is None
