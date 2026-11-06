"""Configuração local e OIDC explícita. Ausência de configuração nunca libera acesso."""
from dataclasses import dataclass, field
from pathlib import Path
import json
import os
import re
from urllib.parse import urlsplit

from dotenv import load_dotenv
from app.core.workspace_access import COORDINATOR_KEY, SECCO_ACCOUNTS, WORKSPACE_DOMAIN
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
    receipts_storage_backend: str = "temporary"
    receipts_private_dir: Path | None = None
    receipts_drive_mode: str = 'disabled'
    google_drive_argentina_id: str = '0AARGENTINAEXEMPLO1'
    google_drive_portugal_id: str = '0APORTUGALEXEMPLO01'
    google_drive_folders_json: str = '{}'

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
            allowed = tuple((entry.get("participant_id",entry.get("account")), entry["email"].strip().casefold()) for entry in entries)
        except (ValueError, TypeError, KeyError, AttributeError):
            raise RuntimeError("ALLOWED_USERS deve ser uma lista JSON de participant_id ou account e email.") from None
        try:
            idle = int(os.getenv("SESSION_IDLE_SECONDS", "1800"))
            absolute = int(os.getenv("SESSION_ABSOLUTE_SECONDS", "43200"))
            rotation = int(os.getenv("SESSION_ROTATION_SECONDS", "900"))
        except ValueError:
            raise RuntimeError("Os tempos de sessão devem ser números inteiros.") from None
        return cls(
            receipts_drive_mode=os.getenv('RECEIPTS_DRIVE_MODE', 'disabled').strip().lower(),
            google_drive_argentina_id=os.getenv('GOOGLE_DRIVE_ARGENTINA_ID', '0AARGENTINAEXEMPLO1').strip(),
            google_drive_portugal_id=os.getenv('GOOGLE_DRIVE_PORTUGAL_ID', '0APORTUGALEXEMPLO01').strip(),
            google_drive_folders_json=os.getenv('GOOGLE_DRIVE_FOLDERS_JSON', '{}'),
            receipts_storage_backend=os.getenv("RECEIPTS_STORAGE_BACKEND", "temporary").strip().lower(),
            receipts_private_dir=Path(os.environ["RECEIPTS_PRIVATE_DIR"]) if os.getenv("RECEIPTS_PRIVATE_DIR") else None,
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
        if not testing_enabled() and domain != WORKSPACE_DOMAIN:
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
                    or any(not ((type(i) is int and i>0) or i==COORDINATOR_KEY) for i in ids)
                    or any(not isinstance(e,str) or len(e)>320 or not re.fullmatch(r"[^@\s]+@[^@\s]+", e) or e != e.casefold().strip() for e in emails)):
                errors.append("ALLOWED_USERS")
            if self.google_workspace_domain==WORKSPACE_DOMAIN and any(
                key not in SECCO_ACCOUNTS or SECCO_ACCOUNTS[key][0]!=email for key,email in self.allowed_users):
                errors.append("ALLOWED_USERS")
        except (TypeError, IndexError):
            errors.append("ALLOWED_USERS")
        return errors

    @property
    def auth_ready(self):
        return not self.auth_errors()

    def validate(self):
        enforce_database_policy(self.database_path)
        from app.core.drive_config import DriveConfiguration
        DriveConfiguration(self.google_drive_argentina_id, self.google_drive_portugal_id,
                           self.google_drive_folders_json).validate()
        if self.receipts_drive_mode not in ('disabled', 'simulated'):
            raise RuntimeError('Envio real ao Drive bloqueado nesta etapa.')
        if self.receipts_drive_mode == 'simulated' and not (
                testing_enabled() and self.app_env == 'development' and not self.dev_no_auth
                and self.receipts_synthetic_enabled and self.receipts_storage_backend == 'local'):
            raise RuntimeError('Drive simulado exige testes isolados e armazenamento local sintético autenticado.')
        if self.app_env not in ("development", "production") or (self.dev_no_auth and self.app_env != "development"):
            raise RuntimeError("Acesso sem login exige APP_ENV=development e DEV_NO_AUTH=true. Esta versão não pode executar com acesso público por omissão.")
        if not (60 <= self.session_idle_seconds <= self.session_absolute_seconds <= 2592000
                and 60 <= self.session_rotation_seconds <= self.session_idle_seconds):
            raise RuntimeError("Confira os limites de expiração e renovação da sessão.")
        if self.receipts_synthetic_enabled and self.app_env != "development":
            raise RuntimeError("Captura sintética de comprovantes é permitida somente em desenvolvimento.")
        if self.receipts_storage_backend not in ("temporary","local"):
            raise RuntimeError("Adaptador de armazenamento desconhecido.")
        if self.receipts_storage_backend=="local":
            if self.app_env!="development" or not self.receipts_synthetic_enabled or self.dev_no_auth or not self.auth_ready:
                raise RuntimeError("Persistência local exige desenvolvimento sintético explicitamente habilitado e autenticação configurada.")
            if self.receipts_private_dir is None:
                raise RuntimeError("Configure RECEIPTS_PRIVATE_DIR para ativar a persistência local.")
            from app.core.storage_paths import validate_private_directory
            validate_private_directory(self.receipts_private_dir,self.database_path)
        if self.app_env == "production" and not self.auth_ready:
            raise RuntimeError("Esta versão não pode executar em produção sem configuração OIDC completa e HTTPS.")
