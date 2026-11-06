"""Synthetic documents and leased SQLite only; never read operational itineraries."""
from dataclasses import replace
from datetime import date, datetime, time, timezone
from pathlib import Path
import hashlib
import json
import sqlite3

import pytest
from openpyxl import Workbook
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from app.db.connection import connect
from app.repositories.itinerary import ItineraryRepository
from app.repositories.missions import MissionRepository
from app.services.itinerary import validate_activity
from app.services.itinerary_documents import DocumentError, ParsedDocument, SourceEvent, read_document, category
from app.services.itinerary_import import ImportConflict, preview, apply_plan, readonly, database_fingerprints, local_database
from app.services.itinerary_provenance import decode, PREFIX
from app.services.missions import operational_dashboard
from scripts.import_itinerary import main as import_main, private_path
from test_workspace_access import workspace, coordinator
from auth_support import login_as


@pytest.fixture
def import_db(database):
    with connect(database) as db:
        db.execute("UPDATE missions SET data_inicio='2031-11-01',data_fim='2031-11-30'")
    return database


def event(**changes):
    return SourceEvent(**dict({'day':'2031-11-10','title':'Encontro fictício de laboratórios',
        'description':'Programação sintética para teste','category':'institucional','locator':'Teste!C7:C8',
        'start':'09:00','end':'10:00','time_kind':'grid','grid_start':'09:00','grid_end':'10:00'},**changes))


def document(*events):
    return ParsedDocument('synthetic','fixture.xlsx','synthetic-document-digest',list(events or [event()]))


def run_import(path,doc,backup,code='argentina',**options):
    plan=preview(path,code,doc,'synthetic-edition',**options)
    return apply_plan(path,doc,'synthetic-edition',plan,backup,**options)


