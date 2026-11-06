from contextlib import closing
import os
import sqlite3
from pathlib import Path

import pytest

from app.core.config import ROOT, Settings
from app.core.test_database import TemporaryDatabase, UnsafeTestDatabase, assert_temporary_database
from app.db.connection import connect
from app.db.migrate import migrate


@pytest.mark.parametrize("candidate",[
    ROOT/"data/secco.sqlite3",
    ROOT/".tools/qa-persistent.sqlite3",
    ROOT/"persistent-test.sqlite3",
])
def test_persistent_databases_refused(candidate):
    with pytest.raises(UnsafeTestDatabase):
        with connect(candidate):
            pass
    with pytest.raises(UnsafeTestDatabase):
        sqlite3.connect(candidate)
    with pytest.raises(UnsafeTestDatabase):
        Settings("development",True,candidate).validate()


def test_sqlite_uri_cannot_bypass_guard():
    uri="file:"+str(ROOT/"data/secco.sqlite3").replace("\\","/")+"?mode=ro"
    with pytest.raises(UnsafeTestDatabase):
        sqlite3.connect(uri,uri=True)


def test_migration_refuses_operational_path_before_writing():
    with pytest.raises(UnsafeTestDatabase):
        migrate(ROOT/"data/secco.sqlite3")


def test_lease_creates_and_cleans_only_owned_directory():
    lease=TemporaryDatabase()
    directory=lease.directory
    with lease:
        with connect(lease.path) as db:
            db.execute("CREATE TABLE example(id INTEGER)")
        assert lease.path.exists()
    assert not directory.exists()
    with pytest.raises(UnsafeTestDatabase):
        assert_temporary_database(lease.path)


def test_cleanup_refuses_changed_marker():
    lease=TemporaryDatabase()
    marker=lease.directory/".secco-test-owner"
    marker.write_text("alterado",encoding="utf-8")
    with pytest.raises(UnsafeTestDatabase,match="Limpeza recusada"):
        lease.close()
    assert lease.directory.exists()
    marker.write_text(lease.nonce,encoding="utf-8")
    lease.close()


def test_memory_is_ephemeral():
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("CREATE TABLE example(id INTEGER)")


def test_attach_is_blocked(tmp_path):
    with connect(tmp_path/"safe.sqlite3") as db:
        with pytest.raises((sqlite3.DatabaseError,UnsafeTestDatabase)):
            db.execute("ATTACH DATABASE ? AS other",(str(tmp_path/"forbidden.sqlite3"),))


def test_raw_sqlite_attach_is_blocked_by_audit(tmp_path):
    # A conexão direta também só pode abrir o temporário autorizado.
    with closing(sqlite3.connect(tmp_path/"raw.sqlite3")) as db:
        with pytest.raises((sqlite3.DatabaseError,UnsafeTestDatabase)):
            db.execute("ATTACH DATABASE ? AS other",(str(ROOT/"data/secco.sqlite3"),))


def test_hardlink_refused(tmp_path):
    with connect(tmp_path/"source.sqlite3") as db:
        db.execute("CREATE TABLE example(id INTEGER)")
    try:
        os.link(tmp_path/"source.sqlite3",tmp_path/"alias.sqlite3")
    except OSError:
        pytest.skip("O sistema não disponibiliza links físicos para este teste.")
    with pytest.raises(UnsafeTestDatabase):
        sqlite3.connect(tmp_path/"alias.sqlite3")


def test_env_cannot_select_operational_database(monkeypatch):
    monkeypatch.setenv("DATABASE_PATH",str(ROOT/"data/secco.sqlite3"))
    with pytest.raises(UnsafeTestDatabase):
        Settings.from_env()


@pytest.mark.parametrize("event,args",[("os.remove",(str(ROOT/"data/secco.sqlite3"),None)),("os.rename",(str(ROOT/"data/secco.sqlite3"),str(ROOT/"data/outro.sqlite3"),None,None)),("shutil.rmtree",(str(ROOT/"data"),None))])
def test_filesystem_mutations_are_blocked_without_executing_them(event,args):
    import sys
    with pytest.raises(UnsafeTestDatabase):
        sys.audit(event,*args)

def test_persistent_sqlite_file_cannot_be_created_by_python():
    with pytest.raises(UnsafeTestDatabase):
        (ROOT/".tools/never-create.sqlite3").write_bytes(b"test")


def test_connection_failure_does_not_fall_back_to_persistent_database(tmp_path):
    missing = tmp_path / "missing-parent" / "test.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        with connect(missing):
            pass
    assert not missing.exists()
    with connect(tmp_path / "recovered.sqlite3") as db:
        assert db.execute("SELECT 1").fetchone()[0] == 1
