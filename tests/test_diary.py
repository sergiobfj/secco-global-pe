import html
import os
import re
import sqlite3
import subprocess
import sys
import uuid

import pytest

from app.core.config import ROOT
from app.db.connection import connect
from app.db.migrate import migrate
from app.db.seed import seed
from app.repositories.diary import DiaryRepository
from app.services.diary import prefill_from_itinerary

def form_values(client,url,**changes):
    response=client.get(url)
    assert response.status_code==200
    values={"csrf_token":client.cookies.get("secco_csrf")}
    for name in ("request_key","version","itinerary_item_id","entry_version","evidence_versions"):
        found=re.search('name="'+name+'" value="([^"]*)"',response.text)
        if found: values[name]=html.unescape(found.group(1))
    return {**values,**changes}

def create_entry(client,code="argentina",**changes):
    values=form_values(client,f"/missoes/{code}/diario/novo",
        tipo="reuniao_empresarial",titulo="Reunião exclusiva de teste",data="2026-11-01",
        horario="",organizacao="Organização de teste",local="Local de teste",objetivo="Objetivo de teste",
        descricao="Descrição da atividade realizada no teste",resultados="Resultado observado no teste",
        proximos_passos="",status="realizada",participantes=[],**{})
    values.update(changes)
    response=client.post(f"/missoes/{code}/diario/novo",data=values,headers={"Accept":"application/json"})
    return response,values

def entry_id(response):
    assert response.status_code==200,response.text
    return int(response.json()["redirect"].split("/diario/")[1].split("?")[0])

def add_evidence(client,code,item_id,**changes):
    unique=uuid.uuid4().hex
    values=form_values(client,f"/missoes/{code}/diario/{item_id}/evidencias/nova",
        tipo="documento",titulo="Comprovação de teste",status="referencia_conferida",
        referencia_url="https://example.test/documento/"+unique,referencia_chave="TESTE-"+unique,
        conferido_por="Responsável de teste",nota_conferencia="Referência conferida em ambiente temporário")
    values.update(changes)
    response=client.post(f"/missoes/{code}/diario/{item_id}/evidencias/nova",data=values,headers={"Accept":"application/json"})
    return response,values

def add_claim(client,code,item_id,evidence_id="",**changes):
    values=form_values(client,f"/missoes/{code}/diario/{item_id}/metas/nova",
        tipo_meta="reuniao_qualificada",justificativa="Justificativa exclusiva de teste",
        criterio_referencia="Orientação fornecida pela coordenação no cenário de teste",
        evidence_id=str(evidence_id),validacao_status="aprovada",validado_por="Coordenação de teste")
    values.update(changes)
    response=client.post(f"/missoes/{code}/diario/{item_id}/metas/nova",data=values,headers={"Accept":"application/json"})
    return response,values

def eligible_setup(client,code="argentina",kind="reuniao_qualificada",evidence_type="documento"):
    response,_=create_entry(client,code)
    item=entry_id(response)
    response,_=add_evidence(client,code,item,tipo=evidence_type)
    assert response.status_code==200,response.text
    evidence=client.app.state.diary.evidence(1 if code=="portugal" else 2,item)[0]
    response,_=add_claim(client,code,item,evidence["id"],tipo_meta=kind)
    assert response.status_code==200,response.text
    return item,evidence

def counts(client,code="argentina"):
    return {g.tipo_meta:g.realizado for g in client.app.state.repository.get(code).metas}

def test_empty_diary_and_no_seed_results(client):
    assert client.app.state.diary.list(1)==[]
    assert client.app.state.diary.list(2)==[]
    for code in ("portugal","argentina"):
        response=client.get(f"/missoes/{code}/diario")
        assert response.status_code==200
        assert "Cada encontro pode deixar um registro" in response.text
        assert all(value==0 for value in counts(client,code).values())

