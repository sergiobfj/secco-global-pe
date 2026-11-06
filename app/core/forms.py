"""Formulários locais com CSRF e limite de tamanho, sem dependência multipart."""
import secrets
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException, Request

COOKIE = "secco_csrf"


def csrf_token(request):
    return request.cookies.get(COOKIE) or secrets.token_urlsafe(32)


async def read_form(request: Request):
    request.app.state.settings.validate()
    origin = request.headers.get("origin")
    expected = f"{request.url.scheme}://{request.url.netloc}"
    if origin and origin != expected:
        raise HTTPException(403,"Origem da solicitação não permitida.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403,"Solicitação de outro site recusada.")
    referer = request.headers.get("referer")
    if not origin and referer:
        parsed = urlsplit(referer)
        if f"{parsed.scheme}://{parsed.netloc}" != expected:
            raise HTTPException(403,"Origem da solicitação não permitida.")
    if request.headers.get("content-type","").split(";")[0] != "application/x-www-form-urlencoded":
        raise HTTPException(415,"Envie um formulário compatível.")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>196608:
            raise HTTPException(413,"O formulário excede o limite permitido.")
    try:
        parsed = parse_qs(body.decode("utf-8"),keep_blank_values=True,max_num_fields=60)
    except (ValueError,UnicodeDecodeError):
        raise HTTPException(400,"Formulário inválido.")
    values = {key:(value if key=="participantes" else value[-1]) for key,value in parsed.items()}
    token = values.get("csrf_token","")
    cookie = request.cookies.get(COOKIE,"")
    if not cookie or not isinstance(token,str) or not secrets.compare_digest(token,cookie):
        raise HTTPException(403,"A sessão do formulário expirou. Reabra a página antes de salvar.")
    return values
