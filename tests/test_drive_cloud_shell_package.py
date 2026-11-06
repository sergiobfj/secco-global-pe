"""Pacote portatil: whitelist, privacidade, subprocessos offline e API mockada."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

import pytest

from app.core.drive_config import READERS,SERVICE_ACCOUNT
from scripts.build_drive_cloud_shell_package import ROOT,build,payload,NAME


PRIVATE_BUILD_INPUTS=('artifacts/stage07c/offline-plan.json','artifacts/stage07b/mapping/folders.json',
                      'artifacts/stage07c/probe-prepared.zip')


def require_private_artifacts(*names):
    """Distribuição pública: os pacotes e entradas operacionais (IDs reais) não são versionados."""
    missing=[name for name in names if not (ROOT/name).exists()]
    if missing: pytest.skip('requer artefatos operacionais privados: '+', '.join(missing))


@pytest.fixture
def package(tmp_path):
    require_private_artifacts(*PRIVATE_BUILD_INPUTS)
    target,digest=build(tmp_path/'output')
    root=tmp_path/'extracted'
    root.mkdir()
    with zipfile.ZipFile(target) as archive:
        for info in archive.infolist():
            assert not info.filename.startswith('/') and '..' not in Path(info.filename).parts
            path=root/info.filename
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(archive.read(info))
    return root,target,digest


def run(root,*args,stdin=None,code=None):
    environment={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1'}
    environment.pop('PYTHONPATH',None)
    command=[sys.executable,'-B']+(['-c',code] if code else ['probe.py',*args])
    result=subprocess.run(command,cwd=root,input=stdin,text=True,capture_output=True,env=environment,timeout=60)
    return result


def policy_input():
    return ''.join(email+'\n' for mission in ('argentina','portugal') for email in sorted(READERS[mission]-{SERVICE_ACCOUNT}))


def test_zip_is_minimal_deterministic_and_contains_no_personal_data(package,tmp_path):
    root,target,digest=package
    other,other_digest=build(tmp_path/'second-build')
    assert digest==other_digest and target.read_bytes()==other.read_bytes()
    assert target.stat().st_size<50000
    with zipfile.ZipFile(target) as archive:
        assert set(archive.namelist())==set(payload())
        assert sum(n.endswith('.png') for n in archive.namelist())==2
        for name in archive.namelist():
            assert not any(part in {'.env','data','migrations','.local','evidence','__pycache__'} for part in Path(name).parts)
            assert Path(name).suffix not in ('.sqlite3','.db','.key','.pem')
            data=archive.read(name)
            if not name.endswith('.png'):
                assert set(re.findall(rb'[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+',data))<={SERVICE_ACCOUNT.encode()}
                assert b'C:\\Users\\' not in data and b'BEGIN PRIVATE KEY' not in data
    assert (target.with_suffix('.zip.sha256')).read_text().strip()==digest+'  '+NAME


def test_verification_uses_only_stdlib_before_install(package):
    root,target,digest=package
    result=subprocess.run([sys.executable,'-I','-S','-B','verify_package.py'],cwd=root,text=True,capture_output=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout)['package']=='verified'


@pytest.mark.parametrize('name',['payload/argentina.png','folders.json','plan.json','app/services/drive_supervised.py'])
def test_manifest_rejects_changed_payload_or_executor(package,name):
    root,_,_=package
    (root/name).write_bytes((root/name).read_bytes()+b'\n')
    result=run(root,'verify')
    assert result.returncode==2 and json.loads(result.stdout)['result']=='stopped'


def test_unknown_source_file_is_rejected(package):
    root,_,_=package
    (root/'unexpected.py').write_text('pass',encoding='utf-8')
    assert run(root,'verify').returncode==2


def test_runtime_dependency_closure_has_no_web_app_framework(package):
    root,_,_=package
    result=run(root,code="import probe; probe.verify(); probe.config_and_plan(); import sys,json; print(json.dumps({'forbidden':sorted(set(sys.modules)&{'fastapi','dotenv','jwt','cryptography','app.main'})}))")
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout)['forbidden']==[]
    assert set((root/'requirements.txt').read_text().splitlines())=={
        'httpx==0.28.1','httpcore==1.0.9','anyio==4.15.1','certifi==2026.7.22',
        'idna==3.18','h11==0.16.0','typing_extensions==4.16.0'}


def test_prepare_preserves_original_plan_and_restores_without_network(package):
    root,_,_=package
    code="""import socket,subprocess,json,probe