def test_create_realized_entry(client):
    response,_=create_entry(client,participantes=["3","4"])
    item=client.app.state.diary.get(2,entry_id(response))
    assert item["status"]=="realizada" and len(item["participantes"])==2
    assert item["horario"] is None and item["itinerary_item_id"] is None
    assert client.app.state.diary.summary(2)["meetings"]==1
    assert counts(client)["reuniao_qualificada"]==0

def test_incomplete_draft_is_saved(client):
    response,_=create_entry(client,titulo="",data="",descricao="",resultados="",status="rascunho")
    item=client.app.state.diary.get(2,entry_id(response))
    assert item["titulo"]=="" and item["titulo_label"]=="Rascunho sem título"
    assert item["data"] is None and item["status"]=="rascunho"
    assert client.app.state.diary.summary(2)["drafts"]==1
    assert client.app.state.diary.summary(2)["meetings"]==0

@pytest.mark.parametrize("field",["titulo","data","descricao","resultados"])
def test_realized_requires_completion(client,field):
    response,_=create_entry(client,**{field:""})
    assert response.status_code==422 and field in response.json()["errors"]

@pytest.mark.parametrize("changes,field",[
    ({"tipo":"crm"},"tipo"),({"status":"agendada"},"status"),
    ({"data":"2026-02-30"},"data"),({"horario":"10:00","data":""},"data"),
    ({"horario":"25:00"},"horario"),({"titulo":"x"*161},"titulo"),
    ({"organizacao":"x"*201},"organizacao"),({"participantes":["1"]},"participantes"),
    ({"participantes":["invalido"]},"participantes"),
    ({"data":"2026-03-29","horario":"01:30"},"horario"),
])
def test_entry_validation(client,changes,field):
    code="portugal" if field=="horario" and changes.get("data")=="2026-03-29" else "argentina"
    response,_=create_entry(client,code,**changes)
    assert response.status_code==422 and field in response.json()["errors"]

@pytest.mark.parametrize("kind",[
    "reuniao_empresarial","visita_institucional","participacao_evento",
    "networking_profissional","apresentacao_geocarbo","outra_profissional"])
def test_professional_types(client,kind):
    response,_=create_entry(client,tipo=kind)
    assert client.app.state.diary.get(2,entry_id(response))["tipo"]==kind

def test_prefill_from_agenda_and_unique_link(client):
    source=next(i for i in client.app.state.itinerary.list(2) if i["titulo"]=="InvestBA")
    # Completa somente os dados de agenda no banco temporário.
    with connect(client.app.state.settings.database_path) as db:
        db.execute("UPDATE itinerary_items SET organizacao='InvestBA',data='2026-11-01',horario_inicio='10:00',local='Local conhecido' WHERE id=?",(source["id"],))
        db.execute("INSERT INTO itinerary_participants(item_id,mission_id,participant_id) VALUES(?,2,3)",(source["id"],))
    url=f"/missoes/argentina/diario/novo?agenda={source['id']}"
    values=form_values(client,url)
    page=client.get(url).text
    for known in ["InvestBA","2026-11-01","10:00","Local conhecido"]:
        assert known in page
    assert 'name="participantes" value="3" checked' in page
    values.update(tipo="reuniao_empresarial",titulo="InvestBA",data="2026-11-01",horario="10:00",
        organizacao="InvestBA",local="Local conhecido",descricao="Aconteceu no teste",resultados="Resultado do teste",
        status="realizada",participantes=["3"])
    response=client.post("/missoes/argentina/diario/novo",data=values,headers={"Accept":"application/json"})
    item=entry_id(response)
    assert client.app.state.diary.get(2,item)["itinerary_item_id"]==source["id"]
    linked=client.get(url,follow_redirects=False)
    assert linked.status_code==303 and linked.headers["location"].endswith("/"+str(item))
    assert "Abrir registro do Diário" in client.get(f"/missoes/argentina/atividades/{source['id']}").text
    assert "Registro no Diário" in client.get("/missoes/argentina/planejamento?data=2026-11-01").text
    assert client.app.state.itinerary.get(2,source["id"])["status"]=="a_confirmar"
    replay = client.post("/missoes/argentina/diario/novo", data=values, headers={"Accept": "application/json"})
    assert entry_id(replay) == item
    values["request_key"]=uuid.uuid4().hex
    assert client.post("/missoes/argentina/diario/novo",data=values,headers={"Accept":"application/json"}).status_code==409
    assert len(client.app.state.diary.list(2))==1

