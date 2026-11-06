# SECCO Global PE

> **Situação consolidada da publicação:** esta cópia usa configuração e participantes fictícios. O responsável informou a validação operacional posterior do Cloud Shell v4 com dois uploads sintéticos e repetição idempotente. Essa execução não foi repetida nesta distribuição; IDs e evidências privados ficam fora do repositório. Os blocos de etapas abaixo são registros históricos e podem mencionar pendências anteriores a essa validação. Consulte o [guia público](docs/distribuicao-publica.md) para instalação e resultados locais.


> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


> **Distribuição pública.** Dados pessoais, identificadores do Google Workspace/Drive/Cloud e artefatos operacionais foram substituídos por valores fictícios ou removidos. Nenhuma licença de código aberto é concedida.


Revisão 07C de menor privilégio: o ensaio usa somente `drive.file` + `drive.metadata.readonly`, consulta as pastas conhecidas via `files.get` e bloqueia `drives.get`/escopos mais amplos. A escrita sob pastas existentes ainda requer validação real autorizada. Consulte o [plano revisado](docs/ensaio-supervisionado-drive.md) e a [validação local](docs/validacao-etapa07c-menor-privilegio.md). Integração real permanece desativada.

Etapa 07C: ensaio independente preparado, offline por padrão, com dois PNGs sintéticos, journal/backup em SQLite temporário e transporte HTTP restrito atrás de aprovação explícita. **No registro inicial desta etapa, nenhum upload real havia sido executado; a aplicação mantém o envio real desativado.** Consulte o [procedimento e checklist de autorização](docs/ensaio-supervisionado-drive.md) e a [validação 07C](docs/validacao-etapa07c.md). Não iniciar a aplicação operacional ou aplicar a migração 008 para executar esse ensaio.

Continuação 07B: os 14 destinos informados pelo responsável após leitura supervisionada no Cloud Shell foram mapeados na configuração operacional; nesta distribuição, `.env.example` traz IDs fictícios no mesmo formato. A validação mantém os nomes exatos por missão, incluindo **Deslocamento** na Argentina e **Deslocamentos** em Portugal. **Integração real continua desativada**; `.env`, banco operacional e migrações foram preservados. Consulte o [mapeamento e os pré-requisitos do ensaio futuro](docs/integracao-google-drive.md) e a [validação 07B](docs/validacao-etapa07b.md).

Etapa 07A: infraestrutura de integração com os dois Google Shared Drives, com credenciais desacopladas, journal remoto, idempotência e verificação de integridade/permissões. **Exclusivamente simulada e desativada por padrão; uploads reais continuam bloqueados.** Validação: **522 testes aprovados, zero falhas e dois avisos de depreciação existentes**. Consulte [o guia da integração](docs/integracao-google-drive.md) e [a validação 07A](docs/validacao-etapa07a.md). A migração 008 não foi aplicada ao banco operacional. Não inicie a versão operacional antes de backup validado e autorização da migração; o startup existente aplica migrações pendentes.

Etapa 06.1: recuperação do login OAuth corrigida e acabamento visual refinado. Validação: **469 testes aprovados, 0 falhas, 0 erros e 2 avisos**, com uma única suíte integral; 24 layouts revisados. O login Google real continua pendente de validação manual. Consulte [a validação da etapa](docs/validacao-etapa061.md).

Aplicação local para operar as missões internacionais da SECCO. Python 3.12, FastAPI, SQLite, Jinja2 e JavaScript puro. A visão Hoje mantém a agenda como prioridade.

## Etapa 06

**Implementação pronta, ativação real pendente.** Domínio confirmado no projeto operacional (nesta distribuição, o fictício secco.example). Allowlist explícita para Tiago, Bruno, Hugo, Alan e Marcos. Os quatro viajantes entram na visão Hoje de sua missão; Marcos tem coordenação somente de consulta e chega à visão consolidada, sem vínculo de viajante ou acesso financeiro.

