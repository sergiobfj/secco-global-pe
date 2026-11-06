"""Google Authorization Code + PKCE S256 e validação criptográfica no servidor."""
import asyncio
import base64
import hashlib
import hmac
import re
import time
from urllib.parse import urlencode

import httpx

AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")


class InvalidIdentity(ValueError):
    pass


class AuthUnavailable(RuntimeError):
    pass


def base64url(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class GoogleOIDC:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport
        self._keys = {}
        self._expires = 0
        self._last_fetch = float("-inf")
        self._lock = asyncio.Lock()

    def authorization_url(self, transaction):
        s = self.settings
        return AUTHORIZATION_URL + "?" + urlencode({
            "response_type":"code", "client_id":s.google_client_id,
            "redirect_uri":s.google_redirect_uri, "scope":"openid email",
            "state":transaction["state"], "nonce":transaction["nonce"],
            "hd":s.google_workspace_domain, "prompt":"select_account",
            "code_challenge":base64url(hashlib.sha256(transaction["verifier"].encode()).digest()),
            "code_challenge_method":"S256",
        })

    async def _json(self, method, url, **kwargs):
        try:
            async with httpx.AsyncClient(transport=self.transport,timeout=10,follow_redirects=False,trust_env=False) as client:
                async with client.stream(method,url,**kwargs) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body)>131072:
                            raise ValueError()
                    import json
                    data = json.loads(body)
                    if not isinstance(data,dict):
                        raise ValueError()
                    return data
        except (httpx.HTTPError,ValueError,TypeError,RecursionError):
            raise AuthUnavailable("O provedor de identidade não está disponível.") from None

    async def _key(self, kid, jwt):
        now = time.monotonic()
        async with self._lock:
            if now>=self._expires or (kid not in self._keys and now-self._last_fetch>=60):
                self._last_fetch = now
                data = await self._json("GET",JWKS_URL)
                try:
                    entries = data["keys"]
                    if not isinstance(entries,list) or not 1<=len(entries)<=20:
                        raise ValueError()
                    keys = {}
                    for item in entries:
                        if (not isinstance(item,dict) or item.get("kty")!="RSA" or item.get("alg")!="RS256"
                                or item.get("use")!="sig" or not isinstance(item.get("kid"),str)):
                            continue
                        key = jwt.PyJWK.from_dict(item,algorithm="RS256").key
                        if key.key_size<2048 or item["kid"] in keys:
                            raise ValueError()
                        keys[item["kid"]] = key
                    if not keys:
                        raise ValueError()
                    self._keys, self._expires = keys, now+300
                except (KeyError,ValueError,TypeError,AttributeError,RecursionError,jwt.PyJWTError):
                    raise AuthUnavailable("Não foi possível conferir as chaves de identidade.") from None
            key = self._keys.get(kid)
            if key is None:
                raise InvalidIdentity()
            return key

    async def verify(self, token, nonce_hash, access_token=None):
        try:
            import jwt
        except ImportError:
            raise AuthUnavailable("As dependências de autenticação precisam ser instaladas.") from None
        try:
            if not isinstance(token,str) or len(token)>16384:
                raise InvalidIdentity()
            parts = token.split(".")
            if len(parts)!=3 or any(not re.fullmatch(r"[A-Za-z0-9_-]+",part) for part in parts) or len(parts[0])>2048:
                raise InvalidIdentity()
            header = jwt.get_unverified_header(token)
            if (header.get("alg")!="RS256" or header.get("typ") not in (None,"JWT")
                    or set(header)-{"alg","kid","typ"} or not isinstance(header.get("kid"),str)
                    or not 1<=len(header["kid"])<=200):
                raise InvalidIdentity()
            key = await self._key(header["kid"],jwt)
            claims = jwt.decode(token,key,algorithms=["RS256"],audience=self.settings.google_client_id,
                issuer=ISSUERS,leeway=0,options={"require":["iss","aud","exp","iat","sub","nonce","email","email_verified","hd"],
                    "enforce_minimum_key_length":True})
            if (not isinstance(claims["sub"],str) or not 1<=len(claims["sub"])<=255 or claims["sub"].strip()!=claims["sub"]
                    or not isinstance(claims["email"],str) or len(claims["email"])>320
                    or not re.fullmatch(r"[^@\s]+@[^@\s]+",claims["email"])
                    or claims["email_verified"] is not True
                    or not isinstance(claims["hd"],str) or claims["hd"].casefold()!=self.settings.google_workspace_domain
                    or not isinstance(claims["nonce"],str)
                    or not hmac.compare_digest(hashlib.sha256(claims["nonce"].encode()).hexdigest(),nonce_hash)):
                raise InvalidIdentity()
            audience = claims["aud"]
            if ("azp" in claims and claims["azp"]!=self.settings.google_client_id) or (isinstance(audience,list) and claims.get("azp")!=self.settings.google_client_id):
                raise InvalidIdentity()
            if "at_hash" in claims:
                if not isinstance(access_token,str) or not isinstance(claims["at_hash"],str):
                    raise InvalidIdentity()
                expected = base64url(hashlib.sha256(access_token.encode()).digest()[:16])
                if not hmac.compare_digest(claims["at_hash"],expected):
                    raise InvalidIdentity()
            return claims
        except (jwt.PyJWTError,ValueError,TypeError,KeyError,AttributeError,RecursionError):
            raise InvalidIdentity() from None

    async def exchange(self, code, transaction):
        if not isinstance(code,str) or not 1<=len(code)<=4096:
            raise InvalidIdentity()
        data = await self._json("POST",TOKEN_URL,data={
            "grant_type":"authorization_code", "code":code,
            "client_id":self.settings.google_client_id,
            "client_secret":self.settings.google_client_secret,
            "redirect_uri":self.settings.google_redirect_uri,
            "code_verifier":transaction["code_verifier"],
        },headers={"Accept":"application/json"})
        # ID/access tokens existem apenas durante esta chamada, sem persistência ou logs.
        return await self.verify(data.get("id_token"),transaction["nonce_hash"],data.get("access_token"))
