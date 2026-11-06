from app.core.auth import can_edit
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from app.core.forms import COOKIE, csrf_token
from app.services.itinerary import mission_today, WEEKDAYS
from fastapi.templating import Jinja2Templates

from app.core.config import ROOT
from app.services.missions import mission_situation, operational_dashboard

router = APIRouter()
templates = Jinja2Templates(directory=ROOT / "app" / "templates")
SECTIONS = {
    "planejamento": ("Planejamento", "Rotas, agendas institucionais e mobilidade em um só lugar."),
    "diario": ("Diário de Atividades", "Um registro organizado das experiências e resultados de cada missão."),
    "prestacao-de-contas": ("Prestação de Contas", "Acompanhamento financeiro e organização da prestação de contas."),
    "organizacao": ("Organização", "Documentos e informações essenciais para cada etapa da viagem."),
    "documentos": ("Documentos", "Os documentos da missão terão seu espaço aqui."),
}


def render(request, template, **context):
    token = csrf_token(request)
    user = getattr(request.state,"user",None)
    mission = context.get("mission")
    auth_available = hasattr(request.app.state,"auth")
    response = templates.TemplateResponse(request=request, name=template, context={
        "csrf_token": token, "features_diary": True,
        "features_receipts": True,
        "receipts_enabled": request.app.state.settings.receipts_synthetic_enabled,
        "features_auth": True, "current_user": user,
        "dev_access": request.app.state.settings.dev_no_auth,
        "can_edit": can_edit(request,mission.id) if mission else request.app.state.settings.dev_no_auth,
        "author_names": request.app.state.auth.author_names() if auth_available else {},
        "active": "inicio", "mission": None, **context
    })
    response.set_cookie(COOKIE,token,httponly=True,samesite="strict",secure=request.app.state.settings.secure_cookies,path="/")
    selected = context.get("mission")
    if selected and not user:
        response.set_cookie("secco_mission",selected.codigo,max_age=31536000,httponly=True,samesite="lax",secure=request.app.state.settings.secure_cookies,path="/")
    return response


def find_mission(request, codigo):
    mission = request.app.state.repository.get(codigo)
    if not mission:
        raise HTTPException(404, "Missão não encontrada")
    return mission


@router.get("/", response_class=HTMLResponse, name="home")
def home(request: Request):
    user = getattr(request.state,"user",None)
    if user and user.get("is_coordinator"):
        return RedirectResponse("/consolidado",status_code=303)
    preferred = user["default_mission_code"] if user else request.cookies.get("secco_mission")
    if not request.query_params.get("selecionar") and preferred in ("portugal","argentina"):
        return RedirectResponse(f"/missoes/{preferred}",status_code=303)
    missions = request.app.state.repository.list()
    situations = {m.codigo: mission_situation(m.data_inicio,m.data_fim,m.timezone,status=m.status) for m in missions}
    return render(request, "home.html", missions=missions, situations=situations, title="Início")


@router.get("/missoes/{codigo}", response_class=HTMLResponse, name="dashboard")
def dashboard(request: Request, codigo: str):
    mission = find_mission(request, codigo)
    context = operational_dashboard(request.app.state.repository,request.app.state.itinerary,mission,
        sync_legacy=not bool(getattr(request.state,"user",None) and request.state.user.get("is_coordinator")))
    context["diary_summary"]=request.app.state.diary.summary(mission.id)
    context["diary_links"]=request.app.state.diary.links(mission.id)
    response = render(request,"dashboard.html",mission=mission,title=mission.nome,**context)
    return response


@router.get("/secoes/{section}", response_class=HTMLResponse, name="section")
@router.get("/missoes/{codigo}/secoes/{section}", response_class=HTMLResponse, name="mission_section")
def section_page(request: Request, section: str, codigo: str | None = None):
    if section not in SECTIONS:
        raise HTTPException(404, "Página não encontrada")
    if section == "prestacao-de-contas" and request.app.state.settings.receipts_synthetic_enabled:
        user = getattr(request.state,"user",None)
        preferred = codigo or (user["default_mission_code"] if user else None)
        if preferred:
            return RedirectResponse(f"/missoes/{preferred}/comprovantes",status_code=303)
    if section == "diario":
        if codigo:
            from app.routers.diary import diary
            return diary(request,codigo)
        preferred=request.cookies.get("secco_mission")
        if preferred in ("portugal","argentina"):
            from app.routers.diary import diary
            return diary(request,preferred)
        return home(request)
    if section == "planejamento":
        if codigo:
            from app.routers.planning import planning
            return planning(request,codigo)
        preferred=request.cookies.get("secco_mission")
        if preferred in ("portugal","argentina"):
            return RedirectResponse(f"/missoes/{preferred}/planejamento",status_code=303)
        return home(request)
    title, description = SECTIONS[section]
    mission = find_mission(request, codigo) if codigo else None
    return render(request, "placeholder.html", mission=mission, title=title,
                  description=description, active="organizacao" if section=="documentos" else section)


@router.get('/consolidado',response_class=HTMLResponse,name='consolidated')
def consolidated(request: Request):
    user=getattr(request.state,'user',None)
    if not user: raise HTTPException(401,'Entre com sua conta autorizada.')
    missions=request.app.state.repository.list()
    rows=[]
    for mission in missions:
        context=operational_dashboard(request.app.state.repository,request.app.state.itinerary,mission,sync_legacy=False)
        rows.append({'mission':mission,**context,'summary':request.app.state.diary.summary(mission.id)})
    return render(request,'consolidated.html',title='Visão consolidada',overview=rows)