A implementação reutiliza OIDC e sessões da etapa 4. A migração aditiva 007 cria contas/sessões de coordenação sem alterar participantes, autoria ou subvenção. Startup normal não cria usuários reais; o provisionamento exige comando explícito do responsável em banco previamente migrado. O .env operacional e as contas Google não foram alterados.

**Validação automatizada: 445 aprovados, 0 falhas, 0 erros e 2 avisos em 158,06 segundos, em uma única suíte integral.** Login real continua pendente.

Consulte [configuração Google Workspace](docs/configuracao-google-workspace.md), [autenticação](docs/autenticacao.md) e [validação da etapa 06](docs/validacao-etapa06.md). O callback local inicial foi verificado em http://127.0.0.1:8003/auth/google/callback. Credenciais e teste manual real permanecem pendentes.

## Etapa 05B

Armazenamento local privado e persistente, exclusivamente sintético, com recuperação após reinício, publicação sem sobrescrita, journal, quarentena, exclusão autorizada e histórico. O modo temporário da 05A continua padrão. Um diretório existente não ativa a persistência.

A ativação local exige RECEIPTS_STORAGE_BACKEND=local e RECEIPTS_PRIVATE_DIR absoluto fora do projeto, além de captura sintética habilitada e autenticação configurada. Produção e uso com comprovantes reais permanecem bloqueados. A .env operacional não foi modificada e a migração 006 não foi aplicada ao banco operacional nesta rodada.

**Validação final: 400 testes aprovados, 0 falhas, 0 erros e 2 avisos em 362,57 segundos, em uma única execução integral.**

Veja [armazenamento de comprovantes](docs/armazenamento-comprovantes.md) para configuração, consistência, permissões, limites e backup; [validação 05B](docs/validacao-etapa05b.md) registra os resultados. Não há API Drive ou aprovação automática.

## Etapa 05A

Captura rápida exclusivamente sintética, com formulário mobile, prévia de JPEG/PNG e PDF, rascunho, checklist contextual, edição com versão e anexos privados por autor. Exige sessão autenticada, permissão por missão e RECEIPTS_SYNTHETIC_ENABLED=true em development. Arquivos são temporários e não garantem conservação. Não utilize comprovantes reais.

Veja [captura de comprovantes](docs/captura-comprovantes.md) para ativação, limites, funcionamento e pendências; [arquivos da etapa](docs/arquivos-etapa05a.md) registra as alterações. Nenhum servidor foi iniciado e a migração operacional não foi aplicada nesta rodada.

## Etapa 4

- Google OpenID Connect com Authorization Code, PKCE S256, state e nonce.
- Validação criptográfica no servidor, claim hd, e-mail verificado e allowlist explícita.
- Vínculo estável pelo sub a participantes existentes, sem duplicar cadastros.
- Sessões opacas no servidor, expiração, renovação, logout e CSRF vinculado à sessão.
- Consulta das duas missões e edição somente na missão do participante ou com concessão explícita.
- Autoria na agenda, Diário, evidências, classificações e respectivos históricos.
- Tela de login com identidade oficial SECCO e menu da conta.
- Missão padrão persistida por usuário, abrindo diretamente Hoje.
- Administração local simples, sem painel complexo ou privilégios financeiros implícitos.

**O login Google real ainda não foi configurado ou validado.** Domínio e cinco e-mails estão confirmados no projeto operacional (fictícios nesta distribuição); credenciais, configuração operacional e validação manual permanecem pendentes. Sem configuração completa, as rotas de dados ficam bloqueadas e o login informa a pendência.

PyJWT 2.15.1 e cryptography 50.0.2 foram instalados manualmente e confirmados no ambiente virtual. A validação final da etapa 4 aprovou 289 testes com essas versões.