def denied(*a,**k): raise AssertionError('real network/credentials forbidden')
socket.socket.connect=denied
subprocess.run=denied
assert probe.main(['prepare'])==0
assert probe.main(['prepare'])==0
"""
    result=run(root,code=code)
    assert result.returncode==0,result.stdout+result.stderr
    outputs=[json.loads(line) for line in result.stdout.splitlines()]
    assert outputs[0]['plan_sha256']==outputs[1]['plan_sha256']==json.loads((root/'plan.json').read_text())['plan_sha256']
    assert all(r['remote_id'] is None and r['attempts']==0 for r in outputs[1]['items'])
    assert not (root/'.local/approval.json').exists()
    with zipfile.ZipFile(root/'evidence/probe-state.zip') as archive:
        for mission in ('argentina','portugal'):
            assert archive.read(mission+'.png')==(root/'payload'/f'{mission}.png').read_bytes()


def test_lost_state_cannot_be_reinitialized(package):
    root,_,_=package
    assert run(root,'prepare').returncode==0
    (root/'evidence/probe-state.zip').unlink()
    result=run(root,'prepare')
    assert result.returncode==2 and json.loads(result.stdout)['code']=='journal_perdido_nao_reinicializar'


def test_acl_policy_is_supplied_locally_and_cannot_include_other_members(package):
    root,_,_=package
    assert run(root,'configure-policy',stdin='someone@workspace.test\n'*4).returncode==2
    assert not (root/'.local/access-policy.json').exists()
    assert run(root,'configure-policy',stdin=policy_input()).returncode==0
    data=json.loads((root/'.local/access-policy.json').read_text())
    assert {m:set(v) for m,v in data.items()}=={m:set(v) for m,v in READERS.items()}
    assert run(root,'verify').returncode==0


def test_new_authorization_is_required_and_bound_to_cloud_shell_package(package):
    root,_,_=package
    assert run(root,'configure-policy',stdin=policy_input()).returncode==0
    code="""import probe,json,socket,subprocess
def denied(*a,**k): raise AssertionError('real network/credentials forbidden')
socket.socket.connect=denied; subprocess.run=denied
probe.sys.platform='linux' # Apenas gate de declaracao; nao simula kernel/WSL.
assert probe.main(['authorize','--operator','operator@workspace.test','--reference','NEW-EXPLICIT-TEST-APPROVAL','--minutes','20'])==0
"""
    result=run(root,code=code,stdin='AUTORIZO CLOUD SHELL 07C\n')
    assert result.returncode==0,result.stdout+result.stderr
    data=json.loads((root/'.local/approval.json').read_text())
    assert data['environment']=='google-cloud-shell'
    assert data['approved'] and data['package_manifest_sha256']==hashlib.sha256((root/'MANIFEST.json').read_bytes()).hexdigest()
    assert data['plan_sha256']==json.loads((root/'plan.json').read_text())['plan_sha256']
    assert data['scopes']==['https://www.googleapis.com/auth/drive.file','https://www.googleapis.com/auth/drive.metadata.readonly']


def test_execute_without_approval_stops_before_gcloud(package):
    root,_,_=package
    code="""import probe,socket,subprocess
