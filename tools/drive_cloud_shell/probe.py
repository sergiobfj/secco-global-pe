"""Pacote 07C portátil. Nenhuma operação real sem novo aceite vinculado ao pacote."""
import argparse
from contextlib import redirect_stdout
from datetime import datetime,timedelta,timezone
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import platform
import re
import secrets
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
STATE=ROOT
RESUME_ONLY=False
V2_MANIFEST='89ed1e3a19a658468cd74f9562baa0f4dd73be96a5a973a73d389118b89e62de'
sys.path.insert(0,str(ROOT))
from verify_package import verify
_PHASE='not_started'


def phase(name):
    global _PHASE
    _PHASE=name


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_new(path,data):
    from app.core.storage_paths import reject_links
    path=Path(path)
    reject_links(path)
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w',encoding='utf-8') as out:
        json.dump(data,out,indent=2,ensure_ascii=False)
        out.write('\n'); out.flush(); os.fsync(out.fileno())


def config_and_plan():
    from app.core.drive_config import DriveConfiguration
    from app.services.drive_supervised import mapping_digest,plan_digest
    from app.services.storage_contracts import StoredReceipt
    plan=read_json(ROOT/'plan.json')
    config=DriveConfiguration(folders_json=json.dumps(read_json(ROOT/'folders.json')))
    config.validate()
    items={m:StoredReceipt(**i) for m,i in plan['items'].items()}
    if mapping_digest(config)!=plan['mapping_sha256'] or plan_digest(items)!=plan['plan_sha256']:
        raise ValueError('vinculo_do_plano')
    for mission,item in items.items():
        content=(ROOT/'payload'/f'{mission}.png').read_bytes()
        if len(content)!=69 or hashlib.sha256(content).hexdigest()!=item.checksum:
            raise ValueError('integridade_do_png')
    return config,plan,items


def select_state(source):
    """Executar código v3 usando o MESMO journal/lock v2, sem bifurcar o estado."""
    global STATE,RESUME_ONLY
    from app.core.storage_paths import reject_links
    candidate=Path(source).absolute()
    reject_links(candidate)
    if candidate.resolve()==ROOT.resolve(): raise ValueError('origem_de_retomada_invalida')
    if verify(candidate,expected_format='secco-drive-cloud-shell-07c-v2')!=V2_MANIFEST:
        raise ValueError('manifesto_v2_nao_confere')
    for name in ('plan.json','folders.json','policy-contract.json','payload/argentina.png','payload/portugal.png'):
        if (candidate/name).read_bytes()!=(ROOT/name).read_bytes(): raise ValueError('vinculo_do_plano')
    STATE=candidate
    RESUME_ONLY=True


def authorization_path(relative):
    from app.core.storage_paths import reject_links
    if (not isinstance(relative,str) or not re.fullmatch(
            r'\.local/(?:approval\.json|authorizations/approval-[a-f0-9]{32}\.json)',relative)):
        raise ValueError('caminho_de_aprovacao_invalido')
    path=STATE/relative
    reject_links(path)
    return path


def has_authorization():
    return (STATE/'.local/approval.json').exists() or any((STATE/'.local/authorizations').glob('*'))


