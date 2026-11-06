"""Despesa sintética, autoria e arquivos com compensação em falha transacional."""
import json
import secrets
import sqlite3
from contextlib import suppress
from app.db.connection import connect
from app.repositories.itinerary import ActivityConflict
from app.services.receipts import derive_status, official_filename, payload_hash

FIELDS=("participant_id","tipo","rubrica","data","valor_centavos","moeda","descricao")


class ReceiptRepository:
    def __init__(self,database_path,storage):
        self.database_path=database_path
        self.storage=storage

    def _attachments(self,db,expense_id):
        return [dict(r) for r in db.execute('''SELECT a.*,o.volume_id,o.object_key,o.local_state,o.sync_state,
            o.delete_requested_by FROM expense_attachments a LEFT JOIN receipt_local_objects o ON o.attachment_id=a.id
            WHERE a.expense_id=? ORDER BY a.created_at,a.id''',(expense_id,))]

    def _hydrate(self,db,row):
        item=dict(row)
        item['complemento']=json.loads(item['complemento'])
        checklist=db.execute('SELECT * FROM expense_checklists WHERE expense_id=?',(item['id'],)).fetchone()
        item['checklist']=dict(checklist)
        for key in ('definition','answers'): item['checklist'][key]=json.loads(item['checklist'][key])
        item['attachments']=self._attachments(db,item['id'])
        item['persistent_storage']=self.storage.persistent
        for attachment in item['attachments']:
            attachment['available']=self.storage.available(attachment)
            state=attachment.get('local_state')
            attachment['storage_label']=('Excluído localmente' if state=='excluido' else 'Exclusão pendente' if state=='exclusao_pendente'
                else 'Armazenado localmente' if state=='armazenado' and attachment['available'] else 'Erro de armazenamento' if state
                else 'Arquivo recebido temporariamente' if attachment['available'] else 'Erro de armazenamento')
        active=[a for a in item['attachments'] if a.get('local_state')!='excluido']
        item['effective_status']=item['status']
        if item['status']!='rascunho' and not any(a['available'] for a in active): item['effective_status']='pendente_comprovante'
        elif item['status']=='pronto_revisao' and any(not a['available'] for a in active): item['effective_status']='pendente_revisao'
        item['participant']=dict(db.execute('SELECT p.nome,mp.financiado_pela_subvencao FROM participants p JOIN mission_participants mp ON mp.participant_id=p.id WHERE mp.mission_id=? AND p.id=?',(item['mission_id'],item['participant_id'])).fetchone())
        return item

    def list(self,mission_id,user_id):
        with connect(self.database_path) as db:
            return [self._hydrate(db,r) for r in db.execute('SELECT * FROM expenses WHERE mission_id=? AND created_by_user_id=? ORDER BY created_at DESC,id DESC',(mission_id,user_id))]

    def get(self,mission_id,expense_id,user_id):
        with connect(self.database_path) as db:
            row=db.execute('SELECT * FROM expenses WHERE mission_id=? AND id=? AND created_by_user_id=?',(mission_id,expense_id,user_id)).fetchone()
            return self._hydrate(db,row) if row else None

    def history(self,expense_id,user_id):
        with connect(self.database_path) as db:
            return [dict(r) for r in db.execute('SELECT h.* FROM expense_history h JOIN expenses e ON e.id=h.expense_id WHERE e.id=? AND e.created_by_user_id=? ORDER BY h.id DESC',(expense_id,user_id))]

    def save(self,mission,data,files,actor_user_id,request_key,expense_id=None,version=None):
        digest=payload_hash(data,files)
        written=[]
        committed=False
        try:
            with connect(self.database_path) as db:
                db.execute('BEGIN IMMEDIATE')
                user=db.execute('SELECT * FROM app_users WHERE id=? AND enabled=1',(actor_user_id,)).fetchone()
                if not user or user['participant_id']!=data['participant_id']:
                    raise ActivityConflict('O participante precisa corresponder à sessão autenticada.')
                member=db.execute('SELECT p.nome FROM participants p JOIN mission_participants mp ON mp.participant_id=p.id WHERE p.id=? AND mp.mission_id=?',(data['participant_id'],mission.id)).fetchone()
                if not member: raise ActivityConflict('O participante não pertence a esta missão.')
                submitted=db.execute('SELECT * FROM expense_submissions WHERE request_key=?',(request_key,)).fetchone()
                if submitted:
                    old=db.execute('SELECT * FROM expenses WHERE id=?',(submitted['expense_id'],)).fetchone()
                    if submitted['actor_user_id']!=actor_user_id or old['mission_id']!=mission.id or submitted['payload_hash']!=digest or expense_id and expense_id!=old['id']:
                        raise ActivityConflict('Este envio já foi salvo com outros dados. Abra o registro existente.')
                    return old['id']
                if expense_id:
                    old=db.execute('SELECT * FROM expenses WHERE id=? AND mission_id=? AND created_by_user_id=?',(expense_id,mission.id,actor_user_id)).fetchone()
                    if not old: raise LookupError('Registro não encontrado.')
                    if old['version']!=version: raise ActivityConflict('Este registro mudou em outra aba. Seus campos foram preservados. Confira a versão atual antes de reenviar.')
                    assignments=','.join(f+'=?' for f in FIELDS)
                    db.execute(f"UPDATE expenses SET {assignments},complemento=?,payload_hash=?,updated_by_user_id=?,version=version+1,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",(*[data[f] for f in FIELDS],json.dumps(data['complemento']),digest,actor_user_id,expense_id))
                    action='edicao'
                else:
                    columns=['mission_id',*FIELDS,'complemento','status','created_by_user_id','updated_by_user_id','request_key','payload_hash']
                    values=[mission.id,*[data[f] for f in FIELDS],json.dumps(data['complemento']),'rascunho',actor_user_id,actor_user_id,request_key,digest]
                    expense_id=db.execute(f"INSERT INTO expenses({','.join(columns)}) VALUES({','.join('?' for _ in values)})",values).lastrowid
                    action='criacao'
                existing=self._attachments(db,expense_id)
                newchecks={f['checksum']:f for f in files}
                added=[f for checksum,f in newchecks.items() if checksum not in {a['checksum'] for a in existing if a.get('local_state')!='excluido'}]
                active_existing=[a for a in existing if a.get('local_state')!='excluido']
                if len(active_existing)+len(added)>8 or sum(a['size_bytes'] for a in active_existing)+sum(f['size_bytes'] for f in added)>20*1024*1024:
                    raise ActivityConflict('Cada registro aceita até 8 anexos e 20 MB no total.')
                failed=False
                for checksum,file in newchecks.items():
                    previous=next((a for a in existing if a['checksum']==checksum),None)
                    if previous and self.storage.available(previous): continue
                    identifier=previous['id'] if previous else secrets.token_hex(16)
                    state='recebido_temporario'
                    if self.storage.persistent:
                        # O objeto aleatório novo nunca sobrescreve uma referência anterior.
                        obj=self.storage.allocate(identifier,mission.id,expense_id,file)
                        try:
                            self.storage.put(obj,file['content']); written.append(obj)
                        except OSError:
                            state='falha'; failed=True
                    else:
                        try:
                            self.storage.put(identifier,file['content']); written.append(identifier)
                            if self.storage.read(identifier,checksum)!=file['content']: raise OSError('Arquivo não conferido.')
                        except OSError:
                            state='falha'; failed=True
                            with suppress(OSError): self.storage.remove(identifier)
                    if previous:
                        db.execute('UPDATE expense_attachments SET storage_status=?,storage_session=? WHERE id=?',(state,self.storage.session,identifier))
                    else:
                        db.execute('INSERT INTO expense_attachments(id,expense_id,mission_id,original_name,extension,mime,size_bytes,checksum,storage_session,storage_status,name_status) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                            (identifier,expense_id,mission.id,file['name'],file['extension'],file['mime'],file['size_bytes'],checksum,self.storage.session,state,'pendente'))
                    if self.storage.persistent:
                        local_state='armazenado' if state!='falha' else 'erro'
                        db.execute('''INSERT INTO receipt_local_objects(attachment_id,volume_id,object_key,local_state) VALUES(?,?,?,?)
                            ON CONFLICT(attachment_id) DO UPDATE SET volume_id=excluded.volume_id,object_key=excluded.object_key,
                            local_state=excluded.local_state,sync_state='pendente',delete_requested_by=NULL,deleted_at=NULL,
                            updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')''',(identifier,self.storage.session,obj.object_key,local_state))
                        db.execute("INSERT INTO receipt_storage_events(attachment_id,object_key,actor_user_id,action,source) VALUES(?,?,?,?,'usuario')",(identifier,obj.object_key,actor_user_id,local_state))
                process=db.execute('SELECT processo FROM receipt_mission_config WHERE mission_id=?',(mission.id,)).fetchone()
                for attachment in db.execute('SELECT * FROM expense_attachments WHERE expense_id=?',(expense_id,)).fetchall():
                    filename=official_filename(process['processo'] if process else None,mission,data,member['nome'],attachment['id'],attachment['extension'])
                    db.execute('UPDATE expense_attachments SET official_name=?,name_status=? WHERE id=?',(filename,'preparado' if filename else 'pendente',attachment['id']))
                allfiles=[a for a in self._attachments(db,expense_id) if a.get('local_state')!='excluido']
                received=any(self.storage.available(a) for a in allfiles)
                status=derive_status(data,received)
                if status=='pronto_revisao' and any(not self.storage.available(a) for a in allfiles): status='pendente_revisao'
                db.execute('UPDATE expenses SET status=? WHERE id=?',(status,expense_id))
                db.execute('INSERT INTO expense_checklists(expense_id,revision,definition,answers) VALUES(?,?,?,?) ON CONFLICT(expense_id) DO UPDATE SET revision=excluded.revision,definition=excluded.definition,answers=excluded.answers',
                    (expense_id,data['revision'],json.dumps(data['checklist_definition'],ensure_ascii=False),json.dumps(data['answers'])))
                snapshot={k:v for k,v in data.items() if k not in ('checklist_definition',)}
                snapshot.update(status=status,storage_failure=failed,attachments=[{'id':a['id'],'checksum':a['checksum'],'storage_status':a['storage_status']} for a in allfiles])
                db.execute('INSERT INTO expense_history(expense_id,actor_user_id,acao,snapshot) VALUES(?,?,?,?)',(expense_id,actor_user_id,action,json.dumps(snapshot,ensure_ascii=False)))
                db.execute('INSERT INTO expense_submissions(request_key,expense_id,actor_user_id,payload_hash) VALUES(?,?,?,?)',(request_key,expense_id,actor_user_id,digest))
            committed=True
            if self.storage.persistent:
                for obj in written:
                    with suppress(OSError,ValueError,TypeError): self.storage.finish(obj)
            return expense_id
        except Exception:
            # Depois do commit, uma falha no journal nunca apaga um comprovante confirmado.
            for identifier in ([] if committed else written):
                with suppress(OSError):
                    if self.storage.persistent: self.storage.discard(identifier)
                    else: self.storage.remove(identifier)
            raise


    def storage_events(self,expense_id,user_id):
        with connect(self.database_path) as db:
            return [dict(r) for r in db.execute('''SELECT s.* FROM receipt_storage_events s
                JOIN expense_attachments a ON a.id=s.attachment_id JOIN expenses e ON e.id=a.expense_id
                WHERE e.id=? AND e.created_by_user_id=? ORDER BY s.id DESC''',(expense_id,user_id))]

    def delete_attachment(self,mission_id,expense_id,attachment_id,user_id,version):
        if not self.storage.persistent: raise ActivityConflict('Exclusão controlada disponível somente no armazenamento local persistente.')
        with connect(self.database_path) as db:
            db.execute('BEGIN IMMEDIATE')
            entry=db.execute('SELECT * FROM expenses WHERE id=? AND mission_id=? AND created_by_user_id=?',(expense_id,mission_id,user_id)).fetchone()
            if not entry: raise LookupError('Registro não encontrado.')
            if entry['version']!=version: raise ActivityConflict('Este registro mudou em outra aba. Confira a versão atual antes de excluir.')
            user=db.execute('SELECT * FROM app_users WHERE id=? AND enabled=1',(user_id,)).fetchone()
            member=db.execute('SELECT 1 FROM mission_participants WHERE mission_id=? AND participant_id=?',(mission_id,user['participant_id'] if user else None)).fetchone()
            if not member: raise ActivityConflict('A exclusão exige participante autenticado desta missão.')
            item=next((a for a in self._attachments(db,expense_id) if a['id']==attachment_id),None)
            if not item or item['volume_id']!=self.storage.session: raise LookupError('Anexo não encontrado neste volume.')
            if item['local_state']=='excluido': return
            if item['local_state']!='exclusao_pendente':
                db.execute("UPDATE receipt_local_objects SET local_state='exclusao_pendente',delete_requested_by=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE attachment_id=?",(user_id,attachment_id))
                db.execute("UPDATE expenses SET version=version+1,updated_by_user_id=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",(user_id,expense_id))
                db.execute("INSERT INTO expense_history(expense_id,actor_user_id,acao,snapshot) VALUES(?,?,'exclusao_solicitada',?)",(expense_id,user_id,json.dumps({'attachment_id':attachment_id,'object_key':item['object_key']})))
                db.execute("INSERT INTO receipt_storage_events(attachment_id,object_key,actor_user_id,action,source) VALUES(?,?,?,'exclusao_solicitada','usuario')",(attachment_id,item['object_key'],user_id))
        # A intenção autorizada é durável antes de qualquer remoção física.
        try: self.storage.delete(self.storage.record(item))
        except OSError: return
        with connect(self.database_path) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE receipt_local_objects SET local_state='excluido',deleted_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE attachment_id=? AND object_key=? AND local_state='exclusao_pendente'",(attachment_id,item['object_key']))
            db.execute("INSERT INTO receipt_storage_events(attachment_id,object_key,actor_user_id,action,source) VALUES(?,?,?,'exclusao_concluida','usuario')",(attachment_id,item['object_key'],user_id))