def workbook(tmp_path, entries, days=3):
    book=Workbook();sheet=book.active;sheet.title='Teste'
    sheet['C2']=datetime(2031,11,10)
    for col in range(3,3+days):sheet.cell(3,col,'=C2'+('+'+str(col-3) if col>3 else ''))
    for row in range(5,29):sheet.cell(row,2,time(8+(row-5)//2,30*((row-5)%2)))
    for coordinate,value in entries.items():sheet[coordinate]=value
    path=tmp_path/'fixture.xlsx';book.save(path);book.close()
    return path


def pdf_fixture(tmp_path):
    writer=PdfWriter();page=writer.add_blank_page(width=360,height=400)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    commands=['0.3 0.9 0.4 rg 70 270 110 40 re f','0.2 0.4 0.9 rg 190 100 110 235 re f','0 0 0 rg']
    def text(x,y,value):commands.append(f'BT /F1 9 Tf {x} {y} Td ({value}) Tj ET')
    text(100,360,'10/11/2031');text(220,360,'11/11/2031')
    for n in range(12):text(20,320-20*n,f'{8+n//2:02}:{30*(n%2):02}')
    text(83,290,'Visita ficticia');text(83,190,'Encontro teste 11-12')
    text(205,230,'Congresso ficticio')
    content=DecodedStreamObject();content.set_data('\n'.join(commands).encode('ascii'))
    page[NameObject('/Contents')]=writer._add_object(content)
    path=tmp_path/'fixture.pdf'
    with path.open('wb') as handle:writer.write(handle)
    return path


def test_xlsx_dates_consolidation_sessions_and_free_days(tmp_path):
    path=workbook(tmp_path,{'C7':'Feira fictícia','C8':'Feira fictícia','C10':'Feira fictícia',
        'D7':'Dia livre','E7':'Cidade Exemplo','E8':'Reunião sintética'})
    doc=read_document(path,context_labels=['Cidade Exemplo'])
    assert len(doc.events)==3
    assert [(e.day,e.start,e.end) for e in doc.events[:2]]==[('2031-11-10','09:00','10:00'),('2031-11-10','10:30',None)]
    assert doc.free_windows[0]['day']=='2031-11-11' and doc.free_windows[0]['all_day']
    assert doc.contexts[0]['day']=='2031-11-12'
    assert doc.events[-1].day=='2031-11-12'


def test_xlsx_explicit_intervals_preserve_simultaneous_meal(tmp_path):
    doc=read_document(workbook(tmp_path,{'C7':'Congresso exemplo - 9 as 12','C8':'Congresso exemplo - 9 as 12',
        'C9':'Almoço institucional','C10':'Congresso exemplo - 9 as 12','C11':'Congresso exemplo - 9 as 12','C12':'Congresso exemplo - 9 as 12'}))
    assert len(doc.events)==2
    assert (doc.events[0].start,doc.events[0].end,doc.events[0].time_kind)==('09:00','12:00','explicit')
    assert doc.events[1].category=='alimentacao' and doc.events[1].start=='10:00'


@pytest.mark.parametrize('text,kind',[('Café teste (verificar local e confirmar horário)','provisional'),
    ('Visita teste - 11 as 12','conflict'),('Visita teste','grid')])
def test_xlsx_provisional_and_written_grid_conflicts(tmp_path,text,kind):
    doc=read_document(workbook(tmp_path,{'C7':text}))
    assert doc.events[0].time_kind==kind
    assert doc.events[0].end is None if kind!='conflict' else doc.events[0].end=='12:00'


def test_xlsx_address_and_different_similar_events(tmp_path):
    doc=read_document(workbook(tmp_path,{'C7':'Almoço corporativo fictício + traslado','C8':'Almoço corporativo fictício',
        'D7':'Visita fictícia (Centro Exemplo)\nMorada: Rua Sintética, 123'}))
    assert len(doc.events)==3
    assert doc.events[-1].location=='Centro Exemplo'
    assert doc.events[-1].address=='Rua Sintética, 123'


def test_xlsx_rejects_unknown_date_formula(tmp_path):
    path=workbook(tmp_path,{'C3':'=TODAY()','C7':'Atividade'})
    with pytest.raises(DocumentError,match='Fórmula'):read_document(path)


def test_pdf_real_extraction_keeps_color_as_suggestion(tmp_path):
    path=pdf_fixture(tmp_path);doc=read_document(path,year=2031)
    assert len(doc.events)==3
    assert doc.events[0].day=='2031-11-10'
    assert doc.events[0].time_kind=='grid_window'
    assert doc.events[0].start is None and doc.events[0].end is None
    assert doc.events[1].time_kind=='explicit' and doc.events[1].start=='11:00'
    assert doc.events[2].day=='2031-11-11' and doc.events[2].time_kind=='missing'
    with pytest.raises(DocumentError,match='ano'):read_document(path)


def test_preview_never_writes_and_second_import_is_noop(import_db,tmp_path):
    before=hashlib.sha256(import_db.read_bytes()).hexdigest();doc=document()
    plan=preview(import_db,'argentina',doc,'synthetic-edition')
    assert plan['counts']=={'new':1}
    assert before==hashlib.sha256(import_db.read_bytes()).hexdigest()
    result=apply_plan(import_db,doc,'synthetic-edition',plan,tmp_path/'backup.sqlite3')
    assert result['created']==1
    before=hashlib.sha256(import_db.read_bytes()).hexdigest()
    assert preview(import_db,'argentina',doc,'synthetic-edition')['counts']=={'existing':1}
    assert run_import(import_db,doc,tmp_path/'unused.sqlite3')['created']==0
    assert before==hashlib.sha256(import_db.read_bytes()).hexdigest() and not (tmp_path/'unused.sqlite3').exists()
    with readonly(tmp_path/'backup.sqlite3') as backup:assert database_fingerprints(backup)==plan['database_fingerprints']


@pytest.mark.parametrize('code,expected',[('argentina','2031-11-10T12:00:00Z'),('portugal','2031-11-10T09:00:00Z')])
def test_mission_timezone_and_isolation(import_db,tmp_path,code,expected):
    other=1 if code=='argentina' else 2
    before=ItineraryRepository(import_db).list(other)
    run_import(import_db,document(),tmp_path/'backup.sqlite3',code=code)
    items=ItineraryRepository(import_db).list(2 if code=='argentina' else 1)
    item=next(i for i in items if i['document_source'])
    assert item['inicio_utc']==expected and item['status']=='a_confirmar'
    assert ItineraryRepository(import_db).list(other)==before


def test_preserves_manual_records_and_all_other_tables(import_db,tmp_path):
    repo=ItineraryRepository(import_db);mission=MissionRepository(import_db).get('argentina')
    manual=repo.save(2,validate_activity({'titulo':'Passeio sintético manual','categoria':'turismo','data':'2031-11-10'},mission))
    before=repo.get(2,manual)
    with readonly(import_db) as db:fingerprints=database_fingerprints(db)
    run_import(import_db,document(),tmp_path/'backup.sqlite3')
    assert repo.get(2,manual)==before
    with readonly(import_db) as db:after=database_fingerprints(db)
    for table in fingerprints:
        if table not in {'itinerary_items','itinerary_history','itinerary_participants'}:assert after[table]==fingerprints[table]


def test_manual_edit_blocks_import_update(import_db,tmp_path):
    run_import(import_db,document(),tmp_path/'first.sqlite3');repo=ItineraryRepository(import_db)
    item=next(i for i in repo.list(2) if i['document_source'])
    mission=MissionRepository(import_db).get('argentina')
    data=validate_activity({**item,'observacoes':'Anotação manual a preservar','participantes':[]},mission)
    repo.save(2,data,item['id'],item['version'])
    doc=document(event(start='10:00',end='11:00'))
    plan=preview(import_db,'argentina',doc,'synthetic-edition',allow_source_updates=True)
    assert plan['counts']=={'conflict':1}
    with pytest.raises(ImportConflict):apply_plan(import_db,doc,'synthetic-edition',plan,tmp_path/'blocked.sqlite3',allow_source_updates=True)
    assert repo.get(2,item['id'])['observacoes']=='Anotação manual a preservar'


def test_source_updates_require_review_and_unmodified_baseline(import_db,tmp_path):
    run_import(import_db,document(),tmp_path/'first.sqlite3')
    doc=document(event(start='10:00',end='11:00'))
    assert preview(import_db,'argentina',doc,'synthetic-edition')['counts']=={'conflict':1}
    result=run_import(import_db,doc,tmp_path/'second.sqlite3',allow_source_updates=True)
    assert result['updated']==1
    assert preview(import_db,'argentina',doc,'synthetic-edition')['counts']=={'existing':1}


def test_duplicate_candidates_require_explicit_link_without_overwrite(import_db,tmp_path):
    mission=MissionRepository(import_db).get('argentina');repo=ItineraryRepository(import_db)
    item_id=repo.save(2,validate_activity({'titulo':event().title,'descricao':'Texto manual','data':'2031-11-10'},mission))
    before=repo.get(2,item_id);doc=document()
    plan=preview(import_db,'argentina',doc,'synthetic-edition')
    assert plan['counts']=={'possible_duplicate':1}
    with pytest.raises(ImportConflict):apply_plan(import_db,doc,'synthetic-edition',plan,tmp_path/'blocked.sqlite3')
    links={plan['entries'][0]['key']:item_id}
    assert run_import(import_db,doc,tmp_path/'linked.sqlite3',links=links)['linked']==1
    item=repo.get(2,item_id)
    assert item['titulo']==before['titulo'] and item['descricao']=='Texto manual' and item['horario_inicio'] is None
    assert preview(import_db,'argentina',doc,'synthetic-edition')['counts']=={'existing':1}


def test_conflict_in_source_is_never_imported(import_db,tmp_path):
    doc=document(event(time_kind='conflict'));plan=preview(import_db,'argentina',doc,'synthetic-edition')
    assert plan['counts']=={'conflict':1}
    with pytest.raises(ImportConflict):apply_plan(import_db,doc,'synthetic-edition',plan,tmp_path/'blocked.sqlite3')
    assert not (tmp_path/'blocked.sqlite3').exists()


def test_stale_preview_and_bad_backup_are_rejected(import_db,tmp_path):
    doc=document();plan=preview(import_db,'argentina',doc,'synthetic-edition')
    with connect(import_db) as db:db.execute("UPDATE missions SET observacoes=observacoes||' modificado' WHERE id=2")
    with pytest.raises(ImportConflict,match='desatualizada'):apply_plan(import_db,doc,'synthetic-edition',plan,tmp_path/'backup.sqlite3')
    fresh=preview(import_db,'argentina',doc,'synthetic-edition')
    with pytest.raises(ValueError,match='novo'):apply_plan(import_db,doc,'synthetic-edition',fresh,import_db)


def test_outside_mission_and_remote_db_rejected(import_db):
    with pytest.raises(ValueError,match='fora'):preview(import_db,'argentina',document(event(day='2032-01-01')),'synthetic-edition')
    with pytest.raises(ValueError,match='local'):preview('https://example.test/database','argentina',document(),'synthetic-edition')


def test_simultaneous_events_remain_separate(import_db,tmp_path):
    doc=document(event(),event(title='Almoço fictício institucional',category='alimentacao',locator='Teste!C9:C10',start='09:30',end='10:30'))
    plan=preview(import_db,'argentina',doc,'synthetic-edition')
    assert len(plan['simultaneous'])==1
    assert run_import(import_db,doc,tmp_path/'backup.sqlite3')['created']==2


def test_calendar_details_today_and_diary_compatibility(client,tmp_path):
    database=client.app.state.settings.database_path
    doc=document(event(day='2026-11-18',start=None,end=None,time_kind='grid_window',grid_start='09:00',grid_end='11:00',
        address='Rua Sintética, 123',location='Centro fictício'))
    run_import(database,doc,tmp_path/'backup.sqlite3')
    repo=client.app.state.itinerary;item=next(i for i in repo.list(2) if i['document_source'])
    page=client.get('/missoes/argentina/planejamento?data=2026-11-18').text
    assert 'Agenda oficial' in page and 'Janela sugerida pela grade' in page and 'Horário a confirmar' in page
    detail=client.get(f"/missoes/argentina/atividades/{item['id']}").text
    assert 'fixture.xlsx' in detail and 'Precisão do horário' in detail and 'Como chegar' in detail
    assert client.get(f"/missoes/portugal/atividades/{item['id']}").status_code==404
    mission=client.app.state.repository.get('argentina')
    now=datetime(2026,11,18,12,tzinfo=timezone.utc)
    context=operational_dashboard(client.app.state.repository,repo,mission,now,sync_legacy=False)
    assert item['id'] in [i['id'] for i in context['today_events']]
    assert context['next_event'] is None and context['next_planned']['id']==item['id']
    assert repo.get(2,item['id'])['status']=='a_confirmar'
    page=client.get(f"/missoes/argentina/diario/novo?agenda={item['id']}")
    assert page.status_code==200 and 'Encontro fictício' in page.text
    assert all(goal.realizado==0 for goal in client.app.state.repository.get('argentina').metas)
    assert client.get('/missoes/argentina').status_code==200
    past=operational_dashboard(client.app.state.repository,repo,mission,datetime(2027,1,1,tzinfo=timezone.utc),sync_legacy=False)
    assert past['next_planned'] is None and repo.get(2,item['id'])['status']=='a_confirmar'


@pytest.mark.parametrize('email,allowed',[('tiago@secco.example',True),('bruno@secco.example',True),
    ('hugo@secco.example',False),('alan@secco.example',False),('marcos@secco.example',False)])
def test_imported_items_keep_existing_edit_permissions(workspace,tmp_path,email,allowed):
    client,google,settings=workspace
    run_import(settings.database_path,document(event(day='2026-11-18')),tmp_path/'backup.sqlite3')
    assert login_as(client,google,email=email,sub='synthetic-'+email).status_code==303
    item=next(i for i in client.app.state.itinerary.list(2) if i['document_source'])
    assert client.get(f"/missoes/argentina/atividades/{item['id']}").status_code==200
    url=f"/missoes/argentina/atividades/{item['id']}/editar"
    assert client.get(url).status_code==(200 if allowed else 403)
    if not allowed:
        response=client.post(url,data={'titulo':'Tentativa','csrf_token':client.cookies.get('secco_csrf'),'version':item['version']})
        assert response.status_code==403
        assert client.app.state.itinerary.get(2,item['id'])['titulo']==item['titulo']


def test_cli_dry_run_apply_and_private_outputs(import_db,tmp_path,capsys):
    source=workbook(tmp_path,{'C7':'Reunião fictícia'});report=tmp_path/'preview.json'
    args=['--input',str(source),'--database',str(import_db),'--mission','argentina','--source-key','synthetic-cli']
    assert import_main(args+['--report',str(report)])==0
    assert json.loads(report.read_text(encoding='utf-8'))['counts']=={'new':1}
    assert import_main(args+['--apply','--approved-plan',str(report),'--backup',str(tmp_path/'backup.sqlite3'),
        '--owner-authorized-local','--report',str(tmp_path/'result.json')])==0
    assert json.loads((tmp_path/'result.json').read_text(encoding='utf-8'))['result']['created']==1
    with pytest.raises(ValueError,match='fora'):private_path(Path(__file__).parent/'private.json')


@pytest.mark.parametrize('format',['pdf','xlsx'])
def test_actual_document_import_and_repeat(import_db,tmp_path,format):
    source=pdf_fixture(tmp_path) if format=='pdf' else workbook(tmp_path,{'C7':'Feira sintética','C8':'Feira sintética'})
    doc=read_document(source,year=2031)
    assert run_import(import_db,doc,tmp_path/'backup.sqlite3')['created']==len(doc.events)
    assert preview(import_db,'argentina',doc,'synthetic-edition')['counts']=={'existing':len(doc.events)}


def test_source_rename_and_reschedule_in_same_cell_requires_review(import_db,tmp_path):
    run_import(import_db,document(),tmp_path/'backup.sqlite3')
    changed=document(event(title='Título alterado na fonte',day='2031-11-11'))
    assert preview(import_db,'argentina',changed,'synthetic-edition')['counts']=={'conflict':1}


def test_batch_failure_rolls_back_every_agenda_change(import_db,tmp_path,monkeypatch):
    doc=document(event(),event(title='Segunda atividade sintética',locator='Teste!C10:C11',start='11:00',end='12:00'))
    plan=preview(import_db,'argentina',doc,'synthetic-edition')
    save=ItineraryRepository.save;calls=[]
    def failing_save(self,*args,**kwargs):
        calls.append(True)
        if len(calls)==2:raise RuntimeError('Interrupção sintética')
        return save(self,*args,**kwargs)
    monkeypatch.setattr(ItineraryRepository,'save',failing_save)
    with pytest.raises(RuntimeError,match='sintética'):apply_plan(import_db,doc,'synthetic-edition',plan,tmp_path/'backup.sqlite3')
    with readonly(import_db) as db:assert database_fingerprints(db)==plan['database_fingerprints']


def test_editing_time_preserves_provenance_and_shows_team_edit(import_db,tmp_path):
    run_import(import_db,document(),tmp_path/'backup.sqlite3');repo=ItineraryRepository(import_db)
    item=next(i for i in repo.list(2) if i['document_source'])
    mission=MissionRepository(import_db).get('argentina')
    data=validate_activity({**item,'horario_inicio':'10:00','horario_fim':'11:00','participantes':[]},mission)
    repo.save(2,data,item['id'],item['version'])
    assert repo.get(2,item['id'])['time_note']=='Horário editado pela equipe'


@pytest.mark.parametrize('title,expected',[('Deslocamento para jantar sintético','transporte'),
    ('Almoço institucional + deslocamento','alimentacao'),('Jantar oficial fictício','alimentacao')])
def test_official_meals_and_transport_keep_functional_categories(title,expected):
    assert category(title)==expected


def test_calendar_keeps_tourism_separate_from_official_meals(client,tmp_path):
    path=client.app.state.settings.database_path;repo=client.app.state.itinerary
    mission=client.app.state.repository.get('argentina')
    repo.save(2,validate_activity({'titulo':'Passeio sintético de lazer','categoria':'turismo','data':'2026-11-18'},mission))
    run_import(path,document(event(day='2026-11-18',title='Almoço institucional sintético',category='alimentacao')),tmp_path/'backup.sqlite3')
    page=client.get('/missoes/argentina/planejamento?data=2026-11-18').text
    assert page.index('Agenda oficial</h3>')<page.index('Almoço institucional sintético')<page.index('Turismo / tempo livre</h3>')<page.index('Passeio sintético de lazer')


def test_cli_requires_review_and_does_not_load_environment(import_db,tmp_path,monkeypatch):
    source=workbook(tmp_path,{'C7':'Atividade fictícia'});before=hashlib.sha256(import_db.read_bytes()).hexdigest()
    monkeypatch.setenv('DATABASE_PATH','https://example.test/not-used')
    with pytest.raises(SystemExit) as error:
        import_main(['--input',str(source),'--database',str(import_db),'--mission','argentina',
            '--source-key','synthetic-cli','--apply','--report',str(tmp_path/'rejected.json')])
    assert error.value.code==2 and before==hashlib.sha256(import_db.read_bytes()).hexdigest()


def test_explicit_partial_import_preserves_pending_duplicates(import_db,tmp_path):
    repo=ItineraryRepository(import_db);mission=MissionRepository(import_db).get('argentina')
    manual=repo.save(2,validate_activity({'titulo':event().title},mission))
    before=repo.get(2,manual)
    doc=document(event(),event(title='Atividade nova e distinta',locator='Teste!C11:C12'))
    plan=preview(import_db,'argentina',doc,'synthetic-edition')
    result=apply_plan(import_db,doc,'synthetic-edition',plan,tmp_path/'backup.sqlite3',allow_partial=True)
    assert result['created']==1 and result['skipped']==1 and repo.get(2,manual)==before
    assert preview(import_db,'argentina',doc,'synthetic-edition')['counts']=={'possible_duplicate':1,'existing':1}


def test_partial_forged_metadata_is_a_regular_creation_key(client):
    from test_itinerary import create,item_from_response
    forged=PREFIX+'{"key":"x","baseline":"y"}'
    assert decode(forged) is None
    response,_=create(client,request_key=forged)
    item=item_from_response(client,response)
    assert client.get(f'/missoes/argentina/atividades/{item}').status_code==200
    assert client.app.state.itinerary.get(2,item)['document_source'] is None


def test_database_path_resolving_to_network_is_rejected(import_db,monkeypatch):
    monkeypatch.setattr(Path,'resolve',lambda self:Path('//server/share/private.sqlite3'))
    with pytest.raises(ValueError,match='local'):local_database(import_db)


def test_readonly_context_uses_a_consistent_transaction(import_db):
    with readonly(import_db) as db:
        assert db.in_transaction
        with pytest.raises(sqlite3.OperationalError,match='readonly'):db.execute("UPDATE missions SET nome='not allowed'")
