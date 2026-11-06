# Ativação controlada do Google Workspace SECCO

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


> **Distribuição pública:** nomes, e-mails, domínio Google Workspace, IDs de Drive/pastas e identificadores Google Cloud deste documento são fictícios. Resultados e decisões descritos referem-se ao projeto operacional.


> Atualização local da etapa 06.1: as sete migrações já estão aplicadas e os cinco perfis já foram provisionados na ativação autorizada anterior. Não repetir scripts.init_db, migrações ou sync para testar esta correção. As instruções de preparação abaixo são históricas; o procedimento atual de reinício e nova tentativa está em [validação da etapa 06.1](validacao-etapa061.md). A autenticação Google real continua pendente de confirmação manual.

Estado: **implementação pronta, ativação real pendente**. Esta documentação não declara login Google real validado.

## Endereço local verificado

Em 02/11/2026, consultas somente de leitura a /health confirmaram respostas locais nas portas 8000, 8001, 8002 e 8003. O endpoint existente no código é /auth/google/callback. O endereço inicial desta etapa é:

    http://127.0.0.1:8003/auth/google/callback

A instância em 8003 ainda é um processo anterior. Nenhum servidor foi iniciado, encerrado ou atualizado nesta rodada. Registrar a URI não atualiza esse processo. Use exatamente 127.0.0.1 e a porta 8003 durante o primeiro ensaio; localhost é outra origem e não deve ser alternado no mesmo fluxo.

## Perfis autorizados

| Conta | Perfil | Visão principal | Edição |
| --- | --- | --- | --- |
| tiago@secco.example | Tiago Prado, viajante | Hoje Argentina | Argentina |
| bruno@secco.example | Bruno de Castro, viajante | Hoje Argentina | Argentina |
| hugo@secco.example | Hugo Mendes, viajante | Hoje Portugal | Portugal |
| alan@secco.example | Alan Renato, viajante | Hoje Portugal | Portugal |
| marcos@secco.example | Coordenação SECCO | Consolidada | Nenhuma |

Todos consultam agenda, Diário e metas das duas missões. Marcos não é participante, bolsista ou responsável por despesa por padrão. Não recebe acesso a comprovantes privados. As contas dos viajantes mantêm seus participantes existentes; Hugo e Bruno continuam custeados, Tiago e Alan continuam fora da subvenção.

A visão principal é política do servidor, não parâmetro do navegador. Trocar de missão para consulta não a altera. O perfil SECCO recusa concessões de edição fora da missão principal e a coordenação não pode ser promovida pelo campo role ou por preferências do cliente.

## 1. Configurar o cliente OAuth manualmente

O responsável autorizado deve acessar o Google Cloud e selecionar o projeto da organização SECCO. Em Google Auth Platform, revisar Branding/identificação e Audience. Use audiência interna quando o projeto estiver vinculado à organização Workspace autorizada. Se essa opção não estiver disponível, alinhe o projeto e as políticas com o administrador; não amplie a audiência para contornar o bloqueio.

Em Clients, criar ou selecionar um cliente do tipo Aplicação Web e registrar a URI exata acima em Authorized redirect URIs. Este fluxo é Authorization Code no backend; não usa o SDK JavaScript, então não precisa inventar origens JavaScript ou callbacks adicionais. Se uma política administrativa impedir o cliente, a aprovação deve ser feita pelo responsável no Google Workspace.

Solicitar somente openid e email. Não adicionar Drive, refresh token, acesso offline ou outros escopos. Copiar o client ID e o client secret diretamente para o ambiente local privado, sem colá-los em chat, terminal de saída, relatório ou repositório.

