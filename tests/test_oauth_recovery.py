"""Regressão do retorno OAuth: somente identidades assinadas e SQLite temporário."""
from urllib.parse import parse_qs, urlsplit
import httpx
import pytest
from app.db.connection import connect
from app.services.oidc import GoogleOIDC
from auth_support import begin_login, finish_login, login_as
from test_authentication import authenticated_app
from test_workspace_access import workspace


@pytest.mark.parametrize('headers',[
    {},
    {'Referer':'https://accounts.google.com/','Sec-Fetch-Site':'cross-site'},
    {'Origin':'https://accounts.google.com','Sec-Fetch-Site':'cross-site'},
])
def test_external_get_callback_uses_oauth_proofs_not_form_origin(authenticated_app,headers):
    client,google=authenticated_app
    query=begin_login(client,google)
    response=client.get('/auth/google/callback',params={'state':query['state'][0],'code':'synthetic-code'},headers=headers,follow_redirects=False)
    assert response.status_code==303
    assert response.headers['location']=='/missoes/argentina'
    assert response.headers['referrer-policy']=='no-referrer'
    assert client.get('/api/usuario').json()['participant_id']==3


@pytest.mark.parametrize('failure',['connection','timeout','http','invalid_state','invalid_nonce','invalid_signature','denied'])
def test_callback_failure_recovers_by_get_without_post_under_no_referrer(authenticated_app,failure):
    client,google=authenticated_app
    query=begin_login(client,google)
    params={'state':query['state'][0],'code':'synthetic-code'}
    if failure=='connection': google.unavailable=True
    elif failure in ('timeout','http'):
        def failed(request):
            if failure=='timeout': raise httpx.ReadTimeout('synthetic-timeout',request=request)
            return httpx.Response(503,json={'error':'synthetic-provider-error'})
        client.app.state.oidc=GoogleOIDC(client.app.state.settings,transport=httpx.MockTransport(failed))
    elif failure=='invalid_state': params['state']='synthetic-invalid-state'
    elif failure=='invalid_nonce': google.overrides['nonce']='synthetic-invalid-nonce'
    elif failure=='invalid_signature': google.invalid_signature=True
    else: params={'state':query['state'][0],'error':'access_denied'}
    response=client.get('/auth/google/callback',params=params,follow_redirects=False)
    assert response.status_code==(503 if failure in ('connection','timeout','http') else 403)
    assert response.headers['referrer-policy']=='no-referrer'
    assert 'href="/login">Tentar novamente' in response.text
    assert '<form' not in response.text
    assert query['state'][0] not in response.text
    assert 'synthetic-code' not in response.text
    assert not client.cookies.get('secco_session')
    page=client.get('/login',headers={'Sec-Fetch-Site':'same-origin'})
    assert page.status_code==200 and page.headers['referrer-policy']=='same-origin'
    assert 'action="/auth/google"' in page.text
    google.unavailable=False;google.invalid_signature=False;google.overrides.clear()
    client.app.state.oidc=google.provider()
    assert login_as(client,google).status_code==303


@pytest.mark.parametrize('headers',[
    {'Origin':'https://attacker.test'},
    {'Origin':'null'},
    {'Referer':'https://attacker.test/form'},
    {'Origin':'http://127.0.0.1','Sec-Fetch-Site':'cross-site'},
])
def test_external_or_opaque_post_remains_denied_with_correct_csrf(authenticated_app,headers):
    client,google=authenticated_app
    client.get('/login')
    response=client.post('/auth/google',data={'csrf_token':client.cookies.get('secco_csrf')},headers=headers,follow_redirects=False)
    assert response.status_code==403
    assert 'href="/login">Tentar novamente' in response.text
    assert google.calls==[]
    with connect(client.app.state.settings.database_path) as db:
        assert db.execute('SELECT count(*) FROM oauth_transactions').fetchone()[0]==0


@pytest.mark.parametrize('headers',[{}, {'Referer':'http://127.0.0.1/login','Sec-Fetch-Site':'same-origin'}])
def test_legitimate_post_without_origin_still_requires_csrf(authenticated_app,headers):
    client,_=authenticated_app
    client.get('/login')
    assert client.post('/auth/google',data={'csrf_token':'invalid'},headers=headers).status_code==403
    response=client.post('/auth/google',data={'csrf_token':client.cookies.get('secco_csrf')},headers=headers,follow_redirects=False)
    assert response.status_code==303
    query=parse_qs(urlsplit(response.headers['location']).query)
    assert query['code_challenge_method']==['S256']
    assert query['scope']==['openid email']


def test_callback_is_get_only_and_does_not_consume_state_on_post(authenticated_app):
    client,google=authenticated_app
    query=begin_login(client,google)
    assert client.post('/auth/google/callback',data={'state':query['state'][0],'code':'synthetic-code'}).status_code==405
    assert google.calls==[]
    assert finish_login(client,query).status_code==303


def test_wrong_browser_callback_is_not_accepted_from_google_referer(authenticated_app):
    client,google=authenticated_app
    query=begin_login(client,google)
    client.cookies.delete('secco_oidc')
    response=client.get('/auth/google/callback',params={'state':query['state'][0],'code':'synthetic-code'},headers={'Referer':'https://accounts.google.com/'},follow_redirects=False)
    assert response.status_code==403 and google.calls==[]


def test_expired_session_reentry_and_logout_preserve_mission_permissions(workspace):
    client,google,_=workspace
    assert login_as(client,google).headers['location']=='/missoes/argentina'
    identity=client.get('/api/usuario').json()
    assert identity['permissoes']['argentina']['editar'] is True
    assert identity['permissoes']['portugal']['editar'] is False
    assert client.get('/missoes/portugal/atividades/nova').status_code==403
    now=client.app.state.auth.clock()
    client.app.state.auth.clock=lambda:now+1801
    response=client.get('/missoes/argentina',follow_redirects=False)
    assert response.status_code==303 and response.headers['location']=='/login?erro=sessao-expirada'
    assert 'Sua sessão expirou' in client.get(response.headers['location']).text
    assert login_as(client,google).headers['location']=='/missoes/argentina'
    token=client.cookies.get('secco_session')
    csrf=client.cookies.get('secco_csrf')
    assert client.post('/auth/logout',data={'csrf_token':csrf},headers={'Origin':'https://attacker.test'}).status_code==403
    assert client.post('/auth/logout',data={'csrf_token':'invalid'}).status_code==403
    assert client.post('/auth/logout',data={'csrf_token':csrf},headers={'Origin':'http://127.0.0.1'},follow_redirects=False).status_code==303
    assert client.app.state.auth.resolve_session(token) is None


@pytest.mark.parametrize('email,home',[
 ('tiago@secco.example','/missoes/argentina'),
 ('bruno@secco.example','/missoes/argentina'),
 ('hugo@secco.example','/missoes/portugal'),
 ('alan@secco.example','/missoes/portugal'),
 ('marcos@secco.example','/consolidado'),
])
def test_external_callback_returns_to_server_defined_home(workspace,email,home):
    client,google,_=workspace
    google.overrides.update(email=email,sub='synthetic-recovery-'+email.split('@')[0])
    query=begin_login(client,google)
    response=client.get('/auth/google/callback',params={'state':query['state'][0],'code':'synthetic-code','next':'https://attacker.test'},headers={'Sec-Fetch-Site':'cross-site','Referer':'https://accounts.google.com/'},follow_redirects=False)
    assert response.status_code==303 and response.headers['location']==home
