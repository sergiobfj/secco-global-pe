"""Explicit local operator tool. Never loads .env, starts the app, or runs migrations."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from app.services.itinerary_documents import read_document
from app.services.itinerary_import import preview, apply_plan


def private_path(value):
    path=Path(value).resolve()
    if path.is_relative_to(ROOT):
        raise ValueError('Documentos, perfis, relatórios e backups devem ficar fora do repositório público.')
    return path


def main(argv=None):
    parser=argparse.ArgumentParser(description='Importação local de agenda oficial; dry-run por padrão.')
    parser.add_argument('--input',required=True)
    parser.add_argument('--database',required=True)
    parser.add_argument('--mission',required=True)
    parser.add_argument('--source-key',required=True,help='Chave estável da edição documental; reutilize nas próximas execuções.')
    parser.add_argument('--year',type=int,help='Ano da missão, obrigatório para PDF sem ano.')
    parser.add_argument('--profile',help='JSON privado opcional: context_labels (cabeçalhos de cidade) e links (chave documental: ID revisado).')
    parser.add_argument('--report',required=True,help='Novo arquivo JSON privado de resultado.')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--approved-plan',help='Dry-run privado revisado, exatamente igual ao impacto atual.')
    parser.add_argument('--backup',help='Novo arquivo de backup privado; obrigatório antes de escrever.')
    parser.add_argument('--owner-authorized-local',action='store_true',help='Confirma que o operador possui autorização sobre este banco LOCAL.')
    parser.add_argument('--allow-partial',action='store_true',help='Após decisão explícita, importar só novos/vínculos revisados, mantendo conflitos pendentes.')
    parser.add_argument('--allow-source-updates',action='store_true',help='Atualizar apenas importados que continuam idênticos à versão anterior, após revisão da prévia.')
    args=parser.parse_args(argv)
    try:
        source=private_path(args.input);report_path=private_path(args.report)
        if report_path.exists():raise ValueError('O relatório deve ser um arquivo novo para preservar evidências anteriores.')
        profile=json.loads(private_path(args.profile).read_text(encoding='utf-8')) if args.profile else {}
        if set(profile)-{'context_labels','links'}:raise ValueError('Campos de perfil desconhecidos.')
        document=read_document(source,year=args.year,context_labels=profile.get('context_labels',[]))
        options={'links':profile.get('links',{}),'allow_source_updates':args.allow_source_updates}
        report=preview(args.database,args.mission,document,args.source_key,**options)
        if args.apply:
            if not all((args.approved_plan,args.backup,args.owner_authorized_local)):
                raise ValueError('Aplicação exige dry-run revisado, backup novo e autorização explícita do operador local.')
            approved=json.loads(private_path(args.approved_plan).read_text(encoding='utf-8'))
            if approved['impact_sha256']!=report['impact_sha256']:
                raise ValueError('A prévia ou o documento mudou; execute outro dry-run antes de escrever.')
            report['result']=apply_plan(args.database,document,args.source_key,approved,private_path(args.backup),
                allow_partial=args.allow_partial,**options)
        elif any((args.backup,args.approved_plan,args.owner_authorized_local,args.allow_partial)):
            raise ValueError('Opções de escrita exigem --apply; o dry-run não escreve no banco.')
        report_path.parent.mkdir(parents=True,exist_ok=True)
        # Exclusive creation prevents accidental overwrite of private review material.
        with report_path.open('x',encoding='utf-8') as handle:
            json.dump(report,handle,ensure_ascii=False,indent=2)
        print(json.dumps({'mode':'apply' if args.apply else 'dry-run','events_found':report['events_found'],
            'counts':report['counts'],'result':report.get('result'),'private_report':str(report_path)},ensure_ascii=False))
        return 0
    except (ValueError,OSError,KeyError) as error:
        parser.exit(2,str(error)+'\n')


if __name__=='__main__':raise SystemExit(main())
