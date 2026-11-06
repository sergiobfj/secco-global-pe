"""Uma conexão por operação, com integridade referencial sempre habilitada."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3


@contextmanager
def connect(database_path: Path):
    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    try:
        with connection:
            yield connection
    finally:
        connection.close()
