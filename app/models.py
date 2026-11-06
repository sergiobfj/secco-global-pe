"""Modelos de leitura tipados. Persistência e regras de negócio ficam separadas."""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Participant:
    id: int
    nome: str
    email: str | None
    papel: str
    financiado_pela_subvencao: bool


@dataclass(frozen=True)
class Goal:
    tipo_meta: str
    quantidade_alvo: int
    realizado: int

    @property
    def percentual(self):
        return min(100, round(self.realizado / self.quantidade_alvo * 100))

    @property
    def rotulo(self):
        return {"reuniao_qualificada": "Reuniões qualificadas",
                "loi": "LOIs", "manifestacao_interesse": "Manifestações formais de interesse"}[self.tipo_meta]


@dataclass(frozen=True)
class Mission:
    id: int
    codigo: str
    nome: str
    pais: str
    data_inicio: date
    data_fim: date
    timezone: str
    edital: str
    status: str
    cidades: list[str]
    atividades_previstas: list[str]
    observacoes: str | None
    participantes: list[Participant]
    metas: list[Goal]

    @property
    def periodo(self):
        return f"{self.data_inicio:%d} a {self.data_fim:%d/%m/%Y}"

    @property
    def nomes_participantes(self):
        return " e ".join(p.nome for p in self.participantes)
