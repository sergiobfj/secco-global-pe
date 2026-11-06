"""Transporte de ensaio separado da aplicação. Nenhuma conexão na importação.

A aprovação é uma declaração do responsável, não um substituto para autorização
humana nem uma sandbox contra código deliberadamente hostil.
"""
from dataclasses import asdict, dataclass
from datetime import datetime
from email import policy
from email.parser import BytesParser
import hashlib
import json
import logging
import os
import re
import subprocess
import struct
import time
import zlib

import httpx

from app.core.drive_config import CATEGORIES, DriveConfiguration, SERVICE_ACCOUNT, valid_id
from app.services.drive_credentials import DriveAccessToken
from app.services.google_drive_storage import UPLOAD, GoogleDriveAdapter
from app.services.storage_contracts import DriveError

SCOPE_FILE = 'https://www.googleapis.com/auth/drive.file'
SCOPE_METADATA = 'https://www.googleapis.com/auth/drive.metadata.readonly'
IAM_URL = f'https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{SERVICE_ACCOUNT}:generateAccessToken'


def mapping_digest(configuration):
    return hashlib.sha256(json.dumps({'argentina': configuration.argentina,
        'portugal': configuration.portugal, 'folders': configuration.folders()},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def plan_digest(items):
    return hashlib.sha256(json.dumps({m:asdict(i) for m,i in items.items()},
        sort_keys=True,separators=(',',':')).encode()).hexdigest()


@dataclass(frozen=True)
class ProbeApproval:
    reference: str
    operator_account: str
    expires_at: float
    mapping_sha256: str
    scopes: tuple
    approved: bool = False
    synthetic_only: bool = False
    backup_verified: bool = False
    cleanup: str = 'retain'
    plan_sha256: str = ''

    def validate(self, configuration):
        configuration.validate()
        folders = configuration.folders()
        expected = DriveConfiguration()
        if (self.approved is not True or self.synthetic_only is not True or self.backup_verified is not True
                or not isinstance(self.reference, str) or not self.reference.strip()
                or not re.fullmatch(r'[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+', self.operator_account)
                or self.operator_account.endswith('.gserviceaccount.com')
                or not time.time()+30 < self.expires_at <= time.time()+3600
                or self.mapping_sha256 != mapping_digest(configuration)
                or self.scopes != (SCOPE_FILE, SCOPE_METADATA)
                or self.cleanup != 'retain' or configuration.argentina != expected.argentina
                or not re.fullmatch('[a-f0-9]{64}',self.plan_sha256)
                or configuration.portugal != expected.portugal or set(folders) != {'argentina','portugal'}
                or any(set(categories) != set(CATEGORIES) for categories in folders.values())):
            raise DriveError('autorizacao')


def probe_png(mission):
    color = {'argentina': b'\x60\xa0\xff', 'portugal': b'\x30\xc0\x60'}[mission]
    def chunk(kind, value):
        return struct.pack('>I',len(value))+kind+value+struct.pack('>I',zlib.crc32(kind+value)&0xffffffff)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))
            +chunk(b'IDAT',zlib.compress(b'\x00'+color))+chunk(b'IEND',b''))


class _NoGoogleHTTPLog(logging.Filter):
    def filter(self, record):
        # HTTPX registra URLs com IDs/pageTokens em INFO; não registrar essas chamadas.
        message = record.getMessage()
        return not any(host in message for host in ('www.googleapis.com', 'iamcredentials.googleapis.com'))


def protect_http_logs():
    logger = logging.getLogger('httpx')
    if not any(isinstance(f, _NoGoogleHTTPLog) for f in logger.filters):
        logger.addFilter(_NoGoogleHTTPLog())


