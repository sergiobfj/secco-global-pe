import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest

from app.core.config import ROOT
from app.db.connection import connect
from app.db.migrate import migrate
from app.db.seed import seed
from app.repositories.itinerary import ItineraryRepository, ActivityConflict
from app.services.itinerary import (InvalidActivity, validate_activity, local_to_utc,
                                    mission_today, choose_day, calendar_days)

def form(client, code="argentina", **overrides):
    response = client.get(f"/missoes/{code}/atividades/nova")
    values = {
        "csrf_token":client.cookies.get("secco_csrf"),
        "request_key":re.search(r'name="request_key" value="([^"]+)"',response.text).group(1),
        "titulo":"Atividade exclusiva de teste", "categoria":"institucional",
        "status":"a_confirmar", "participantes":[],
    }
    return {**values, **overrides}

def create(client, code="argentina", **overrides):
    values = form(client,code,**overrides)
    response = client.post(f"/missoes/{code}/atividades/nova",data=values,
                           headers={"Accept":"application/json"})
    return response,values

def item_from_response(client,response):
    return int(response.json()["redirect"].split("/atividades/")[1].split("?")[0])

def test_seed_itinerary_is_factual_and_idempotent(database):
    repo = ItineraryRepository(database)
    before = repo.list(1)+repo.list(2)
    assert len(before)==20
    assert sum(item["data"] is None for item in before)==18
    assert all(item["horario_inicio"] is None and item["horario_fim"] is None for item in before)
    assert all(item["status"] in ("sugestao","a_confirmar") for item in before)
    dated = [item for item in before if item["data"]]
    assert [item["data"] for item in dated]==["2026-11-18","2026-11-19"]
    assert all(item["endereco"]=="Av. Santa Fe 750, Buenos Aires" for item in dated)
    assert all(item["origem"] is None for item in before if item["categoria"]!="turismo")
    for _ in range(3):
        migrate(database)
        seed(database)
    assert repo.list(1)+repo.list(2)==before

def test_minimal_create_and_persistence(client):
    response,_ = create(client)
    assert response.status_code==200
    item_id = item_from_response(client,response)
    repo = ItineraryRepository(client.app.state.settings.database_path)
    item = repo.get(2,item_id)
    assert item["data"] is None and item["horario_inicio"] is None
    assert item["origem"] is None and item["participantes"]==[]
    assert item["categoria"]=="institucional" and item["status"]=="a_confirmar"
    assert item["maps_url"] is None and item["created_at"] and item["updated_at"]
    assert repo.get(1,item_id) is None

def test_complete_activity(client):
    response,_ = create(client,titulo="Reunião de teste",categoria="institucional",status="confirmado",
        origem="sugestao_viajantes",data="2026-11-18",horario_inicio="10:00",horario_fim="11:15",
        local="Local de teste",endereco="Endereço de teste",endereco_validado="1",
        participantes=["3","4"],descricao="Descrição de teste",observacoes="Observação de teste",
        link_externo="https://example.org/referencia")
    assert response.status_code==200
    item = client.app.state.itinerary.get(2,item_from_response(client,response))
    assert item["inicio_utc"]=="2026-11-18T13:00:00Z"
    assert item["fim_utc"]=="2026-11-18T14:15:00Z"
    assert [p["id"] for p in item["participantes"]]==[3,4]
    assert item["origem_label"]=="Sugestão dos viajantes"
    assert "api=1" in item["maps_url"] and "query=" in item["maps_url"]

@pytest.mark.parametrize("changes,field",[
    ({"titulo":"  "},"titulo"),
    ({"titulo":"x"*161},"titulo"),
    ({"categoria":"qualquer"},"categoria"),
    ({"status":"qualquer"},"status"),
    ({"origem":"inexistente"},"origem"),
    ({"data":"2026-02-30"},"data"),
    ({"data":"20261118"},"data"),
    ({"data":"2101-01-01"},"data"),
    ({"horario_inicio":"25:00","data":"2026-11-18"},"horario_inicio"),
    ({"horario_inicio":"10:00"},"data"),
    ({"horario_fim":"12:00"},"horario_fim"),
    ({"horario_inicio":"12:00","horario_fim":"11:00","data":"2026-11-18"},"horario_fim"),
    ({"horario_inicio":"12:00","horario_fim":"12:00","data":"2026-11-18"},"horario_fim"),
    ({"status":"confirmado"},"data"),
    ({"status":"realizado"},"data"),
    ({"endereco_validado":"1"},"endereco"),
    ({"participantes":["1"]},"participantes"),
    ({"participantes":["abc"]},"participantes"),
    ({"link_externo":"javascript:alert(1)"},"link_externo"),
    ({"link_externo":"//example.org"},"link_externo"),
    ({"link_externo":"https://usuario:senha@example.org"},"link_externo"),
    ({"descricao":"x"*4001},"descricao"),
])
def test_validation(client,changes,field):
    response,_ = create(client,**changes)
    assert response.status_code==422
    assert field in response.json()["errors"]

