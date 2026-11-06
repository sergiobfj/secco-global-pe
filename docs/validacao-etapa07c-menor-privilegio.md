# Revisão 07C — menor privilégio, somente validação local

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


## Resultado

**190 testes relevantes aprovados, zero falhas, zero erros, 47 não selecionados e dois avisos de depreciação existentes**, em **56,57 segundos**. Foram executados 57 cenários do executor 07C, 14 específicos desta revisão, 113 do mapeamento e seis regressões anteriores de configuração/upload simulado. Não foi reexecutada a suíte integral ou executada qualquer migração.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_drive_probe.py tests/test_drive_least_privilege.py tests/test_drive_folder_mapping.py tests/test_google_drive_sync.py -q -k 'not test_google_drive_sync or invalid_configuration or correct_drive_and_technical_name' -p no:cacheprovider
```

Log: `artifacts/stage07c/least-privilege/targeted-tests.log`. Não houve consulta a documentação externa nesta revisão, chamada autenticada, obtenção de token, upload real ou uso de credenciais. HTTP usa apenas `MockTransport`; os testes do executor bloqueiam também conexões de socket reais.

## Plano revisado

O adaptador consulta diretamente os Folder IDs existentes por `files.get`, com `supportsAllDrives=true` e exatamente:

```text
id,name,mimeType,parents,driveId,trashed,capabilities(canAddChildren)
```

Não chama `drives.get`; o transporte do ensaio recusa esse endpoint. A aprovação aceita **exclusivamente `drive.file` + `drive.metadata.readonly`**, inclusive na emissão do token IAM. `drive.readonly`, `drive` e aprovações anteriores que os incluam são recusados. Não existe ampliação automática em resposta a erro.

A remoção da consulta de nome de exibição do Drive não remove a prova de missão: `DRIVE_IDS` vincula cada país ao ID confirmado da 07B. Configuração invertida/diferente falha antes de consultar a pasta. A resposta de cada pasta precisa confirmar ao mesmo tempo ID solicitado, `driveId`, pai único igual à raiz da missão, nome exato da categoria, MIME pasta e `trashed=false`. ACLs paginadas da raiz, pasta e arquivo continuam sob a política restritiva. `canAddChildren=true` é exigido no preflight e novamente antes do POST.

## Confirmações solicitadas

1. **Escrita sob pastas existentes: pendente de validação real.** A autorização de leitura da 07B e os mocks não provam que `drive.file` permitirá criar arquivos sob esses pais. Se houver 401/403, ausência de capacidade ou ACL incompatível, parar antes de avançar para a outra missão. Não trocar pai, conceder papel ou ampliar escopo para fazer o teste passar. Este ponto será um critério do ensaio futuro autorizado.
2. **SHA-256 independente:** o aplicativo calcula SHA-256 dos bytes locais e consulta `sha256Checksum` no GET posterior do arquivo remoto. Não envia esse hash no JSON de criação ou em `appProperties`. Não usa hash do ACK do POST como comprovação. O resultado `ConfirmedRemoteReceipt` devolve o valor efetivamente recebido no GET, depois de conferido. Tags de idempotência/missão corretas não substituem campo remoto ausente/divergente. Sem disponibilidade desse campo, não há estado verificado. Não foi feito download de arquivo.
3. **Dois PNGs de 69 bytes:** o plano e ZIP preparados antes desta revisão foram conservados. Os dois conteúdos determinísticos, nomes, tamanhos e SHA-256 são os mesmos, um por missão, nas pastas Deslocamento/Deslocamentos já definidas.
4. **Aprovação vinculada:** permanecem os hashes exatos do mapa/destinos e do plano/arquivos, a conta fonte, validade curta conferida a cada requisição, confirmação de backup/sintéticos e retenção. O modelo foi alterado só nos escopos e continua pendente (`approved=false`, `backup_verified=false`); não foi assinada ou preenchida uma autorização em nome do responsável.
5. **Parada por permissão:** o teste de 403 no POST confirma uma única tentativa, ID argentino preservado, Portugal ainda aguardando sem ID reservado, nenhum objeto criado e nenhum escopo ampliado. O mesmo comportamento de parada se aplica ao preflight, IAM, hashes e demais erros.

O campo remoto é tratado como checksum calculado e retornado pelo serviço Google, não como uma tag gravada pela aplicação. Sua disponibilidade real para o arquivo binário será conferida no ensaio. Os testes simulam o servidor calculando o hash dos bytes recebidos e demonstram que um ACK com hash correto não vence um GET posterior divergente. Não se afirma que mocks provam o conteúdo de uma resposta futura do Google.

## Novas regressões e preservação

Foram testados os 14 GETs de pastas com os campos exatos, proibição de `drives.get`, inversão dos Drives antes da rede, escopos reduzidos, dois arquivos e repetição sem duplicatas, ausência de hash no JSON enviado, hash remoto ausente, hash correto só no ACK, parada por 403, expiração da aprovação e metadados locais de integridade inválidos. O tamanho local precisa ser inteiro positivo e o checksum local um SHA-256 válido antes de qualquer consulta.

SQLite operacional, `.env` e migrações 001–008 mantêm os SHA-256 do início. Não houve abertura de banco operacional, aplicação da 008, startup, dependência nova, deploy, commit ou push. `RECEIPTS_DRIVE_MODE=disabled` permanece. A restauração/idempotência sintética anterior também foi reexercitada pelos testes do executor com schema temporário próprio.

Alterados: `app/core/drive_config.py`, `app/services/google_drive_storage.py`, `app/services/drive_supervised.py`, `tests/test_drive_probe.py`, `tests/test_google_drive_sync.py`, `docs/drive-probe-approval.example.json`, `docs/ensaio-supervisionado-drive.md`, `docs/validacao-etapa07c.md`, `docs/integracao-google-drive.md` e `README.md`.

Criados: `tests/test_drive_least_privilege.py`, este relatório e `artifacts/stage07c/least-privilege/targeted-tests.log` / `validation.json`. O ZIP, o plano e a evidência de restauração anteriores não foram substituídos.

## Próxima autorização

O [procedimento revisado](ensaio-supervisionado-drive.md) continua com executor offline por padrão e exige nova aprovação explícita antes do comando de execução real. A proposta limita-se aos dois PNGs já preparados, impersonação temporária da conta de serviço, somente `drive.file` + `drive.metadata.readonly`, mesmos IDs de destino e retenção dos arquivos sem limpeza remota.

O ajuste funcionou nos testes locais. SDK, IAM, APIs, quotas, ACLs/capacidades e compatibilidade de criação com `drive.file` continuam condições a verificar no ambiente autorizado. Não há declaração de prontidão de produção.
