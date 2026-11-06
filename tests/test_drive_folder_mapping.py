"""07B: destinos informados pelo responsável, verificados apenas com metadados simulados.

Nenhuma chamada real, upload, abertura SQLite ou migração é necessária nestes casos.
"""
from dataclasses import replace
import json
import re
import time

from dotenv import dotenv_values
import httpx
import pytest

from app.core.config import ROOT, Settings
from app.core.drive_config import CATEGORIES, DriveConfiguration, READERS
from app.services.drive_credentials import DriveAccessToken
from app.services.google_drive_storage import GoogleDriveAdapter
from app.services.storage_contracts import DriveError, StoredReceipt


# Oráculo independente de FOLDER_NAMES e do exemplo: transcrição da tabela do responsável.
FOLDERS = [
    ('argentina', 'passagens', 'Passagens', '1EXEMPLO_AR_passagens_00000000000'),
    ('argentina', 'diarias', 'Diárias', '1EXEMPLO_AR_diarias_0000000000000'),
    ('argentina', 'inscricoes', 'Inscrições', '1EXEMPLO_AR_inscricoes_0000000000'),
    ('argentina', 'deslocamentos', 'Deslocamento', '1EXEMPLO_AR_deslocamentos_0000000'),
    ('argentina', 'contrapartida', 'Contrapartida', '1EXEMPLO_AR_contrapartida_0000000'),
    ('argentina', 'eventos', 'Comprovantes de Eventos', '1EXEMPLO_AR_eventos_0000000000000'),
    ('argentina', 'atividades', 'Atividades', '1EXEMPLO_AR_atividades_0000000000'),
    ('portugal', 'passagens', 'Passagens', '1EXEMPLO_PT_passagens_00000000000'),
    ('portugal', 'diarias', 'Diárias', '1EXEMPLO_PT_diarias_0000000000000'),
    ('portugal', 'inscricoes', 'Inscrições', '1EXEMPLO_PT_inscricoes_0000000000'),
    ('portugal', 'deslocamentos', 'Deslocamentos', '1EXEMPLO_PT_deslocamentos_0000000'),
    ('portugal', 'contrapartida', 'Contrapartida', '1EXEMPLO_PT_contrapartida_0000000'),
    ('portugal', 'eventos', 'Comprovantes de Eventos', '1EXEMPLO_PT_eventos_0000000000000'),
    ('portugal', 'atividades', 'Atividades', '1EXEMPLO_PT_atividades_0000000000'),
]
DRIVES = {'argentina': '0AARGENTINAEXEMPLO1', 'portugal': '0APORTUGALEXEMPLO01'}
NAMES = {'argentina': 'Global PE - Argentina', 'portugal': 'Global PE - Portugal'}
CASES = pytest.mark.parametrize('mission,category,name,folder_id', FOLDERS,
                                ids=[m+'-'+c for m,c,_,_ in FOLDERS])


def example():
    # Leitura do exemplo explicitamente; nunca .env, Settings.from_env ou startup.
    return dotenv_values(ROOT/'.env.example', interpolate=False)


def configuration():
    values = example()
    return DriveConfiguration(values['GOOGLE_DRIVE_ARGENTINA_ID'],
                              values['GOOGLE_DRIVE_PORTUGAL_ID'], values['GOOGLE_DRIVE_FOLDERS_JSON'])


class SyntheticCredentials:
    def access_token(self):
        return DriveAccessToken('SYNTHETIC-METADATA-ONLY', time.time()+300)