As funcionalidades anteriores continuam disponíveis para usuários autorizados: agenda, Diário, metas, histórico, CSRF, concorrência e navegação responsiva. A etapa 05A permite cadastro e upload exclusivamente sintéticos em armazenamento temporário, sem integração Drive, sincronização offline ou deploy. O uso financeiro real permanece bloqueado.

## Executar localmente

Para instalação nova em PowerShell, com acesso autorizado ao registro de pacotes:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8003 --no-proxy-headers --no-access-log
```

Abra http://127.0.0.1:8003. Sem credenciais, é esperado ver Configuração do acesso pendente e HTTP 503 no login. Isso não libera acesso anônimo aos dados.



Em Linux/macOS, use python3.12 e .venv/bin/python nos mesmos comandos. Não há Docker. Não publique a aplicação: o acesso continua limitado a loopback, inclusive com a estrutura de autenticação preparada.

## Configuração autorizada

| Variável | Uso |
| --- | --- |
| APP_ENV | development nesta entrega |
| DEV_NO_AUTH | false como padrão seguro |
| DATABASE_PATH | data/secco.sqlite3, preservado |
| GOOGLE_CLIENT_ID | Cliente OAuth Web autorizado |
| GOOGLE_CLIENT_SECRET | Segredo privado do cliente |
| GOOGLE_REDIRECT_URI | Callback exato registrado, terminando em /auth/google/callback |
| GOOGLE_WORKSPACE_DOMAIN | Domínio Workspace autorizado (fictício nesta distribuição) |
| ALLOWED_USERS | Lista JSON de participant_id e e-mail inicial autorizado |
| SESSION_SECRET | Segredo aleatório persistente de pelo menos 32 bytes |
| SESSION_IDLE_SECONDS | 1800 por padrão |
| SESSION_ABSOLUTE_SECONDS | 43200 por padrão |
| SESSION_ROTATION_SECONDS | 900 por padrão |
| RECEIPTS_SYNTHETIC_ENABLED | false por padrão; habilita somente captura sintética local autenticada |
| RECEIPTS_STORAGE_BACKEND | temporary por padrão; local exige ativação explícita |
| RECEIPTS_PRIVATE_DIR | Caminho absoluto privado fora do projeto, usado somente pelo adaptador local |

A .env.example mantém credenciais vazias e traz domínio e e-mails fictícios no formato da configuração operacional. Não envie segredos em mensagens, código ou logs. O preenchimento e a configuração futura do Google Cloud estão descritos em [autenticação](docs/autenticacao.md).

No primeiro login verificado, o e-mail identifica o participante da allowlist e o sub é vinculado de forma estável. Mudanças posteriores de e-mail com o mesmo sub preservam o usuário. Uma conta diferente não substitui um vínculo existente reutilizando o e-mail.

Na política SECCO, os viajantes consultam ambas as missões e editam somente sua missão principal. Marcos consulta ambas sem escrita ou acesso a comprovantes privados. Permissão de uso não significa financiamento: Hugo e Bruno continuam custeados; Tiago e Alan continuam fora da subvenção.

O modo DEV_NO_AUTH=true existe apenas para manutenção local intencional em development, com aviso visual de autoria não autenticada. Ele é recusado em produção e não foi usado para simular os testes de autorização.

## Usar a aplicação

Depois de entrar, Hoje abre na missão padrão do usuário. A troca de missão fica no cabeçalho. O menu da conta mostra o nome, o perfil/visão principal definida pelo servidor e oferece Sair do aplicativo. A visão consolidada é a entrada de Marcos.

Em Planejamento, escolha o dia ou Sem data. Sugestão e A confirmar não são compromissos confirmados. Horários continuam opcionais. O mapa aparece somente com endereço conferido.

Para registrar um resultado: compromisso profissional → Registrar resultado → revisar dados e completar descrição/resultados → Salvar registro. O vínculo é explícito e único, sem alterar automaticamente o compromisso. Turismo não gera Diário profissional.

Também é possível criar registros diretamente no Diário. Rascunhos podem ficar incompletos; Realizada exige título, data, descrição e resultados. Organização, local, participantes, objetivo e próximos passos são progressivos. Erros preservam o preenchimento quando aplicável, com JavaScript ou no retorno de validação HTML.

## Metas e evidências

Portugal: 10 reuniões qualificadas e 3 LOIs. Argentina: 8 reuniões qualificadas e 3 manifestações formais de interesse.

Uma reunião realizada não se torna qualificada automaticamente. A contagem exige registro Realizada, classificação justificada, critério informado, aprovação declarada e evidência correspondente com referência externa conferida. Rascunhos, cancelamentos e pendências não contam.

A autenticação identifica quem registrou a classificação. A anuência da coordenação continua sendo uma declaração manual, sem assinatura ou validação automática da FACEPE. Critérios oficiais ainda precisam ser fornecidos.

Evidências continuam sendo metadados e referências HTTPS, sem upload. A aprovação corresponde à versão exata do registro e da evidência. Alterações exigem nova revisão. Veja [Diário e metas](docs/diario-e-metas.md).

## Banco e migrações

SQLite é a fonte da verdade. As migrações 001 a 004 são preservadas nesta etapa. A migração 004_authentication.sql cria app_users, user_mission_permissions, user_sessions, oauth_transactions e auth_events e adiciona autoria às estruturas existentes.

A migração aditiva 007_workspace_coordination.sql cria coordination_accounts e coordination_sessions e estende a auditoria, sem criar participantes. A migração 006_receipt_storage.sql cria volumes, objetos persistentes e eventos de armazenamento. A migração 005_receipts.sql cria expenses, expense_attachments, expense_checklists, expense_history, expense_submissions e receipt_mission_config, sem seeds financeiros. Será aplicada na próxima inicialização autorizada.

Nenhum participante é duplicado. Não há carga de contas Google fictícias. Sem allowlist configurada, app_users permanece vazio. As informações de financiamento são independentes das permissões.

A inicialização é idempotente:

```powershell
.\.venv\Scripts\python.exe -m scripts.init_db
```

O backup consistente anterior à etapa 4 está em .tools/backups/etapa3-before-stage4.sqlite3. Todos os dados anteriores foram comparados após a migração e preservados. Não apague o banco nem altere migrações já aplicadas.

## Estrutura

```text
app/
  main.py
  core/              configuração, CSRF, autorização, logs e isolamento de testes
  db/                conexão, autoria, migrações 001 a 007 e seeds
  repositories/      missions.py, itinerary.py, diary.py, auth.py, receipts.py
  services/          regras de missão, agenda, Diário, Google OIDC e captura sintética
  routers/           web.py, api.py, planning.py, diary.py, auth.py
  templates/         login, conta, páginas e componentes
  static/            marca oficial, fontes, CSS e JavaScript locais
