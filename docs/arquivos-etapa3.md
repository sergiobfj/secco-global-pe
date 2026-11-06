# Arquivos da etapa 3

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


Inventário do código e documentação. As migrações 001 e 002, marca oficial, fontes, dependências, .env e regras financeiras foram preservadas. Não há repositório Git nesta pasta, portanto a comparação de app/ e tests/ usou o snapshot local anterior à etapa 3.

| Arquivo                                     | Situação |
| ------------------------------------------- | -------- |
| app/core/config.py                          | Alterado |
| app/core/forms.py                           | Alterado |
| app/core/test_database.py                   | Novo     |
| app/db/connection.py                        | Alterado |
| app/db/migrate.py                           | Alterado |
| app/db/migrations/003_diary.sql             | Novo     |
| app/main.py                                 | Alterado |
| app/repositories/diary.py                   | Novo     |
| app/repositories/itinerary.py               | Alterado |
| app/repositories/missions.py                | Alterado |
| app/routers/diary.py                        | Novo     |
| app/routers/planning.py                     | Alterado |
| app/routers/web.py                          | Alterado |
| app/services/diary.py                       | Novo     |
| app/services/itinerary.py                   | Alterado |
| app/static/css/diary.css                    | Novo     |
| app/static/js/app.js                        | Alterado |
| app/templates/activity_detail.html          | Alterado |
| app/templates/activity_form.html            | Alterado |
| app/templates/base.html                     | Alterado |
| app/templates/components/activity.html      | Alterado |
| app/templates/components/diary_fields.html  | Novo     |
| app/templates/components/diary_summary.html | Novo     |
| app/templates/dashboard.html                | Alterado |
| app/templates/diary.html                    | Novo     |
| app/templates/diary_detail.html             | Novo     |
| app/templates/diary_form.html               | Novo     |
| app/templates/planning.html                 | Alterado |
| tests/conftest.py                           | Alterado |
| tests/test_database.py                      | Alterado |
| tests/test_database_isolation.py            | Novo     |
| tests/test_diary.py                         | Novo     |
| tests/test_missions.py                      | Alterado |
| tests/test_web.py                           | Alterado |
| scripts/serve_qa.py                         | Alterado |
| scripts/qa-responsive.cjs                   | Alterado |
| scripts/qa-guard.cjs                        | Novo     |
| scripts/qa-diary.cjs                        | Novo     |
| README.md                                   | Alterado |
| docs/arquitetura.md                         | Alterado |
| docs/diario-e-metas.md                      | Novo     |
| docs/isolamento-testes.md                   | Novo     |
| docs/validacao-etapa3.md                    | Novo     |
| docs/arquivos-etapa3.md                     | Novo     |

## Artefatos locais

- artifacts/stage3/: 36 capturas, relatório do Diário, verificações Python/JS, integridade SQLite, disponibilidade e inventário de código.
- artifacts/stage2/: 32 capturas e relatório da regressão executada novamente nesta etapa.
- .tools/backups/etapa2-before-stage3.sqlite3: backup consistente anterior à migração 003.
- .tools/backups/stage3-before.json: snapshot local dos dados anteriores para comparação lógica.
- .tools/stage3-server.log: log do servidor novo na porta 8002.
- data/secco.sqlite3: atualização aditiva de esquema, sem registros sintéticos.

Os artefatos, backups e banco continuam locais e ignorados pelo Git. As capturas com prefixo qa têm dados sintéticos somente do banco temporário; não são resultados de missão.
