"""Journal e backup do ensaio sintético. Schema próprio, sem migrations/008.

Só aceita SQLite dentro da concessão temporária ativa. Não usa Settings, despesas,
usuários reais ou volume operacional. Arquivo ZIP guarda apenas este ensaio.
"""
from dataclasses import asdict
from contextlib import AbstractContextManager
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import secrets
import zipfile

from app.core.storage_paths import reject_links
from app.core.test_database import assert_temporary_database
from app.db.connection import connect
from app.services.drive_supervised import mapping_digest, probe_png
from app.services.storage_contracts import DriveError, StoredReceipt


class ProbeArchiveLock(AbstractContextManager):
    def __init__(self, archive):
        self.archive=Path(archive).absolute()
        self.stream=None

    def __enter__(self):
        if self.archive.suffix != '.zip': raise DriveError('backup')
        reject_links(self.archive)
        self.archive.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        lock=self.archive.with_suffix('.zip.lock')
        reject_links(lock)
        descriptor=os.open(lock,os.O_RDWR|os.O_CREAT,0o600)
        self.stream=os.fdopen(descriptor,'r+b')
        if self.stream.seek(0,2)==0:
            self.stream.write(b'0'); self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise DriveError('ensaio_em_uso') from None
        return self

    def __exit__(self,*args):
        if self.stream: self.stream.close()


