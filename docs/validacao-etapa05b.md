# Validação da etapa 05B

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


## Resultado final

Em 02/11/2026, a suíte integral foi executada uma única vez após a implementação:

- **400 aprovados, 0 falhas, 0 erros, 2 avisos**, em **362,57 segundos**.
- Código de saída 0.
- Os 361 cenários anteriores foram preservados e 39 cenários específicos foram adicionados.
- Os dois avisos são depreciações conhecidas do TestClient/HTTPX e do alias BlockingPortal no AnyIO.

Comando: .venv/Scripts/python.exe -B -m pytest -v -p no:cacheprovider --tb=short.

Stdout e stderr foram gravados diretamente em arquivo, sem limite de captura em memória: relatório integral (`artifacts/stage05b/full-suite.log`, não distribuído).

Antes da suíte integral, a rodada específica inicial aprovou 37 testes, com 2 avisos, em 63,72 segundos: relatório específico (`artifacts/stage05b/specific-tests.log`, não distribuído). A revisão acrescentou dois casos de consistência e segurança, aprovados em uma execução focada de 3,57 segundos, com 2 avisos: relatório focado (`artifacts/stage05b/focused-consistency-tests.log`, não distribuído). A suíte integral posterior inclui todos os 39 casos; não se somam essas rodadas ao total de 400 como se fossem cenários diferentes. A suíte integral não foi repetida.

## Persistência confirmada

O teste test_app_restart_recovers_confirmed_attachment passou: uma aplicação salva o PNG sintético, encerra o lifespan e fecha o adaptador; uma nova aplicação abre o mesmo banco e volume temporários, autentica a identidade sintética e baixa exatamente os mesmos bytes. O ID do volume é preservado e o histórico não é duplicado.

Também passaram testes de disco indisponível, publicação interrompida, arquivo incompleto, checksum, duplicidade, colisão física sem sobrescrita, falha transacional com compensação, falha de compensação recuperada por quarentena/purga e limpeza de journal após commit. Uma falha de journal após commit não remove arquivo confirmado.

## Autorização e exclusão

Passaram acesso sem sessão, consulta de outra missão, acesso de outro autor da mesma missão, download privado, CSRF, confirmação de exclusão, versão antiga, intenção de exclusão gravada antes da remoção, retomada de exclusão pendente e histórico do responsável. Despesas continuam sintéticas e o financiamento dos quatro participantes permanece independente do acesso.

Configuração sem ativação explícita, domínio/cliente pendente, acesso local sem identidade, produção, caminho relativo, diretório público/no projeto, diretório genérico, escape da concessão de testes, links no caminho, marcador de outro volume e concorrência pelo mesmo volume foram recusados. A mera existência de diretório não ativa o serviço.

## SQLite, migração e isolamento

006_receipt_storage.sql foi validada exclusivamente em bancos temporários ou em memória. O teste test_idempotent_migration_and_sync_success_is_impossible passou, repetindo a migração, verificando seis versões, integridade SQLite e ausência de violações de FK. Estados remotos de sucesso e referência Drive fictícia são recusados pelas restrições do banco.

As proteções de tests/conftest.py ativam isolamento antes de importar a aplicação, não carregam .env e recusam bancos persistentes. Os volumes locais de teste ficam dentro das mesmas concessões temporárias dos bancos. Foram utilizados somente metadados, contas e PNG/PDF sintéticos. Nenhuma conta Google real foi acessada.

A comparação de SHA-256, tamanho e data de modificação confirmou a preservação de data/secco.sqlite3, .env operacional, migrações 001 a 005 e arquivos protegidos de agenda/Diário. Não foi aplicada migração ao banco operacional ou feita escrita de teste nele. Nenhum caminho de armazenamento operacional foi ativado.

## Verificações e limites

Sintaxe Python, todos os templates Jinja2 e as seis migrações em memória passaram nas verificações estáticas, com integrity_check=ok e foreign_key_check vazio. Não foi necessário instalar dependências. Não houve teste de navegador ou dispositivo físico, servidor persistente, serviço externo, deploy, commit ou push. Não há repositório ou checkpoint Git nesta pasta.

O resultado cobre reinício de aplicação, integridade e falhas simuladas em armazenamento temporário de testes. Não certifica apagamento forense, ACLs Windows completas, criptografia, restauração de backup, filesystem de rede ou sobrevivência a perda física/queda de energia. A implantação e o backup continuam pendentes, assim como a validação do login real e dos documentos aplicáveis. O modo de comprovantes reais e a produção permanecem bloqueados.

Configuração, permissões, reconciliação, manutenção e estratégia futura de backup estão em [armazenamento de comprovantes](armazenamento-comprovantes.md).
