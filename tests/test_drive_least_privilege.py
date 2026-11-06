"""Revisão 07C: menor privilégio, API inteiramente simulada e nenhuma migração."""
from dataclasses import replace
import time

import httpx
import pytest

from app.core.drive_config import DRIVE_IDS
from app.services.google_drive_storage import FOLDER_FIELDS
from app.services.drive_supervised import SCOPE_FILE, SCOPE_METADATA
from app.services.storage_contracts import DriveError
from test_drive_probe import probe, no_network


def test_all_fourteen_folders_use_files_get_and_exact_fields(probe):
    journal,api,adapter,archive=probe
    journal.preflight(adapter)
    folders={i for categories in journal.configuration.folders().values() for i in categories.values()}
    folder_gets=[(path,params) for method,path,params in api.requests
                 if method=='GET' and path.rsplit('/',1)[-1] in folders]
    assert len(folder_gets)==14
    assert {path.rsplit('/',1)[-1] for path,_ in folder_gets}==folders
    for path,params in folder_gets:
        assert params=={'supportsAllDrives':'true','fields':FOLDER_FIELDS}
    assert FOLDER_FIELDS=='id,name,mimeType,parents,driveId,trashed,capabilities(canAddChildren)'
    assert not any('/drives/' in path for _,path,_ in api.requests)
    assert api.post_count==api.generated==0


@pytest.mark.parametrize('mission',['argentina','portugal'])
def test_drives_get_is_not_an_allowed_transport_operation(probe,mission):
    journal,api,adapter,archive=probe
    with pytest.raises(DriveError,match='destino'):
        adapter.client.get('https://www.googleapis.com/drive/v3/drives/'+DRIVE_IDS[mission])
    assert api.requests==[]


def test_swapping_drive_configuration_is_rejected_before_metadata(probe):
    journal,api,adapter,archive=probe
    config=adapter.configuration
    adapter.configuration=replace(config,argentina=config.portugal,portugal=config.argentina)
    with pytest.raises(DriveError,match='destino'):
        adapter.preflight_destination(journal.plan()['argentina'],require_write=True)
    assert api.requests==[]


def test_narrow_scopes_and_two_fixed_pngs_remain_bound_to_approval(probe):
    journal,api,adapter,archive=probe
    permit=adapter.probe_transport.approval
    assert permit.scopes==(SCOPE_FILE,SCOPE_METADATA)
    assert set(journal.contents())=={'argentina','portugal'}
    assert all(len(content)==69 for content in journal.contents().values())
    assert journal.run(adapter,archive)
    assert len(api.files)==api.post_count==2
    assert adapter.probe_transport.approval==permit
    assert journal.run(adapter,archive)
    assert api.post_count==api.generated==2


def test_sha256_is_independent_of_application_metadata(probe):
    journal,api,adapter,archive=probe
    assert journal.run(adapter,archive)
    # A aplicação não envia o hash no JSON ou em appProperties.
    assert len(api.create_metadata)==2
    for metadata in api.create_metadata:
        assert set(metadata)=={'id','name','parents','mimeType','appProperties'}
        assert set(metadata['appProperties'])=={'secco_sync','secco_mission'}
    # API simulada computa SHA-256 dos bytes recebidos, não de um hash enviado no JSON.
    for row in journal.rows():
        remote=api.files[row['remote_id']]
        assert remote['sha256Checksum']==journal.plan()[row['mission']].checksum
    file_gets=[params for method,path,params in api.requests
               if method=='GET' and path.rsplit('/',1)[-1] in api.files]
    assert file_gets and all('sha256Checksum' in params['fields'] for params in file_gets)


def test_valid_idempotency_tag_cannot_replace_missing_remote_sha256(probe):
    journal,api,adapter,archive=probe
    assert journal.run(adapter,archive)
    api.checksum_override=''
    # As tags appProperties continuam válidas; a falta do campo de integridade reprova.
    assert journal.run(adapter,archive) is False
    assert journal.rows()[0]['error_code']=='integridade'
    assert api.post_count==2


def test_echoed_hash_in_create_acknowledgement_does_not_override_remote_mismatch(probe):
    journal,api,adapter,archive=probe
    api.checksum_override='0'*64
    original=api.__call__
    def echo(request):
        result=original(request)
        if request.method=='POST':
            data=result.json()
            data['sha256Checksum']=journal.plan()['argentina'].checksum
            return httpx.Response(result.status_code,json=data)
        return result
    # Substitui só o transporte mock interno, mantendo todos os gates reais do executor.
    adapter.probe_transport.inner=httpx.MockTransport(echo)
    assert journal.run(adapter,archive) is False
    assert journal.rows()[0]['error_code']=='integridade'
    assert api.post_count==1


def test_upload_permission_denied_stops_after_first_post_without_scope_change(probe):
    journal,api,adapter,archive=probe
    scopes=adapter.probe_transport.approval.scopes
    original=api.__call__
    denied=[]
    def deny(request):
        if request.method=='POST':
            denied.append(request)
            return httpx.Response(403,json={'error':{'message':'SYNTHETIC-INSUFFICIENT-PERMISSION'}})
        return original(request)
    adapter.probe_transport.inner=httpx.MockTransport(deny)
    assert journal.run(adapter,archive) is False
    assert len(denied)==1 and api.files=={}
    rows=journal.rows()
    assert rows[0]['error_code']=='permissao' and rows[0]['remote_id']
    assert rows[1]['state']=='aguardando' and rows[1]['remote_id'] is None
    assert adapter.probe_transport.approval.scopes==scopes==(SCOPE_FILE,SCOPE_METADATA)


def test_approval_expiration_stops_even_after_plan_was_prepared(probe):
    journal,api,adapter,archive=probe
    adapter.probe_transport.approval=replace(adapter.probe_transport.approval,expires_at=time.time()-1)
    with pytest.raises(DriveError,match='autorizacao'): journal.run(adapter,archive)
    assert api.requests==[]


@pytest.mark.parametrize('changes',[{'checksum':None},{'checksum':''},{'size_bytes':0},{'size_bytes':True}])
def test_missing_local_integrity_metadata_cannot_validate_absent_remote_hash(probe,changes):
    journal,api,adapter,archive=probe
    item=replace(journal.plan()['argentina'],**changes)
    with pytest.raises(DriveError,match='destino'):
        adapter.verify(item,idempotency_key='a'*64,remote_id='synthetic_reserved')
    assert api.requests==[]
