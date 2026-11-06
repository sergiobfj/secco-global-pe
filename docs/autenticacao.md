# Autenticação e autorização, etapa 06

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


> **Distribuição pública:** nomes, e-mails, domínio Google Workspace, IDs de Drive/pastas e identificadores Google Cloud deste documento são fictícios. Resultados e decisões descritos referem-se ao projeto operacional.


## Estado

**Implementação pronta, ativação real pendente.** Nenhuma autenticação com conta Google real foi realizada. O domínio e os cinco e-mails foram confirmados pelo responsável no projeto operacional; nesta distribuição, são fictícios (secco.example). Client ID, secret, callback registrado, segredo de sessão e configuração/provisionamento operacionais continuam pendentes.

PyJWT 2.15.1 e cryptography 50.0.2 estão instalados e já foram validados no ambiente virtual. Não há fallback para versões antigas. Sem configuração válida, as rotas de dados falham de forma fechada. O domínio autorizado fora dos testes é o de `WORKSPACE_DOMAIN` (fictício nesta distribuição: secco.example); domínios fictícios são usados somente em fixtures isoladas, sob a política de SQLite temporário.

A configuração manual está em [configuracao-google-workspace.md](configuracao-google-workspace.md). Os resultados automatizados estão em [validacao-etapa06.md](validacao-etapa06.md).

## OIDC existente, preservado

A etapa reutiliza o fluxo da etapa 4: Authorization Code para cliente Web confidencial, PKCE S256, state de uso único vinculado ao navegador e nonce. Os únicos escopos são openid e email. Não há Drive, acesso offline, refresh token ou autenticação por senha.

A troca do código acontece no backend por HTTPS, em endpoints Google fixos, com timeout e sem seguir redirecionamentos. O ID Token é verificado por assinatura RS256, chaves RSA de no mínimo 2048 bits, emissor exato, audiência, emissão, expiração, nonce, sub, email_verified e hd. azp e at_hash são verificados quando presentes. Não são aceitas fontes de chave indicadas pelo cabeçalho do token ou algoritmos escolhidos pelo cliente.

A claim hd do token assinado precisa corresponder a secco.example. O sufixo textual do e-mail e o parâmetro hd do pedido não provam pertencimento ao Workspace. Referência: [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect).

O e-mail verificado associa inicialmente a conta provisionada à allowlist. sub é o identificador estável. E-mail alterado com o mesmo sub preserva o perfil e a identidade autorizada, desde que a conta permaneça habilitada, na allowlist e com hd válido. Outro sub não substitui um vínculo existente reutilizando seu e-mail. Há unicidade de identidade entre viajantes e coordenação.

## Cinco perfis

| Conta autorizada | Participante | Visão principal | Escrita |
| --- | --- | --- | --- |
| tiago@secco.example | Tiago Prado, ID 3 | Hoje Argentina | Argentina |
| bruno@secco.example | Bruno de Castro, ID 4 | Hoje Argentina | Argentina |
| hugo@secco.example | Hugo Mendes, ID 1 | Hoje Portugal | Portugal |
| alan@secco.example | Alan Renato, ID 2 | Hoje Portugal | Portugal |
| marcos@secco.example | Nenhum | Consolidada | Nenhuma |

A política está no servidor em core/workspace_access.py. A allowlist é explícita e não pode trocar arbitrariamente as associações dos quatro participantes. O servidor confere os nomes e as missões existentes durante o provisionamento. Todos os cinco perfis consultam ambas as missões. A política SECCO não amplia escrita para outra missão por cookie, formulário, role ou concessão legada. A coordenação permanece somente leitura.

Os perfis SECCO não alteram sua visão principal pelo menu da conta. A troca de missão continua disponível para consulta. Marcos chega diretamente a /consolidado; os viajantes chegam à visão Hoje correspondente. /api/usuario informa perfil, visão principal e permissões, sem tokens. Para coordenação, participant_id é null.

## Modelo aditivo de coordenação

A tabela legada app_users exige participant_id e é referenciada por autoria, despesas e sessões. Para preservar esses vínculos sem DROP, reconstrução de tabelas ou participantes fictícios, a migração 007 acrescenta coordination_accounts e coordination_sessions. auth_events recebe coordinator_id opcional. Não insere usuários ou altera dados existentes.