def test_tourism_not_converted_to_professional_record(client):
    tourist=next(i for i in client.app.state.itinerary.list(2) if i["categoria"]=="turismo")
    assert "Registrar resultado" not in client.get(f"/missoes/argentina/atividades/{tourist['id']}").text
    assert client.get(f"/missoes/argentina/diario/novo?agenda={tourist['id']}").status_code==422
    assert client.app.state.diary.list(2)==[]

def test_cross_mission_agenda_and_entry_are_rejected(client):
    source=client.app.state.itinerary.list(1)[0]
    assert client.get(f"/missoes/argentina/diario/novo?agenda={source['id']}").status_code==404
    response,_=create_entry(client,itinerary_item_id=str(source["id"]))
    assert response.status_code==409
    response,_=create_entry(client)
    item=entry_id(response)
    for suffix in ("","/editar","/evidencias/nova","/metas/nova"):
        assert client.get(f"/missoes/portugal/diario/{item}"+suffix).status_code==404

def test_duplicate_submit_and_stale_edit(client):
    response,values=create_entry(client)
    item=entry_id(response)
    retry=client.post("/missoes/argentina/diario/novo",data=values,headers={"Accept":"application/json"})
    assert entry_id(retry)==item
    url=f"/missoes/argentina/diario/{item}/editar"
    values.update(version="1",resultados="Resultado revisado")
    assert client.post(url,data=values,headers={"Accept":"application/json"}).status_code==200
    values["resultados"]="Texto não salvo por conflito"
    response=client.post(url,data=values)
    assert response.status_code==409 and "Texto não salvo por conflito" in response.text

def test_draft_completion_and_cancellation(client):
    response,values=create_entry(client,status="rascunho",descricao="",resultados="")
    item=entry_id(response)
    values.update(version="1",status="realizada",descricao="Aconteceu",resultados="Resultado")
    url=f"/missoes/argentina/diario/{item}/editar"
    assert client.post(url,data=values,headers={"Accept":"application/json"}).status_code==200
    assert client.app.state.diary.summary(2)["meetings"]==1
    values.update(version="2",status="cancelada")
    assert client.post(url,data=values,headers={"Accept":"application/json"}).status_code==200
    assert client.app.state.diary.summary(2)["meetings"]==0
    assert client.app.state.diary.get(2,item) is not None

def test_pending_evidence_does_not_simulate_upload(client):
    response,_=create_entry(client)
    item=entry_id(response)
    response,_=add_evidence(client,"argentina",item,status="pendente",referencia_url="",referencia_chave="",conferido_por="",nota_conferencia="")
    assert response.status_code==200
    page=client.get(f"/missoes/argentina/diario/{item}")
    assert "Upload oficial pendente" in page.text
    assert 'type="file"' not in page.text
    assert counts(client)["reuniao_qualificada"]==0

@pytest.mark.parametrize("changes,field",[
    ({"referencia_url":"http://example.org"},"referencia_url"),
    ({"referencia_url":"javascript:alert(1)"},"referencia_url"),
    ({"referencia_url":"https://user:secret@example.org"},"referencia_url"),
    ({"conferido_por":""},"conferido_por"),
    ({"nota_conferencia":""},"nota_conferencia"),
    ({"referencia_chave":""},"referencia_chave"),
    ({"tipo":"upload"},"tipo"),
])
def test_evidence_validation(client,changes,field):
    response,_=create_entry(client)
    response,_=add_evidence(client,"argentina",entry_id(response),**changes)
    assert response.status_code==422 and field in response.json()["errors"]

