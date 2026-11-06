"""07C: SQLite concedido, schema próprio sem 008, arquivos e HTTP sintéticos."""
from dataclasses import replace
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
from threading import RLock
import time
from types import SimpleNamespace
import zipfile

import httpx
import pytest

from app.db.connection import connect
from app.services.drive_probe import ProbeArchiveLock, ProbeJournal
from app.services.drive_supervised import (
    GcloudSourceCredentials, ImpersonatedProbeCredentials, ProbeApproval, ProbeHTTPTransport,
    SCOPE_FILE, SCOPE_METADATA, SupervisedProbeAdapter, mapping_digest, plan_digest, probe_png,
)
from app.services.storage_contracts import DriveError
from app.services.receipt_drive_sync import ReceiptDriveSync
from scripts.drive_probe import main
from test_drive_folder_mapping import configuration, MetadataAPI, DRIVES, FOLDERS


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket
    def blocked(*a,**k): raise AssertionError('Rede real proibida no teste 07C.')
    monkeypatch.setattr(socket.socket,'connect',blocked)


def approval(config,items=None):
    return ProbeApproval('APROVACAO-FICTICIA-DE-TESTE','operator@workspace.test',time.time()+1800,
        mapping_digest(config),(SCOPE_FILE,SCOPE_METADATA),True,True,True,
        plan_sha256=plan_digest(items) if items else '0'*64)


class Credentials:
    def access_token(self):
        from app.services.drive_credentials import DriveAccessToken
        return DriveAccessToken('SYNTHETIC-METADATA-ONLY',time.time()+300)


class ProbeAPI(MetadataAPI):
    def __init__(self):
        super().__init__()
        self.files={}
        self.post_count=0
        self.generated=0
        self.after_create=None
        self.status=None
        self.checksum_override=None
        self.can_add=True
        self.unsafe_acl=False
        self.requests=[]
        self.create_metadata=[]

    def __call__(self,request):
        path=request.url.path
        self.requests.append((request.method,path,dict(request.url.params)))
        assert not path.startswith('/drive/v3/drives/')
        if self.status: return httpx.Response(self.status,json={'sensitive':'NEVER-EXPOSE'})
        if path.endswith('/generateIds'):
            self.generated+=1
            return httpx.Response(200,json={'ids':['probe_reserved_'+str(self.generated)]})
        if request.method=='POST':
            assert path=='/upload/drive/v3/files'
            self.post_count+=1
            msg=BytesParser(policy=policy.default).parsebytes(
                ('Content-Type: '+request.headers['content-type']+'\r\n\r\n').encode()+request.content)
            parts=list(msg.iter_parts())
            metadata=json.loads(parts[0].get_payload(decode=True))
            self.create_metadata.append(metadata)
            content=parts[1].get_payload(decode=True)
            identifier=metadata['id']
            if identifier in self.files: return httpx.Response(409,json={})
            mission=metadata['appProperties']['secco_mission']
            assert content==probe_png(mission)
            self.files[identifier]={**metadata,'driveId':DRIVES[mission],'size':str(len(content)),
                'sha256Checksum':hashlib.sha256(content).hexdigest(),'trashed':False}
            if self.after_create=='timeout': raise httpx.ReadTimeout('NEVER-EXPOSE',request=request)
            if self.after_create=='interrupt': raise SystemExit('interrupção sintética')
            return httpx.Response(200,json={'id':identifier})
        identifier=path.rsplit('/',1)[1]
        if path.endswith('/permissions'):
            resource=path.split('/')[-2]
            if self.unsafe_acl:
                return httpx.Response(200,json={'permissions':[{'type':'anyone','role':'reader'}]})
            if resource in self.files:
                mission=self.files[resource]['appProperties']['secco_mission']
                folder=next(folder_id for m,category,name,folder_id in FOLDERS if m==mission and category=='deslocamentos')
                request=httpx.Request('GET','https://www.googleapis.com/drive/v3/files/'+folder+'/permissions',
                    params=dict(request.url.params),headers=dict(request.headers))
        if identifier in self.files:
            data=dict(self.files[identifier])
            if self.checksum_override is not None: data['sha256Checksum']=self.checksum_override
            return httpx.Response(200,json=data)
        if identifier in self.folders:
            return httpx.Response(200,json={**self.folders[identifier],
                'capabilities':{'canAddChildren':self.can_add}})
        return super().__call__(request)