class MetadataAPI:
    def __init__(self):
        self.calls = []
        self.missing = set()
        self.changes = {}
        self.folders = {folder_id: {'id': folder_id, 'name': name, 'driveId': DRIVES[mission],
            'parents': [DRIVES[mission]], 'mimeType': 'application/vnd.google-apps.folder', 'trashed': False}
            for mission, category, name, folder_id in FOLDERS}

    def __call__(self, request):
        assert request.method == 'GET'
        assert request.url.host == 'www.googleapis.com'
        assert request.headers['Authorization'] == 'Bearer SYNTHETIC-METADATA-ONLY'
        path = request.url.path
        self.calls.append((path, dict(request.url.params)))
        if path.startswith('/drive/v3/drives/'):
            identifier = path.rsplit('/', 1)[1]
            mission = next(m for m in DRIVES if DRIVES[m] == identifier)
            return httpx.Response(200, json={'id': identifier, 'name': NAMES[mission]})
        assert path.startswith('/drive/v3/files/') and not path.endswith('/generateIds')
        assert request.url.params['supportsAllDrives'] == 'true'
        if path.endswith('/permissions'):
            identifier = path.split('/')[-2]
            drive = self.folders[identifier]['driveId'] if identifier in self.folders else identifier
            mission = next(m for m in DRIVES if DRIVES[m] == drive)
            return httpx.Response(200, json={'permissions': [
                {'type': 'user', 'emailAddress': email, 'role': 'writer'} for email in sorted(READERS[mission])]})
        identifier = path.rsplit('/', 1)[1]
        if identifier in self.missing or identifier not in self.folders:
            return httpx.Response(404, json={})
        return httpx.Response(200, json={**self.folders[identifier], **self.changes})


def verify_destination(config, api, mission, category):
    item = StoredReceipt('a'*32, 2 if mission == 'argentina' else 1, 1, 'b'*64,
        'c'*64, 1, 'png', 'image/png', mission, 'comprovante-sintetico.png', category)
    adapter = GoogleDriveAdapter(config, SyntheticCredentials(), transport=httpx.MockTransport(api))
    try:
        # Arquivo sintético remoto inexistente: valida o destino e retorna None, sem enviar.
        return adapter.verify(item, idempotency_key='d'*64, remote_id='synthetic_missing_receipt')
    finally:
        adapter.close()


@CASES
def test_all_fourteen_configured_ids_and_exact_names(mission, category, name, folder_id):
    config = configuration()
    assert config.destination(mission, category) == (DRIVES[mission], folder_id)
    api = MetadataAPI()
    assert verify_destination(config, api, mission, category) is None
    assert api.folders[folder_id]['name'] == name
    assert any(path == '/drive/v3/files/'+folder_id for path, _ in api.calls)


@CASES
def test_divergent_name_is_rejected_for_each_destination(mission, category, name, folder_id):
    for wrong in ('01-'+name, name.lower(), name+' '):
        api = MetadataAPI()
        api.changes = {'name': wrong}
        with pytest.raises(DriveError, match='destino'):
            verify_destination(configuration(), api, mission, category)


@pytest.mark.parametrize('mission,wrong_name', [('argentina', 'Deslocamentos'), ('portugal', 'Deslocamento')])
def test_singular_plural_exception_cannot_leak_between_missions(mission, wrong_name):
    api = MetadataAPI()
    api.changes = {'name': wrong_name}
    with pytest.raises(DriveError, match='destino'):
        verify_destination(configuration(), api, mission, 'deslocamentos')


@CASES
def test_other_mission_folder_id_is_rejected(mission, category, name, folder_id):
    config = configuration()
    mapping = config.folders()
    other = 'portugal' if mission == 'argentina' else 'argentina'
    other_id = mapping[other][category]
    # Troca (em vez de duplicar) IDs para exercitar a verificação remota de missão.
    mapping[mission][category], mapping[other][category] = other_id, folder_id
    api = MetadataAPI()
    with pytest.raises(DriveError, match='destino'):
        verify_destination(replace(config, folders_json=json.dumps(mapping)), api, mission, category)
    assert api.calls[-1][0] == '/drive/v3/files/'+other_id


@CASES
def test_other_category_folder_id_is_rejected(mission, category, name, folder_id):
    config = configuration()
    mapping = config.folders()
    other_category = next(c for c in mapping[mission] if c != category)
    mapping[mission][category], mapping[mission][other_category] = mapping[mission][other_category], folder_id
    with pytest.raises(DriveError, match='destino'):
        verify_destination(replace(config, folders_json=json.dumps(mapping)), MetadataAPI(), mission, category)


