"""Volume local privado e persistente, restrito a conteúdo sintético.

Journal em disco precede publicação. SQLite confirma a referência. Reconciliação
sob bloqueio exclusivo recupera interrupções sem confiar no nome original.
"""
from contextlib import suppress
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
from threading import RLock
from app.core.storage_paths import reject_links, validate_private_directory
from app.db.connection import connect
from app.services.receipt_storage import MAX_FILE, MAX_STORAGE, validate_file
from app.services.storage_contracts import StoredReceipt


class LocalReceiptStorage:
    persistent=True

    def __init__(self,database_path,directory):
        self.database_path=database_path
        self.directory=validate_private_directory(directory,database_path)
        self.lock=RLock()
        self._handle=None
        self.directory.mkdir(mode=0o700,exist_ok=True)
        try:
            self._acquire()
            self._bind_volume()
            for name in ('objects','.staging','.journal','.quarantine'):
                self._mkdir(self.directory/name)
        except Exception:
            self.close()
            raise

    def _acquire(self):
        target=self.directory/'.lock'
        reject_links(target)
        descriptor=os.open(target,os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
        self._handle=os.fdopen(descriptor,'r+b')
        if self._handle.seek(0,2)==0:
            self._handle.write(b'0'); self._handle.flush(); os.fsync(self._handle.fileno())
        self._handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self._handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self._handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError('O volume privado já está em uso ou não permite bloqueio exclusivo.') from None

    def _bind_volume(self):
        marker=self.directory/'.volume.json'
        with connect(self.database_path) as db:
            db.execute('BEGIN IMMEDIATE')
            known=[r[0] for r in db.execute('SELECT id FROM receipt_storage_volumes')]
            if marker.exists():
                value=json.loads(self._read_small(marker))
                identifier=value.get('id','')
                if value.get('format')!=1 or not re.fullmatch('[a-f0-9]{48}',identifier) or identifier not in known:
                    raise RuntimeError('O volume privado não corresponde a este banco. Reconciliação recusada.')
                self.session=identifier
            else:
                if known or any(p.name!='.lock' for p in self.directory.iterdir()):
                    raise RuntimeError('Volume ausente, não identificado ou não vazio. Não foi adotado automaticamente.')
                self.session=secrets.token_hex(24)
                self._write_new(marker,json.dumps({'format':1,'id':self.session}).encode())
                db.execute('INSERT INTO receipt_storage_volumes(id) VALUES(?)',(self.session,))

    def _assert_volume(self):
        if not self._handle or self._handle.closed: raise OSError('Volume privado fechado.')
        reject_links(self.directory)
        value=json.loads(self._read_small(self.directory/'.volume.json'))
        if value!={'format':1,'id':self.session}: raise OSError('Identificação do volume inválida.')

    def _safe(self,target):
        target=Path(target)
        if not target.is_relative_to(self.directory): raise OSError('Objeto fora do volume privado.')
        reject_links(target)
        if target.exists():
            info=target.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1: raise OSError('Objeto privado inválido.')
        return target

    def _mkdir(self,folder):
        reject_links(folder)
        folder.mkdir(mode=0o700,exist_ok=True)
        if not folder.is_dir(): raise OSError('Pasta privada inválida.')
        if os.name!='nt' and stat.S_IMODE(folder.stat().st_mode)&0o077: raise OSError('Permissões da pasta privada inválidas.')

    def _read_small(self,target):
        target=self._safe(target)
        if target.stat().st_size>8192: raise OSError('Metadados de armazenamento inválidos.')
        return target.read_bytes()

    def _sync_directory(self,folder):
        if os.name!='nt':
            descriptor=os.open(folder,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
            try: os.fsync(descriptor)
            finally: os.close(descriptor)

    def _write_new(self,target,content):
        target=self._safe(target)
        descriptor=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0),0o600)
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        self._sync_directory(target.parent)

    def _validate_record(self,item):
        if (type(item.mission_id) is not int or item.mission_id<=0 or type(item.expense_id) is not int or item.expense_id<=0
                or not re.fullmatch('[a-f0-9]{32}',item.attachment_id) or not re.fullmatch('[a-f0-9]{64}',item.object_key)
                or not re.fullmatch('[a-f0-9]{64}',item.checksum) or not 0<item.size_bytes<=MAX_FILE
                or {'png':'image/png','jpg':'image/jpeg','pdf':'application/pdf'}.get(item.extension)!=item.mime):
            raise OSError('Identificação interna do comprovante inválida.')

    def paths(self,item,create=False):
        self._assert_volume(); self._validate_record(item)
        mission=self.directory/'objects'/str(item.mission_id)
        expense=mission/str(item.expense_id)
        if create:
            self._mkdir(mission); self._mkdir(expense)
        for folder in (mission,expense): reject_links(folder)
        return (expense/(item.object_key+'.bin'),self.directory/'.staging'/(item.object_key+'.part'),self.directory/'.journal'/(item.object_key+'.json'))

    def allocate(self,attachment_id,mission_id,expense_id,file):
        return StoredReceipt(attachment_id,mission_id,expense_id,secrets.token_hex(32),file['checksum'],file['size_bytes'],file['extension'],file['mime'])

    def put(self,item,content):
        with self.lock:
            final,stage,journal=self.paths(item,create=True)
            if any(target.exists() for target in (final,stage,journal)):
                raise FileExistsError('O identificador físico já está em uso. Nenhum arquivo foi sobrescrito.')
            validated=validate_file({'name':'sintetico.'+item.extension,'mime':item.mime,'content':content})
            if validated['checksum']!=item.checksum or len(content)!=item.size_bytes: raise OSError('Integridade do envio inválida.')
            total=0
            for folder,dirs,files in os.walk(self.directory,followlinks=False):
                for name in dirs: reject_links(Path(folder)/name)
                for name in files:
                    candidate=self._safe(Path(folder)/name); total+=candidate.stat().st_size
            if total+len(content)>MAX_STORAGE: raise OSError('Limite do volume sintético atingido.')
            self._write_new(journal,json.dumps(asdict(item),sort_keys=True).encode())
            try:
                self._write_new(stage,content)
                self._publish(stage,final)
                if self._read_object(final,item)!=content: raise OSError('Integridade do arquivo inválida.')
            except Exception:
                # O journal permanece recuperável mesmo se a compensação falhar.
                with suppress(OSError): self.discard(item)
                raise

    def _publish(self,stage,final):
        self._safe(stage); self._safe(final)
        os.link(stage,final,follow_symlinks=False)  # criação atômica, sem sobrescrita
        stage.unlink()
        self._sync_directory(final.parent); self._sync_directory(stage.parent)

    def _read_object(self,target,item):
        target=self._safe(target)
        if target.stat().st_size!=item.size_bytes: raise OSError('Arquivo incompleto.')
        content=target.read_bytes()
        if hashlib.sha256(content).hexdigest()!=item.checksum: raise OSError('Checksum do arquivo inválido.')
        return content

    def record(self,attachment):
        return StoredReceipt(attachment['id'],attachment['mission_id'],attachment['expense_id'],attachment['object_key'],
            attachment['checksum'],attachment['size_bytes'],attachment['extension'],attachment['mime'])

    def read_attachment(self,attachment):
        with self.lock:
            if attachment.get('volume_id')!=self.session or attachment.get('local_state')!='armazenado': raise OSError('Comprovante indisponível.')
            item=self.record(attachment)
            final,_,_=self.paths(item)
            return self._read_object(final,item)

    def available(self,attachment):
        try: self.read_attachment(attachment); return True
        except (OSError,ValueError,KeyError,TypeError): return False

    def finish(self,item):
        with self.lock:
            _,_,journal=self.paths(item)
            self._safe(journal).unlink(missing_ok=True)
            self._sync_directory(journal.parent)

    def discard(self,item):
        with self.lock:
            final,stage,journal=self.paths(item)
            for target in (stage,final): self._safe(target).unlink(missing_ok=True)
            self._sync_directory(final.parent)
            self._safe(journal).unlink(missing_ok=True)
            self._sync_directory(journal.parent)

    def delete(self,item):
        self.discard(item)

    def _event(self,db,key,action,attachment_id=None,actor=None,source='recuperacao'):
        db.execute('INSERT OR IGNORE INTO receipt_storage_events(attachment_id,object_key,actor_user_id,action,source) VALUES(?,?,?,?,?)',(attachment_id,key,actor,action,source))

    def _quarantine(self,target,key):
        if not target.exists(): return
        target=self._safe(target)
        destination=self.directory/'.quarantine'/(key+target.suffix)
        self._safe(destination)
        os.link(target,destination,follow_symlinks=False); target.unlink()
        self._sync_directory(target.parent); self._sync_directory(destination.parent)

    def reconcile(self,purge_quarantine=False):
        with self.lock,connect(self.database_path) as db:
            db.execute('BEGIN IMMEDIATE')
            self._assert_volume()
            rows=[dict(r) for r in db.execute('SELECT a.*,o.volume_id,o.object_key,o.local_state,o.delete_requested_by FROM expense_attachments a JOIN receipt_local_objects o ON o.attachment_id=a.id')]
            references={r['object_key']:r for r in rows}
            results={'recovered':0,'errors':0,'quarantined':0,'deleted':0,'purged':0,'manual_review':0}
            # Duplicação de links só é admitida na janela entre publicação e remoção do staging.
            for journal in (self.directory/'.journal').glob('*.json'):
                try:
                    item=StoredReceipt(**json.loads(self._read_small(journal)))
                    self._validate_record(item)
                    if journal.stem!=item.object_key: raise ValueError()
                    final,stage,_=self.paths(item)
                    if final.exists() and stage.exists() and os.path.samefile(final,stage):
                        reject_links(stage); stage.unlink()
                    row=references.get(item.object_key)
                    match=row and row['volume_id']==self.session and self.record(row)==item
                    if match and row['local_state']=='armazenado':
                        if not final.exists() and stage.exists():
                            self._read_object(stage,item); self._publish(stage,final)
                        self._read_object(final,item)
                        self.finish(item); results['recovered']+=1
                        self._event(db,item.object_key,'publicacao_recuperada',item.attachment_id)
                    else:
                        for target in (stage,final):
                            if target.exists(): self._quarantine(target,item.object_key); results['quarantined']+=1
                        self.finish(item)
                        self._event(db,item.object_key,'residuo_em_quarentena',row['id'] if row else None)
                except (OSError,ValueError,TypeError,KeyError):
                    results['manual_review']+=1
                    self._event(db,journal.stem if re.fullmatch('[a-f0-9]{64}',journal.stem) else None,'journal_exige_revisao')
            for row in rows:
                if row['volume_id']!=self.session: continue
                item=self.record(row)
                if row['local_state']=='exclusao_pendente':
                    try:
                        self.delete(item)
                        db.execute("UPDATE receipt_local_objects SET local_state='excluido',deleted_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE attachment_id=?",(item.attachment_id,))
                        self._event(db,item.object_key,'exclusao_concluida',item.attachment_id,row['delete_requested_by'])
                        results['deleted']+=1
                    except OSError: results['errors']+=1
                elif row['local_state']=='armazenado' and not self.available(row):
                    db.execute("UPDATE receipt_local_objects SET local_state='erro',updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE attachment_id=?",(item.attachment_id,))
                    self._event(db,item.object_key,'arquivo_ausente_ou_integro_invalido',item.attachment_id)
                    results['errors']+=1
            # Objetos sem referência SQLite nunca são apresentados como comprovantes.
            for final in (self.directory/'objects').glob('*/*/*.bin'):
                try:
                    key=final.stem
                    if not re.fullmatch('[a-f0-9]{64}',key): continue
                    row=references.get(key)
                    expected=self.paths(self.record(row))[0] if row and row['volume_id']==self.session else None
                    if expected==final: continue
                    self._quarantine(final,key); results['quarantined']+=1
                    self._event(db,key,'orfao_em_quarentena')
                except OSError: results['manual_review']+=1
            for stage in (self.directory/'.staging').glob('*.part'):
                if not re.fullmatch('[a-f0-9]{64}',stage.stem): continue
                try:
                    self._quarantine(stage,stage.stem); results['quarantined']+=1
                    self._event(db,stage.stem,'parcial_em_quarentena')
                except OSError: results['manual_review']+=1
        if purge_quarantine:
            results['purged']=self.purge_quarantine()
        return results

    def purge_quarantine(self):
        count=0
        with self.lock:
            self._assert_volume()
            for target in (self.directory/'.quarantine').iterdir():
                if not re.fullmatch(r'[a-f0-9]{64}\.(bin|part)',target.name): continue
                self._safe(target)
                with connect(self.database_path) as db: self._event(db,target.stem,'purga_sintetica_solicitada')
                target.unlink(); self._sync_directory(target.parent)
                with connect(self.database_path) as db: self._event(db,target.stem,'purga_sintetica_concluida')
                count+=1
        return count

    def close(self):
        if self._handle:
            self._handle.close()
            self._handle=None
