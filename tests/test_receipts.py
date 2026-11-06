"""Somente identidades, metadados e arquivos sintéticos em concessões temporárias."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import struct
import zlib

import pytest
from fastapi.testclient import TestClient
from app.core.config import Settings, ROOT
from app.core.test_database import UnsafeTestDatabase, assert_temporary_database
from app.db.connection import connect
from app.db.migrate import migrate
from app.main import create_app
from app.services.receipts import load_rules, official_filename, validate_expense
from app.services.receipt_storage import TemporaryReceiptStorage, validate_file
from app.services.itinerary import InvalidActivity
from auth_support import synthetic_settings, SyntheticGoogle, login_as

BASE='/missoes/argentina/comprovantes'


def png():
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\xff\xff\xff'))+chunk(b'IEND',b'')


def pdf():
    data=b'%PDF-1.4\n'
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>']
    offsets=[]
    for i,obj in enumerate(objects,1):
        offsets.append(len(data)); data+=str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
    xref=len(data)
    data+=b'xref\n0 4\n0000000000 65535 f \n'
    for offset in offsets: data+=f'{offset:010d} 00000 n \n'.encode()
    data+=b'trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n'+str(xref).encode()+b'\n%%EOF\n'
    return data


@pytest.fixture
def receipt_client(tmp_path):
    settings=synthetic_settings(tmp_path/'receipts.sqlite3',receipts_synthetic_enabled=True)
    app=create_app(settings)
    google=SyntheticGoogle(settings); app.state.oidc=google.provider()
    with TestClient(app,base_url='http://127.0.0.1') as client:
        assert login_as(client,google).status_code==303
        yield client,google


def values(client,kind='aplicativo',**changes):
    assert client.get(BASE+'/novo').status_code==200
    data={'csrf_token':client.cookies.get('secco_csrf'),'request_key':secrets.token_urlsafe(24),
        'participant_id':'3','tipo':kind,'rubrica':'Rubrica sintética','data':'2026-11-18','valor':'12,34',
        'moeda':'ARS','descricao':'Transporte sintético para teste','intent':'rascunho','synthetic_ack':'on'}
    data.update(changes)
    return data


def send(client,data,files=None,url=None,json_response=True):
    # Uma parte vazia força multipart, inclusive no rascunho sem anexo.
    upload=files if files is not None else [('files',('',b'','application/octet-stream'))]
    return client.post(url or BASE+'/novo',data=data,files=upload,headers={'Accept':'application/json'} if json_response else {},follow_redirects=False)


def entry_id(response):
    assert response.status_code in (200,303),response.text
    url=response.json()['redirect'] if response.status_code==200 else response.headers['location']
    return int(url.split('?')[0].split('/')[-1])


def get_entry(client,item):
    user=client.get('/api/usuario').json()
    return client.app.state.receipts.get(2,item,user['id'])


def image_upload(): return [('files',('comprovante-sintetico.png',png(),'image/png'))]


def test_quick_action_and_prefilled_fields(receipt_client):
    client,_=receipt_client
    page=client.get('/missoes/argentina')
    assert 'Registrar comprovante' in page.text and BASE+'/novo' in page.text
    page=client.get(BASE+'/novo')
    assert 'Tiago Prado' in page.text and 'Fora da subvenção' in page.text
    assert 'capture="environment"' in page.text and 'multipart/form-data' in page.text
    assert '<option selected>ARS</option>' in page.text
    assert 'name="participant_id" value="3"' in page.text
    assert 'value="'+__import__('app.services.itinerary',fromlist=['mission_today']).mission_today(client.app.state.repository.get('argentina')).isoformat()+'"' in page.text


def test_draft_partial_persistence_and_funding(receipt_client):
    client,_=receipt_client
    item=entry_id(send(client,values(client,data='',valor='',rubrica='',descricao='')))
    entry=get_entry(client,item)
    assert entry['status']=='rascunho' and entry['valor_centavos'] is None and entry['data'] is None
    assert entry['participant']['financiado_pela_subvencao']==0
    with connect(client.app.state.settings.database_path) as db:
        assert db.execute('SELECT COUNT(*) FROM mission_results').fetchone()[0]==0
        assert [r[0] for r in db.execute('SELECT participant_id FROM mission_participants WHERE financiado_pela_subvencao=1 ORDER BY participant_id')]==[1,4]


@pytest.mark.parametrize('participant,code,currency,funded,email,sub',[
 (1,'portugal','EUR',1,'hugo@workspace.test','synthetic-hugo'),(2,'portugal','EUR',0,'alan@workspace.test','synthetic-alan'),
 (4,'argentina','ARS',1,'bruno@workspace.test','synthetic-bruno')])
def test_each_participant_uses_existing_identity(receipt_client,participant,code,currency,funded,email,sub):
    client,google=receipt_client
    assert login_as(client,google,email=email,sub=sub).status_code==303
    base=f'/missoes/{code}/comprovantes'
    assert client.get(base+'/novo').status_code==200
    data={'csrf_token':client.cookies.get('secco_csrf'),'request_key':secrets.token_urlsafe(24),'participant_id':str(participant),'tipo':'diaria','rubrica':'Teste','data':'2026-11-18','valor':'1','moeda':currency,'descricao':'Teste sintético','intent':'rascunho','synthetic_ack':'on'}
    response=send(client,data,url=base+'/novo'); item=entry_id(response)
    mission_id=1 if code=='portugal' else 2
    entry=client.app.state.receipts.get(mission_id,item,client.get('/api/usuario').json()['id'])
    assert entry['participant_id']==participant and entry['participant']['financiado_pela_subvencao']==funded
    with connect(client.app.state.settings.database_path) as db: assert db.execute('SELECT COUNT(*) FROM participants').fetchone()[0]==4


@pytest.mark.parametrize('kind',list(load_rules()['types']))
def test_all_expense_types_and_checklists(receipt_client,kind):
    client,_=receipt_client
    data=values(client,kind=kind)
    item=entry_id(send(client,data))
    entry=get_entry(client,item)
    assert entry['tipo']==kind and entry['checklist']['revision']==1
    assert entry['checklist']['definition']==load_rules()['types'][kind]


@pytest.mark.parametrize('field,value',[
 ('valor','-1'),('valor','0'),('valor','1.000,00'),('valor','NaN'),('valor','1.234'),('moeda','BTC'),
 ('data','2026-02-30'),('data','2026-11-18T12:00'),('tipo','inexistente'),('participant_id','4'),
 ('synthetic_ack',''),('intent','validado_manualmente'),('descricao','x'*1201),('rubrica','x'*121)])
def test_invalid_metadata_does_not_write_files(receipt_client,field,value):
    client,_=receipt_client
    response=send(client,values(client,**{field:value}),image_upload())
    assert response.status_code==422,response.text
    assert list(client.app.state.receipt_storage.directory.iterdir())==[client.app.state.receipt_storage.marker]
    with connect(client.app.state.settings.database_path) as db: assert db.execute('SELECT COUNT(*) FROM expenses').fetchone()[0]==0


@pytest.mark.parametrize('field',['rubrica','data','valor','descricao'])
def test_required_fields_for_review(receipt_client,field):
    client,_=receipt_client
    response=send(client,values(client,kind='diaria',intent='revisao',**{field:''}),image_upload())
    assert response.status_code==422


def test_transport_details_required_for_review(receipt_client):
    client,_=receipt_client
    response=send(client,values(client,intent='revisao'),image_upload())
    assert response.status_code==422 and 'extra_trajeto' in response.json()['errors']


@pytest.mark.parametrize('extension,mime,content',[('png','image/png',png()),('pdf','application/pdf',pdf())])
def test_synthetic_upload_checksum_private_download(receipt_client,extension,mime,content):
    client,_=receipt_client
    item=entry_id(send(client,values(client),[('files',('sintetico.'+extension,content,mime))]))
    entry=get_entry(client,item); attachment=entry['attachments'][0]
    assert attachment['available'] and attachment['checksum']==hashlib.sha256(content).hexdigest()
    assert attachment['storage_status']=='recebido_temporario' and attachment['sync_status']=='pendente'
    assert attachment['official_name'] is None and attachment['name_status']=='pendente'
    path=client.app.state.receipt_storage.directory/attachment['id']
    assert path.read_bytes()==content and not path.is_relative_to(ROOT/'app/static')
    assert_temporary_database(path)
    response=client.get(BASE+f'/{item}/anexos/'+attachment['id'])
    assert response.content==content and response.headers['content-disposition'].startswith('attachment;')
    assert response.headers['cache-control']=='no-store'


@pytest.mark.parametrize('name,mime,content',[
 ('bad.exe','image/png',png()),('bad.png','text/html',png()),('bad.png','image/png',b'not png'),
 ('bad.pdf','application/pdf',b'%PDF-1.4 fake'),('bad.jpg','image/jpeg',b'\xff\xd8fake\xff\xd9'),
 ('bad.png','image/png',png()[:-4]),('bad.png','image/png',png()+b'junk'),
 ('bad.pdf','application/pdf',pdf().replace(b'/Catalog',b'/JavaScript')),
 ('bad.pdf','application/pdf',pdf().replace(b'/Catalog',b'/J#61vaScript')),
 ('empty.png','image/png',b''),('large.png','image/png',b'x'*(5*1024*1024+1)),
 ('../../secret.png','image/png',png()),('..\\secret.png','image/png',png()),('C:secret.png','image/png',png()),
 ('.hidden.png','image/png',png()),('trailing.png.','image/png',png())],ids=lambda value: f'{len(value)}-bytes' if isinstance(value,bytes) else value)
def test_invalid_files_rejected(receipt_client,name,mime,content):
    client,_=receipt_client
    response=send(client,values(client),[('files',(name,content,mime))])
    assert response.status_code==422,response.text
    assert list(client.app.state.receipt_storage.directory.iterdir())==[client.app.state.receipt_storage.marker]


def test_body_limit_and_file_count(receipt_client):
    client,_=receipt_client
    response=send(client,values(client),[('files',('large.png',b'x'*(12*1024*1024),'image/png'))])
    assert response.status_code==413
    response=send(client,values(client),image_upload()*5)
    assert response.status_code==400


def test_csrf_origin_and_anonymous_access(receipt_client):
    client,_=receipt_client
    data=values(client,csrf_token='invalid')
    assert send(client,data,image_upload()).status_code==403
    data=values(client)
    assert client.post(BASE+'/novo',data=data,files=image_upload(),headers={'Origin':'https://evil.test'}).status_code==403
    client.cookies.clear()
    assert client.get(BASE,follow_redirects=False).status_code==303
    assert send(client,data,image_upload()).status_code==401


def test_mission_and_owner_isolation(receipt_client):
    client,google=receipt_client
    item=entry_id(send(client,values(client),image_upload())); a=get_entry(client,item)['attachments'][0]
    assert client.get('/missoes/portugal/comprovantes/novo').status_code==403
    assert client.post('/missoes/portugal/comprovantes/novo',data={},files=image_upload()).status_code==403
    assert login_as(client,google,email='bruno@workspace.test',sub='synthetic-bruno').status_code==303
    assert client.get(BASE+f'/{item}').status_code==404
    assert client.get(BASE+f'/{item}/editar').status_code==404
    assert client.get(BASE+f'/{item}/anexos/'+a['id']).status_code==404
    assert client.post(BASE+f'/{item}/editar',data={},files=image_upload()).status_code==404
    assert 'Transporte sintético para teste' not in client.get(BASE).text


def test_idempotency_and_duplicate_attachments(receipt_client):
    client,_=receipt_client
    data=values(client); item=entry_id(send(client,data,image_upload()*2))
    assert entry_id(send(client,data,image_upload()*2))==item
    assert len(get_entry(client,item)['attachments'])==1
    assert send(client,{**data,'valor':'99'},image_upload()*2).status_code==409
    with connect(client.app.state.settings.database_path) as db:
        assert db.execute('SELECT COUNT(*) FROM expenses').fetchone()[0]==1
        assert db.execute('SELECT COUNT(*) FROM expense_history').fetchone()[0]==1


def test_edit_version_history_and_metadata(receipt_client):
    client,_=receipt_client
    item=entry_id(send(client,values(client),image_upload()))
    data=values(client,version='1',descricao='Texto sintético editado')
    url=BASE+f'/{item}/editar'
    assert entry_id(send(client,data,url=url))==item
    assert entry_id(send(client,data,url=url))==item
    entry=get_entry(client,item)
    assert entry['version']==2 and entry['descricao']=='Texto sintético editado'
    assert len(client.app.state.receipts.history(item,entry['created_by_user_id']))==2
    stale=values(client,version='1',descricao='Texto preservado por conflito')
    response=send(client,stale,url=url,json_response=False)
    assert response.status_code==409 and 'Texto preservado por conflito' in response.text
    assert client.get(url).status_code==200


def test_ready_requires_checklist_and_never_means_validated(receipt_client):
    client,_=receipt_client
    data=values(client,kind='diaria',intent='revisao')
    item=entry_id(send(client,data,image_upload()))
    assert get_entry(client,item)['status']=='pendente_revisao'
    data=values(client,kind='diaria',intent='revisao',check_diaria_0='on',check_diaria_1='on')
    item=entry_id(send(client,data,image_upload()))
    assert get_entry(client,item)['status']=='pronto_revisao'
    page=client.get(BASE+f'/{item}?aviso=salvo')
    assert page.status_code==200 and 'Metadados salvos no SQLite local.' in page.text
    assert 'não garante conservação' in page.text
    assert 'Nome oficial pendente' in page.text
    with pytest.raises(sqlite3.IntegrityError):
        with connect(client.app.state.settings.database_path) as db: db.execute("UPDATE expenses SET status='validado_manualmente' WHERE id=?",(item,))


def test_pending_receipt_and_conditional_exchange(receipt_client):
    client,_=receipt_client
    data=values(client,kind='inscricao_evento',intent='revisao',check_inscricao_evento_0='on',check_inscricao_evento_1='on')
    item=entry_id(send(client,data)); assert get_entry(client,item)['status']=='pendente_comprovante'
    item=entry_id(send(client,values(client,kind='inscricao_evento',intent='revisao',check_inscricao_evento_0='on',check_inscricao_evento_1='on'),image_upload()))
    assert get_entry(client,item)['status']=='pendente_revisao'
    item=entry_id(send(client,values(client,kind='inscricao_evento',intent='revisao',check_inscricao_evento_0='on',check_inscricao_evento_1='on',conditional_inscricao_evento_0='nao_exigido'),image_upload()))
    assert get_entry(client,item)['status']=='pronto_revisao'


def test_storage_failure_preserves_metadata_and_retry(receipt_client,monkeypatch):
    client,_=receipt_client
    storage=client.app.state.receipt_storage
    with monkeypatch.context() as patch:
        patch.setattr(storage,'put',lambda *args: (_ for _ in ()).throw(OSError('falha sintética')))
        item=entry_id(send(client,values(client,kind='diaria',intent='revisao'),image_upload()))
    entry=get_entry(client,item)
    assert entry['status']=='pendente_comprovante' and entry['attachments'][0]['storage_status']=='falha'
    assert not entry['attachments'][0]['available']
    response=client.get(BASE+f'/{item}?aviso=salvo')
    assert 'falharam ou estão indisponíveis' in response.text
    data=values(client,kind='diaria',intent='revisao',version='1')
    assert entry_id(send(client,data,image_upload(),BASE+f'/{item}/editar'))==item
    assert len(get_entry(client,item)['attachments'])==1 and get_entry(client,item)['attachments'][0]['available']


def test_missing_corrupt_and_expired_storage_never_claims_synced(receipt_client):
    client,_=receipt_client
    item=entry_id(send(client,values(client,kind='diaria',intent='revisao',check_diaria_0='on',check_diaria_1='on'),image_upload()))
    entry=get_entry(client,item); attachment=entry['attachments'][0]
    file=client.app.state.receipt_storage.directory/attachment['id']; file.write_bytes(b'corrompido')
    assert get_entry(client,item)['effective_status']=='pendente_comprovante'
    assert client.get(BASE+f'/{item}/anexos/'+attachment['id']).status_code==410
    file.unlink()
    assert not get_entry(client,item)['attachments'][0]['available']


def test_database_failure_does_not_claim_success(receipt_client,monkeypatch):
    client,_=receipt_client
    with monkeypatch.context() as patch:
        patch.setattr(client.app.state.receipts,'save',lambda *a,**k: (_ for _ in ()).throw(sqlite3.OperationalError('falha sintética')))
        response=send(client,values(client),image_upload())
    assert response.status_code==503 and 'Não foi possível confirmar' in response.json()['errors']['form']


def test_no_javascript_form_and_error_preservation(receipt_client):
    client,_=receipt_client
    response=send(client,values(client,valor='invalido',descricao='Texto sintético preservado'),image_upload(),json_response=False)
    assert response.status_code==422 and 'Texto sintético preservado' in response.text and 'selecione os arquivos novamente' in response.text
    # Campos têm nomes exclusivos para todas as seções, inclusive sem JS.
    page=client.get(BASE+'/novo').text
    names=re.findall(r'name="((?:extra|check|conditional)_[^"]+)"',page)
    assert len(names)==len(set(names))
    item=entry_id(send(client,values(client),image_upload(),json_response=False))
    assert client.get(BASE+f'/{item}').status_code==200
    assert 'method="post" enctype="multipart/form-data"' in page


def test_no_auth_bypass_and_explicit_activation(tmp_path):
    with TestClient(create_app(Settings('development',True,tmp_path/'dev.sqlite3',receipts_synthetic_enabled=True))) as client:
        assert client.get(BASE+'/novo').status_code==403
    settings=synthetic_settings(tmp_path/'off.sqlite3')
    app=create_app(settings); google=SyntheticGoogle(settings); app.state.oidc=google.provider()
    with TestClient(app,base_url='http://127.0.0.1') as client:
        assert login_as(client,google).status_code==303
        assert client.get(BASE+'/novo').status_code==503
    with pytest.raises(RuntimeError,match='somente em desenvolvimento'):
        replace(settings,app_env='production',receipts_synthetic_enabled=True).validate()


def test_storage_cannot_use_operational_path_and_cleans_lease(tmp_path):
    with pytest.raises(UnsafeTestDatabase): TemporaryReceiptStorage(ROOT/'data/secco.sqlite3')
    storage=TemporaryReceiptStorage(tmp_path/'isolated.sqlite3')
    directory=storage.directory
    assert directory.is_relative_to(tmp_path)
    storage.put('a'*32,png())
    with pytest.raises(OSError): storage.read('../escape',hashlib.sha256(png()).hexdigest())
    storage.close(); assert not directory.exists()


def test_automatic_filename_pending_and_sanitized(receipt_client):
    client,_=receipt_client
    mission=client.app.state.repository.get('argentina')
    data={'data':'2026-11-18','rubrica':'Rubrica / sintética','tipo':'aplicativo','valor_centavos':1234,'moeda':'ARS'}
    assert official_filename(None,mission,data,'Tiago Prado','a'*32,'png') is None
    filename=official_filename('PROCESSO SINTÉTICO / TESTE',mission,data,'Tiago Prado','a'*32,'png')
    assert filename=='processo-sintetico-teste_argentina_2026-11-18_rubrica-sintetica_aplicativo_12.34ARS_tiago-prado_'+'a'*32+'.png'
    assert filename!=official_filename('PROCESSO SINTÉTICO / TESTE',mission,data,'Tiago Prado','b'*32,'png')
    with connect(client.app.state.settings.database_path) as db:
        db.execute('INSERT INTO receipt_mission_config(mission_id,processo) VALUES(2,?)',('PROCESSO SINTÉTICO / TESTE',))
    item=entry_id(send(client,values(client),image_upload()))
    assert get_entry(client,item)['attachments'][0]['name_status']=='preparado'


def test_migration_integrity_and_no_duplicate_seed(receipt_client):
    client,_=receipt_client
    location=client.app.state.settings.database_path
    item=entry_id(send(client,values(client),image_upload()))
    migrate(location); migrate(location)
    assert get_entry(client,item)
    with connect(location) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert db.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0]==6
        assert db.execute('SELECT COUNT(*) FROM expenses').fetchone()[0]==1
        with pytest.raises(sqlite3.IntegrityError): db.execute('UPDATE expenses SET mission_id=1 WHERE id=?',(item,))


def test_rule_catalog_is_configurable_and_snapshotted(receipt_client,tmp_path,monkeypatch):
    client,_=receipt_client
    import app.services.receipts as module
    catalog=load_rules(); catalog['revision']=2; catalog['types']['diaria']['items'].append('Exigência sintética de teste')
    target=tmp_path/'receipt_rules.json'; target.write_text(json.dumps(catalog),encoding='utf-8')
    monkeypatch.setattr(module,'RULES_PATH',target)
    item=entry_id(send(client,values(client,kind='diaria')))
    entry=get_entry(client,item)
    assert entry['checklist']['revision']==2 and len(entry['checklist']['definition']['items'])==3


def test_mobile_template_accessibility_contract(receipt_client):
    client,_=receipt_client
    page=client.get(BASE+'/novo')
    assert 'name="viewport"' in page.text and 'inputmode="decimal"' in page.text
    assert 'role="status"' in page.text and 'role="alert"' in page.text and '<noscript>' in page.text
    assert '\u2014' not in page.text
    assert "blob:" in page.headers['content-security-policy']
    css=client.get('/static/css/receipts.css').text
    assert '@media(max-width:600px)' in css and 'min-width:0' in css


def test_transaction_rollback_removes_new_files(receipt_client):
    client,_=receipt_client
    with connect(client.app.state.settings.database_path) as db:
        db.execute("CREATE TRIGGER fail_receipt_history BEFORE INSERT ON expense_history BEGIN SELECT RAISE(ABORT,'falha sintética'); END")
    response=send(client,values(client),image_upload())
    assert response.status_code==503
    with connect(client.app.state.settings.database_path) as db:
        assert db.execute('SELECT COUNT(*) FROM expenses').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM expense_attachments').fetchone()[0]==0
    assert list(client.app.state.receipt_storage.directory.iterdir())==[client.app.state.receipt_storage.marker]


def test_storage_quota_becomes_visible_failure(receipt_client,monkeypatch):
    client,_=receipt_client
    import app.services.receipt_storage as module
    monkeypatch.setattr(module,'MAX_STORAGE',1)
    item=entry_id(send(client,values(client,kind='diaria',intent='revisao'),image_upload()))
    entry=get_entry(client,item)
    assert entry['status']=='pendente_comprovante' and entry['attachments'][0]['storage_status']=='falha'


def test_multipart_duplicate_text_and_wrong_encoding_rejected(receipt_client):
    client,_=receipt_client
    data=values(client)
    parts=[(key,(None,value)) for key,value in data.items()]+[('tipo',(None,'diaria'))]
    assert client.post(BASE+'/novo',files=parts).status_code==400
    assert client.post(BASE+'/novo',data=data).status_code==415


def test_checklist_body_and_participant_are_not_authority(receipt_client):
    client,_=receipt_client
    data=values(client,created_by_user_id='999',status='validado_manualmente',financiado_pela_subvencao='1')
    item=entry_id(send(client,data,image_upload()))
    entry=get_entry(client,item)
    assert entry['status']=='rascunho' and entry['participant']['financiado_pela_subvencao']==0
    assert entry['created_by_user_id']==client.get('/api/usuario').json()['id']
