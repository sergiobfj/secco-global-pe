"""Entrada OIDC e logout. Nenhuma identidade sintética é criada por estas rotas."""
import secrets
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.core.auth import LOGIN_COOKIE, SESSION_COOKIE, clear_session_cookie, set_session_cookie
from app.core.forms import COOKIE, read_form
from app.repositories.auth import IdentityDenied
from app.core.workspace_access import configured_home
from app.routers.web import render
from app.services.oidc import AuthUnavailable, InvalidIdentity, ISSUERS

router = APIRouter()
ERRORS = {
    "acesso-negado":"Acesso não autorizado. Confirme sua conta Workspace e a liberação com o responsável.",
    "sessao-expirada":"Sua sessão expirou ou foi invalidada. Entre novamente para continuar.",
    "login-invalido":"Não foi possível validar esta tentativa de login. Inicie uma nova entrada.",
    "provedor-indisponivel":"Não foi possível conectar ao provedor de identidade. Tente novamente mais tarde.",
}


def login_page(request, error=None, status_code=None, logged_out=False, retry_from_login=False):
    configured = request.app.state.settings.auth_ready
    response = render(request,"login.html",title="Entrar",configured=configured,
        login_error=ERRORS.get(error),logged_out=logged_out,retry_from_login=retry_from_login)
    response.status_code = status_code or (200 if configured else 503)
    return response


def require_oidc_origin(request):
    expected = urlsplit(request.app.state.settings.google_redirect_uri)
    if (request.url.scheme,request.url.netloc)!=(expected.scheme,expected.netloc):
        raise HTTPException(400,"Use o endereço local configurado para iniciar a autenticação.")


@router.get("/login", name="login")
def login(request: Request, erro: str="", saiu: bool=False):
    if getattr(request.state,"user",None) and not erro:
        return RedirectResponse("/",status_code=303)
    return login_page(request,erro,logged_out=saiu)


@router.post("/auth/google", name="google_login")
async def google_login(request: Request):
    await read_form(request)
    if not request.app.state.settings.auth_ready:
        return login_page(request,status_code=503)
    require_oidc_origin(request)
    transaction = await run_in_threadpool(request.app.state.auth.begin_login)
    response = RedirectResponse(request.app.state.oidc.authorization_url(transaction),status_code=303)
    response.set_cookie(LOGIN_COOKIE,transaction["browser"],max_age=600,httponly=True,
        secure=request.app.state.settings.secure_cookies,samesite="lax",path="/auth")
    return response


@router.get("/auth/google/callback", name="google_callback")
async def google_callback(request: Request):
    settings = request.app.state.settings
    if not settings.auth_ready:
        return login_page(request,status_code=503)
    require_oidc_origin(request)
    auth = request.app.state.auth
    old_token = request.cookies.get(SESSION_COOKIE)
    try:
        if any(len(request.query_params.getlist(key))!=1 for key in request.query_params):
            raise IdentityDenied()
        transaction = await run_in_threadpool(auth.consume_login,request.query_params.get("state"),request.cookies.get(LOGIN_COOKIE))
        request.state.session_replaced = True
        await run_in_threadpool(auth.logout,old_token)
        if request.query_params.get("error"):
            raise IdentityDenied()
        if request.query_params.get("iss") and request.query_params["iss"] not in ISSUERS:
            raise IdentityDenied()
        claims = await request.app.state.oidc.exchange(request.query_params.get("code"),transaction)
        user_id = await run_in_threadpool(auth.bind_identity,claims)
        session = await run_in_threadpool(auth.create_session,user_id,old_token)
        user = await run_in_threadpool(auth.get_user,user_id)
        response = RedirectResponse(configured_home(settings,user),status_code=303)
        set_session_cookie(response,settings,session["token"],session["expires_at"],auth.clock())
        response.set_cookie(COOKIE,session["csrf"],httponly=True,secure=settings.secure_cookies,samesite="strict",path="/")
        response.delete_cookie("secco_mission",path="/")
    # Callback oculta seus parâmetros com no-referrer. Um formulário POST nessa
    # página enviaria Origin: null no navegador. A recuperação é sempre GET /login;
    # a nova tentativa mantém a validação estrita de origem, CSRF e PKCE.
    except (IdentityDenied,InvalidIdentity):
        response = login_page(request,"acesso-negado",status_code=403,retry_from_login=True)
        if request.state.session_replaced:
            clear_session_cookie(response,settings)
    except AuthUnavailable:
        response = login_page(request,"provedor-indisponivel",status_code=503,retry_from_login=True)
        clear_session_cookie(response,settings)
    if request.state.session_replaced:
        response.delete_cookie(LOGIN_COOKIE,httponly=True,secure=settings.secure_cookies,samesite="lax",path="/auth")
    return response


@router.post("/auth/logout", name="logout")
async def logout(request: Request):
    await read_form(request)
    if request.app.state.settings.auth_ready:
        await run_in_threadpool(request.app.state.auth.logout,request.cookies.get(SESSION_COOKIE))
    request.state.session_replaced = True
    response = RedirectResponse("/login?saiu=true",status_code=303)
    clear_session_cookie(response,request.app.state.settings)
    response.delete_cookie(LOGIN_COOKIE,path="/auth")
    response.delete_cookie(COOKIE,path="/")
    response.delete_cookie("secco_mission",path="/")
    return response


@router.post("/auth/preferencia", name="mission_preference")
async def mission_preference(request: Request):
    values = await read_form(request)
    user = getattr(request.state,"user",None)
    if not user:
        raise HTTPException(401,"Entre com sua conta autorizada.")
    code = values.get("missao")
    mission = request.app.state.repository.get(code) if code in ("portugal","argentina") else None
    if not mission:
        raise HTTPException(422,"Selecione uma missão válida.")
    if user.get("primary_locked"):
        raise HTTPException(403,"A visão principal deste perfil é definida pela coordenação no servidor.")
    await run_in_threadpool(request.app.state.auth.set_default,user["id"],mission.id)
    return RedirectResponse("/missoes/"+mission.codigo,status_code=303)


@router.get("/api/usuario")
def current_user(request: Request):
    user = getattr(request.state,"user",None)
    if not user:
        raise HTTPException(401,"Este ambiente local está sem identidade autenticada.")
    return {"id":user["id"],"participant_id":user["participant_id"],"nome":user["nome"],
        "missao_padrao":user["default_mission_code"],"perfil":"coordenacao" if user.get("is_coordinator") else "viajante",
        "visao_principal":"consolidada" if user.get("is_coordinator") else user["default_mission_code"],
        "permissoes":{m.codigo:{"consultar":True,"editar":request.app.state.auth.can_edit(user,m.id)}
            for m in request.app.state.repository.list()}}
