# Distribuição pública — estado 08 de 14

Esta cópia usa dados de exemplo e está separada da aplicação operacional. Países, eventos do programa e ativos de marca foram mantidos. Participantes, contas e identificadores de serviços são fictícios; a observação operacional sobre extensão de viagem foi retirada do seed e da documentação. Nenhuma licença de código aberto foi adicionada.

## Instalação e ambiente

Use Python 3.12, crie um venv e instale `requirements-dev.txt`. Copie `.env.example` para um `.env` local somente se necessário. Configure `DATABASE_PATH` para um banco novo dentro desta cópia. Segredos ficam vazios no exemplo e nunca devem ser versionados. IDs de exemplo não apontam para os Drives operacionais e não habilitam envio.

A autenticação exige configuração OIDC autorizada; sem credenciais, o login e os dados protegidos ficam bloqueados. Configurações fictícias não permitem login Google real. Não use o modo sem autenticação como evidência de autorização.

## Migrações

A migração 002 pública substitui nomes por fictícios e tem checksum `6bcc1590e154633781746fcd901b899ef016b77b499211e7c9bed91dafa77b5b`. O conteúdo difere da 002 operacional: use somente um banco novo desta distribuição. O migrador recusa checksum incompatível. Nunca aponte esta distribuição para um banco operacional existente.

## Testes desta composição

Execute `python -m pytest -q -p no:cacheprovider -rfEs` na raiz do estado, com as dependências instaladas. Os testes usam bancos temporários e identidades/HTTP simulados.

Execução desta distribuição, estado 08: **469 aprovados, 0 ignorados, 0 falhas e 0 erros**, saída 0. As contagens incluem a suíte integral coletada neste estado; testes ignorados não contam como aprovados. Quando houve sanitização textual posterior da agenda, seus testes de renderização e agenda foram executados novamente, sem alterar a lógica Python.

### Testes ignorados

Não há módulos do executor portátil neste estado.

## Proveniência e etapas

Os estados 01–03 reutilizam snapshots preservados. Os estados 04–09 recuperam versões de arquivos registradas nas sessões de desenvolvimento, com a mesma sanitização pública e recomposição de versões completas. Os estados seguintes agrupam o código existente por funcionalidade e trazem as dependências necessárias com seus consumidores. Estes são estados preparados agora para publicação, sem datas retroativas ou alegação de reproduzir cada instante operacional.

Funcionalidade desta etapa: `fix(auth): recover interrupted OAuth callbacks and access denials`. Cada commit futuro será criado somente após autorização, com a data real da criação e autoria confirmada.

## Validação operacional e validação pública

Os documentos históricos registram testes e decisões operacionais de cada etapa. O responsável informou a validação posterior do executor Cloud Shell v4, com dois uploads sintéticos e repetição idempotente. Esse relato não é apresentado como execução desta distribuição; seus IDs e evidências privadas não são distribuídos. Nesta preparação, não há chamada ao Google Drive, alteração IAM/ACL ou deploy. A aplicação mantém o envio real desativado.

## Artefatos ausentes

Os artefatos operacionais, bancos, `.env`, credenciais, logs, aprovações, checkpoints, journals, backups e ZIPs de evidência ficam fora do repositório. Logs locais podem ser gerados com `python -m pytest`. Capturas de QA exigem Node/Playwright e os scripts de QA presentes neste estado; consulte o README. Não inclua os artefatos gerados no Git.