@pytest.fixture
def probe(tmp_path):
    config=configuration()
    journal=ProbeJournal.create(tmp_path/'probe',config)
    api=ProbeAPI()
    permit=approval(config,journal.plan())
    adapter=SupervisedProbeAdapter(config,Credentials(),permit,journal.plan(),journal.contents(),inner=httpx.MockTransport(api))
    yield journal,api,adapter,tmp_path/'backup.zip'
    adapter.close()


@pytest.mark.parametrize('changes',[
    {'approved':False},{'synthetic_only':False},{'backup_verified':False},
    {'expires_at':time.time()-10},{'mapping_sha256':'0'*64},{'reference':''},
    {'scopes':(SCOPE_METADATA,)},{'scopes':(SCOPE_FILE,'https://www.googleapis.com/auth/drive.readonly')},
    {'scopes':('https://www.googleapis.com/auth/drive',)},
    {'cleanup':'delete'},{'operator_account':'operator & shell'},
    {'operator_account':'source@project.iam.gserviceaccount.com'},
])
def test_approval_is_required_before_transport(changes):
    config=configuration()
    with pytest.raises(DriveError,match='autorizacao'):
        replace(approval(config),**changes).validate(config)


def test_two_synthetic_uploads_and_retries_use_same_ids(probe):
    journal,api,adapter,archive=probe
    assert journal.run(adapter,archive)
    first=[r['remote_id'] for r in journal.rows()]
    assert len(api.files)==api.post_count==api.generated==2
    assert journal.run(adapter,archive)
    assert [r['remote_id'] for r in journal.rows()]==first
    assert api.post_count==api.generated==2
    assert all(r['state']=='verificado' for r in journal.rows())


@pytest.mark.parametrize('phase',['timeout','interrupt'])
def test_backup_restore_after_lost_confirmation_keeps_remote_id(probe,tmp_path,phase):
    journal,api,adapter,archive=probe
    api.after_create=phase
    if phase=='interrupt':
        with pytest.raises(SystemExit): journal.run(adapter,archive)
    else:
        assert journal.run(adapter,archive) is False
    identifier=journal.rows()[0]['remote_id']
    assert identifier in api.files
    restored=ProbeJournal.restore(archive,tmp_path/'restored',journal.configuration)
    assert restored.rows()[0]['remote_id']==identifier
    api.after_create=None
    second=SupervisedProbeAdapter(restored.configuration,Credentials(),approval(restored.configuration,restored.plan()),
        restored.plan(),restored.contents(),inner=httpx.MockTransport(api))
    try:
        assert restored.run(second,archive)
        assert len(api.files)==api.post_count==api.generated==2
        assert restored.contents()==journal.contents()
    finally: second.close()


def test_backup_api_restores_confirmed_journal_and_volume_marker(probe,tmp_path):
    journal,api,adapter,archive=probe
    assert journal.run(adapter,archive)
    restored=ProbeJournal.restore(archive,tmp_path/'restored',journal.configuration)
    assert restored.rows()==journal.rows()
    assert restored.contents()==journal.contents()
    assert (restored.directory/'.volume.json').read_bytes()==(journal.directory/'.volume.json').read_bytes()
    with connect(restored.database_path) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert db.execute("SELECT name FROM sqlite_master WHERE name='schema_migrations'").fetchone() is None


@pytest.mark.parametrize('target',['argentina.png','.volume.json','probe.sqlite3','missing','traversal'])
def test_restore_rejects_incomplete_tampered_or_path_traversal_archive(probe,tmp_path,target):
    journal,api,adapter,archive=probe
    journal.checkpoint(archive)
    with zipfile.ZipFile(archive) as original:
        files={n:original.read(n) for n in original.namelist()}
    if target=='missing': files.pop('portugal.png')
    elif target=='traversal': files['../escape.txt']=b'no'
    else: files[target]=b'corrompido'
    broken=tmp_path/'broken.zip'
    with zipfile.ZipFile(broken,'w') as output:
        for name,content in files.items(): output.writestr(name,content)
    with pytest.raises(DriveError,match='backup'):
        ProbeJournal.restore(broken,tmp_path/'rejected',journal.configuration)
    assert not (tmp_path/'rejected').exists()


