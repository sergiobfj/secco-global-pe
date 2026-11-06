"""SQLite de testes exige uma concessão temporária ativa, nunca apenas um nome."""
from contextlib import AbstractContextManager
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import sys
import tempfile
from threading import RLock
from urllib.parse import unquote, urlsplit

_ROOT = Path(__file__).resolve().parents[2]
_RawConnection = sqlite3.Connection
_raw_connect = sqlite3.connect
_active = False
_leases = {}
_connections = {}
_cleanup_directories = set()
_lock = RLock()


class UnsafeTestDatabase(RuntimeError):
    pass


def testing_enabled():
    return _active


def enable_test_mode():
    global _active
    _active = True
    sqlite3.connect = isolated_connect
    sqlite3.dbapi2.connect = isolated_connect
    sqlite3.Connection = _IsolatedConnection
    sqlite3.dbapi2.Connection = _IsolatedConnection


def _database_path(value):
    raw = os.fsdecode(value)
    if raw == ":memory:":
        return None
    if raw.startswith("file:"):
        parsed = urlsplit(raw)
        if parsed.netloc and parsed.netloc != "localhost":
            raise UnsafeTestDatabase("URI SQLite de rede não permitida em testes.")
        raw = unquote(parsed.path)
        if os.name == "nt" and raw.startswith("/") and len(raw)>2 and raw[2]==":":
            raw = raw[1:]
    if not raw:
        raise UnsafeTestDatabase("O caminho do banco de testes deve ser explícito.")
    return Path(raw).absolute()


def assert_temporary_database(value):
    candidate = _database_path(value)
    if candidate is None:
        return
    resolved = candidate.resolve()
    if candidate.is_relative_to(_ROOT/"data") or resolved.is_relative_to((_ROOT/"data").resolve()):
        raise UnsafeTestDatabase("Testes recusados: o banco operacional não pode ser usado.")
    with _lock:
        leases = list(_leases.items())
    for directory, nonce in leases:
        if not resolved.is_relative_to(directory):
            continue
        marker = directory/".secco-test-owner"
        if directory.resolve()!=directory or directory.is_symlink():
            break
        if not marker.is_file() or marker.read_text(encoding="utf-8")!=nonce:
            break
        if candidate.exists() and candidate.stat().st_nlink>1:
            raise UnsafeTestDatabase("Links físicos de bancos não são permitidos em testes.")
        return
    raise UnsafeTestDatabase(
        "Testes recusados: SQLite precisa estar dentro de uma concessão temporária ativa. "
        "Bancos persistentes, mesmo com nome de teste, não são permitidos."
    )


def enforce_database_policy(value):
    if _active:
        assert_temporary_database(value)
    elif os.getenv("SECCO_TEST_MODE") or "pytest" in sys.modules:
        raise UnsafeTestDatabase("Ative o isolamento temporário antes de abrir SQLite em testes.")


def _protect_filesystem(value):
    if not isinstance(value,(str,bytes,os.PathLike)): return
    candidate=Path(os.fsdecode(value)).absolute()
    resolved=candidate.resolve()
    protected=candidate.is_relative_to(_ROOT/"data") or resolved.is_relative_to((_ROOT/"data").resolve()) or (_ROOT/"data").resolve().is_relative_to(resolved)
    if protected:
        raise UnsafeTestDatabase("Testes não podem modificar arquivos do banco operacional.")
    if candidate.suffix.lower() in (".sqlite3",".sqlite",".db",".sqlite3-wal",".sqlite3-shm",".sqlite3-journal"):
        with _lock:
            cleaning=any(resolved.is_relative_to(folder) for folder in _cleanup_directories)
        if not cleaning: assert_temporary_database(candidate)


def _audit(event,args):
    if _active and event=="open":
        mode=args[1]
        flags=args[2] if len(args)>2 else 0
        if (isinstance(mode,str) and any(c in mode for c in "wax+")) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC)):
            _protect_filesystem(args[0])
    elif _active and event in ("os.remove","os.rmdir","shutil.rmtree"):
        _protect_filesystem(args[0])
    elif _active and event in ("os.rename","os.link","os.symlink"):
        for value in args[:2]: _protect_filesystem(value)
    elif event=="sqlite3.connect":
        enforce_database_policy(args[0])
    elif _active and event=="sqlite3.enable_load_extension" and args[1]:
        raise UnsafeTestDatabase("Extensões SQLite são proibidas em testes.")


sys.addaudithook(_audit)


def configure_connection(connection):
    if _active:
        def authorize(action,first,second,database,trigger):
            return sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_ATTACH else sqlite3.SQLITE_OK
        connection.set_authorizer(authorize)
    return connection


class _IsolatedConnection(_RawConnection):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._closed = False
        configure_connection(self)
        candidate = _database_path(args[0] if args else kwargs["database"])
        if candidate:
            with _lock:
                for directory in _leases:
                    if candidate.resolve().is_relative_to(directory):
                        _connections[directory].append(self)
                        break

    def close(self):
        if not getattr(self,"_closed",False):
            super().close()
            self._closed = True


def isolated_connect(*args,**kwargs):
    database = args[0] if args else kwargs.get("database")
    enforce_database_policy(database)
    if len(args)>5:
        if args[5] is not _IsolatedConnection:
            raise UnsafeTestDatabase("Factory SQLite não permitida no ambiente de testes.")
    else:
        if kwargs.get("factory",_IsolatedConnection) is not _IsolatedConnection:
            raise UnsafeTestDatabase("Factory SQLite não permitida no ambiente de testes.")
        kwargs["factory"] = _IsolatedConnection
    return _raw_connect(*args,**kwargs)


def connection_factory():
    return _IsolatedConnection if _active else _RawConnection


class TemporaryDatabase(AbstractContextManager):
    def __init__(self):
        enable_test_mode()
        self.parent = Path(tempfile.gettempdir()).resolve()
        self.directory = Path(tempfile.mkdtemp(prefix="secco-test-",dir=self.parent)).resolve()
        self.nonce = secrets.token_urlsafe(32)
        (self.directory/".secco-test-owner").write_text(self.nonce,encoding="utf-8")
        self.path = self.directory/"test.sqlite3"
        self.closed = False
        with _lock:
            _leases[self.directory] = self.nonce
            _connections[self.directory] = []

    def __enter__(self):
        return self

    def close(self):
        if self.closed:
            return
        with _lock:
            connections = _connections.pop(self.directory,[])
        for connection in connections:
            connection.close()
        marker = self.directory/".secco-test-owner"
        safe = (self.directory.resolve()==self.directory
                and self.directory.parent==self.parent
                and self.directory.name.startswith("secco-test-")
                and not self.directory.is_symlink()
                and marker.is_file()
                and marker.read_text(encoding="utf-8")==self.nonce)
        with _lock:
            _leases.pop(self.directory,None)
        if not safe:
            raise UnsafeTestDatabase("Limpeza recusada: a pasta temporária não passou na verificação de propriedade.")
        with _lock:
            _cleanup_directories.add(self.directory)
        try:
            shutil.rmtree(self.directory)
            self.closed = True
        finally:
            with _lock:
                _cleanup_directories.discard(self.directory)

    def __exit__(self,exc_type,exc,traceback):
        self.close()