def initialize(*,require_existing=False):
    """Materializa o mesmo plano em schema novo de ensaio, nunca em banco operacional."""
    phase('prepare_imports')
    from app.core.test_database import TemporaryDatabase
    from app.db.connection import connect
    from app.services.drive_probe import ProbeArchiveLock,ProbeJournal
    from app.services.drive_supervised import plan_digest
    phase('prepare_plan')
    config,plan,items=config_and_plan()
    archive=STATE/'evidence/probe-state.zip'
    marker=STATE/'evidence/session.json'
    from app.core.storage_paths import reject_links
    reject_links(marker)
    phase('prepare_archive_lock')
    with ProbeArchiveLock(archive):
        if (require_existing or RESUME_ONLY) and (not archive.is_file() or not marker.is_file()):
            raise ValueError('retomada_exige_checkpoint_e_marcador')
        if not archive.exists() and marker.exists(): raise ValueError('journal_perdido_nao_reinicializar')
        if not archive.exists() and has_authorization():
            raise ValueError('aprovacao_existe_nao_reinicializar')
        phase('prepare_temporary_create')
        with TemporaryDatabase() as temporary:
            if archive.exists():
                phase('prepare_restore')
                journal=ProbeJournal.restore(archive,temporary.directory/'probe',config)
            else:
                phase('prepare_bootstrap')
                journal=ProbeJournal.create(temporary.directory/'probe',config)
                # A criação aleatória é apenas bootstrap local; nenhum de seus IDs é publicado.
                # Antes do checkpoint, substituímos pelo plano original aprovado, sem rede.
                run_id=re.fullmatch(r'secco-ensaio-([a-f0-9]{16})-argentina\.png',items['argentina'].official_name)[1]
                with connect(journal.database_path) as db:
                    db.execute('UPDATE probe_run SET run_id=?',(run_id,))
                    for mission,item in items.items():
                        from dataclasses import asdict
                        db.execute('UPDATE probe_items SET item=?,sync_key=? WHERE mission=?',
                            (json.dumps(asdict(item),sort_keys=True),item.object_key,mission))
                volume=read_json(journal.directory/'.volume.json')
                volume['run_id']=run_id
                (journal.directory/'.volume.json').write_text(json.dumps(volume),encoding='utf-8')
                journal.validate()
                phase('prepare_checkpoint')
                journal.checkpoint(archive)
                write_new(marker,{'plan_sha256':plan['plan_sha256'],'archive':'probe-state.zip'})
            if plan_digest(journal.plan())!=plan['plan_sha256']: raise ValueError('vinculo_do_plano')
            if marker.exists() and read_json(marker)!={'plan_sha256':plan['plan_sha256'],'archive':'probe-state.zip'}:
                raise ValueError('marcador_de_sessao_divergente')
            phase('prepare_report')
            report={'mode':'offline','python':platform.python_version(),'platform':sys.platform,
                'manifest_sha256':verify(),'mapping_sha256':plan['mapping_sha256'],
                'plan_sha256':plan['plan_sha256'],'files':2,'bytes_each':69,
                'items':[{k:r[k] for k in ('mission','remote_id','state','attempts')} for r in journal.rows()]}
            # Exercita lock/restore real do sistema atual; não falsifica kernel Linux em Windows.
            phase('prepare_lock_check')
            try:
                with ProbeArchiveLock(archive): pass
            except Exception as error:
                from app.services.storage_contracts import DriveError
                if not isinstance(error,DriveError) or error.code!='ensaio_em_uso': raise
            else: raise ValueError('lock_nao_exclusivo')
            phase('prepare_temporary_cleanup')
        phase('prepare_archive_unlock')
    phase('prepare_offline_report_write')
    if not (STATE/'evidence/offline-check.json').exists(): write_new(STATE/'evidence/offline-check.json',report)
    return report


def inspect_backup(path):
    phase('inspect_backup_imports')
    from app.core.test_database import TemporaryDatabase
    from app.services.drive_probe import ProbeJournal
    from app.services.drive_supervised import plan_digest
    config,plan,_=config_and_plan()
    phase('inspect_backup_restore')
    with TemporaryDatabase() as temporary:
        journal=ProbeJournal.restore(Path(path).absolute(),temporary.directory/'inspection',config)
        if plan_digest(journal.plan())!=plan['plan_sha256']: raise ValueError('vinculo_do_plano')
        rows=[{key:r[key] for key in ('mission','remote_id','state','attempts')} for r in journal.rows()]
        safe=pristine_journal(journal)
        result={'mode':'offline_inspection','read_only_archive':True,'items':rows,
            'plan_sha256':plan['plan_sha256'],'safe_to_prepare_fresh_copy':safe}
        phase('inspect_backup_temporary_cleanup')
    return result


