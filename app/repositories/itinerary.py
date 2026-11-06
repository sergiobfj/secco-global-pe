"""Fonte da agenda planejada. Compromissos legados são preservados e importados uma vez."""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.db.connection import connect
from app.services.itinerary import present_item

FIELDS = ("organizacao","titulo","descricao","categoria","status","origem","data","horario_inicio","horario_fim",
          "inicio_utc","fim_utc","local","endereco","endereco_validado","observacoes","link_externo")


class ActivityConflict(ValueError):
    pass


class ItineraryRepository:
    def __init__(self,database_path):
        self.database_path = database_path

    def _hydrate(self,db,row):
        data = dict(row)
        data["participantes"] = [dict(person) for person in db.execute("""
            SELECT p.id,p.nome FROM itinerary_participants ip JOIN participants p ON p.id=ip.participant_id
            WHERE ip.item_id=? ORDER BY p.id
        """,(row["id"],))]
        return present_item(data)

    def list(self,mission_id):
        with connect(self.database_path) as db:
            return [self._hydrate(db,row) for row in db.execute("""
                SELECT * FROM itinerary_items WHERE mission_id=?
                ORDER BY data IS NULL,data,horario_inicio IS NULL,horario_inicio,id
            """,(mission_id,))]

    def get(self,mission_id,item_id):
        with connect(self.database_path) as db:
            row = db.execute("SELECT * FROM itinerary_items WHERE mission_id=? AND id=?",(mission_id,item_id)).fetchone()
            return self._hydrate(db,row) if row else None

    def save(self,mission_id,data,item_id=None,version=None,request_key=None):
        with connect(self.database_path) as db:
            # Reserva a escrita antes de conferir a versão, evitando atualizações perdidas.
            db.execute("BEGIN IMMEDIATE")
            if item_id is None and request_key:
                existing = db.execute("SELECT * FROM itinerary_items WHERE request_key=?",
                                      (request_key,)).fetchone()
                if existing:
                    people = [row[0] for row in db.execute("SELECT participant_id FROM itinerary_participants WHERE item_id=? ORDER BY participant_id",(existing["id"],))]
                    if existing["mission_id"]!=mission_id or any(existing[field]!=data[field] for field in FIELDS) or people!=data["participantes"]:
                        raise ActivityConflict("Este envio já foi salvo com outros dados. Reabra a agenda e confira o registro antes de criar outra atividade.")
                    return existing["id"]
            if item_id is not None:
                row = db.execute("SELECT version FROM itinerary_items WHERE id=? AND mission_id=?",
                                 (item_id,mission_id)).fetchone()
                if row is None:
                    raise LookupError("Atividade não encontrada")
                if row["version"]!=version:
                    raise ActivityConflict("Esta atividade foi alterada em outra aba. Seus campos foram preservados. Confira a versão atual antes de tentar novamente.")
                assignments = ",".join(field+"=?" for field in FIELDS)
                db.execute(f"""UPDATE itinerary_items SET {assignments},version=version+1,
                    updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=? AND mission_id=?""",
                           (*[data[field] for field in FIELDS],item_id,mission_id))
                db.execute("DELETE FROM itinerary_participants WHERE item_id=?",(item_id,))
                action = "edicao"
            else:
                columns = ",".join(("mission_id",*FIELDS,"request_key"))
                placeholders = ",".join("?" for _ in range(len(FIELDS)+2))
                cursor = db.execute(f"INSERT INTO itinerary_items({columns}) VALUES({placeholders})",
                                    (mission_id,*[data[field] for field in FIELDS],request_key))
                item_id,action = cursor.lastrowid,"criacao"
            for participant in data["participantes"]:
                db.execute("INSERT INTO itinerary_participants(item_id,mission_id,participant_id) VALUES(?,?,?)",
                           (item_id,mission_id,participant))
            db.execute("INSERT INTO itinerary_history(item_id,acao,snapshot) VALUES(?,?,?)",
                       (item_id,action,json.dumps(data,ensure_ascii=False)))
            return item_id

    def cancel(self,mission_id,item_id,version):
        with connect(self.database_path) as db:
            cursor = db.execute("""UPDATE itinerary_items SET status='cancelado',version=version+1,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=? AND mission_id=? AND version=?""",
                                (item_id,mission_id,version))
            if cursor.rowcount!=1:
                raise ActivityConflict("A atividade mudou. Reabra os detalhes antes de cancelar.")
            row = dict(db.execute("SELECT * FROM itinerary_items WHERE id=?",(item_id,)).fetchone())
            db.execute("INSERT INTO itinerary_history(item_id,acao,snapshot) VALUES(?,'cancelamento',?)",
                       (item_id,json.dumps(row,ensure_ascii=False)))

    def import_legacy(self,mission):
        # Os registros legados ficam intactos. A agenda usa a cópia vinculada, sem contá-los duas vezes.
        with connect(self.database_path) as db:
            for row in db.execute("""SELECT e.* FROM mission_events e WHERE e.mission_id=?
                AND NOT EXISTS(SELECT 1 FROM itinerary_items i WHERE i.legacy_event_id=e.id)""",(mission.id,)).fetchall():
                start = datetime.fromisoformat(row["inicio_utc"].replace("Z","+00:00"))
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                local = start.astimezone(ZoneInfo(mission.timezone))
                end = datetime.fromisoformat(row["fim_utc"].replace("Z","+00:00")) if row["fim_utc"] else None
                if end and end.tzinfo is None:
                    end = end.replace(tzinfo=timezone.utc)
                end_local = end.astimezone(ZoneInfo(mission.timezone)) if end else None
                db.execute("""INSERT INTO itinerary_items(mission_id,legacy_event_id,titulo,categoria,status,data,
                    horario_inicio,horario_fim,inicio_utc,fim_utc,local,observacoes)
                    VALUES(?,?,?,'institucional','a_confirmar',?,?,?,?,?,?,?)
                    ON CONFLICT(legacy_event_id) DO NOTHING""",
                    (mission.id,row["id"],row["titulo"],local.date().isoformat(),local.strftime("%H:%M"),
                     end_local.strftime("%H:%M") if end_local and end_local.date()==local.date() and end_local>local else None,
                     start.isoformat(),end.isoformat() if end else None,row["local"] or "",
                     "Migrado do registro anterior. Situação de confirmação a conferir."))
