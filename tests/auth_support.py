"""Provedor sintético somente nos testes. Nenhuma conta Google real."""
import hashlib
import json
import time
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings
from app.services.oidc import GoogleOIDC, JWKS_URL, TOKEN_URL, base64url


def synthetic_settings(path, **changes):
    settings = Settings("development",False,path,
        google_client_id="synthetic-client.apps.googleusercontent.com",
        google_client_secret="SOMENTE-SEGREDO-SINTETICO-DE-TESTE",
        google_redirect_uri="http://127.0.0.1/auth/google/callback",
        google_workspace_domain="workspace.test",
        allowed_users=((1,"hugo@workspace.test"),(2,"alan@workspace.test"),(3,"tiago@workspace.test"),(4,"bruno@workspace.test")),
        session_secret="SOMENTE-TESTE-"+"a"*64)
    return replace(settings,**changes)


class SyntheticGoogle:
    def __init__(self, settings):
        self.settings = settings
        self.key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
        self.jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        self.jwk.update(kid="synthetic-key",alg="RS256",use="sig")
        self.overrides = {}
        self.remove = set()
        self.header = {}
        self.invalid_signature = False
        self.bad_token = None
        self.unavailable = False
        self.calls = []
        self.nonce = "synthetic-nonce"
        self.challenge = None

    def token(self):
        now = int(time.time())
        claims = {"iss":"https://accounts.google.com","aud":self.settings.google_client_id,
            "sub":"synthetic-tiago-sub","exp":now+3600,"iat":now,
            "email":"tiago@workspace.test","email_verified":True,
            "hd":"workspace.test","nonce":self.nonce,**self.overrides}
        for key in self.remove:
            claims.pop(key,None)
        if self.bad_token is not None:
            return self.bad_token
        private_key = rsa.generate_private_key(public_exponent=65537,key_size=2048) if self.invalid_signature else self.key
        return jwt.encode(claims,private_key,algorithm="RS256",headers={"kid":"synthetic-key",**self.header})

    def transport(self, request):
        self.calls.append((request.method,str(request.url)))
        if self.unavailable:
            raise httpx.ConnectError("falha sintética",request=request)
        if str(request.url)==JWKS_URL:
            return httpx.Response(200,json={"keys":[self.jwk]})
        if str(request.url)==TOKEN_URL:
            data = parse_qs(request.content.decode())
            assert data["grant_type"]==["authorization_code"]
            assert data["client_id"]==[self.settings.google_client_id]
            assert data["client_secret"]==[self.settings.google_client_secret]
            assert data["redirect_uri"]==[self.settings.google_redirect_uri]
            verifier = data["code_verifier"][0]
            assert self.challenge==base64url(hashlib.sha256(verifier.encode()).digest())
            return httpx.Response(200,json={"id_token":self.token(),"access_token":"synthetic-access-token"})
        raise AssertionError("Requisição externa inesperada no teste")

    def provider(self):
        return GoogleOIDC(self.settings,transport=httpx.MockTransport(self.transport))


def begin_login(client, google):
    page = client.get("/login")
    assert page.status_code==200
    response = client.post("/auth/google",data={"csrf_token":client.cookies.get("secco_csrf")},follow_redirects=False)
    assert response.status_code==303,response.text
    url = urlsplit(response.headers["location"])
    assert url.netloc=="accounts.google.com"
    query = parse_qs(url.query)
    google.nonce = query["nonce"][0]
    google.challenge = query["code_challenge"][0]
    return query


def finish_login(client, query, **params):
    return client.get("/auth/google/callback",params={"state":query["state"][0],"code":"synthetic-code",**params},follow_redirects=False)


def login_as(client, google, **claims):
    google.overrides.update(claims)
    return finish_login(client,begin_login(client,google))
