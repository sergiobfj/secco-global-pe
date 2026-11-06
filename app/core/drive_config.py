"""Roteamento explícito. Configurar pastas não cria recursos no Google."""
from dataclasses import dataclass
import json
import re

CATEGORIES = {
    'passagens': 'Passagens', 'diarias': 'Diárias', 'inscricoes': 'Inscrições',
    'deslocamentos': 'Deslocamentos', 'contrapartida': 'Contrapartida',
    'eventos': 'Comprovantes de Eventos', 'atividades': 'Atividades',
}
# Nomes exatos informados pelo responsável após leitura supervisionada (07B).
# A chave da categoria é estável; o nome físico pode variar entre missões.
FOLDER_NAMES = {
    'argentina': {**CATEGORIES, 'deslocamentos': 'Deslocamento'},
    'portugal': dict(CATEGORIES),
}
TYPE_CATEGORY = {
    'passagem_aerea': 'passagens', 'diaria': 'diarias', 'inscricao_evento': 'inscricoes',
    'aplicativo': 'deslocamentos', 'taxi': 'deslocamentos',
    'intermunicipal': 'deslocamentos', 'urbano': 'deslocamentos',
}
DRIVE_NAMES = {'argentina': 'Global PE - Argentina', 'portugal': 'Global PE - Portugal'}
# IDs confirmados para cada missão; nome de exibição não é prova de identidade.
DRIVE_IDS = {'argentina': '0AARGENTINAEXEMPLO1', 'portugal': '0APORTUGALEXEMPLO01'}
SERVICE_ACCOUNT = 'global-pe-drive@exemplo-global-pe.iam.gserviceaccount.com'
READERS = {
    'argentina': frozenset((SERVICE_ACCOUNT, 'tiago@secco.example', 'bruno@secco.example')),
    'portugal': frozenset((SERVICE_ACCOUNT, 'hugo@secco.example', 'alan@secco.example')),
}


def valid_id(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{3,200}', value) is not None


@dataclass(frozen=True)
class DriveConfiguration:
    argentina: str = DRIVE_IDS['argentina']
    portugal: str = DRIVE_IDS['portugal']
    # JSON de {codigo_missao: {categoria: id_pasta}}. Vazio até aprovação.
    folders_json: str = '{}'

    def folders(self):
        try:
            folders = json.loads(self.folders_json)
            if not isinstance(folders, dict): raise ValueError()
            ids = []
            for mission, mapping in folders.items():
                if mission not in DRIVE_NAMES or not isinstance(mapping, dict): raise ValueError()
                for category, folder in mapping.items():
                    if category not in CATEGORIES or not valid_id(folder): raise ValueError()
                    ids.append(folder)
            if len(ids) != len(set(ids)) or any(i in (self.argentina, self.portugal) for i in ids): raise ValueError()
            return folders
        except (TypeError, ValueError):
            raise ValueError('Mapeamento de pastas do Drive inválido.') from None

    def validate(self):
        if not valid_id(self.argentina) or not valid_id(self.portugal) or self.argentina == self.portugal:
            raise ValueError('Configure dois Drives distintos e válidos.')
        self.folders()

    def destination(self, mission, category):
        self.validate()
        if mission not in DRIVE_NAMES or category not in CATEGORIES:
            raise ValueError('Missão ou categoria do Drive inválida.')
        folder = self.folders().get(mission, {}).get(category)
        if not folder: raise ValueError('Pasta da categoria ainda não configurada.')
        return getattr(self, mission), folder
