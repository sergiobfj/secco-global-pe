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
