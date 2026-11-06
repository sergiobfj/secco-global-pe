"""Regressão dir_fd: eventos POSIX, pacote anterior preservado e v2 sem rede."""
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace
import zipfile

import pytest

from app.core import test_database as isolation
from scripts.build_drive_cloud_shell_package import ROOT
from test_drive_cloud_shell_package import package,require_private_artifacts,run


def mock_directory_fd(monkeypatch,base,*,mode=stat.S_IFDIR|0o700,deleted=False):
    descriptor=987654321
    original_stat=os.fstat
    original_link=os.readlink
    monkeypatch.setattr(os,'fstat',lambda fd:SimpleNamespace(st_mode=mode) if fd==descriptor else original_stat(fd))
    monkeypatch.setattr(os,'readlink',lambda path,*a,**k:(str(base)+(' (deleted)' if deleted else ''))
                        if str(path)==f'/proc/self/fd/{descriptor}' else original_link(path,*a,**k))
    return descriptor


def test_relative_fd_path_is_joined_to_directory_not_cwd(tmp_path,monkeypatch):
    descriptor=mock_directory_fd(monkeypatch,tmp_path)
    assert isolation._event_path('probe.sqlite3',descriptor)==tmp_path/'probe.sqlite3'
    isolation._audit('os.remove',('probe.sqlite3',descriptor))


def test_relative_fd_must_not_escape_the_lease(tmp_path,monkeypatch):
    descriptor=mock_directory_fd(monkeypatch,tmp_path)
    with pytest.raises(isolation.UnsafeTestDatabase):
        isolation._audit('os.remove',('../outside.sqlite3',descriptor))


def test_fd_targeting_operational_data_is_refused_before_any_operation(monkeypatch):
    descriptor=mock_directory_fd(monkeypatch,ROOT/'data')
    with pytest.raises(isolation.UnsafeTestDatabase):
        isolation._audit('os.remove',('secco.sqlite3',descriptor))


@pytest.mark.parametrize('mode,deleted',[(stat.S_IFREG|0o600,False),(stat.S_IFDIR|0o700,True)])
def test_non_directory_or_deleted_descriptor_fails_closed(tmp_path,monkeypatch,mode,deleted):
    descriptor=mock_directory_fd(monkeypatch,tmp_path,mode=mode,deleted=deleted)
    with pytest.raises(isolation.UnsafeTestDatabase):
        isolation._audit('os.remove',('probe.sqlite3',descriptor))


def test_unknown_descriptor_fails_closed():
    with pytest.raises(isolation.UnsafeTestDatabase): isolation._event_path('probe.sqlite3',987654321)


def test_absolute_path_does_not_use_directory_descriptor(tmp_path):
    assert isolation._event_path(tmp_path/'probe.sqlite3',987654321)==tmp_path/'probe.sqlite3'


@pytest.mark.parametrize('event',['os.rename','os.link'])
def test_both_directory_descriptors_are_checked(tmp_path,monkeypatch,event):
    descriptor=mock_directory_fd(monkeypatch,ROOT/'data')
    with pytest.raises(isolation.UnsafeTestDatabase):
        isolation._audit(event,(str(tmp_path/'source.sqlite3'),'secco.sqlite3',None,descriptor))


RELATIVE_CLEANUP=r'''
import json,sys,os,shutil,stat,socket,subprocess
import probe
import app.core.test_database as policy
from pathlib import Path
from types import SimpleNamespace
def forbidden(*a,**k): raise AssertionError('No real network/credentials')
socket.socket.connect=forbidden; subprocess.run=forbidden
original_temp=policy.TemporaryDatabase
created=[]
class Tracked(original_temp):
    def __init__(self): super().__init__(); created.append(self)
policy.TemporaryDatabase=Tracked
original_remove=shutil.rmtree
original_link=os.readlink
original_stat=os.fstat
descriptor=987654321
context={'base':None,'blocked_error':None}
def stat_fd(fd):
    return SimpleNamespace(st_mode=stat.S_IFDIR|0o700) if fd==descriptor else original_stat(fd)
def fd_link(path,*a,**k):
    return str(context['base']) if str(path)==f'/proc/self/fd/{descriptor}' else original_link(path,*a,**k)
def relative_cleanup(path,*a,**k):
    context['base']=Path(path)/'probe'
    try: sys.audit('os.remove','probe.sqlite3',descriptor)
    except Exception as error:
        context['blocked_error']=type(error).__name__
        raise
    return original_remove(path,*a,**k)
os.fstat=stat_fd; os.readlink=fd_link; shutil.rmtree=relative_cleanup
try:
    result=probe.main(['prepare'])
    files={'backup_exists':(probe.ROOT/'evidence/probe-state.zip').exists(),
           'session_exists':(probe.ROOT/'evidence/session.json').exists(),
           'offline_report_exists':(probe.ROOT/'evidence/offline-check.json').exists()}
finally:
    os.fstat=original_stat; os.readlink=original_link; shutil.rmtree=original_remove
    for lease in created:
        if not lease.closed: lease.close()
print(json.dumps({'return_code':result,'blocked_error':context['blocked_error'],**files}))
'''