def test_restore_rejects_wrong_mission_configuration(probe,tmp_path):
    journal,api,adapter,archive=probe
    journal.checkpoint(archive)
    mapping=journal.configuration.folders()
    mapping['argentina']['diarias']='synthetic_wrong_id'
    with pytest.raises(DriveError,match='destino'):
        ProbeJournal.restore(archive,tmp_path/'wrong-map',replace(journal.configuration,folders_json=json.dumps(mapping)))


def test_backup_failure_happens_before_remote_create(probe,monkeypatch):
    journal,api,adapter,archive=probe
    monkeypatch.setattr(journal,'checkpoint',lambda *a: (_ for _ in ()).throw(OSError('backup indisponível')))
    with pytest.raises(OSError): journal.run(adapter,archive)
    assert api.post_count==0 and api.files=={}


@pytest.mark.parametrize('status',[401,403,429,500])
def test_http_failure_never_claims_success_or_discards_local(probe,status):
    journal,api,adapter,archive=probe
    api.status=status
    with pytest.raises(DriveError): journal.run(adapter,archive)
    assert api.post_count==0
    assert journal.contents()=={m:probe_png(m) for m in ('argentina','portugal')}


def test_capability_and_inherited_public_acl_block_before_create(probe):
    journal,api,adapter,archive=probe
    api.can_add=False
    with pytest.raises(DriveError,match='permissao'): journal.run(adapter,archive)
    api.can_add=True; api.unsafe_acl=True
    with pytest.raises(DriveError,match='permissao'): journal.run(adapter,archive)
    assert api.post_count==api.generated==0


def test_missing_sha256_and_deleted_confirmed_file_do_not_recreate(probe):
    journal,api,adapter,archive=probe
    assert journal.run(adapter,archive)
    identifier=journal.rows()[0]['remote_id']
    del api.files[identifier]
    assert journal.run(adapter,archive) is False
    assert journal.run(adapter,archive) is False
    assert api.post_count==2
    assert journal.rows()[0]['error_code']=='integridade'


def test_sha256_absent_stays_pending_and_reconciles_without_duplicate(probe):
    journal,api,adapter,archive=probe
    api.checksum_override=''
    assert journal.run(adapter,archive) is False
    assert journal.rows()[0]['state']=='erro' and api.post_count==1
    api.checksum_override=None
    assert journal.run(adapter,archive)
    assert api.post_count==2


@pytest.mark.parametrize('method,url',[
    ('DELETE','https://www.googleapis.com/drive/v3/files/anything'),
    ('PATCH','https://www.googleapis.com/drive/v3/files/anything'),
    ('POST','https://www.googleapis.com/drive/v3/files/anything/permissions'),
    ('GET','https://www.googleapis.com/drive/v3/files'),
    ('GET','https://evil.test/drive/v3/files/anything'),
    ('GET','http://www.googleapis.com/drive/v3/files/anything'),
])
def test_transport_blocks_unapproved_operations_before_network(probe,method,url):
    journal,api,adapter,archive=probe
    with pytest.raises(DriveError,match='destino'):
        adapter.client.request(method,url)


def test_download_and_arbitrary_content_are_blocked(probe):
    journal,api,adapter,archive=probe
    folder=journal.configuration.folders()['argentina']['passagens']
    with pytest.raises(DriveError): adapter.client.get('https://www.googleapis.com/drive/v3/files/'+folder,params={'alt':'media'})
    with pytest.raises(DriveError,match='sintetico'):
        SupervisedProbeAdapter(journal.configuration,Credentials(),approval(journal.configuration,journal.plan()),
            journal.plan(),{'argentina':b'arbitrary','portugal':probe_png('portugal')},inner=httpx.MockTransport(api))


def test_redirect_does_not_follow_or_create(probe):
    journal,api,adapter,archive=probe
    api.status=302
    with pytest.raises(DriveError,match='remoto'): journal.run(adapter,archive)
    assert api.post_count==0


