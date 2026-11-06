# Validação — etapa 07A

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


> **Distribuição pública:** nomes, e-mails, domínio Google Workspace, IDs de Drive/pastas e identificadores Google Cloud deste documento são fictícios. Resultados e decisões descritos referem-se ao projeto operacional.


## Escopo

Somente concessões temporárias de `TemporaryDatabase`, volumes dentro dessas concessões, PNG de 1×1 gerado nos testes, identidades/tokens fictícios e `httpx.MockTransport`. A política de isolamento é ativada antes da importação da aplicação; `.env` não é carregado nos testes. Nenhum comprovante real foi utilizado.

Não foram abertas conexões SQLite ao banco operacional, aplicadas migrações operacionais, iniciados servidores operacionais, feitas chamadas reais ao Drive, criadas pastas, alteradas políticas Google/IAM, provisionadas credenciais reais, executados deploy, commit ou push. A consulta à documentação pública Google foi leitura de páginas técnicas, sem autenticação ou API Drive.

## Execuções

Primeira rodada focada:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_google_drive_sync.py tests/test_persistent_receipts.py -q
```

Resultado: **82 aprovados**, zero falhas, em 187,74 s. Três avisos: duas deprecações já existentes de Starlette/httpx e anyio; um aviso de impossibilidade de escrever no cache pytest do projeto. Não foi alterada a permissão desse cache.

Rodada dos cenários adicionais de reinício, confirmação antes de falha SQLite, coordenação, migração, quatro operadores e concorrência:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_google_drive_sync.py -q -k 'sqlite_failure or restart_restores or marcos_cannot or 008_is or four_operators or concurrent_retry' -p no:cacheprovider
```

Resultado: **9 aprovados**, 43 não selecionados, zero falhas, em 30,36 s. Apenas as duas deprecações existentes. A suíte integral usa `-p no:cacheprovider` para evitar o aviso de cache, sem relaxar a política de bancos.

O resultado da suíte integral está registrado em `artifacts/stage07a/full-suite.log` e consolidado ao final deste relatório.

Após consolidar o tipo de erro e o roteamento na interface `SharedDriveAdapter`, os fluxos afetados foram revalidados:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_google_drive_sync.py -q -k 'enqueue_upload_verify_and_ui or remote_errors_preserve_local or lost_confirmation or four_operators' -p no:cacheprovider
```

Resultado: **11 aprovados**, 42 não selecionados, zero falhas, em 18,77 s, com duas deprecações existentes. Log: `artifacts/stage07a/final-contract-check.log`.

## Cobertura da integração

- Seleção do Drive de Argentina e Portugal; recusa de IDs invertidos pela identidade remota do Drive.
- Operação individual de Tiago, Bruno, Hugo e Alan em suas missões, independentemente da condição de beneficiário.
- Bloqueio de outro autor da mesma missão, da outra missão, de conta desabilitada e de Marcos, inclusive no download privado. Coordenação mantém consulta consolidada.
- Nome técnico preservado; processo/nome pendente e tipos sem categoria não são enviados.
- Upload multipart com `supportsAllDrives=true`; confirmação posterior por GET, SHA-256, tamanho, pais, Drive, MIME, nome e chave idempotente.
- Permissão negada, falha de conexão, timeout com upload já concluído, redirecionamento, JSON inválido e ID reservado inválido.
- Interrupção antes de enviar, depois de criar remotamente, reinício completo da aplicação e rollback SQLite após confirmação remota.
- Reenvio sequencial e concorrente sem duplicação; mesmo ID reservado e uma única criação remota.
- Reconciliação de estados interrompidos e de erro; confirmação inválida jamais exibida como sucesso.
- ACL pública, de domínio, de grupo não auditável, de Marcos ou de operador da outra missão bloqueia upload; leitura paginada de permissões.
- Pastas de outro Drive/categoria, atalhos e pastas excluídas são recusados antes do upload.
- Metadados editados invalidam confirmação; exclusão local suspende sincronização e conserva a referência remota, sem excluir no Google.
- Credencial ausente/expirada e transporte real bloqueados antes de chamada; token fora de `repr`, mensagens HTTP e segredos fictícios ausentes dos logs capturados.
- Migração aditiva 008 mantém schema e linhas da 007 sintética, com `integrity_check=ok` e `foreign_key_check` vazio. Migrações anteriores mantêm seus checksums.
- Interface detalha armazenamento local, espera, confirmação simulada, erro e suspensão sem alterar os passos da captura. Formulário, listagem e detalhe reaproveitam os estilos responsivos existentes.

## Preservação

Leitura binária para comparação SHA-256, sem abrir o SQLite pela API ou consultar dados operacionais:

| Alvo | Resultado |
|---|---|
| `data/secco.sqlite3` | SHA-256 idêntico ao início |
| `.env` | SHA-256 idêntico ao início; conteúdo não publicado |
| Migrações 001–007 | SHA-256 idênticos ao início |
| Adaptador/journal local | Código preservado; regressões incluídas |

Evidência legível por máquina: `artifacts/stage07a/preservation.json`. O fingerprint não certifica backup/restauração ou durabilidade contra perda física do disco; esses testes permanecem pendentes de autorização e ambiente apropriado.

## Limites da validação

Simulação não prova escopos, disponibilidade de SHA-256 na API, capacidade do Colaborador de listar todas as ACLs, permissões reais, identidade WIF, latência, quota ou durabilidade do Google. O primeiro ensaio real permanece pendente. Não foi criada alternativa para contornar o bloqueio de chaves JSON.

Procedimento futuro, métodos de autenticação, riscos e inventário de arquivos: [integracao-google-drive.md](integracao-google-drive.md).

## Resultado integral final

```powershell
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider
```

**522 aprovados, zero falhas, zero erros, dois avisos de depreciação já existentes**, em **564,25 s** (9 min 24 s). São 469 casos anteriores e 53 casos novos de integração. Não houve exclusão de cenários anteriores. Log integral: full-suite.log (`artifacts/stage07a/full-suite.log`, não distribuído). A checagem adicional de 11 casos confirmou o ajuste final da interface compartilhada de erros/roteamento.

Todos os limites de ativação permanecem: transporte somente simulado, configuração padrão desativada, captura somente sintética, produção bloqueada. Não há botão, rota, comando operacional ou variável que permita envio real nesta versão. A ativação exige aprovação do método de autenticação, backup/restauração validados e ensaio controlado, conforme o guia.
