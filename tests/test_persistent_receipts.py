"""05B: todos os bancos e volumes são concessões temporárias sintéticas."""
from dataclasses import asdict,replace
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3

import pytest
from fastapi.testclient import TestClient
from app.core.config import ROOT,Settings
from app.core.test_database import UnsafeTestDatabase
from app.db.connection import connect
from app.db.migrate import migrate
from app.main import create_app
from app.services.local_receipt_storage import LocalReceiptStorage
from app.services.receipt_storage import validate_file
from app.services.storage_contracts import StoredReceipt
from app.repositories.itinerary import ActivityConflict
from app.services.receipts import load_rules,validate_expense
from auth_support import synthetic_settings,SyntheticGoogle,login_as
from test_receipts import BASE,values,send,entry_id,get_entry,image_upload,png


@pytest.fixture
def persistent_client(tmp_path):
    settings=synthetic_settings(tmp_path/'persistent.sqlite3',receipts_synthetic_enabled=True,
        receipts_storage_backend='local',receipts_private_dir=tmp_path/'private-volume')
    app=create_app(settings); google=SyntheticGoogle(settings); app.state.oidc=google.provider()
    with TestClient(app,base_url='http://127.0.0.1') as client:
        assert login_as(client,google).status_code==303
        yield client,google,settings


def upload(client):
    return entry_id(send(client,values(client,kind='diaria',intent='revisao',check_diaria_0='on',check_diaria_1='on'),image_upload()))


def attachment(client,item): return get_entry(client,item)['attachments'][0]


def delete(client,item,a,version=1,**changes):
    client.get(BASE+f'/{item}')
    data={'csrf_token':client.cookies.get('secco_csrf'),'version':str(version),'confirm_delete':'on',**changes}
    return client.post(BASE+f'/{item}/anexos/'+a['id']+'/excluir',data=data,follow_redirects=False)


def restart(settings):
    app=create_app(settings); google=SyntheticGoogle(settings); app.state.oidc=google.provider()
    return app,google


def test_persistent_upload_and_private_metadata(persistent_client):
    client,_,settings=persistent_client
    item=upload(client); a=attachment(client,item)
    store=client.app.state.receipt_storage
    assert a['available'] and a['local_state']=='armazenado' and a['sync_state']=='pendente'
    obj=store.record(a); file=store.paths(obj)[0]
    assert file.read_bytes()==png() and file.parent.name==str(item) and file.parent.parent.name=='2'
    assert len(file.stem)==64 and a['id'] not in file.name and a['original_name'] not in file.name
    assert a['checksum']==hashlib.sha256(png()).hexdigest() and a['official_name'] is None
    page=client.get(BASE+f'/{item}?aviso=salvo')
    assert 'Armazenado localmente' in page.text and 'Aguardando sincronização' in page.text
    assert str(settings.receipts_private_dir) not in page.text and '\u2014' not in page.text
    assert 'não substitui backup' in page.text
    response=client.get(BASE+f'/{item}/anexos/'+a['id'])
    assert response.content==png() and 'attachment;' in response.headers['content-disposition']
    assert response.headers['cache-control']=='no-store'
    with connect(settings.database_path) as db:
        assert db.execute('SELECT remote_reference FROM receipt_local_objects').fetchone()[0] is None


def test_app_restart_recovers_confirmed_attachment(tmp_path):
    settings=synthetic_settings(tmp_path/'restart.sqlite3',receipts_synthetic_enabled=True,receipts_storage_backend='local',receipts_private_dir=tmp_path/'volume')
    app,google=restart(settings)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        assert login_as(client,google).status_code==303
        item=upload(client); a=attachment(client,item); store_id=client.app.state.receipt_storage.session
    assert settings.receipts_private_dir.exists()
    app2,google2=restart(settings)
    with TestClient(app2,base_url='http://127.0.0.1') as client:
        assert login_as(client,google2).status_code==303
        assert client.app.state.receipt_storage.session==store_id
        assert attachment(client,item)['available']
        assert client.get(BASE+f'/{item}/anexos/'+a['id']).content==png()
        assert len(client.app.state.receipts.history(item,client.get('/api/usuario').json()['id']))==1