def policy_digest(data):
    canonical={m:sorted(v) for m,v in data.items()}
    return hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def install_policy():
    import app.core.drive_config as config
    from app.core.storage_paths import reject_links
    reject_links(STATE/'.local/access-policy.json')
    data=read_json(STATE/'.local/access-policy.json')
    contract=read_json(ROOT/'policy-contract.json')
    if (set(data)!= {'argentina','portugal'} or any(not isinstance(v,list) or len(v)!=3 or len(set(v))!=3 for v in data.values())
            or policy_digest(data)!=contract['policy_sha256']): raise ValueError('politica_nao_confere')
    # O mesmo objeto importado pelo adaptador recebe a política conferida; sem aliases.
    config.READERS.clear()
    config.READERS.update({m:frozenset(v) for m,v in data.items()})


def configure_policy():
    from app.core.drive_config import SERVICE_ACCOUNT
    data={}
    for mission in ('argentina','portugal'):
        emails=[input(f'{mission}: email do membro autorizado {i}: ').strip().casefold() for i in (1,2)]
        data[mission]=emails+[SERVICE_ACCOUNT]
    if policy_digest(data)!=read_json(ROOT/'policy-contract.json')['policy_sha256']:
        raise ValueError('politica_nao_confere')
    write_new(STATE/'.local/access-policy.json',data)
    return {'policy':'verified','personal_data_stays_local':True}


def journal_identity(journal):
    from app.db.connection import connect
    with connect(journal.database_path) as db:
        data=[dict(row) for row in db.execute('SELECT * FROM probe_run ORDER BY run_id')]
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def pristine_journal(journal):
    from app.db.connection import connect
    rows=journal.rows()
    with connect(journal.database_path) as db:
        events=db.execute('SELECT COUNT(*) FROM probe_events').fetchone()[0]
    return (events==0 and len(rows)==2 and all(row['remote_id'] is None and row['attempts']==0
        and row['state']=='aguardando' and row['ever_verified']==0 and row['error_code'] is None for row in rows))


def authorization_proof(config,plan):
    from app.core.test_database import TemporaryDatabase
    from app.services.drive_probe import ProbeJournal
    from app.services.drive_supervised import plan_digest
    with TemporaryDatabase() as temporary:
        journal=ProbeJournal.restore(STATE/'evidence/probe-state.zip',temporary.directory/'authorization',config)
        if plan_digest(journal.plan())!=plan['plan_sha256']: raise ValueError('vinculo_do_plano')
        if not pristine_journal(journal):
            raise ValueError('atividade_remota_possivel_revisao_obrigatoria')
        return journal_identity(journal)


def check_previous(relative,config,plan):
    from dataclasses import replace
    from app.services.drive_supervised import ProbeApproval
    path=authorization_path(relative)
    data=read_json(path)
    expiry=datetime.fromisoformat(data['expires_at'].replace('Z','+00:00'))
    if expiry.tzinfo is None: raise ValueError('validade_sem_fuso')
    approval=ProbeApproval(data['reference'],data['operator_account'],expiry.timestamp(),data['mapping_sha256'],
        tuple(data['scopes']),data['approved'],data['synthetic_only'],data['backup_verified'],data['cleanup'],data['plan_sha256'])
    # Validar contrato histórico sem reutilizar seu prazo nem sua autorização.
    replace(approval,expires_at=(datetime.now(timezone.utc)+timedelta(minutes=5)).timestamp()).validate(config)
    if (data['plan_sha256']!=plan['plan_sha256'] or data.get('environment')!='google-cloud-shell'
            or data.get('package_manifest_sha256') not in (V2_MANIFEST,verify())
            or data.get('policy_sha256')!=read_json(ROOT/'policy-contract.json')['policy_sha256']):
        raise ValueError('vinculo_da_aprovacao_anterior')
    return hashlib.sha256(path.read_bytes()).hexdigest(),data.get('journal_identity_sha256')


