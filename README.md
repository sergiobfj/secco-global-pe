# SECCO Global PE

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


> **Distribuição pública.** Dados pessoais, identificadores do Google Workspace/Drive/Cloud e artefatos operacionais foram substituídos por valores fictícios ou removidos. Nenhuma licença de código aberto é concedida.


Aplicação local para operar as missões internacionais da SECCO. Python 3.12, FastAPI, SQLite, Jinja2 e JavaScript puro. A visão Hoje continua sendo a entrada da missão escolhida, com a agenda antes dos indicadores.

## Funcionalidades

- Marca oficial, favicon e fontes locais; navegação responsiva.
- Portugal e Argentina, quatro participantes e metas aprovadas.
- Agenda diária, sugestões sem data, criação, edição, cancelamento e histórico.
- Diário profissional com seis tipos, rascunhos, atividades realizadas e canceladas.
- Registrar resultado a partir de um compromisso, aproveitando seus dados e preservando um vínculo único.
- Metadados de evidências e classificação explícita para metas, com validação manual e controle de versões.
- Reuniões realizadas, qualificadas, LOIs/manifestações, atividades recentes e rascunhos pendentes.
- CSRF, validação no servidor, idempotência e proteção contra edição concorrente.
- Bancos de testes exclusivamente temporários, com bloqueio de caminhos persistentes.

Não há autenticação, upload, cadastro financeiro, sincronização offline ou publicação. Uma referência externa conferida não significa que o aplicativo armazenou ou verificou o arquivo automaticamente.

## Executar localmente

