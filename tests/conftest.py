import os
from pathlib import Path

import pytest
from app.core.test_database import (
    TemporaryDatabase, assert_temporary_database, enable_test_mode,
)

# Executado antes de importar a aplicação ou carregar .env.
enable_test_mode()
if os.getenv("DATABASE_PATH"):
    assert_temporary_database(os.environ["DATABASE_PATH"])
_session_database = TemporaryDatabase()
os.environ["DATABASE_PATH"] = str(_session_database.path)
os.environ["SECCO_TEST_MODE"] = "1"

from fastapi.testclient import TestClient
from app.core.config import Settings
from app.db.connection import connect
from app.db.migrate import migrate
from app.db.seed import seed
from app.main import create_app
from app.repositories.missions import MissionRepository


def pytest_unconfigure(config):
    _session_database.close()


@pytest.fixture
def tmp_path():
    with TemporaryDatabase() as temporary:
        yield temporary.directory


@pytest.fixture
def database(tmp_path):
    location = tmp_path/"test.sqlite3"
    migrate(location)
    seed(location)
    return location


@pytest.fixture
def repository(database):
    return MissionRepository(database)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings("development",True,tmp_path/"web.sqlite3"))) as client:
        yield client