def test_previous_reported_zip_reproduces_generic_failure_after_checkpoint(tmp_path):
    require_private_artifacts('artifacts/stage07c/cloud-shell/secco-drive-07c-cloud-shell.zip')
    old=ROOT/'artifacts/stage07c/cloud-shell/secco-drive-07c-cloud-shell.zip'
    root=tmp_path/'old-package'
    root.mkdir()
    import hashlib
    with zipfile.ZipFile(old) as archive:
        assert hashlib.sha256(archive.read('MANIFEST.json')).hexdigest()=='79fcffb7a3f9605f9aaaa426c7a5b7811aaf69a0aa5dc8228a3141bf1a96f1ed'
        for info in archive.infolist():
            path=root/info.filename; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(archive.read(info))
    result=run(root,code=RELATIVE_CLEANUP)
    assert result.returncode==0,result.stdout+result.stderr
    records=[json.loads(line) for line in result.stdout.splitlines()]
    assert records[0]=={'result':'stopped','code':'configuracao_ou_backup'}
    assert records[1]=={'return_code':2,'blocked_error':'UnsafeTestDatabase',
        'backup_exists':True,'session_exists':True,'offline_report_exists':False}


def test_v2_relative_cleanup_succeeds_with_same_guard_active(package):
    root,_,_=package
    result=run(root,code=RELATIVE_CLEANUP)
    assert result.returncode==0,result.stdout+result.stderr
    records=[json.loads(line) for line in result.stdout.splitlines()]
    assert records[0]['mode']=='offline'
    assert records[-1]=={'return_code':0,'blocked_error':None,
        'backup_exists':True,'session_exists':True,'offline_report_exists':True}


def test_missing_dependency_diagnostic_exposes_phase_and_type_without_secret(package):
    root,_,_=package
    code="""import probe
def failed():
    probe.phase('prepare_imports')
    raise ModuleNotFoundError('NEVER-EXPOSE-TOKEN-OR-PRIVATE-PATH')
probe.initialize=failed
assert probe.main(['prepare'])==2
"""
    result=run(root,code=code)
    assert result.returncode==0
    data=json.loads(result.stdout)
    assert data=={'result':'stopped','code':'dependencia_ausente','phase':'prepare_imports','error_type':'ModuleNotFoundError'}
    assert 'NEVER-EXPOSE' not in result.stdout


def test_inspection_of_existing_backup_is_read_only_and_reports_empty_remote_state(package,tmp_path):
    root,_,_=package
    assert run(root,'prepare').returncode==0
    source=root/'evidence/probe-state.zip'
    import hashlib
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    result=run(root,'inspect-backup','--archive',str(source))
    assert result.returncode==0,result.stdout+result.stderr
    data=json.loads(result.stdout)
    assert data['read_only_archive'] and data['safe_to_prepare_fresh_copy']
    assert all(r['remote_id'] is None and r['attempts']==0 for r in data['items'])
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before


@pytest.mark.parametrize('remote_id,attempts',[('reserved-remote-id',0),(None,1)])
def test_inspection_never_recommends_fresh_state_after_remote_reservation_or_attempt(package,remote_id,attempts):
    root,_,_=package
    code=f'''import probe
from app.core.test_database import TemporaryDatabase
from app.db.connection import connect
from app.services.drive_probe import ProbeJournal
probe.initialize()
config,_,_=probe.config_and_plan()
with TemporaryDatabase() as temporary:
    journal=ProbeJournal.restore(probe.ROOT/'evidence/probe-state.zip',temporary.directory/'probe',config)
    with connect(journal.database_path) as db:
        db.execute('UPDATE probe_items SET remote_id=?, attempts=? WHERE mission=?',({remote_id!r},{attempts!r},'argentina'))
    journal.checkpoint(probe.ROOT/'evidence/probe-state.zip')
assert probe.main(['inspect-backup','--archive',str(probe.ROOT/'evidence/probe-state.zip')])==0
'''
    result=run(root,code=code)
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout)['safe_to_prepare_fresh_copy'] is False


def test_inspection_rejects_corrupt_backup_without_changing_source(package):
    root,_,_=package
    source=root/'evidence/broken.zip'
    source.parent.mkdir()
    source.write_bytes(b'not-a-valid-checkpoint')
    result=run(root,'inspect-backup','--archive',str(source))
    assert result.returncode==2
    data=json.loads(result.stdout)
    assert data['code']=='backup' and data['phase']=='inspect_backup_restore'
    assert source.read_bytes()==b'not-a-valid-checkpoint'
