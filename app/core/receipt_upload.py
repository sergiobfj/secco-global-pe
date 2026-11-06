"""Multipart limitado em memória, sem escrita antes de CSRF e validação.

Parser MIME da biblioteca padrão, aceitando apenas o subconjunto form-data.
Corpos, partes, cabeçalhos e campos têm limites independentes.
"""
from email import policy
from email.errors import MessageError
from email.parser import BytesParser
import secrets
from urllib.parse import urlsplit
from fastapi import HTTPException
from app.core.forms import COOKIE

MAX_BODY=12*1024*1024


async def read_receipt_form(request):
    request.app.state.settings.validate()
    expected=f"{request.url.scheme}://{request.url.netloc}"
    origin=request.headers.get("origin")
    referer=request.headers.get("referer")
    if origin and origin!=expected or request.headers.get("sec-fetch-site")=="cross-site":
        raise HTTPException(403,"Origem da solicitação não permitida.")
    if not origin and referer:
        parsed=urlsplit(referer)
        if f"{parsed.scheme}://{parsed.netloc}"!=expected: raise HTTPException(403,"Origem da solicitação não permitida.")
    content_type=request.headers.get("content-type","")
    if not content_type.lower().startswith("multipart/form-data;") or len(content_type)>200 or "\r" in content_type or "\n" in content_type:
        raise HTTPException(415,"Envie o formulário com seus anexos.")
    body=bytearray()
    async for chunk in request.stream():
        if len(body)+len(chunk)>MAX_BODY: raise HTTPException(413,"O envio excede 12 MB. Reduza os arquivos e tente novamente.")
        body.extend(chunk)
    try:
        message=BytesParser(policy=policy.default).parsebytes(b"Content-Type: "+content_type.encode("ascii")+b"\r\nMIME-Version: 1.0\r\n\r\n"+body)
        if not message.is_multipart() or message.defects or message.preamble or message.epilogue and message.epilogue.strip(): raise ValueError()
        boundary=message.get_boundary()
        if not boundary or not 1<=len(boundary)<=70: raise ValueError()
        parts=list(message.iter_parts())
        if len(parts)>60: raise ValueError()
        values={}; files=[]
        for part in parts:
            if part.is_multipart() or part.defects or len(str(part).split("\n\n",1)[0])>4096: raise ValueError()
            if part.get_content_disposition()!="form-data" or part.get("Content-Transfer-Encoding"): raise ValueError()
            if any(len(part.get_all(key,[]))>1 for key in ("Content-Disposition","Content-Type")): raise ValueError()
            name=part.get_param("name",header="content-disposition")
            if not name or len(name)>80: raise ValueError()
            content=part.get_payload(decode=True)
            if not isinstance(content,bytes): raise ValueError()
            filename=part.get_filename()
            if filename is not None:
                if name not in ("camera","files"): raise ValueError()
                if not filename and not content: continue
                files.append({"name":filename,"mime":part.get_content_type(),"content":content})
                if len(files)>4: raise ValueError()
            else:
                if name in values or len(content)>8192: raise ValueError()
                values[name]=content.decode("utf-8",errors="strict")
        token=values.get("csrf_token","")
        cookie=request.cookies.get(COOKIE,"")
        bound=getattr(request.state,"auth_csrf",None)
        if not cookie or not secrets.compare_digest(token,cookie) or bound and not secrets.compare_digest(token,bound):
            raise HTTPException(403,"A sessão do formulário expirou. Reabra a página antes de salvar.")
        return values,files
    except (ValueError,UnicodeError,TypeError,MessageError):
        raise HTTPException(400,"Formulário de comprovante inválido. Confira os arquivos e tente novamente.") from None
