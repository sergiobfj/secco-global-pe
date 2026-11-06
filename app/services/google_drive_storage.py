"""Drive API v3. Aplicação continua restrita a transporte simulado."""
import hashlib
import json
import re
import secrets
import time

import httpx

from app.core.drive_config import FOLDER_NAMES, DRIVE_IDS, READERS, SERVICE_ACCOUNT, valid_id
from app.core.test_database import testing_enabled
from app.services.drive_credentials import DriveAccessToken
from app.services.receipt_storage import MAX_FILE, validate_file
from app.services.itinerary import InvalidActivity
from app.services.storage_contracts import ConfirmedRemoteReceipt, DriveError

API = 'https://www.googleapis.com/drive/v3'
UPLOAD = 'https://www.googleapis.com/upload/drive/v3/files'
FILE_FIELDS = 'id,driveId,parents,name,mimeType,size,sha256Checksum,trashed,appProperties'
FOLDER_FIELDS = 'id,name,mimeType,parents,driveId,trashed,capabilities(canAddChildren)'


class GoogleDriveAdapter:
    def __init__(self, configuration, credentials, *, transport):
        # Não existe fallback para rede, ADC, .env ou credenciais de usuário.
        if not testing_enabled() or type(transport) is not httpx.MockTransport:
            raise RuntimeError('Etapa 07A permite somente MockTransport em testes isolados.')
        configuration.validate()
        self.configuration = configuration
        self.credentials = credentials
        self.client = httpx.Client(transport=transport, timeout=30, follow_redirects=False, trust_env=False)

    def close(self):
        self.client.close()

    def _request(self, method, url, *, allow_missing=False, allow_conflict=False, **kwargs):
        try:
            token = self.credentials.access_token()
            if (not isinstance(token, DriveAccessToken) or not isinstance(token.value, str)
                    or not re.fullmatch(r'[A-Za-z0-9._~+/-]{8,8192}=*', token.value)
                    or not token.expires_at > time.time() + 30):
                raise ValueError()
        except Exception:
            raise DriveError('credenciais') from None
        try:
            response = self.client.request(method, url, headers={
                **kwargs.pop('headers', {}), 'Authorization': 'Bearer ' + token.value}, **kwargs)
        except httpx.RequestError:
            raise DriveError('conexao') from None
        if response.status_code == 404 and allow_missing: return None
        if response.status_code == 409 and allow_conflict: return {}
        if response.status_code == 401: raise DriveError('credenciais')
        if response.status_code == 403: raise DriveError('permissao')
        if response.status_code == 429 or response.status_code >= 500: raise DriveError('conexao')
        if not 200 <= response.status_code < 300: raise DriveError('remoto')
        try:
            data = response.json()
            if not isinstance(data, dict): raise ValueError()
            return data
        except (ValueError, TypeError):
            raise DriveError('resposta_invalida') from None

    def reserve_id(self):
        data = self._request('GET', API + '/files/generateIds', params={'count': 1, 'space': 'drive', 'type': 'files'})
        ids = data.get('ids')
        if not isinstance(ids, list) or len(ids) != 1 or not valid_id(ids[0]):
            raise DriveError('resposta_invalida')
        return ids[0]

    def _acl(self, file_id, mission):
        token = None
        seen = set()
        principals = set()
        for _ in range(100):
            params = {'supportsAllDrives': 'true', 'pageSize': 100,
                      'fields': 'nextPageToken,permissions(type,emailAddress,role,deleted)'}
            if token: params['pageToken'] = token
            data = self._request('GET', API + f'/files/{file_id}/permissions', params=params)
            permissions = data.get('permissions')
            if not isinstance(permissions, list) or not permissions: raise DriveError('permissao')
            for permission in permissions:
                if (not isinstance(permission, dict) or permission.get('type') != 'user'
                        or not isinstance(permission.get('emailAddress'), str)
                        or permission.get('emailAddress') not in READERS[mission]
                        or permission.get('deleted', False) is not False
                        or permission.get('role') not in ('organizer', 'fileOrganizer', 'writer', 'commenter', 'reader', 'owner')):
                    raise DriveError('permissao')
                principals.add(permission['emailAddress'])
            token = data.get('nextPageToken')
            if token is None:
                if SERVICE_ACCOUNT not in principals: raise DriveError('permissao')
                return
            if not isinstance(token, str) or not token or token in seen: raise DriveError('resposta_invalida')
            seen.add(token)
        raise DriveError('resposta_invalida')

    def _destination(self, item, *, require_write=False):
        try: drive, folder = self.configuration.destination(item.mission_code, item.category)
        except ValueError: raise DriveError('destino') from None
        # Não usa drives.get: vincula a missão ao ID confirmado e confere pasta/raiz via files.get.
        if drive != DRIVE_IDS[item.mission_code]: raise DriveError('destino')
        data = self._request('GET', API + f'/files/{folder}', params={
            'supportsAllDrives': 'true', 'fields': FOLDER_FIELDS})
        if (data.get('id') != folder or data.get('driveId') != drive or data.get('parents') != [drive]
                or data.get('name') != FOLDER_NAMES[item.mission_code][item.category] or data.get('trashed') is not False
                or data.get('mimeType') != 'application/vnd.google-apps.folder'):
            raise DriveError('destino')
        if require_write:
            capabilities = data.get('capabilities')
            if not isinstance(capabilities, dict) or capabilities.get('canAddChildren') is not True:
                raise DriveError('permissao')
        self._acl(drive, item.mission_code)
        self._acl(folder, item.mission_code)
        return drive, folder

    def _identity(self, item, idempotency_key, remote_id):
        if (not valid_id(remote_id) or not isinstance(idempotency_key, str)
                or not re.fullmatch(r'[a-f0-9]{64}', idempotency_key)
                or not isinstance(item.checksum, str) or not re.fullmatch(r'[a-f0-9]{64}', item.checksum)
                or type(item.size_bytes) is not int or not 0 < item.size_bytes <= MAX_FILE
                or not isinstance(item.official_name, str) or not item.official_name or len(item.official_name) > 1000
                or any(c in item.official_name for c in ('/', '\\'))
                or any(ord(c) < 32 for c in item.official_name)
                or not item.official_name.endswith('.' + item.extension)):
            raise DriveError('destino')

    def preflight_destination(self, item, *, require_write=False):
        return self._destination(item, require_write=require_write)

    def verify(self, item, *, idempotency_key, remote_id):
        self._identity(item, idempotency_key, remote_id)
        drive, folder = self._destination(item)
        data = self._request('GET', API + f'/files/{remote_id}', allow_missing=True,
                             params={'supportsAllDrives': 'true', 'fields': FILE_FIELDS})
        if data is None: return None
        if (data.get('id') != remote_id or data.get('driveId') != drive or data.get('parents') != [folder]
                or data.get('name') != item.official_name or data.get('mimeType') != item.mime
                or data.get('trashed') is not False or data.get('appProperties') != {
                    'secco_sync': idempotency_key, 'secco_mission': item.mission_code}
                or data.get('size') != str(item.size_bytes) or data.get('sha256Checksum') != item.checksum):
            raise DriveError('integridade')
        self._acl(remote_id, item.mission_code)
        return ConfirmedRemoteReceipt(remote_id, data['sha256Checksum'])

    def upload(self, item, stream, *, idempotency_key, remote_id):
        self._identity(item, idempotency_key, remote_id)
        content = stream.read(MAX_FILE + 1)
        if len(content) != item.size_bytes or hashlib.sha256(content).hexdigest() != item.checksum:
            raise DriveError('local')
        try: validate_file({'name': 'receipt.' + item.extension, 'mime': item.mime, 'content': content})
        except InvalidActivity: raise DriveError('local') from None
        # GET antes de reenviar, mesmo após timeout. ID reservado permanece no journal.
        confirmed = self.verify(item, idempotency_key=idempotency_key, remote_id=remote_id)
        if confirmed: return confirmed
        _, folder = self.preflight_destination(item, require_write=True)
        boundary = 'secco_' + secrets.token_hex(24)
        metadata = {'id': remote_id, 'name': item.official_name, 'parents': [folder],
                    'mimeType': item.mime, 'appProperties': {
                        'secco_sync': idempotency_key, 'secco_mission': item.mission_code}}
        body = (f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'.encode()
                + json.dumps(metadata).encode() + f'\r\n--{boundary}\r\nContent-Type: {item.mime}\r\n\r\n'.encode()
                + content + f'\r\n--{boundary}--\r\n'.encode())
        self._request('POST', UPLOAD, allow_conflict=True, content=body,
                      headers={'Content-Type': f'multipart/related; boundary={boundary}'},
                      params={'uploadType': 'multipart', 'supportsAllDrives': 'true', 'fields': 'id'})
        confirmed = self.verify(item, idempotency_key=idempotency_key, remote_id=remote_id)
        if confirmed is None: raise DriveError('resposta_invalida')
        return confirmed
