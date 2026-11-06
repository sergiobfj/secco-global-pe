# Etapa 07C — plano de ensaio supervisionado, ainda não autorizado

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


> **Distribuição pública:** nomes, e-mails, domínio Google Workspace, IDs de Drive/pastas e identificadores Google Cloud deste documento são fictícios. Resultados e decisões descritos referem-se ao projeto operacional.


Revisão de menor privilégio: somente `drive.file` + `drive.metadata.readonly`; `drives.get`, `drive.readonly` e `drive` não fazem parte do ensaio. Nenhuma chamada externa foi realizada nesta revisão.

## Estado da entrega

O transporte HTTP real está implementado **somente para um ensaio independente**, atrás de aprovação explícita, validade curta e hash do plano. Não foi executado. A aplicação, o worker `ReceiptDriveSync` e `GoogleDriveAdapter` normal continuam bloqueados para transporte real e `RECEIPTS_DRIVE_MODE=disabled` permanece intacto. Não há alteração de `.env`, banco operacional, migração 008, IAM, ACLs ou Drives. Não há deploy, commit ou push.

O comando padrão é offline. Ele não lê `.env`, não importa/inicializa FastAPI, não busca ADC, não usa login dos usuários e não executa migrações. Cria dois PNGs de 1×1 exclusivamente sintéticos e um SQLite próprio, dentro de concessão temporária. A recuperação é exportada em ZIP sem tokens. Nenhum anexo do volume operacional é lido.

Este ensaio testa o protocolo do adaptador, não a elegibilidade financeira ou a operação FACEPE. Os nomes `secco-ensaio-{run_id}-{missao}.png` identificam fixtures separadas; não se inventa processo FACEPE nem se gravam despesas, participantes ou permissões. O fluxo operacional de nomenclatura permanece inalterado.

## Auditoria e melhorias

| Item | Situação / medida |
|---|---|
| Mapeamentos | Os 14 IDs da 07B permanecem no exemplo e no mapa; os testes conferem uma transcrição independente. Argentina exige Deslocamento; Portugal, Deslocamentos. |
| Destino | `files.get` do Folder ID conhecido exige ID exato, `driveId` vinculado ao Drive ID confirmado da missão, pai único igual àquela raiz, nome exato por missão/categoria, MIME pasta e não excluído. Não usa nome de exibição do Drive como prova de identidade. |
| Permissões | Todas as páginas de ACL da raiz/pasta/arquivo são verificadas pela política anterior. O ensaio verifica também `capabilities.canAddChildren=true` antes de escrever. |
| Transporte | HTTPS e host Google fixos, timeout, TLS padrão, sem proxies/CA do ambiente, redirects ou retries automáticos. Sem PATCH, DELETE, compartilhamento, criação de pasta, lista ampla ou download. |
| Conteúdo | Apenas os dois PNGs determinísticos de 69 bytes produzidos pelo código. Corpo multipart, nome, MIME, pasta, missão, chave e ID são conferidos novamente antes do transporte interno. |
| Autorização | Referência do aceite, conta humana do operador, validade de até uma hora, escopos exatos, confirmação de dados sintéticos/backup, hashes do mapa e plano. Aprovação de outro plano não funciona. |
| Idempotência | Um ID por missão; reserva no SQLite e checkpoint durável antes do POST. Retry usa GET do mesmo ID e trata 409 sem novo ID. Até duas reservas por transporte. |
| Integridade | SHA-256 e tamanho locais; GET remoto confirma também nome, pasta, Drive, MIME, chave e ACL. Hash ausente/divergente produz erro, sem sucesso fictício. |
| Reconciliação | Depois de já verificado, objeto remoto ausente não é recriado automaticamente, nem após uma primeira falha. O histórico é consultado também no worker anterior. |
| Logs | Códigos controlados, sem corpo de erro, conteúdo ou token. URLs Google do HTTPX são suprimidas para evitar IDs/pageTokens em INFO. Fonte gcloud sem logs HTTP/arquivo. |
| Exclusão | Não há implementação de limpeza remota no ensaio. Aprovação `cleanup` só aceita `retain`. |

O componente `SupervisedProbeAdapter` reaproveita upload/verify/reserve da 07A; `ProbeHTTPTransport` acrescenta a restrição de escopo técnico do ensaio. Esse transporte tem capacidade real de rede depois de aprovado, mas não é conectado a `Settings`, FastAPI ou startup. A aprovação declarativa é um mecanismo contra execução acidental, não autenticação criptográfica do aprovador nem proteção contra código/operador malicioso.

## Credenciais, escopos e permissões a verificar