def test_duplicate_evidence_reference_is_rejected(client):
    response,_=create_entry(client)
    item=entry_id(response)
    response,values=add_evidence(client,"argentina",item)
    assert response.status_code==200
    response,_=add_evidence(client,"argentina",item,referencia_url=values["referencia_url"],referencia_chave=values["referencia_chave"])
    assert response.status_code==409

@pytest.mark.parametrize("code,kind,evidence_type",[
    ("argentina","reuniao_qualificada","fotografia"),
    ("argentina","manifestacao_interesse","confirmacao_institucional"),
    ("portugal","reuniao_qualificada","lista_presenca"),
    ("portugal","loi","carta_intencao"),
])
def test_validated_results_count_once(client,code,kind,evidence_type):
    item,evidence=eligible_setup(client,code,kind,evidence_type)
    assert counts(client,code)[kind]==1
    assert all(value==0 for value in counts(client,"portugal" if code=="argentina" else "argentina").values())
    response,_=add_claim(client,code,item,evidence["id"],tipo_meta=kind)
    assert response.status_code==409
    assert counts(client,code)[kind]==1

@pytest.mark.parametrize("changes,field",[
    ({"justificativa":""},"justificativa"),
    ({"criterio_referencia":""},"criterio_referencia"),
    ({"validado_por":""},"validado_por"),
    ({"tipo_meta":"loi"},"tipo_meta"),
])
def test_qualification_requires_explicit_justification_and_criterion(client,changes,field):
    response,_=create_entry(client)
    item=entry_id(response)
    add_evidence(client,"argentina",item)
    evidence=client.app.state.diary.evidence(2,item)[0]
    response,_=add_claim(client,"argentina",item,evidence["id"],**changes)
    assert response.status_code==422 and field in response.json()["errors"]
    assert counts(client)["reuniao_qualificada"]==0

def test_drafts_and_unproven_results_never_count(client):
    response,_=create_entry(client,status="rascunho")
    item=entry_id(response)
    add_evidence(client,"argentina",item)
    evidence=client.app.state.diary.evidence(2,item)[0]
    response,_=add_claim(client,"argentina",item,evidence["id"])
    assert response.status_code==422
    response,_=add_claim(client,"argentina",item,"",validacao_status="pendente")
    assert response.status_code==200 and counts(client)["reuniao_qualificada"]==0

def test_no_evidence_or_wrong_type_cannot_count(client):
    response,_=create_entry(client,"portugal")
    item=entry_id(response)
    response,_=add_claim(client,"portugal",item,"",tipo_meta="loi")
    assert response.status_code==422
    add_evidence(client,"portugal",item,tipo="fotografia")
    evidence=client.app.state.diary.evidence(1,item)[0]
    response,_=add_claim(client,"portugal",item,evidence["id"],tipo_meta="loi")
    assert response.status_code==422 and "evidence_id" in response.json()["errors"]
    assert counts(client,"portugal")["loi"]==0

def test_approval_is_invalidated_when_activity_changes(client):
    item,_=eligible_setup(client)
    record=client.app.state.diary.get(2,item)
    values={**record,"participantes":[str(p["id"]) for p in record["participantes"]],
            "csrf_token":client.cookies.get("secco_csrf"),"resultados":"Novo resultado informado"}
    response=client.post(f"/missoes/argentina/diario/{item}/editar",data=values,headers={"Accept":"application/json"})
    assert response.status_code==200
    assert counts(client)["reuniao_qualificada"]==0
    assert client.app.state.diary.claims(2,item)[0]["validacao_status"]=="pendente"

def test_evidence_revision_invalidates_related_approval(client):
    item,evidence=eligible_setup(client)
    values={**evidence,"status":"invalidada","csrf_token":client.cookies.get("secco_csrf")}
    response=client.post(f"/missoes/argentina/diario/{item}/evidencias/{evidence['id']}/editar",
        data=values,headers={"Accept":"application/json"})
    assert response.status_code==200
    assert counts(client)["reuniao_qualificada"]==0

