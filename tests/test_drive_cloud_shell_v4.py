"""v4: ACL de seis membros retomando o MESMO journal v2 após a falha v3. Sem Google real.

Cadeia reproduzida: v2 (prepare/policy/authorize, IAM 403) → v3 (renovação e execute que para
na ACL da raiz Argentina antes de qualquer reserva) → v4 (nova política, novo aceite, execução).
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

import pytest

from app.core.drive_config import READERS,SERVICE_ACCOUNT
from scripts.build_drive_cloud_shell_package import ROOT,build as build_v3
from scripts.build_drive_cloud_shell_package_v4 import (CHANGED,LEGACY_POLICY_SHA256,V3_ZIP_SHA256,build,
    commitment,partner_accounts,policy)
from test_drive_cloud_shell_package import PRIVATE_BUILD_INPUTS,require_private_artifacts,run
from test_drive_cloud_shell_renewal import OFFLINE,hashes,previous,setup_previous

V3_ZIP=ROOT/'artifacts/stage07c/cloud-shell-v3/secco-drive-07c-cloud-shell-v3.zip'
V3_MANIFEST='f6916d72f32efe0c3f08f740e48cfc9bb7263d821a67af69d88ea31103980d9f'
PARTNERS=''.join(email+'\n' for email in partner_accounts())
CONFIRM='AUTORIZO CLOUD SHELL 07C\n'
EMAIL=rb'[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+'


def extract(archive,root):
    root.mkdir()
    with zipfile.ZipFile(archive) as source:
        for info in source.infolist():
            assert not info.filename.startswith('/') and '..' not in Path(info.filename).parts
            path=root/info.filename
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(source.read(info))
    return root


@pytest.fixture
def v4(tmp_path):
    require_private_artifacts(*PRIVATE_BUILD_INPUTS,V3_ZIP.relative_to(ROOT).as_posix())
    target,digest=build(tmp_path/'v4-output')
    return extract(target,tmp_path/'v4'),target,digest


@pytest.fixture
def v3(tmp_path):
    require_private_artifacts(V3_ZIP.relative_to(ROOT).as_posix())
    return extract(V3_ZIP,tmp_path/'v3')


# API Drive simulada: ACL real com cinco sócios + conta de serviço; registra cada chamada.
MOCK=r'''
import hashlib,time
from email.parser import BytesParser
from email import policy as email_policy
import httpx
import app.services.drive_supervised as supervised
from app.core.drive_config import FOLDER_NAMES,DRIVE_IDS,SERVICE_ACCOUNT as SA
from app.services.drive_credentials import DriveAccessToken
config,_,_=probe.config_and_plan()
folder_map={identifier:(mission,category) for mission,categories in config.folders().items() for category,identifier in categories.items()}
files={}; calls=[]
def api(request):
    path=request.url.path
    calls.append((request.method,path))
    assert '/drives/' not in path
    if path.endswith('/generateIds'):
        return httpx.Response(200,json={'ids':['v4_reserved_'+str(sum(p.endswith('/generateIds') for _,p in calls))]})
    if request.method=='POST':
        message=BytesParser(policy=email_policy.default).parsebytes(('Content-Type: '+request.headers['content-type']+'\r\n\r\n').encode()+request.content)
        parts=list(message.iter_parts())
        data=json.loads(parts[0].get_payload(decode=True)); content=parts[1].get_payload(decode=True)
        mission=data['appProperties']['secco_mission']
        files[data['id']]={**data,'driveId':DRIVE_IDS[mission],'trashed':False,'size':str(len(content)),'sha256Checksum':hashlib.sha256(content).hexdigest()}
        return httpx.Response(200,json={'id':data['id']})
    if path.endswith('/permissions'):
        resource=path.split('/')[-2]
        if PERMISSION_STATUS!=200 and resource==DRIVE_IDS['argentina']: return httpx.Response(PERMISSION_STATUS,json={})
        permissions=[{'type':'user','emailAddress':e,'role':'writer'} for e in MEMBERS if not (DROP_SERVICE_ACCOUNT and e==SA)]
        if EXTRA and resource==DRIVE_IDS['argentina']: permissions.append(EXTRA)
        return httpx.Response(200,json={'permissions':permissions})
    identifier=path.rsplit('/',1)[1]
    if identifier in folder_map:
        mission,category=folder_map[identifier]
        return httpx.Response(200,json={'id':identifier,'name':FOLDER_NAMES[mission][category],'mimeType':'application/vnd.google-apps.folder','driveId':DRIVE_IDS[mission],'parents':[DRIVE_IDS[mission]],'trashed':False,'capabilities':{'canAddChildren':True}})
    return httpx.Response(200,json=files[identifier]) if identifier in files else httpx.Response(404,json={})
class Credentials:
    def __init__(self,*a,**k): pass
    def access_token(self): return DriveAccessToken('SYNTHETIC-V4-TOKEN',time.time()+300)
    def close(self): pass
Original=supervised.SupervisedProbeAdapter
class MockAdapter(Original):
    def __init__(self,*a,**k): super().__init__(*a,**k,inner=httpx.MockTransport(api))
supervised.ImpersonatedProbeCredentials=Credentials
supervised.SupervisedProbeAdapter=MockAdapter
def writes(): return [c for c in calls if c[0]!='GET' or c[1].endswith('/generateIds')]
'''


def script(old,body,*,extra=None,status=200,drop_sa=False,**variables):
    members=sorted(partner_accounts()+[SERVICE_ACCOUNT])
    head=OFFLINE+(f'OLD={str(old)!r}\nR=["--resume-from",OLD]\nMEMBERS={members!r}\nEXTRA={extra!r}\n'
        f'PERMISSION_STATUS={status!r}\nDROP_SERVICE_ACCOUNT={drop_sa!r}\nLEGACY={LEGACY_POLICY_SHA256!r}\n'
        f'V3_MANIFEST={V3_MANIFEST!r}\n')
    head+=''.join(f'{name}={value!r}\n' for name,value in variables.items())
    return head+MOCK+body


def last(result):
    assert result.returncode==0,result.stdout+result.stderr
    return json.loads(result.stdout.splitlines()[-1])


# Mesmo fluxo do Cloud Shell: v3 renova a partir do aceite v2 e o execute para na raiz Argentina.
V3_FAILURE=r'''
probe.select_state(OLD)
status,data=call(['renew-authorization','--previous-approval','.local/approval.json','--operator','operator@workspace.test','--reference','V3-ACCEPTED-BEFORE-ACL-FAILURE'])
assert status==0,data
record=data['authorization_file']
status,failure=call(['execute','--confirm-write','--approval-file',record])
assert status==2 and failure=={'result':'stopped','code':'permissao','phase':'execution_journal_run','error_type':'DriveError'},failure
acl=[p for _,p in calls if p.endswith('/permissions')]
assert acl==['/drive/v3/files/'+DRIVE_IDS['argentina']+'/permissions'],calls
assert writes()==[]
assert probe.inspect_backup(probe.STATE/'evidence/probe-state.zip')['safe_to_prepare_fresh_copy'] is True
print(json.dumps({'v3_record':record}))
'''


@pytest.fixture
def after_v3_failure(previous,v3):
    setup_previous(previous)
    return previous,last(run(v3,code=script(previous,V3_FAILURE),stdin=CONFIRM))['v3_record']


def test_v4_package_is_deterministic_private_and_differs_from_v3_only_in_executor_and_policy(v4,tmp_path):
    root,target,digest=v4
    other,other_digest=build(tmp_path/'second-build')
    assert digest==other_digest and target.read_bytes()==other.read_bytes()
    assert target.stat().st_size<50000
    assert hashlib.sha256(V3_ZIP.read_bytes()).hexdigest()==V3_ZIP_SHA256
    with zipfile.ZipFile(target) as new,zipfile.ZipFile(V3_ZIP) as old:
        assert set(new.namelist())==set(old.namelist())
        assert {name for name in new.namelist() if new.read(name)!=old.read(name)}==CHANGED
        for name in new.namelist():
            if not name.endswith('.png'):
                assert set(re.findall(EMAIL,new.read(name)))<={SERVICE_ACCOUNT.encode()}
                assert b'C:\\Users\\' not in new.read(name) and b'BEGIN PRIVATE KEY' not in new.read(name)
        assert json.loads(new.read('MANIFEST.json'))['format']=='secco-drive-cloud-shell-07c-v4'
        assert hashlib.sha256(old.read('MANIFEST.json')).hexdigest()==V3_MANIFEST
        contract=json.loads(new.read('policy-contract.json'))
    members=policy()
    assert members['argentina']==members['portugal'] and len(set(members['argentina']))==6 and SERVICE_ACCOUNT in members['argentina']
    assert set(READERS['argentina']|READERS['portugal'])<set(members['argentina'])
    assert contract['policy_sha256']==commitment(members)!=LEGACY_POLICY_SHA256
    assert contract['human_members_per_mission']==5 and contract['previous_policy_sha256']==LEGACY_POLICY_SHA256
    # A constante histórica é exatamente o compromisso da política v2/v3 derivada de READERS.
    assert commitment({m:list(v) for m,v in READERS.items()})==LEGACY_POLICY_SHA256
    source=(root/'probe.py').read_text(encoding='utf-8')
    assert f"LEGACY_POLICY_SHA256='{LEGACY_POLICY_SHA256}'" in source and f"V3_MANIFEST='{V3_MANIFEST}'" in source
    result=subprocess.run([sys.executable,'-I','-S','-B','verify_package.py'],cwd=root,text=True,capture_output=True,timeout=20)
    assert result.returncode==0 and json.loads(result.stdout)['package']=='verified',result.stdout+result.stderr
    # Fontes v3 preservadas: o builder v3 ainda reproduz o ZIP v3 byte a byte.
    assert build_v3(tmp_path/'v3-rebuild')[1]==V3_ZIP_SHA256


@pytest.mark.parametrize('name',['probe.py','policy-contract.json','app/services/google_drive_storage.py'])
def test_v4_manifest_rejects_changed_executor_policy_or_adapter(v4,name):
    root,_,_=v4
    (root/name).write_bytes((root/name).read_bytes()+b'\n')
    result=run(root,'verify')
    assert result.returncode==2 and json.loads(result.stdout)['result']=='stopped'


@pytest.mark.parametrize('action',['prepare','configure-policy','authorize','check-renewal','renew-authorization','execute','evidence'])
def test_v4_never_creates_or_forks_state_without_resume_from(v4,action):
    root,_,_=v4
    result=run(root,action)
    assert result.returncode==2
    assert json.loads(result.stdout)=={'result':'stopped','code':'v4_exige_resume_from','phase':'package_verification','error_type':'ValueError'}
    assert not any((root/folder).exists() for folder in ('.local','evidence','exports'))


def test_v3_acl_failure_is_reproduced_before_any_reservation_and_leaves_state_intact(previous,v3):
    setup_previous(previous)
    before=hashes(previous)
    last(run(v3,code=script(previous,V3_FAILURE),stdin=CONFIRM))
    after=hashes(previous)
    assert all(after[name]==digest for name,digest in before.items()) # checkpoint/marcador/política/aceite v2
    new=set(after)-set(before)
    assert len(new)==1 and next(iter(new)).startswith('.local/authorizations/approval-')
    assert not any(name.startswith('evidence/result-') for name in after)


RECOVERY=r'''
status,data=call(['verify',*R])
assert status==0 and data['manifest_sha256']==probe.verify()
assert call(['authorize',*R,'--operator','operator@workspace.test','--reference','NO-FRESH'])[1]['code']=='retomada_exige_renovacao_explicita'
status,data=call(['check-renewal',*R,'--previous-approval',V3_RECORD])
assert status==2 and data['code']=='politica_v4_nao_configurada',data
status,data=call(['configure-policy',*R])
assert status==2 and data['code']=='politica_nao_confere',data
assert not (probe.STATE/'.local/access-policy-v4.json').exists()
status,data=call(['configure-policy',*R])
assert status==0 and data['members_per_mission']==6 and data['policy_file']=='.local/access-policy-v4.json',data
assert call(['configure-policy',*R])[1]['code']=='politica_v4_ja_registrada'
status,check=call(['check-renewal',*R,'--previous-approval',V3_RECORD])
assert status==0 and check['renewal']=='eligible' and not check['authorization_created'] and not check['execution_started'],check
new_policy=probe.read_json(probe.ROOT/'policy-contract.json')['policy_sha256']
assert check['policy_sha256']==new_policy!=LEGACY and check['members_per_mission']==6
assert check['previous_package_manifest_sha256']==V3_MANIFEST and check['previous_policy_sha256']==LEGACY
for old in ('.local/approval.json',V3_RECORD): # Aceites v2/v3 jamais executam a v4.
    status,data=call(['execute',*R,'--confirm-write','--approval-file',old])
    assert status==2 and data['code']=='vinculo_da_aprovacao',data
assert calls==[]
status,data=call(['renew-authorization',*R,'--previous-approval',V3_RECORD,'--operator','operator@workspace.test','--reference','NEW-V4-EXPLICIT-APPROVAL'])
assert status==0 and not data['execution_started'],data
record=probe.read_json(probe.STATE/data['authorization_file'])
assert record['package_manifest_sha256']==probe.verify() and record['policy_sha256']==new_policy
assert record['previous_approval_file']==V3_RECORD and record['previous_package_manifest_sha256']==V3_MANIFEST
assert record['previous_policy_sha256']==LEGACY and record['journal_identity_sha256']==check['journal_identity_sha256']
assert calls==[]
print(json.dumps({'v4_record':data['authorization_file']}))
'''

EXECUTION=r'''
names={item['official_name'] for item in probe.read_json(probe.ROOT/'plan.json')['items'].values()}
status,first=call(['execute',*R,'--confirm-write','--approval-file',V4_RECORD])
assert status==0 and first['result']=='verified' and first['verified_count']==first['known_remote_file_count']==2,first
assert first['policy_sha256']==probe.read_json(probe.ROOT/'policy-contract.json')['policy_sha256'] and 'acl_detail' not in first
status,second=call(['execute',*R,'--confirm-write','--approval-file',V4_RECORD])
assert status==0 and second['result']=='verified',second
assert [r['remote_id'] for r in first['items']]==[r['remote_id'] for r in second['items']]
assert sum(m=='POST' for m,_ in calls)==2 and sum(p.endswith('/generateIds') for _,p in calls)==2
assert len(files)==2 and {f['name'] for f in files.values()}==names
assert {m for m,_ in calls}<={'GET','POST'}
status,data=call(['evidence',*R])
assert status==0
print(json.dumps({'export':data['evidence_archive']}))
'''


def test_v4_recovers_same_journal_with_new_policy_and_approval_then_uploads_two_files_idempotently(after_v3_failure,v4):
    previous,v3_record=after_v3_failure
    root,_,_=v4
    before=hashes(previous)
    wrong=''.join(email+'\n' for email in partner_accounts()[:4]+['outsider@workspace.test'])
    record=last(run(root,code=script(previous,RECOVERY,V3_RECORD=v3_record),stdin=wrong+PARTNERS+CONFIRM))['v4_record']
    after=hashes(previous)
    assert all(after[name]==digest for name,digest in before.items()) # nada sobrescrito, inclusive política antiga
    assert set(after)-set(before)=={'.local/access-policy-v4.json',record}
    assert not (root/'evidence').exists() and not (root/'.local').exists() # sem bifurcar estado no diretório v4
    stored=json.loads((previous/'.local/access-policy-v4.json').read_text())
    assert {m:set(v) for m,v in stored.items()}=={m:set(v) for m,v in policy().items()}
    export=last(run(root,code=script(previous,EXECUTION,V4_RECORD=record)))['export']
    final=hashes(previous)
    stable=[name for name in after if name!='evidence/probe-state.zip']
    assert all(final[name]==after[name] for name in stable) # aceites e políticas intactos
    assert final['evidence/probe-state.zip']!=after['evidence/probe-state.zip'] # checkpoint legítimo do ensaio
    assert sum(name.startswith('evidence/result-') for name in final)==2
    with zipfile.ZipFile(previous/export) as archive:
        names=archive.namelist()
        assert not any('.local' in n or 'access-policy' in n or 'approval' in n for n in names)
        assert all(not set(re.findall(EMAIL,archive.read(n))) for n in names if n.endswith('.json'))
        reports=[json.loads(archive.read(n)) for n in names if n.startswith('evidence/result-')]
        assert len(reports)==2 and all(r['verified_count']==2 and len(r['remote_checks'])==2 for r in reports)


ACL_FAILURE=r'''
assert call(['configure-policy',*R])[0]==0
status,data=call(['renew-authorization',*R,'--previous-approval',V3_RECORD,'--operator','operator@workspace.test','--reference','NEW-V4-EXPLICIT-APPROVAL'])
assert status==0,data
record=data['authorization_file']
status,data=call(['execute',*R,'--confirm-write','--approval-file',record])
assert status==2 and data['phase']=='execution_journal_run',data
if CASE=='http-403':
    assert data=={'result':'stopped','code':'permissao','phase':'execution_journal_run','error_type':'DriveError'},data
else:
    assert data['code']=='acl_fora_da_politica' and data['acl_mission']=='argentina' and data['acl_resource']=='drive_root',data
assert writes()==[]
status,data=call(['check-renewal',*R,'--previous-approval',record])
assert status==0 and data['renewal']=='eligible',data
'''


@pytest.mark.parametrize('case,options',[
    ('unknown-user',{'extra':{'type':'user','emailAddress':'outsider@workspace.test','role':'reader'}}),
    ('group',{'extra':{'type':'group','emailAddress':'team@workspace.test','role':'reader'}}),
    ('anyone',{'extra':{'type':'anyone','role':'reader'}}),
    ('missing-service-account',{'drop_sa':True}),
    ('http-403',{'status':403}),
])
def test_v4_acl_outside_policy_stops_before_any_reservation_and_stays_renewable(after_v3_failure,v4,case,options):
    previous,v3_record=after_v3_failure
    root,_,_=v4
    result=run(root,code=script(previous,ACL_FAILURE,V3_RECORD=v3_record,CASE=case,**options),stdin=PARTNERS+CONFIRM)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'outsider@' not in result.stdout and 'team@' not in result.stdout
    assert not any(name.startswith('evidence/result-') for name in hashes(previous))


@pytest.mark.parametrize('case',['unknown','duplicate','service-account','legacy-pair'])
def test_v4_policy_accepts_only_the_five_confirmed_partners(previous,v4,case):
    root,_,_=v4
    partners=partner_accounts()
    lines={'unknown':partners[:4]+['outsider@workspace.test'],'duplicate':partners[:4]+[partners[0]],
        'service-account':partners[:4]+[SERVICE_ACCOUNT],
        'legacy-pair':sorted(READERS['argentina']-{SERVICE_ACCOUNT})+['','','']}[case]
    before=hashes(previous)
    body=r'''
status,data=call(['configure-policy',*R])
assert status==2 and data['code']=='politica_nao_confere',data
assert not (probe.STATE/'.local/access-policy-v4.json').exists()
'''
    last_line=run(root,code=script(previous,body),stdin=''.join(line+'\n' for line in lines))
    assert last_line.returncode==0,last_line.stdout+last_line.stderr
    assert hashes(previous)==before


@pytest.mark.parametrize('tamper',['seventh-member','swapped-member'])
def test_v4_tampered_local_policy_is_refused_before_any_authorization(previous,v4,tamper):
    setup_previous(previous)
    root,_,_=v4
    body=r'''
assert call(['configure-policy',*R])[0]==0
path=probe.STATE/'.local/access-policy-v4.json'
data=probe.read_json(path)
if TAMPER=='seventh-member': data['argentina'].append('outsider@workspace.test')
else: data['argentina'][data['argentina'].index(next(e for e in data['argentina'] if e!=SA))]='outsider@workspace.test'
path.write_text(json.dumps(data)) # Fixture sintética de adulteração local.
status,data=call(['check-renewal',*R,'--previous-approval','.local/approval.json'])
assert status==2 and data['code']=='politica_nao_confere',data
assert not (probe.STATE/'.local/authorizations').exists()
'''
    last_line=run(root,code=script(previous,body,TAMPER=tamper),stdin=PARTNERS)
    assert last_line.returncode==0,last_line.stdout+last_line.stderr


@pytest.mark.parametrize('forged',['v3-manifest-new-policy','v4-manifest-legacy-policy'])
def test_v4_execute_requires_both_v4_manifest_and_v4_policy_before_credentials(previous,v4,forged):
    setup_previous(previous)
    root,_,_=v4
    body=r'''
assert call(['configure-policy',*R])[0]==0
status,data=call(['renew-authorization',*R,'--previous-approval','.local/approval.json','--operator','operator@workspace.test','--reference','NEW-V4-EXPLICIT-APPROVAL'])
assert status==0,data
record=probe.read_json(probe.STATE/data['authorization_file'])
if FORGED=='v3-manifest-new-policy': record['package_manifest_sha256']=V3_MANIFEST
else: record['policy_sha256']=LEGACY
forged='.local/authorizations/approval-'+'f'*32+'.json'
probe.write_new(probe.STATE/forged,record) # Fixture: registro forjado, nunca fluxo real.
status,data=call(['execute',*R,'--confirm-write','--approval-file',forged])
assert status==2 and data['code']=='vinculo_da_aprovacao',data
assert calls==[]
'''
    result=run(root,code=script(previous,body,FORGED=forged),stdin=PARTNERS+CONFIRM)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('change,expected',[
    ('v2-history','eligible'),('expired','eligible'),
    ('v3-manifest-with-new-policy','vinculo_da_aprovacao_anterior'),
    ('unknown-manifest','vinculo_da_aprovacao_anterior'),('broader-scope','autorizacao'),
])
def test_v4_predecessor_is_only_legacy_history_or_v4(previous,v4,change,expected):
    setup_previous(previous)
    root,_,_=v4
    source=previous/'.local/approval.json'
    data=json.loads(source.read_text())
    if change=='expired': data['expires_at']='2000-01-01T00:00:00+00:00'
    elif change=='v3-manifest-with-new-policy': data.update(package_manifest_sha256=V3_MANIFEST,policy_sha256=commitment(policy()))
    elif change=='unknown-manifest': data['package_manifest_sha256']='0'*64
    elif change=='broader-scope': data['scopes']=['https://www.googleapis.com/auth/drive']
    if change!='v2-history': source.write_text(json.dumps(data)) # Fixture, nunca operação real.
    body=r'''
assert call(['configure-policy',*R])[0]==0
status,data=call(['check-renewal',*R,'--previous-approval','.local/approval.json'])
if EXPECTED=='eligible': assert status==0 and data['renewal']=='eligible' and data['previous_policy_sha256']==LEGACY,data
else: assert status==2 and data['code']==EXPECTED,data
assert not (probe.STATE/'.local/authorizations').exists()
'''
    result=run(root,code=script(previous,body,EXPECTED=expected),stdin=PARTNERS)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('mutation',[
    "db.execute(\"UPDATE probe_items SET attempts=1 WHERE mission='argentina'\")",
    "db.execute(\"INSERT INTO probe_events(mission,state) VALUES('argentina','enviando')\")",
    "db.execute(\"UPDATE probe_items SET remote_id='reserved-id' WHERE mission='portugal'\")",
])
def test_v4_renewal_still_refuses_any_journal_activity(previous,v4,mutation):
    setup_previous(previous)
    root,_,_=v4
    body=r'''
from app.core.test_database import TemporaryDatabase
from app.db.connection import connect
from app.services.drive_probe import ProbeJournal
assert call(['configure-policy',*R])[0]==0
probe.select_state(OLD)
with TemporaryDatabase() as temporary:
    journal=ProbeJournal.restore(probe.STATE/'evidence/probe-state.zip',temporary.directory/'mutation',config)
    with connect(journal.database_path) as db:
        MUTATION
    journal.checkpoint(probe.STATE/'evidence/probe-state.zip')
before=(probe.STATE/'evidence/probe-state.zip').read_bytes()
status,data=call(['renew-authorization',*R,'--previous-approval','.local/approval.json','--operator','operator@workspace.test','--reference','MUST-BLOCK'])
assert status==2 and data['code']=='atividade_remota_possivel_revisao_obrigatoria',data
assert (probe.STATE/'evidence/probe-state.zip').read_bytes()==before
assert not (probe.STATE/'.local/authorizations').exists()
'''.replace('MUTATION',mutation)
    result=run(root,code=script(previous,body),stdin=PARTNERS+CONFIRM)
    assert result.returncode==0,result.stdout+result.stderr
