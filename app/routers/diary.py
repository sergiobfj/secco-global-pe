import json
import secrets
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.forms import read_form
from app.repositories.itinerary import ActivityConflict
from app.routers.web import find_mission, render
from app.services.diary import (TYPES,STATUSES,EVIDENCE_TYPES,EVIDENCE_STATUSES,DECISIONS,
    validate_entry,validate_evidence,validate_claim,prefill_from_itinerary)
from app.services.itinerary import InvalidActivity,mission_today

router=APIRouter()


def repo(request):
    return request.app.state.diary


def entry_or_404(request,mission,entry_id):
    item=repo(request).get(mission.id,entry_id)
    if not item: raise HTTPException(404,"Registro não encontrado")
    return item


def related_or_404(rows,item_id):
    item=next((r for r in rows if r["id"]==item_id),None)
    if not item: raise HTTPException(404,"Registro não encontrado")
    return item


def integer(values,key,optional=False):
    raw=values.get(key)
    if optional and not raw: return None
    try:
        value=int(raw)
        if value<=0: raise ValueError()
        return value
    except (ValueError,TypeError):
        raise InvalidActivity({key:"Reabra o formulário para conferir a versão ou o vínculo."})


def saved(request,url):
    if "application/json" in request.headers.get("accept",""):
        return JSONResponse({"redirect":url,"message":"Registro salvo no banco local."})
    return RedirectResponse(url,status_code=303)


def form_page(request,mission,kind,values,entry=None,related=None,errors=None,status_code=200):
    evidence=repo(request).evidence(mission.id,entry["id"]) if entry else []
    response=render(request,"diary_form.html",title={"registro":"Registrar atividade","evidencia":"Referenciar evidência","classificacao":"Classificar resultado"}[kind],
        active="diario",mission=mission,kind=kind,values=values,entry=entry,related=related,
        errors=errors or {},types=TYPES,statuses=STATUSES,evidence_types=EVIDENCE_TYPES,
        evidence_statuses=EVIDENCE_STATUSES,decisions=DECISIONS,evidence=evidence,
        evidence_versions={str(e["id"]):e["version"] for e in evidence})
    response.status_code=status_code
    return response


def failed(request,mission,kind,values,errors,entry=None,related=None,status_code=422):
    if "application/json" in request.headers.get("accept",""):
        return JSONResponse({"errors":errors},status_code=status_code)
    return form_page(request,mission,kind,values,entry,related,errors,status_code)


@router.get("/missoes/{codigo}/diario",name="diary")
def diary(request: Request,codigo: str,status: str=""):
    mission=find_mission(request,codigo)
    entries=repo(request).list(mission.id)
    if status and status not in STATUSES: raise HTTPException(422,"Status inválido.")
    if status: entries=[entry for entry in entries if entry["status"]==status]
    return render(request,"diary.html",title="Diário de Atividades",active="diario",mission=mission,
        entries=entries,summary=repo(request).summary(mission.id),filter_status=status)


@router.get("/missoes/{codigo}/diario/novo",name="new_diary")
def new_diary(request: Request,codigo: str,agenda: int | None=None):
    mission=find_mission(request,codigo)
    values={"tipo":"outra_profissional","status":"rascunho","data":mission_today(mission).isoformat(),"participantes":[]}
    if agenda is not None:
        source=request.app.state.itinerary.get(mission.id,agenda)
        if not source: raise HTTPException(404,"Compromisso não encontrado nesta missão.")
        existing=repo(request).for_itinerary(mission.id,agenda)
        if existing: return RedirectResponse(f"/missoes/{codigo}/diario/{existing}",status_code=303)
        try: values=prefill_from_itinerary(source)
        except InvalidActivity as error: raise HTTPException(422,next(iter(error.errors.values())))
    values["request_key"]=secrets.token_urlsafe(24)
    return form_page(request,mission,"registro",values)


@router.get("/missoes/{codigo}/diario/{entry_id:int}",name="diary_detail")
def diary_detail(request: Request,codigo: str,entry_id: int):
    mission=find_mission(request,codigo)
    entry=entry_or_404(request,mission,entry_id)
    return render(request,"diary_detail.html",title=entry["titulo_label"],active="diario",mission=mission,
        entry=entry,evidence=repo(request).evidence(mission.id,entry_id),claims=repo(request).claims(mission.id,entry_id),
        evidence_types=EVIDENCE_TYPES,evidence_statuses=EVIDENCE_STATUSES,decisions=DECISIONS,
        message="Registro salvo no banco local." if request.query_params.get("aviso")=="salvo" else None)


@router.get("/missoes/{codigo}/diario/{entry_id:int}/editar",name="edit_diary")
def edit_diary(request: Request,codigo: str,entry_id: int):
    mission=find_mission(request,codigo)
    entry=entry_or_404(request,mission,entry_id)
    return form_page(request,mission,"registro",{**entry,"participantes":[str(p["id"]) for p in entry["participantes"]]},entry)