def check_renewal(args):
    initialize(require_existing=True)
    phase('renewal_check_policy')
    install_policy()
    from app.services.drive_probe import ProbeArchiveLock
    config,plan,_=config_and_plan()
    with ProbeArchiveLock(STATE/'evidence/probe-state.zip'):
        phase('renewal_check_previous')
        if not args.previous_approval: raise ValueError('selecione_aprovacao_anterior')
        previous,previous_identity=check_previous(args.previous_approval,config,plan)
        phase('renewal_check_journal')
        identity=authorization_proof(config,plan)
        if previous_identity is not None and previous_identity!=identity:
            raise ValueError('identidade_do_journal_divergente')
        return {'renewal':'eligible','execution_started':False,'authorization_created':False,
            'manifest_sha256':verify(),'plan_sha256':plan['plan_sha256'],'mapping_sha256':plan['mapping_sha256'],
            'journal_identity_sha256':identity,'previous_approval_sha256':previous,
            'checkpoint_sha256':hashlib.sha256((STATE/'evidence/probe-state.zip').read_bytes()).hexdigest()}


def authorize(args,*,renew=False):
    if sys.platform!='linux': raise ValueError('autorizacao_exige_linux_cloud_shell')
    if RESUME_ONLY and not renew: raise ValueError('retomada_exige_renovacao_explicita')
    initialize(require_existing=renew)
    phase('authorization_policy')
    install_policy()
    if not args.reference or not args.operator or not 1<=args.minutes<=60:
        raise ValueError('nova_aprovacao_necessaria')
    from app.services.drive_probe import ProbeArchiveLock
    from app.services.drive_supervised import ProbeApproval,SCOPE_FILE,SCOPE_METADATA
    config,plan,_=config_and_plan()
    from dataclasses import asdict
    with ProbeArchiveLock(STATE/'evidence/probe-state.zip'):
        phase('authorization_existing_state')
        if not renew and has_authorization(): raise ValueError('aprovacao_existente_use_renovacao')
        previous=previous_identity=None
        if renew:
            if not args.previous_approval: raise ValueError('selecione_aprovacao_anterior')
            previous,previous_identity=check_previous(args.previous_approval,config,plan)
        phase('authorization_journal_proof')
        identity=authorization_proof(config,plan)
        if previous_identity is not None and previous_identity!=identity:
            raise ValueError('identidade_do_journal_divergente')
        phase('authorization_confirmation')
        answer=input('Somente apos novo aceite explicito: digite AUTORIZO CLOUD SHELL 07C: ')
        if answer!='AUTORIZO CLOUD SHELL 07C': raise ValueError('nova_aprovacao_necessaria')
        expiry=datetime.now(timezone.utc)+timedelta(minutes=args.minutes)
        approval=ProbeApproval(args.reference,args.operator,expiry.timestamp(),plan['mapping_sha256'],
            (SCOPE_FILE,SCOPE_METADATA),True,True,True,plan_sha256=plan['plan_sha256'])
        approval.validate(config)
        data=asdict(approval)
        data['expires_at']=expiry.isoformat()
        data['environment']='google-cloud-shell'
        data['package_manifest_sha256']=verify()
        data['policy_sha256']=read_json(ROOT/'policy-contract.json')['policy_sha256']
        data['journal_identity_sha256']=identity
        data['checkpoint_sha256_at_authorization']=hashlib.sha256((STATE/'evidence/probe-state.zip').read_bytes()).hexdigest()
        relative='.local/approval.json'
        if renew:
            relative='.local/authorizations/approval-'+secrets.token_hex(16)+'.json'
            data['previous_approval_file']=args.previous_approval
            data['previous_approval_sha256']=previous
        phase('authorization_record_write')
        write_new(authorization_path(relative),data)
    return {'authorization':'recorded','authorization_file':relative,'expires_at':data['expires_at'],'execution_started':False}


