"""Diário profissional e classificação de resultados, sem critérios presumidos."""
from datetime import date, datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from app.services.itinerary import InvalidActivity, local_to_utc

TYPES = {
 "reuniao_empresarial":"Reunião empresarial","visita_institucional":"Visita institucional",
 "participacao_evento":"Participação em evento","networking_profissional":"Networking profissional",
 "apresentacao_geocarbo":"Apresentação do GeoCarbo","outra_profissional":"Outra atividade profissional"}
STATUSES={"rascunho":"Rascunho","realizada":"Realizada","cancelada":"Cancelada"}
EVIDENCE_TYPES={"fotografia":"Fotografia","certificado":"Certificado","lista_presenca":"Lista de presença",
 "documento":"Documento","carta_intencao":"Carta de intenção","confirmacao_institucional":"Confirmação institucional"}
EVIDENCE_STATUSES={"pendente":"Pendente","referencia_conferida":"Referência externa conferida","invalidada":"Invalidada"}
DECISIONS={"pendente":"Pendente de validação","aprovada":"Aprovação informada","rejeitada":"Rejeitada"}
TEXT_LIMITS={"titulo":160,"organizacao":200,"local":400,"objetivo":4000,"descricao":8000,"resultados":8000,"proximos_passos":4000}


def text_fields(values,limits,errors):
    data={}
    for field,limit in limits.items():
        data[field]=str(values.get(field,"")).strip()
        if len(data[field])>limit:
            errors[field]=f"Use no máximo {limit} caracteres."
    return data


def validate_entry(values,mission):
    errors={}
    data=text_fields(values,TEXT_LIMITS,errors)
    data["tipo"]=values.get("tipo","outra_profissional")
    data["status"]=values.get("status","rascunho")
    if data["tipo"] not in TYPES: errors["tipo"]="Selecione um tipo válido."
    if data["status"] not in STATUSES: errors["status"]="Selecione um status válido."
    data["data"]=values.get("data") or None
    data["horario"]=values.get("horario") or None
    if data["data"]:
        try:
            parsed=date.fromisoformat(data["data"])
            if parsed.isoformat()!=data["data"] or not 2000<=parsed.year<=2100: raise ValueError()
        except (ValueError,TypeError):
            errors["data"]="Informe uma data válida."
    if data["horario"]:
        if not data["data"]:
            errors["data"]="Informe a data antes do horário."
        elif "data" not in errors:
            try:
                if len(data["horario"])!=5: raise ValueError()
                local_to_utc(data["data"],data["horario"],mission.timezone)
            except ValueError:
                errors["horario"]="Confira o horário local. Horários inválidos ou ambíguos não são aceitos."
    people=values.get("participantes",[])
    if not isinstance(people,list): people=[people]
    try:
        data["participantes"]=sorted(set(int(p) for p in people if p))
        if set(data["participantes"])-{p.id for p in mission.participantes}: raise ValueError()
    except (ValueError,TypeError):
        errors["participantes"]="Selecione apenas participantes desta missão."
    if data["status"]=="realizada":
        for field,label in (("titulo","título"),("data","data"),("descricao","o que aconteceu"),("resultados","os resultados obtidos")):
            if not data[field]: errors[field]=f"Informe {label} para concluir como realizada."
    if errors: raise InvalidActivity(errors)
    return data


def prefill_from_itinerary(item):
    if item["categoria"] not in ("institucional","evento"):
        raise InvalidActivity({"form":"Este compromisso não possui categoria profissional para registro direto no Diário."})
    known={"argentina:institucional-0":"SECOM / Embaixada do Brasil","argentina:institucional-1":"InvestBA","argentina:institucional-2":"Parque de Innovación"}
    organization=item.get("organizacao","") or (known.get(item.get("seed_key"),"") if known.get(item.get("seed_key"))==item["titulo"] else "")
    return {"itinerary_item_id":item["id"],"tipo":"participacao_evento" if item["categoria"]=="evento" else "outra_profissional",
        "titulo":item["titulo"],"data":item["data"],"horario":item["horario_inicio"],
        "organizacao":organization,"local":item["local"],
        "objetivo":item["descricao"],"descricao":"","resultados":"","proximos_passos":"",
        "status":"rascunho","participantes":[str(p["id"]) for p in item["participantes"]]}


