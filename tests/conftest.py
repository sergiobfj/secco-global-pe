from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.connection import connect
from app.db.migrate import migrate
from app.db.seed import seed
from app.main import create_app
from app.repositories.missions import MissionRepository


@pytest.fixture
def database(tmp_path):
    location = tmp_path / "test.sqlite3"
    migrate(location)
    seed(location)
    return location


@pytest.fixture
def repository(database):
    return MissionRepository(database)


@pytest.fixture
def client(tmp_path):
    settings = Settings("development", True, tmp_path / "web.sqlite3")
    with TestClient(create_app(settings)) as test_client:
        yield test_client
