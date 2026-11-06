"""Renovação append-only, sem Google, usando v2 preservada e journal compartilhado."""
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from scripts.build_drive_cloud_shell_package import ROOT
from test_drive_cloud_shell_package import package,policy_input,require_private_artifacts,run


@pytest.fixture
def previous(tmp_path):
    require_private_artifacts('artifacts/stage07c/cloud-shell-v2/secco-drive-07c-cloud-shell-v2.zip')
    root=tmp_path/'v2'
    root.mkdir()
    with zipfile.ZipFile(ROOT/'artifacts/stage07c/cloud-shell-v2/secco-drive-07c-cloud-shell-v2.zip') as z:
        assert hashlib.sha256(z.read('MANIFEST.json')).hexdigest()=='89ed1e3a19a658468cd74f9562baa0f4dd73be96a5a973a73d389118b89e62de'
        z.extractall(root)
    return root


OFFLINE=r'''
import builtins,contextlib,hashlib,io,json,socket,subprocess,sys
import probe
def denied(*a,**k): raise AssertionError('real network/credentials forbidden')
socket.socket.connect=denied; socket.socket.connect_ex=denied; subprocess.run=denied
builtins.input=lambda prompt:sys.stdin.readline().rstrip('\n')
probe.sys.platform='linux' # Gate somente, não é execução de kernel Linux.
def call(args):
    output=io.StringIO()
    with contextlib.redirect_stdout(output): status=probe.main(args)
    data=json.loads(output.getvalue())
    print(json.dumps(data))
    return status,data
'''

SETUP=OFFLINE+r'''
assert call(['prepare'])[0]==0
assert call(['configure-policy'])[0]==0
assert call(['authorize','--operator','operator@workspace.test','--reference','FIRST-EXPLICIT-TEST-APPROVAL'])[0]==0
import httpx
import app.services.drive_supervised as supervised
class Source:
    def __init__(self,*a): pass
    def source_token(self): return 'SYNTHETIC-SOURCE-TOKEN'
Original=supervised.ImpersonatedProbeCredentials
class IAMDenied(Original):
    def __init__(self,*a,**k):
        super().__init__(*a,**k,transport=httpx.MockTransport(lambda request:httpx.Response(403,json={'error':{'details':[]}})))
supervised.GcloudSourceCredentials=Source
supervised.ImpersonatedProbeCredentials=IAMDenied
status,data=call(['execute','--confirm-write'])
assert status==2 and data['code']=='iam_get_access_token'
'''


def setup_previous(previous):
    result=run(previous,code=SETUP,stdin=policy_input()+'AUTORIZO CLOUD SHELL 07C\n')
    assert result.returncode==0,result.stdout+result.stderr


def hashes(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def test_v2_complete_flow_reproduces_exact_eexist_file_and_misleading_phase(previous):
    code=SETUP+r'''
before={name:hashlib.sha256((probe.ROOT/name).read_bytes()).hexdigest() for name in
        ('.local/approval.json','.local/access-policy.json','evidence/probe-state.zip','evidence/session.json','evidence/offline-check.json')}
original_write=probe.write_new
attempted=[]
def tracked(path,data):
    attempted.append(str(path.relative_to(probe.ROOT)).replace('\\','/'))
    return original_write(path,data)
probe.write_new=tracked
status,data=call(['authorize','--operator','operator@workspace.test','--reference','SECOND-EXPLICIT-TEST-APPROVAL'])
assert status==2
assert data=={'result':'stopped','code':'configuracao_ou_backup','phase':'prepare_offline_report_write','error_type':'FileExistsError','errno':17}
assert attempted==['.local/approval.json']
assert before=={name:hashlib.sha256((probe.ROOT/name).read_bytes()).hexdigest() for name in before}
print(json.dumps({'failed_file':attempted[0],'operation':'os.open: O_WRONLY|O_CREAT|O_EXCL','preserved':True}))
'''
    result=run(previous,code=code,stdin=policy_input()+'AUTORIZO CLOUD SHELL 07C\n'*2)
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout.splitlines()[-1])['failed_file']=='.local/approval.json'


