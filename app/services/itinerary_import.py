"""Dry-run first, local-only, conservative document imports using the existing agenda schema."""
from collections import Counter
from contextlib import contextmanager, closing
from dataclasses import asdict
from pathlib import Path
import json
import os
import re
import sqlite3

from app.core.test_database import enforce_database_policy, connection_factory, configure_connection
from app.db.connection import connect
from app.repositories.itinerary import ItineraryRepository, FIELDS
from app.repositories.missions import MissionRepository
from app.services.itinerary import validate_activity
from app.services.itinerary_documents import normalized
from app.services.itinerary_provenance import decode, digest, encode, TIME_LABELS


class ImportConflict(ValueError):
    pass


def local_database(path):
    raw=str(path)
    if '://' in raw or raw.startswith(('\\\\','//')):
        raise ValueError('Somente um arquivo SQLite local é permitido.')
    path=Path(path).resolve()
    if str(path).startswith(('\\\\','//')):
        raise ValueError('Somente um arquivo SQLite local é permitido.')
    if os.name=='nt':
        import ctypes
        if ctypes.windll.kernel32.GetDriveTypeW(path.anchor)==4:
            raise ValueError('Banco em unidade de rede não permitido.')
    if not path.is_file():raise ValueError('O banco local deve existir; a importação não cria nem migra bancos.')
    enforce_database_policy(path)
    return path


@contextmanager
def readonly(path):
    path=local_database(path)
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,factory=connection_factory())
    configure_connection(db);db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')
    try:yield db
    finally:db.close()


def _schema(db):
    versions={r[0] for r in db.execute('SELECT version FROM schema_migrations')}
    if '007_workspace_coordination.sql' not in versions:
        raise ValueError('A importação exige o esquema de agenda e permissões da etapa 007; nenhuma migração foi aplicada.')
    columns={r[1] for r in db.execute('PRAGMA table_info(itinerary_items)')}
    if not set(FIELDS).union({'seed_key','request_key','version'})<=columns:
        raise ValueError('Esquema de agenda incompatível; nenhuma alteração aplicada.')


def database_fingerprints(db):
    """Private hashes only: do not put sessions, finance, or user data in import reports."""
    result={}
    tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for table in tables:
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',table):raise ValueError('Nome de tabela inesperado.')
        rows=[list(row) for row in db.execute('SELECT * FROM "'+table+'"')]
        rows.sort(key=lambda row:json.dumps(row,sort_keys=True,default=str))
        result[table]={'count':len(rows),'sha256':digest(json.loads(json.dumps(rows,default=lambda value:{'blob':value.hex()} if isinstance(value,bytes) else str(value))))}
    return result


def row_data(db,row):
    data={field:row[field] for field in FIELDS}
    data['endereco_validado']=int(data['endereco_validado'])
    data['participantes']=[r[0] for r in db.execute('SELECT participant_id FROM itinerary_participants WHERE item_id=? ORDER BY participant_id',(row['id'],))]
    return data


def canonical_data(data):
    result={field:data[field] for field in FIELDS}
    result['endereco_validado']=int(result['endereco_validado'])
    result['participantes']=sorted(data.get('participantes',[]))
    return result


def _tokens(text):
    ignore={'a','ao','as','da','das','de','do','dos','e','em','na','no','o','os','para','visita','dia','missao','com','1','2'}
    return {w.replace('innovacion','inovacao') for w in normalized(text).split() if w not in ignore}


def _possible_duplicates(event,rows):
    wanted=_tokens(event.title)
    found=[]
    for row in rows:
        if row['status']=='cancelado' or row['categoria'] in ('turismo','descanso'):continue
        if (event.category=='alimentacao') != (row['categoria']=='alimentacao'):continue
        if row['data'] not in (None,event.day):continue
        existing=_tokens(row['titulo'])
        common=wanted&existing
        if normalized(row['titulo'])==normalized(event.title) or (len(common)>=2 and len(common)/max(1,min(len(wanted),len(existing)))>=.65):
            found.append({'id':row['id'],'title':row['titulo'],'day':row['data'],'version':row['version']})
    return found


