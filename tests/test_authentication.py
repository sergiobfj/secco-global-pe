import asyncio
from dataclasses import replace
import hashlib
import logging
import secrets
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.core.auth_logging import AuthQueryFilter
from app.core.config import Settings
from app.db.connection import connect
from app.db.migrate import migrate
from app.db.seed import seed
from app.main import create_app
from app.repositories.auth import AuthRepository
from app.services.oidc import InvalidIdentity, JWKS_URL
from auth_support import SyntheticGoogle, synthetic_settings, begin_login, finish_login, login_as
from test_diary import create_entry, entry_id, form_values, add_evidence, add_claim


@pytest.fixture
def authenticated_app(tmp_path):
    settings = synthetic_settings(tmp_path/"authenticated.sqlite3")
    app = create_app(settings)
    google = SyntheticGoogle(settings)
    app.state.oidc = google.provider()
    assert settings.dev_no_auth is False
    with TestClient(app,base_url="http://127.0.0.1") as client:
        yield client,google


def test_identity_associates_existing_participant_and_preserves_funding(authenticated_app):
    client,google = authenticated_app
    assert login_as(client,google).headers["location"]=="/missoes/argentina"
    user = client.get("/api/usuario").json()
    assert user["participant_id"]==3 and user["nome"]=="Tiago Prado"
    with connect(client.app.state.settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM participants").fetchone()[0]==4
        assert db.execute("SELECT COUNT(*) FROM app_users").fetchone()[0]==4
        assert [r[0] for r in db.execute("SELECT participant_id FROM mission_participants WHERE financiado_pela_subvencao=1 ORDER BY participant_id")]==[1,4]
        assert db.execute("SELECT google_sub FROM app_users WHERE participant_id=3").fetchone()[0]=="synthetic-tiago-sub"


@pytest.mark.parametrize("path",["/","/missoes/argentina","/missoes/portugal/planejamento","/missoes/argentina/diario","/secoes/organizacao"])
def test_unauthenticated_html_is_protected(authenticated_app,path):
    client,_ = authenticated_app
    response = client.get(path,follow_redirects=False)
    assert response.status_code==303 and response.headers["location"]=="/login"


def test_unauthenticated_api_and_mutation_are_denied(authenticated_app):
    client,_ = authenticated_app
    assert client.get("/api/missoes").status_code==401
    assert client.post("/missoes/argentina/atividades/nova",data={}).status_code==401
    assert client.post("/missoes/argentina/diario/novo",data={}).status_code==401


def test_unconfigured_authentication_fails_closed(tmp_path):
    with TestClient(create_app(Settings("development",False,tmp_path/"closed.sqlite3"))) as client:
        assert client.get("/",follow_redirects=False).status_code==303
        assert client.get("/api/missoes").status_code==503
        response = client.get("/login")
        assert response.status_code==503 and "Configuração do acesso pendente" in response.text and "disabled" in response.text
        assert client.post("/missoes/argentina/diario/novo",data={}).status_code==503


@pytest.mark.parametrize("overrides,remove",[
    ({"email":"outsider@workspace.test"},set()),
    ({"hd":"other.test"},set()),({}, {"hd"}),
    ({"exp":1},set()),({"aud":"wrong-audience"},set()),
    ({"iss":"https://evil.test"},set()),({"iss":"https://accounts.google.com.evil.test"},set()),
    ({"nonce":"wrong-nonce"},set()),({"email_verified":False},set()),
    ({"email_verified":"true"},set()),({"sub":42},set()),
    ({"iat":4102444800},set()),({}, {"nonce"}),({}, {"exp"}),
])
def test_invalid_identity_cannot_log_in(authenticated_app,overrides,remove):
    client,google = authenticated_app
    google.overrides = overrides
    google.remove = remove
    response = finish_login(client,begin_login(client,google))
    assert response.status_code==403
    assert not client.cookies.get("secco_session")
    with connect(client.app.state.settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM user_sessions").fetchone()[0]==0


def test_invalid_signature_denied(authenticated_app):
    client,google = authenticated_app
    google.invalid_signature = True
    assert login_as(client,google).status_code==403


@pytest.mark.parametrize("token",["invalid","a.b.c","", "x"*17000])
def test_invalid_tokens_denied(authenticated_app,token):
    client,google = authenticated_app
    google.bad_token = token
    assert login_as(client,google).status_code==403


def test_provider_failure_is_safe(authenticated_app):
    client,google = authenticated_app
    google.unavailable = True
    assert login_as(client,google).status_code==503
    assert client.get("/api/missoes").status_code==401


def test_email_change_with_same_sub_keeps_participant(authenticated_app):
    client,google = authenticated_app
    assert login_as(client,google).status_code==303
    first = client.get("/api/usuario").json()
    client.post("/auth/logout",data={"csrf_token":client.cookies.get("secco_csrf")},follow_redirects=False)
    assert login_as(client,google,email="renamed@workspace.test").status_code==303
    second = client.get("/api/usuario").json()
    assert second["id"]==first["id"] and second["participant_id"]==3
    assert client.app.state.auth.get_user(second["id"])["email_current"]=="renamed@workspace.test"


def test_email_reuse_cannot_replace_bound_google_identity(authenticated_app):
    client,google = authenticated_app
    assert login_as(client,google).status_code==303
    assert login_as(client,google,sub="different-synthetic-sub").status_code==403
    assert client.app.state.auth.get_user(3)["google_sub"]=="synthetic-tiago-sub"


def test_authorization_request_uses_state_nonce_pkce_and_minimal_scopes(authenticated_app):
    client,google = authenticated_app
    query = begin_login(client,google)
    assert query["scope"]==["openid email"]
    assert query["response_type"]==["code"] and query["code_challenge_method"]==["S256"]
    assert query["hd"]==["workspace.test"] and len(query["state"][0])>=40 and len(google.nonce)>=40
    assert "client_secret" not in query and "code_verifier" not in query
    assert finish_login(client,query).status_code==303


def test_login_requires_csrf(authenticated_app):
    client,_ = authenticated_app
    client.get("/login")
    assert client.post("/auth/google",data={"csrf_token":""}).status_code==403


def test_state_is_browser_bound_expiring_and_one_use(authenticated_app):
    client,google = authenticated_app
    query = begin_login(client,google)
    assert finish_login(client,query,state="wrong-state").status_code==403
    assert finish_login(client,query).status_code==303
    assert finish_login(client,query).status_code==403
    assert len([x for x in google.calls if x[0]=="POST"])==1


def test_state_from_other_browser_denied(authenticated_app):
    client,google = authenticated_app
    query = begin_login(client,google)
    client.cookies.delete("secco_oidc")
    assert finish_login(client,query).status_code==403
    assert google.calls==[]


def test_expired_state_denied(authenticated_app):
    client,google = authenticated_app
    query = begin_login(client,google)
    now = client.app.state.auth.clock()
    client.app.state.auth.clock = lambda: now+601
    assert finish_login(client,query).status_code==403


def test_session_cookie_fixation_logout_and_replay(authenticated_app):
    client,google = authenticated_app
    client.cookies.set("secco_session","attacker-fixed-value",domain="127.0.0.1",path="/")
    assert login_as(client,google).status_code==303
    token = client.cookies.get("secco_session")
    assert token and token!="attacker-fixed-value" and len(token)>=60
    assert client.post("/auth/logout",data={"csrf_token":""}).status_code==403
    response = client.post("/auth/logout",data={"csrf_token":client.cookies.get("secco_csrf")},follow_redirects=False)
    assert response.status_code==303 and not client.cookies.get("secco_session")
    assert client.get("/api/usuario",headers={"Cookie":"secco_session="+token}).status_code==401


def test_session_expires_by_inactivity(authenticated_app):
    client,google = authenticated_app
    login_as(client,google)
    now = client.app.state.auth.clock()
    client.app.state.auth.clock = lambda: now+1801
    assert client.get("/api/usuario").status_code==401


def test_session_absolute_expiration_despite_activity(authenticated_app):
    client,google = authenticated_app
    login_as(client,google)
    now = client.app.state.auth.clock()
    for elapsed in range(1700,43200,1700):
        client.app.state.auth.clock = lambda elapsed=elapsed: now+elapsed
        assert client.get("/api/usuario").status_code==200
    client.app.state.auth.clock = lambda: now+43201
    assert client.get("/api/usuario").status_code==401


def test_session_rotation_has_short_grace_and_revokes_on_logout(authenticated_app):
    client,google = authenticated_app
    login_as(client,google)
    old = client.cookies.get("secco_session")
    now = client.app.state.auth.clock()
    client.app.state.auth.clock = lambda: now+901
    assert client.get("/api/usuario").status_code==200
    new = client.cookies.get("secco_session")
    assert new!=old
    assert client.get("/api/usuario",headers={"Cookie":"secco_session="+old}).status_code==200
    client.app.state.auth.clock = lambda: now+932
    assert client.get("/api/usuario",headers={"Cookie":"secco_session="+old}).status_code==401
    assert client.get("/api/usuario",headers={"Cookie":"secco_session="+new}).status_code==200
    client.app.state.auth.logout(new)
    assert client.app.state.auth.resolve_session(new) is None


def test_disabled_user_session_invalidated(authenticated_app):
    client,google = authenticated_app
    login_as(client,google)
    with connect(client.app.state.settings.database_path) as db:
        db.execute("UPDATE app_users SET enabled=0 WHERE participant_id=3")
    assert client.get("/api/usuario").status_code==401


def test_allowlist_removal_and_secret_change_invalidate_access(authenticated_app):
    client,google = authenticated_app
    login_as(client,google)
    token = client.cookies.get("secco_session")
    original = client.app.state.settings
    removed = replace(original,allowed_users=tuple(x for x in original.allowed_users if x[0]!=3))
    assert AuthRepository(removed).resolve_session(token) is None
    changed = replace(original,session_secret="different-session-secret-"+"x"*64)
    assert AuthRepository(changed).resolve_session(token) is None


def test_default_mission_ignores_shared_browser_cookie(authenticated_app):
    client,google = authenticated_app
    client.cookies.set("secco_mission","portugal",domain="127.0.0.1",path="/")
    assert login_as(client,google).headers["location"]=="/missoes/argentina"
    assert client.get("/",follow_redirects=False).headers["location"]=="/missoes/argentina"
    assert "Tiago Prado" in client.get("/missoes/argentina").text
    response = client.post("/auth/preferencia",data={"missao":"portugal","csrf_token":client.cookies.get("secco_csrf")},follow_redirects=False)
    assert response.status_code==303
    assert client.get("/",follow_redirects=False).headers["location"]=="/missoes/portugal"


def test_cross_mission_read_allowed_write_and_forms_denied(authenticated_app):
    client,google = authenticated_app
    login_as(client,google)
    assert client.get("/missoes/portugal").status_code==200
    page = client.get("/missoes/portugal/planejamento")
    assert "Missão em modo de consulta" in page.text and "Nova atividade" not in page.text
    for url in ("/missoes/portugal/atividades/nova","/missoes/portugal/diario/novo"):
        assert client.get(url).status_code==403
        assert client.post(url,data={"csrf_token":client.cookies.get("secco_csrf")}).status_code==403
    result = client.get("/api/usuario").json()
    assert result["permissoes"]["portugal"]=={"consultar":True,"editar":False}
    assert result["permissoes"]["argentina"]["editar"] is True


def test_explicit_cross_mission_permission_is_separate_from_subvention(authenticated_app):
    client,google = authenticated_app
    login_as(client,google)
    user = client.get("/api/usuario").json()
    with connect(client.app.state.settings.database_path) as db:
        db.execute("INSERT INTO user_mission_permissions(user_id,mission_id,can_edit) VALUES(?,1,1)",(user["id"],))
    response,_ = create_entry(client,"portugal",status="rascunho")
    assert response.status_code==200
    assert client.get("/api/usuario").json()["permissoes"]["portugal"]["editar"] is True
    with connect(client.app.state.settings.database_path) as db:
        assert db.execute("SELECT financiado_pela_subvencao FROM mission_participants WHERE participant_id=3").fetchone()[0]==0


def test_diary_agenda_preservation_and_attribution(authenticated_app):
    client,google = authenticated_app
    login_as(client,google)
    user = client.get("/api/usuario").json()
    values = form_values(client,"/missoes/argentina/atividades/nova",titulo="Compromisso sintético",categoria="institucional",status="a_confirmar",organizacao="Organização sintética")
    values["created_by_user_id"] = "999999"
    response = client.post("/missoes/argentina/atividades/nova",data=values,headers={"Accept":"application/json"})
    assert response.status_code==200,response.text
    url = response.json()["redirect"].split("?")[0]
    item_id = int(url.rsplit("/",1)[1])
    response = client.get(f"/missoes/argentina/diario/novo?agenda={item_id}")
    assert response.status_code==200 and "Organização sintética" in response.text
    response,_ = create_entry(client,itinerary_item_id=str(item_id),status="rascunho")
    diary_id = entry_id(response)
    add_evidence(client,"argentina",diary_id,status="pendente",referencia_url="",referencia_chave="",conferido_por="",nota_conferencia="")
    with connect(client.app.state.settings.database_path) as db:
        for table,identity in (("itinerary_items",item_id),("diary_entries",diary_id)):
            row = db.execute(f"SELECT created_by_user_id,updated_by_user_id FROM {table} WHERE id=?",(identity,)).fetchone()
            assert tuple(row)==(user["id"],user["id"])
        assert db.execute("SELECT actor_user_id FROM itinerary_history WHERE item_id=?",(item_id,)).fetchone()[0]==user["id"]
        assert all(r[0]==user["id"] for r in db.execute("SELECT actor_user_id FROM diary_history WHERE entry_id=?",(diary_id,)))
        assert db.execute("PRAGMA foreign_key_check").fetchall()==[]
    assert "Criado por Tiago Prado" in client.get(url).text


def test_csrf_is_bound_to_authenticated_session(authenticated_app):
    client,google = authenticated_app
    client.get("/login")
    old_csrf = client.cookies.get("secco_csrf")
    login_as(client,google)
    assert client.cookies.get("secco_csrf")!=old_csrf
    headers = {"Cookie":"secco_session="+client.cookies.get("secco_session")+"; secco_csrf="+old_csrf}
    response = client.post("/auth/preferencia",data={"csrf_token":old_csrf,"missao":"portugal"},headers=headers)
    assert response.status_code==403


def test_no_raw_tokens_or_session_secret_in_database(authenticated_app):
    client,google = authenticated_app
    query = begin_login(client,google)
    assert finish_login(client,query).status_code==303
    raw_session = client.cookies.get("secco_session")
    with connect(client.app.state.settings.database_path) as db:
        values = " ".join(str(tuple(r)) for r in db.execute("SELECT * FROM user_sessions"))
        assert raw_session not in values
        assert "synthetic-access-token" not in values
        assert client.app.state.settings.google_client_secret not in values
        assert db.execute("SELECT COUNT(*) FROM oauth_transactions").fetchone()[0]==0
    assert client.app.state.settings.session_secret not in repr(client.app.state.settings)


def test_callback_access_log_redacts_state_and_code():
    record = logging.LogRecord("uvicorn.access",20,"",0,"%s %s %s %s %s",("client","GET","/auth/google/callback?code=SECRET&state=OTHER","1.1",200),None)
    assert AuthQueryFilter().filter(record)
    assert "SECRET" not in record.getMessage() and "OTHER" not in record.getMessage()


def test_migration_is_additive_and_initialization_idempotent(authenticated_app):
    client,_ = authenticated_app
    location = client.app.state.settings.database_path
    migrate(location);seed(location);client.app.state.auth.provision()
    migrate(location);seed(location);client.app.state.auth.provision()
    with connect(location) as db:
        assert db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]==4
        assert db.execute("SELECT COUNT(*) FROM app_users").fetchone()[0]==4
        assert db.execute("SELECT COUNT(*) FROM participants").fetchone()[0]==4
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall()==[]


def test_every_mission_mutation_has_backend_authorization(authenticated_app):
    client,_ = authenticated_app
    from app.core.auth import authorize_mission_route
    for route in client.app.routes:
        if getattr(route,"path","").startswith("/missoes/") and "POST" in getattr(route,"methods",set()):
            assert any(d.call==authorize_mission_route for d in route.dependant.dependencies), route.path


@pytest.mark.parametrize("participant_id,email,code",[(1,"hugo@workspace.test","portugal"),(2,"alan@workspace.test","portugal"),(4,"bruno@workspace.test","argentina")])
def test_each_traveler_has_existing_default_mission(authenticated_app,participant_id,email,code):
    client,google = authenticated_app
    response = login_as(client,google,email=email,sub=f"synthetic-account-{participant_id}")
    assert response.status_code==303 and response.headers["location"]=="/missoes/"+code
    assert client.get("/api/usuario").json()["participant_id"]==participant_id


def test_production_cookies_are_secure_httponly_and_same_site(tmp_path):
    settings = synthetic_settings(tmp_path/"secure.sqlite3",app_env="production",google_redirect_uri="https://127.0.0.1/auth/google/callback")
    app = create_app(settings)
    google = SyntheticGoogle(settings)
    app.state.oidc = google.provider()
    with TestClient(app,base_url="https://127.0.0.1") as client:
        query = begin_login(client,google)
        oidc_cookie = next(c for c in client.cookies.jar if c.name=="secco_oidc")
        assert oidc_cookie.secure and oidc_cookie._rest["SameSite"]=="lax"
        response = finish_login(client,query)
        assert response.status_code==303
        header = next(h for h in response.headers.get_list("set-cookie") if h.startswith("secco_session="))
        assert "HttpOnly" in header and "Secure" in header and "SameSite=lax" in header
        assert "Domain=" not in header
        assert client.get("/api/usuario").status_code==200


def test_existing_sessions_revoked_when_logging_in_again(authenticated_app):
    client,google = authenticated_app
    login_as(client,google)
    first = client.cookies.get("secco_session")
    login_as(client,google)
    second = client.cookies.get("secco_session")
    assert first!=second
    assert client.get("/api/usuario",headers={"Cookie":"secco_session="+first}).status_code==401
    assert client.get("/api/usuario",headers={"Cookie":"secco_session="+second}).status_code==200


def test_invalid_state_cannot_force_logout_of_existing_user(authenticated_app):
    client,google = authenticated_app
    login_as(client,google)
    response = client.get("/auth/google/callback",params={"state":"invalid","code":"invalid"})
    assert response.status_code==403
    assert client.get("/api/usuario").status_code==200


@pytest.mark.parametrize("header",[{"jku":"https://evil.test/keys"},{"crit":["unknown"]},{"alg":"HS256"}])
def test_untrusted_header_and_algorithm_denied(authenticated_app,header):
    client,google = authenticated_app
    if header.get("alg")=="HS256":
        import jwt
        google.bad_token = jwt.encode({"sub":"synthetic"},"synthetic-key-"*10,algorithm="HS256",headers={"kid":"synthetic-key"})
    else:
        google.header = header
    assert login_as(client,google).status_code==403


def test_unknown_kid_refresh_is_bounded(authenticated_app):
    client,google = authenticated_app
    google.header = {"kid":"unknown"}
    assert login_as(client,google).status_code==403
    assert login_as(client,google).status_code==403
    assert sum(url==JWKS_URL for method,url in google.calls)==1


def test_admin_label_does_not_implicitly_grant_cross_mission_access(authenticated_app):
    client,google = authenticated_app
    login_as(client,google)
    with connect(client.app.state.settings.database_path) as db:
        db.execute("UPDATE app_users SET role='admin' WHERE participant_id=3")
    assert client.get("/api/usuario").json()["permissoes"]["portugal"]["editar"] is False


def test_diary_and_agenda_edits_cannot_cross_missions(authenticated_app):
    client,google = authenticated_app
    login_as(client,google,email="hugo@workspace.test",sub="synthetic-hugo")
    response,_ = create_entry(client,"portugal",status="rascunho")
    identity = entry_id(response)
    login_as(client,google,email="tiago@workspace.test",sub="synthetic-tiago-sub")
    assert client.get(f"/missoes/portugal/diario/{identity}").status_code==200
    for suffix in ("/editar","/evidencias/nova","/metas/nova"):
        url = f"/missoes/portugal/diario/{identity}"+suffix
        assert client.get(url).status_code==403
        assert client.post(url,data={"csrf_token":client.cookies.get("secco_csrf")}).status_code==403
    item = client.app.state.itinerary.list(1)[0]
    assert client.get(f"/missoes/portugal/atividades/{item['id']}").status_code==200
    for action in ("editar","cancelar"):
        assert client.post(f"/missoes/portugal/atividades/{item['id']}/{action}",data={"csrf_token":client.cookies.get("secco_csrf")}).status_code==403


def test_local_mode_does_not_create_authenticated_identity(client):
    assert client.app.state.settings.dev_no_auth is True
    assert client.get("/api/usuario").status_code==401
    response,_ = create_entry(client,status="rascunho")
    row = client.app.state.diary.get(2,entry_id(response))
    assert row["created_by_user_id"] is None and row["updated_by_user_id"] is None


def test_missing_verification_dependency_fails_closed(authenticated_app,monkeypatch):
    import builtins
    client,google = authenticated_app
    original = builtins.__import__
    def import_without_jwt(name,*args,**kwargs):
        if name=="jwt":
            raise ImportError("dependência ausente no cenário de teste")
        return original(name,*args,**kwargs)
    # O token sintético é assinado antes de indisponibilizar a biblioteca no verificador.
    query = begin_login(client,google)
    token = google.token()
    google.bad_token = token
    monkeypatch.setattr(builtins,"__import__",import_without_jwt)
    assert finish_login(client,query).status_code==503


def test_previous_three_migrations_preserved():
    from app.core.config import ROOT
    expected = {"001_foundation.sql":"b4b905d3033057eaef2db5855ec9a74587d34fe868773122c9b59f030592d434", "002_itinerary.sql":"6bcc1590e154633781746fcd901b899ef016b77b499211e7c9bed91dafa77b5b"}
    expected["003_diary.sql"] = "f4da718ba22c0adc582a33338695d722b45731d7213f558362b49e07376a3e18"
    for name,digest in expected.items():
        assert hashlib.sha256((ROOT/"app/db/migrations"/name).read_bytes()).hexdigest()==digest


@pytest.mark.parametrize("changes,field",[
    ({"google_client_id":""},"GOOGLE_CLIENT_ID"),({"google_client_secret":""},"GOOGLE_CLIENT_SECRET"),
    ({"google_workspace_domain":""},"GOOGLE_WORKSPACE_DOMAIN"),({"google_workspace_domain":"*.workspace.test"},"GOOGLE_WORKSPACE_DOMAIN"),
    ({"google_redirect_uri":"http://evil.test/auth/google/callback"},"GOOGLE_REDIRECT_URI"),
    ({"google_redirect_uri":"http://127.0.0.1/callback"},"GOOGLE_REDIRECT_URI"),
    ({"google_redirect_uri":"http://127.0.0.1/auth/google/callback?next=evil"},"GOOGLE_REDIRECT_URI"),
    ({"session_secret":"weak"},"SESSION_SECRET"),({"allowed_users":()},"ALLOWED_USERS"),
    ({"allowed_users":((3,"a@workspace.test"),(3,"b@workspace.test"))},"ALLOWED_USERS"),
    ({"allowed_users":((3,"a@workspace.test"),(4,"a@workspace.test"))},"ALLOWED_USERS"),
])
def test_configuration_requirements_are_fail_closed(tmp_path,changes,field):
    settings = synthetic_settings(tmp_path/"configuration.sqlite3",**changes)
    assert field in settings.auth_errors() and not settings.auth_ready


def test_default_environment_does_not_enable_bypass(monkeypatch):
    monkeypatch.delenv("DEV_NO_AUTH",raising=False)
    monkeypatch.setenv("APP_ENV","development")
    assert Settings.from_env().dev_no_auth is False


def test_invalid_allowlist_json_is_rejected_without_exposing_value(monkeypatch):
    monkeypatch.setenv("ALLOWED_USERS","NOT-JSON-SENSITIVE-VALUE")
    with pytest.raises(RuntimeError) as error:
        Settings.from_env()
    assert "NOT-JSON-SENSITIVE-VALUE" not in str(error.value)


def test_secure_configuration_does_not_fall_back_to_dev_mode(tmp_path):
    from dataclasses import replace
    settings = synthetic_settings(tmp_path/"production.sqlite3",app_env="production",dev_no_auth=True)
    with pytest.raises(RuntimeError):
        settings.validate()


def test_unknown_participant_does_not_create_participant(tmp_path):
    settings = synthetic_settings(tmp_path/"unknown.sqlite3",allowed_users=((999,"unknown@workspace.test"),))
    with pytest.raises(RuntimeError,match="participante"):
        with TestClient(create_app(settings)):
            pass
    with connect(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM participants").fetchone()[0]==4


def test_permitted_coworker_edit_preserves_original_author(authenticated_app):
    client,google = authenticated_app
    login_as(client,google)
    values = form_values(client,"/missoes/argentina/atividades/nova",titulo="QA autoria inicial",categoria="institucional",status="a_confirmar")
    response = client.post("/missoes/argentina/atividades/nova",data=values,headers={"Accept":"application/json"})
    item_id = int(response.json()["redirect"].split("?")[0].rsplit("/",1)[1])
    diary_response,_ = create_entry(client,status="rascunho")
    diary_id = entry_id(diary_response)
    login_as(client,google,email="bruno@workspace.test",sub="synthetic-bruno")
    edit = {**values,"csrf_token":client.cookies.get("secco_csrf"),"version":"1","titulo":"QA título revisado"}
    assert client.post(f"/missoes/argentina/atividades/{item_id}/editar",data=edit,headers={"Accept":"application/json"}).status_code==200
    assert client.post(f"/missoes/argentina/atividades/{item_id}/cancelar",data={"csrf_token":client.cookies.get("secco_csrf"),"version":"2"},headers={"Accept":"application/json"}).status_code==200
    record = client.app.state.diary.get(2,diary_id)
    record.update(csrf_token=client.cookies.get("secco_csrf"),participantes=[],titulo="QA Diário revisado")
    assert client.post(f"/missoes/argentina/diario/{diary_id}/editar",data=record,headers={"Accept":"application/json"}).status_code==200
    add_claim(client,"argentina",diary_id,validacao_status="pendente",validado_por="",criterio_referencia="",justificativa="")
    with connect(client.app.state.settings.database_path) as db:
        for table,identity in (("itinerary_items",item_id),("diary_entries",diary_id)):
            assert tuple(db.execute(f"SELECT created_by_user_id,updated_by_user_id FROM {table} WHERE id=?",(identity,)).fetchone())==(3,4)
        assert [r[0] for r in db.execute("SELECT actor_user_id FROM itinerary_history WHERE item_id=? ORDER BY id",(item_id,))]==[3,4,4]
        assert db.execute("SELECT created_by_user_id FROM diary_goal_claims WHERE entry_id=?",(diary_id,)).fetchone()[0]==4


def test_local_operator_grant_revoke_and_disable(authenticated_app,monkeypatch):
    import sys
    from scripts import manage_access
    client,google = authenticated_app
    login_as(client,google)
    settings = client.app.state.settings
    monkeypatch.setattr(Settings,"from_env",classmethod(lambda cls:settings))
    for action,expected in (("grant",True),("revoke",False)):
        monkeypatch.setattr(sys,"argv",["manage_access",action,"--participant-id","3","--mission","portugal"])
        manage_access.main()
        assert client.get("/api/usuario").json()["permissoes"]["portugal"]["editar"] is expected
    monkeypatch.setattr(sys,"argv",["manage_access","disable","--participant-id","3"])
    manage_access.main()
    assert client.get("/api/usuario").status_code==401


def test_callback_parameters_do_not_allow_issuer_or_redirect_injection(authenticated_app):
    client,google = authenticated_app
    query = begin_login(client,google)
    assert finish_login(client,query,iss="https://evil.test",next="https://evil.test").status_code==403
    assert client.get("/api/usuario").status_code==401


def test_bound_sessions_do_not_survive_client_id_change(authenticated_app):
    client,google = authenticated_app
    login_as(client,google)
    token = client.cookies.get("secco_session")
    changed = replace(client.app.state.settings,google_client_id="other.apps.googleusercontent.com")
    assert AuthRepository(changed).resolve_session(token) is None


def test_login_native_form_keeps_origin_while_callback_hides_parameters(authenticated_app):
    client,google = authenticated_app
    assert client.get("/login").headers["referrer-policy"]=="same-origin"
    query = begin_login(client,google)
    assert finish_login(client,query).headers["referrer-policy"]=="no-referrer"


def test_public_assets_and_health_do_not_clear_valid_session(authenticated_app):
    client,google = authenticated_app
    login_as(client,google)
    token = client.cookies.get("secco_session")
    for url in ("/static/css/auth.css","/static/brand/secco-logo-horizontal-forest.svg","/health"):
        response = client.get(url)
        assert response.status_code==200
        assert not any(c.startswith("secco_session=") for c in response.headers.get_list("set-cookie"))
    assert client.cookies.get("secco_session")==token
    assert client.get("/api/usuario").status_code==200