Para instalação nova, em PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8002 --no-proxy-headers
```

Abra http://127.0.0.1:8002. Encerre seu servidor pelo terminal com Ctrl+C. Nesta máquina, a versão anterior na porta 8001 foi preservada; não tente encerrar à força o processo antigo da porta 8000. A nova etapa usa 8002 para revisão local.

O ambiente virtual, .env e SQLite desta entrega já estão preparados. Para iniciar novamente basta o comando uvicorn. Não substitua um .env existente sem revisar. A aplicação aplica migrações pendentes no startup, sem apagar o banco.

Em Linux/macOS, use python3.12, .venv/bin/python e o mesmo comando de uvicorn. Não use Docker. As dependências de runtime continuam as mesmas, sem frameworks de frontend ou bibliotecas de upload.

## Configuração e segurança

| Variável      | Valor local                                              |
| ------------- | -------------------------------------------------------- |
| APP_ENV       | development                                              |
| DEV_NO_AUTH   | true                                                     |
| DATABASE_PATH | data/secco.sqlite3, relativo à raiz, ou caminho absoluto |

A aplicação recusa produção e exige autorização explícita para desenvolvimento sem login. Cada POST valida a configuração, CSRF e origem. Somente clientes loopback e hosts locais são aceitos. Use 127.0.0.1 e --no-proxy-headers, sem túnel ou publicação.

A missão lembrada por cookie é uma preferência, sem autenticação nem autorização. As declarações de conferência de evidências e validação da coordenação são manuais; os nomes ainda não representam identidades autenticadas. Não use dados financeiros reais.

A interface foi validada em viewports móveis, mas o servidor não está aberto à rede do celular. Acesso de aparelhos reais e uso compartilhado dependem de autenticação e autorização futuras.

## Registrar uma atividade

1. Abra um compromisso profissional na agenda e toque em Registrar resultado.
2. Revise os dados aproveitados e selecione o tipo da atividade.
3. Preencha O que aconteceu e Resultados obtidos. Escolha Realizada somente quando a atividade tiver ocorrido.
4. Toque em Salvar registro.

Também é possível usar Diário → Registrar atividade para um registro sem compromisso anterior. Rascunho permite salvar preenchimento incompleto e completar depois. O status Realizada exige título, data, descrição e resultados; horário permanece opcional.

A missão, título, data, horário, organização, local e participantes conhecidos são aproveitados da agenda. O vínculo é explícito e único. Reabrir Registrar resultado leva ao registro existente. Turismo não oferece essa conversão. Salvar o Diário não altera automaticamente o status do compromisso.

Uma edição conserva o histórico e invalida classificações anteriores. Cancelar é uma alteração de status, sem exclusão física. Erros mantêm os campos, inclusive com JavaScript desabilitado. Fechar ou recarregar um formulário ainda não salvo pode perder o preenchimento.

## Metas e evidências

Portugal: 10 reuniões qualificadas e 3 LOIs. Argentina: 8 reuniões qualificadas e 3 manifestações formais de interesse.

Uma reunião realizada aparece no indicador de realização, mas não se torna qualificada automaticamente. Para contar em uma meta, o registro precisa estar Realizada, possuir classificação justificada, referência do critério da proposta ou orientação da coordenação, aprovação manual informada e evidência correspondente com referência externa conferida.

Não há critérios de qualificação inventados ou pré-configurados. Sem orientação/documento verificável, mantenha Pendente de validação. LOI exige carta de intenção; manifestação exige documento, carta ou confirmação institucional correspondente. Rascunhos, cancelamentos, classificações pendentes e registros sem comprovação não entram nas metas finais.

Referenciar evidência cadastra somente tipo, título, identificação e, quando existente, link HTTPS. Não envia arquivos. A conferência exige referência, identificador, responsável e nota do que foi conferido. A aprovação fica vinculada à versão do registro e da evidência. Alterações exigem nova revisão. Veja [Diário e metas](docs/diario-e-metas.md).

## Banco e migrações

SQLite é a fonte da verdade. As migrações 001 e 002 permanecem byte a byte iguais. A nova 003_diary.sql é aditiva: acrescenta organização à agenda, cria Diário, participantes, evidências, classificações, histórico e a visão de resultados elegíveis. Não cadastra atividades realizadas ou evidências de demonstração.

A inicialização e a carga são idempotentes:

```powershell
.\.venv\Scripts\python.exe -m scripts.init_db
```

As 20 atividades previstas da etapa anterior continuam preservadas. Datas ou confirmações não são inventadas. As tabelas legadas mission_events e mission_results permanecem intactas. Os antigos contadores sem classificação não são usados como resultados comprovados; os indicadores finais consultam eligible_goal_claims.

Antes da migração operacional da etapa 3, foi criado backup consistente em .tools/backups/etapa2-before-stage3.sqlite3. Não apague o banco ou edite migrações já aplicadas. Novas alterações de esquema devem usar um próximo arquivo versionado.

## Datas e fusos

- Portugal: Europe/Lisbon, 09 a 20/11/2026.
- Argentina: America/Argentina/Buenos_Aires, 16 a 23/11/2026.
- Consulta de datas fora do período oficial para planejamento de exemplo.

Hoje usa o fuso da missão. Datas e horários do Diário também pertencem a esse fuso. Horários inválidos ou ambíguos são recusados. A agenda mantém representação UTC para compromissos com horário. O Diário mantém o fato em data e horário locais opcionais, com fuso obtido da missão.

## Estrutura

```text
app/
  main.py, models.py
  core/              configuração, CSRF, política de testes
  db/                conexão, migrações 001/002/003 e carga inicial
  repositories/      missions.py, itinerary.py, diary.py
  services/          validação, apresentação, fusos e regras de elegibilidade
  routers/           web.py, api.py, planning.py, diary.py
  templates/         páginas e componentes reutilizáveis
  static/            marca oficial, fontes, CSS e JavaScript locais
data/                SQLite operacional, ignorado pelo Git
scripts/             inicialização e QA com banco temporário
tests/              regressão, isolamento, agenda, Diário e metas
docs/               arquitetura, regras e validação
artifacts/           capturas e relatórios locais
```

Consulte o inventário de [arquivos da etapa 3](docs/arquivos-etapa3.md).

## Rotas do Diário

| Rota                                                        | Uso                                        |
| ----------------------------------------------------------- | ------------------------------------------ |
| /                                                           | Hoje da missão padrão ou seleção           |
| /?selecionar=1                                              | Seleção de missão                          |
| /missoes/{codigo}/planejamento                              | Agenda diária                              |
| /missoes/{codigo}/diario                                    | Lista e filtros por status                 |
| /missoes/{codigo}/diario/novo                               | GET do formulário e POST de criação        |
| /missoes/{codigo}/diario/novo?agenda={id}                   | Preenchimento com compromisso profissional |
| /missoes/{codigo}/diario/{id}                               | Detalhes                                   |
| /missoes/{codigo}/diario/{id}/editar                        | GET e POST de edição                       |
| /missoes/{codigo}/diario/{id}/evidencias/nova               | Referenciar evidência                      |
| /missoes/{codigo}/diario/{id}/evidencias/{evidencia}/editar | Revisar metadados                          |
| /missoes/{codigo}/diario/{id}/metas/nova                    | Classificar resultado                      |
| /missoes/{codigo}/diario/{id}/metas/{classificacao}/editar  | Rever classificação                        |

Prestação de Contas, Organização e Documentos continuam em desenvolvimento.

## Testes isolados

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q app scripts tests
```

