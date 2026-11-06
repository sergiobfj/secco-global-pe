# Validação da etapa 05A

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


## Resultado final

Validação concluída em 02/11/2026, em uma única execução integral nesta rodada, diretamente no ambiente virtual do projeto:

- 361 testes aprovados, incluindo os 289 cenários anteriores e 72 novos.
- 0 falhas, 0 erros e 2 avisos.
- Duração informada pelo pytest: 115,67 segundos.
- Código de saída: 0.

Comando: .venv/Scripts/python.exe -B -m pytest -v -p no:cacheprovider.

A saída completa de stdout e stderr foi redirecionada diretamente para um arquivo, sem captura limitada em memória ou truncamento do console: relatório integral (`artifacts/stage05a/pytest-integral-2026-11-02T12-22-53-837Z.log`, não distribuído). Nenhum teste foi repetido nesta rodada. Não houve alteração de código ou de configuração.

Os dois avisos são depreciações do TestClient/HTTPX e do alias BlockingPortal no AnyIO. Não representam falhas da suíte.

## Isolamento e migração 005

As proteções existentes de tests/conftest.py foram verificadas: o modo de isolamento é ativado antes da importação da aplicação, caminhos persistentes explícitos são recusados e o .env operacional não é carregado. Os testes utilizaram exclusivamente SQLite em memória ou bancos em concessões temporárias. Os anexos sintéticos ficaram em diretórios temporários subordinados a essas concessões.

O teste tests/test_receipts.py::test_migration_integrity_and_no_duplicate_seed passou. Ele inicializa a aplicação com banco temporário, verifica cinco migrações aplicadas, repete a migração de modo idempotente, preserva a despesa sintética e confirma PRAGMA integrity_check=ok e foreign_key_check sem violações. Assim, 005_receipts.sql foi validada em banco temporário, sem aplicação ao banco operacional.

## Preservação do ambiente

Antes e depois da suíte, foram comparados SHA-256, tamanho e data de modificação de 470 arquivos preexistentes inspecionados no projeto, excluindo o ambiente virtual e caches. Nenhum desses arquivos foi modificado pela execução, incluindo data/secco.sqlite3, .env e as migrações existentes.

A localização do armazenamento de comprovantes foi verificada no código. Não havia diretórios secco-receipts-* preexistentes no temporário do sistema ou nas concessões de teste existentes. Os arquivos preexistentes inspecionados no projeto também permaneceram iguais. Nenhum comprovante existente foi alterado.

Após a aprovação, somente este documento foi atualizado. O único arquivo novo da rodada é o relatório integral solicitado. README, relatórios históricos, código, testes e configurações foram preservados.

Não houve instalação, download, teste de navegador, início de servidor, configuração externa, deploy, commit ou push. A migração operacional não foi executada.

## Histórico e limites

A tentativa anterior havia sofrido erro por um identificador de parâmetro que incorporava os 5 MB de um arquivo sintético, excedendo o limite de variável de ambiente do Windows e truncando o relatório. O identificador já havia sido corrigido antes desta rodada. A execução integral atual, com 361 aprovações, encerra a pendência de validação automatizada.

Este resultado não valida contas Google reais, integração com Drive, câmera física ou layout em navegador. A aplicação continua local e a captura permanece exclusivamente sintética e temporária, sem autorização para comprovantes financeiros reais ou promessa de armazenamento durável.