AuthRepository oferece uma projeção comum de identidade e reutiliza os mesmos métodos de sessão, HMAC, expiração, rotação e logout para os dois tipos. Não há segundo protocolo OIDC ou autenticação paralela. IDs de coordenação usam prefixo interno coord:, evitando confusão com IDs de viajantes. As sessões físicas ficam em tabelas separadas para manter integridade referencial sem referência polimórfica inválida.

Marcos não vai para participants, mission_participants ou app_users, não recebe financiamento, não entra nas metas e não vira autor de atividade realizada por viajante. actor_id retorna None para coordenação; operações de escrita são recusadas antes da persistência. Os nomes dos autores das atividades continuam sendo derivados dos participantes existentes.

## Provisionamento explícito

Não existe cadastro público. Callback Google não cria usuário ausente. Startup normal e scripts.init_db não provisionam contas reais. Somente scripts.manage_access sync associa intencionalmente a allowlist após configuração e autorização. Em testes, o startup provisiona apenas dentro das concessões temporárias já protegidas.

manage_access exige banco previamente migrado e não executa migrações automaticamente, nem ao listar acessos. sync é idempotente e preserva desativação e sub já vinculado. Os comandos enable/disable são explícitos; desativar bloqueia sessões imediatamente. Uma conta nova com sub diferente exige revisão administrativa, não reassociação automática.

A coordenação é selecionada por --account coordenacao_secco; viajantes por --participant-id. Tentativas de grant/default para coordenação são recusadas. Concessões fora da missão principal da política SECCO também são recusadas. O operador local precisa ter acesso autorizado ao filesystem e ao banco; esse CLI não é um painel administrativo público.

## Autorização nos módulos

Os formulários de criação/edição e as operações de escrita de agenda, Diário, metas e comprovantes verificam permissão no backend. Requisições diretas não autorizadas recebem 403, independentemente de botões ocultos. Preferências de visão principal do perfil fixo também são protegidas. A leitura da visão consolidada e do dashboard pela coordenação não importa registros legados ou cria atividades.

Comprovantes exigem, adicionalmente, participante da sessão, autoria da despesa e as regras do armazenamento privado. Coordenação não consulta, baixa, cria, edita ou exclui comprovantes por padrão. Não foi implementada concessão financeira específica para Marcos nesta etapa.

Hugo e Bruno continuam custeados, Tiago e Alan continuam fora da subvenção. Acesso ao aplicativo não concede reembolso, elegibilidade financeira ou autoridade para validar metas. O perfil de coordenação atual não autentica ou aprova a anuência financeira/institucional declarada nos formulários anteriores.

## Sessões e CSRF

Cookies contêm somente identificadores opacos aleatórios. O SQLite armazena HMAC, segredo CSRF de sessão e prazos; não armazena tokens Google. Cookies são HttpOnly, SameSite=Lax para sessão e OAuth, e Secure em HTTPS/produção. O formulário usa CSRF vinculado ao cookie e à sessão, com validação de origem.

Login troca o identificador e o CSRF e invalida a sessão anterior observada. A renovação periódica mantém janela curta de 30 segundos para requisições em trânsito; logout invalida também a referência anterior. Há expiração por inatividade e limite absoluto. Conta desabilitada ou removida da allowlist perde acesso. Tokens de sessão das duas categorias são invalidados pelos mesmos métodos.

CSS, imagens e health não renovam atividade ou removem cookies válidos. Logout encerra apenas o aplicativo, sem alterar a sessão Google. Mudanças de client ID, domínio ou SESSION_SECRET invalidam o acesso vinculado. Não existe webhook de revogação Workspace; use desativação local para bloqueio imediato e respeite a expiração.

HTML protegido sem sessão redireciona ao login; APIs e escritas retornam 401 quando configuradas ou 503 quando a configuração está pendente. Login e health são públicos por finalidade; não há acesso anônimo aos dados. DEV_NO_AUTH permanece modo de manutenção local explícito, sem identidade, e não valida autorização real ou libera captura de comprovantes.

