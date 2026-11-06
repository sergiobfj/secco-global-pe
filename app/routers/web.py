from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.config import ROOT
from app.services.missions import dashboard_data, mission_situation

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
    return templates.TemplateResponse(request=request, name=template, context={
        "active": "inicio", "mission": None, **context
    })


def find_mission(request, codigo):
    mission = request.app.state.repository.get(codigo)
    if not mission:
        raise HTTPException(404, "Missão não encontrada")
    return mission


@router.get("/", response_class=HTMLResponse, name="home")
def home(request: Request):
    missions = request.app.state.repository.list()
    situations = {m.codigo: mission_situation(m.data_inicio,m.data_fim,m.timezone,status=m.status) for m in missions}
    return render(request, "home.html", missions=missions, situations=situations, title="Início")


@router.get("/missoes/{codigo}", response_class=HTMLResponse, name="dashboard")
def dashboard(request: Request, codigo: str):
    mission = find_mission(request, codigo)
    return render(request, "dashboard.html", mission=mission, title=mission.nome,
                  **dashboard_data(request.app.state.repository, mission))


@router.get("/secoes/{section}", response_class=HTMLResponse, name="section")
@router.get("/missoes/{codigo}/secoes/{section}", response_class=HTMLResponse, name="mission_section")
def section_page(request: Request, section: str, codigo: str | None = None):
    if section not in SECTIONS:
        raise HTTPException(404, "Página não encontrada")
    title, description = SECTIONS[section]
    mission = find_mission(request, codigo) if codigo else None
    return render(request, "placeholder.html", mission=mission, title=title,
                  description=description, active="organizacao" if section=="documentos" else section)
