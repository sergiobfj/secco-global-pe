"""07A: SQLite/volume temporários, PNG sintético, credenciais fictícias e MockTransport."""
from dataclasses import replace
from email import policy
from email.parser import BytesParser
import hashlib
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import time

import httpx
import pytest

from app.core.drive_config import CATEGORIES, FOLDER_NAMES, DRIVE_NAMES, DriveConfiguration, READERS, SERVICE_ACCOUNT
from app.db.connection import connect
from app.services.drive_credentials import DriveAccessToken, UnconfiguredDriveCredentials
from app.services.google_drive_storage import GoogleDriveAdapter, DriveError
from app.services.receipt_drive_sync import ReceiptDriveSync
from app.services.storage_contracts import StoredReceipt
from test_persistent_receipts import persistent_client, upload, attachment, delete
from test_receipts import BASE, png, entry_id, send, image_upload
from auth_support import login_as
from test_workspace_access import workspace_settings, make_app
from fastapi.testclient import TestClient


class FakeCredentials:
    def access_token(self):
        return DriveAccessToken('SYNTHETIC-NOT-A-GOOGLE-TOKEN', time.time() + 300)


def configuration():
    return DriveConfiguration(folders_json=json.dumps({
        mission: {category: mission + '_' + category for category in CATEGORIES}
        for mission in DRIVE_NAMES}))