@pytest.mark.parametrize("status",["sugestao","a_confirmar","confirmado","realizado","cancelado"])
def test_all_statuses(client,status):
    response,_=create(client,status=status,data="2026-11-18")
    assert response.status_code==200
    item=client.app.state.itinerary.get(2,item_from_response(client,response))
    assert item["status"]==status

@pytest.mark.parametrize("origin",["edital","proposta_aprovada","agenda_oficial","sugestao_viajantes"])
def test_origin_never_confirms(client,origin):
    response,_=create(client,origem=origin)
    item=client.app.state.itinerary.get(2,item_from_response(client,response))
    assert item["origem"]==origin and item["status"]=="a_confirmar"

def test_edit_date_time_participants_and_history(client):
    response,values=create(client,data="2026-11-18",participantes=["3"])
    item_id=item_from_response(client,response)
    values.update(titulo="Título revisado",data="2026-11-19",horario_inicio="14:00",status="confirmado",version="1",participantes=["4"])
    update=client.post(f"/missoes/argentina/atividades/{item_id}/editar",data=values,headers={"Accept":"application/json"})
    assert update.status_code==200
    item=client.app.state.itinerary.get(2,item_id)
    assert item["version"]==2 and item["titulo"]=="Título revisado"
    assert item["inicio_utc"]=="2026-11-19T17:00:00Z"
    assert [p["id"] for p in item["participantes"]]==[4]
    with connect(client.app.state.settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM itinerary_history WHERE item_id=?",(item_id,)).fetchone()[0]==2

def test_stale_edit_keeps_entered_data(client):
    response,values=create(client)
    item_id=item_from_response(client,response)
    url=f"/missoes/argentina/atividades/{item_id}/editar"
    values.update(version="1",titulo="Primeira alteração")
    assert client.post(url,data=values,headers={"Accept":"application/json"}).status_code==200
    values["titulo"]="Texto ainda não salvo"
    conflict=client.post(url,data=values)
    assert conflict.status_code==409 and "Texto ainda não salvo" in conflict.text
    assert client.app.state.itinerary.get(2,item_id)["titulo"]=="Primeira alteração"

def test_cancel_preserves_record_and_history(client):
    response,values=create(client,status="confirmado",data="2026-11-18")
    item_id=item_from_response(client,response)
    url=f"/missoes/argentina/atividades/{item_id}/cancelar"
    values["version"]="1"
    assert client.post(url,data=values,headers={"Accept":"application/json"}).status_code==200
    assert client.app.state.itinerary.get(2,item_id)["status"]=="cancelado"
    assert client.post(url,data=values,headers={"Accept":"application/json"}).status_code==409
    with connect(client.app.state.settings.database_path) as db:
        assert db.execute("SELECT acao FROM itinerary_history WHERE item_id=? ORDER BY id DESC",(item_id,)).fetchone()[0]=="cancelamento"

def test_cross_mission_cannot_read_edit_cancel(client):
    response,values=create(client)
    item_id=item_from_response(client,response)
    values["version"]="1"
    for suffix,method in [("",client.get),("/editar",client.get),("/editar",client.post),("/cancelar",client.post)]:
        result=method(f"/missoes/portugal/atividades/{item_id}"+suffix,**({"data":values} if method==client.post else {}))
        assert result.status_code==404

def test_double_submit_creates_once(client):
    values=form(client)
    url="/missoes/argentina/atividades/nova"
    first=client.post(url,data=values,headers={"Accept":"application/json"})
    second=client.post(url,data=values,headers={"Accept":"application/json"})
    assert first.json()["redirect"]==second.json()["redirect"]
    item_id=item_from_response(client,first)
    with connect(client.app.state.settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM itinerary_history WHERE item_id=?",(item_id,)).fetchone()[0]==1

@pytest.mark.parametrize("kind",["missing","wrong","origin","cross-site"])
def test_csrf_protection(client,kind):
    values=form(client)
    headers={"Accept":"application/json"}
    if kind=="missing": values.pop("csrf_token")
    if kind=="wrong": values["csrf_token"]="incorrect"
    if kind=="origin": headers["Origin"]="https://example.org"
    if kind=="cross-site": headers["Sec-Fetch-Site"]="cross-site"
    response=client.post("/missoes/argentina/atividades/nova",data=values,headers=headers)
    assert response.status_code==403

def test_oversized_form_and_wrong_media_type(client):
    values=form(client)
    response=client.post("/missoes/argentina/atividades/nova",content="x"*200000,
        headers={"Content-Type":"application/x-www-form-urlencoded"})
    assert response.status_code==413
    assert client.post("/missoes/argentina/atividades/nova",json=values).status_code==415

def test_no_js_validation_preserves_input(client):
    values=form(client,titulo="Título preservado",horario_inicio="25:90",data="2026-11-18")
    response=client.post("/missoes/argentina/atividades/nova",data=values)
    assert response.status_code==422
    assert 'value="Título preservado"' in response.text
    assert "Informe um horário válido" in response.text

def test_local_preference_and_explicit_selection(client):
    assert "Acessar missão" in client.get("/").text
    client.get("/missoes/argentina")
    response=client.get("/",follow_redirects=False)
    assert response.status_code==303 and response.headers["location"]=="/missoes/argentina"
    assert "Acessar missão" in client.get("/?selecionar=1").text
    client.get("/missoes/portugal")
    assert client.get("/",follow_redirects=False).headers["location"]=="/missoes/portugal"
    client.cookies.set("secco_mission","invalida")
    assert client.get("/",follow_redirects=False).status_code==200

def test_daily_and_undated_view(client):
    response=client.get("/missoes/argentina/planejamento?data=2026-11-18")
    assert response.status_code==200 and "Simpósio Iberoamericano" in response.text
    assert "Sem horário" in response.text and "A confirmar" in response.text
    undated=client.get("/missoes/argentina/planejamento?sem_data=true")
    assert "InvestBA" in undated.text and "Obelisco" in undated.text
    assert "Web Summit" not in undated.text
    portugal=client.get("/missoes/portugal/planejamento?sem_data=true")
    assert "Web Summit" in portugal.text and "InvestBA" not in portugal.text
    assert client.get("/missoes/portugal/planejamento?data=invalid").status_code==422

def test_references_are_escaped(client):
    response,_=create(client,titulo="<script>alert(1)</script>",descricao="<img src=x onerror=alert(1)>")
    detail=client.get(response.json()["redirect"])
    assert "<script>alert(1)</script>" not in detail.text
    assert "&lt;script&gt;" in detail.text and "&lt;img" in detail.text

def test_legacy_import_preserves_times_and_does_not_confirm(database,repository):
    with connect(database) as db:
        db.execute("INSERT INTO mission_events(mission_id,titulo,inicio_utc) VALUES(2,'Legado de teste','2026-11-18T01:30:00Z')")
    repo=ItineraryRepository(database)
    mission=repository.get("argentina")
    repo.import_legacy(mission)
    repo.import_legacy(mission)
    legacy=[item for item in repo.list(2) if item["legacy_event_id"]]
    assert len(legacy)==1 and legacy[0]["data"]=="2026-11-17"
    assert legacy[0]["horario_inicio"]=="22:30" and legacy[0]["status"]=="a_confirmar"
    with connect(database) as db:
        assert db.execute("SELECT COUNT(*) FROM mission_events").fetchone()[0]==1

def test_seed_does_not_restore_cancelled_or_edited_item(database):
    repo=ItineraryRepository(database)
    item=repo.list(2)[0]
    repo.cancel(2,item["id"],item["version"])
    seed(database)
    assert repo.get(2,item["id"])["status"]=="cancelado"

def test_participant_constraint_prevents_cross_mission(database):
    repo=ItineraryRepository(database)
    item=repo.list(2)[0]
    with pytest.raises(sqlite3.IntegrityError):
        with connect(database) as db:
            db.execute("INSERT INTO itinerary_participants(item_id,mission_id,participant_id) VALUES(?,?,?)",(item["id"],2,1))

@pytest.mark.parametrize("zone,day,hour,expected",[
    ("Europe/Lisbon","2026-11-09","10:00","2026-11-09T10:00:00Z"),
    ("America/Argentina/Buenos_Aires","2026-11-18","00:30","2026-11-18T03:30:00Z"),
])
def test_timezones(zone,day,hour,expected):
    assert local_to_utc(day,hour,zone)==expected

@pytest.mark.parametrize("day",["2026-03-29","2026-10-25"])
def test_nonexistent_or_ambiguous_time_rejected(day):
    with pytest.raises(ValueError):
        local_to_utc(day,"01:30","Europe/Lisbon")

def test_day_selection_and_extension(repository):
    mission=repository.get("argentina")
    now=datetime.fromisoformat("2026-11-18T02:30:00+00:00")
    assert mission_today(mission,now)==date(2026,11,17)
    days=calendar_days(mission,date(2026,11,18),date(2026,11,18))
    assert days[0]["date"]==date(2026,11,15) and days[-1]["date"]==date(2026,11,24)
    assert sum(day["today"] for day in days)==1

def test_original_migration_is_unchanged():
    import hashlib
    assert hashlib.sha256((ROOT/"app/db/migrations/001_foundation.sql").read_bytes()).hexdigest()=="b4b905d3033057eaef2db5855ec9a74587d34fe868773122c9b59f030592d434"

def test_upgrade_keeps_existing_data(tmp_path,monkeypatch):
    import app.db.migrate as module
    old=tmp_path/"old";old.mkdir()
    initial=module.MIGRATIONS/"001_foundation.sql"
    (old/initial.name).write_bytes(initial.read_bytes())
    database=tmp_path/"upgrade.sqlite3"
    original=module.MIGRATIONS
    monkeypatch.setattr(module,"MIGRATIONS",old)
    migrate(database)
    with connect(database) as db:
        db.execute("INSERT INTO participants(id,nome,email) VALUES(10,'Renato','preservado@example.org')")
    monkeypatch.setattr(module,"MIGRATIONS",original)
    migrate(database)
    with connect(database) as db:
        person=db.execute("SELECT * FROM participants WHERE id=10").fetchone()
        assert person["nome"]=="Alan Renato" and person["email"]=="preservado@example.org"

def test_reused_submission_key_cannot_hide_new_values(client):
    response,values=create(client)
    item_id=item_from_response(client,response)
    values["titulo"]="Outro texto após resposta perdida"
    retry=client.post("/missoes/argentina/atividades/nova",data=values,headers={"Accept":"application/json"})
    assert retry.status_code==409 and "form" in retry.json()["errors"]
    assert client.app.state.itinerary.get(2,item_id)["titulo"]=="Atividade exclusiva de teste"

def test_reused_submission_key_across_missions_is_rejected(client):
    response,values=create(client)
    retry=client.post("/missoes/portugal/atividades/nova",data=values,headers={"Accept":"application/json"})
    assert retry.status_code==409

def test_form_reference_policy_supports_native_post(client):
    response=client.get("/missoes/portugal/atividades/nova")
    assert response.headers["referrer-policy"]=="same-origin"

def test_deep_link_remembers_mission(client):
    client.get("/missoes/portugal/planejamento")
    assert client.get("/",follow_redirects=False).headers["location"]=="/missoes/portugal"

def test_today_uses_confirmations_and_mission_timezone(database,repository):
    from app.services.missions import operational_dashboard
    repo=ItineraryRepository(database)
    mission=repository.get("argentina")
    for title,status,hour in [("Sugestão anterior","sugestao","08:00"),
                             ("Confirmado em curso","confirmado","09:00"),
                             ("Confirmado futuro","confirmado","11:00"),
                             ("Cancelado","cancelado","08:30")]:
        data=validate_activity({"titulo":title,"categoria":"institucional","status":status,
            "data":"2026-11-18","horario_inicio":hour,"horario_fim":"12:00"},mission)
        repo.save(mission.id,data)
    view=operational_dashboard(repository,repo,mission,datetime.fromisoformat("2026-11-18T13:30:00+00:00"))
    assert view["today"]==date(2026,11,18)
    assert view["next_event"]["titulo"]=="Confirmado em curso"
    assert len(view["today_events"])==5
    assert all(goal.realizado==0 for goal in repository.get("argentina").metas)