Resultado final: **203 testes aprovados**, com dois avisos de depreciação já conhecidos do TestClient/AnyIO. Foram validados também **68 layouts no navegador**, em 360, 390, 768 e 1280 px.

O pytest não carrega .env. Cada fixture recebe uma concessão temporária exclusiva. Um DATABASE_PATH explícito que aponte a banco operacional ou persistente faz os testes falharem antes da inicialização. Não basta chamar um arquivo de teste.sqlite3. A política também protege conexões SQLite diretas, ATTACH e alterações de arquivos do diretório operacional no processo de testes.

Ao terminar, somente diretórios temporários com propriedade validada são removidos; conexões são fechadas antes. Em caso de encerramento abrupto, um diretório temporário pode permanecer, sem habilitar limpeza ampla de pastas. Veja [isolamento de testes](docs/isolamento-testes.md).

## QA no navegador

```powershell
# Terminal 1, banco temporário com identidade exclusiva
.\.venv\Scripts\python.exe -m scripts.serve_qa --port 8057

# Terminal 2, módulo Playwright já disponível para QA
node scripts/qa-diary.cjs C:\caminho\node_modules\@playwright\test

# Inicie um novo helper antes de executar a regressão anterior
node scripts/qa-responsive.cjs C:\caminho\node_modules\@playwright\test
```

Aguarde o terminal do helper informar Uvicorn running antes de executar o script. Cada script encerra o helper ao terminar; inicie outro helper para a próxima execução.

Os scripts leem .tools/qa-current.json e verificam a concessão antes de qualquer escrita. Recusam servidores operacionais, portas 8000/8001/8002 e destinos diferentes do manifesto. Um cabeçalho exclusivo identifica todas as requisições de QA. O servidor operacional recusa clientes assim identificados. O helper encerra de forma controlada no final e limpa seu banco temporário.

Playwright é ferramenta opcional de QA, sem dependência no runtime. Nesta máquina o módulo está no projeto irmão seccolp. Para outra máquina, instale em diretório de ferramentas, se necessário, e informe o caminho absoluto. O navegador padrão é Microsoft Edge; QA_BROWSER_PATH permite outro executável Chromium. QA_BASE_URL precisa corresponder ao manifesto criado pelo helper.

Capturas da nova etapa em artifacts/stage3/; regressão em artifacts/stage2/. Capturas cujo nome começa com qa usam dados sintéticos identificados, exclusivamente no banco temporário. Veja [validação da etapa 3](docs/validacao-etapa3.md).

## Documentação e limites

A marca oficial e sua origem estão em [identidade SECCO](docs/identidade-secco.md). Consulte [arquitetura](docs/arquitetura.md), [Diário e metas](docs/diario-e-metas.md) e [registro rápido futuro](docs/ux-registro-rapido.md).

Não há cache de dados, fila offline, upload ou verificação automática do conteúdo dos documentos. O manifesto prepara a PWA sem prometer instalação completa. Testes em viewports não substituem validação física Android/iOS. Sem autenticação, as declarações de responsáveis são registros manuais e não trilha de auditoria com identidade certificada.

Próximas etapas: fornecer os critérios aprovados para validação da coordenação, autenticação real com autorização por missão, evidências no Shared Drive e, depois, módulo financeiro com checklist próprio. Não houve deploy, commit, push ou integração de contas externas.
