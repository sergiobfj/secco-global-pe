"""Journal SQLite remoto independente do journal de publicação local.

Sem endpoint, worker automático ou execução fora da concessão de testes nesta etapa.
"""
from dataclasses import replace
import hashlib
from io import BytesIO

from app.core.drive_config import TYPE_CATEGORY
from app.core.test_database import assert_temporary_database, testing_enabled
from app.db.connection import connect
from app.services.storage_contracts import DriveError, SharedDriveAdapter


class ReceiptDriveSync:
    def __init__(self, settings, storage, adapter: SharedDriveAdapter, auth):
        settings.validate()
        if not testing_enabled() or settings.receipts_drive_mode != 'simulated' or not storage.persistent:
            raise RuntimeError('Sincronização disponível somente em simulação isolada explícita.')
        assert_temporary_database(settings.database_path)
        if storage.database_path != settings.database_path or auth.database_path != settings.database_path:
            raise RuntimeError('Armazenamento e autorização precisam pertencer ao mesmo banco.')
        self.database_path = settings.database_path
        self.storage = storage
        self.adapter = adapter
        self.auth = auth

    def _load(self, db, attachment_id):
        row = db.execute('''SELECT a.*,o.object_key,o.volume_id,o.local_state,e.tipo,
            e.created_by_user_id,m.codigo AS mission_code FROM expense_attachments a
            JOIN receipt_local_objects o ON o.attachment_id=a.id
            JOIN expenses e ON e.id=a.expense_id AND e.mission_id=a.mission_id
            JOIN missions m ON m.id=e.mission_id WHERE a.id=?''', (attachment_id,)).fetchone()
        if not row: raise DriveError('local')
        return dict(row)

    def _authorized(self, item, user_id):
        user = self.auth.get_user(user_id)
        if item['created_by_user_id'] != user_id or not self.auth.can_edit(user, item['mission_id']):
            raise DriveError('permissao')

    def enqueue(self, attachment_id, *, actor_user_id):
        with self.storage.lock, connect(self.database_path) as db:
            db.execute('BEGIN IMMEDIATE')
            item = self._load(db, attachment_id)
            self._authorized(item, actor_user_id)
            if (item['local_state'] != 'armazenado' or item['volume_id'] != self.storage.session
                    or not self.storage.available(item)):
                raise DriveError('local')
            category = TYPE_CATEGORY.get(item['tipo'])
            if not category or not item['official_name'] or item['name_status'] != 'preparado':
                raise DriveError('destino')
            try: drive, folder = self.adapter.configuration.destination(item['mission_code'], category)
            except ValueError: raise DriveError('destino') from None
            old = db.execute('SELECT * FROM receipt_drive_sync WHERE attachment_id=?', (attachment_id,)).fetchone()
            if old:
                self._snapshot(item, dict(old))
                return
            key = hashlib.sha256((self.storage.session + ':' + attachment_id).encode()).hexdigest()
            db.execute('''INSERT INTO receipt_drive_sync(attachment_id,object_key,volume_id,mission_code,
                category,official_name,checksum,drive_id,folder_id,idempotency_key,state)
                VALUES(?,?,?,?,?,?,?,?,?,?,'aguardando')''',
                (attachment_id, item['object_key'], item['volume_id'], item['mission_code'], category,
                 item['official_name'], item['checksum'], drive, folder, key))
            self._event(db, attachment_id, 'aguardando')

    def _snapshot(self, item, job):
        if any(item[k] != job[k] for k in ('object_key', 'volume_id', 'mission_code', 'official_name', 'checksum')):
            raise DriveError('metadados_alterados')
        if TYPE_CATEGORY.get(item['tipo']) != job['category']: raise DriveError('metadados_alterados')
        if item['local_state'] != 'armazenado' or item['volume_id'] != self.storage.session: raise DriveError('local')
        try: destination = self.adapter.configuration.destination(item['mission_code'], job['category'])
        except ValueError: raise DriveError('destino') from None
        if destination != (job['drive_id'], job['folder_id']): raise DriveError('destino')

    def _event(self, db, attachment_id, state, error=None):
        db.execute('INSERT INTO receipt_drive_events(attachment_id,state,error_code) VALUES(?,?,?)',
                   (attachment_id, state, error))

    def run_one(self, attachment_id):
        # O mesmo RLock é usado pelo armazenamento local. O volume já possui lock de processo.
        with self.storage.lock:
            with connect(self.database_path) as db:
                job = db.execute('''SELECT s.*,EXISTS(SELECT 1 FROM receipt_drive_events e
                    WHERE e.attachment_id=s.attachment_id AND e.state='verificado') AS ever_verified
                    FROM receipt_drive_sync s WHERE attachment_id=?''', (attachment_id,)).fetchone()
            if not job: raise LookupError('Sincronização não enfileirada.')
            job = dict(job)
            try:
                with connect(self.database_path) as db:
                    item = self._load(db, attachment_id)
                self._authorized(item, item['created_by_user_id'])
                self._snapshot(item, job)
                content = self.storage.read_attachment(item)
                record = replace(self.storage.record(item), mission_code=item['mission_code'],
                                 official_name=item['official_name'], category=job['category'])
                if job['remote_id'] is None:
                    remote_id = self.adapter.reserve_id()
                    # Confirma ID antes de qualquer byte remoto. Queda aqui só perde um ID vazio.
                    with connect(self.database_path) as db:
                        db.execute('UPDATE receipt_drive_sync SET remote_id=? WHERE attachment_id=?', (remote_id, attachment_id))
                    job['remote_id'] = remote_id
                with connect(self.database_path) as db:
                    db.execute("UPDATE receipt_drive_sync SET state='enviando',error_code=NULL,verified_at=NULL,attempts=attempts+1,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE attachment_id=?", (attachment_id,))
                    self._event(db, attachment_id, 'enviando')
                args = {'idempotency_key': job['idempotency_key'], 'remote_id': job['remote_id']}
                if job['state'] == 'verificado' or job['ever_verified']:
                    confirmed = self.adapter.verify(record, **args)
                    if confirmed is None: raise DriveError('integridade')
                else:
                    confirmed = self.adapter.upload(record, BytesIO(content), **args)
                if confirmed.remote_id != job['remote_id'] or confirmed.checksum != item['checksum']:
                    raise DriveError('integridade')
                with connect(self.database_path) as db:
                    db.execute('BEGIN IMMEDIATE')
                    current = self._load(db, attachment_id)
                    self._snapshot(current, job)
                    self._authorized(current, current['created_by_user_id'])
                    db.execute("UPDATE receipt_drive_sync SET state='verificado',error_code=NULL,verified_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE attachment_id=?", (attachment_id,))
                    self._event(db, attachment_id, 'verificado')
                return 'verificado'
            except (DriveError, OSError) as error:
                code = error.code if isinstance(error, DriveError) else 'local'
                with connect(self.database_path) as db:
                    db.execute("UPDATE receipt_drive_sync SET state='erro',error_code=?,verified_at=NULL,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE attachment_id=?", (code, attachment_id))
                    self._event(db, attachment_id, 'erro', code)
                return 'erro'

    def reconcile(self):
        # Inclui enviando (queda abrupta), erros e confirmações para revalidar a API.
        with connect(self.database_path) as db:
            ids = [r[0] for r in db.execute('''SELECT s.attachment_id FROM receipt_drive_sync s
                JOIN receipt_local_objects o ON o.attachment_id=s.attachment_id
                WHERE o.local_state='armazenado' ORDER BY s.attachment_id''')]
        counts = {'verificado': 0, 'erro': 0}
        for attachment_id in ids:
            counts[self.run_one(attachment_id)] += 1
        return counts