def build_plan(db,path,mission,document,source_key,*,links=None,allow_source_updates=False):
    _schema(db)
    if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}',source_key):raise ValueError('Use uma chave de origem estável, com letras, números, ponto, hífen ou sublinhado.')
    links=links or {}
    rows=[dict(r) for r in db.execute('SELECT * FROM itinerary_items WHERE mission_id=? ORDER BY id',(mission.id,))]
    row_index={r['id']:r for r in rows};index={};anchors={}
    for row in rows:
        meta=decode(row['request_key'])
        if row['seed_key']:index[row['seed_key']]=row
        if meta:
            if meta['key'] in index and index[meta['key']]['id']!=row['id']:raise ImportConflict('Associação documental duplicada no banco; revise antes de continuar.')
            index[meta['key']]=row
            if meta.get('source_key')==source_key:
                anchor=re.sub(r':[^:]+$','',meta.get('locator',''))
                if anchor in anchors:raise ImportConflict('Âncora documental duplicada; revise a origem.')
                anchors[anchor]=row
    entries=[];seen=set()
    for event in document.events:
        if not mission.data_inicio.isoformat()<=event.day<=mission.data_fim.isoformat():
            raise ValueError('O documento contém uma data fora do período da missão selecionada.')
        key='official:'+digest([source_key,mission.codigo,event.identity()])
        if key not in index:
            # A renamed/rescheduled event in the same source cell is a change to review,
            # rather than an unrelated new record. Moving its cell retains the title/day key.
            anchored=anchors.get(re.sub(r':[^:]+$','',event.locator))
            if anchored:key=decode(anchored['request_key'])['key']
        if key in seen:raise ImportConflict('O documento gerou identificadores repetidos; revise a origem.')
        seen.add(key)
        data=validate_activity({'titulo':event.title,'descricao':event.description,'categoria':event.category,
            'status':'a_confirmar','origem':'agenda_oficial','data':event.day,'horario_inicio':event.start,
            'horario_fim':event.end,'local':event.location,'endereco':event.address,'participantes':[],
            'observacoes':'Importado de programação oficial. '+TIME_LABELS.get(event.time_kind,TIME_LABELS['missing'])+'. '+(
                'Janela sugerida pela grade: '+str(event.grid_start)+' a '+str(event.grid_end or 'término não informado')+'; não confirma duração. '
                if event.time_kind=='grid_window' else '')+('; '.join(event.warnings) if event.warnings else ''),
            'organizacao':'','link_externo':'','endereco_validado':False},mission)
        source_digest=digest({'data':canonical_data(data),'time_kind':event.time_kind,'grid_start':event.grid_start,'grid_end':event.grid_end})
        existing=index.get(key);action='new';reason='';matches=[]
        if existing:
            metadata=decode(existing['request_key'])
            if not metadata or metadata.get('baseline')!=digest(row_data(db,existing)) or metadata.get('version')!=existing['version']:
                action='conflict';reason='O registro mudou desde a última importação; nenhuma alteração automática.'
            elif metadata.get('source_digest')==source_digest:
                action='existing'
            elif metadata.get('mode')=='linked' or not allow_source_updates:
                action='conflict';reason='A origem foi alterada; requer revisão explícita antes de atualizar.'
            else:action='update'
        elif key in links:
            existing=row_index.get(int(links[key]))
            if not existing:raise ImportConflict('O vínculo solicitado não pertence à missão selecionada.')
            if existing['request_key'] is not None:raise ImportConflict('Não substituir uma chave de criação manual para associar um documento.')
            if any(e.get('existing_id')==existing['id'] for e in entries):raise ImportConflict('Um mesmo registro não pode receber dois compromissos documentais distintos.')
            action='link'
        else:
            matches=_possible_duplicates(event,rows)
            if matches:action='possible_duplicate';reason='Possível registro anterior; preserve e decida o vínculo antes de importar este compromisso.'
        if event.time_kind=='conflict':action='conflict';reason='Há contradição de horários no documento; revisar antes de escrever.'
        entries.append({'key':key,'action':action,'reason':reason,'existing_id':existing['id'] if existing else None,
            'existing_version':existing['version'] if existing else None,'possible_duplicates':matches,
            'existing_data':row_data(db,existing) if existing else None,
            'event':asdict(event),'data':data,'source_digest':source_digest,
            'missing_fields':[field for field in ('horario_inicio','horario_fim','local','endereco') if not data.get(field)]})
    unknown_links=set(links)-seen
    if unknown_links:raise ImportConflict('O plano de vínculos contém origens ausentes do documento.')
    overlaps=[]
    for n,entry in enumerate(entries):
        a=entry['data']
        for other in entries[n+1:]:
            b=other['data']
            if a['data']==b['data'] and all(x for x in (a['horario_inicio'],a['horario_fim'],b['horario_inicio'],b['horario_fim'])) and max(a['horario_inicio'],b['horario_inicio'])<min(a['horario_fim'],b['horario_fim']):
                overlaps.append({'day':a['data'],'keys':[entry['key'],other['key']],'note':'Atividades simultâneas preservadas; não são duplicações por si só.'})
    fingerprints=database_fingerprints(db)
    report={'database':str(path),'mission':mission.codigo,'timezone':mission.timezone,'source_key':source_key,
        'source':{'name':document.name,'sha256':document.sha256,'format':document.format},
        'entries':entries,'counts':dict(Counter(e['action'] for e in entries)),
        'events_found':len(entries),'free_windows':document.free_windows,'contexts':document.contexts,
        'simultaneous':overlaps,'database_fingerprints':fingerprints,'allow_source_updates':allow_source_updates}
    report['missing_source_items']=[{'id':r['id'],'key':decode(r['request_key'])['key']} for r in rows
        if decode(r['request_key']) and decode(r['request_key']).get('source_key')==source_key
        and decode(r['request_key'])['key'] not in seen]
    report['impact_sha256']=digest(report)
    return report


