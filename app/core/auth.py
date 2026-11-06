"""Autorização separada do fluxo OIDC. Nenhum perfil implica custeio financeiro."""
from fastapi import HTTPException, Request

SESSION_COOKIE = "secco_session"
LOGIN_COOKIE = "secco_oidc"


def actor_id(request):
    user = getattr(request.state,"user",None)
    return user["id"] if user else None


def can_edit(request, mission_id):
    if request.app.state.settings.dev_no_auth:
        return True
    user = getattr(request.state,"user",None)
    return request.app.state.auth.can_edit(user,mission_id)


def authorize_mission_route(request: Request, codigo: str):
    mission = request.app.state.repository.get(codigo)
    if not mission:
        raise HTTPException(404,"Missão não encontrada.")
    editing_form = request.url.path.endswith(("/nova","/novo","/editar"))
    if (request.method not in ("GET","HEAD") or editing_form) and not can_edit(request,mission.id):
        raise HTTPException(403,"Você pode consultar esta missão, mas não possui permissão para editar seus registros.")


def set_session_cookie(response, settings, token, expires_at, now):
    response.set_cookie(SESSION_COOKIE,token,max_age=max(0,int(expires_at-now)),httponly=True,
        secure=settings.secure_cookies,samesite="lax",path="/")


def clear_session_cookie(response, settings):
    response.delete_cookie(SESSION_COOKIE,httponly=True,secure=settings.secure_cookies,samesite="lax",path="/")