@CASES
def test_missing_mapping_fails_before_api(mission, category, name, folder_id):
    config = configuration()
    mapping = config.folders()
    del mapping[mission][category]
    api = MetadataAPI()
    with pytest.raises(DriveError, match='destino'):
        verify_destination(replace(config, folders_json=json.dumps(mapping)), api, mission, category)
    assert api.calls == []


@CASES
def test_missing_remote_folder_is_rejected(mission, category, name, folder_id):
    api = MetadataAPI()
    api.missing.add(folder_id)
    with pytest.raises(DriveError, match='remoto'):
        verify_destination(configuration(), api, mission, category)
    assert api.calls[-1][0] == '/drive/v3/files/'+folder_id


@CASES
def test_response_must_match_requested_folder_id(mission, category, name, folder_id):
    api = MetadataAPI()
    api.changes = {'id': 'synthetic_other_folder'}
    with pytest.raises(DriveError, match='destino'):
        verify_destination(configuration(), api, mission, category)


@pytest.mark.parametrize('changes', [
    {'parents': []}, {'parents': ['synthetic_nested_parent']},
    {'parents': [DRIVES['argentina'], 'synthetic_extra_parent']},
    {'driveId': DRIVES['portugal']}, {'trashed': True},
    {'mimeType': 'application/vnd.google-apps.shortcut'},
])
def test_root_drive_folder_type_and_trash_checks_remain_strict(changes):
    api = MetadataAPI()
    api.changes = changes
    with pytest.raises(DriveError, match='destino'):
        verify_destination(configuration(), api, 'argentina', 'passagens')


@pytest.mark.parametrize('bad_id', ['invalid/id', '', None, DRIVES['argentina']])
def test_invalid_configured_ids_are_rejected_without_network(bad_id):
    config = configuration()
    mapping = config.folders()
    mapping['argentina']['passagens'] = bad_id
    with pytest.raises(ValueError): replace(config, folders_json=json.dumps(mapping)).validate()


def test_duplicate_folder_id_in_different_missions_is_rejected():
    config = configuration()
    mapping = config.folders()
    mapping['portugal']['passagens'] = mapping['argentina']['passagens']
    with pytest.raises(ValueError): replace(config, folders_json=json.dumps(mapping)).validate()


def test_example_is_complete_disabled_and_does_not_change_runtime_default(tmp_path):
    values = example()
    config = configuration()
    mapping = config.folders()
    assert set(mapping) == {'argentina', 'portugal'}
    assert all(set(categories) == set(CATEGORIES) for categories in mapping.values())
    assert sum(map(len, mapping.values())) == 14
    assert values['RECEIPTS_DRIVE_MODE'] == 'disabled'
    assert DriveConfiguration().folders() == {}
    settings = Settings('development', False, tmp_path/'not-opened.sqlite3',
                        google_drive_folders_json=values['GOOGLE_DRIVE_FOLDERS_JSON'])
    settings.validate()
    assert settings.receipts_drive_mode == 'disabled'
    assert not settings.database_path.exists()
    with pytest.raises(RuntimeError, match='real'):
        replace(settings, receipts_drive_mode='real').validate()
    with pytest.raises(RuntimeError, match='MockTransport'):
        GoogleDriveAdapter(config, SyntheticCredentials(), transport=None)


def test_documented_json_matches_example_and_all_supplied_ids():
    guide = (ROOT/'docs/integracao-google-drive.md').read_text(encoding='utf-8')
    blocks = re.findall(r'```json\n(.*?)\n```', guide, re.DOTALL)
    assert len(blocks) == 1
    mapping = json.loads(blocks[0])
    assert mapping == configuration().folders()
    assert {(m,c,identifier) for m,categories in mapping.items() for c,identifier in categories.items()} == {
        (mission, category, folder_id) for mission, category, _, folder_id in FOLDERS}
