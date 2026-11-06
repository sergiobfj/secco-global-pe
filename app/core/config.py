"""Configuração local e OIDC explícita. Ausência de configuração nunca libera acesso."""
from dataclasses import dataclass, field
from pathlib import Path
import json
import os
import re
from urllib.parse import urlsplit

from dotenv import load_dotenv
from app.core.test_database import testing_enabled, enforce_database_policy

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    app_env: str
    dev_no_auth: bool
    database_path: Path
    google_client_id: str = ""
    google_client_secret: str = field(default="", repr=False)
    google_redirect_uri: str = ""
    google_workspace_domain: str = ""
    allowed_users: tuple = field(default=(), repr=False)
    session_secret: str = field(default="", repr=False)
    session_idle_seconds: int = 1800
    session_absolute_seconds: int = 43200
    session_rotation_seconds: int = 900
    receipts_synthetic_enabled: bool = False

    @classmethod
    def from_env(cls):
        if not testing_enabled():
            load_dotenv(ROOT / ".env", override=False)
        raw_path = Path(os.getenv("DATABASE_PATH", "data/secco.sqlite3"))
        enforce_database_policy(raw_path)
        try:
            entries = json.loads(os.getenv("ALLOWED_USERS", "[]") or "[]")
            if not isinstance(entries, list):
                raise ValueError()
            allowed = tuple((entry["participant_id"], entry["email"].strip().casefold()) for entry in entries)
        except (ValueError, TypeError, KeyError, AttributeError):
            raise RuntimeError("ALLOWED_USERS deve ser uma lista JSON de participant_id e email.") from None
        try:
            idle = int(os.getenv("SESSION_IDLE_SECONDS", "1800"))
            absolute = int(os.getenv("SESSION_ABSOLUTE_SECONDS", "43200"))
            rotation = int(os.getenv("SESSION_ROTATION_SECONDS", "900"))
        except ValueError:
            raise RuntimeError("Os tempos de sessão devem ser números inteiros.") from None
        return cls(
            app_env=os.getenv("APP_ENV", "").strip().lower(),
            receipts_synthetic_enabled=os.getenv("RECEIPTS_SYNTHETIC_ENABLED", "false").strip().lower() == "true",
            dev_no_auth=os.getenv("DEV_NO_AUTH", "false").strip().lower() == "true",
            database_path=raw_path if raw_path.is_absolute() else ROOT / raw_path,
            google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
            google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
            google_redirect_uri=os.getenv("GOOGLE_REDIRECT_URI", "").strip(),
            google_workspace_domain=os.getenv("GOOGLE_WORKSPACE_DOMAIN", "").strip().casefold(),
            allowed_users=allowed,
            session_secret=os.getenv("SESSION_SECRET", ""),
            session_idle_seconds=idle,
            session_absolute_seconds=absolute,
            session_rotation_seconds=rotation,
        )

    @property
    def secure_cookies(self):
        return self.app_env == "production" or self.google_redirect_uri.startswith("https://")

    def auth_errors(self):
        errors = []
        if not self.google_client_id.endswith(".apps.googleusercontent.com"):
            errors.append("GOOGLE_CLIENT_ID")
        if not self.google_client_secret:
            errors.append("GOOGLE_CLIENT_SECRET")
        domain = self.google_workspace_domain
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", domain) or "." not in domain or ".." in domain:
            errors.append("GOOGLE_WORKSPACE_DOMAIN")
        try:
            uri = urlsplit(self.google_redirect_uri)
            local = uri.hostname in ("127.0.0.1", "localhost", "::1") or (testing_enabled() and uri.hostname == "testserver")
            if (uri.path != "/auth/google/callback" or uri.query or uri.fragment or uri.username or uri.password
                    or not uri.hostname or not (uri.scheme == "https" or (self.app_env == "development" and local and uri.scheme == "http"))):
                errors.append("GOOGLE_REDIRECT_URI")
        except ValueError:
            errors.append("GOOGLE_REDIRECT_URI")
        if len(self.session_secret.encode()) < 32 or self.session_secret.lower().startswith(("change", "example", "exemplo")):
            errors.append("SESSION_SECRET")
        try:
            ids = [entry[0] for entry in self.allowed_users]
            emails = [entry[1] for entry in self.allowed_users]
            if (not ids or len(set(ids)) != len(ids) or len(set(emails)) != len(emails)
                    or any(type(i) is not int or i <= 0 for i in ids)
                    or any(not isinstance(e,str) or len(e)>320 or not re.fullmatch(r"[^@\s]+@[^@\s]+", e) or e != e.casefold().strip() for e in emails)):
                errors.append("ALLOWED_USERS")
        except (TypeError, IndexError):
            errors.append("ALLOWED_USERS")
        return errors

    @property
    def auth_ready(self):
        return not self.auth_errors()

    def validate(self):
        enforce_database_policy(self.database_path)
        if self.app_env not in ("development", "production") or (self.dev_no_auth and self.app_env != "development"):
            raise RuntimeError("Acesso sem login exige APP_ENV=development e DEV_NO_AUTH=true. Esta versão não pode executar com acesso público por omissão.")
        if not (60 <= self.session_idle_seconds <= self.session_absolute_seconds <= 2592000
                and 60 <= self.session_rotation_seconds <= self.session_idle_seconds):
            raise RuntimeError("Confira os limites de expiração e renovação da sessão.")
        if self.receipts_synthetic_enabled and self.app_env != "development":
            raise RuntimeError("Captura sintética de comprovantes é permitida somente em desenvolvimento.")
        if self.app_env == "production" and not self.auth_ready:
            raise RuntimeError("Esta versão não pode executar em produção sem configuração OIDC completa e HTTPS.")