def preview(path,mission_code,document,source_key,**options):
    path=local_database(path)
    with readonly(path) as db:
        _schema(db)
        row=db.execute('SELECT * FROM missions WHERE codigo=?',(mission_code,)).fetchone()
        if row is None:raise ValueError('Missão inexistente.')
        mission=MissionRepository(path)._hydrate(db,row)
        return build_plan(db,path,mission,document,source_key,**options)


def _backup(path,destination,expected):
    destination=Path(destination).absolute()
    if destination.exists() or destination==path:raise ValueError('O backup deve usar um arquivo novo e separado.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with readonly(path) as source:
        if database_fingerprints(source)!=expected:raise ImportConflict('O banco mudou após o dry-run; gere uma nova prévia.')
        with closing(sqlite3.connect(destination,factory=connection_factory())) as target:
            configure_connection(target);source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or target.execute('PRAGMA foreign_key_check').fetchall():
                raise ImportConflict('O backup não passou na verificação de integridade.')
            if database_fingerprints(target)!=expected:raise ImportConflict('O backup não corresponde à prévia.')
    return destination


def apply_plan(path,document,source_key,approved,backup_path,*,links=None,allow_source_updates=False,allow_partial=False):
    path=local_database(path)
    current=preview(path,approved['mission'],document,source_key,links=links,allow_source_updates=allow_source_updates)
    if current['impact_sha256']!=approved.get('impact_sha256'):raise ImportConflict('A prévia ficou desatualizada; nenhuma escrita aplicada.')
    if any(e['action'] in ('conflict','possible_duplicate') for e in current['entries']) and not allow_partial:
        raise ImportConflict('Há conflitos ou possíveis duplicações; revise ou autorize explicitamente apenas os itens novos sem conflito.')
    actionable=[e for e in current['entries'] if e['action'] in ('new','update','link')]
    if not actionable:return {'created':0,'updated':0,'linked':0,'skipped':len(current['entries']),'backup':None}
    backup=_backup(path,backup_path,current['database_fingerprints'])
    mission_id=MissionRepository(path).get(current['mission']).id
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        if database_fingerprints(db)!=current['database_fingerprints']:raise ImportConflict('O banco mudou após o backup; nenhuma escrita aplicada.')
        repo=ItineraryRepository(path,_connection=db);counts=Counter()
        for entry in actionable:
            event=entry['event'];data=entry['data'];action=entry['action']
            if action=='link':item_id=entry['existing_id']
            else:
                item_id=repo.save(mission_id,data,
                    item_id=entry['existing_id'] if action=='update' else None,
                    version=entry['existing_version'] if action=='update' else None)
            row=dict(db.execute('SELECT * FROM itinerary_items WHERE id=?',(item_id,)).fetchone())
            metadata={'key':entry['key'],'baseline':digest(row_data(db,row)),'version':row['version'],
                'source_digest':entry['source_digest'],'source_key':source_key,'mode':'linked' if action=='link' else 'imported',
                'document':current['source'],'locator':event['locator'],'time_kind':event['time_kind'],
                'grid_start':event['grid_start'],'grid_end':event['grid_end'],
                'source_start':data['horario_inicio'],'source_end':data['horario_fim'],
                'location':event['location'],'address':event['address']}
            db.execute('UPDATE itinerary_items SET request_key=?,seed_key=COALESCE(seed_key,?) WHERE id=?',
                (encode(metadata),entry['key'],item_id))
            if action=='link':
                db.execute("INSERT INTO itinerary_history(item_id,acao,snapshot,actor_user_id) VALUES(?,'edicao',?,NULL)",
                    (item_id,json.dumps({'document_association':entry['key'],'activity_fields_preserved':True})))
            counts[action]+=1
        after=database_fingerprints(db)
        for table,fingerprint in current['database_fingerprints'].items():
            if table not in {'itinerary_items','itinerary_history','itinerary_participants'} and after.get(table)!=fingerprint:
                raise ImportConflict('Uma tabela fora da agenda mudou; importação revertida.')
    return {'created':counts['new'],'updated':counts['update'],'linked':counts['link'],
        'skipped':len(current['entries'])-len(actionable),'backup':str(backup)}