@pytest.mark.parametrize('phase',['_write_new','_publish'])
def test_disk_failure_does_not_mark_stored(persistent_client,monkeypatch,phase):
    client,_,_=persistent_client
    store=client.app.state.receipt_storage
    with monkeypatch.context() as patch:
        patch.setattr(store,phase,lambda *a,**k: (_ for _ in ()).throw(OSError('falha sintética de disco')))
        item=upload(client)
    a=attachment(client,item)
    assert not a['available'] and a['local_state']=='erro'
    assert get_entry(client,item)['effective_status']=='pendente_comprovante'
    assert 'Erro de armazenamento' in client.get(BASE+f'/{item}').text


def test_incomplete_file_is_never_served_and_reconciles(persistent_client):
    client,_,settings=persistent_client
    item=upload(client); a=attachment(client,item); store=client.app.state.receipt_storage
    file=store.paths(store.record(a))[0]; file.write_bytes(png()[:20])
    assert client.get(BASE+f'/{item}/anexos/'+a['id']).status_code==410
    result=store.reconcile()
    assert result['errors']==1 and attachment(client,item)['local_state']=='erro'
    assert get_entry(client,item)['effective_status']=='pendente_comprovante'
    with connect(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM receipt_storage_events WHERE action='arquivo_ausente_ou_integro_invalido'").fetchone()[0]==1
    store.reconcile()
    with connect(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM receipt_storage_events WHERE action='arquivo_ausente_ou_integro_invalido'").fetchone()[0]==1


def test_duplicate_upload_does_not_duplicate_object_or_history(persistent_client):
    client,_,_=persistent_client
    data=values(client); first=entry_id(send(client,data,image_upload()*2))
    a=attachment(client,first)
    assert entry_id(send(client,data,image_upload()*2))==first
    assert len(get_entry(client,first)['attachments'])==1
    assert len(list(client.app.state.receipt_storage.directory.glob('objects/*/*/*.bin')))==1
    assert attachment(client,first)['object_key']==a['object_key']
    assert len(client.app.state.receipts.storage_events(first,client.get('/api/usuario').json()['id']))==1


def test_no_overwrite_on_physical_collision(persistent_client):
    client,_,_=persistent_client
    item=upload(client); a=attachment(client,item); store=client.app.state.receipt_storage
    obj=store.record(a); final=store.paths(obj)[0]
    with pytest.raises(FileExistsError): store.put(obj,png())
    # Uma colisão de alocação deve falhar sem remover o objeto confirmado.
    assert final.exists() and final.read_bytes()==png()


def test_unauthorized_cross_mission_and_other_owner(persistent_client):
    client,google,_=persistent_client
    item=upload(client); a=attachment(client,item)
    assert client.get('/missoes/portugal/comprovantes/novo').status_code==403
    assert client.post('/missoes/portugal/comprovantes/novo',data={},files=image_upload()).status_code==403
    assert client.get('/missoes/portugal/comprovantes/'+str(item)+'/anexos/'+a['id']).status_code==403
    assert login_as(client,google,email='bruno@workspace.test',sub='synthetic-bruno').status_code==303
    assert client.get(BASE+f'/{item}').status_code==404
    assert client.get(BASE+f'/{item}/anexos/'+a['id']).status_code==404
    assert delete(client,item,a).status_code==404
    client.cookies.clear()
    assert client.get(BASE+f'/{item}/anexos/'+a['id'],follow_redirects=False).status_code==303
    assert client.post(BASE+f'/{item}/anexos/'+a['id']+'/excluir',data={}).status_code==401


def test_csrf_and_confirmed_authorized_deletion(persistent_client):
    client,_,settings=persistent_client
    item=upload(client); a=attachment(client,item); store=client.app.state.receipt_storage
    final=store.paths(store.record(a))[0]
    assert delete(client,item,a,csrf_token='invalid').status_code==403
    assert delete(client,item,a,confirm_delete='').status_code==422
    assert final.exists()
    assert delete(client,item,a).status_code==303
    assert not final.exists()
    entry=get_entry(client,item)
    assert entry['attachments'][0]['local_state']=='excluido' and entry['version']==2
    assert entry['effective_status']=='pendente_comprovante'
    assert client.get(BASE+f'/{item}/anexos/'+a['id']).status_code==410
    history=client.app.state.receipts.history(item,entry['created_by_user_id'])
    assert history[0]['acao']=='exclusao_solicitada'
    with connect(settings.database_path) as db:
        assert db.execute('SELECT COUNT(*) FROM expense_attachments').fetchone()[0]==1
        assert db.execute('SELECT delete_requested_by FROM receipt_local_objects').fetchone()[0]==entry['created_by_user_id']


def test_deletion_rejects_stale_version(persistent_client):
    client,_,_=persistent_client
    item=upload(client); a=attachment(client,item)
    assert delete(client,item,a,version=99).status_code==409
    assert attachment(client,item)['available']


def test_interrupted_deletion_finishes_during_recovery(persistent_client,monkeypatch):
    client,_,_=persistent_client
    item=upload(client); a=attachment(client,item); store=client.app.state.receipt_storage
    with monkeypatch.context() as patch:
        patch.setattr(store,'delete',lambda *args: (_ for _ in ()).throw(OSError('disco indisponível sintético')))
        assert delete(client,item,a).status_code==303
    assert attachment(client,item)['local_state']=='exclusao_pendente'
    assert not attachment(client,item)['available']
    result=store.reconcile()
    assert result['deleted']==1 and attachment(client,item)['local_state']=='excluido'


def test_db_failure_compensates_new_object(persistent_client):
    client,_,settings=persistent_client
    with connect(settings.database_path) as db:
        db.execute("CREATE TRIGGER failure_before_history BEFORE INSERT ON expense_history BEGIN SELECT RAISE(ABORT,'falha sintética'); END")
    response=send(client,values(client),image_upload())
    assert response.status_code==503
    store=client.app.state.receipt_storage
    assert list(store.directory.glob('objects/*/*/*.bin'))==[]
    with connect(settings.database_path) as db:
        assert db.execute('SELECT COUNT(*) FROM expenses').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM receipt_local_objects').fetchone()[0]==0


def test_db_failure_and_failed_compensation_have_recovery(persistent_client,monkeypatch):
    client,_,settings=persistent_client
    store=client.app.state.receipt_storage
    with connect(settings.database_path) as db:
        db.execute("CREATE TRIGGER fail_history BEFORE INSERT ON expense_history BEGIN SELECT RAISE(ABORT,'falha sintética'); END")
    with monkeypatch.context() as patch:
        patch.setattr(store,'discard',lambda *args: (_ for _ in ()).throw(OSError('falha de compensação sintética')))
        response=send(client,values(client),image_upload())
    assert response.status_code==503 and len(list(store.directory.glob('objects/*/*/*.bin')))==1
    result=store.reconcile()
    assert result['quarantined']==1 and list(store.directory.glob('objects/*/*/*.bin'))==[]
    assert len(list((store.directory/'.quarantine').glob('*.bin')))==1
    assert store.purge_quarantine()==1
    with connect(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM receipt_storage_events WHERE action='purga_sintetica_concluida'").fetchone()[0]==1


def test_committed_file_journal_recovers_after_restart(tmp_path,monkeypatch):
    settings=synthetic_settings(tmp_path/'journal.sqlite3',receipts_synthetic_enabled=True,receipts_storage_backend='local',receipts_private_dir=tmp_path/'private')
    app,google=restart(settings)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        assert login_as(client,google).status_code==303
        store=client.app.state.receipt_storage
        with monkeypatch.context() as patch:
            patch.setattr(store,'finish',lambda *args: (_ for _ in ()).throw(OSError('interrupção sintética')))
            item=upload(client)
        assert len(list((store.directory/'.journal').glob('*.json')))==1
    app,google=restart(settings)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        assert login_as(client,google).status_code==303
        assert attachment(client,item)['available']
        assert list((client.app.state.receipt_storage.directory/'.journal').glob('*.json'))==[]


@pytest.mark.parametrize('partial',[True,False])
def test_uncommitted_staging_is_quarantined(persistent_client,partial):
    client,_,_=persistent_client
    store=client.app.state.receipt_storage
    file=validate_file({'name':'sintetico.png','mime':'image/png','content':png()})
    obj=store.allocate(secrets.token_hex(16),2,123,file)
    final,stage,journal=store.paths(obj,create=True)
    store._write_new(journal,json.dumps(asdict(obj)).encode())
    store._write_new(stage,png()[:20] if partial else png())
    result=store.reconcile()
    assert result['quarantined']==1 and not stage.exists() and not final.exists()
    assert store.purge_quarantine()==1


def test_registered_complete_staging_can_finish_publication(persistent_client):
    client,_,_=persistent_client
    item=upload(client); store=client.app.state.receipt_storage; obj=store.record(attachment(client,item))
    final,stage,journal=store.paths(obj)
    store._write_new(journal,json.dumps(asdict(obj)).encode())
    final.rename(stage)
    result=store.reconcile()
    assert result['recovered']==1 and attachment(client,item)['available'] and not stage.exists()


def test_unknown_object_is_quarantined_without_public_access(persistent_client):
    client,_,_=persistent_client
    store=client.app.state.receipt_storage
    file=validate_file({'name':'sintetico.png','mime':'image/png','content':png()})
    obj=store.allocate(secrets.token_hex(16),2,456,file)
    final,_,_=store.paths(obj,create=True)
    store._write_new(final,png())
    result=store.reconcile()
    assert result['quarantined']==1 and not final.exists()
    assert client.get('/static/'+obj.object_key+'.bin').status_code==404


def test_reupload_deleted_proof_uses_new_unique_physical_key(persistent_client):
    client,_,_=persistent_client
    item=upload(client); old=attachment(client,item)
    assert delete(client,item,old).status_code==303
    data=values(client,kind='diaria',version='2')
    assert entry_id(send(client,data,image_upload(),BASE+f'/{item}/editar'))==item
    new=attachment(client,item)
    assert new['id']==old['id'] and new['object_key']!=old['object_key'] and new['available']


def test_concurrent_duplicate_submission_is_idempotent(persistent_client):
    client,_,settings=persistent_client
    mission=client.app.state.repository.get('argentina')
    raw=values(client,kind='diaria')
    data=validate_expense(raw,mission,3,load_rules())
    file=validate_file({'name':'sintetico.png','mime':'image/png','content':png()})
    user=client.get('/api/usuario').json()['id']; key=secrets.token_urlsafe(24)
    repo=client.app.state.receipts
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(repo.save,mission,data,[file],user,key) for _ in range(2)]
        ids=[future.result(timeout=20) for future in futures]
    assert ids[0]==ids[1]
    with connect(settings.database_path) as db:
        assert db.execute('SELECT COUNT(*) FROM expenses').fetchone()[0]==1
        assert db.execute('SELECT COUNT(*) FROM expense_history').fetchone()[0]==1


def test_exclusive_volume_lock(persistent_client):
    _,_,settings=persistent_client
    with pytest.raises(RuntimeError,match='bloqueio exclusivo'):
        LocalReceiptStorage(settings.database_path,settings.receipts_private_dir)


@pytest.mark.parametrize('change',[{'receipts_synthetic_enabled':False},{'dev_no_auth':True},{'google_client_id':''},{'app_env':'production'},{'receipts_private_dir':None},{'receipts_storage_backend':'drive'}])
def test_config_fails_closed(persistent_client,change):
    _,_,settings=persistent_client
    with pytest.raises(RuntimeError): replace(settings,**change).validate()


@pytest.mark.parametrize('directory',[Path('relative-private'),ROOT/'app/static/receipts',ROOT/'data/private',ROOT.parent])
def test_public_or_unsafe_volume_rejected(persistent_client,directory):
    _,_,settings=persistent_client
    with pytest.raises((RuntimeError,OSError,UnsafeTestDatabase)): replace(settings,receipts_private_dir=directory).validate()


def test_persistent_directory_cannot_escape_test_lease(persistent_client,tmp_path):
    _,_,settings=persistent_client
    outside=tmp_path.parent/'never-create-secco-private'
    with pytest.raises(UnsafeTestDatabase): LocalReceiptStorage(settings.database_path,outside)
    assert not outside.exists()


def test_directory_existence_does_not_activate_backend(tmp_path):
    folder=tmp_path/'unactivated'; folder.mkdir()
    settings=synthetic_settings(tmp_path/'disabled.sqlite3',receipts_private_dir=folder)
    app,google=restart(settings)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        assert login_as(client,google).status_code==303
        assert client.get(BASE+'/novo').status_code==503
        assert not hasattr(app.state,'receipt_storage')
    assert list(folder.iterdir())==[]


def test_path_traversal_and_record_scope_rejected(persistent_client):
    client,_,_=persistent_client
    item=upload(client); a=attachment(client,item); store=client.app.state.receipt_storage
    obj=store.record(a)
    with pytest.raises(OSError): store.paths(replace(obj,object_key='../escape'))
    with pytest.raises(OSError): store.paths(replace(obj,mission_id=-1))
    with pytest.raises(OSError): store.read_attachment({**a,'mission_id':1})
    assert store.read_attachment(a)==png()


def test_volume_marker_mismatch_fails_without_adoption(tmp_path):
    settings=synthetic_settings(tmp_path/'marker.sqlite3',receipts_synthetic_enabled=True,receipts_storage_backend='local',receipts_private_dir=tmp_path/'volume')
    app,google=restart(settings)
    with TestClient(app,base_url='http://127.0.0.1'): pass
    marker=settings.receipts_private_dir/'.volume.json'
    marker.write_text(json.dumps({'format':1,'id':'f'*48}),encoding='utf-8')
    with pytest.raises(RuntimeError,match='não corresponde'):
        LocalReceiptStorage(settings.database_path,settings.receipts_private_dir)


def test_idempotent_migration_and_sync_success_is_impossible(persistent_client):
    client,_,settings=persistent_client
    item=upload(client)
    migrate(settings.database_path); migrate(settings.database_path)
    assert attachment(client,item)['available']
    with connect(settings.database_path) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert db.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0]==8
    for sql in ("UPDATE receipt_local_objects SET sync_state='sincronizado'","UPDATE receipt_local_objects SET remote_reference='drive-falso'"):
        with pytest.raises(sqlite3.IntegrityError):
            with connect(settings.database_path) as db: db.execute(sql)


def test_original_participants_and_funding_are_unchanged(persistent_client):
    client,_,settings=persistent_client
    upload(client)
    with connect(settings.database_path) as db:
        assert db.execute('SELECT COUNT(*) FROM participants').fetchone()[0]==4
        assert [(r[0],r[1]) for r in db.execute('SELECT participant_id,financiado_pela_subvencao FROM mission_participants ORDER BY participant_id')]==[(1,1),(2,0),(3,0),(4,1)]


def test_post_commit_journal_error_does_not_delete_confirmed_file(persistent_client,monkeypatch):
    client,_,settings=persistent_client
    store=client.app.state.receipt_storage
    with monkeypatch.context() as patch:
        patch.setattr(store,'finish',lambda *args: (_ for _ in ()).throw(ValueError('journal sintético interrompido')))
        item=upload(client)
    assert attachment(client,item)['available'] and attachment(client,item)['local_state']=='armazenado'
    assert len(list((store.directory/'.journal').glob('*.json')))==1
    assert store.reconcile()['recovered']==1
    assert attachment(client,item)['available']


def test_link_in_private_path_is_refused_without_creation(tmp_path,monkeypatch):
    import app.core.storage_paths as module
    directory=tmp_path/'linked-volume'
    settings=synthetic_settings(tmp_path/'paths.sqlite3',receipts_synthetic_enabled=True,receipts_storage_backend='local',receipts_private_dir=directory)
    original=Path.is_symlink
    monkeypatch.setattr(Path,'is_symlink',lambda self: True if self==directory else original(self))
    with pytest.raises(OSError,match='Links não são permitidos'):
        settings.validate()
    assert not directory.exists()
