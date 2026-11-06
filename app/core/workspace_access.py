"""Política SECCO confirmada pelo responsável. Não cadastra contas ou participantes."""
WORKSPACE_DOMAIN='secco.example'
COORDINATOR_KEY='coordenacao_secco'
COORDINATOR_PREFIX='coord:'
SECCO_ACCOUNTS={
 3:('tiago@secco.example','argentina','Tiago Prado'),
 4:('bruno@secco.example','argentina','Bruno de Castro'),
 1:('hugo@secco.example','portugal','Hugo Mendes'),
 2:('alan@secco.example','portugal','Alan Renato'),
 COORDINATOR_KEY:('marcos@secco.example',None,'Marcos'),
}


def account_key(user):
    return COORDINATOR_KEY if user.get('is_coordinator') else user['participant_id']


def configured_home(settings,user):
    if user.get('is_coordinator'): return '/consolidado'
    if settings.google_workspace_domain==WORKSPACE_DOMAIN:
        policy=SECCO_ACCOUNTS.get(user['participant_id'])
        if policy and policy[0]==user['email_allowlist']: return '/missoes/'+policy[1]
    return '/missoes/'+user['default_mission_code']