## Configuração e logs

GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, GOOGLE_WORKSPACE_DOMAIN, ALLOWED_USERS e SESSION_SECRET são preenchidos manualmente no ambiente privado. .env.example contém domínio e e-mails fictícios no formato da configuração, mas os campos de credenciais continuam vazios. O .env operacional não foi alterado.

scripts.check_auth_config não abre banco, não chama Google e não exibe segredos ou conteúdo de configuração malformada. Não certifica login real. Não coloque client secret, ID/access tokens, cookies, códigos OAuth ou sub em relatórios.

O callback filtra código/state do access log e usa no-referrer; as demais páginas usam same-origin para preservar formulários nativos. Use --no-access-log no ensaio local. Não há tokens em localStorage, IndexedDB ou HTML. A biblioteca de OIDC não registra o token recebido ou o conteúdo da resposta do provedor.

## Ativação pendente e preservação

A porta 8003 respondeu em 127.0.0.1; o callback a registrar inicialmente é http://127.0.0.1:8003/auth/google/callback. O processo atual é anterior e não foi reiniciado. As portas antigas foram preservadas; o responsável deve encerrar versões sem identidade pelos seus terminais antes de qualquer ensaio real.

O banco operacional contém 001 a 004. As migrações 005/006/007 exigem revisão, backup e autorização antes de inicializar a versão nova. Nenhuma migração operacional ou provisionamento com os e-mails reais foi executado. A migração 007 é aditiva e não altera os participantes, financiamento, despesas ou resultados existentes.

Após configurar, migrar com autorização, provisionar explicitamente e iniciar uma única instância local, o responsável fará login manual, conferirá os cinco perfis, logout e bloqueio de conta não autorizada conforme o procedimento documentado. Até isso ocorrer, o estado permanece **implementação pronta, ativação real pendente**. Comprovantes reais, Drive e produção não foram liberados.


## Correção do retorno OAuth, etapa 06.1

Uma falha de conexão ou validação fazia o callback renderizar novamente um formulário de entrada. O callback usa Referrer-Policy: no-referrer para impedir a propagação de code e state. Em um formulário HTML nativo, essa política faz o navegador enviar Origin: null, inclusive no POST de mesma origem. A comparação estrita de origem rejeitava corretamente a nova tentativa, mas a interface oferecia justamente essa tentativa incompatível.

A reprodução foi feita com Edge e documentos totalmente interceptados, sem Google ou SQLite operacional: o formulário na página com no-referrer envia Origin: null; a mesma ação em /login, com same-origin, envia a origem local correta. Referência primária: [MDN Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy).

Agora, erros no callback mantêm os códigos HTTP 403/503 e no-referrer, mas não renderizam formulários POST. A ação Tentar novamente é um link GET para /login, sem parâmetros. Essa página emite o formulário CSRF normalmente e inicia outra transação OIDC. Não aceitamos Origin: null como exceção.

- Navegação GET /login: não exige Origin, mostra a entrada sem iniciar OAuth.
- POST /auth/google: continua exigindo CSRF; origem externa, opaca ou Sec-Fetch-Site cross-site permanece recusada.
- GET /auth/google/callback: pode ser navegação externa legítima; exige destino configurado, state associado ao navegador, nonce e todos os controles OIDC. Referer do Google não é prova de identidade.
- Callback inválido, expirado ou sem cookie: recusa acesso e permite uma nova tentativa limpa.
- POST de agenda, Diário, comprovantes e logout: as validações de origem, CSRF, sessão e missão não foram alteradas.

PKCE S256, assinatura RS256, issuer, audience, expiração, hd, email_verified, sub, allowlist e redirecionamento principal no servidor permanecem intactos. Cookies OIDC e de sessão continuam HttpOnly, SameSite=Lax, com Secure conforme ambiente/HTTPS; o cookie CSRF permanece Strict. Nenhum token Google é armazenado no navegador.

A mensagem histórica de falha de comunicação com Google não permite distinguir rede, timeout ou resposta do provedor sem evidência adicional. Não foi realizada chamada real para diagnosticar essa ocorrência. Os três cenários foram simulados com transporte HTTP isolado e falham sem criar sessão.
