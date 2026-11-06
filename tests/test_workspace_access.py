"""Etapa 06: contas e tokens sintéticos, sem acesso ao Google ou banco operacional."""
from dataclasses import replace
import json
import secrets
import sqlite3
import time
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app.core.auth import actor_id
from app.core.config import Settings
from app.core.workspace_access import COORDINATOR_KEY,SECCO_ACCOUNTS,WORKSPACE_DOMAIN
from app.db.connection import connect
from app.db.migrate import migrate
from app.main import create_app
from app.repositories.auth import AuthRepository
from auth_support import synthetic_settings,SyntheticGoogle,login_as,begin_login,finish_login
from test_receipts import BASE,values,send,entry_id,image_upload


def workspace_settings(location,**changes):
    return synthetic_settings(location,google_workspace_domain=WORKSPACE_DOMAIN,
        allowed_users=tuple((key,policy[0]) for key,policy in SECCO_ACCOUNTS.items()),**changes)


def make_app(settings):
    app=create_app(settings); google=SyntheticGoogle(settings)
    google.overrides={'hd':WORKSPACE_DOMAIN,'email':'tiago@secco.example','sub':'synthetic-secco-tiago'}
    app.state.oidc=google.provider()
    return app,google


@pytest.fixture
def workspace(tmp_path):
    settings=workspace_settings(tmp_path/'workspace.sqlite3',receipts_synthetic_enabled=True)
    app,google=make_app(settings)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        yield client,google,settings


def coordinator(client,google):
    return login_as(client,google,email='marcos@secco.example',sub='synthetic-secco-marcos')


@pytest.mark.parametrize('email,participant,home,editable',[
 ('tiago@secco.example',3,'/missoes/argentina','argentina'),
 ('bruno@secco.example',4,'/missoes/argentina','argentina'),
 ('hugo@secco.example',1,'/missoes/portugal','portugal'),
 ('alan@secco.example',2,'/missoes/portugal','portugal'),
 ('marcos@secco.example',None,'/consolidado',None)])
def test_five_authorized_profiles(workspace,email,participant,home,editable):
    client,google,_=workspace
    response=login_as(client,google,email=email,sub='synthetic-secco-'+email.split('@')[0])
    assert response.status_code==303 and response.headers['location']==home
    identity=client.get('/api/usuario').json()
    assert identity['participant_id']==participant
    assert identity['perfil']==('coordenacao' if participant is None else 'viajante')
    assert identity['visao_principal']==(editable or 'consolidada')
    for code in ('argentina','portugal'):
        assert identity['permissoes'][code]=={'consultar':True,'editar':code==editable}
        assert client.get('/missoes/'+code).status_code==200
    assert client.get('/',follow_redirects=False).headers['location']==home


@pytest.mark.parametrize('changes,remove',[
 ({'hd':'other.test'},set()),({'hd':'secco.example.evil.test'},set()),({}, {'hd'}),
 ({'email':'outsider@secco.example'},set()),({'email':'marcos@secco.example','hd':'other.test'},set()),
 ({'email_verified':False},set()),({'aud':'wrong-audience'},set()),({'iss':'https://evil.test'},set()),
 ({'exp':1},set()),({'nonce':'wrong-nonce'},set())])
def test_verified_claims_and_allowlist_fail_closed(workspace,changes,remove):
    client,google,_=workspace
    google.overrides.update(changes); google.remove=remove
    assert finish_login(client,begin_login(client,google)).status_code==403
    assert client.get('/api/usuario').status_code==401


def test_signature_and_state_are_required(workspace):
    client,google,_=workspace
    google.invalid_signature=True
    assert login_as(client,google).status_code==403
    google.invalid_signature=False
    query=begin_login(client,google)
    assert finish_login(client,query,state='invalid-state').status_code==403
    assert client.get('/api/usuario').status_code==401


def test_coordinator_is_not_a_traveler_or_result_author(workspace):
    client,google,settings=workspace
    assert coordinator(client,google).status_code==303
    identity=client.get('/api/usuario').json()
    user=client.app.state.auth.get_user(identity['id'])
    assert actor_id(SimpleNamespace(state=SimpleNamespace(user=user))) is None
    with connect(settings.database_path) as db:
        assert db.execute('SELECT COUNT(*) FROM participants').fetchone()[0]==4
        assert db.execute('SELECT COUNT(*) FROM mission_participants').fetchone()[0]==4
        assert db.execute('SELECT COUNT(*) FROM app_users').fetchone()[0]==4
        assert db.execute('SELECT COUNT(*) FROM coordination_accounts').fetchone()[0]==1
        assert [(r[0],r[1]) for r in db.execute('SELECT participant_id,financiado_pela_subvencao FROM mission_participants ORDER BY participant_id')]==[(1,1),(2,0),(3,0),(4,1)]
        assert db.execute('SELECT COUNT(*) FROM expenses').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM diary_entries').fetchone()[0]==0
    assert identity['id'] not in client.app.state.auth.author_names()
    page=client.get('/consolidado')
    assert page.status_code==200 and 'Missão Portugal' in page.text and 'Missão Argentina' in page.text
    assert 'Registrar comprovante' not in page.text and '\u2014' not in page.text


