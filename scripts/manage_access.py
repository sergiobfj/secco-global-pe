"""Administração local explícita. Não chama Google ou altera a subvenção."""
import argparse
import json
from app.core.config import Settings
from app.db.connection import connect
from app.db.migrate import migrate
from app.db.seed import seed
from app.repositories.auth import AuthRepository


def main():
    parser = argparse.ArgumentParser(description="Gerenciar acesso local do SECCO Global PE")
    parser.add_argument("action",choices=("sync","list","enable","disable","grant","revoke","default"))
    parser.add_argument("--participant-id",type=int)
    parser.add_argument("--mission",choices=("portugal","argentina"))
    args = parser.parse_args()
    settings = Settings.from_env()
    settings.validate()
    if not settings.auth_ready:
        parser.error("Configure OIDC, domínio e allowlist antes de gerenciar usuários.")
    migrate(settings.database_path)
    seed(settings.database_path)
    auth = AuthRepository(settings)
    auth.provision()
    if args.action=="sync":
        print("Allowlist associada aos participantes. O vínculo Google ocorre somente no login verificado.")
        return
    with connect(settings.database_path) as db:
        if args.action=="list":
            for row in db.execute("SELECT p.id,p.nome,u.enabled,u.google_sub IS NOT NULL AS vinculado,m.codigo AS missao_padrao FROM app_users u JOIN participants p ON p.id=u.participant_id JOIN missions m ON m.id=u.default_mission_id ORDER BY p.id"):
                print(json.dumps(dict(row),ensure_ascii=False))
            return
        user = db.execute("SELECT id FROM app_users WHERE participant_id=?",(args.participant_id,)).fetchone()
        if not user or args.participant_id not in {p for p,e in settings.allowed_users}:
            parser.error("Informe um participante já associado e presente na allowlist.")
        user_id = user["id"]
        if args.action in ("enable","disable"):
            enabled = int(args.action=="enable")
            db.execute("UPDATE app_users SET enabled=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",(enabled,user_id))
            if not enabled:
                db.execute("UPDATE user_sessions SET revoked_at=? WHERE user_id=?",(auth.clock(),user_id))
        else:
            mission = db.execute("SELECT id FROM missions WHERE codigo=?",(args.mission,)).fetchone()
            if not mission:
                parser.error("Informe --mission para esta operação.")
            if args.action=="default":
                db.execute("UPDATE app_users SET default_mission_id=? WHERE id=?",(mission["id"],user_id))
            else:
                db.execute("INSERT INTO user_mission_permissions(user_id,mission_id,can_edit) VALUES(?,?,?) ON CONFLICT(user_id,mission_id) DO UPDATE SET can_edit=excluded.can_edit",(user_id,mission["id"],int(args.action=="grant")))
        db.execute("INSERT INTO auth_events(user_id,event) VALUES(?,?)",(user_id,"local_operator_"+args.action+(":"+args.mission if args.mission else "")))
    print("Permissão atualizada localmente. O financiamento pela subvenção permanece independente.")


if __name__=="__main__":
    main()