def resume_script(previous):
    return OFFLINE+f"\nprobe.select_state({str(previous)!r})\n"


def test_renewal_after_realistic_iam_failure_preserves_v2_and_requires_explicit_new_selection(package,previous):
    root,_,_=package
    setup_previous(previous)
    before=hashes(previous)
    code=resume_script(previous)+r'''
status,check=call(['check-renewal','--previous-approval','.local/approval.json'])
assert status==0 and check['renewal']=='eligible' and not check['authorization_created']
assert not (probe.STATE/'.local/authorizations').exists()
status,data=call(['renew-authorization','--previous-approval','.local/approval.json','--operator','operator@workspace.test','--reference','NEW-V3-EXPLICIT-APPROVAL'])
assert status==0 and not data['execution_started']
selected=data['authorization_file']
record=probe.read_json(probe.STATE/selected)
assert record['package_manifest_sha256']==probe.verify()
assert record['previous_approval_sha256']==hashlib.sha256((probe.STATE/'.local/approval.json').read_bytes()).hexdigest()
assert record['checkpoint_sha256_at_authorization']==hashlib.sha256((probe.STATE/'evidence/probe-state.zip').read_bytes()).hexdigest()
assert call(['execute','--confirm-write'])[1]['code']=='selecione_aprovacao_explicita'
assert call(['execute','--confirm-write','--approval-file','.local/approval.json'])[1]['code']=='vinculo_da_aprovacao'
import app.services.drive_supervised as supervised
from app.services.storage_contracts import DriveError
class StillDenied:
    def __init__(self,*a,**k): pass
    def access_token(self): raise DriveError('iam_get_access_token')
    def close(self): pass
supervised.ImpersonatedProbeCredentials=StillDenied
status,data=call(['execute','--confirm-write','--approval-file',selected])
assert status==2 and data['code']=='iam_get_access_token' and data['phase']=='execution_credentials'
first_bytes=(probe.STATE/selected).read_bytes()
status,data=call(['renew-authorization','--previous-approval',selected,'--operator','operator@workspace.test','--reference','ANOTHER-V3-EXPLICIT-APPROVAL'])
assert status==0 and data['authorization_file']!=selected
assert (probe.STATE/selected).read_bytes()==first_bytes
assert call(['authorize','--operator','operator@workspace.test','--reference','NO-RESET'])[1]['code']=='retomada_exige_renovacao_explicita'
'''
    result=run(root,code=code,stdin='AUTORIZO CLOUD SHELL 07C\n'*2)
    assert result.returncode==0,result.stdout+result.stderr
    after=hashes(previous)
    assert all(after[name]==digest for name,digest in before.items())
    assert len(set(after)-set(before))==2
    assert all(name.startswith('.local/authorizations/') for name in set(after)-set(before))
    assert not (root/'evidence/probe-state.zip').exists() # Não bifurcou o journal.


