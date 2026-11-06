"""Configuração explícita para a etapa local, sem simular autenticação."""
from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    app_env: str
    dev_no_auth: bool
    database_path: Path

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env", override=False)
        raw_path = Path(os.getenv("DATABASE_PATH", "data/secco.sqlite3"))
        return cls(
            app_env=os.getenv("APP_ENV", "").strip().lower(),
            dev_no_auth=os.getenv("DEV_NO_AUTH", "").strip().lower() == "true",
            database_path=raw_path if raw_path.is_absolute() else ROOT / raw_path,
        )

    def validate(self):
        if self.app_env != "development" or not self.dev_no_auth:
            raise RuntimeError(
                "Acesso sem login exige APP_ENV=development e DEV_NO_AUTH=true. "
                "Esta versão não pode executar em produção."
            )
