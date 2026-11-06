"""Migrações aditivas, com versão e checksum. Nunca recria o banco."""
import hashlib
from pathlib import Path

from app.core.config import ROOT
from app.db.connection import connect
from app.core.test_database import enforce_database_policy

MIGRATIONS = ROOT / "app" / "db" / "migrations"


def migrate(database_path: Path):
    enforce_database_policy(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(database_path) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY, checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        )""")
        known = {row["version"]: row["checksum"] for row in db.execute(
            "SELECT version, checksum FROM schema_migrations"
        )}
        files = sorted(MIGRATIONS.glob("*.sql"))
        if set(known) - {file.name for file in files}:
            raise RuntimeError("Banco com migrações desconhecidas. Atualize o código.")
        for file in files:
            sql = file.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            if file.name in known:
                if known[file.name] != checksum:
                    raise RuntimeError(f"Migração aplicada foi alterada: {file.name}")
                continue
            # O script e o registro da versão compartilham a mesma transação.
            try:
                db.executescript("BEGIN IMMEDIATE;\n" + sql)
                db.execute("INSERT INTO schema_migrations(version, checksum) VALUES (?, ?)",
                           (file.name, checksum))
                db.commit()
            except Exception:
                db.rollback()
                raise
