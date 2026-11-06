"""Administração local explícita. Não migra, não chama Google ou altera subvenção."""
import argparse
import json
from app.core.config import Settings
from app.core.workspace_access import COORDINATOR_KEY,COORDINATOR_PREFIX,SECCO_ACCOUNTS,WORKSPACE_DOMAIN
from app.db.connection import connect
from app.repositories.auth import AuthRepository


def main():
    parser=argparse.ArgumentParser(description='Gerenciar acesso local do SECCO Global PE, em banco já migrado')
    parser.add_argument('action',choices=('sync','list','enable','disable','grant','revoke','default'))
    selector=parser.add_mutually_exclusive_group()
    selector.add_argument('--participant-id',type=int)
    selector.add_argument('--account',choices=(COORDINATOR_KEY,))
    parser.add_argument('--mission',choices=('portugal','argentina'))
    args=parser.parse_args()
    settings=Settings.from_env(); settings.validate()
    if not settings.auth_ready: parser.error('Configure OIDC, domínio e allowlist antes de gerenciar usuários.')
    if not settings.database_path.is_file(): parser.error('O banco existente precisa estar migrado. Nenhuma migração foi executada.')
    auth=AuthRepository(settings)
    with connect(settings.database_path) as db:
        if not db.execute("SELECT 1 FROM schema_migrations WHERE version='007_workspace_coordination.sql'").fetchone():
            parser.error('A migração 007 precisa de revisão e aplicação autorizada antes desta operação.')
    if args.action=='sync':
        auth.provision()
        print('Contas associadas por ação explícita. Identificadores Google permanecem pendentes até o login verificado.')
        return
    with connect(settings.database_path) as db:
        if args.action=='list':
            ids=[r[0] for r in db.execute('SELECT id FROM app_users')]
            ids += [COORDINATOR_PREFIX+str(r[0]) for r in db.execute('SELECT id FROM coordination_accounts')]
            for identifier in ids:
                user=auth.get_user(identifier)
                print(json.dumps({'id':user['id'],'participant_id':user['participant_id'],'nome':user['nome'],
                    'enabled':user['enabled'],'vinculado':user['google_sub'] is not None,
                    'perfil':'coordenacao' if user['is_coordinator'] else 'viajante',
                    'visao_principal':user['default_mission_code'] or 'consolidada'},ensure_ascii=False))
            return
        coord=args.account==COORDINATOR_KEY
        if coord:
            row=db.execute('SELECT id FROM coordination_accounts WHERE account_key=?',(COORDINATOR_KEY,)).fetchone()
            key=COORDINATOR_KEY; table='coordination_accounts'; sessions='coordination_sessions'
        else:
            row=db.execute('SELECT id FROM app_users WHERE participant_id=?',(args.participant_id,)).fetchone()
            key=args.participant_id; table='app_users'; sessions='user_sessions'
        if not row or key not in {key for key,email in settings.allowed_users}: parser.error('Informe uma conta já associada e presente na allowlist.')
        identifier=row['id']; user_id=COORDINATOR_PREFIX+str(identifier) if coord else identifier
        if args.action in ('enable','disable'):
            enabled=int(args.action=='enable')
            db.execute(f"UPDATE {table} SET enabled=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",(enabled,identifier))
            if not enabled: db.execute(f'UPDATE {sessions} SET revoked_at=? WHERE user_id=?',(auth.clock(),identifier))
        else:
            if coord: parser.error('Coordenação é somente consulta; não recebe edição ou missão de viajante.')
            mission=db.execute('SELECT id,codigo FROM missions WHERE codigo=?',(args.mission,)).fetchone()
            if not mission: parser.error('Informe --mission para esta operação.')
            if settings.google_workspace_domain==WORKSPACE_DOMAIN and args.action in ('grant','default') and mission['codigo']!=SECCO_ACCOUNTS[key][1]:
                parser.error('A política SECCO mantém edição e visão principal na missão autorizada.')
            if args.action=='default': db.execute('UPDATE app_users SET default_mission_id=? WHERE id=?',(mission['id'],identifier))
            else:
                db.execute('''INSERT INTO user_mission_permissions(user_id,mission_id,can_edit) VALUES(?,?,?)
                    ON CONFLICT(user_id,mission_id) DO UPDATE SET can_edit=excluded.can_edit''',(identifier,mission['id'],int(args.action=='grant')))
        auth._event(db,user_id,'local_operator_'+args.action+(':'+args.mission if args.mission else ''))
    print('Acesso atualizado localmente. O financiamento da subvenção permanece independente.')


if __name__=='__main__': main()
