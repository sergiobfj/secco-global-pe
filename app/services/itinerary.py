"""Validação localizada e conversão dos horários locais para UTC."""
from datetime import date, datetime, time, timezone, timedelta
from urllib.parse import urlsplit, urlencode
from zoneinfo import ZoneInfo

CATEGORIES = {"institucional":"Institucional","evento":"Evento","turismo":"Turismo",
              "alimentacao":"Alimentação","transporte":"Transporte","descanso":"Descanso"}
STATUSES = {"sugestao":"Sugestão","a_confirmar":"A confirmar","confirmado":"Confirmado",
            "realizado":"Realizado","cancelado":"Cancelado"}
ORIGINS = {"edital":"Edital","proposta_aprovada":"Proposta aprovada",
           "agenda_oficial":"Agenda oficial","sugestao_viajantes":"Sugestão dos viajantes"}
WEEKDAYS = ("segunda-feira","terça-feira","quarta-feira","quinta-feira","sexta-feira","sábado","domingo")
LIMITS = {"titulo":160,"descricao":4000,"local":200,"endereco":400,"observacoes":4000,"link_externo":2000}


class InvalidActivity(ValueError):
    def __init__(self, errors):
        self.errors = errors


def local_to_utc(day, hour, zone):
    naive = datetime.combine(date.fromisoformat(day),time.fromisoformat(hour))
    tz = ZoneInfo(zone)
    candidates = []
    for fold in (0,1):
        aware = naive.replace(tzinfo=tz,fold=fold)
        utc = aware.astimezone(timezone.utc)
        if utc.astimezone(tz).replace(tzinfo=None) == naive and utc not in candidates:
            candidates.append(utc)
    if not candidates:
        raise ValueError("Horário inexistente na mudança de fuso. Confira o horário local.")
    if len(candidates)>1:
        raise ValueError("Horário ambíguo na mudança de fuso. Registre sem horário e detalhe nas observações.")
    return candidates[0].isoformat().replace("+00:00","Z")


def validate_activity(values, mission):
    errors, data = {}, {}
    for field, maximum in LIMITS.items():
        data[field] = str(values.get(field,"")).strip()
        if len(data[field])>maximum:
            errors[field] = f"Use no máximo {maximum} caracteres."
    if not data["titulo"]:
        errors["titulo"] = "Informe o título da atividade."
    for field, choices, default in (("categoria",CATEGORIES,"institucional"),("status",STATUSES,"a_confirmar")):
        data[field] = values.get(field,default)
        if data[field] not in choices:
            errors[field] = "Selecione uma opção válida."
    data["origem"] = values.get("origem") or None
    if data["origem"] and data["origem"] not in ORIGINS:
        errors["origem"] = "Selecione uma origem válida."
    for field in ("data","horario_inicio","horario_fim"):
        data[field] = values.get(field) or None
    if data["data"]:
        try:
            parsed = date.fromisoformat(data["data"])
            if parsed.isoformat()!=data["data"] or not 2000<=parsed.year<=2100:
                raise ValueError()
        except (ValueError,TypeError):
            errors["data"] = "Informe uma data válida entre 2000 e 2100."
    for field in ("horario_inicio","horario_fim"):
        if data[field]:
            try:
                if time.fromisoformat(data[field]).strftime("%H:%M")!=data[field]:
                    raise ValueError()
            except (ValueError,TypeError):
                errors[field] = "Informe um horário válido no formato HH:MM."
    if data["horario_inicio"] and not data["data"]:
        errors["data"] = "Informe a data para definir um horário."
    if data["horario_fim"] and not data["horario_inicio"]:
        errors["horario_fim"] = "Informe o horário inicial primeiro."
    if (data["horario_inicio"] and data["horario_fim"] and data["horario_fim"]<=data["horario_inicio"]):
        errors["horario_fim"] = "O término deve ser posterior ao início, no mesmo dia."
    if data["status"] in ("confirmado","realizado") and not data["data"]:
        errors["data"] = "Atividades confirmadas ou realizadas precisam de data."
    data["endereco_validado"] = str(values.get("endereco_validado","")) in ("1","true","on")
    if data["endereco_validado"] and not data["endereco"]:
        errors["endereco"] = "Informe o endereço conferido."
    if data["link_externo"]:
        try:
            url = urlsplit(data["link_externo"])
            if (url.scheme not in ("http","https") or not url.hostname or url.username
                    or url.password or any(c.isspace() for c in data["link_externo"])):
                raise ValueError()
        except ValueError:
            errors["link_externo"] = "Use um link completo com http:// ou https://, sem credenciais."
    people = values.get("participantes",[])
    if not isinstance(people,list):
        people = [people]
    try:
        data["participantes"] = sorted(set(int(person) for person in people if person))
        if set(data["participantes"]) - {p.id for p in mission.participantes}:
            raise ValueError()
    except (TypeError,ValueError):
        errors["participantes"] = "Selecione apenas participantes desta missão."
    data["inicio_utc"] = data["fim_utc"] = None
    if not any(field in errors for field in ("data","horario_inicio","horario_fim")) and data["data"]:
        for hour,utc in (("horario_inicio","inicio_utc"),("horario_fim","fim_utc")):
            if data[hour]:
                try:
                    data[utc] = local_to_utc(data["data"],data[hour],mission.timezone)
                except ValueError as error:
                    errors[hour] = str(error)
    if errors:
        raise InvalidActivity(errors)
    return data


def present_item(item):
    result = dict(item)
    result["categoria_label"] = CATEGORIES[result["categoria"]]
    result["status_label"] = STATUSES[result["status"]]
    result["origem_label"] = ORIGINS.get(result["origem"],"Origem documental a validar")
    result["data_label"] = date.fromisoformat(result["data"]).strftime("%d/%m/%Y") if result["data"] else "Sem data definida"
    result["horario_label"] = (
        result["horario_inicio"] + (" às "+result["horario_fim"] if result["horario_fim"] else "")
        if result["horario_inicio"] else "Sem horário definido"
    )
    result["maps_url"] = ("https://www.google.com/maps/search/?"+urlencode({"api":"1","query":result["endereco"]})
                          if result["endereco_validado"] and result["endereco"] else None)
    return result


def mission_today(mission, now=None):
    return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(mission.timezone)).date()


def calendar_days(mission, selected, today):
    start,end = mission.data_inicio,mission.data_fim
    if mission.codigo=="argentina":
        start,end = start-timedelta(days=1),end+timedelta(days=1)
    days = [start+timedelta(days=offset) for offset in range((end-start).days+1)]
    if selected not in days:
        days = sorted(days+[selected])
    return [{"date":day,"weekday":WEEKDAYS[day.weekday()][:3],"today":day==today} for day in days]


def choose_day(mission, raw=None):
    today = mission_today(mission)
    if raw:
        try:
            selected = date.fromisoformat(raw)
            if not 2000<=selected.year<=2100:
                raise ValueError()
            return selected
        except ValueError:
            raise InvalidActivity({"data":"Selecione uma data válida."})
    return today if mission.data_inicio<=today<=mission.data_fim else mission.data_inicio
