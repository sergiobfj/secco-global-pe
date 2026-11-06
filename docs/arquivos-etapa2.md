# Arquivos da etapa 2

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


> **Distribuição pública:** nomes, e-mails, domínio Google Workspace, IDs de Drive/pastas e identificadores Google Cloud deste documento são fictícios. Resultados e decisões descritos referem-se ao projeto operacional.


## Backend

Alterados:
- app/main.py: registro do módulo, inicialização e política de referência compatível com POST nativo.
- app/routers/web.py: preferência de missão, Hoje e compatibilidade dos links anteriores.
- app/services/missions.py: composição operacional da visão Hoje.
- app/db/seed.py: nome Alan Renato e chamada da carga de planejamento.

Novos:
- app/core/forms.py: parser limitado, CSRF e verificação de origem.
- app/routers/planning.py: agenda, formulários, detalhes, gravação e cancelamento.
- app/services/itinerary.py: validação, fusos, dias e apresentação.
- app/repositories/itinerary.py: persistência, concorrência, histórico e importação legada.
- app/db/seed_itinerary.py: informações conhecidas da etapa.
- app/db/migrations/002_itinerary.sql: evolução aditiva.

## Interface e assets

Alterados:
- app/templates/base.html, home.html e dashboard.html.
- app/static/css/app.css, com aplicação da marca.
- app/static/js/app.js.
- app/static/manifest.webmanifest.
- app/static/icons/app.svg, substituído pelo favicon oficial.

Novos:
- app/templates/planning.html.
- app/templates/activity_form.html.
- app/templates/activity_detail.html.
- app/templates/components/activity.html.
- app/static/css/agenda.css.
- app/static/brand/secco-logo-horizontal-cream.svg.
- app/static/brand/secco-logo-horizontal-forest.svg.
- app/static/brand/secco-symbol-cream.svg.
- app/static/brand/secco-symbol-forest.svg.

## Testes, ferramentas e documentação

Alterados:
- tests/test_database.py e tests/test_web.py, mantendo os cenários anteriores.
- scripts/qa-responsive.cjs.
- README.md.
- docs/arquitetura.md.
- docs/validacao.md.

Novos:
- tests/test_itinerary.py.
- scripts/serve_qa.py.
- docs/identidade-secco.md.
- docs/ux-registro-rapido.md.
- docs/arquivos-etapa2.md.

A primeira migração, os modelos de missão, as dependências Python e as regras de metas permanecem preservados. SQLite foi atualizado aditivamente. Backups e artefatos de execução estão em .tools/ e artifacts/, ignorados pelo Git.
