# Validação da etapa 06

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


> **Distribuição pública:** nomes, e-mails, domínio Google Workspace, IDs de Drive/pastas e identificadores Google Cloud deste documento são fictícios. Resultados e decisões descritos referem-se ao projeto operacional.


## Conclusão

**Implementação pronta, ativação real pendente.** Domínio e cinco perfis estão preparados e verificados por testes sintéticos. Nenhum login com conta Google real foi realizado ou declarado validado.

Em 02/11/2026, a suíte integral foi executada uma única vez após a implementação:

- **445 testes aprovados, 0 falhas, 0 erros e 2 avisos**, em **158,06 segundos**.
- Código de saída 0.
- Os 400 cenários anteriores foram preservados, com 45 novos cenários da etapa 06.
- Os avisos conhecidos são depreciações do TestClient/HTTPX e do alias BlockingPortal no AnyIO.

Comando: .venv/Scripts/python.exe -B -m pytest -v -p no:cacheprovider --tb=short.

Stdout e stderr foram gravados diretamente em full-suite.log (`artifacts/stage06/full-suite.log`, não distribuído), sem truncamento do console. Não houve repetição da suíte integral.

## Rodadas específicas anteriores à integral

A primeira rodada aprovou 44 testes em 21,11 segundos, com 2 avisos: specific-tests.log (`artifacts/stage06/specific-tests.log`, não distribuído). A revisão de autorização acrescentou o teste de consulta sem importação de registros legados, aprovado em 0,81 segundo: readonly-test.log (`artifacts/stage06/readonly-test.log`, não distribuído).

A restrição do domínio operacional foi reforçada no caso de configuração já existente e esse teste foi repetido de forma focada: 1 aprovado em 0,52 segundo, com 2 avisos: domain-config-test.log (`artifacts/stage06/domain-config-test.log`, não distribuído). Ele se sobrepõe à primeira rodada; são 45 cenários únicos novos, não 46. Todos foram incluídos na suíte final de 445.

## Cobertura

- Cinco contas da allowlist, associadas aos quatro participantes existentes ou à coordenação sem participante.
- Destino automático: Argentina para Tiago/Bruno, Portugal para Hugo/Alan, consolidado para Marcos.
- Assinatura, emissor, audiência, expiração, nonce, state, email_verified e domínio hd; e-mail com domínio textual correto não contorna hd incorreto ou ausente.
- Bloqueio fora da allowlist, conta desativada e remoção da allowlist com sessão existente.
- Identidade estável por sub durante troca de e-mail e recusa de substituição por outro sub.
- Unicidade de identidade entre as duas categorias de conta.
- Leitura de ambas as missões e escrita restrita à principal; coordenação recusada em criação, edição, cancelamento, metas e exclusão de anexos.
- Comprovantes privados protegidos contra consulta/download pela coordenação, sem alterar o arquivo do viajante.
- Sessão opaca, logout com CSRF, invalidação, rotação e expiração da coordenação, além dos cenários anteriores de segurança.
- Visão consolidada e Hoje da coordenação sem criação de registros legados durante a consulta.
- Sem cadastro público ou provisionamento automático no startup normal; provisionamento somente por ação explícita, com fixture isolada para comprovar o comportamento.
- CLI bloqueia edição para coordenação e permite desativação com revogação de sessão.
- Preflight de configuração não revela segredos ou certifica login real.
- Migração 007 repetida de forma idempotente em SQLite temporário, mantendo integridade e participantes.

## Isolamento e preservação

Todos os bancos foram SQLite temporários ou em memória sob as proteções existentes de tests/conftest.py. A política é ativada antes de importar a aplicação e não carrega o .env operacional. Os dados, chaves de assinatura e tokens foram sintéticos; o transporte OIDC foi mockado. Nenhuma conta Google real foi acessada.

A comparação de SHA-256, tamanho e data de modificação confirmou a preservação de .env, data/secco.sqlite3, migrações 001 a 006 e arquivos protegidos de comprovantes, armazenamento, agenda e Diário. Nenhuma migração operacional foi aplicada, nenhum usuário real foi provisionado e nenhum dado financeiro foi alterado.

A inspeção operacional foi somente de leitura, com SQLite em modo ro e immutable, e confirmou os participantes: ID 1 Hugo custeado; ID 2 Alan fora da subvenção; ID 3 Tiago fora da subvenção; ID 4 Bruno custeado. O banco operacional possui apenas 001 a 004. As versões 005, 006 e 007 permanecem pendentes de autorização antes da ativação da versão nova.

## Verificações locais e pendências reais

GET /health confirmou respostas em 127.0.0.1 nas portas 8000, 8001, 8002 e 8003, sem iniciar ou encerrar processos. A rota existente é /auth/google/callback; a URI inicial documentada é http://127.0.0.1:8003/auth/google/callback. O processo atual em 8003 não foi atualizado nesta etapa.

O comando scripts.check_auth_config confirmou prontidão false no ambiente operacional, sem mostrar valores. Permanecem pendentes ALLOWED_USERS, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, GOOGLE_WORKSPACE_DOMAIN e SESSION_SECRET nesse ambiente. Isso não contradiz a confirmação do domínio e e-mails no briefing: eles estão preparados em política/.env.example e ainda não foram escritos na configuração privada.

Sintaxe Python, templates Jinja2 e sete migrações em SQLite em memória passaram nas verificações estáticas, com integridade válida. Não houve instalação de dependências, validação de navegador, Google Drive, comprovantes reais, serviços externos, deploy, commit ou push. Não há repositório/checkpoint Git nesta pasta.

O responsável deve configurar o cliente Web, preencher o ambiente privado sem compartilhar secrets, autorizar backup/migrações pendentes, provisionar explicitamente e iniciar uma única instância autenticada após encerrar as versões antigas pelos seus terminais. Só então fará o login manual, conferência dos perfis, logout e bloqueio de conta não autorizada. Procedimento: [configuracao-google-workspace.md](configuracao-google-workspace.md).

## Arquivos da etapa

Novos:

- app/core/workspace_access.py
- app/db/migrations/007_workspace_coordination.sql
- app/templates/consolidated.html
- scripts/check_auth_config.py
- tests/test_workspace_access.py
- docs/configuracao-google-workspace.md
- docs/validacao-etapa06.md

Alterados:

- app/core/config.py e auth.py
- app/repositories/auth.py
- app/routers/auth.py e web.py
- app/services/missions.py, apenas opção de consulta sem importação legada, mantendo o comportamento anterior por padrão
- app/main.py, retirando provisionamento automático fora das concessões de testes
- app/templates/base.html
- scripts/manage_access.py e init_db.py
- .env.example, README.md e docs/autenticacao.md
- tests/test_database.py, test_authentication.py, test_receipts.py e test_persistent_receipts.py, somente expectativa da quantidade de migrações atualizada para 7

Os relatórios completos desta etapa ficam em artifacts/stage06. Migrações anteriores, .env operacional, regras financeiras e arquivos privados não foram alterados.
