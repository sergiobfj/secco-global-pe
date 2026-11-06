"""Carga inicial idempotente. Preserva alterações feitas após o primeiro uso."""
import json
from pathlib import Path

from app.db.connection import connect
from app.db.seed_itinerary import seed_itinerary

MISSIONS = (
    {
        "codigo": "portugal", "nome": "Missão Portugal", "pais": "Portugal",
        "data_inicio": "2026-11-09", "data_fim": "2026-11-20",
        "timezone": "Europe/Lisbon", "edital": "26/2026",
        "cidades": ["Lisboa", "Aveiro", "Porto"],
        "atividades": ["Bootcamp na NOVA SBE", "Web Summit", "Aveiro Tech Week", "Portus Park", "UPTEC"],
        "observacoes": None,
        "participantes": [("Hugo Mendes", True), ("Alan Renato", False)],
        "metas": [("reuniao_qualificada", 10), ("loi", 3)],
    },
    {
        "codigo": "argentina", "nome": "Missão Argentina", "pais": "Argentina",
        "data_inicio": "2026-11-16", "data_fim": "2026-11-23",
        "timezone": "America/Argentina/Buenos_Aires", "edital": "29/2026",
        "cidades": ["Buenos Aires"],
        "atividades": ["1º Simpósio Iberoamericano de Inovação, Ciência e Tecnologia, previsto para 18 e 19/11"],
        "observacoes": None,
        "participantes": [("Tiago Prado", False), ("Bruno de Castro", True)],
        "metas": [("reuniao_qualificada", 8), ("manifestacao_interesse", 3)],
    },
)


def seed(database_path: Path):
    with connect(database_path) as db:
        for mission in MISSIONS:
            db.execute("""
                INSERT INTO missions(codigo,nome,pais,data_inicio,data_fim,timezone,edital,cidades,atividades_previstas,observacoes)
                VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(codigo) DO NOTHING
            """, (mission["codigo"], mission["nome"], mission["pais"], mission["data_inicio"],
                  mission["data_fim"], mission["timezone"], mission["edital"],
                  json.dumps(mission["cidades"], ensure_ascii=False),
                  json.dumps(mission["atividades"], ensure_ascii=False), mission["observacoes"]))
            mission_id = db.execute("SELECT id FROM missions WHERE codigo=?", (mission["codigo"],)).fetchone()["id"]
            for nome, funded in mission["participantes"]:
                db.execute("INSERT INTO participants(nome) VALUES (?) ON CONFLICT(nome) DO NOTHING", (nome,))
                participant_id = db.execute("SELECT id FROM participants WHERE nome=?", (nome,)).fetchone()["id"]
                db.execute("""
                    INSERT INTO mission_participants(mission_id,participant_id,papel,financiado_pela_subvencao)
                    VALUES (?,?,'Participante',?) ON CONFLICT(mission_id,participant_id) DO NOTHING
                """, (mission_id, participant_id, funded))
            for kind, target in mission["metas"]:
                db.execute("""
                    INSERT INTO mission_goals(mission_id,tipo_meta,quantidade_alvo)
                    VALUES (?,?,?) ON CONFLICT(mission_id,tipo_meta) DO NOTHING
                """, (mission_id, kind, target))

    seed_itinerary(database_path)
