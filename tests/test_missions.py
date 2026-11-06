from datetime import date, datetime, timezone

import pytest

from app.db.connection import connect
from app.services.missions import dashboard_data, mission_situation

START, END = date(2026,11,9), date(2026,11,20)


@pytest.mark.parametrize("instant,code,days",[
    ("2026-11-01T12:00:00+00:00","planejada",8),
    ("2026-11-08T23:59:00+00:00","planejada",1),
    ("2026-11-09T00:00:00+00:00","em_andamento",None),
    ("2026-11-20T23:59:59+00:00","em_andamento",None),
    ("2026-11-21T00:00:00+00:00","concluida",None),
])
def test_mission_dates(instant,code,days):
    result = mission_situation(START,END,"Europe/Lisbon",datetime.fromisoformat(instant))
    assert result.codigo == code and result.dias == days


def test_argentina_uses_local_day():
    start,end = date(2026,11,16),date(2026,11,23)
    before = mission_situation(start,end,"America/Argentina/Buenos_Aires",datetime.fromisoformat("2026-11-16T02:59:00+00:00"))
    after = mission_situation(start,end,"America/Argentina/Buenos_Aires",datetime.fromisoformat("2026-11-16T03:00:00+00:00"))
    assert before.dias == 1 and before.mensagem == "Falta 1 dia"
    assert after.mensagem == "Missão em andamento"


def test_lisbon_summer_timezone():
    result = mission_situation(date(2026,7,2),date(2026,7,4),"Europe/Lisbon",
                               datetime.fromisoformat("2026-07-01T23:00:00+00:00"))
    assert result.codigo == "em_andamento"


def test_cancelled_mission():
    result = mission_situation(START,END,"Europe/Lisbon",status="cancelada")
    assert result.mensagem == "Missão cancelada"


def test_naive_datetime_rejected():
    with pytest.raises(ValueError,match="fuso"):
        mission_situation(START,END,"Europe/Lisbon",datetime(2026,11,1))


def test_invalid_period():
    with pytest.raises(ValueError,match="inválido"):
        mission_situation(END,START,"Europe/Lisbon")


def test_empty_dashboard_reads_database(repository):
    mission = repository.get("portugal")
    view = dashboard_data(repository,mission,datetime(2026,11,1,tzinfo=timezone.utc))
    assert view["next_event"] is None
    assert view["today_events"] == [] and view["tasks"] == []
    assert view["situation"].dias == 8


def test_real_records_update_summary_and_respect_mission(database,repository):
    mission = repository.get("argentina")
    with connect(database) as db:
        # Dados sintéticos exclusivos do banco temporário de testes.
        db.execute("INSERT INTO mission_results(mission_id,tipo_meta,descricao,ocorrido_em) VALUES(?, 'reuniao_qualificada','Registro de teste','2026-11-18')",(mission.id,))
        db.execute("INSERT INTO mission_events(mission_id,titulo,inicio_utc) VALUES(?, 'Compromisso de teste','2026-11-18T01:00:00Z')",(mission.id,))
        db.execute("INSERT INTO mission_events(mission_id,titulo,inicio_utc) VALUES(?, 'Próximo teste','2026-11-18T15:00:00Z')",(mission.id,))
        db.execute("INSERT INTO mission_tasks(mission_id,titulo) VALUES(?, 'Tarefa de teste')",(mission.id,))
        db.execute("INSERT INTO mission_tasks(mission_id,titulo,concluida) VALUES(?, 'Concluída',1)",(mission.id,))
    updated = repository.get("argentina")
    assert updated.metas[0].realizado == 1
    assert updated.metas[0].percentual == 12
    assert repository.get("portugal").metas[0].realizado == 0
    view = dashboard_data(repository, updated, datetime.fromisoformat("2026-11-18T12:00:00+00:00"))
    assert len(view["today_events"]) == 1
    assert view["today_events"][0]["inicio"].hour == 12
    assert view["next_event"]["titulo"] == "Próximo teste"
    assert [task["titulo"] for task in view["tasks"]] == ["Tarefa de teste"]
    portugal = dashboard_data(repository,repository.get("portugal"))
    assert portugal["next_event"] is None and portugal["tasks"] == []