O mecanismo preparado usa uma **conta humana do operador já autenticada no Google Cloud CLI**. O processo captura `gcloud auth print-access-token` diretamente em memória e solicita à API oficial IAM Credentials um token de **900 segundos** para `global-pe-drive@exemplo-global-pe.iam.gserviceaccount.com`, com os escopos aprovados. Não executa login, não muda configuração IAM e não aceita conta fonte `.gserviceaccount.com`. Não usa a flag `--scopes` no comando fonte; os escopos alvo são enviados a `generateAccessToken`. Fonte: [IAM Credentials generateAccessToken](https://docs.cloud.google.com/iam/docs/reference/credentials/rest/v1/projects.serviceAccounts/generateAccessToken).

O SDK pode já guardar credencial de usuário/refresh token; só esse uso supervisionado explicitamente aprovado é contemplado. Não há criação de credencial duradoura pela aplicação. O token alvo é renovado em memória antes de expirar, somente dentro da janela aprovada. `gcloud` roda sem login automático e com `--configuration=NONE`, conta explícita e logs desativados. Variáveis de override de token/arquivo de credenciais não são herdadas. Configuração/fonte do SDK devem ser confiáveis e auditadas pelo responsável. Referências: [print-access-token](https://docs.cloud.google.com/sdk/gcloud/reference/auth/print-access-token), [configurações e logs do SDK](https://docs.cloud.google.com/sdk/gcloud/reference/topic/configurations).

Ainda é necessário verificar no ambiente escolhido: SDK instalado e conta correta já autenticada; `iam.serviceAccounts.getAccessToken` na conta alvo, normalmente por `roles/iam.serviceAccountTokenCreator`; IAM Credentials e Drive API ativas; conectividade/TLS; escopos e quotas. O sucesso relatado no Cloud Shell na 07B não é um novo teste dessas condições neste host. Falha IAM informa `iam_get_access_token` ou `iam_api_desativada` e interrompe sem conceder papel/ativar serviço. `credenciais_fonte` indica SDK/conta fonte indisponível, sem imprimir stderr externo.

O modelo pendente aceita exclusivamente `drive.file` + `drive.metadata.readonly`. Não permite `drive.readonly` nem `drive`, mesmo que constem de um arquivo de aprovação anterior. Nenhum token foi obtido ou renovado nesta revisão. O escopo de metadados não concede escrita; a tentativa de criação depende de `drive.file` e da autorização efetiva da conta de serviço na pasta existente.

`drives.get` foi removido. O adaptador usa `files.get` de cada um dos 14 Folder IDs já conhecidos, com `supportsAllDrives=true` e `fields=id,name,mimeType,parents,driveId,trashed,capabilities(canAddChildren)`. A missão é fixada ao Drive ID confirmado, inclusive se a configuração tentar inverter os dois Drives; `driveId` e `parents=[drive_id]` precisam confirmar a mesma raiz. As ACLs da raiz/pasta/arquivo continuam sendo lidas por `permissions.list`, com paginação e política restritiva. Antes do POST, a mesma conferência de pasta e `canAddChildren=true` é repetida. Nome físico da categoria, MIME, lixeira e ID solicitado continuam obrigatórios. Não há dependência de `drives.get` ou aceitação aproximada de nomes.

**A compatibilidade de upload com `drive.file` sob essas pastas existentes permanece pendente de validação real.** Passar no preflight ou ter Colaborador não prova que o aplicativo tem acesso de escrita ao pai com esse escopo. Os mocks validam somente o protocolo. Em 401/403, falta de capacidade, ACL inesperada ou outra falha, interromper sem avançar para a outra missão, sem escolher outro destino e sem ampliar escopos. Se houver incompatibilidade, requer nova análise/autorização; não há fallback para `drive` ou `drive.readonly`. Referências apenas para consulta futura (não acessadas nesta revisão): [files.get](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/get), [permissions.list](https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions/list), [escopos Drive](https://developers.google.com/workspace/drive/api/guides/api-specific-auth).

O SHA-256 remoto vem do campo de saída `sha256Checksum` de um **GET posterior do arquivo**, retornado pelo Google e associado aos bytes remotos. O aplicativo calcula SHA-256 local dos bytes sintéticos e compara ao campo remoto, além de tamanho, ID, missão, pasta, nome, MIME, lixeira, chave e ACL. Ele não envia `sha256Checksum` no JSON de criação nem em `appProperties`, e não usa o hash eventualmente retornado no ACK do POST como confirmação. `appProperties` é apenas marca de idempotência/missão, não prova de integridade. Campo remoto ausente ou divergente interrompe sem estado verificado, mesmo se as tags e um hash no ACK estiverem corretos. Não há download ou cálculo fictício de hash remoto a partir de um valor armazenado pelo próprio aplicativo. A disponibilidade desse campo no Google também será validada no ensaio autorizado. Referência para consulta futura: [campos do recurso File](https://developers.google.com/workspace/drive/api/reference/rest/v3/files).

Verificar ACL e capacidade efetiva nos dois Drives: Colaborador (`writer`) pode criar arquivos, mas restrições de organização/pasta e visibilidade de ACL podem impedir o fluxo. Membro de Drive não equivale a poder impersonar, e IAM não concede acesso ao Drive. A política vigente continua recusando Marcos, usuários da outra missão, membros extras não aprovados, grupos não auditáveis, domínio ou público. Não remover/adicionar membros para fazer o teste passar. [Papéis nos Shared Drives](https://developers.google.com/workspace/drive/api/guides/ref-roles).

## Backup e restauração exercitados

O ensaio possui schema próprio (`probe_run`, `probe_items`, `probe_events`), sem executar a migração 008. Guarda run_id, UUID do volume, checksum do mapa, plano, estados, tentativas, IDs reservados e histórico. Usa a [SQLite Backup API](https://www.sqlite.org/backup.html), com cópia consistente do SQLite, marcador do volume e os dois PNGs sob serialização do processo. O ZIP tem manifesto de hashes/tamanhos, escrita temporária exclusiva, fsync e substituição atômica. Um lock do sistema operacional impede dois executores usando o mesmo arquivo ZIP.

A restauração só escreve numa concessão temporária nova, recusa alvos existentes, entradas extras/traversal, cópia incompleta, hashes inválidos, marcador/UUID incompatíveis ou mapa diferente. Verifica `integrity_check` e conteúdos determinísticos. IDs e estados são preservados depois de falhas antes e depois do upload simulado; a confirmação perdida é resolvida por consulta ao ID original.

Os testes não usam cópia do banco operacional nem comprovantes reais. Eles validam o conjunto sintético do ensaio; **não certificam backup/restauração do conjunto operacional**, criptografia, ACLs NTFS, proteção contra perda de energia ou perda física do disco. O manifesto detecta corrupção, não adulteração intencional de backup e manifesto por um operador com acesso. Para produção continua pendente backup/restauração operacional autorizada. Em Windows não há a mesma confirmação de fsync de diretório que em POSIX.

O ZIP mais recente é necessário. Se ele for perdido, estiver corrompido ou for anterior a alterações remotas, **não preparar outro ensaio/ID para “tentar de novo”**: interromper e conferir administrativamente os IDs e `appProperties` remotos antes de retomar. Não extrair SQLite para uso operacional, não purgar o ZIP por falha e não alterar manualmente os estados. O checkpoint anterior ao POST permite recuperar confirmação perdida; a perda do próprio journal/backup exige revisão manual.

## Checklist de autorização — preencher antes de qualquer execução real

- [ ] Responsável aprovou por escrito este plano e a referência desse aceite foi registrada.
- [ ] Máximo: dois PNGs de 69 bytes, um por missão; nenhuma despesa/comprovante real.
- [ ] Argentina: `0AARGENTINAEXEMPLO1` / Deslocamento / `1EXEMPLO_AR_deslocamentos_0000000`.
- [ ] Portugal: `0APORTUGALEXEMPLO01` / Deslocamentos / `1EXEMPLO_PT_deslocamentos_0000000`.
- [ ] Conta humana fonte, impersonação da conta alvo e somente `drive.file` + `drive.metadata.readonly` aprovados. Upload sob as pastas existentes ainda é compatibilidade a validar, sem escalada de escopos.
- [ ] IAM/Drive APIs, rede, quotas, ACLs e `canAddChildren` foram conferidos sem alterar permissões.
- [ ] Backup/restauração sintética conferidos; política de preservação operacional reconhecida; ZIP guardado em local acessível ao responsável.
- [ ] Hashes de mapa/plano correspondem ao arquivo preparado; validade UTC termina em até 60 minutos.
- [ ] Aceite define retenção dos dois arquivos (`retain`); exclusão não faz parte desta autorização.
- [ ] Ambiente operacional continua parado/intacto e `RECEIPTS_DRIVE_MODE=disabled`.

## Procedimento exato — comando de escrita é somente para aprovação futura

No diretório do projeto, o ambiente Python precisa já conter as dependências do projeto; o SDK precisa existir no ambiente escolhido. Não instalar ferramenta ou iniciar autenticação interativa automaticamente. Os comandos abaixo usam o Python existente no Windows; em Cloud Shell, usar o interpretador equivalente já preparado e a mesma revisão do código, mapa, ZIP e aprovação. Não copiar `.env`, banco ou comprovantes operacionais para o Cloud Shell.

1. Revisar o mapa `artifacts/stage07b/mapping/folders.json`, o plano `artifacts/stage07c/offline-plan.json` e o relatório de testes. O ZIP `artifacts/stage07c/probe-prepared.zip` já foi preparado **offline**, sem tokens e com `remote_id=NULL`. Não criar outro ZIP para repetir uma tentativa do mesmo ensaio.
2. Para conferir/restaurar offline o mesmo plano, sem rede ou credenciais:

```powershell
.venv/Scripts/python.exe -m scripts.drive_probe --mapping artifacts/stage07b/mapping/folders.json --archive artifacts/stage07c/probe-prepared.zip --resume
```

3. Somente após aceite explícito, copiar `docs/drive-probe-approval.example.json` para um arquivo de autorização local separado. Preencher referência, conta humana já autenticada, expiração ISO-8601 com UTC/offset e escopos aprovados. Manter os hashes do plano preparado. Marcar `approved=true` e `backup_verified=true` apenas depois de sua conferência pelo responsável. O modelo entregue permanece **pendente**, `approved=false`, e não contém tokens/chaves.
4. **NÃO EXECUTADO NESTA ETAPA.** Depois da autorização, usar o mesmo ZIP e o arquivo preenchido:

```powershell
.venv/Scripts/python.exe -m scripts.drive_probe --mapping artifacts/stage07b/mapping/folders.json --archive artifacts/stage07c/probe-prepared.zip --resume --execute-authorized --approval CAMINHO_DA_AUTORIZACAO_APROVADA.json
```

5. O processo valida aprovação antes de buscar credenciais; restaura SQLite só em temporário; obtém token curto em memória; consulta os 14 destinos, ACLs e capacidades; reserva um ID; confirma SQLite/backup; envia o PNG argentino; verifica metadados/checksum/ACL; salva checkpoint; repete para Portugal. Para cada missão exigir estado `verificado`, ID, pasta/Drive/nome corretos, `image/png`, 69 bytes e SHA-256 igual ao plano. Nenhum ID reservado sozinho ou HTTP 200 do POST conta como sucesso.
6. Com a autorização ainda válida, repetir **o mesmo comando e ZIP** uma vez: devem continuar exatamente os mesmos dois IDs, com GET de verificação e nenhum arquivo novo. Guardar resultado controlado e ZIP mais recente. O arquivo local de aprovação não é credencial; ainda assim deve ser protegido contra alteração por terceiros.

### Falhas, limpeza e recuperação

Em timeout/429/5xx, parar (saída 2), preservar ZIP e não avançar para a outra missão após a falha. Não há retry automático. O responsável pode aguardar e, dentro da autorização, repetir uma única vez com `--resume` e o mesmo ZIP. Novo token é obtido em memória quando necessário. Se a autorização expirou, renovar seu aceite/validade sem trocar plano, IDs ou arquivo de recuperação. Em 401/403/IAM/ACL, corrigir a pendência com o administrador mediante aprovação separada; o script não faz isso. Falha de backup impede o POST. Interrupção abrupta usa o checkpoint anterior; não reservar outro ID para o mesmo item.

Se o hash remoto ainda não estiver disponível, manter erro/pendência; não declarar sucesso por tamanho. Objeto que já foi verificado e depois estiver ausente ou divergente requer revisão manual; não é recriado. Não causar intencionalmente falhas reais de rede nem excluir arquivo para “testar recuperação” nesta primeira autorização; esses cenários já foram simulados.

**Limpeza remota não implementada nem autorizada.** Conservar os dois arquivos ao terminar, até uma autorização separada definir o que remover e quem fará isso. A conta Colaborador não deve ser promovida para limpeza. Se houver autorização futura, um administrador conferirá os dois IDs, pais e `appProperties` do ensaio antes de mover para lixeira/remover, sem busca genérica por nome. Exclusão permanente em Shared Drive exige papel apropriado de organizador no pai, não apenas Colaborador. [Regras de exclusão](https://developers.google.com/workspace/drive/api/guides/delete).

Depois de interromper/sair, descartar tokens da memória encerrando o processo; ele não os salva. Conservar o ZIP e os relatórios enquanto houver arquivos remotos a auditar. Não remover por fora o lock de um processo vivo. Resíduos temporários de queda abrupta não autorizam limpeza ampla de diretórios.

## Critério de prontidão

Transporte, fornecedor temporário e comando controlado estão implementados e testados com mocks; o plano offline é concreto e revisável. **O primeiro uso real ainda depende da aprovação, das permissões efetivas e da disponibilidade do SDK/rede no ambiente escolhido.** Não houve teste real de escrita nem se presume prontidão de produção. O backup operacional, autenticação contínua da VPS, retenção, operação financeira FACEPE e ativação do worker permanecem fora deste ensaio.

Resultados automatizados, inventário de arquivos e prova de preservação: [validacao-etapa07c.md](validacao-etapa07c.md).