@pytest.mark.parametrize('mutation',[
    "db.execute(\"UPDATE probe_items SET remote_id='reserved-id' WHERE mission='argentina'\")",
    "db.execute(\"UPDATE probe_items SET attempts=1 WHERE mission='argentina'\")",
    "db.execute(\"UPDATE probe_items SET ever_verified=1 WHERE mission='argentina'\")",
    "db.execute(\"UPDATE probe_items SET state='erro' WHERE mission='argentina'\")",
    "db.execute(\"UPDATE probe_items SET error_code='rede' WHERE mission='argentina'\")",
    "db.execute(\"INSERT INTO probe_events(mission,state) VALUES('argentina','enviando')\")",
])
def test_any_remote_possibility_or_history_blocks_renewal_without_reinitialization(package,previous,mutation):
    root,_,_=package
    setup_previous(previous)
    code=resume_script(previous)+f'''
from app.core.test_database import TemporaryDatabase
from app.db.connection import connect
from app.services.drive_probe import ProbeJournal
config,_,_=probe.config_and_plan()
with TemporaryDatabase() as temporary:
    journal=ProbeJournal.restore(probe.STATE/'evidence/probe-state.zip',temporary.directory/'mutation',config)
    with connect(journal.database_path) as db:
        {mutation}
    journal.checkpoint(probe.STATE/'evidence/probe-state.zip')
before=(probe.STATE/'evidence/probe-state.zip').read_bytes()
inspection=probe.inspect_backup(probe.STATE/'evidence/probe-state.zip')
assert not inspection['safe_to_prepare_fresh_copy']
status,data=call(['renew-authorization','--previous-approval','.local/approval.json','--operator','operator@workspace.test','--reference','MUST-BLOCK'])
assert status==2 and data['code']=='atividade_remota_possivel_revisao_obrigatoria'
assert (probe.STATE/'evidence/probe-state.zip').read_bytes()==before
assert not (probe.STATE/'.local/authorizations').exists()
'''
    result=run(root,code=code)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('missing',['evidence/probe-state.zip','evidence/session.json'])
def test_resume_never_bootstraps_when_checkpoint_or_marker_is_missing(package,previous,missing):
    root,_,_=package
    setup_previous(previous)
    (previous/missing).unlink() # Apenas fixture sintética, antes da recuperação.
    before=hashes(previous)
    result=run(root,code=resume_script(previous)+r'''
status,data=call(['renew-authorization','--previous-approval','.local/approval.json','--operator','operator@workspace.test','--reference','MUST-BLOCK'])
assert status==2 and data['code']=='retomada_exige_checkpoint_e_marcador'
''')
    assert result.returncode==0,result.stdout+result.stderr
    assert hashes(previous)==before


def test_interrupted_record_is_preserved_and_retry_creates_another_file(package,previous):
    root,_,_=package
    setup_previous(previous)
    before=hashes(previous)
    code=resume_script(previous)+r'''
import os
original=probe.write_new
broken=[]
def interrupted(path,data):
    if '/authorizations/' in path.as_posix():
        path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with path.open('xb') as out: out.write(b'{')
        broken.append(path)
        raise OSError(5,'PRIVATE-MESSAGE-MUST-NOT-LEAK')
    return original(path,data)
probe.write_new=interrupted
args=['renew-authorization','--previous-approval','.local/approval.json','--operator','operator@workspace.test','--reference','NEW-EXPLICIT-APPROVAL']
status,data=call(args)
assert status==2 and data['phase']=='authorization_record_write' and data['errno']==5
probe.write_new=original
status,data=call(args)
assert status==0 and probe.STATE/data['authorization_file']!=broken[0]
assert broken[0].read_bytes()==b'{'
status,_=call(['renew-authorization','--previous-approval',broken[0].relative_to(probe.STATE).as_posix(),'--operator','operator@workspace.test','--reference','INVALID-PREDECESSOR'])
assert status==2
'''
    result=run(root,code=code,stdin='AUTORIZO CLOUD SHELL 07C\n'*2)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'PRIVATE-MESSAGE' not in result.stdout
    assert all(hashes(previous)[name]==digest for name,digest in before.items())