def test_iam_temporary_token_is_scoped_cached_and_not_logged(caplog):
    config=configuration(); permit=approval(config); calls=[]
    def iam(request):
        calls.append(request)
        assert request.url.host=='iamcredentials.googleapis.com'
        assert json.loads(request.content)=={'scope':list(permit.scopes),'lifetime':'900s'}
        return httpx.Response(200,json={'accessToken':'SYNTHETIC-TARGET-TOKEN',
            'expireTime':datetime.fromtimestamp(time.time()+900,timezone.utc).isoformat()})
    source=SimpleNamespace(source_token=lambda:'SYNTHETIC-SOURCE-TOKEN')
    provider=ImpersonatedProbeCredentials(source,permit,config,transport=httpx.MockTransport(iam))
    caplog.set_level('DEBUG')
    try:
        assert provider.access_token() is provider.access_token()
        assert len(calls)==1
        assert 'SYNTHETIC' not in repr(provider.cached)
        assert 'SYNTHETIC' not in caplog.text
        assert 'iamcredentials.googleapis.com' not in caplog.text
    finally: provider.close()
    assert provider.cached is None


@pytest.mark.parametrize('disabled,code',[(True,'iam_api_desativada'),(False,'iam_get_access_token')])
def test_iam_permissions_fail_without_escalation(disabled,code):
    details=[{'reason':'SERVICE_DISABLED'}] if disabled else []
    provider=ImpersonatedProbeCredentials(SimpleNamespace(source_token=lambda:'SYNTHETIC-SOURCE'),
        approval(configuration()),configuration(),transport=httpx.MockTransport(
            lambda request:httpx.Response(403,json={'error':{'details':details,'message':'NEVER-EXPOSE'}})))
    try:
        with pytest.raises(DriveError,match=code): provider.access_token()
    finally: provider.close()


def test_gcloud_captures_token_without_shell_argument_or_file(monkeypatch):
    calls=[]
    def run(command,**kwargs):
        calls.append((command,kwargs))
        return SimpleNamespace(returncode=0,stdout='SYNTHETIC-SOURCE-TOKEN\n',stderr='')
    monkeypatch.setattr('subprocess.run',run)
    monkeypatch.setenv('CLOUDSDK_AUTH_ACCESS_TOKEN','NEVER-REUSE')
    monkeypatch.setenv('CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT','NEVER-IMPERSONATE-IMPLICITLY')
    monkeypatch.setenv('CLOUDSDK_CORE_TRACE_TOKEN','NEVER-TRACE')
    assert GcloudSourceCredentials('operator@workspace.test').source_token()=='SYNTHETIC-SOURCE-TOKEN'
    command,kwargs=calls[0]
    assert 'print-access-token' in command and not any('login' in x for x in command)
    assert 'NEVER-REUSE' not in kwargs['env'].values()
    assert 'NEVER-IMPERSONATE-IMPLICITLY' not in kwargs['env'].values()
    assert 'NEVER-TRACE' not in kwargs['env'].values()
    assert kwargs['capture_output'] and kwargs['check'] is False and 'shell' not in kwargs
    assert kwargs['env']['CLOUDSDK_CORE_DISABLE_FILE_LOGGING']=='true'
    assert kwargs['env']['CLOUDSDK_CORE_LOG_HTTP']=='false'


def test_cli_default_is_offline_and_real_requires_approval(tmp_path,monkeypatch,capsys):
    mapping=tmp_path/'folders.json'
    mapping.write_text(json.dumps(configuration().folders()),encoding='utf-8')
    archive=tmp_path/'backup.zip'
    def forbidden(*a,**k): raise AssertionError('Credenciais reais proibidas.')
    monkeypatch.setattr('subprocess.run',forbidden)
    assert main(['--mapping',str(mapping),'--archive',str(archive)])==0
    output=json.loads(capsys.readouterr().out)
    assert output['mode']=='offline' and len(output['items'])==2 and archive.exists()
    assert main(['--mapping',str(mapping),'--archive',str(archive),'--resume'])==0
    capsys.readouterr()
    assert main(['--mapping',str(mapping),'--archive',str(archive),'--resume','--execute-authorized'])==2
    assert json.loads(capsys.readouterr().out)['code']=='autorizacao'


