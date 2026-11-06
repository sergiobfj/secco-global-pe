# Google Shared Drive — preparação 07A e destinos confirmados na 07B

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


> **Distribuição pública:** nomes, e-mails, domínio Google Workspace, IDs de Drive/pastas e identificadores Google Cloud deste documento são fictícios. Resultados e decisões descritos referem-se ao projeto operacional.


Atualização 07C: existe uma entrada **independente** para futuro ensaio de dois arquivos sintéticos, com transporte HTTPS e impersonação temporária preparados, sujeitos a autorização explícita. O adaptador normal da aplicação e `RECEIPTS_DRIVE_MODE` continuam bloqueados/desativados. Nenhum ensaio real foi executado. O procedimento 07C (`ensaio-supervisionado-drive.md`, não incluído nesta etapa da distribuição) detalha os gates, escopos efetivamente exigidos, backup/restauração e a limpeza separada; a validação 07C (`validacao-etapa07c.md`, não incluído nesta etapa da distribuição) registra as evidências. Os limites descritos abaixo continuam aplicáveis à integração operacional.

## Situação e limites

Implementação exclusivamente simulada. Não há credencial real, descoberta ADC, chamadas à API Drive, criação de pastas, endpoint de sincronização, worker de startup ou habilitação em produção. `RECEIPTS_DRIVE_MODE=disabled` é o padrão. O único outro valor aceito, `simulated`, exige desenvolvimento autenticado, captura sintética, armazenamento local e política de bancos temporários ativa. O adaptador exige explicitamente `httpx.MockTransport`; não possui transporte real por omissão. Não foram alterados `.env`, banco operacional, migrações 001–007 ou Drives. Não houve deploy, commit ou push.

A migração 008 é aditiva e foi aplicada apenas pelas fixtures em SQLite temporário. Atenção: o startup normal existente aplica migrações disponíveis. Não inicie a aplicação operacional com esta versão antes de backup validado e autorização da migração. Acrescentar o arquivo de migração não significa que ele já foi aplicado ao banco operacional.

Na continuação da 07B, o responsável informou sucesso da leitura supervisionada via Google Cloud Shell, pela conta de serviço, com escopo `drive.metadata.readonly`, e forneceu os 14 IDs e nomes reais; nesta distribuição, os IDs abaixo são fictícios. Essa consulta ocorreu fora deste ambiente e não foi repetida pelo agente. Os nomes atuais não têm prefixos numéricos e substituem a informação preliminar de `01-…` a `07-…`. O exemplo local foi preenchido e a validação de nomes foi alinhada, mantendo toda integração real desativada. Sucesso de leitura de metadados não constitui autorização de escrita.

## Inspeção e arquitetura

Foram inspecionados `Settings`, OIDC, política Workspace, autoria no repositório/rotas, validação de captura e regras FACEPE, contratos de armazenamento, volume privado, journal em disco, reconciliação local, migrações e concessões temporárias dos testes. O acesso continua mais restrito que simplesmente pertencer à missão: cada viajante acessa apenas os próprios arquivos pela aplicação. Tiago/Bruno operam Argentina; Hugo/Alan operam Portugal; Marcos permanece na visão consolidada. Beneficiário da subvenção não determina permissão. Nenhuma regra financeira, checklist, captura ou permissão existente foi ampliada.

Fluxo da integração:

1. A captura existente confirma o arquivo no volume privado com journal e SHA-256.
2. `ReceiptDriveSync.enqueue` exige autor habilitado e autorizado, missão obtida do SQLite, objeto local íntegro, nome técnico já preparado e categoria mapeada. Não aceita missão/destino fornecidos pelo formulário.
3. `receipt_drive_sync` registra intenção, volume, objeto, checksum, nome técnico, categoria e destino. A chave idempotente é SHA-256 de volume + ID do anexo.
4. `files.generateIds` reserva um ID. O SQLite confirma esse ID antes de qualquer upload. Queda antes da confirmação pode desperdiçar um ID vazio; não cria arquivo.
5. O adaptador confere o Drive ID confirmado de cada missão e os metadados da pasta da categoria diretamente na raiz via `files.get`, além das ACLs. `files.get` procura o ID reservado antes de cada criação.
6. O upload multipart usa esse mesmo ID, nome técnico intacto e `appProperties` com chave opaca e código da missão. Não envia nome original nem metadados financeiros extras. Um conflito 409 exige verificação, sem criar outro ID.
7. Outra consulta confirma ID, `driveId`, pasta, nome, MIME, tamanho, SHA-256, estado não excluído e chave idempotente. As ACLs do arquivo também são conferidas. Só então o journal marca `verificado` com data e evento.