class ProbeJournal:
    def __init__(self, directory, configuration):
        self.directory = Path(directory).absolute()
        self.database_path = self.directory/'probe.sqlite3'
        assert_temporary_database(self.database_path)
        reject_links(self.directory)
        self.directory.mkdir(mode=0o700, exist_ok=False)
        self.configuration = configuration

    @classmethod
    def create(cls, directory, configuration):
        self = cls(directory, configuration)
        run_id = secrets.token_hex(8)
        volume = secrets.token_hex(24)
        self._write(self.directory/'.volume.json', json.dumps({'id':volume,'run_id':run_id}).encode())
        with connect(self.database_path) as db:
            db.executescript('''CREATE TABLE probe_run(run_id TEXT PRIMARY KEY,volume_id TEXT NOT NULL,mapping_sha256 TEXT NOT NULL);
                CREATE TABLE probe_items(mission TEXT PRIMARY KEY,item TEXT NOT NULL,sync_key TEXT NOT NULL UNIQUE,
                remote_id TEXT UNIQUE,state TEXT NOT NULL DEFAULT 'aguardando',ever_verified INTEGER NOT NULL DEFAULT 0,
                error_code TEXT,attempts INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE probe_events(id INTEGER PRIMARY KEY,mission TEXT,state TEXT,error_code TEXT);''')
            db.execute('INSERT INTO probe_run VALUES(?,?,?)', (run_id,volume,mapping_digest(configuration)))
            for mission, mission_id in (('argentina',2),('portugal',1)):
                content = probe_png(mission)
                key = hashlib.sha256((run_id+':'+mission).encode()).hexdigest()
                item = StoredReceipt(key[:32],mission_id,1,key,hashlib.sha256(content).hexdigest(),
                    len(content),'png','image/png',mission,f'secco-ensaio-{run_id}-{mission}.png','deslocamentos')
                self._write(self.directory/(mission+'.png'), content)
                db.execute('INSERT INTO probe_items(mission,item,sync_key) VALUES(?,?,?)',
                           (mission,json.dumps(asdict(item),sort_keys=True),key))
        self.validate()
        return self

    @staticmethod
    def _write(path, content):
        reject_links(path)
        descriptor = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())

    def rows(self):
        with connect(self.database_path) as db:
            return [dict(r) for r in db.execute('SELECT * FROM probe_items ORDER BY mission')]

    def plan(self):
        return {r['mission']:StoredReceipt(**json.loads(r['item'])) for r in self.rows()}

    def contents(self):
        return {m:(self.directory/(m+'.png')).read_bytes() for m in ('argentina','portugal')}

    def validate(self):
        assert_temporary_database(self.database_path)
        for path in self.directory.iterdir(): reject_links(path)
        with connect(self.database_path) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise DriveError('backup')
            rows = db.execute('SELECT * FROM probe_run').fetchall()
            if len(rows) != 1 or rows[0]['mapping_sha256'] != mapping_digest(self.configuration): raise DriveError('destino')
            run_id = rows[0]['run_id']
            marker = json.loads((self.directory/'.volume.json').read_text(encoding='utf-8'))
            if marker != {'id':rows[0]['volume_id'],'run_id':run_id} or not re.fullmatch('[a-f0-9]{16}',run_id):
                raise DriveError('backup')
        items = self.plan()
        if set(items) != {'argentina','portugal'}: raise DriveError('backup')
        for mission, item in items.items():
            content = (self.directory/(mission+'.png')).read_bytes()
            key = hashlib.sha256((run_id+':'+mission).encode()).hexdigest()
            if (content != probe_png(mission) or hashlib.sha256(content).hexdigest() != item.checksum
                    or item.size_bytes != len(content) or item.mission_code != mission
                    or item.official_name != f'secco-ensaio-{run_id}-{mission}.png' or item.object_key != key
                    or item.category != 'deslocamentos' or item.mime != 'image/png' or item.extension != 'png'):
                raise DriveError('backup')
            row = next(r for r in self.rows() if r['mission']==mission)
            if row['sync_key'] != key or (row['remote_id'] is not None and not re.fullmatch('[A-Za-z0-9_-]{3,200}',row['remote_id'])):
                raise DriveError('backup')

    def checkpoint(self, archive):
        """SQLite Backup API + volume no mesmo lock lógico: uso single-process do ensaio."""
        self.validate()
        archive = Path(archive).absolute()
        reject_links(archive)
        if archive.is_relative_to(self.directory): raise DriveError('backup')
        archive.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        snapshot = self.directory/'snapshot.sqlite3'
        if snapshot.exists(): snapshot.unlink()
        with connect(self.database_path) as source, connect(snapshot) as target:
            source.backup(target)
        files = {'probe.sqlite3':snapshot.read_bytes()}
        for name in ('.volume.json','argentina.png','portugal.png'):
            files[name] = (self.directory/name).read_bytes()
        manifest = {name:{'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)}
                    for name,content in files.items()}
        # O arquivo anterior só é substituído depois de uma cópia completa sincronizada.
        temporary = archive.with_name(archive.name+'.'+secrets.token_hex(8)+'.part')
        try:
            descriptor=os.open(temporary,os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(descriptor,'w+b') as stream:
                with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as output:
                    for name,content in files.items(): output.writestr(name,content)
                    output.writestr('manifest.json',json.dumps(manifest,sort_keys=True))
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary,archive)
            if os.name!='nt':
                descriptor=os.open(archive.parent,os.O_RDONLY|os.O_DIRECTORY)
                try: os.fsync(descriptor)
                finally: os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)
            snapshot.unlink(missing_ok=True)

    @classmethod
    def restore(cls, archive, directory, configuration):
        reject_links(Path(archive).absolute())
        try:
            with zipfile.ZipFile(archive) as source:
                expected={'probe.sqlite3','.volume.json','argentina.png','portugal.png','manifest.json'}
                if set(source.namelist()) != expected or len(source.infolist()) != 5: raise ValueError()
                if any(i.file_size > 1024*1024 or i.is_dir() for i in source.infolist()): raise ValueError()
                files={name:source.read(name) for name in expected}
            manifest=json.loads(files.pop('manifest.json'))
            if manifest != {name:{'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)}
                            for name,content in files.items()}: raise ValueError()
        except (OSError,ValueError,KeyError,zipfile.BadZipFile):
            raise DriveError('backup') from None
        self=cls(directory,configuration)
        for name,content in files.items(): self._write(self.directory/name,content)
        self.validate()
        return self

    def _state(self, mission, state, error=None):
        with connect(self.database_path) as db:
            db.execute('UPDATE probe_items SET state=?,error_code=?,ever_verified=MAX(ever_verified,?) WHERE mission=?',
                       (state,error,int(state=='verificado'),mission))
            db.execute('INSERT INTO probe_events(mission,state,error_code) VALUES(?,?,?)',(mission,state,error))

    def preflight(self, adapter):
        self.validate()
        # Todos os 14 destinos e ACLs antes de qualquer criação. Só dois serão usados.
        for mission,item in self.plan().items():
            for category in self.configuration.folders()[mission]:
                from dataclasses import replace
                adapter.preflight_destination(replace(item,category=category),require_write=True)

    def run(self, adapter, archive):
        self.validate()
        self.preflight(adapter)
        for row in self.rows():
            mission=row['mission']
            item=self.plan()[mission]
            try:
                if row['remote_id'] is None:
                    identifier=adapter.reserve_id()
                    with connect(self.database_path) as db:
                        db.execute('UPDATE probe_items SET remote_id=? WHERE mission=?',(identifier,mission))
                    row['remote_id']=identifier
                # ID e conteúdo recuperáveis ANTES do POST; falha de backup impede envio.
                adapter.probe_transport.bind(mission,row['remote_id'],row['sync_key'])
                self._state(mission,'enviando')
                with connect(self.database_path) as db:
                    db.execute('UPDATE probe_items SET attempts=attempts+1 WHERE mission=?',(mission,))
                self.checkpoint(archive)
                args={'remote_id':row['remote_id'],'idempotency_key':row['sync_key']}
                if row['ever_verified']:
                    confirmed=adapter.verify(item,**args)
                    if confirmed is None: raise DriveError('integridade')
                else:
                    confirmed=adapter.upload(item,BytesIO(self.contents()[mission]),**args)
                if confirmed.remote_id != row['remote_id'] or confirmed.checksum != item.checksum:
                    raise DriveError('integridade')
                self._state(mission,'verificado')
                self.checkpoint(archive)
            except DriveError as error:
                self._state(mission,'erro',error.code)
                self.checkpoint(archive)
                return False  # Sem retry automático, troca de ID ou avanço após falha.
        return True
