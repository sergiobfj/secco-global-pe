import json
from datetime import date, datetime, timezone

from app.db.connection import connect
from app.models import Goal, Mission, Participant


class MissionRepository:
    def __init__(self, database_path):
        self.database_path = database_path

    def _hydrate(self, db, row):
        people = [Participant(**dict(p)) for p in db.execute("""
            SELECT p.id,p.nome,p.email,mp.papel,mp.financiado_pela_subvencao
            FROM participants p JOIN mission_participants mp ON mp.participant_id=p.id
            WHERE mp.mission_id=? ORDER BY mp.id
        """, (row["id"],))]
        goals = [Goal(**dict(g)) for g in db.execute("""
            SELECT g.tipo_meta,g.quantidade_alvo,COUNT(r.id) AS realizado
            FROM mission_goals g LEFT JOIN mission_results r
              ON r.mission_id=g.mission_id AND r.tipo_meta=g.tipo_meta
            WHERE g.mission_id=? GROUP BY g.id ORDER BY g.id
        """, (row["id"],))]
        fields = {k: row[k] for k in ("id","codigo","nome","pais","timezone","edital","status","observacoes")}
        return Mission(**fields, data_inicio=date.fromisoformat(row["data_inicio"]),
                       data_fim=date.fromisoformat(row["data_fim"]),
                       cidades=json.loads(row["cidades"]),
                       atividades_previstas=json.loads(row["atividades_previstas"]),
                       participantes=people, metas=goals)

    def list(self):
        with connect(self.database_path) as db:
            return [self._hydrate(db, row) for row in db.execute("SELECT * FROM missions ORDER BY data_inicio,id")]

    def get(self, codigo):
        with connect(self.database_path) as db:
            row = db.execute("SELECT * FROM missions WHERE codigo=?", (codigo,)).fetchone()
            return self._hydrate(db, row) if row else None

    def events(self, mission_id):
        with connect(self.database_path) as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM mission_events WHERE mission_id=? ORDER BY inicio_utc,id", (mission_id,)
            )]

    def tasks(self, mission_id):
        with connect(self.database_path) as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM mission_tasks WHERE mission_id=? AND concluida=0 ORDER BY id", (mission_id,)
            )]
