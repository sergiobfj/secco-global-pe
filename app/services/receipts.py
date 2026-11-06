"""Metadados e orientação provisória. Nenhuma decisão de elegibilidade financeira."""
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from app.services.itinerary import InvalidActivity

RULES_PATH = Path(__file__).with_name("receipt_rules.json")
STATUSES = {"rascunho":"Rascunho", "pendente_comprovante":"Pendente de comprovante",
 "pendente_revisao":"Pendente de revisão", "pronto_revisao":"Pronto para revisão",
 "validado_manualmente":"Validado manualmente"}
CURRENCIES = ("EUR", "ARS", "BRL", "USD")


def load_rules():
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    if not isinstance(rules.get("revision"), int) or rules["revision"]<1:
        raise RuntimeError("Revisão de checklist inválida.")
    return rules


def validate_expense(values, mission, participant_id, rules):
    errors = {}
    data = {key:str(values.get(key, "")).strip() for key in ("tipo","rubrica","data","moeda","descricao")}
    data["participant_id"] = participant_id
    if str(values.get("participant_id", "")) != str(participant_id):
        errors["participant_id"] = "O registro deve identificar o participante da sessão autenticada."
    if participant_id not in {p.id for p in mission.participantes}:
        errors["participant_id"] = "O participante precisa estar vinculado a esta missão."
    if data["tipo"] not in rules["types"]: errors["tipo"] = "Selecione um tipo de despesa."
    if data["moeda"] not in CURRENCIES: errors["moeda"] = "Selecione uma moeda disponível."
    for key,limit in (("rubrica",120),("descricao",1200)):
        if len(data[key])>limit: errors[key] = f"Use no máximo {limit} caracteres."
    if data["data"]:
        try:
            parsed=date.fromisoformat(data["data"])
            if parsed.isoformat()!=data["data"] or not 2000<=parsed.year<=2100: raise ValueError()
        except (ValueError,TypeError): errors["data"]="Informe uma data válida."
    data["data"]=data["data"] or None
    raw=str(values.get("valor", "")).strip()
    data["valor_centavos"] = None
    if raw:
        try:
            if not re.fullmatch(r"[0-9]{1,10}(?:[.,][0-9]{1,2})?",raw): raise ValueError()
            amount=Decimal(raw.replace(",","."))*100
            if not 0<amount<=999999999999: raise ValueError()
            data["valor_centavos"]=int(amount)
        except (ValueError,InvalidOperation): errors["valor"]="Informe um valor positivo com até duas casas decimais, sem separador de milhar."
    intent=values.get("intent","rascunho")
    if intent not in ("rascunho","revisao"): errors["intent"]="Selecione salvar rascunho ou preparar revisão."
    definition=rules["types"].get(data["tipo"],{})
    data["complemento"]={}
    for key,label in definition.get("fields",{}).items():
        value=str(values.get("extra_"+key, "")).strip()
        if len(value)>400: errors["extra_"+key]="Use no máximo 400 caracteres."
        if intent=="revisao" and not value: errors["extra_"+key]=f"Informe {label.lower()}."
        if key=="horario" and value and not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]",value): errors["extra_horario"]="Informe um horário válido."
        data["complemento"][key]=value
    data["answers"]={}
    for i,_ in enumerate(definition.get("items",[])):
        data["answers"][str(i)] = values.get("check_"+str(i))=="on"
    for i,_ in enumerate(definition.get("conditional",[])):
        answer=values.get("conditional_"+str(i),"pendente")
        if answer not in ("pendente","anexado","nao_exigido"): errors["checklist"]="Confira o checklist condicional."
        data["answers"]["conditional_"+str(i)]=answer
    if intent=="revisao":
        for key,label in (("rubrica","a rubrica conforme o termo aplicável"),("data","a data da despesa"),("valor_centavos","o valor"),("descricao","uma descrição")):
            if not data[key]: errors[key] = "Informe "+label+" para preparar a revisão."
    if values.get("synthetic_ack")!="on": errors["synthetic_ack"]="Confirme que está usando exclusivamente dados e comprovantes sintéticos."
    if errors: raise InvalidActivity(errors)
    data["intent"]=intent
    data["checklist_definition"]=definition
    data["revision"]=rules["revision"]
    return data


def derive_status(data, received):
    if data["intent"]=="rascunho": return "rascunho"
    if not received: return "pendente_comprovante"
    answers=data["answers"]
    complete=all(v is True or v in ("anexado","nao_exigido") for v in answers.values())
    # Estes tipos aguardam regra documental específica, mesmo com anexos.
    if not complete or data["tipo"] in ("taxi","urbano","outro"): return "pendente_revisao"
    return "pronto_revisao"


def safe_component(value):
    normalized=unicodedata.normalize("NFKD",str(value)).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+","-",normalized).strip("-")[:80]


def official_filename(processo, mission, data, person, attachment_id, extension):
    required=(processo,mission.codigo,data.get("data"),data.get("rubrica"),data.get("tipo"),data.get("valor_centavos"),data.get("moeda"),person)
    if any(not part for part in required): return None
    components=[safe_component(v) for v in (processo,mission.codigo,data["data"],data["rubrica"],data["tipo"])]
    if not all(components): return None
    components.extend([f'{data["valor_centavos"]//100}.{data["valor_centavos"]%100:02d}'+data["moeda"],safe_component(person),attachment_id])
    if not components[-2]: return None
    return "_".join(components)+"."+extension


def payload_hash(data, files):
    body={**data,"files":sorted(hashlib.sha256(f["content"]).hexdigest() for f in files)}
    return hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