scripts/
  init_db.py
  manage_access.py   concessões locais explícitas
  serve_qa.py        concessão temporária, modos local/synthetic/pending
  qa-auth.cjs        login sintético assinado e revisão responsiva
tests/
docs/
data/                banco operacional fora do Git
artifacts/           capturas e relatórios locais
```

Veja [arquivos da etapa 05A](docs/arquivos-etapa05a.md) e [arquitetura](docs/arquitetura.md).

## Rotas de acesso

| Rota | Uso |
| --- | --- |
| /login | Entrada ou configuração pendente |
| POST /auth/google | Iniciar OIDC com CSRF |
| /auth/google/callback | Validar retorno, token e vínculo |
| POST /auth/logout | Revogar sessão e limpar cookies |
| POST /auth/preferencia | Definir missão padrão |
| /api/usuario | Identidade mínima e permissões da sessão |
| / | Hoje da missão principal, consolidado da coordenação ou seleção no modo local |
| /consolidado | Consulta de agenda/metas das duas missões |
| /missoes/{codigo} | Hoje |
| /missoes/{codigo}/planejamento | Agenda |
| /missoes/{codigo}/diario | Diário |
| /missoes/{codigo}/comprovantes | Capturas sintéticas do próprio usuário |
| /missoes/{codigo}/comprovantes/novo | Registro rápido, câmera/arquivo |

As rotas anteriores permanecem compatíveis e protegidas. Prestação de Contas contém somente a captura sintética quando habilitada. Organização, Documentos e os demais recursos financeiros continuam em desenvolvimento.

## Testes

Após instalar as dependências fixadas:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q app scripts tests
```

