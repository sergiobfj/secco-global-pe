"""Preflight sem rede, banco, provisionamento ou impressão de segredos."""
import json
from app.core.config import Settings
from app.core.workspace_access import WORKSPACE_DOMAIN

CALLBACK='http://127.0.0.1:8003/auth/google/callback'


def inspect_configuration(settings):
    pending=set(settings.auth_errors())
    if settings.app_env!='development': pending.add('APP_ENV')
    if settings.dev_no_auth: pending.add('DEV_NO_AUTH')
    if settings.google_workspace_domain!=WORKSPACE_DOMAIN: pending.add('GOOGLE_WORKSPACE_DOMAIN')
    if settings.google_redirect_uri!=CALLBACK: pending.add('GOOGLE_REDIRECT_URI')
    return {'pronto':not pending,'pendencias':sorted(pending),'contas_na_allowlist':len(settings.allowed_users),
        'dominio_autorizado_configurado':settings.google_workspace_domain==WORKSPACE_DOMAIN,
        'callback_local_verificado_configurado':settings.google_redirect_uri==CALLBACK,
        'escopos':['openid','email'],'login_real_validado':False}


def main():
    try: result=inspect_configuration(Settings.from_env())
    except (RuntimeError,ValueError,TypeError): result={'pronto':False,'erro':'Configuração inválida. Revise o arquivo local, sem divulgar seu conteúdo.'}
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['pronto'] else 1


if __name__=='__main__': raise SystemExit(main())