O contrato `SharedDriveAdapter` define reserva, upload e verificação; `StoredReceipt` ganhou campos opcionais de missão, categoria e nome técnico, sem mudar o uso local. `DriveCredentials` fornece token de acesso curto com validade; o adaptador não conhece sua origem e nunca acessa o login OIDC. O único provedor de produção entregue recusa uso por falta de método aprovado. Não foi adicionada dependência de SDK Google: o HTTP v3 usa o `httpx` já existente.

`supportsAllDrives=true` é usado em `files.get`, `files.create` e `permissions.list`. `files.generateIds` não recebe esse parâmetro. `drives.get` não é usado na revisão atual de menor privilégio. Não há `permissions.create`, compartilhamento público, atualização, remoção remota ou criação de pasta. Referências: [suporte a Shared Drives](https://developers.google.com/workspace/drive/api/guides/enable-shareddrives), [IDs pré-gerados e repetição com 409](https://developers.google.com/workspace/drive/api/guides/create-file), [campos/checksums](https://developers.google.com/workspace/drive/api/reference/rest/v3/files).

## Configuração dos dois Drives

`GOOGLE_DRIVE_FOLDERS_JSON` é uma string JSON de **missão → categoria → Folder ID**. Não aceita objetos com nome/ID no lugar do valor string, nem chaves com rótulos de exibição. `.env.example` contém o mapa completo em uma única linha; o mesmo valor é apresentado formatado abaixo. O padrão no código permanece `{}` quando a variável está ausente. Nenhum ID foi incorporado como fallback automático de pasta, e `.env.example` não é carregado como configuração operacional. O `.env` real foi preservado.

```dotenv
RECEIPTS_DRIVE_MODE=disabled
GOOGLE_DRIVE_ARGENTINA_ID=0AARGENTINAEXEMPLO1
GOOGLE_DRIVE_PORTUGAL_ID=0APORTUGALEXEMPLO01
```

Projeto: `exemplo-global-pe`. Identidade: `global-pe-drive@exemplo-global-pe.iam.gserviceaccount.com`. API ativada, participação como Colaborador, leitura de ambos os Drives e sete pastas diretamente em cada raiz foram informadas pelo responsável. Os IDs abaixo seguem o formato dessa descoberta (fictícios nesta distribuição), com validação local por API simulada; não são evidência de uma nova consulta real pelo agente.

| Missão | Nome esperado | Drive ID |
|---|---|---|
| Argentina | Global PE - Argentina | `0AARGENTINAEXEMPLO1` |
| Portugal | Global PE - Portugal | `0APORTUGALEXEMPLO01` |

As sete pastas de cada Drive já foram criadas manualmente. Não criar novas pastas nem terceiro Drive. Mapeamento completo informado pelo responsável (IDs fictícios nesta distribuição):

| Missão | Categoria | Nome real exigido | Folder ID |
|---|---|---|---|
| Argentina | `passagens` | Passagens | `1EXEMPLO_AR_passagens_00000000000` |
| Argentina | `diarias` | Diárias | `1EXEMPLO_AR_diarias_0000000000000` |
| Argentina | `inscricoes` | Inscrições | `1EXEMPLO_AR_inscricoes_0000000000` |
| Argentina | `deslocamentos` | Deslocamento | `1EXEMPLO_AR_deslocamentos_0000000` |
| Argentina | `contrapartida` | Contrapartida | `1EXEMPLO_AR_contrapartida_0000000` |
| Argentina | `eventos` | Comprovantes de Eventos | `1EXEMPLO_AR_eventos_0000000000000` |
| Argentina | `atividades` | Atividades | `1EXEMPLO_AR_atividades_0000000000` |
| Portugal | `passagens` | Passagens | `1EXEMPLO_PT_passagens_00000000000` |
| Portugal | `diarias` | Diárias | `1EXEMPLO_PT_diarias_0000000000000` |
| Portugal | `inscricoes` | Inscrições | `1EXEMPLO_PT_inscricoes_0000000000` |
| Portugal | `deslocamentos` | Deslocamentos | `1EXEMPLO_PT_deslocamentos_0000000` |
| Portugal | `contrapartida` | Contrapartida | `1EXEMPLO_PT_contrapartida_0000000` |
| Portugal | `eventos` | Comprovantes de Eventos | `1EXEMPLO_PT_eventos_0000000000000` |
| Portugal | `atividades` | Atividades | `1EXEMPLO_PT_atividades_0000000000` |

Valor sugerido para `GOOGLE_DRIVE_FOLDERS_JSON` (compactado em uma linha em `.env.example`):

```json
{
  "argentina": {
    "passagens": "1EXEMPLO_AR_passagens_00000000000",
    "diarias": "1EXEMPLO_AR_diarias_0000000000000",
    "inscricoes": "1EXEMPLO_AR_inscricoes_0000000000",
    "deslocamentos": "1EXEMPLO_AR_deslocamentos_0000000",
    "contrapartida": "1EXEMPLO_AR_contrapartida_0000000",
    "eventos": "1EXEMPLO_AR_eventos_0000000000000",
    "atividades": "1EXEMPLO_AR_atividades_0000000000"
  },
  "portugal": {
    "passagens": "1EXEMPLO_PT_passagens_00000000000",
    "diarias": "1EXEMPLO_PT_diarias_0000000000000",
    "inscricoes": "1EXEMPLO_PT_inscricoes_0000000000",
    "deslocamentos": "1EXEMPLO_PT_deslocamentos_0000000",
    "contrapartida": "1EXEMPLO_PT_contrapartida_0000000",
    "eventos": "1EXEMPLO_PT_eventos_0000000000000",
    "atividades": "1EXEMPLO_PT_atividades_0000000000"
  }
}
```

`CATEGORIES` preserva os rótulos e as chaves de categoria. `FOLDER_NAMES` define o nome físico exato por missão, incluindo exclusivamente a exceção argentina `deslocamentos → Deslocamento`. O adaptador não normaliza nomes, não aceita aliases singular/plural, prefixos numéricos, diferença de caixa ou espaço extra. Continua exigindo simultaneamente ID igual ao solicitado, `driveId` correto, pai único igual à raiz daquele Drive, nome da categoria naquela missão, tipo pasta e `trashed=false`, além das ACLs. Os IDs são configuração explícita, não descoberta/aproximação pelo nome; uma alteração legítima de IDs exige revisão de configuração.

Configuração vazia continua válida para preparação e bloqueia o envio. IDs de pasta repetidos, categorias/missões desconhecidas, IDs de Drive iguais e IDs de pasta iguais à raiz são recusados. A identidade do Drive é vinculada ao ID confirmado da missão: inverter IDs entre países falha antes da consulta de metadados. Mudança de pasta/Drive depois de enfileirar falha e exige revisão; não redireciona silenciosamente um comprovante.

O mapeamento documental não altera a classificação FACEPE: `passagem_aerea → passagens`, `diaria → diarias`, `inscricao_evento → inscricoes`; `aplicativo`, `taxi`, `intermunicipal` e `urbano → deslocamentos`. `contrapartida`, `eventos` e `atividades` têm destinos preparados, mas continuam sem origem automática no fluxo de despesas. `seguro_saude` e `outro` não são classificados automaticamente. Não há suposição de que despesas de Tiago/Alan pertençam à Contrapartida: financiamento e classificação documental são independentes. A inscrição vai a Inscrições, sem duplicar anexos automaticamente em Comprovantes de Eventos.

## Privacidade e permissões herdadas

Ausência de chamada para compartilhar **não garante** privacidade: membros e permissões dos pais são herdados. O adaptador percorre todas as páginas de `permissions.list` para raiz, pasta e arquivo e recusa domínio, público, grupo não auditável, usuário desconhecido, Marcos ou operadores da outra missão. Exige a conta de serviço na ACL. Sem leitura suficiente da ACL, a operação falha; não pede promoção automática do Colaborador. Fonte: [propagação de permissões](https://developers.google.com/workspace/drive/api/guides/manage-sharing).

Esta política restritiva permite apenas Tiago/Bruno/conta de serviço na Argentina e Hugo/Alan/conta de serviço em Portugal. Se houver outro administrador visível na ACL, o ensaio será bloqueado até revisão explícita da política; não removeremos membros nem ampliaremos a lista automaticamente. A aplicação continua impedindo acesso ao comprovante de outro autor da mesma missão. No próprio Drive, os dois operadores de cada missão podem herdar acesso aos arquivos daquela missão; isso precisa ser aceito na revisão de privacidade antes do uso real.

ACL pode mudar depois da verificação, e há uma janela entre conferência e upload. A aplicação não consegue garantir imutabilidade da política do Workspace ou impedir ações de administradores. Antes da ativação, impor/revisar restrições administrativas de compartilhamento e auditar membros; depois, monitorar mudanças. Se a ACL ficar insegura após um upload, a reconciliação revoga o estado verificado e conserva a referência para correção administrativa. Não promete apagar/revogar permissões herdadas com o papel de Colaborador.

Não há URL remota na interface, download público ou caminho privado exposto. Downloads continuam pela rota autenticada local, com autoria, checksum, `no-store` e download como anexo. Journal/eventos armazenam apenas metadados necessários em SQLite privado, sem corpo HTTP, token, credencial, bytes ou mensagens arbitrárias. Falhas usam códigos fixos. Não habilitar debug HTTP com segredos num futuro transporte real.

A mesma conta de serviço tem acesso aos dois Drives. O isolamento entre missões é imposto pelo roteamento e pela autorização da aplicação, não por identidades Google distintas. Uma credencial comprometida dessa conta afetaria os dois Drives; a aprovação do método deve considerar esse alcance.

## Retomada, falhas e interface

Os journals local e remoto são independentes. A 006 permanece intacta: suas colunas `sync_state='pendente'` e `remote_reference=NULL` continuam legadas; o estado remoto oficial desta preparação é `receipt_drive_sync`. O repositório lê esse journal separadamente. A fonte do ID remoto é exclusivamente essa tabela; não derivar sucesso do enum legado.

`reconcile()` percorre trabalhos `aguardando`, `enviando`, `erro` e `verificado` ainda associados a objetos locais armazenados. Não inicia automaticamente com a aplicação. Queda após upload e antes do commit é resolvida por GET do ID reservado. Reenvio não gera ID novo. SHA-256 ausente no Google é pendência/erro até disponível, sem declarar sucesso por tamanho ou nome. Rede, 401/403, 429/5xx, redirects e JSON inválido geram erro controlado. Não há loop de retry nem backoff nesta etapa; cada reconciliação explícita faz uma tentativa e registra evento. Agendamento/backoff limitado será definido antes de ativação real.

O lock já existente do volume impede dois processos; o mesmo RLock serializa os serviços de sincronização no processo. Não usar múltiplos workers. Nenhuma falha remota remove o comprovante local. Edição de nome/categoria ou troca do objeto após enfileirar invalida a confirmação e bloqueia novo envio para revisão, sem criar cópia nem alterar o arquivo remoto automaticamente.

Exclusão local continua com a confirmação, autoria e journal existentes. Suspende sincronização; **não exclui a cópia remota**. Sua referência e histórico são preservados. Retenção, exclusão remota e edição de metadados após sincronizar exigem política e implementação autorizadas antes do uso real. Após exclusão local, reconciliar não ressuscita o arquivo. Conteúdo remoto já enviado precisa de tratamento administrativo separado quando aplicável.

O fluxo Fotografar → preencher → Salvar não ganhou passos. Estado local e estado de sincronização aparecem separadamente:

| Situação | Interface |
|---|---|
| Arquivo local íntegro | Armazenado localmente |
| Sem trabalho ou aguardando/envio em curso | Aguardando sincronização |
| GET confirmou todos os campos e ACL | Sincronizado e verificado (simulação) |
| Falha ou metadados divergentes | Erro de sincronização |
| Exclusão solicitada/concluída | Sincronização suspensa |

O rótulo de simulação é obrigatório nesta entrega. Salvar no SQLite ou receber 200 do upload não equivale à confirmação de sincronização.

## Autenticação numa VPS Ubuntu fora do Google Cloud

Nenhuma opção abaixo foi ativada. Configurar o método, os escopos, IAM ou armazenamento de credenciais exige aprovação separada. A política que bloqueia chaves JSON permanece respeitada. Não é necessário nem proposto usar delegação em todo o domínio Workspace.

| Estratégia | Pré-requisitos | Riscos/limitações e avaliação |
|---|---|---|
| **WIF + impersonação da conta de serviço** | Identidade de workload comprovável na VPS (IdP OIDC/SAML confiável ou identidade de outro provedor suportado); pool/provider; atributos e condição vinculados a essa workload; permissão de impersonação com `roles/iam.workloadIdentityUser` na conta específica; STS/IAM Credentials habilitados conforme arquitetura; saída HTTPS, relógio correto e renovação | Recomendação para operação contínua **se** houver identidade externa adequada. Reduz segredo Google duradouro na VPS. A identidade de origem ainda precisa ser protegida; confiança ampla no IdP comprometeria a conta. Login Google Workspace do aplicativo não fornece por si uma identidade de workload da VPS. Não criar IdP ou ampliar IAM automaticamente. [Documentação WIF](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-other-providers). |
| Impersonação supervisionada por operador, token curto | Identidade administrativa autorizada, `roles/iam.serviceAccountTokenCreator` apenas na conta alvo, IAM Credentials e escopo Drive aprovado; entrega segura do token curto ao provedor, somente em memória | Adequada ao **primeiro ensaio manual** após aprovação. Expira e não resolve serviço contínuo sozinha. Não colocar token em argumentos de shell, `.env`, logs ou histórico. Não usar tokens OIDC do aplicativo. ADC com usuário pode guardar refresh token: não será criado sem aprovação. [Credenciais curtas](https://docs.cloud.google.com/iam/docs/create-short-lived-credentials-direct), [impersonação e ADC](https://docs.cloud.google.com/docs/authentication/use-service-account-impersonation). |
| OAuth dedicado para integração, separado do login | Consentimento/admin Workspace, cliente OAuth específico, identidade dedicada membro dos Drives, escopos e armazenamento seguro de refresh token aprovados | Tecnicamente viável, porém troca a identidade efetiva e exige reavaliar ACL/política. Credencial duradoura, revogação, rotação e dependência da conta. Não é a recomendação neste cenário e não se aproveita a sessão dos usuários. [OAuth Drive e escopos](https://developers.google.com/workspace/drive/api/guides/api-specific-auth). |
| Executor/broker no Google Cloud com conta anexada | Componente GCP aprovado e autenticação forte da VPS para ele, custos, IAM, escopos Drive e desenho do canal | Alternativa se a VPS não oferece identidade federável; reduz segredo Google local, mas adiciona infraestrutura, transporte de arquivos e fronteira de confiança. Não cria credenciais a partir do nada: ainda exige autenticar a VPS. [Autenticação Google](https://docs.cloud.google.com/docs/authentication). |

A recomendação é avaliar WIF com impersonação como destino de produção e token curto supervisionado como opção do primeiro ensaio. Se não houver IdP/identidade de workload, não há solução automática sem novos pré-requisitos: manter integração desativada e decidir arquitetura com o administrador.

O token final deve representar **a conta de serviço pretendida**, com escopo Drive aprovado. `cloud-platform` sozinho não é escopo Drive. Avaliar primeiro `drive.file`, que é limitado aos arquivos autorizados para a aplicação; não presumir que permita inspecionar Drives/pastas existentes e todas as ACLs exigidas. Se for necessário `https://www.googleapis.com/auth/drive`, documentar a abrangência e obter aprovação. A concessão IAM para impersonar não concede participação no Shared Drive; e o papel Colaborador no Drive não concede IAM para impersonar. Referências: [escopos Drive](https://developers.google.com/workspace/drive/api/guides/api-specific-auth), [problemas de escopos em ADC](https://docs.cloud.google.com/docs/authentication/troubleshoot-adc).

O provedor futuro deverá usar biblioteca oficial de autenticação, renovar antes de expirar, manter token só em memória, não aceitar configuração externa não confiável/executáveis sem revisão e validar conta/escopos. Não buscar chave JSON, não desativar política e não fazer fallback silencioso para credenciais do operador. WIF usa arquivo de configuração de credenciais externas, diferente de chave privada de conta de serviço, mas ainda exige integridade/controle de origem e proteção das credenciais do IdP.

## Pendências e ativação segura futura

1. Aprovar método, identidade de origem, IAM mínimo, escopos e proteção/renovação de credenciais. Confirmar leitura das ACLs com o papel atual; se insuficiente, revisar com o administrador, sem escalada automática.
2. Validar backup **coerente** do SQLite + volume + marcador + journals e uma restauração isolada com checksums. Ver procedimento em `armazenamento-comprovantes.md`. Não basta copiar SQLite aberto ou guardar só o banco.
3. Aprovar e executar migração 008 em janela controlada, com captura/remoção/sincronização pausadas. Primeiro ensaiar a migração em banco sintético com schema 007 e verificar integridade. Não iniciar esta versão operacionalmente antes disso.
4. Auditar membros/restrições dos dois Drives e política de privacidade entre autores da mesma missão. As sete pastas por Drive e seus IDs foram informados após leitura supervisionada na 07B; revalidar os metadados antes do ensaio, sem criar pastas adicionais. Nenhuma pasta foi criada pelo agente.
5. Validar processos FACEPE e nomenclatura técnica. Definir classificação para tipos sem mapeamento; retenção, edição e exclusão remota continuam pendentes. Não usar processo inventado para superar bloqueio.
6. Implementar provedor aprovado e uma entrada operacional explícita para sincronização; retirar o bloqueio de transporte simulado em alteração revisada, com destino fixo Google/HTTPS, timeout, sem redirects/fallback, logs seguros e backoff limitado. Não há flag pronta para uploads reais nesta entrega. Preservar o volume local e a possibilidade de parar apenas o worker.
7. Autorizar ensaio real pequeno e supervisionado com arquivos sintéticos e SQLite temporário, **um em cada missão**, nos mesmos dois Drives. Testar também timeout com confirmação perdida, repetição com mesmo ID, 403, ACL e retomada; conferir no Google nome, checksum, pais, ID e ausência de duplicata. Toda escrita real dependerá dessa autorização futura. Não enviar comprovantes reais como primeiro teste.
8. Só após aceite do ensaio e revisão das políticas pendentes, decidir ativação operacional separada. Definir monitoramento, quota, alertas por códigos sem dados privados, frequência de reconciliação, auditoria de ACL e retenção de eventos.

Reversão segura futura: parar worker e manter captura/volume privado conforme autorização vigente; conservar SQLite com journal remoto e IDs para retomada. Nunca apagar/recriar journal ou reservar IDs novos para resolver um timeout. Não fazer rollback destrutivo da 008 nem purgar anexos locais após sincronização. Uso real permanece bloqueado pelas proteções sintéticas anteriores, que não foram relaxadas.

Após restaurar um backup anterior a uploads já realizados, não retomar envios automaticamente: o journal restaurado pode não conhecer IDs criados depois do backup. Será necessária conferência administrativa das referências e `appProperties` remotas antes da retomada. A recuperação automática entregue cobre interrupções com journal persistido, não perda/restauração antiga do próprio journal.

## Arquivos e validação

Criados: `app/core/drive_config.py`, `app/services/drive_credentials.py`, `app/services/google_drive_storage.py`, `app/services/receipt_drive_sync.py`, `app/db/migrations/008_receipt_drive_sync.sql`, `tests/test_google_drive_sync.py`, este guia e `docs/validacao-etapa07a.md`.

Alterados: `app/core/config.py`, `app/services/storage_contracts.py`, `app/repositories/receipts.py`, `app/templates/receipt_detail.html`, `app/templates/receipt_form.html`, `app/templates/receipts.html`, `.env.example`, `README.md`. Os testes anteriores `test_authentication.py`, `test_database.py`, `test_persistent_receipts.py`, `test_receipts.py` e `test_workspace_access.py` receberam atualização da contagem esperada de migrações para oito; o teste da interface local também passou a esperar o rótulo Aguardando sincronização.

Artefatos de validação criados em `artifacts/stage07a/`: `full-suite.log`, `final-contract-check.log`, `preservation.json` e `validation.json`.

Resultados, comandos e prova de preservação em [validacao-etapa07a.md](validacao-etapa07a.md). Não foi iniciada aplicação operacional nem realizado teste real no Google. As fontes oficiais acima foram consultadas para desenho/documentação, sem autenticação ou acesso à API Drive.

Continuação 07B: alterados `app/core/drive_config.py`, `app/services/google_drive_storage.py`, `.env.example`, `tests/test_google_drive_sync.py` (nome físico na simulação), `README.md` e este guia. Criado `tests/test_drive_folder_mapping.py`. O relato histórico do preflight foi preservado e recebeu uma atualização em [validacao-etapa07b.md](validacao-etapa07b.md), onde estão os resultados atuais e as pendências para um futuro upload sintético. `artifacts/stage07b/preflight.json` continua sendo a evidência histórica do bloqueio local, não um diagnóstico do Cloud Shell.