Na validação final da etapa 4, **289 testes passaram**, incluindo os 203 cenários anteriores e 86 casos de autenticação. Há dois avisos conhecidos de depreciação do TestClient/AnyIO.

A validação final posterior à instalação manual usou diretamente o ambiente virtual, sem bootstrap auxiliar. Nenhuma dependência adicional foi necessária na etapa 05A.

A validação final da etapa 05A aprovou **361 testes, sem falhas ou erros e com dois avisos**, em 115,67 segundos. Consulte [validação da etapa 05A](docs/validacao-etapa05a.md). A etapa 05B preserva esses cenários e acrescenta testes de armazenamento persistente; o relatório final fica em [validação da etapa 05B](docs/validacao-etapa05b.md).

Testes e navegador usam somente concessões temporárias. .env não é carregado no pytest. DATABASE_PATH persistente explícito falha antes de migração ou criação de arquivos. Veja [isolamento](docs/isolamento-testes.md).

## QA de navegador

Com as dependências exigidas instaladas, em terminais separados:

```powershell
# Terminal 1
.\.venv\Scripts\python.exe -m scripts.serve_qa --port 8057 --auth-mode synthetic
# Terminal 2, Playwright disponível como ferramenta de QA
node scripts/qa-auth.cjs C:\caminho\node_modules\@playwright\test
```

O helper usa banco temporário e um provedor sintético que assina tokens de teste. O navegador intercepta a autorização externa; não há conta Google ou tráfego real de login. DEV_NO_AUTH é false nesses fluxos. Nenhum endpoint sintético existe na aplicação normal.

Para revisar configuração ausente, inicie outro helper com --auth-mode pending e execute o mesmo script com --pending. Cada execução encerra seu helper e limpa somente a concessão verificada.

Foram validados 36 layouts em 360, 390, 768 e 1280 px: 32 autenticados sintéticos e quatro de configuração pendente, com login/logout sem JavaScript e teclado. Capturas e relatórios históricos estão em artifacts/stage4. As telas novas da captura não foram validadas em navegador nesta rodada.

O guard recusa portas 8000/8001/8002/8003, exige manifesto, URL exata e identidade da concessão. O servidor normal recusa requisições identificadas como QA. Playwright não é dependência de runtime.

## Limites e próximos passos

1. Conferir o relatório da etapa 05A e suas limitações antes de qualquer uso.
2. Configurar manualmente o cliente Web e callback com o responsável, preservando o domínio e os cinco perfis confirmados.
3. Após autorização das migrações pendentes e provisionamento explícito, fazer teste manual dos perfis, logout e bloqueio, encerrando antes as versões antigas sem identidade.
4. Fornecer critérios oficiais de qualificação, evoluir perfis de coordenação e integração Shared Drive.
5. Validar os documentos FACEPE, processos e rubricas, depois planejar armazenamento durável no Shared Drive antes de qualquer despesa real.

Não há deploy, commit, push, criação de credenciais ou alteração do Workspace. O servidor segue local, sem acesso de outros aparelhos. Viewports não substituem validação física Android/iOS. Não há fila offline; fechar ou recarregar um formulário não salvo ainda pode perder os campos.

A marca oficial permanece preservada. Consulte [identidade SECCO](docs/identidade-secco.md), [autenticação](docs/autenticacao.md), [arquitetura](docs/arquitetura.md) e [experiência do registro rápido](docs/ux-registro-rapido.md).