class GcloudSourceCredentials:
    """Usa somente conta do operador já autenticada. Nunca executa login ou IAM set."""
    def __init__(self, operator_account):
        if (not re.fullmatch(r'[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+', operator_account)
                or operator_account.endswith('.gserviceaccount.com')):
            raise DriveError('credenciais')
        self.operator_account = operator_account

    def source_token(self):
        environment = {**os.environ, 'CLOUDSDK_CORE_DISABLE_FILE_LOGGING': 'true',
            'CLOUDSDK_CORE_LOG_HTTP': 'false', 'CLOUDSDK_CORE_DISABLE_PROMPTS': 'true',
            'CLOUDSDK_CORE_DISABLE_USAGE_REPORTING': 'true'}
        for key in ('CLOUDSDK_AUTH_ACCESS_TOKEN','CLOUDSDK_AUTH_ACCESS_TOKEN_FILE',
                    'CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE','CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT',
                    'CLOUDSDK_CORE_TRACE_TOKEN','GOOGLE_APPLICATION_CREDENTIALS'):
            environment.pop(key,None)
        # NONE não herda impersonação/trace/debug de uma configuração ativa.
        command = ['gcloud', '--configuration=NONE', '--project=exemplo-global-pe',
            '--quiet', '--verbosity=none', 'auth', 'print-access-token', '--account='+self.operator_account]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=45,
                                       env=environment, check=False)
            value = completed.stdout.strip()
            if completed.returncode or not re.fullmatch(r'[A-Za-z0-9._~+/-]{8,8192}=*', value):
                raise ValueError()
            return value
        except (OSError, subprocess.SubprocessError, ValueError):
            raise DriveError('credenciais_fonte') from None


class ImpersonatedProbeCredentials:
    """IAM Credentials oficial: token alvo de 900s, em memória, escopos aprovados."""
    def __init__(self, source, approval, configuration, *, transport=None):
        approval.validate(configuration)
        protect_http_logs()
        self.source, self.approval, self.configuration = source, approval, configuration
        self.cached = None
        self.client = httpx.Client(transport=transport, timeout=30, follow_redirects=False, trust_env=False)

    def access_token(self):
        self.approval.validate(self.configuration)
        if self.cached and self.cached.expires_at > time.time()+60: return self.cached
        try:
            source = self.source.source_token()
            if not re.fullmatch(r'[A-Za-z0-9._~+/-]{8,8192}=*', source): raise ValueError()
            response = self.client.post(IAM_URL, headers={'Authorization': 'Bearer '+source},
                json={'scope': list(self.approval.scopes), 'lifetime': '900s'})
            if response.status_code == 403:
                # SERVICE_DISABLED é distinguido sem conservar corpo ou mensagem externos.
                data = response.json()
                details = data.get('error', {}).get('details', [])
                disabled = any(isinstance(d, dict) and d.get('reason') == 'SERVICE_DISABLED' for d in details)
                raise DriveError('iam_api_desativada' if disabled else 'iam_get_access_token')
            if response.status_code != 200: raise DriveError('credenciais')
            data = response.json()
            expires = datetime.fromisoformat(data['expireTime'].replace('Z', '+00:00')).timestamp()
            value = data['accessToken']
            if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._~+/-]{8,8192}=*', value)
                    or not time.time()+30 < expires <= time.time()+1000): raise ValueError()
            self.cached = DriveAccessToken(value, expires)
            return self.cached
        except DriveError:
            raise
        except (httpx.RequestError, ValueError, KeyError, TypeError, AttributeError):
            raise DriveError('credenciais') from None

    def close(self):
        self.cached = None
        self.client.close()


