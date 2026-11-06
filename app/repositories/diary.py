import json
import sqlite3

from app.db.connection import connect
from app.repositories.itinerary import ActivityConflict
from app.services.diary import present_entry

ENTRY_FIELDS=("tipo","titulo","data","horario","organizacao","local","objetivo","descricao","resultados","proximos_passos","status")
EVIDENCE_FIELDS=("tipo","titulo","referencia_url","referencia_chave","status","conferido_por","nota_conferencia","conferido_em")
CLAIM_FIELDS=("tipo_meta","justificativa","criterio_referencia","evidence_id","evidence_version","validacao_status","validado_por","validado_em","entry_version")


class DiaryRepository:
    def __init__(self,database_path):
        self.database_path=database_path

    def _hydrate(self,db,row):
        item=present_entry(row)
        item["participantes"]=[dict(p) for p in db.execute("""
            SELECT p.id,p.nome FROM diary_participants dp JOIN participants p ON p.id=dp.participant_id
            WHERE dp.entry_id=? ORDER BY p.id""",(row["id"],))]
        return item

    def list(self,mission_id):
        with connect(self.database_path) as db:
            return [self._hydrate(db,r) for r in db.execute("""
                SELECT * FROM diary_entries WHERE mission_id=?
                ORDER BY data IS NULL,data DESC,id DESC""",(mission_id,))]

    def get(self,mission_id,entry_id):
        with connect(self.database_path) as db:
            row=db.execute("SELECT * FROM diary_entries WHERE mission_id=? AND id=?",(mission_id,entry_id)).fetchone()
            return self._hydrate(db,row) if row else None

    def for_itinerary(self,mission_id,item_id):
        with connect(self.database_path) as db:
            row=db.execute("SELECT id FROM diary_entries WHERE mission_id=? AND itinerary_item_id=?",(mission_id,item_id)).fetchone()
            return row["id"] if row else None

    def links(self,mission_id):
        with connect(self.database_path) as db:
            return {r["itinerary_item_id"]:dict(r) for r in db.execute("""
                SELECT id,itinerary_item_id,status FROM diary_entries WHERE mission_id=? AND itinerary_item_id IS NOT NULL""",(mission_id,))}

    def _history(self,db,entry_id,entity,entity_id,action,data):
        db.execute("INSERT INTO diary_history(entry_id,entidade,entidade_id,acao,snapshot) VALUES(?,?,?,?,?)",
                   (entry_id,entity,entity_id,action,json.dumps(data,ensure_ascii=False)))

    def save(self,mission_id,data,entry_id=None,version=None,request_key=None,itinerary_item_id=None):
        try:
            with connect(self.database_path) as db:
                db.execute("BEGIN IMMEDIATE")
                if entry_id is None:
                    existing=db.execute("SELECT * FROM diary_entries WHERE request_key=?",(request_key,)).fetchone() if request_key else None
                    if existing:
                        if existing["mission_id"]!=mission_id or any(existing[f]!=data[f] for f in ENTRY_FIELDS):
                            raise ActivityConflict("Este envio já foi salvo. Confira o registro existente antes de reenviar outros dados.")
                        people=[r[0] for r in db.execute("SELECT participant_id FROM diary_participants WHERE entry_id=? ORDER BY participant_id",(existing["id"],))]
                        if people!=data["participantes"]:
                            raise ActivityConflict("Este envio já foi salvo com outros participantes.")
                        return existing["id"]
                    if itinerary_item_id is not None:
                        linked=db.execute("SELECT id FROM diary_entries WHERE itinerary_item_id=? AND mission_id=?",
                                          (itinerary_item_id,mission_id)).fetchone()
                        if linked:
                            raise ActivityConflict("Este compromisso já possui registro no Diário. Abra o registro existente.")
                    if itinerary_item_id is not None:
                        source=db.execute("SELECT categoria FROM itinerary_items WHERE id=? AND mission_id=?",(itinerary_item_id,mission_id)).fetchone()
                        if not source or source["categoria"] not in ("institucional","evento"):
                            raise ActivityConflict("O vínculo com a agenda precisa ser profissional e pertencer à mesma missão.")
                    columns=",".join(("mission_id","itinerary_item_id",*ENTRY_FIELDS,"request_key"))
                    marks=",".join("?" for _ in range(len(ENTRY_FIELDS)+3))
                    entry_id=db.execute(f"INSERT INTO diary_entries({columns}) VALUES({marks})",
                        (mission_id,itinerary_item_id,*[data[f] for f in ENTRY_FIELDS],request_key)).lastrowid
                    action="criacao"
                else:
                    current=db.execute("SELECT * FROM diary_entries WHERE mission_id=? AND id=?",(mission_id,entry_id)).fetchone()
                    if not current: raise LookupError("Registro não encontrado")
                    if current["version"]!=version: raise ActivityConflict("O registro mudou em outra aba. Seus campos foram preservados.")
                    fields=",".join(f+"=?" for f in ENTRY_FIELDS)
                    db.execute(f"""UPDATE diary_entries SET {fields},version=version+1,
                        updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=? AND mission_id=?""",
                        (*[data[f] for f in ENTRY_FIELDS],entry_id,mission_id))
                    db.execute("DELETE FROM diary_participants WHERE entry_id=?",(entry_id,))
                    # A alteração dos fatos exige rever a classificação, sem conservar aprovação silenciosa.
                    db.execute("""UPDATE diary_goal_claims SET validacao_status='pendente',validado_por='',
                        validado_em=NULL,version=version+1,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                        WHERE entry_id=?""",(entry_id,))
                    action="edicao"
                for person in data["participantes"]:
                    db.execute("INSERT INTO diary_participants(entry_id,mission_id,participant_id) VALUES(?,?,?)",
                               (entry_id,mission_id,person))
                self._history(db,entry_id,"registro",entry_id,action,data)
                return entry_id
        except sqlite3.IntegrityError as error:
            raise ActivityConflict("O registro não pôde ser salvo. Confira o vínculo e possíveis duplicidades.") from error

    def evidence(self,mission_id,entry_id):
        with connect(self.database_path) as db:
            return [dict(r) for r in db.execute("SELECT * FROM diary_evidence WHERE mission_id=? AND entry_id=? ORDER BY id",
                                               (mission_id,entry_id))]

    def claims(self,mission_id,entry_id):
        with connect(self.database_path) as db:
            return [dict(r) for r in db.execute("""
                SELECT c.*,EXISTS(SELECT 1 FROM eligible_goal_claims v WHERE v.id=c.id) AS counted
                FROM diary_goal_claims c WHERE c.mission_id=? AND c.entry_id=? ORDER BY c.id""",(mission_id,entry_id))]

    def save_related(self,mission_id,entry_id,data,entity,entity_id=None,version=None,request_key=None,entry_version=None):
        fields=EVIDENCE_FIELDS if entity=="evidencia" else CLAIM_FIELDS
        table="diary_evidence" if entity=="evidencia" else "diary_goal_claims"
        try:
            with connect(self.database_path) as db:
                db.execute("BEGIN IMMEDIATE")
                current=db.execute("SELECT version FROM diary_entries WHERE id=? AND mission_id=?",(entry_id,mission_id)).fetchone()
                if not current: raise LookupError("Registro não encontrado")
                if entry_version is not None and current["version"]!=entry_version:
                    raise ActivityConflict("O registro mudou. Reabra os detalhes antes de classificar ou referenciar evidências.")
                if entity == "classificacao" and data["evidence_id"] is not None:
                    proof = db.execute("SELECT version FROM diary_evidence WHERE id=? AND entry_id=? AND mission_id=?",
                                       (data["evidence_id"], entry_id, mission_id)).fetchone()
                    if not proof or proof["version"] != data["evidence_version"]:
                        raise ActivityConflict("A evidência mudou. Confira a referência antes de classificar o resultado.")
                if entity_id is not None:
                    old=db.execute(f"SELECT * FROM {table} WHERE id=? AND entry_id=? AND mission_id=?",
                                   (entity_id,entry_id,mission_id)).fetchone()
                    if not old: raise LookupError("Registro não encontrado")
                    if old["version"]!=version: raise ActivityConflict("Este registro mudou em outra aba. Confira a versão atual.")
                    assignments=",".join(f+"=?" for f in fields)
                    db.execute(f"""UPDATE {table} SET {assignments},version=version+1,
                        updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?""",
                               (*[data[f] for f in fields],entity_id))
                    if entity=="evidencia":
                        db.execute("""UPDATE diary_goal_claims SET validacao_status='pendente',validado_por='',
                            validado_em=NULL,version=version+1,
                            updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE evidence_id=?""",(entity_id,))
                else:
                    if entity=="evidencia" and request_key:
                        old=db.execute("SELECT * FROM diary_evidence WHERE request_key=?",(request_key,)).fetchone()
                        if old:
                            if old["mission_id"]==mission_id and old["entry_id"]==entry_id and all(old[f]==data[f] for f in fields if f!="conferido_em"):
                                return old["id"]
                            raise ActivityConflict("Este envio já foi salvo com outros dados.")
                    columns=["entry_id","mission_id",*fields]
                    values=[entry_id,mission_id,*[data[f] for f in fields]]
                    if entity=="evidencia":
                        columns.append("request_key"); values.append(request_key)
                    marks=",".join("?" for _ in values)
                    entity_id=db.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES({marks})",values).lastrowid
                self._history(db,entry_id,entity,entity_id,"salvar",data)
                return entity_id
        except sqlite3.IntegrityError as error:
            raise ActivityConflict("Já existe esta classificação ou referência nesta missão. Confira o registro original e os vínculos.") from error

    def summary(self,mission_id):
        with connect(self.database_path) as db:
            counts={r["tipo_meta"]:r["n"] for r in db.execute("SELECT tipo_meta,COUNT(*) n FROM eligible_goal_claims WHERE mission_id=? GROUP BY tipo_meta",(mission_id,))}
            meetings=db.execute("SELECT COUNT(*) FROM diary_entries WHERE mission_id=? AND tipo='reuniao_empresarial' AND status='realizada'",(mission_id,)).fetchone()[0]
            drafts=db.execute("SELECT COUNT(*) FROM diary_entries WHERE mission_id=? AND status='rascunho'",(mission_id,)).fetchone()[0]
            pending=db.execute("SELECT COUNT(*) FROM diary_goal_claims c WHERE mission_id=? AND NOT EXISTS(SELECT 1 FROM eligible_goal_claims v WHERE v.id=c.id)",(mission_id,)).fetchone()[0]
            return {"meetings":meetings,"drafts":drafts,"pending_claims":pending,"counts":counts,
                    "recent":[self._hydrate(db,r) for r in db.execute(
                        "SELECT * FROM diary_entries WHERE mission_id=? ORDER BY updated_at DESC,id DESC LIMIT 4",
                        (mission_id,))]}