class FakeDrive:
    def __init__(self):
        self.files = {}
        self.calls = []
        self.posts = 0
        self.created = 0
        self.generated = 0
        self.failure = None
        self.after_create = None
        self.extra_permission = None
        self.response_changes = {}
        self.folder_changes = {}
        self.paginate = False
        self.bad_generate = False

    def __call__(self, request):
        path = request.url.path
        self.calls.append((request.method, path, dict(request.url.params)))
        assert request.headers['authorization'] == 'Bearer SYNTHETIC-NOT-A-GOOGLE-TOKEN'
        if self.failure == 'permission': return httpx.Response(403, json={'secret': 'NEVER-LOG-THIS'})
        if self.failure == 'connection': raise httpx.ConnectError('NEVER-LOG-THIS', request=request)
        if self.failure == 'invalid': return httpx.Response(200, text='NEVER-LOG-THIS')
        if self.failure == 'redirect': return httpx.Response(302, headers={'Location': 'https://evil.test/token'})
        if path.endswith('/generateIds'):
            self.generated += 1
            return httpx.Response(200, json={'ids': ['reserved_' + str(self.generated)]} if not self.bad_generate else {'ids': ['../bad']})
        config = DriveConfiguration()
        if '/drives/' in path:
            drive = path.rsplit('/', 1)[1]
            mission = next(m for m in DRIVE_NAMES if getattr(config, m) == drive)
            return httpx.Response(200, json={'id': drive, 'name': DRIVE_NAMES[mission]})
        assert request.url.params['supportsAllDrives'] == 'true'
        if path.endswith('/permissions'):
            resource = path.split('/')[-2]
            if resource in (config.argentina, config.portugal):
                mission = 'argentina' if resource == config.argentina else 'portugal'
            elif resource in self.files:
                mission = self.files[resource]['appProperties']['secco_mission']
            else: mission = resource.split('_')[0]
            permissions = [{'type': 'user', 'emailAddress': email, 'role': 'writer'} for email in sorted(READERS[mission])]
            if self.extra_permission: permissions.append(self.extra_permission)
            if self.paginate:
                if request.url.params.get('pageToken') == 'second': permissions = permissions[1:]
                else: return httpx.Response(200, json={'permissions': permissions[:1], 'nextPageToken': 'second'})
            return httpx.Response(200, json={'permissions': permissions})
        if request.method == 'POST':
            assert path == '/upload/drive/v3/files'
            self.posts += 1
            message = BytesParser(policy=policy.default).parsebytes(
                ('Content-Type: ' + request.headers['content-type'] + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + request.content)
            parts = list(message.iter_parts())
            metadata = json.loads(parts[0].get_payload(decode=True))
            content = parts[1].get_payload(decode=True)
            identifier = metadata['id']
            if identifier in self.files: return httpx.Response(409, json={'error': {}})
            mission = metadata['appProperties']['secco_mission']
            assert metadata['parents'][0].startswith(mission + '_')
            self.files[identifier] = {**metadata, 'driveId': getattr(config, mission), 'trashed': False,
                                      'size': str(len(content)), 'sha256Checksum': hashlib.sha256(content).hexdigest()}
            self.created += 1
            if self.after_create == 'interrupt': raise SystemExit('interrupção sintética')
            if self.after_create == 'timeout': raise httpx.ReadTimeout('NEVER-LOG-THIS', request=request)
            return httpx.Response(200, json={'id': identifier})
        identifier = path.rsplit('/', 1)[1]
        if identifier.startswith(('argentina_', 'portugal_')):
            mission, category = identifier.split('_', 1)
            return httpx.Response(200, json={'id': identifier, 'driveId': getattr(config, mission),
                'parents': [getattr(config, mission)], 'name': FOLDER_NAMES[mission][category], 'trashed': False,
                'mimeType': 'application/vnd.google-apps.folder', 'capabilities': {'canAddChildren': True}, **self.folder_changes})
        if identifier not in self.files: return httpx.Response(404, json={})
        return httpx.Response(200, json={**self.files[identifier], **self.response_changes})


@pytest.fixture
def sync_setup(persistent_client):
    client, google, settings = persistent_client
    with connect(settings.database_path) as db:
        db.execute("INSERT INTO receipt_mission_config(mission_id,processo) VALUES(2,'PROCESSO-SINTETICO-07A')")
    item = upload(client)
    file = attachment(client, item)
    assert file['official_name']
    remote = FakeDrive()
    adapter = GoogleDriveAdapter(configuration(), FakeCredentials(), transport=httpx.MockTransport(remote))
    settings = replace(settings, receipts_drive_mode='simulated')
    worker = ReceiptDriveSync(settings, client.app.state.receipt_storage, adapter, client.app.state.auth)
    user_id = client.get('/api/usuario').json()['id']
    yield client, google, settings, worker, remote, item, file, user_id
    adapter.close()


def job(setup):
    _, _, settings, _, _, _, file, _ = setup
    with connect(settings.database_path) as db:
        row = db.execute('SELECT * FROM receipt_drive_sync WHERE attachment_id=?', (file['id'],)).fetchone()
        return dict(row) if row else None


def enqueue(setup):
    _, _, _, worker, _, _, file, user_id = setup
    worker.enqueue(file['id'], actor_user_id=user_id)


@pytest.mark.parametrize('mission', ['argentina', 'portugal'])
def test_correct_drive_and_technical_name(mission):
    remote = FakeDrive()
    adapter = GoogleDriveAdapter(configuration(), FakeCredentials(), transport=httpx.MockTransport(remote))
    item = StoredReceipt('a'*32, 2 if mission == 'argentina' else 1, 1, 'b'*64,
                         hashlib.sha256(png()).hexdigest(), len(png()), 'png', 'image/png',
                         mission, 'nome-tecnico-preservado.png', 'diarias')
    try:
        result = adapter.upload(item, BytesIO(png()), idempotency_key='c'*64, remote_id=adapter.reserve_id())
        assert result.checksum == item.checksum
        assert remote.files[result.remote_id]['driveId'] == getattr(configuration(), mission)
        assert remote.files[result.remote_id]['name'] == item.official_name
        assert remote.created == 1
        assert not any('/permissions' in path and method != 'GET' for method, path, _ in remote.calls)
    finally: adapter.close()


def test_enqueue_upload_verify_and_ui(sync_setup):
    client, _, settings, worker, remote, item, file, _ = sync_setup
    assert 'Armazenado localmente' in client.get(BASE + f'/{item}').text
    assert 'Sincronizado e verificado' not in client.get(BASE + f'/{item}').text
    enqueue(sync_setup)
    assert job(sync_setup)['state'] == 'aguardando' and job(sync_setup)['remote_id'] is None
    assert 'Aguardando sincronização' in client.get(BASE + f'/{item}').text
    assert worker.run_one(file['id']) == 'verificado'
    assert job(sync_setup)['verified_at'] and remote.created == 1
    assert 'Sincronizado e verificado (simulação)' in client.get(BASE + f'/{item}').text
    assert client.app.state.receipt_storage.read_attachment(file) == png()
    with connect(settings.database_path) as db:
        # A tabela local permanece intacta: 006 não foi reescrita.
        assert tuple(db.execute('SELECT sync_state,remote_reference FROM receipt_local_objects').fetchone()) == ('pendente', None)


@pytest.mark.parametrize('failure,code', [('permission','permissao'), ('connection','conexao'),
                                        ('invalid','resposta_invalida'), ('redirect','remoto')])
def test_remote_errors_preserve_local(sync_setup, failure, code, caplog):
    client, _, _, worker, remote, item, file, _ = sync_setup
    enqueue(sync_setup)
    remote.failure = failure
    assert worker.run_one(file['id']) == 'erro'
    assert job(sync_setup)['error_code'] == code and job(sync_setup)['verified_at'] is None
    assert client.app.state.receipt_storage.read_attachment(file) == png()
    assert 'Erro de sincronização' in client.get(BASE + f'/{item}').text
    assert 'NEVER-LOG-THIS' not in caplog.text and 'SYNTHETIC-NOT-A-GOOGLE-TOKEN' not in caplog.text
    remote.failure = None
    assert worker.reconcile() == {'verificado': 1, 'erro': 0}
    assert remote.created == 1


@pytest.mark.parametrize('phase', ['timeout', 'interrupt'])
def test_lost_confirmation_reconciles_without_duplicates(sync_setup, phase):
    _, _, _, worker, remote, _, file, _ = sync_setup
    enqueue(sync_setup)
    remote.after_create = phase
    if phase == 'interrupt':
        with pytest.raises(SystemExit): worker.run_one(file['id'])
        assert job(sync_setup)['state'] == 'enviando'
    else:
        assert worker.run_one(file['id']) == 'erro'
    remote_id = job(sync_setup)['remote_id']
    assert remote_id in remote.files
    remote.after_create = None
    assert worker.reconcile() == {'verificado': 1, 'erro': 0}
    enqueue(sync_setup)
    assert worker.run_one(file['id']) == 'verificado'
    assert job(sync_setup)['remote_id'] == remote_id
    assert remote.created == remote.posts == remote.generated == 1


def test_interruption_before_send_keeps_reserved_id(sync_setup, monkeypatch):
    _, _, _, worker, remote, _, file, _ = sync_setup
    enqueue(sync_setup)
    with monkeypatch.context() as patch:
        patch.setattr(worker.adapter, 'upload', lambda *a, **k: (_ for _ in ()).throw(SystemExit()))
        with pytest.raises(SystemExit): worker.run_one(file['id'])
    assert job(sync_setup)['state'] == 'enviando' and job(sync_setup)['remote_id']
    assert remote.created == 0
    assert worker.reconcile()['verificado'] == 1 and remote.generated == 1


@pytest.mark.parametrize('changes', [
    {'driveId': DriveConfiguration().portugal}, {'parents': ['portugal_diarias']},
    {'sha256Checksum': '0'*64}, {'sha256Checksum': None}, {'size': '999'},
    {'name': 'nome-alterado.png'}, {'mimeType': 'text/html'}, {'trashed': True},
    {'appProperties': {}}, {'id': 'wrong-remote-id'},
])
def test_invalid_confirmation_is_never_success(sync_setup, changes):
    client, _, _, worker, remote, item, file, _ = sync_setup
    enqueue(sync_setup)
    remote.response_changes = changes
    assert worker.run_one(file['id']) == 'erro' and job(sync_setup)['error_code'] == 'integridade'
    assert 'Sincronizado e verificado' not in client.get(BASE + f'/{item}').text
    remote.response_changes = {}
    assert worker.reconcile()['verificado'] == 1 and remote.created == 1


@pytest.mark.parametrize('permission', [
    {'type': 'anyone', 'role': 'reader'}, {'type': 'domain', 'role': 'reader'},
    {'type': 'group', 'emailAddress': 'group@secco.example', 'role': 'reader'},
    {'type': 'user', 'emailAddress': 'marcos@secco.example', 'role': 'reader'},
    {'type': 'user', 'emailAddress': 'hugo@secco.example', 'role': 'reader'},
    {'type': 'user', 'emailAddress': [], 'role': 'reader'},
])
def test_unsafe_inherited_permissions_block_upload(sync_setup, permission):
    _, _, _, worker, remote, _, file, _ = sync_setup
    enqueue(sync_setup)
    remote.extra_permission = permission
    assert worker.run_one(file['id']) == 'erro' and job(sync_setup)['error_code'] == 'permissao'
    assert remote.posts == 0


def test_permission_pagination(sync_setup):
    _, _, _, worker, remote, _, file, _ = sync_setup
    enqueue(sync_setup)
    remote.paginate = True
    assert worker.run_one(file['id']) == 'verificado'
    assert any(params.get('pageToken') == 'second' for _, _, params in remote.calls)


@pytest.mark.parametrize('changes', [
    {'driveId': DriveConfiguration().portugal}, {'parents': [DriveConfiguration().portugal]},
    {'mimeType': 'application/vnd.google-apps.shortcut'}, {'name': 'Atividades'}, {'trashed': True},
])
def test_wrong_folder_blocks_before_upload(sync_setup, changes):
    _, _, _, worker, remote, _, file, _ = sync_setup
    enqueue(sync_setup)
    remote.folder_changes = changes
    assert worker.run_one(file['id']) == 'erro' and job(sync_setup)['error_code'] == 'destino'
    assert remote.posts == 0


def test_swapped_drive_configuration_rejected_by_remote_identity(sync_setup):
    _, _, _, worker, remote, _, file, _ = sync_setup
    config = configuration()
    worker.adapter.configuration = replace(config, argentina=config.portugal, portugal=config.argentina)
    enqueue(sync_setup)
    assert worker.run_one(file['id']) == 'erro' and remote.posts == 0


def test_authorization_other_owner_cross_mission_and_disabled(sync_setup):
    client, google, settings, worker, remote, _, file, _ = sync_setup
    for email in ('bruno', 'hugo', 'alan'):
        assert login_as(client, google, email=email+'@workspace.test', sub='synthetic-'+email).status_code == 303
        user_id = client.get('/api/usuario').json()['id']
        with pytest.raises(DriveError, match='permissao'): worker.enqueue(file['id'], actor_user_id=user_id)
    assert job(sync_setup) is None and remote.calls == []
    enqueue(sync_setup)
    with connect(settings.database_path) as db: db.execute('UPDATE app_users SET enabled=0 WHERE id=?', (sync_setup[-1],))
    assert worker.run_one(file['id']) == 'erro' and remote.calls == []


def test_pending_official_name_and_unmapped_category_never_enqueue(sync_setup):
    _, _, settings, worker, remote, _, file, _ = sync_setup
    with connect(settings.database_path) as db: db.execute('UPDATE expense_attachments SET official_name=NULL WHERE id=?', (file['id'],))
    with pytest.raises(DriveError, match='destino'): enqueue(sync_setup)
    with connect(settings.database_path) as db:
        db.execute('UPDATE expense_attachments SET official_name=? WHERE id=?', (file['official_name'], file['id']))
        db.execute("UPDATE expenses SET tipo='seguro_saude'")
    with pytest.raises(DriveError, match='destino'): enqueue(sync_setup)
    assert job(sync_setup) is None and remote.calls == []


def test_metadata_edit_invalidates_confirmation_without_new_upload(sync_setup):
    client, _, settings, worker, remote, item, file, _ = sync_setup
    enqueue(sync_setup)
    assert worker.run_one(file['id']) == 'verificado'
    with connect(settings.database_path) as db:
        db.execute('UPDATE expense_attachments SET official_name=? WHERE id=?', ('outro-nome.png', file['id']))
    assert 'Sincronizado e verificado' not in client.get(BASE + f'/{item}').text
    assert worker.run_one(file['id']) == 'erro' and job(sync_setup)['error_code'] == 'metadados_alterados'
    assert remote.created == 1


def test_deleted_attachment_is_not_resynchronized_or_remotely_deleted(sync_setup):
    client, _, _, worker, remote, item, file, _ = sync_setup
    enqueue(sync_setup)
    assert worker.run_one(file['id']) == 'verificado'
    assert delete(client, item, file).status_code == 303
    count = len(remote.calls)
    assert worker.reconcile() == {'verificado': 0, 'erro': 0} and len(remote.calls) == count
    assert worker.run_one(file['id']) == 'erro' and job(sync_setup)['error_code'] == 'local'
    assert remote.created == 1 and len(remote.files) == 1


def test_unconfigured_and_expired_credentials_do_not_touch_transport(sync_setup):
    _, _, _, worker, remote, _, file, _ = sync_setup
    enqueue(sync_setup)
    worker.adapter.credentials = UnconfiguredDriveCredentials()
    assert worker.run_one(file['id']) == 'erro' and job(sync_setup)['error_code'] == 'credenciais'
    assert remote.calls == []
    class Expired:
        def access_token(self): return DriveAccessToken('SYNTHETIC-EXPIRED', time.time()-1)
    worker.adapter.credentials = Expired()
    assert worker.run_one(file['id']) == 'erro' and remote.calls == []
    assert 'SYNTHETIC-EXPIRED' not in repr(Expired().access_token())


def test_no_real_transport_or_mode(sync_setup):
    _, _, settings, worker, _, _, _, _ = sync_setup
    with pytest.raises(RuntimeError, match='MockTransport'):
        GoogleDriveAdapter(configuration(), FakeCredentials(), transport=httpx.HTTPTransport())
    with pytest.raises(RuntimeError, match='real'):
        replace(settings, receipts_drive_mode='real').validate()
    with pytest.raises(RuntimeError, match='simulação'):
        ReceiptDriveSync(replace(settings, receipts_drive_mode='disabled'), worker.storage, worker.adapter, worker.auth)


@pytest.mark.parametrize('changes', [
    {'portugal': DriveConfiguration().argentina}, {'folders_json': '[]'},
    {'folders_json': '{"argentina":{"diarias":"same"},"portugal":{"diarias":"same"}}'},
    {'folders_json': '{"argentina":{"unknown":"folder"}}'},
])
def test_invalid_configuration(changes):
    with pytest.raises(ValueError): replace(configuration(), **changes).validate()


def test_reservation_response_is_validated(sync_setup):
    _, _, _, worker, remote, _, file, _ = sync_setup
    enqueue(sync_setup)
    remote.bad_generate = True
    assert worker.run_one(file['id']) == 'erro' and job(sync_setup)['remote_id'] is None
    assert remote.created == 0


def test_sqlite_failure_after_remote_confirmation_is_recoverable(sync_setup, monkeypatch):
    _, _, _, worker, remote, _, file, _ = sync_setup
    enqueue(sync_setup)
    original = worker._event
    def event(db, attachment_id, state, error=None):
        if state == 'verificado': raise sqlite3.OperationalError('falha SQLite sintética')
        original(db, attachment_id, state, error)
    with monkeypatch.context() as patch:
        patch.setattr(worker, '_event', event)
        with pytest.raises(sqlite3.OperationalError): worker.run_one(file['id'])
    assert job(sync_setup)['state'] == 'enviando' and job(sync_setup)['remote_id'] in remote.files
    assert worker.reconcile()['verificado'] == 1 and remote.created == remote.posts == 1


def test_restart_restores_remote_journal_without_duplicate(tmp_path):
    settings = workspace_settings(tmp_path/'restart-drive.sqlite3', receipts_synthetic_enabled=True,
        receipts_storage_backend='local', receipts_private_dir=tmp_path/'volume', receipts_drive_mode='simulated')
    remote = FakeDrive()
    adapter = GoogleDriveAdapter(configuration(), FakeCredentials(), transport=httpx.MockTransport(remote))
    try:
        app, google = make_app(settings)
        with TestClient(app, base_url='http://127.0.0.1') as client:
            assert login_as(client, google).status_code == 303
            with connect(settings.database_path) as db:
                db.execute("INSERT INTO receipt_mission_config(mission_id,processo) VALUES(2,'PROCESSO-SINTETICO')")
            item = upload(client)
            file = attachment(client, item)
            worker = ReceiptDriveSync(settings, app.state.receipt_storage, adapter, app.state.auth)
            worker.enqueue(file['id'], actor_user_id=client.get('/api/usuario').json()['id'])
            remote.after_create = 'interrupt'
            with pytest.raises(SystemExit): worker.run_one(file['id'])
        remote.after_create = None
        second, google2 = make_app(settings)
        with TestClient(second, base_url='http://127.0.0.1') as client:
            assert login_as(client, google2).status_code == 303
            worker = ReceiptDriveSync(settings, second.state.receipt_storage, adapter, second.state.auth)
            assert worker.reconcile() == {'verificado': 1, 'erro': 0}
            assert remote.posts == remote.created == remote.generated == 1
            assert second.state.receipt_storage.read_attachment(attachment(client, item)) == png()
    finally: adapter.close()


def test_marcos_cannot_enqueue_or_download_private_files(tmp_path):
    settings = workspace_settings(tmp_path/'coordinator-drive.sqlite3', receipts_synthetic_enabled=True,
        receipts_storage_backend='local', receipts_private_dir=tmp_path/'volume', receipts_drive_mode='simulated')
    app, google = make_app(settings)
    remote = FakeDrive()
    adapter = GoogleDriveAdapter(configuration(), FakeCredentials(), transport=httpx.MockTransport(remote))
    try:
        with TestClient(app, base_url='http://127.0.0.1') as client:
            assert login_as(client, google).status_code == 303
            item = upload(client)
            file = attachment(client, item)
            assert login_as(client, google, email='marcos@secco.example', sub='synthetic-marcos').status_code == 303
            assert client.get('/consolidado').status_code == 200
            assert client.get(BASE+f'/{item}/anexos/'+file['id']).status_code == 403
            worker = ReceiptDriveSync(settings, app.state.receipt_storage, adapter, app.state.auth)
            with pytest.raises(DriveError, match='permissao'):
                worker.enqueue(file['id'], actor_user_id=client.get('/api/usuario').json()['id'])
            assert remote.calls == []
    finally: adapter.close()


def test_008_is_additive_and_keeps_all_existing_rows(database, tmp_path, monkeypatch):
    # Migração sobre snapshot 007 estritamente sintético, nunca cópia do operacional.
    import app.db.migrate as migration
    from app.core.config import ROOT
    folder = tmp_path/'previous-migrations'
    folder.mkdir()
    for file in migration.MIGRATIONS.glob('00[1-7]_*.sql'):
        (folder/file.name).write_bytes(file.read_bytes())
    previous = tmp_path/'previous.sqlite3'
    with monkeypatch.context() as patch:
        patch.setattr(migration, 'MIGRATIONS', folder)
        migration.migrate(previous)
    from app.db.seed import seed
    seed(previous)
    with connect(previous) as db:
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        before = {table: [tuple(r) for r in db.execute('SELECT * FROM '+table)] for table in tables}
        schema = {r[0]: r[1] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE type IN ('table','index','trigger')")}
    migration.migrate(previous)
    with connect(previous) as db:
        for table in tables:
            rows = [tuple(r) for r in db.execute('SELECT * FROM '+table)]
            if table == 'schema_migrations': rows = rows[:7]
            assert rows == before[table]
        after = {r[0]: r[1] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE type IN ('table','index','trigger')")}
        assert all(after[name] == value for name, value in schema.items())
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert db.execute('SELECT COUNT(*) FROM receipt_drive_sync').fetchone()[0] == 0
    expected = {
        '004_authentication.sql': '1a6af33b948c8a7c98fe636364938b87399dd679905e1193b66ba4a7a7dafb0f',
        '005_receipts.sql': '82e5aea2a7b3c437c5ab624f6997ff022408060fb24f88dc0107aa0d05a53b97',
        '006_receipt_storage.sql': '40f26bf80edad117da2bae42998a2da5c23209840fc9011cbba054d3a2159585',
        '007_workspace_coordination.sql': '9152df1d702d840461a0228e81d4b0610edbb023f46fa65c0fb87228e47d3a08',
    }
    for name, digest in expected.items():
        assert hashlib.sha256((ROOT/'app/db/migrations'/name).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize('email,mission,participant,funded', [
    ('tiago', 'argentina', 3, 0), ('bruno', 'argentina', 4, 1),
    ('hugo', 'portugal', 1, 1), ('alan', 'portugal', 2, 0),
])
def test_four_operators_sync_own_mission_independent_of_funding(tmp_path, email, mission, participant, funded):
    settings = workspace_settings(tmp_path/'operators.sqlite3', receipts_synthetic_enabled=True,
        receipts_storage_backend='local', receipts_private_dir=tmp_path/'volume', receipts_drive_mode='simulated')
    app, google = make_app(settings)
    remote = FakeDrive()
    adapter = GoogleDriveAdapter(configuration(), FakeCredentials(), transport=httpx.MockTransport(remote))
    try:
        with TestClient(app, base_url='http://127.0.0.1') as client:
            assert login_as(client, google, email=email+'@secco.example', sub='synthetic-'+email).status_code == 303
            mission_id = app.state.repository.get(mission).id
            with connect(settings.database_path) as db:
                db.execute("INSERT INTO receipt_mission_config(mission_id,processo) VALUES(?,'PROCESSO-SINTETICO')", (mission_id,))
            base = '/missoes/'+mission+'/comprovantes'
            assert client.get(base+'/novo').status_code == 200
            data = {'csrf_token': client.cookies.get('secco_csrf'), 'request_key': 'synthetic-'+email+'-request-00001',
                    'participant_id': str(participant), 'tipo': 'diaria', 'rubrica': 'Rubrica sintética',
                    'data': '2026-11-18', 'valor': '12,34', 'moeda': 'ARS' if mission == 'argentina' else 'EUR',
                    'descricao': 'Diária sintética', 'intent': 'rascunho', 'synthetic_ack': 'on'}
            item = entry_id(send(client, data, image_upload(), url=base+'/novo'))
            user_id = client.get('/api/usuario').json()['id']
            entry = app.state.receipts.get(mission_id, item, user_id)
            assert entry['participant']['financiado_pela_subvencao'] == funded
            file = entry['attachments'][0]
            worker = ReceiptDriveSync(settings, app.state.receipt_storage, adapter, app.state.auth)
            worker.enqueue(file['id'], actor_user_id=user_id)
            assert worker.run_one(file['id']) == 'verificado'
            assert next(iter(remote.files.values()))['driveId'] == getattr(configuration(), mission)
    finally: adapter.close()


def test_concurrent_retry_does_not_duplicate(sync_setup):
    _, _, _, worker, remote, _, file, _ = sync_setup
    enqueue(sync_setup)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker.run_one, [file['id'], file['id']]))
    assert results == ['verificado', 'verificado']
    assert remote.created == remote.posts == remote.generated == 1