def execute(args):
    if sys.platform!='linux' or not args.confirm_write: raise ValueError('execucao_exige_cloud_shell_e_aceite')
    digest=verify()
    install_policy()
    phase('execution_approval_read')
    if not args.approval_file: raise ValueError('selecione_aprovacao_explicita')
    raw=read_json(authorization_path(args.approval_file))
    if (raw.get('environment')!='google-cloud-shell' or raw.get('package_manifest_sha256')!=digest
            or raw.get('policy_sha256')!=read_json(ROOT/'policy-contract.json')['policy_sha256']):
        raise ValueError('vinculo_da_aprovacao')
    from app.services.drive_supervised import GcloudSourceCredentials,ImpersonatedProbeCredentials,SupervisedProbeAdapter,ProbeApproval,plan_digest
    from app.services.drive_probe import ProbeArchiveLock,ProbeJournal
    from app.core.test_database import TemporaryDatabase
    config,plan,_=config_and_plan()
    expiry=datetime.fromisoformat(raw['expires_at'].replace('Z','+00:00'))
    if expiry.tzinfo is None: raise ValueError('validade_sem_fuso')
    approval=ProbeApproval(raw['reference'],raw['operator_account'],expiry.timestamp(),raw['mapping_sha256'],
        tuple(raw['scopes']),raw['approved'],raw['synthetic_only'],raw['backup_verified'],raw['cleanup'],raw['plan_sha256'])
    approval.validate(config)
    if raw.get('previous_approval_file'):
        if hashlib.sha256(authorization_path(raw['previous_approval_file']).read_bytes()).hexdigest()!=raw['previous_approval_sha256']:
            raise ValueError('aprovacao_anterior_alterada')
    archive=STATE/'evidence/probe-state.zip'
    if not archive.exists(): raise ValueError('journal_ausente_nao_reinicializar')
    observations={}
    class EvidenceAdapter(SupervisedProbeAdapter):
        def _request(self,*a,**k):
            data=super()._request(*a,**k)
            if a[0]=='GET' and data and data.get('id') in self.probe_transport.remote_ids.values():
                self.latest={key:data.get(key) for key in ('id','name','mimeType','parents','driveId','size','sha256Checksum','trashed')}
            return data
        def verify(self,item,**kwargs):
            confirmed=super().verify(item,**kwargs)
            if confirmed: observations[item.mission_code]=self.latest
            return confirmed
    credentials=adapter=None
    with ProbeArchiveLock(archive),TemporaryDatabase() as temporary:
        phase('execution_restore')
        marker=STATE/'evidence/session.json'
        from app.core.storage_paths import reject_links
        reject_links(marker)
        if not marker.is_file(): raise ValueError('retomada_exige_checkpoint_e_marcador')
        if read_json(marker)!={'plan_sha256':plan['plan_sha256'],'archive':'probe-state.zip'}:
            raise ValueError('marcador_de_sessao_divergente')
        journal=ProbeJournal.restore(archive,temporary.directory/'probe',config)
        if plan_digest(journal.plan())!=approval.plan_sha256: raise ValueError('vinculo_do_plano')
        if journal_identity(journal)!=raw.get('journal_identity_sha256'): raise ValueError('identidade_do_journal_divergente')
        try:
            phase('execution_credentials')
            credentials=ImpersonatedProbeCredentials(GcloudSourceCredentials(approval.operator_account),approval,config)
            credentials.access_token()
            phase('execution_transport')
            adapter=EvidenceAdapter(config,credentials,approval,journal.plan(),journal.contents())
            phase('execution_journal_run')
            ok=journal.run(adapter,archive)
            rows=journal.rows()
            report={'result':'verified' if ok else 'stopped','manifest_sha256':digest,
                'plan_sha256':plan['plan_sha256'],'mapping_sha256':plan['mapping_sha256'],
                'known_remote_file_count':len({item['id'] for item in observations.values()}),
                'reserved_ids_count':len({r['remote_id'] for r in rows if r['remote_id']}),
                'remote_count_complete':ok,
                'verified_count':sum(r['state']=='verificado' for r in rows),'remote_checks':observations,
                'items':[{key:r[key] for key in ('mission','remote_id','state','attempts','error_code')} for r in rows]}
        finally:
            if adapter: adapter.close()
            if credentials: credentials.close()
    phase('execution_report_write')
    write_new(STATE/'evidence'/('result-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(3)+'.json'),report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description='Ensaio 07C Cloud Shell; verificar/preparar e offline por padrao.')
    parser.add_argument('action',choices=('verify','prepare','inspect-backup','configure-policy','authorize','check-renewal','renew-authorization','execute','evidence'))
    parser.add_argument('--resume-from',help='Usar journal/lock e politica existentes do pacote v2 conhecido, sem copia ou bootstrap.')
    parser.add_argument('--previous-approval',help='Registro historico preservado para renovacao explicita.')
    parser.add_argument('--approval-file',help='Registro exato da NOVA aprovacao selecionada para execute.')
    parser.add_argument('--archive',help='Somente leitura para inspect-backup; nunca altera o arquivo indicado.')
    parser.add_argument('--operator')
    parser.add_argument('--reference')
    parser.add_argument('--minutes',type=int,default=30)
    parser.add_argument('--confirm-write',action='store_true')
    args=parser.parse_args(argv)
    try:
        phase('package_verification')
        manifest=verify()
        if args.resume_from:
            phase('resume_source_verification')
            select_state(args.resume_from)
        phase(args.action)
        if args.action=='verify': result={'package':'verified','manifest_sha256':manifest}
        elif args.action=='prepare': result=initialize()
        elif args.action=='inspect-backup':
            if not args.archive: raise ValueError('caminho_do_backup_necessario')
            result=inspect_backup(args.archive)
        elif args.action=='configure-policy': result=configure_policy()
        elif args.action=='authorize': result=authorize(args)
        elif args.action=='check-renewal': result=check_renewal(args)
        elif args.action=='renew-authorization': result=authorize(args,renew=True)
        elif args.action=='execute': result=execute(args)
        else:
            import zipfile
            from datetime import datetime as dt
            (STATE/'exports').mkdir(mode=0o700,exist_ok=True)
            target=STATE/'exports'/('evidence-'+dt.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.zip')
            with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED) as output:
                for path in (STATE/'evidence').glob('*'):
                    if path.is_file() and path.suffix in ('.json','.zip'): output.write(path,'evidence/'+path.name)
                for name in ('MANIFEST.json','plan.json','folders.json','policy-contract.json'):
                    output.write(ROOT/name,name)
            result={'evidence_archive':'exports/'+target.name,'credentials_included':False}
        print(json.dumps(result,ensure_ascii=False))
        return 0 if result.get('result')!='stopped' else 2
    except Exception as error:
        # Nunca imprimir erro arbitrário, traceback, stdout SDK ou ACL contendo identidades.
        code=getattr(error,'code',None)
        if code is None and isinstance(error,ValueError) and re.fullmatch('[a-z0-9_]+',str(error)):
            code=str(error)
        specific={'UnsafeTestDatabase':'isolamento_temporario','FileNotFoundError':'arquivo_ausente',
            'PermissionError':'permissao_local','FileExistsError':'registro_local_ja_existe',
            'ModuleNotFoundError':'dependencia_ausente','ImportError':'dependencia_ausente'}
        safe={'result':'stopped','code':code or specific.get(type(error).__name__,'configuracao_ou_backup'),
            'phase':_PHASE,'error_type':type(error).__name__}
        if isinstance(error,OSError): safe['errno']=error.errno
        print(json.dumps(safe))
        return 2


if __name__=='__main__': raise SystemExit(main())