def test_same_mission_evidence_must_belong_to_entry(client):
    response,_=create_entry(client)
    first=entry_id(response)
    add_evidence(client,"argentina",first)
    proof=client.app.state.diary.evidence(2,first)[0]
    response,_=create_entry(client)
    second=entry_id(response)
    response,_=add_claim(client,"argentina",second,proof["id"])
    assert response.status_code==422
    with pytest.raises(sqlite3.IntegrityError):
        with connect(client.app.state.settings.database_path) as db:
            db.execute("INSERT INTO diary_goal_claims(entry_id,mission_id,tipo_meta,evidence_id) VALUES(?,2,'reuniao_qualificada',?)",(second,proof["id"]))

def test_diary_fk_prevents_cross_mission_participants(client):
    response,_=create_entry(client)
    item=entry_id(response)
    with pytest.raises(sqlite3.IntegrityError):
        with connect(client.app.state.settings.database_path) as db:
            db.execute("INSERT INTO diary_participants(entry_id,mission_id,participant_id) VALUES(?,2,1)",(item,))

def test_history_persistence_and_seed_no_diary_duplicates(client):
    item,_=eligible_setup(client)
    path=client.app.state.settings.database_path
    migrate(path);seed(path);migrate(path);seed(path)
    with connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM diary_entries").fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM diary_history WHERE entry_id=?",(item,)).fetchone()[0]==3
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall()==[]

def test_csrf_and_xss(client):
    values=form_values(client,"/missoes/argentina/diario/novo",titulo="Teste",tipo="reuniao_empresarial",status="rascunho")
    token=values.pop("csrf_token")
    assert client.post("/missoes/argentina/diario/novo",data=values).status_code==403
    values.update(csrf_token=token,titulo="<script>alert(1)</script>")
    response=client.post("/missoes/argentina/diario/novo",data=values,headers={"Accept":"application/json"})
    page=client.get(response.json()["redirect"])
    assert "<script>alert(1)</script>" not in page.text and "&lt;script&gt;" in page.text

def test_html_error_preserves_description(client):
    response,values=create_entry(client,descricao="",resultados="")
    values.update(titulo="Texto preservado",descricao="Descrição preservada",status="realizada",data="invalid")
    response=client.post("/missoes/argentina/diario/novo",data=values)
    assert response.status_code==422 and "Descrição preservada" in response.text and "Texto preservado" in response.text

def test_pending_classification_visible_and_dashboard_agenda_stays_first(client):
    response,_=create_entry(client)
    item=entry_id(response)
    add_claim(client,"argentina",item,validacao_status="pendente",validado_por="",criterio_referencia="",justificativa="")
    page=client.get("/missoes/argentina")
    assert page.text.index("Agenda do dia")<page.text.index("Resultados da missão")
    assert "Reunião exclusiva de teste" in page.text
    assert "rascunhos a completar" in page.text
    assert 'class="pending-strip" href="/missoes/argentina/diario"' in page.text
    assert counts(client)["reuniao_qualificada"]==0

def test_stale_classification_cannot_approve_changed_entry(client):
    response,_=create_entry(client)
    item=entry_id(response)
    add_evidence(client,"argentina",item)
    proof=client.app.state.diary.evidence(2,item)[0]
    values=form_values(client,f"/missoes/argentina/diario/{item}/metas/nova",
        tipo_meta="reuniao_qualificada",justificativa="Justificativa",criterio_referencia="Referência",
        validado_por="Coordenação",validacao_status="aprovada",evidence_id=str(proof["id"]))
    entry=client.app.state.diary.get(2,item)
    entry["participantes"]=[]
    client.app.state.diary.save(2,entry,item,entry["version"])
    response=client.post(f"/missoes/argentina/diario/{item}/metas/nova",data=values,headers={"Accept":"application/json"})
    assert response.status_code==409 and counts(client)["reuniao_qualificada"]==0

