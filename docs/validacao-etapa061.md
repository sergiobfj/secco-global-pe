# Validação da etapa 06.1

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


> **Distribuição pública:** nomes, e-mails, domínio Google Workspace, IDs de Drive/pastas e identificadores Google Cloud deste documento são fictícios. Resultados e decisões descritos referem-se ao projeto operacional.


## Resultado

Implementação e validação sintética concluídas. Login Google real ainda não validado. A instância operacional da porta 8003 não foi reiniciada; o backend em execução precisa ser reiniciado pelo responsável para carregar a correção.

| Verificação | Resultado |
| --- | --- |
| Testes direcionados de OAuth, autenticação e Workspace | 155 aprovados, 0 falhas, 0 erros, 2 avisos; 124,09 s |
| Suíte integral, executada uma única vez | 469 aprovados, 0 falhas, 0 erros, 2 avisos; 296,83 s |
| Cenários anteriores preservados | 445 |
| Novos cenários de regressão | 24 |
| Layouts no navegador | 24, em 360, 390, 768 e 1280 px |
| Rolagem horizontal indevida | Nenhuma nos layouts medidos |
| Erros de JavaScript/console inesperados | 0 |
| Login e logout sem JavaScript | Aprovados no provedor sintético |
| Instância de QA temporária | Encerrada, concessão limpa e manifesto removido |

Os dois avisos são de depreciação do TestClient HTTPX/Starlette e do alias BlockingPortal do AnyIO. Não houve instalação ou troca de dependências.

Relatórios completos:

- Suíte integral (`artifacts/stage061/full-suite.log`, não distribuído).
- Testes direcionados (`artifacts/stage061/targeted-tests.log`, não distribuído).
- Navegador (`artifacts/stage061/browser-report.json`, não distribuído).
- Reprodução da origem (`artifacts/stage061/reproduction-origin.json`, não distribuído).
- Preservação e resumo (`artifacts/stage061/validation.json`, não distribuído).

## Causa raiz confirmada

Depois de uma falha de comunicação ou de validação no callback, a aplicação renderizava outro formulário POST de login na própria página de callback. Essa resposta usa Referrer-Policy: no-referrer para ocultar parâmetros sensíveis. O navegador envia Origin: null ao submeter um formulário HTML nativo sob essa política. O servidor recusava corretamente essa origem opaca. A interface, porém, induzia uma nova tentativa que seria recusada.

A reprodução foi feita antes da correção com Edge, sem servidor operacional, SQLite ou Google: documentos e requisições totalmente interceptados. Sob no-referrer, Origin foi null; na página limpa com same-origin, foi a origem local esperada. [Comportamento documentado pela MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy).

A hipótese de um filtro de origem aplicado ao GET legítimo do callback não foi confirmada: o filtro de formulário só é chamado nos POSTs. Agora há testes explícitos do GET externo legítimo com state, cookie do navegador, assinatura e demais provas válidas, inclusive sem Origin.

A origem da falha histórica de comunicação com Google não foi determinada. Não houve tentativa de acesso externo com as credenciais reais. Foram cobertas falha de conexão, timeout e resposta HTTP de erro com transporte mockado; em todos os casos, não se cria sessão e é possível tentar novamente.

## Correção e segurança

Erros do callback mantêm HTTP 403/503 e no-referrer, mas oferecem somente um link GET Tentar novamente para /login, sem parâmetros. Essa navegação carrega a política same-origin e um formulário CSRF próprio para iniciar outra transação. A rodada de navegador confirmou Origin correto nos dois POSTs, tanto antes do erro sintético quanto depois da recuperação.

Origin null, origem externa, Referer externo em POST e Sec-Fetch-Site cross-site continuam bloqueados, mesmo com token CSRF correto. POST sem Origin continua dependendo dos cookies e token CSRF; não há exceção de autenticação. Callback POST continua recusado.

Preservados: PKCE S256, state vinculado ao navegador com expiração e uso único, nonce, assinatura RS256, issuer, audience, expiração, hd, email_verified, sub, allowlist, sessões opacas, proteção contra fixação, cookies HttpOnly/Lax e Secure conforme ambiente, CSRF Strict e permissões por missão. Não houve mudança no verificador JWT, no repositório de autenticação ou nas regras financeiras.

Os cinco redirecionamentos foram verificados com identidades sintéticas assinadas: Tiago/Bruno para Argentina, Hugo/Alan para Portugal e Marcos para consolidado. Rascunhos, agenda, Diário e comprovantes continuam cobertos pela suíte anterior.