def denied(*a,**k): raise AssertionError('real network/credentials forbidden')
socket.socket.connect=denied; subprocess.run=denied
probe.sys.platform='linux'
assert probe.main(['execute','--confirm-write','--approval-file','.local/approval.json'])==2
"""
    result=run(root,code=code)
    assert result.returncode==0,result.stdout+result.stderr
    assert not (root/'evidence/probe-state.zip').exists()


def test_evidence_export_excludes_personal_policy_and_approval(package):
    root,_,_=package
    assert run(root,'prepare').returncode==0
    assert run(root,'configure-policy',stdin=policy_input()).returncode==0
    result=run(root,'evidence')
    assert result.returncode==0,result.stdout+result.stderr
    export=root/json.loads(result.stdout)['evidence_archive']
    with zipfile.ZipFile(export) as archive:
        assert not any('.local' in name or 'access-policy' in name or 'approval' in name for name in archive.namelist())
        for name in archive.namelist():
            if name.endswith('.json'):
                assert not set(re.findall(rb'[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+',archive.read(name)))
    assert run(root,'verify').returncode==0


def test_packaged_executor_creates_only_two_mock_files_and_repeats_without_duplicates(package):
    root,_,_=package
    assert run(root,'configure-policy',stdin=policy_input()).returncode==0
    code=r'''import probe,json,socket,subprocess,time,hashlib
from email.parser import BytesParser
from email import policy
def denied(*a,**k): raise AssertionError('real network/credentials forbidden')
socket.socket.connect=denied; subprocess.run=denied
probe.sys.platform='linux'
assert probe.main(['authorize','--operator','operator@workspace.test','--reference','NEW-TEST-APPROVAL'])==0
import httpx
import app.services.drive_supervised as supervised
from app.core.drive_config import READERS,FOLDER_NAMES,DRIVE_IDS
from app.services.drive_credentials import DriveAccessToken
config,plan,items=probe.config_and_plan()
folder_map={identifier:(mission,category) for mission,categories in config.folders().items() for category,identifier in categories.items()}
files={}; counter={'ids':0,'posts':0}
def api(request):
    path=request.url.path
    assert '/drives/' not in path
    if path.endswith('/generateIds'):
        counter['ids']+=1
        return httpx.Response(200,json={'ids':['portable_reserved_'+str(counter['ids'])]})
    if request.method=='POST':
        counter['posts']+=1
        # Usa parser por cabeçalho MIME real, sem depender do shell.
        msg=BytesParser(policy=policy.default).parsebytes(('Content-Type: '+request.headers['content-type']+chr(13)+chr(10)+chr(13)+chr(10)).encode()+request.content)
        parts=list(msg.iter_parts())
        data=json.loads(parts[0].get_payload(decode=True)); content=parts[1].get_payload(decode=True)
        assert len(content)==69
        mission=data['appProperties']['secco_mission']
        files[data['id']]={**data,'driveId':DRIVE_IDS[mission],'trashed':False,'size':str(len(content)),'sha256Checksum':hashlib.sha256(content).hexdigest()}
        return httpx.Response(200,json={'id':data['id']})
    if path.endswith('/permissions'):
        resource=path.split('/')[-2]
        if resource in folder_map: mission=folder_map[resource][0]
        elif resource in files: mission=files[resource]['appProperties']['secco_mission']
        else: mission=next(m for m,d in DRIVE_IDS.items() if d==resource)
        return httpx.Response(200,json={'permissions':[{'type':'user','emailAddress':e,'role':'writer'} for e in READERS[mission]]})
    identifier=path.rsplit('/',1)[1]
    if identifier in folder_map:
        mission,category=folder_map[identifier]
        return httpx.Response(200,json={'id':identifier,'name':FOLDER_NAMES[mission][category],'mimeType':'application/vnd.google-apps.folder','driveId':DRIVE_IDS[mission],'parents':[DRIVE_IDS[mission]],'trashed':False,'capabilities':{'canAddChildren':True}})
    return httpx.Response(200,json=files[identifier]) if identifier in files else httpx.Response(404,json={})
class Credentials:
    def __init__(self,*a,**k): pass
    def access_token(self): return DriveAccessToken('SYNTHETIC-PORTABLE-TOKEN',time.time()+300)
    def close(self): pass
Original=supervised.SupervisedProbeAdapter
class MockAdapter(Original):
    def __init__(self,*a,**k): super().__init__(*a,**k,inner=httpx.MockTransport(api))
supervised.ImpersonatedProbeCredentials=Credentials
supervised.SupervisedProbeAdapter=MockAdapter
assert probe.main(['execute','--confirm-write','--approval-file','.local/approval.json'])==0
assert probe.main(['execute','--confirm-write','--approval-file','.local/approval.json'])==0
assert counter=={'ids':2,'posts':2}
assert len(files)==2
assert probe.main(['evidence'])==0
print(json.dumps({'mock_summary':counter,'files':len(files)}))
'''
    result=run(root,code=code,stdin='AUTORIZO CLOUD SHELL 07C\n')
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout.splitlines()[-1])=={'mock_summary':{'ids':2,'posts':2},'files':2}
    with zipfile.ZipFile(next((root/'exports').glob('*.zip'))) as evidence:
        names=evidence.namelist()
        assert not any('.local' in name or 'approval' in name for name in names)
        reports=[json.loads(evidence.read(name)) for name in names if name.startswith('evidence/result-')]
        assert len(reports)==2
        for report in reports:
            assert report['verified_count']==report['known_remote_file_count']==2
            assert len(report['remote_checks'])==2


@pytest.mark.parametrize('failure',['expired','other-package','other-environment','broader-scope'])
def test_invalid_renewal_stops_before_credentials(package,failure):
    root,_,_=package
    assert run(root,'configure-policy',stdin=policy_input()).returncode==0
    code=f'''import probe,json,subprocess,socket
probe.sys.platform='linux'
assert probe.main(['authorize','--operator','operator@workspace.test','--reference','NEW-TEST-APPROVAL'])==0
path=probe.ROOT/'.local/approval.json'
data=json.loads(path.read_text())
failure={failure!r}
if failure=='expired': data['expires_at']='2000-01-01T00:00:00+00:00'
elif failure=='other-package': data['package_manifest_sha256']='0'*64
elif failure=='other-environment': data['environment']='other'
else: data['scopes']=['https://www.googleapis.com/auth/drive']
path.write_text(json.dumps(data))
def denied(*a,**k): raise AssertionError('credentials must not be accessed')
subprocess.run=denied; socket.socket.connect=denied
assert probe.main(['execute','--confirm-write','--approval-file','.local/approval.json'])==2
'''
    result=run(root,code=code,stdin='AUTORIZO CLOUD SHELL 07C\n')
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout.splitlines()[-1])['result']=='stopped'