@pytest.mark.parametrize('url',[
 '/missoes/argentina/atividades/nova','/missoes/portugal/atividades/nova',
 '/missoes/argentina/atividades/1/editar','/missoes/argentina/atividades/1/cancelar',
 '/missoes/argentina/diario/novo','/missoes/portugal/diario/1/editar',
 '/missoes/argentina/diario/1/evidencias/nova','/missoes/argentina/diario/1/metas/nova',
 '/missoes/argentina/comprovantes/novo','/missoes/portugal/comprovantes/1/editar',
 '/missoes/argentina/comprovantes/1/anexos/sintetico/excluir'])
def test_coordinator_write_is_blocked_in_backend(workspace,url):
    client,google,settings=workspace
    assert coordinator(client,google).status_code==303
    response=client.post(url,data={'csrf_token':client.cookies.get('secco_csrf'),'participant_id':'3','role':'admin'})
    assert response.status_code==403
    with connect(settings.database_path) as db:
        assert db.execute('SELECT COUNT(*) FROM diary_history').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM itinerary_history').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM expenses').fetchone()[0]==0


def test_coordinator_cannot_read_private_receipt(workspace):
    client,google,_=workspace
    assert login_as(client,google).status_code==303
    item=entry_id(send(client,values(client),image_upload()))
    traveler=client.get('/api/usuario').json()
    proof=client.app.state.receipts.get(2,item,traveler['id'])['attachments'][0]
    assert coordinator(client,google).status_code==303
    for path in (BASE,BASE+f'/{item}',BASE+f'/{item}/anexos/'+proof['id']):
        assert client.get(path).status_code==403
    assert client.app.state.receipt_storage.read_attachment(proof)==__import__('test_receipts').png()


@pytest.mark.parametrize('coord',[False,True])
def test_disabled_account_is_blocked_immediately(workspace,coord):
    client,google,settings=workspace
    if coord: coordinator(client,google)
    else: login_as(client,google)
    table='coordination_accounts' if coord else 'app_users'
    with connect(settings.database_path) as db: db.execute(f'UPDATE {table} SET enabled=0')
    assert client.get('/api/usuario').status_code==401
    assert (coordinator(client,google) if coord else login_as(client,google)).status_code==403
    client.app.state.auth.provision()
    assert (coordinator(client,google) if coord else login_as(client,google)).status_code==403


@pytest.mark.parametrize('coord',[False,True])
def test_sub_survives_email_change_without_profile_change(workspace,coord):
    client,google,_=workspace
    if coord: coordinator(client,google)
    else: login_as(client,google)
    before=client.get('/api/usuario').json()
    new_email=('marcos' if coord else 'tiago')+'.renomeado@secco.example'
    assert login_as(client,google,email=new_email).status_code==303
    after=client.get('/api/usuario').json()
    assert before==after
    assert client.app.state.auth.get_user(after['id'])['email_current']==new_email
    canonical='marcos@secco.example' if coord else 'tiago@secco.example'
    assert login_as(client,google,email=canonical,sub='synthetic-different-account').status_code==403


def test_identity_cannot_be_bound_to_both_account_kinds(workspace):
    client,google,settings=workspace
    login_as(client,google)
    with pytest.raises(sqlite3.IntegrityError):
        with connect(settings.database_path) as db:
            db.execute("UPDATE coordination_accounts SET google_sub='synthetic-secco-tiago'")


def test_primary_mission_is_server_defined(workspace):
    client,google,settings=workspace
    client.cookies.set('secco_mission','portugal')
    assert login_as(client,google).headers['location']=='/missoes/argentina'
    with connect(settings.database_path) as db:
        db.execute('UPDATE app_users SET default_mission_id=1 WHERE participant_id=3')
    assert client.get('/',follow_redirects=False).headers['location']=='/missoes/argentina'
    assert client.post('/auth/preferencia',data={'missao':'portugal','csrf_token':client.cookies.get('secco_csrf')}).status_code==403
    assert coordinator(client,google).headers['location']=='/consolidado'
    assert client.post('/auth/preferencia',data={'missao':'argentina','csrf_token':client.cookies.get('secco_csrf')}).status_code==403


def test_workspace_grants_do_not_expand_primary_scope(workspace):
    client,google,settings=workspace
    login_as(client,google)
    user=client.get('/api/usuario').json()
    with connect(settings.database_path) as db:
        db.execute('INSERT INTO user_mission_permissions(user_id,mission_id,can_edit) VALUES(?,1,1)',(user['id'],))
    assert client.get('/api/usuario').json()['permissoes']['portugal']['editar'] is False


def test_coordination_logout_csrf_and_session_invalidation(workspace):
    client,google,settings=workspace
    coordinator(client,google); token=client.cookies.get('secco_session')
    assert client.post('/auth/logout',data={'csrf_token':'wrong'}).status_code==403
    assert client.post('/auth/logout',data={'csrf_token':client.cookies.get('secco_csrf')},follow_redirects=False).status_code==303
    assert client.get('/api/usuario',headers={'Cookie':'secco_session='+token}).status_code==401
    with connect(settings.database_path) as db:
        assert db.execute('SELECT revoked_at FROM coordination_sessions').fetchone()[0] is not None
        assert db.execute("SELECT COUNT(*) FROM auth_events WHERE coordinator_id IS NOT NULL AND event='logout'").fetchone()[0]==1