def test_qa_refuses_explicit_operational_configuration():
    env={**os.environ,"DATABASE_PATH":str(ROOT/"data/secco.sqlite3")}
    response=subprocess.run([sys.executable,"-m","scripts.serve_qa","--port","8059"],env=env,capture_output=True,text=True,timeout=10)
    assert response.returncode!=0 and "operacional" in response.stderr

def test_previous_migrations_unchanged():
    import hashlib
    expected = {"001_foundation.sql":"b4b905d3033057eaef2db5855ec9a74587d34fe868773122c9b59f030592d434","002_itinerary.sql":"6bcc1590e154633781746fcd901b899ef016b77b499211e7c9bed91dafa77b5b"}
    for name, checksum in expected.items():
        assert hashlib.sha256((ROOT/"app/db/migrations"/name).read_bytes()).hexdigest() == checksum


def test_qa_tag_cannot_target_normal_application(client):
    response = client.get("/missoes/argentina", headers={"X-SECCO-QA-Instance": "wrong-instance"})
    assert response.status_code == 403
    assert client.get("/__qa__/identity").status_code == 404
    assert client.app.state.diary.list(2) == []


def test_recent_entries_use_last_update_not_activity_date(client):
    first, _ = create_entry(client, titulo="Atualizada agora", data="2026-11-01")
    first_id = entry_id(first)
    second, _ = create_entry(client, titulo="Data posterior", data="2026-11-20")
    second_id = entry_id(second)
    with connect(client.app.state.settings.database_path) as db:
        db.execute("UPDATE diary_entries SET updated_at='2026-11-02T00:00:00Z' WHERE id=?", (first_id,))
        db.execute("UPDATE diary_entries SET updated_at='2026-11-01T00:00:00Z' WHERE id=?", (second_id,))
    assert client.app.state.diary.summary(2)["recent"][0]["id"] == first_id


def test_stale_evidence_cannot_receive_new_approval(client):
    response, _ = create_entry(client)
    item = entry_id(response)
    add_evidence(client, "argentina", item)
    proof = client.app.state.diary.evidence(2, item)[0]
    url = f"/missoes/argentina/diario/{item}/metas/nova"
    values = form_values(client, url, tipo_meta="reuniao_qualificada", justificativa="Justificativa",
        criterio_referencia="Critério recebido", validacao_status="aprovada", validado_por="Coordenação",
        evidence_id=str(proof["id"]))
    edit = {**proof, "referencia_chave": "DOCUMENTO-REVISADO", "csrf_token": client.cookies.get("secco_csrf")}
    response = client.post(f"/missoes/argentina/diario/{item}/evidencias/{proof['id']}/editar",
                          data=edit, headers={"Accept": "application/json"})
    assert response.status_code == 200
    response = client.post(url, data=values, headers={"Accept": "application/json"})
    assert response.status_code == 409
    assert counts(client)["reuniao_qualificada"] == 0


def test_database_view_excludes_approval_of_previous_evidence_version(client):
    item, proof = eligible_setup(client)
    assert counts(client)["reuniao_qualificada"] == 1
    with connect(client.app.state.settings.database_path) as db:
        db.execute("UPDATE diary_evidence SET version=version+1 WHERE id=?", (proof["id"],))
    assert counts(client)["reuniao_qualificada"] == 0


def test_failed_diary_write_rolls_back_without_partial_results(client):
    from app.repositories.itinerary import ActivityConflict
    from app.services.diary import validate_entry
    mission = client.app.state.repository.get("argentina")
    data = validate_entry({"tipo": "reuniao_empresarial", "titulo": "Rascunho de teste", "status": "rascunho"}, mission)
    data["participantes"] = [999999]
    with pytest.raises(ActivityConflict):
        client.app.state.diary.save(2, data, request_key=uuid.uuid4().hex)
    assert client.app.state.diary.list(2) == []
    with connect(client.app.state.settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM diary_history").fetchone()[0] == 0
    response, _ = create_entry(client)
    assert client.app.state.diary.get(2, entry_id(response)) is not None
