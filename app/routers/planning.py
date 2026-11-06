import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.forms import read_form
from app.repositories.itinerary import ActivityConflict
from app.routers.web import find_mission, render
from app.services.itinerary import (CATEGORIES, STATUSES, ORIGINS, WEEKDAYS, InvalidActivity,
                                    calendar_days, choose_day, mission_today, validate_activity)

router = APIRouter()


def repository(request,mission):
    repo = request.app.state.itinerary
    repo.import_legacy(mission)
    return repo


def item_or_404(request,mission,item_id):
    item = repository(request,mission).get(mission.id,item_id)
    if item is None:
        raise HTTPException(404,"Atividade não encontrada")
    return item


def form_page(request,mission,values,errors=None,item=None,status_code=200):
    response = render(request,"activity_form.html",title="Editar atividade" if item else "Nova atividade",
        active="planejamento",mission=mission,values=values,errors=errors or {},item=item,
        categories=CATEGORIES,statuses=STATUSES,origins=ORIGINS)
    response.status_code = status_code
    return response


def result(request,url,message):
    if "application/json" in request.headers.get("accept",""):
        return JSONResponse({"redirect":url,"message":message})
    return RedirectResponse(url,status_code=303)


def failure(request,mission,values,errors,item=None,status_code=422):
    if "application/json" in request.headers.get("accept",""):
        return JSONResponse({"errors":errors},status_code=status_code)
    return form_page(request,mission,values,errors,item,status_code)


@router.get("/missoes/{codigo}/planejamento",name="planning")
def planning(request: Request,codigo: str,data: str | None=None,sem_data: bool=False):
    mission = find_mission(request,codigo)
    try:
        selected = choose_day(mission,data)
    except InvalidActivity:
        raise HTTPException(422,"Selecione uma data válida.")
    today = mission_today(mission)
    all_items = repository(request,mission).list(mission.id)
    items = [item for item in all_items if item["data"] == (None if sem_data else selected.isoformat())]
    return render(request,"planning.html",title="Planejamento",active="planejamento",mission=mission,
        items=items,selected=selected,weekday=WEEKDAYS[selected.weekday()],today=today,
        days=calendar_days(mission,selected,today),undated_count=sum(item["data"] is None for item in all_items),
        sem_data=sem_data)


@router.get("/missoes/{codigo}/atividades/nova",name="new_activity")
def new_activity(request: Request,codigo: str,data: str=""):
    mission = find_mission(request,codigo)
    # A data só vem preenchida quando o usuário escolheu explicitamente um dia.
    if data:
        try:
            choose_day(mission,data)
        except InvalidActivity:
            raise HTTPException(422,"Selecione uma data válida.")
    return form_page(request,mission,{"data":data,"categoria":"institucional","status":"a_confirmar",
                                    "participantes":[],"request_key":secrets.token_urlsafe(24)})


@router.get("/missoes/{codigo}/atividades/{item_id:int}",name="activity_detail")
def activity_detail(request: Request,codigo: str,item_id: int):
    mission = find_mission(request,codigo)
    item = item_or_404(request,mission,item_id)
    messages = {"salva":"Atividade salva no banco local.","cancelada":"Atividade cancelada. O histórico foi preservado."}
    return render(request,"activity_detail.html",title=item["titulo"],active="planejamento",mission=mission,
                  item=item,message=messages.get(request.query_params.get("aviso")))


@router.get("/missoes/{codigo}/atividades/{item_id:int}/editar",name="edit_activity")
def edit_activity(request: Request,codigo: str,item_id: int):
    mission = find_mission(request,codigo)
    item = item_or_404(request,mission,item_id)
    values = {**item,"participantes":[str(p["id"]) for p in item["participantes"]]}
    return form_page(request,mission,values,item=item)


@router.post("/missoes/{codigo}/atividades/nova")
async def create_activity(request: Request,codigo: str):
    mission = find_mission(request,codigo)
    values = await read_form(request)
    try:
        data = validate_activity(values,mission)
        key = values.get("request_key","")
        if not 20<=len(key)<=100:
            raise InvalidActivity({"form":"Reabra o formulário para obter uma identificação válida."})
        item_id = repository(request,mission).save(mission.id,data,request_key=key)
    except InvalidActivity as error:
        return failure(request,mission,values,error.errors)
    except ActivityConflict as error:
        return failure(request,mission,values,{"form":str(error)},status_code=409)
    return result(request,f"/missoes/{codigo}/atividades/{item_id}?aviso=salva","Atividade salva no banco local.")


@router.post("/missoes/{codigo}/atividades/{item_id:int}/editar")
async def update_activity(request: Request,codigo: str,item_id: int):
    mission = find_mission(request,codigo)
    item = item_or_404(request,mission,item_id)
    values = await read_form(request)
    try:
        data = validate_activity(values,mission)
        try:
            version = int(values.get("version",""))
        except ValueError:
            raise InvalidActivity({"form":"Versão inválida. Reabra os detalhes da atividade."})
        repository(request,mission).save(mission.id,data,item_id,version)
    except InvalidActivity as error:
        return failure(request,mission,values,error.errors,item)
    except ActivityConflict as error:
        return failure(request,mission,values,{"form":str(error)},item,409)
    return result(request,f"/missoes/{codigo}/atividades/{item_id}?aviso=salva","Alterações salvas no banco local.")


@router.post("/missoes/{codigo}/atividades/{item_id:int}/cancelar")
async def cancel_activity(request: Request,codigo: str,item_id: int):
    mission = find_mission(request,codigo)
    item = item_or_404(request,mission,item_id)
    values = await read_form(request)
    try:
        version = int(values.get("version",""))
        repository(request,mission).cancel(mission.id,item_id,version)
    except (ValueError,ActivityConflict) as error:
        if "application/json" in request.headers.get("accept",""):
            message = str(error) if isinstance(error,ActivityConflict) else "Versão inválida. Reabra os detalhes antes de cancelar."
            return JSONResponse({"errors":{"form":message}},status_code=409)
        response = render(request,"activity_detail.html",title=item["titulo"],active="planejamento",
                          mission=mission,item=item,message="A atividade mudou. Confira os detalhes atualizados e tente novamente.")
        response.status_code=409
        return response
    return result(request,f"/missoes/{codigo}/atividades/{item_id}?aviso=cancelada","Atividade cancelada.")