def test_application_reconcile_never_recreates_once_confirmed(tmp_path):
    # Schema mínimo de teste, criado diretamente. Nenhum arquivo de migração é executado.
    database=tmp_path/'regression.sqlite3'
    with connect(database) as db:
        db.executescript('''CREATE TABLE receipt_drive_sync(attachment_id TEXT PRIMARY KEY,state TEXT,
            remote_id TEXT,idempotency_key TEXT,category TEXT,error_code TEXT,verified_at TEXT,attempts INT,updated_at TEXT);
            CREATE TABLE receipt_drive_events(id INTEGER PRIMARY KEY,attachment_id TEXT,state TEXT,error_code TEXT);
            INSERT INTO receipt_drive_sync VALUES('a','erro','reserved_original','key','deslocamentos',NULL,NULL,1,NULL);
            INSERT INTO receipt_drive_events(attachment_id,state) VALUES('a','verificado');''')
    worker=ReceiptDriveSync.__new__(ReceiptDriveSync)
    worker.database_path=database
    from app.services.storage_contracts import StoredReceipt
    record=StoredReceipt('a'*32,2,1,'b'*64,'c'*64,1,'png','image/png')
    worker.storage=SimpleNamespace(lock=RLock(),read_attachment=lambda item:b'x',record=lambda item:record)
    worker._load=lambda db,identifier:{'created_by_user_id':1,'mission_code':'argentina','official_name':'synthetic.png','checksum':'c'*64}
    worker._snapshot=lambda *a:None
    worker._authorized=lambda *a:None
    calls=[]
    worker.adapter=SimpleNamespace(verify=lambda *a,**k:None,upload=lambda *a,**k:calls.append('UPLOAD'))
    assert worker.run_one('a')==worker.run_one('a')=='erro'
    assert calls==[]


def test_approval_cannot_be_used_for_another_plan(probe):
    journal,api,adapter,archive=probe
    with pytest.raises(DriveError,match='autorizacao'):
        SupervisedProbeAdapter(journal.configuration,Credentials(),approval(journal.configuration),
            journal.plan(),journal.contents(),inner=httpx.MockTransport(api))


def test_archive_lock_prevents_concurrent_execution(tmp_path):
    archive=tmp_path/'probe.zip'
    with ProbeArchiveLock(archive):
        with pytest.raises(DriveError,match='ensaio_em_uso'):
            with ProbeArchiveLock(archive): pass
    with ProbeArchiveLock(archive): pass


def test_permission_pages_and_scope_gate_are_not_bypassed(probe):
    journal,api,adapter,archive=probe
    folder=journal.configuration.folders()['argentina']['passagens']
    with pytest.raises(DriveError):
        adapter.client.get('https://www.googleapis.com/drive/v3/files/'+folder,
                           params={'useDomainAdminAccess':'true'})
    assert adapter.reserve_id() and adapter.reserve_id()
    with pytest.raises(DriveError): adapter.reserve_id()
    assert api.generated==2


def test_cli_rejects_expired_approval_before_source_credentials(tmp_path,monkeypatch,capsys):
    config=configuration()
    journal=ProbeJournal.create(tmp_path/'probe',config)
    archive=tmp_path/'backup.zip'
    journal.checkpoint(archive)
    from dataclasses import asdict
    data=asdict(approval(config,journal.plan()))
    data['expires_at']=datetime.fromtimestamp(time.time()-60,timezone.utc).isoformat()
    permit=tmp_path/'approval.json'; permit.write_text(json.dumps(data),encoding='utf-8')
    mapping=tmp_path/'folders.json'; mapping.write_text(json.dumps(config.folders()),encoding='utf-8')
    def forbidden(*a,**k): raise AssertionError('Credenciais não devem ser acessadas.')
    monkeypatch.setattr('subprocess.run',forbidden)
    before=archive.read_bytes()
    assert main(['--mapping',str(mapping),'--archive',str(archive),'--resume',
                 '--execute-authorized','--approval',str(permit)])==2
    assert json.loads(capsys.readouterr().out)['code']=='autorizacao'
    assert archive.read_bytes()==before


def test_transport_binding_rejects_idempotency_key_outside_plan(probe):
    journal,api,adapter,archive=probe
    with pytest.raises(DriveError):
        adapter.probe_transport.bind('argentina','valid_reserved_id','0'*64)


