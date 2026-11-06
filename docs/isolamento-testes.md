# Isolamento obrigatório dos bancos de testes

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


## Política

Testes e QA de navegador nunca usam o SQLite operacional, suas cópias persistentes ou bancos nomeados manualmente como teste. Exigem uma concessão criada por app.core.test_database.TemporaryDatabase, dentro de diretório exclusivo do sistema operacional.

A concessão contém marcador aleatório de propriedade, registro ativo em memória, caminho resolvido e conexões rastreadas. O diretório precisa permanecer dentro do temporário do sistema, sem links para arquivos persistentes. SQLite em memória também é permitido. O diretório data/ do projeto é sempre proibido em modo de teste.

## Pontos de bloqueio

- tests/conftest.py ativa o modo antes de importar a aplicação e não carrega .env.
- DATABASE_PATH explícito é verificado antes de ser substituído pela concessão da sessão. Um caminho operacional produz falha explícita, sem criar ou migrar o banco.
- Settings.from_env, Settings.validate, migrate e connect aplicam a mesma política. A verificação precede a criação de diretórios.
- Um processo com pytest carregado ou SECCO_TEST_MODE definido não pode abrir o banco pela aplicação sem ativar a política.
- O processo de testes envolve sqlite3.connect e Connection e usa o evento de auditoria de conexão, impedindo abertura acidental de caminhos persistentes por chamadas diretas.
- As conexões isoladas usam authorizer para recusar ATTACH, inclusive VACUUM INTO. Factories alternativas e extensões SQLite são recusadas.
- Eventos de arquivo recusam gravação, remoção ou movimentação sobre data/ e arquivos SQLite persistentes. Links físicos para bancos também são recusados.

A política previne erros de configuração e uso acidental das APIs do projeto. Não é uma sandbox de segurança contra código Python deliberadamente hostil, processos externos, bibliotecas nativas ou outro usuário do sistema operacional. Não execute testes destrutivos por ferramentas que ignorem o helper.

## Limpeza

Cada fixture possui sua concessão. O fechamento revoga a concessão, fecha conexões rastreadas e valida caminho absoluto, diretório pai, prefixo e marcador antes de remover exclusivamente aquela pasta temporária.

Se o marcador ou caminho não corresponder, a limpeza falha e conserva os arquivos. Não há busca seguida de exclusão de bancos por nome ou extensão. Se o processo for interrompido abruptamente, podem restar temporários; isso não autoriza limpeza ampla. Backups e data/ permanecem intocados.

## Navegador

Use python -m scripts.serve_qa --port 8057. O helper ativa a mesma política antes de importar a aplicação, cria concessão, inicia o startup normal e publica sua identificação em .tools/qa-current.json.

scripts/qa-guard.cjs exige manifesto, loopback, porta diferente de 8000/8001/8002/8003, URL exatamente correspondente e resposta de identidade com nonce e versão da política. Cada contexto do navegador recebe X-SECCO-QA-Instance. Um servidor operacional com o código novo recusa esse cabeçalho. A recusa explícita de destino 8001 é testada antes de qualquer navegação para esse endereço.

O encerramento de QA exige CSRF e é solicitado pelo script mesmo se uma asserção falhar. O helper fecha o servidor, remove apenas seu próprio manifesto e limpa a concessão. Os endpoints de identidade e encerramento não existem na aplicação operacional.

## Cobertura

Há testes de caminho operacional, URI, caminho persistente disfarçado de teste, conexão direta, criação de pasta antes de migração, ATTACH, hard link, limpeza e marcador adulterado, filesystem e configuração do helper. Os testes de segurança não tentam apagar o banco operacional; usam recusa de configuração, alvos temporários ou eventos de auditoria simulados.

Todos os casos de Diário, evidências, metas e agenda escrevem somente em concessões temporárias. As capturas com conteúdo sintético têm prefixo qa e são descritas como QA no relatório.

A verificação operacional da entrega é separada: backup consistente, migração aditiva autorizada e consultas de integridade, sem inserir dados de teste.


## Autenticação, etapa 4

O helper aceita --auth-mode synthetic para contas estritamente sintéticas em concessão temporária. Nesse modo, DEV_NO_AUTH é false e o fluxo OIDC valida tokens RSA assinados por chave de teste, com state, nonce e PKCE. O navegador intercepta a URL de autorização e não acessa contas Google.

A rota /__qa__/authorize é criada somente nesse helper, exige a identificação da concessão e não existe no servidor operacional. O modo --auth-mode pending valida o fechamento do acesso quando faltam credenciais. O modo local continua disponível para regressão dos componentes anteriores, sem ser usado como prova de autorização.

O guard aguarda de forma limitada o manifesto e a prontidão do helper, sem relaxar URL, porta, nonce ou identidade da concessão. Os testes mantêm seus próprios bancos temporários. A migração operacional é uma operação separada, com backup consistente e comparação de todos os dados antigos, sem registros sintéticos.


## Anexos sintéticos, etapa 05A

TemporaryReceiptStorage verifica a concessão ativa do SQLite antes de criar seu diretório quando testing_enabled está ativo. Cada fixture mantém anexos em subpasta temporária da própria concessão. A aplicação fecha o armazenamento no teardown, antes de a fixture limpar o banco. Não existe caminho de armazenamento persistente configurável ou uso de assets para anexos. Os testes usam somente PNG/PDF e metadados sintéticos e exercitam recusa de caminho operacional, quota, checksum, falha e rollback.

A execução integral desta rodada teve seu relatório interrompido por um identificador de teste excessivo. Não houve remoção ampla de temporários após a interrupção. Consulte validacao-etapa05a.md para os resultados e a correção pontual.