@pytest.mark.parametrize('condition',['lock','cancel','corrupt'])
def test_lock_cancel_and_corrupt_backup_leave_old_records_intact(package,previous,condition):
    root,_,_=package
    setup_previous(previous)
    code=resume_script(previous)+f'condition={condition!r}\n'+r'''
from app.services.drive_probe import ProbeArchiveLock
archive=probe.STATE/'evidence/probe-state.zip'
args=['renew-authorization','--previous-approval','.local/approval.json','--operator','operator@workspace.test','--reference','NEW-EXPLICIT-APPROVAL']
if condition=='lock':
    with ProbeArchiveLock(archive): status,data=call(args)
    assert data['code']=='ensaio_em_uso'
elif condition=='corrupt':
    archive.write_bytes(b'broken-synthetic-fixture')
    status,data=call(args)
    assert data['code']=='backup'
    assert archive.read_bytes()==b'broken-synthetic-fixture'
else:
    status,data=call(args)
    assert data['code']=='nova_aprovacao_necessaria'
assert status==2 and not (probe.STATE/'.local/authorizations').exists()
'''
    before=(previous/'.local/approval.json').read_bytes()
    result=run(root,code=code,stdin='CANCELAR\n')
    assert result.returncode==0,result.stdout+result.stderr
    assert (previous/'.local/approval.json').read_bytes()==before


def test_source_manifest_and_journal_identity_are_bound_before_credentials(package,previous):
    root,_,_=package
    setup_previous(previous)
    code=resume_script(previous)+r'''
status,data=call(['renew-authorization','--previous-approval','.local/approval.json','--operator','operator@workspace.test','--reference','NEW-EXPLICIT-APPROVAL'])
assert status==0
selected=data['authorization_file']
marker=probe.STATE/'evidence/session.json'
marker_bytes=marker.read_bytes()
marker.unlink() # Fixture de interrupcao posterior a aprovacao.
status,data=call(['execute','--confirm-write','--approval-file',selected])
assert status==2 and data['code']=='retomada_exige_checkpoint_e_marcador'
marker.write_bytes(marker_bytes)
from app.core.test_database import TemporaryDatabase
from app.db.connection import connect
from app.services.drive_probe import ProbeJournal
config,_,_=probe.config_and_plan()
with TemporaryDatabase() as temporary:
    journal=ProbeJournal.restore(probe.STATE/'evidence/probe-state.zip',temporary.directory/'mutation',config)
    with connect(journal.database_path) as db: db.execute("UPDATE probe_run SET volume_id='different-synthetic-volume'")
    volume=probe.read_json(journal.directory/'.volume.json'); volume['id']='different-synthetic-volume'
    (journal.directory/'.volume.json').write_text(json.dumps(volume))
    journal.checkpoint(probe.STATE/'evidence/probe-state.zip')
status,data=call(['execute','--confirm-write','--approval-file',selected])
assert status==2 and data['code']=='identidade_do_journal_divergente'
status,data=call(['renew-authorization','--previous-approval',selected,'--operator','operator@workspace.test','--reference','MUST-NOT-REBIND-OTHER-VOLUME'])
assert status==2 and data['code']=='identidade_do_journal_divergente'
(probe.STATE/'plan.json').write_text('{}')
status,data=call(['prepare','--resume-from',str(probe.STATE)])
assert status==2 and data['phase']=='resume_source_verification'
'''
    result=run(root,code=code,stdin='AUTORIZO CLOUD SHELL 07C\n')
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('change',['expired','broader-scope'])
def test_expired_predecessor_is_history_but_broader_scope_is_never_accepted(package,previous,change):
    root,_,_=package
    setup_previous(previous)
    source=previous/'.local/approval.json'
    data=json.loads(source.read_text())
    if change=='expired': data['expires_at']='2000-01-01T00:00:00+00:00'
    else: data['scopes']=['https://www.googleapis.com/auth/drive']
    source.write_text(json.dumps(data)) # Fixture, nunca operação da recuperação.
    before=hashes(previous)
    code=resume_script(previous)+f'change={change!r}\n'+r'''
status,data=call(['check-renewal','--previous-approval','.local/approval.json'])
if change=='expired':
    assert status==0 and data['renewal']=='eligible' and not data['authorization_created']
else:
    assert status==2 and data['code']=='autorizacao'
assert not (probe.STATE/'.local/authorizations').exists()
'''
    result=run(root,code=code)
    assert result.returncode==0,result.stdout+result.stderr
    assert hashes(previous)==before
