"""Contratos de armazenamento e da integração futura. Nenhuma chamada ao Drive."""
from dataclasses import dataclass
from typing import BinaryIO, Protocol


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
    # Somente contrato futuro. Um resultado remoto exigirá resposta real da API.
    def upload(self,item: StoredReceipt,stream: BinaryIO,*,idempotency_key: str)->ConfirmedRemoteReceipt: ...
