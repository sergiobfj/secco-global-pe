# Validação 07C — preparação, sem ensaio real

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


> **Distribuição pública:** nomes, e-mails, domínio Google Workspace, IDs de Drive/pastas e identificadores Google Cloud deste documento são fictícios. Resultados e decisões descritos referem-se ao projeto operacional.


Revisão atual de menor privilégio: o plano foi alterado para `drive.file` + `drive.metadata.readonly`, com `files.get` dos Folder IDs conhecidos e sem `drives.get`. Os 173 testes abaixo são o registro da preparação anterior; o resultado da revisão está em [validacao-etapa07c-menor-privilegio.md](validacao-etapa07c-menor-privilegio.md).

## Resultado

**173 testes relevantes aprovados, zero falhas, zero erros, 49 não selecionados e dois avisos de depreciação existentes**, em **36,53 segundos**. São 56 cenários novos da 07C, 113 de mapeamento da 07B e quatro regressões de configuração da 07A. Não se reexecutou a suíte integral, pois esta etapa não autoriza a migração 008, inclusive nas fixtures antigas que a aplicariam em temporário.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_drive_probe.py tests/test_drive_folder_mapping.py tests/test_google_drive_sync.py -q -k 'not test_google_drive_sync or invalid_configuration' -p no:cacheprovider
```

Log: `artifacts/stage07c/targeted-tests.log`. Os avisos são de Starlette/httpx e anyio, já presentes. Não houve instalação de dependência.

Após a revisão final das variáveis do processo fonte, o teste de captura gcloud foi reexecutado: **1 aprovado**, 55 não selecionados, dois avisos existentes, em 0,33 s. Ele confirma também que impersonação e rastreamento do ambiente não são herdados implicitamente. Log: `artifacts/stage07c/source-credentials-check.log`. Não houve gcloud real; o subprocesso foi simulado.

## Cobertura e evidências

- Os 14 destinos e os nomes exatos permanecem verificados contra a tabela da 07B; troca entre missões/categorias, ID/nome divergente, ausência, MIME, lixeira e raiz errados são recusados.
- Aprovação ausente, expirada, sem confirmação sintética/backup, para outro mapa/plano ou com escopo inadequado bloqueia o transporte. A conta fonte não pode ser conta de serviço baseada em chave. O teste não utiliza credenciais reais.
- HTTP real é substituído por `MockTransport`. Os novos testes também recusam `socket.connect` real. SDK é substituído por stub; captura de stdout em memória, ausência de login, remoção de overrides de credenciais e logs desativados são conferidos.
- IAM Credentials é simulado: token de 900s, escopos exatos, cache, renovação após expiração, proteção de `repr`/logs e falhas controladas de permissão/API desativada, sem escalada.
- Preflight confere ACLs e `canAddChildren`; público e falta de capacidade bloqueiam antes da criação.
- Dois PNGs determinísticos, um por missão, usam exatamente dois IDs. Repetições não criam novos objetos; corpo alterado, outra pasta, nome ou MIME são recusados antes do transporte interno.
- 401, 403, 429, 500, redirect, timeout e interrupção são exercitados. Hash ausente mantém erro; posterior confirmação usa o mesmo ID.
- Reserva fica no SQLite e no ZIP antes do POST. Falha de backup bloqueia criação. Interrupções antes do envio e depois da criação simulada são recuperadas com o ID original, sem duplicata.
- Backup usa SQLite Backup API e restaura estado, IDs, PNGs e marcador. Conferências SQLite retornam `integrity_check=ok` e `foreign_key_check` vazio. Não existe tabela de migrações no schema próprio do ensaio.
- Arquivo incompleto, adulterado, marcador incompatível, mapa diferente e traversal são recusados. O lock recusa execução concorrente no mesmo arquivo de recuperação.
- A regressão do worker anterior foi corrigida/testada com schema mínimo escrito diretamente em SQLite temporário: duas tentativas depois de uma confirmação seguida de ausência remota nunca chamam upload. Nenhuma migração foi executada.
- DELETE, PATCH, criação de permissões, lista ampla, download, host externo, HTTP sem TLS e `useDomainAdminAccess` são bloqueados pelo transporte de ensaio.

## Preparação e restauração offline realizadas

Além dos testes, o plano concreto foi preparado com o executor offline:

```powershell
.venv/Scripts/python.exe -m scripts.drive_probe --mapping artifacts/stage07b/mapping/folders.json --archive artifacts/stage07c/probe-prepared.zip
.venv/Scripts/python.exe -m scripts.drive_probe --mapping artifacts/stage07b/mapping/folders.json --archive artifacts/stage07c/probe-prepared.zip --resume
```

Ambos terminaram com sucesso, sem rede/credenciais. `offline-plan.json` e `offline-restore.json` coincidem nos hashes e itens. O ZIP contém apenas `probe.sqlite3`, `.volume.json`, `argentina.png`, `portugal.png` e `manifest.json`; os dois PNGs têm 69 bytes. Os IDs remotos do plano preparado permanecem nulos. O `.zip.lock` é apenas coordenação local, sem credenciais.

| Missão | Nome fictício preparado | Destino |
|---|---|---|
| Argentina | `secco-ensaio-77d0936125e58eb2-argentina.png` | Deslocamento / `1EXEMPLO_AR_deslocamentos_0000000` |
| Portugal | `secco-ensaio-77d0936125e58eb2-portugal.png` | Deslocamentos / `1EXEMPLO_PT_deslocamentos_0000000` |

O modelo de aprovação está pendente (`approved=false`, `backup_verified=false`, operador/validade por preencher) e vinculado a esse plano. Seu JSON é uma declaração de autorização **sem credenciais**, não uma chave de conta de serviço.

## Preservação

SQLite operacional, `.env` e migrações 001–008 mantêm os SHA-256 anteriores à execução. O `.env` não foi carregado ou alterado; apenas seu fingerprint binário foi comparado, sem expor conteúdo. Não houve conexão SQLite ao banco operacional, migração, startup/reinício operacional, chave JSON, login interativo, acesso a credencial operacional, alteração de Drive/IAM/ACL, deploy, commit ou push.

O modo de operação e o exemplo permanecem `RECEIPTS_DRIVE_MODE=disabled`. A leitura das páginas públicas de documentação oficial para revisar APIs não foi uma chamada autenticada à API Drive. O contador de chamadas reais às APIs IAM/Drive nesta etapa é zero.

## Arquivos

Novos:

- `app/services/drive_supervised.py`: aprovação, escopos, fonte gcloud supervisionada, token IAM em memória e transporte/adapter do ensaio.
- `app/services/drive_probe.py`: plano sintético, lock, schema temporário próprio, checkpoint/restore e reconciliação do ensaio.
- `scripts/drive_probe.py`: CLI offline por padrão; entrada real exige aprovação válida e `--resume --execute-authorized`.
- `tests/test_drive_probe.py`: 56 cenários desta etapa, sem migrações.
- `docs/ensaio-supervisionado-drive.md`: auditoria, fontes, checklist e procedimento exato.
- `docs/drive-probe-approval.example.json`: modelo pendente de aprovação, sem token/chave.
- Este relatório e os artefatos em `artifacts/stage07c/`: log, plano/restore offline, ZIP, lock e `validation.json`.

Alterados:

- `app/services/google_drive_storage.py`: preflight opcional de capacidade e aceitação de caracteres válidos de bearer token; construtor operacional continua restrito a mocks.
- `app/services/receipt_drive_sync.py`: histórico impede recriar objeto já confirmado após falha/ausência.
- `README.md` e `docs/integracao-google-drive.md`: ponte para a preparação 07C e distinção entre ensaio independente e operação.

## Prontidão, limites e próxima autorização

O transporte real e o fornecedor temporário estão **tecnicamente preparados para o ensaio restrito**, mas seu funcionamento contra Google ainda não foi validado. SDK, conta fonte, IAM, APIs, scopes, ACLs, quotas, rede e disponibilidade de SHA-256 precisam ser conferidos no ambiente aprovado. O SDK não está sendo instalado nem autenticado nesta entrega.

Os testes comprovam restauração do bundle sintético; não substituem validação de backup/restauração operacional, segurança do host, autenticação contínua da VPS, criptografia, retenção ou durabilidade contra falha física. Perda de um backup/journal mais recente que o estado remoto exige revisão administrativa, sem reinicialização de IDs. Limpeza remota não está implementada/autorizada e pode exigir outro papel; não promover Colaborador para esse fim.

O modelo revisado aceita somente `drive.file` + `drive.metadata.readonly`. Não usa `drives.get` e rejeita os escopos anteriores mais amplos. O upload sob as pastas existentes é compatibilidade pendente de validação real; qualquer falha interrompe sem ampliar escopos. Não se presume que o sucesso de leitura na 07B já autorize escrita ou configure autenticação da VPS.

**Parada obrigatória antes da escrita:** o próximo passo é o responsável aprovar o [checklist e procedimento](ensaio-supervisionado-drive.md), os dois destinos/PNGs, os escopos/conta fonte, a janela e a retenção. O comando real não foi executado. Produção continua fora do escopo.
