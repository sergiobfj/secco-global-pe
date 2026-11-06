"""Fronteira de credenciais: nenhum ADC, chave ou token de login é descoberto."""
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class DriveAccessToken:
    value: str = field(repr=False)
    expires_at: float


class DriveCredentials(Protocol):
    def access_token(self) -> DriveAccessToken:
        """Obter/renovar token curto com escopo Drive; implementação exige aprovação."""
        ...


class UnconfiguredDriveCredentials:
    def access_token(self):
        raise RuntimeError('Método de autenticação do Drive não aprovado/configurado.')