class ProbeHTTPTransport(httpx.BaseTransport):
    """HTTPS Google fixo; GET de metadados e CREATE só de dois PNGs aprovados."""
    def __init__(self, configuration, approval, items, contents, *, inner=None):
        approval.validate(configuration)
        if set(items) != {'argentina', 'portugal'} or set(contents) != set(items): raise DriveError('autorizacao')
        if approval.plan_sha256 != plan_digest(items): raise DriveError('autorizacao')
        for mission, item in items.items():
            content = probe_png(mission)
            if (contents[mission] != content or item.checksum != hashlib.sha256(content).hexdigest()
                    or item.size_bytes != len(content) or item.mime != 'image/png' or item.extension != 'png'
                    or item.mission_code != mission or item.category != 'deslocamentos'
                    or not re.fullmatch(r'secco-ensaio-[a-f0-9]{16}-'+mission+r'\.png', item.official_name)):
                raise DriveError('sintetico')
        self.configuration, self.approval = configuration, approval
        self.items, self.contents = items, contents
        self.remote_ids = {}
        self.keys = {}
        self.reservations = 0
        self.inner = inner if inner is not None else httpx.HTTPTransport(retries=0,trust_env=False)

    def bind(self, mission, remote_id, key):
        if (mission not in self.items or not valid_id(remote_id) or not re.fullmatch('[a-f0-9]{64}', key)
                or key != self.items[mission].object_key
                or (mission in self.remote_ids and self.remote_ids[mission] != remote_id)
                or remote_id in {i for m,i in self.remote_ids.items() if m != mission}):
            raise DriveError('destino')
        self.remote_ids[mission], self.keys[mission] = remote_id, key

    def handle_request(self, request):
        self.approval.validate(self.configuration)
        url = request.url
        if (url.scheme != 'https' or url.host != 'www.googleapis.com' or url.port not in (None,443)
                or url.username or url.password or url.fragment): raise DriveError('destino')
        drives = {self.configuration.argentina, self.configuration.portugal}
        folders = {i for categories in self.configuration.folders().values() for i in categories.values()}
        ids = drives | folders | set(self.remote_ids.values())
        if 'alt' in url.params or 'useDomainAdminAccess' in url.params:
            raise DriveError('destino')
        if request.method == 'GET':
            allowed = url.path in {f'/drive/v3/files/{i}' for i in folders | set(self.remote_ids.values())}
            allowed |= url.path in {f'/drive/v3/files/{i}/permissions' for i in ids}
            allowed |= url.path == '/drive/v3/files/generateIds'
            if not allowed or request.content: raise DriveError('destino')
            if url.path == '/drive/v3/files/generateIds':
                if (dict(url.params) != {'count':'1','space':'drive','type':'files'}
                        or self.reservations >= 2): raise DriveError('destino')
                self.reservations += 1
        elif request.method == 'POST' and str(url.copy_with(query=None)) == UPLOAD:
            self._validate_create(request)
        else:
            # Nunca PATCH, DELETE, compartilhamento, criação de pasta, lista ampla ou download.
            raise DriveError('destino')
        return self.inner.handle_request(request)

    def _validate_create(self, request):
        if request.url.params.get('supportsAllDrives') != 'true' or request.url.params.get('uploadType') != 'multipart':
            raise DriveError('destino')
        try:
            message = BytesParser(policy=policy.default).parsebytes(
                ('Content-Type: '+request.headers['content-type']+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+request.content)
            parts = list(message.iter_parts())
            if len(parts) != 2: raise ValueError()
            metadata = json.loads(parts[0].get_payload(decode=True))
            content = parts[1].get_payload(decode=True)
            mission = metadata['appProperties']['secco_mission']
            item = self.items[mission]
            _, folder = self.configuration.destination(mission, item.category)
            expected = {'id': self.remote_ids[mission], 'name': item.official_name, 'parents': [folder],
                'mimeType': 'image/png', 'appProperties': {'secco_sync': self.keys[mission], 'secco_mission': mission}}
            if metadata != expected or content != self.contents[mission] or len(content) > 1024:
                raise ValueError()
        except (ValueError, KeyError, TypeError, AttributeError):
            raise DriveError('sintetico') from None

    def close(self):
        self.inner.close()


class SupervisedProbeAdapter(GoogleDriveAdapter):
    """Entrada explícita do ensaio; não é usada por FastAPI, Settings ou worker."""
    def __init__(self, configuration, credentials, approval, items, contents, *, inner=None):
        approval.validate(configuration)
        protect_http_logs()
        self.configuration, self.credentials = configuration, credentials
        self.probe_transport = ProbeHTTPTransport(configuration, approval, items, contents, inner=inner)
        self.client = httpx.Client(transport=self.probe_transport, timeout=30, follow_redirects=False, trust_env=False)

    def _request(self, *args, **kwargs):
        # Preserva o diagnóstico IAM controlado também numa renovação durante o ensaio.
        try: self.credentials.access_token()
        except DriveError: raise
        except Exception: raise DriveError('credenciais') from None
        return super()._request(*args, **kwargs)