## Refinamento visual

Mantidos os componentes, a marca oficial local, Space Grotesk, Manrope e as cores SECCO. Foram refinados alinhamento e espaçamento da navegação, estado ativo, cabeçalho e menu de conta; as ações de Hoje foram agrupadas, com botões adequados ao celular. Data, missão, próximo compromisso e agenda continuam antes das metas. Login, acesso negado e 404 receberam tratamento consistente, limites de largura e ações claras para recuperação.

Capturas sintéticas:

- Hoje, celular (`artifacts/stage061/hoje-390.png`, não distribuído).
- Hoje, desktop (`artifacts/stage061/hoje-1280.png`, não distribuído).
- Erro do callback, celular (`artifacts/stage061/callback-erro-390.png`, não distribuído).
- Acesso negado, desktop (`artifacts/stage061/acesso-negado-1280.png`, não distribuído).

Também foram capturados login, agenda e formulário nas quatro larguras. Teclado, link de salto, fontes locais, permissões e logout foram verificados. Nenhum resultado de missão foi inventado.

## Arquivos alterados ou criados

- app/routers/auth.py
- app/templates/login.html
- app/templates/access_denied.html
- app/templates/error.html
- app/templates/dashboard.html
- app/static/css/app.css
- app/static/css/agenda.css
- app/static/css/auth.css
- tests/test_oauth_recovery.py, novo
- scripts/qa-oauth-recovery.cjs, novo
- README.md
- docs/autenticacao.md
- docs/configuracao-google-workspace.md
- docs/validacao-etapa061.md, novo
- artifacts/stage061: relatórios e capturas locais

Nenhuma migração foi criada, editada ou aplicada ao ambiente operacional. Não foi executado scripts.init_db. Não foram modificados código de agenda/Diário, credenciais, .env, banco operacional, backup, dados financeiros ou comprovantes. Os hashes SHA-256 do .env, banco operacional, backup informado e sete migrações permaneceram iguais ao início desta execução. Todos os testes de banco e os dados do navegador utilizaram concessões temporárias, sem carregar .env. O QA usou uma única instância temporária na porta 8059, encerrada ao final. A porta 8003 permaneceu com sua instância anterior.

## Reinício controlado e novo login manual

1. Confirmar a instância atual, sem imprimir ambiente ou credenciais:

       netstat -ano -p TCP | Select-String '127\.0\.0\.1:8003\s+.*LISTENING'

   A instância identificada nesta execução foi o PID 16304. Reconfirme antes de encerrar qualquer processo; o PID pode ser reutilizado.

2. Encerrar somente essa instância Uvicorn, preferencialmente com Ctrl+C no terminal original. Se não houver terminal disponível, confirmar no gerenciador de processos que o PID ainda corresponde ao Uvicorn da porta 8003 e encerrar somente essa instância. Não interromper processos de outras portas nem criar uma duplicata.

3. Com a porta livre, na raiz do projeto, iniciar uma única instância:

       .\.venv\Scripts\python.exe -B -m uvicorn app.main:app --host 127.0.0.1 --port 8003 --workers 1 --no-proxy-headers --no-access-log

   Não usar --reload. Não executar scripts.init_db, migração avulsa ou provisionamento outra vez para esta correção. O startup existente confere migrações e executa sua carga idempotente; não o executamos nesta rodada para respeitar a proibição de escrita no banco operacional.

4. Abrir http://127.0.0.1:8003/login no navegador normal. Não alternar com localhost nem reutilizar a URL antiga do callback. Recarregar a página para obter o formulário atual.
5. Tocar em Entrar com Google e autenticar manualmente com tiago@secco.example. Conferir Tiago Prado, Visão Hoje Argentina e edição restrita à Argentina. Não cadastrar despesas ou resultados fictícios no banco operacional.
6. Se houver erro, tocar em Tentar novamente. O navegador deve abrir /login antes de iniciar outra tentativa. Não copiar a URL do callback, cookies, authorization code, state ou tokens para mensagens ou relatórios.
7. Usar Sair do aplicativo e confirmar retorno ao login. O login real somente poderá ser declarado validado após a confirmação manual do responsável. Os outros perfis precisam de validação manual conforme disponibilidade das contas.

## Limitações

A correção está validada com tokens criptográficos sintéticos e navegador isolado. Credenciais Google, conectividade externa real, políticas do Workspace e o login manual não foram validados nesta execução. Não há autorização para produção, Drive ou comprovantes reais. Nenhum deploy, commit, push ou instalação foi realizado.
