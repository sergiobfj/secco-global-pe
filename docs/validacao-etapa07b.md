# Etapa 07B — preflight histórico e continuação do mapeamento

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


> **Distribuição pública:** nomes, e-mails, domínio Google Workspace, IDs de Drive/pastas e identificadores Google Cloud deste documento são fictícios. Resultados e decisões descritos referem-se ao projeto operacional.


## Atualização — destinos informados após Cloud Shell

O responsável informou que a conta de serviço conseguiu ler os dois Drives via Google Drive API v3 no Google Cloud Shell, com `drive.metadata.readonly`, e forneceu os 14 IDs de pastas diretamente nas raízes. Esse resultado supervisionado externo substitui a pendência de descoberta descrita no registro histórico abaixo; não foi reproduzido neste ambiente e não fornece credenciais ao aplicativo/VPS.

Os nomes reais atuais não têm prefixos numéricos. Todos correspondem aos rótulos da 07A, exceto a pasta argentina **Deslocamento**, no singular. O código foi alinhado com expectativa exata por missão: não foi introduzida aceitação genérica de singular/plural ou busca de pasta por nome. ID solicitado, `driveId`, pai único/raiz, nome, MIME, lixeira, identidade do Drive e ACLs permanecem verificados.

O mapeamento completo e a sugestão de `GOOGLE_DRIVE_FOLDERS_JSON` estão no [guia atualizado](integracao-google-drive.md#configuração-dos-dois-drives) e em `.env.example`, com as sete chaves de categoria por missão. O padrão de runtime continua `{}` para pastas e `disabled` para integração; preencher o exemplo não carrega nem modifica `.env`.

Os testes desta continuação usam somente `httpx.MockTransport` e credenciais fictícias. Os novos cenários verificam metadados sem upload, abertura de SQLite ou execução de migrações. Nenhuma consulta externa foi executada pelo agente. O registro inicial abaixo é mantido como histórico e seus resultados de autenticação/conectividade referem-se apenas ao preflight local anterior.

### Resultado dos testes da continuação

```powershell
.venv/Scripts/python.exe -m pytest tests/test_drive_folder_mapping.py tests/test_google_drive_sync.py -q -k 'not test_google_drive_sync or invalid_configuration' -p no:cacheprovider
```

**117 aprovados, zero falhas, zero erros, 49 não selecionados, dois avisos de depreciação existentes**, em **2,12 s**. São 113 novos cenários e quatro regressões anteriores de configuração. A suíte integral da 07A não foi reexecutada. A seleção evita os testes antigos que inicializam armazenamento/aplicação ou migram bancos, mantendo esta rodada sem aplicar a 008 sequer em banco temporário. A política de concessões temporárias de `tests/conftest.py` permanece ativa; não foi relaxada.

Cobertura: os 14 IDs exatos e seus nomes; troca de IDs entre países e entre categorias; ID retornado diferente do solicitado; pasta ausente na configuração ou inexistente na API simulada; IDs inválidos/repetidos; nome com prefixo antigo, caixa divergente ou espaço extra; singular/plural específico de cada missão; `driveId`, pai único na raiz, MIME e lixeira. O JSON do guia e o exemplo são comparados com uma transcrição independente dos 14 IDs (fictícios nesta distribuição). Os testes também confirmam modo padrão `disabled`, mapa de runtime vazio por omissão e manutenção do bloqueio de transporte real.

Log: `artifacts/stage07b/mapping/targeted-tests.log`. Mapa copiável: `artifacts/stage07b/mapping/folders.json` (somente IDs de destino, não é credencial). Resultados e preservação: `artifacts/stage07b/mapping/validation.json`. O SQLite operacional, `.env` e migrações 001–008 mantêm os SHA-256 anteriores à alteração. Nenhum banco foi aberto ou migrado nesta rodada.

### Prontidão e autorização do futuro ensaio

**O mapeamento está pronto para preparar um futuro ensaio supervisionado de upload sintético. O envio real continua tecnicamente bloqueado e não está autorizado.** O sucesso de leitura com `drive.metadata.readonly` não fornece escopo de escrita, não valida as ACLs para upload e não configura a VPS/aplicação.

Antes de executar esse ensaio, faltam:

1. Nova aprovação explícita para escrita sintética, com escopo, pastas, quantidade/limite de arquivos, retenção e critérios de aceite definidos. Não ampliar/reutilizar automaticamente o token de leitura; emitir token temporário somente pelo mecanismo aprovado e manter em memória.
2. Aprovar o escopo mínimo de escrita e a forma de autenticação para o processo que executará o ensaio. Cloud Shell é o mecanismo informado para leitura supervisionada; não equivale a um provedor já implementado no aplicativo ou a uma solução contínua da VPS.
3. Conferir novamente os metadados e auditar as ACLs herdadas dos dois Drives/pastas. A política do adaptador permanece restritiva: Marcos, outro país, domínio/público/grupo não auditável ou membro adicional não aprovado bloqueiam envio, sem alteração automática de permissões.
4. Validar backup/restauração do conjunto operacional antes de qualquer ativação operacional. Preparar o ensaio em ambiente isolado e SQLite temporário próprio, sem inicializar ou migrar o banco operacional. A 008 operacional continua sem autorização para aplicação.
5. Implementar/revisar uma entrada controlada e o provedor temporário aprovado, com autorização específica para transporte real. O construtor continua exigindo `MockTransport` e não há modo real liberado por variável. O fluxo de upload precisa de nome técnico FACEPE válido; não inventar processo para contornar pendência. Categorias sem origem automática continuam sem classificação financeira automática.

Para o ensaio autorizado futuro, recomenda-se um arquivo estritamente sintético por missão, conferência de ID/pasta/Drive/nome/checksum e repetição com o mesmo ID para verificar idempotência. Exclusão posterior não está implicitamente autorizada: retenção/limpeza deve ser aprovada separadamente. Não é necessário criar pastas ou terceiro Drive.

### Arquivos desta continuação

Alterados: `app/core/drive_config.py`, `app/services/google_drive_storage.py`, `.env.example`, `tests/test_google_drive_sync.py`, `docs/integracao-google-drive.md`, este relatório e `README.md`. Criado: `tests/test_drive_folder_mapping.py`, além dos três artefatos em `artifacts/stage07b/mapping/`. Nenhum arquivo da migração 008 ou de credenciais foi criado/alterado; o preflight JSON anterior foi preservado como histórico.

## Registro histórico do preflight local

## Resultado

O teste foi interrompido antes de qualquer chamada externa por ausência de mecanismo local disponível para obter credenciais temporárias da conta de serviço. Não houve tentativa de login interativo, instalação de ferramenta, emissão de token, leitura de segredos do `.env` ou consulta à API Google.

Não se trata de uma resposta de acesso negado do Google: a autenticação não chegou a ser iniciada.

## Evidências locais

| Verificação | Resultado |
|---|---|
| Google Cloud CLI (`gcloud`) no PATH | Não encontrado |
| Executável nos locais padrão do SDK em LocalAppData, perfil do usuário e Program Files | Não encontrado nos quatro caminhos verificados; não houve busca ampla pelo disco |
| Biblioteca `httpx` no ambiente virtual do projeto | Disponível |
| Biblioteca `google.auth` / suporte de impersonação | Não disponível no ambiente virtual |
| Configuração `GOOGLE_APPLICATION_CREDENTIALS` no processo | Ausente; nenhum valor de credencial foi exibido |
| Configuração alternativa `CLOUDSDK_CONFIG` no processo | Ausente |
| Arquivo ADC e banco de credenciais no diretório padrão do gcloud | Ausentes |
| Token do Cloud SDK em variável do processo | Ausente; nenhum token foi lido/exibido |
| HTTPS às APIs Google | Não testado: execução interrompida no bloqueio de autenticação |
| Impersonação da conta de serviço | Não iniciada |
| `roles/iam.serviceAccountTokenCreator` na conta alvo | Não verificado; não presumir concedido nem ausente |
| IAM Credentials API | Estado não verificado; nenhuma ativação solicitada/executada |

As verificações acima ocorreram sem importar `app.main`, carregar `Settings.from_env`, inicializar FastAPI ou abrir conexões SQLite. A ausência nos caminhos verificados não prova inexistência de SDK em um local personalizado; o responsável pode indicar uma instalação/sessão autorizada.

## Acesso aos Drives

| Missão | Drive ID informado | Autenticação | Consulta / acesso real |
|---|---|---|---|
| Argentina | `0AARGENTINAEXEMPLO1` | Não obtida | Não consultado; acesso não confirmado nem negado |
| Portugal | `0APORTUGALEXEMPLO01` | Não obtida | Não consultado; acesso não confirmado nem negado |

Nenhum Folder ID foi descoberto. Não foi gerado valor preenchido de `GOOGLE_DRIVE_FOLDERS_JSON`, pois seria necessário inventar IDs. O formato esperado pela 07A permanece `{codigo_missao: {chave_categoria: folder_id}}`, com códigos `argentina` e `portugal` e chaves `passagens`, `diarias`, `inscricoes`, `deslocamentos`, `contrapartida`, `eventos` e `atividades`.

## Compatibilidade identificada na inspeção da 07A

`DriveConfiguration.folders_json` aceita o formato acima, porém `GoogleDriveAdapter._destination` também exige que o nome real da pasta seja igual ao valor de `CATEGORIES`. Os nomes numerados informados pelo responsável diferem dos valores atuais:

| Categoria | Nome esperado atualmente pela 07A | Nome informado para consulta 07B |
|---|---|---|
| `passagens` | Passagens | 01-Passagens |
| `diarias` | Diárias | 02-Diarias |
| `inscricoes` | Inscrições | 03-Inscricoes |
| `deslocamentos` | Deslocamentos | 04-Deslocamentos |
| `contrapartida` | Contrapartida | 05-Contrapartida |
| `eventos` | Comprovantes de Eventos | 06-Comprovantes-Eventos |
| `atividades` | Atividades | 07-Atividades |

Mesmo com IDs corretos, o adaptador atual recusaria esses nomes numerados. Não alteramos as pastas nem o código para superar a verificação. Após a descoberta real, será necessário alinhar a expectativa de nomes em uma alteração local revisada antes de qualquer teste de upload. O teste de leitura pode usar os nomes numerados informados, sem habilitar/reutilizar o adaptador de upload.

## Pendência para continuar

O responsável deve indicar um mecanismo temporário autorizado ou uma sessão do Google Cloud CLI já autenticada, em ambiente supervisionado. Não enviar tokens, senhas ou chaves pela conversa. Se for necessária instalação/configuração, isso deve ser decidido explicitamente; nada foi instalado nesta etapa.

Para a opção de impersonação supervisionada, o principal do operador precisa ter a permissão `iam.serviceAccounts.getAccessToken` na conta `global-pe-drive@exemplo-global-pe.iam.gserviceaccount.com`, normalmente por `roles/iam.serviceAccountTokenCreator`, e a IAM Service Account Credentials API precisa estar habilitada no projeto pertinente. Esses requisitos são pendências de **verificação**, não diagnósticos de permissão ausente ou API desativada. Se a tentativa autorizada retornar esse bloqueio, registrar a resposta sanitizada e parar; não conceder papéis nem ativar API automaticamente. Referência para revisão pelo responsável: [credenciais curtas por impersonação](https://docs.cloud.google.com/iam/docs/create-short-lived-credentials-direct).

O escopo final pretendido continua exclusivamente `https://www.googleapis.com/auth/drive.metadata.readonly`. Tokens devem permanecer apenas em memória, capturados diretamente pelo processo de diagnóstico, sem linha de comando, arquivo, log ou saída de console. Não reutilizar tokens do login da aplicação.

## Próximo teste supervisionado proposto

Após orientação sobre autenticação, verificar conectividade HTTPS, sem contornar eventual restrição de saída. Se o ambiente bloquear, preparar diagnóstico para PowerShell normal do responsável, sem executar permissões ampliadas.

Com credencial temporária válida, limitar o diagnóstico a `GET drives/{driveId}` com `fields=id,name` e `GET files` para pastas diretamente na raiz, com query `'<driveId>' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false`, `corpora=drive`, `driveId` fixo da missão, `supportsAllDrives=true`, `includeItemsFromAllDrives=true`, paginação e campos `nextPageToken,incompleteSearch,files(id,name,mimeType,driveId,parents,trashed)`. Conferir nomes exatos, duplicatas, ausências e vínculo de cada pasta ao Drive correto. Não enumerar subpastas ou arquivos de comprovantes e não consultar conteúdo, permissões ou URLs de download.

O relatório poderá então apresentar as 14 pastas e sugerir o JSON, sem escrever no `.env` ou habilitar `RECEIPTS_DRIVE_MODE`. Nesta execução não foi preparado um script de fallback: não há evidência de bloqueio de rede; houve bloqueio anterior de autenticação e a instrução foi interromper e pedir orientação.

## Preservação e arquivos

Criados apenas este relatório e `artifacts/stage07b/preflight.json`. Nenhum arquivo existente da aplicação foi alterado. Não foram executados testes que inicializem a aplicação nem migrações, pois a atividade encerrou no preflight local de autenticação.

O SQLite operacional, o `.env` e o arquivo da migração 008 foram comparados por SHA-256 antes/depois, sem conexão SQLite e sem publicar conteúdo do `.env`. A evidência em JSON registra apenas os resultados das verificações, sem credenciais. Não houve upload, exclusão, criação/renomeação de pasta, alteração de permissão/IAM, deploy, commit ou push.