Fontes oficiais: [criar credenciais Web](https://developers.google.com/workspace/guides/create-credentials), [OAuth para aplicações de servidor](https://developers.google.com/identity/protocols/oauth2/web-server), [OpenID Connect do Google](https://developers.google.com/identity/openid-connect/openid-connect).

## 2. Preencher o ambiente local

Não copie a .env.example por cima do .env existente. Revise-o no editor local autorizado. Nesta entrega apenas .env.example foi atualizado com o domínio/e-mails (fictícios nesta distribuição); o .env operacional foi preservado.

| Variável | Configuração necessária |
| --- | --- |
| APP_ENV | development |
| DEV_NO_AUTH | false |
| GOOGLE_CLIENT_ID | ID do cliente Web real autorizado; não foi gerado nesta etapa |
| GOOGLE_CLIENT_SECRET | Segredo real do cliente, somente no backend |
| GOOGLE_REDIRECT_URI | http://127.0.0.1:8003/auth/google/callback |
| GOOGLE_WORKSPACE_DOMAIN | secco.example |
| ALLOWED_USERS | JSON explícito abaixo |
| SESSION_SECRET | Segredo aleatório persistente de pelo menos 32 bytes, gerado e guardado localmente sem impressão |

Allowlist com IDs dos participantes existentes, conferidos por consulta somente de leitura (e-mails fictícios nesta distribuição):

    ALLOWED_USERS=[{"participant_id":3,"email":"tiago@secco.example"},{"participant_id":4,"email":"bruno@secco.example"},{"participant_id":1,"email":"hugo@secco.example"},{"participant_id":2,"email":"alan@secco.example"},{"account":"coordenacao_secco","email":"marcos@secco.example"}]

A entrada de coordenação usa account e não participant_id. Não adicione Marcos à tabela participants ou mission_participants. O parser recusa duplicidades e a política do domínio confirmado não aceita combinações arbitrárias de conta e participante. Remover uma entrada pode reduzir o acesso; não amplia a lista autorizada.

Gere SESSION_SECRET usando gerenciador de senhas ou rotina local que grave diretamente no armazenamento privado. Não o imprima no terminal nem envie seu valor em mensagens. Mantenha-o estável entre reinicializações; sua troca invalida sessões.

Mantenha RECEIPTS_SYNTHETIC_ENABLED=false para o primeiro ensaio de login. Esta etapa não habilita comprovantes reais, mesmo depois de um login manual bem-sucedido.

## 3. Validar configuração sem expor segredos

Na raiz do projeto:

    .venv/Scripts/python.exe -B -m scripts.check_auth_config

O comando não abre banco, não migra, não provisiona usuários e não chama o Google. Mostra somente prontidão, nomes das variáveis pendentes, quantidade de contas, confirmação do domínio/callback e escopos. login_real_validado permanece false, pois esse script não autentica ninguém. Configuração malformada não é reproduzida no erro.

Nesta execução, o resultado foi pendente para ALLOWED_USERS, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, GOOGLE_WORKSPACE_DOMAIN e SESSION_SECRET no ambiente operacional. Nenhum valor foi inventado para contornar isso.

## 4. Revisar e autorizar migrações antes da ativação

O banco operacional foi inspecionado de forma imutável e somente de leitura. Contém as migrações 001 a 004. As versões 005, 006 e 007 ainda não foram aplicadas nele.

Antes de usar a versão nova com esse banco: revisar as três migrações pendentes, obter autorização, fazer backup consistente e só então executá-las. Nenhum comando de migração operacional foi executado nesta entrega. A inicialização normal aplica migrações pendentes, portanto não inicie a versão nova contra o banco operacional antes dessa revisão/autorização.

Após a autorização, o responsável poderá executar a inicialização existente:

    .venv/Scripts/python.exe -m scripts.init_db

Ela não cria usuários de acesso automaticamente. A migração 007 é aditiva e mantém os participantes e vínculos financeiros. Não há checkpoint Git nesta pasta; prepare o backup antes de qualquer operação autorizada.

## 5. Provisionar explicitamente os cinco acessos

Somente depois de configuração autorizada e banco migrado:

    .venv/Scripts/python.exe -m scripts.manage_access sync
    .venv/Scripts/python.exe -m scripts.manage_access list

sync é a ação explícita que associa a allowlist; não é executado por login ou startup normal. list não cria contas. Nenhum desses comandos executa migrações nesta versão. Os quatro viajantes são associados a participants existentes; Marcos vai para coordination_accounts, sem vínculo financeiro. google_sub permanece nulo até o primeiro callback verificado.

Não foi executado sync com a allowlist real nesta entrega. Usuários não provisionados não são cadastrados automaticamente por um callback Google.

Desativação explícita, com auditoria e invalidação de sessões:

    .venv/Scripts/python.exe -m scripts.manage_access disable --participant-id 3
    .venv/Scripts/python.exe -m scripts.manage_access disable --account coordenacao_secco

Use enable no lugar de disable somente quando houver autorização para reativar. sync preserva contas desativadas e nunca substitui o sub de uma conta vinculada.

## 6. Iniciar uma única versão autenticada

As portas antigas foram preservadas. Antes do teste real, o responsável deve encerrar as versões antigas pelos seus terminais, especialmente as versões sem identidade, e liberar a porta 8003. Não mate processos desconhecidos à força. Nenhuma dessas ações foi realizada nesta etapa.

Depois das autorizações e etapas anteriores, iniciar localmente em um terminal controlado:

    .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8003 --no-proxy-headers --no-access-log

Não criar um segundo processo na mesma porta. O acesso segue limitado a loopback. Não se trata de deploy ou liberação para uso compartilhado/produção.

## 7. Validar login real manualmente

1. Abrir http://127.0.0.1:8003 e usar Entrar com Google no navegador normal, evitando navegadores embutidos.
2. Entrar com uma das contas autorizadas e conferir o nome, perfil e destino automático da tabela acima. Não copiar códigos OAuth ou cookies para relatórios.
3. Conferir /api/usuario no mesmo navegador: identidade, participant_id e permissões, sem tokens. Para Marcos, participant_id deve ser null, perfil coordenacao e ambas as edições false.
4. Visitar ambas as missões. Viajantes podem consultar as duas e editar somente a própria; Marcos consulta ambas e recebe 403 em tentativas diretas de edição e de acesso a comprovantes privados. Não inserir despesas reais ou resultados fictícios para validar isso. Use apenas ensaio sintético isolado se for necessário escrever.
5. Tocar em Sair do aplicativo. Reabrir página protegida deve voltar ao login; API sem sessão deve responder 401. Expiração também exige nova entrada.
6. Em janela privada separada, testar uma conta não autorizada já disponível ao responsável, sem criar conta nova. A audiência interna pode barrá-la no próprio Google; se houver callback, o backend deve recusá-la. Não relaxar a allowlist ou hd para completar esse ensaio.
7. Registrar apenas conta/perfil testado, data e resultado funcional, nunca secret, token, sub, cookie ou código OAuth. Declarar login real validado somente após sucesso manual documentado. Os cinco perfis precisam ser conferidos conforme sua disponibilidade e autorização.

Em erro redirect_uri_mismatch, comparar a URI exata no cliente, no ambiente e na origem usada. Em 403, verificar hd, allowlist, provisionamento explícito e estado habilitado. Em 503, revisar as pendências de configuração; não ativar DEV_NO_AUTH para fingir que o login foi validado. Alterações de conta com outro sub exigem revisão administrativa, não reassociação automática.

## Pendências e limites

Faltam credenciais reais, configuração operacional, autorização/aplicação das migrações, provisionamento explícito e o ensaio manual. A saída esperada desta etapa permanece **implementação pronta, ativação real pendente**.

Não há Google Drive, comprovantes reais habilitados, cadastro público, autenticação por senha, alteração de Workspace, deploy, commit ou push. Políticas de revogação do Workspace não têm webhook nesta versão: use desativação local para bloqueio imediato e respeite a expiração das sessões. Validação de HTTPS, operação de produção, diretórios/backup e regras documentais financeiras continuam fora desta ativação local.
