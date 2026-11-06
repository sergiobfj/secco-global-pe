"""Ensaio separado: padrão offline; execução real exige aprovação e flags explícitas."""
import argparse
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path

from app.core.drive_config import DriveConfiguration
from app.core.test_database import TemporaryDatabase
from app.services.drive_probe import ProbeArchiveLock, ProbeJournal
from app.services.drive_supervised import (
    GcloudSourceCredentials, ImpersonatedProbeCredentials, ProbeApproval,
    SupervisedProbeAdapter, mapping_digest, plan_digest,
)
from app.services.storage_contracts import DriveError


def load_configuration(path):
    # Somente mapa explícito. Não lê .env, ADC, Settings ou banco operacional.
    mapping=json.loads(Path(path).read_text(encoding='utf-8'))
    config=DriveConfiguration(folders_json=json.dumps(mapping))
    config.validate()
    return config


def load_approval(path, configuration):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    expiry=datetime.fromisoformat(data['expires_at'].replace('Z','+00:00'))
    if expiry.tzinfo is None: raise DriveError('autorizacao')
    approval=ProbeApproval(reference=data['reference'],operator_account=data['operator_account'],
        expires_at=expiry.timestamp(),
        mapping_sha256=data['mapping_sha256'],scopes=tuple(data['scopes']),approved=data['approved'],
        synthetic_only=data['synthetic_only'],backup_verified=data['backup_verified'],cleanup=data['cleanup'],
        plan_sha256=data['plan_sha256'])
    approval.validate(configuration)
    return approval


def main(argv=None):
    parser=argparse.ArgumentParser(description='07C: prepara dois PNGs sintéticos; offline por padrão.')
    parser.add_argument('--mapping',required=True)
    parser.add_argument('--archive',required=True,help='ZIP de recuperação deste ensaio; sem tokens.')
    parser.add_argument('--resume',action='store_true',help='Retomar o mesmo ZIP; não cria outro run_id.')
    parser.add_argument('--execute-authorized',action='store_true')
    parser.add_argument('--approval',help='Declaração de aprovação do responsável; sem credenciais.')
    args=parser.parse_args(argv)
    credentials=adapter=None
    try:
        configuration=load_configuration(args.mapping)
        # O teste de autorização precede rede, obtenção de token ou criação do journal.
        approval=load_approval(args.approval,configuration) if args.execute_authorized and args.approval else None
        if args.execute_authorized and (approval is None or not args.resume): raise DriveError('autorizacao')
        archive=Path(args.archive).absolute()
        if not args.resume and archive.exists(): raise DriveError('arquivo_existente_usar_resume')
        with ProbeArchiveLock(archive), TemporaryDatabase() as lease:
            if not args.resume and archive.exists(): raise DriveError('arquivo_existente_usar_resume')
            directory=lease.directory/'probe'
            journal=(ProbeJournal.restore(archive,directory,configuration) if args.resume
                     else ProbeJournal.create(directory,configuration))
            if approval and approval.plan_sha256 != plan_digest(journal.plan()): raise DriveError('autorizacao')
            journal.checkpoint(archive)
            if not args.execute_authorized:
                print(json.dumps({'mode':'offline','mapping_sha256':mapping_digest(configuration),
                    'plan_sha256':plan_digest(journal.plan()),
                    'items':{m:asdict(i) for m,i in journal.plan().items()},'archive':str(archive)},ensure_ascii=False))
                return 0
            credentials=ImpersonatedProbeCredentials(GcloudSourceCredentials(approval.operator_account),approval,configuration)
            credentials.access_token()  # Falhas IAM controladas são informadas antes do adaptador Drive.
            adapter=SupervisedProbeAdapter(configuration,credentials,approval,journal.plan(),journal.contents())
            successful=journal.run(adapter,archive)
            print(json.dumps({'mode':'supervised','result':'verificado' if successful else 'interrompido',
                'items':[{k:r[k] for k in ('mission','remote_id','state','error_code','attempts')}
                         for r in journal.rows()]},ensure_ascii=False))
            return 0 if successful else 2
    except (DriveError,OSError,ValueError,KeyError,TypeError) as error:
        print(json.dumps({'result':'interrompido','code':error.code if isinstance(error,DriveError) else 'configuracao_ou_backup'}))
        return 2
    finally:
        if adapter: adapter.close()
        if credentials: credentials.close()


if __name__=='__main__':
    raise SystemExit(main())
