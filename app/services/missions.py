from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class MissionSituation:
    codigo: str
    mensagem: str
    dias: int | None


def mission_situation(start: date, end: date, tz: str, now: datetime | None = None, status="planejada"):
    if start > end:
        raise ValueError("Período da missão inválido")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("O instante de referência deve conter fuso horário")
    today = current.astimezone(ZoneInfo(tz)).date()
    if status == "cancelada":
        return MissionSituation("cancelada", "Missão cancelada", None)
    if today < start:
        days = (start - today).days
        return MissionSituation("planejada", f"Falta {days} dia" if days == 1 else f"Faltam {days} dias", days)
    if today <= end:
        return MissionSituation("em_andamento", "Missão em andamento", None)
    return MissionSituation("concluida", "Missão concluída", None)


def dashboard_data(repository, mission, now=None):
    current = now or datetime.now(timezone.utc)
    zone = ZoneInfo(mission.timezone)
    local_now = current.astimezone(zone)
    events = []
    for record in repository.events(mission.id):
        start = datetime.fromisoformat(record["inicio_utc"].replace("Z", "+00:00"))
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(record["fim_utc"].replace("Z", "+00:00")) if record["fim_utc"] else None
        if end is not None and end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        events.append({**record, "inicio": start.astimezone(zone), "fim": end})
    upcoming = next((event for event in events if event["inicio"] >= local_now
                     or (event["fim"] and event["fim"] >= current)), None)
    return {
        "situation": mission_situation(mission.data_inicio, mission.data_fim, mission.timezone, current, mission.status),
        "today": local_now.date(),
        "today_events": [event for event in events if event["inicio"].date() == local_now.date()],
        "next_event": upcoming,
        "tasks": repository.tasks(mission.id),
    }

def operational_dashboard(repository, itinerary, mission, now=None, *, sync_legacy=True):
    """Visão Hoje: programação primeiro, sem promover previsões a confirmações."""
    current = now or datetime.now(timezone.utc)
    context = dashboard_data(repository,mission,current)
    if sync_legacy:
        itinerary.import_legacy(mission)
    items = itinerary.list(mission.id)
    today = context["today"]
    from app.services.itinerary import WEEKDAYS
    def upcoming(item):
        if item["status"]!="confirmado" or not item["data"] or item["data"]<today.isoformat():
            return False
        if not item["inicio_utc"]:
            return True
        start = datetime.fromisoformat(item["inicio_utc"].replace("Z","+00:00"))
        end = datetime.fromisoformat(item["fim_utc"].replace("Z","+00:00")) if item["fim_utc"] else None
        return start>=current or bool(end and end>=current)
    context.update(
        weekday=WEEKDAYS[today.weekday()],
        today_events=[item for item in items if item["data"]==today.isoformat()],
        next_event=next((item for item in items if upcoming(item)),None),
        undated_count=sum(item["data"] is None and item["status"]!="cancelado" for item in items),
    )
    return context
