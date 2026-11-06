from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

from app.services.missions import mission_situation

router = APIRouter(prefix="/api", tags=["Missões"])


def serialize(mission):
    data = asdict(mission)
    data["situacao"] = asdict(mission_situation(mission.data_inicio, mission.data_fim,
                                               mission.timezone, status=mission.status))
    return data


@router.get("/missoes")
def missions(request: Request):
    return [serialize(mission) for mission in request.app.state.repository.list()]


@router.get("/missoes/{codigo}")
def mission(request: Request, codigo: str):
    result = request.app.state.repository.get(codigo)
    if result is None:
        raise HTTPException(404, "Missão não encontrada")
    return serialize(result)