def validate_evidence(values):
    errors={}
    data=text_fields(values,{"titulo":200,"referencia_url":2000,"referencia_chave":400,
                             "conferido_por":160,"nota_conferencia":4000},errors)
    data["tipo"]=values.get("tipo","documento")
    data["status"]=values.get("status","pendente")
    if data["tipo"] not in EVIDENCE_TYPES: errors["tipo"]="Selecione um tipo de evidência válido."
    if data["status"] not in EVIDENCE_STATUSES: errors["status"]="Selecione um status válido."
    if not data["titulo"]: errors["titulo"]="Informe um título para a evidência."
    if data["referencia_url"]:
        try:
            url=urlsplit(data["referencia_url"])
            if url.scheme!="https" or not url.hostname or url.username or url.password or any(c.isspace() for c in data["referencia_url"]):
                raise ValueError()
            data["referencia_url"]=urlunsplit(("https",url.netloc.lower(),url.path,url.query,""))
        except ValueError:
            errors["referencia_url"]="Use uma referência HTTPS completa, sem credenciais."
    data["conferido_em"]=None
    if data["status"]=="referencia_conferida":
        for field in ("referencia_url","referencia_chave","conferido_por","nota_conferencia"):
            if not data[field]: errors[field]="Obrigatório para informar uma referência conferida."
        data["conferido_em"]=datetime.now(timezone.utc).isoformat()
    if errors: raise InvalidActivity(errors)
    return data


def validate_claim(values,mission,entry,evidence):
    errors={}
    data=text_fields(values,{"justificativa":4000,"criterio_referencia":4000,"validado_por":160},errors)
    data["tipo_meta"]=values.get("tipo_meta","")
    if data["tipo_meta"] not in {goal.tipo_meta for goal in mission.metas}:
        errors["tipo_meta"]="Selecione uma meta desta missão."
    data["validacao_status"]=values.get("validacao_status","pendente")
    if data["validacao_status"] not in DECISIONS:
        errors["validacao_status"]="Selecione uma decisão válida."
    data["evidence_id"]=None
    if values.get("evidence_id"):
        try:
            data["evidence_id"]=int(values["evidence_id"])
            if not any(e["id"]==data["evidence_id"] for e in evidence): raise ValueError()
        except (ValueError,TypeError):
            errors["evidence_id"]="Selecione uma evidência vinculada a este registro."
    selected = next((e for e in evidence if e["id"] == data["evidence_id"]), None)
    data["evidence_version"] = selected["version"] if selected else None
    data["entry_version"]=entry["version"]
    data["validado_em"]=None
    if data["validacao_status"]=="aprovada":
        if entry["status"]!="realizada": errors["validacao_status"]="Somente registros realizados podem receber aprovação."
        if data["tipo_meta"]=="reuniao_qualificada" and entry["tipo"]!="reuniao_empresarial":
            errors["tipo_meta"]="Classifique o registro como Reunião empresarial antes de validar esta meta."
        for field in ("justificativa","criterio_referencia","validado_por"):
            if not data[field]: errors[field]="Obrigatório para informar uma aprovação."
        selected=next((e for e in evidence if e["id"]==data["evidence_id"]),None)
        if not selected or selected["status"]!="referencia_conferida":
            errors["evidence_id"]="A aprovação exige uma referência externa conferida."
        elif data["tipo_meta"]=="loi" and selected["tipo"]!="carta_intencao":
            errors["evidence_id"]="Uma LOI precisa da carta de intenção correspondente."
        elif data["tipo_meta"]=="manifestacao_interesse" and selected["tipo"] not in ("documento","carta_intencao","confirmacao_institucional"):
            errors["evidence_id"]="Selecione a comprovação formal correspondente."
        data["validado_em"]=datetime.now(timezone.utc).isoformat()
    if errors: raise InvalidActivity(errors)
    return data


def present_entry(item):
    result=dict(item)
    result["titulo_label"]=result["titulo"] or "Rascunho sem título"
    result["tipo_label"]=TYPES[result["tipo"]]
    result["status_label"]=STATUSES[result["status"]]
    result["data_label"]=date.fromisoformat(result["data"]).strftime("%d/%m/%Y") if result["data"] else "Data a completar"
    result["horario_label"]=result["horario"] or "Horário não informado"
    return result