def test_coordination_expiry_and_secure_rotation(workspace):
    client,google,_=workspace
    now=[time.time()]; client.app.state.auth.clock=lambda:now[0]
    coordinator(client,google); first=client.cookies.get('secco_session')
    now[0]+=client.app.state.settings.session_rotation_seconds+1
    assert client.get('/api/usuario').status_code==200
    assert client.cookies.get('secco_session')!=first
    now[0]+=client.app.state.settings.session_idle_seconds+1
    assert client.get('/api/usuario').status_code==401


def test_removed_coordination_allowlist_revokes_existing_session(workspace):
    client,google,settings=workspace
    coordinator(client,google)
    changed=replace(settings,allowed_users=tuple(entry for entry in settings.allowed_users if entry[0]!=COORDINATOR_KEY))
    client.app.state.auth=AuthRepository(changed)
    assert client.get('/api/usuario').status_code==401


def test_production_startup_does_not_create_real_accounts(tmp_path,monkeypatch):
    # Simula o ramo normal fora de QA mantendo a guarda global de SQLite temporário ativa.
    import app.main as module
    settings=workspace_settings(tmp_path/'no-provision.sqlite3')
    monkeypatch.setattr(module,'testing_enabled',lambda:False)
    app,google=make_app(settings)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        assert login_as(client,google).status_code==403
        with connect(settings.database_path) as db:
            assert db.execute('SELECT COUNT(*) FROM app_users').fetchone()[0]==0
            assert db.execute('SELECT COUNT(*) FROM coordination_accounts').fetchone()[0]==0
        app.state.auth.provision()  # ação explícita somente nesta concessão sintética
        assert login_as(client,google).status_code==303


def test_explicit_operator_can_disable_coordination_but_not_grant_edit(workspace,monkeypatch):
    import sys
    from scripts import manage_access
    client,google,settings=workspace
    coordinator(client,google)
    monkeypatch.setattr(Settings,'from_env',classmethod(lambda cls:settings))
    monkeypatch.setattr(sys,'argv',['manage_access','grant','--account',COORDINATOR_KEY,'--mission','argentina'])
    with pytest.raises(SystemExit): manage_access.main()
    assert client.get('/api/usuario').json()['permissoes']['argentina']['editar'] is False
    monkeypatch.setattr(sys,'argv',['manage_access','disable','--account',COORDINATOR_KEY])
    manage_access.main()
    assert client.get('/api/usuario').status_code==401


def test_configuration_preflight_never_prints_secrets(workspace,capsys,monkeypatch):
    from scripts import check_auth_config
    _,_,settings=workspace
    ready=replace(settings,google_redirect_uri=check_auth_config.CALLBACK)
    monkeypatch.setattr(Settings,'from_env',classmethod(lambda cls:ready))
    assert check_auth_config.main()==0
    output=capsys.readouterr().out
    assert settings.google_client_secret not in output and settings.session_secret not in output
    result=json.loads(output)
    assert result['pronto'] and result['contas_na_allowlist']==5 and result['login_real_validado'] is False


def test_configuration_rejects_unapproved_workspace_profile(workspace,monkeypatch):
    _,_,settings=workspace
    wrong=replace(settings,allowed_users=((3,'intruso@secco.example'),))
    assert not wrong.auth_ready and 'ALLOWED_USERS' in wrong.auth_errors()
    monkeypatch.setattr('app.core.config.testing_enabled',lambda:False)
    other=replace(settings,google_workspace_domain='other.test')
    assert not other.auth_ready and 'GOOGLE_WORKSPACE_DOMAIN' in other.auth_errors()


def test_additive_migration_and_sessions_remain_integral(workspace):
    client,google,settings=workspace
    coordinator(client,google); identity=client.get('/api/usuario').json()
    migrate(settings.database_path); migrate(settings.database_path)
    assert client.get('/api/usuario').json()==identity
    with connect(settings.database_path) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert db.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0]==8
        assert db.execute('SELECT COUNT(*) FROM participants').fetchone()[0]==4


def test_coordination_read_does_not_import_or_edit_legacy_records(workspace):
    client,google,settings=workspace
    with connect(settings.database_path) as db:
        before=db.execute('SELECT COUNT(*) FROM itinerary_items').fetchone()[0]
        db.execute("INSERT INTO mission_events(mission_id,titulo,inicio_utc) VALUES(2,'Somente leitura sintetica','2026-11-18T10:00:00Z')")
    coordinator(client,google)
    assert client.get('/consolidado').status_code==200
    assert client.get('/missoes/argentina').status_code==200
    with connect(settings.database_path) as db:
        assert db.execute('SELECT COUNT(*) FROM itinerary_items').fetchone()[0]==before
        assert db.execute('SELECT COUNT(*) FROM itinerary_history').fetchone()[0]==0