@router.post("/missoes/{codigo}/diario/novo")
@router.post("/missoes/{codigo}/diario/{entry_id:int}/editar")
async def save_diary(request: Request,codigo: str,entry_id: int | None=None):
    mission=find_mission(request,codigo)
    entry=entry_or_404(request,mission,entry_id) if entry_id else None
    values=await read_form(request,max_bytes=524288)
    try:
        data=validate_entry(values,mission)
        version=integer(values,"version") if entry else None
        source=integer(values,"itinerary_item_id",optional=True) if not entry else entry["itinerary_item_id"]
        if not entry and not 20<=len(values.get("request_key",""))<=100:
            raise InvalidActivity({"form":"Reabra o formulário para obter uma identificação válida."})
        item_id=repo(request).save(mission.id,data,entry_id,version,values.get("request_key"),source)
    except InvalidActivity as error:
        return failed(request,mission,"registro",values,error.errors,entry)
    except ActivityConflict as error:
        return failed(request,mission,"registro",values,{"form":str(error)},entry,status_code=409)
    return saved(request,f"/missoes/{codigo}/diario/{item_id}?aviso=salvo")


@router.get("/missoes/{codigo}/diario/{entry_id:int}/evidencias/nova")
@router.get("/missoes/{codigo}/diario/{entry_id:int}/evidencias/{related_id:int}/editar")
def evidence_form(request: Request,codigo: str,entry_id: int,related_id: int | None=None):
    mission=find_mission(request,codigo)
    entry=entry_or_404(request,mission,entry_id)
    related=related_or_404(repo(request).evidence(mission.id,entry_id),related_id) if related_id else None
    values=related or {"tipo":"documento","status":"pendente","request_key":secrets.token_urlsafe(24)}
    return form_page(request,mission,"evidencia",values,entry,related)


@router.get("/missoes/{codigo}/diario/{entry_id:int}/metas/nova")
@router.get("/missoes/{codigo}/diario/{entry_id:int}/metas/{related_id:int}/editar")
def claim_form(request: Request,codigo: str,entry_id: int,related_id: int | None=None):
    mission=find_mission(request,codigo)
    entry=entry_or_404(request,mission,entry_id)
    related=related_or_404(repo(request).claims(mission.id,entry_id),related_id) if related_id else None
    values={**(related or {"validacao_status":"pendente"}),"entry_version":entry["version"]}
    return form_page(request,mission,"classificacao",values,entry,related)


@router.post("/missoes/{codigo}/diario/{entry_id:int}/evidencias/nova")
@router.post("/missoes/{codigo}/diario/{entry_id:int}/evidencias/{related_id:int}/editar")
@router.post("/missoes/{codigo}/diario/{entry_id:int}/metas/nova")
@router.post("/missoes/{codigo}/diario/{entry_id:int}/metas/{related_id:int}/editar")
async def save_related(request: Request,codigo: str,entry_id: int,related_id: int | None=None):
    mission=find_mission(request,codigo)
    entry=entry_or_404(request,mission,entry_id)
    kind="evidencia" if "/evidencias/" in request.url.path else "classificacao"
    rows=repo(request).evidence(mission.id,entry_id) if kind=="evidencia" else repo(request).claims(mission.id,entry_id)
    related=related_or_404(rows,related_id) if related_id else None
    values=await read_form(request,max_bytes=524288)
    try:
        if kind=="evidencia":
            data=validate_evidence(values)
            if not related and not 20<=len(values.get("request_key",""))<=100:
                raise InvalidActivity({"form":"Reabra o formulário antes de salvar."})
        else:
            if integer(values,"entry_version")!=entry["version"]:
                raise ActivityConflict("O Diário foi alterado enquanto esta classificação estava aberta. Confira a versão atual.")
            evidence = repo(request).evidence(mission.id,entry_id)
            data = validate_claim(values,mission,entry,evidence)
            if data["evidence_id"] is not None:
                try:
                    versions = json.loads(values.get("evidence_versions", "{}"))
                    shown_version = versions.get(str(data["evidence_id"])) if isinstance(versions,dict) else None
                except (ValueError,TypeError):
                    shown_version = None
                if shown_version != data["evidence_version"]:
                    raise ActivityConflict("A evidência mudou desde a abertura do formulário. Reabra e confira a referência atual.")
        version=integer(values,"version") if related else None
        repo(request).save_related(mission.id,entry_id,data,kind,related_id,version,values.get("request_key"),
                                  entry_version=entry["version"])
    except InvalidActivity as error:
        return failed(request,mission,kind,values,error.errors,entry,related)
    except ActivityConflict as error:
        return failed(request,mission,kind,values,{"form":str(error)},entry,related,409)
    return saved(request,f"/missoes/{codigo}/diario/{entry_id}?aviso=salvo")
