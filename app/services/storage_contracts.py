"""Contratos independentes de transporte e credenciais."""
from dataclasses import dataclass
from typing import BinaryIO, Protocol
from app.core.drive_config import DriveConfiguration


class DriveError(Exception):
    """Falha de integração com código controlado, sem mensagens de provedores."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class StoredReceipt:
    attachment_id: str
    mission_id: int
    expense_id: int
    object_key: str
    checksum: str
    size_bytes: int
    extension: str
    mime: str
    mission_code: str = ''
    official_name: str = ''
    category: str = ''


class ReceiptStorage(Protocol):
    persistent: bool
    def available(self,attachment: dict)->bool: ...
    def read_attachment(self,attachment: dict)->bytes: ...
    def close(self)->None: ...


@dataclass(frozen=True)
class ConfirmedRemoteReceipt:
    remote_id: str
    checksum: str


class SharedDriveAdapter(Protocol):
    configuration: DriveConfiguration
    def reserve_id(self)->str: ...
    def upload(self,item: StoredReceipt,stream: BinaryIO,*,idempotency_key: str,remote_id: str)->ConfirmedRemoteReceipt: ...
    def verify(self,item: StoredReceipt,*,idempotency_key: str,remote_id: str)->ConfirmedRemoteReceipt | None: ...
