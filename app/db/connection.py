"""Uma conexão por operação, com integridade referencial sempre habilitada."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from app.core.test_database import enforce_database_policy, configure_connection, connection_factory


@contextmanager
def connect(database_path: Path):
    enforce_database_policy(database_path)
    connection = sqlite3.connect(database_path, timeout=10,factory=connection_factory())
    configure_connection(connection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    try:
        with connection:
            yield connection
    finally:
        connection.close()