def test_expired_target_token_is_renewed_in_memory():
    calls=[]
    def iam(request):
        calls.append(request)
        return httpx.Response(200,json={'accessToken':'SYNTHETIC-TARGET-TOKEN',
            'expireTime':datetime.fromtimestamp(time.time()+900,timezone.utc).isoformat()})
    provider=ImpersonatedProbeCredentials(SimpleNamespace(source_token=lambda:'SYNTHETIC-SOURCE'),
        approval(configuration()),configuration(),transport=httpx.MockTransport(iam))
    try:
        provider.access_token()
        provider.cached=replace(provider.cached,expires_at=time.time()-1)
        assert provider.access_token().expires_at>time.time()+30
        assert len(calls)==2
    finally: provider.close()


def test_interruption_before_post_restores_reserved_id(probe,tmp_path,monkeypatch):
    journal,api,adapter,archive=probe
    with monkeypatch.context() as patch:
        patch.setattr(adapter,'upload',lambda *a,**k: (_ for _ in ()).throw(SystemExit()))
        with pytest.raises(SystemExit): journal.run(adapter,archive)
    assert api.post_count==0 and api.generated==1
    restored=ProbeJournal.restore(archive,tmp_path/'restore-before-post',journal.configuration)
    assert restored.rows()[0]['remote_id']=='probe_reserved_1'
    assert restored.run(adapter,archive)
    assert api.generated==api.post_count==2


@pytest.mark.parametrize('wrong',['content','folder','name','mime'])
def test_create_guard_rejects_tampered_payload_before_inner_transport(probe,wrong):
    journal,api,adapter,archive=probe
    item=journal.plan()['argentina']
    key=item.object_key
    adapter.probe_transport.bind('argentina','probe_reserved_1',key)
    metadata={'id':'probe_reserved_1','name':item.official_name,
        'parents':[journal.configuration.folders()['argentina']['deslocamentos']],
        'mimeType':'image/png','appProperties':{'secco_sync':key,'secco_mission':'argentina'}}
    content=probe_png('argentina')
    if wrong=='content': content=b'conteudo sintetico divergente'
    elif wrong=='folder': metadata['parents']=[journal.configuration.folders()['portugal']['deslocamentos']]
    elif wrong=='name': metadata['name']='outro.png'
    else: metadata['mimeType']='application/vnd.google-apps.folder'
    body=(b'--test\r\nContent-Type: application/json\r\n\r\n'+json.dumps(metadata).encode()
        +b'\r\n--test\r\nContent-Type: image/png\r\n\r\n'+content+b'\r\n--test--\r\n')
    with pytest.raises(DriveError,match='sintetico'):
        adapter.client.post('https://www.googleapis.com/upload/drive/v3/files',content=body,
            headers={'Content-Type':'multipart/related; boundary=test'},
            params={'supportsAllDrives':'true','uploadType':'multipart'})
    assert api.post_count==0


def test_backup_marker_semantic_mismatch_rejected_even_with_valid_manifest(probe,tmp_path):
    journal,api,adapter,archive=probe
    journal.checkpoint(archive)
    with zipfile.ZipFile(archive) as source:
        files={n:source.read(n) for n in source.namelist()}
    files['.volume.json']=json.dumps({'id':'wrong','run_id':'a'*16}).encode()
    files['manifest.json']=json.dumps({name:{'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)}
        for name,content in files.items() if name!='manifest.json'}).encode()
    broken=tmp_path/'broken.zip'
    with zipfile.ZipFile(broken,'w') as output:
        for name,content in files.items(): output.writestr(name,content)
    with pytest.raises(DriveError,match='backup'):
        ProbeJournal.restore(broken,tmp_path/'bad-marker',journal.configuration)


def test_supervised_adapter_preserves_controlled_iam_failure(probe):
    journal,api,adapter,archive=probe
    def failed(): raise DriveError('iam_get_access_token')
    adapter.credentials=SimpleNamespace(access_token=failed)
    with pytest.raises(DriveError,match='iam_get_access_token'): journal.run(adapter,archive)
    assert api.calls==[] and api.generated==0
