# Etapa 07C — renovação segura no Cloud Shell, pacote v3

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


> **Distribuição pública:** nomes, e-mails, domínio Google Workspace, IDs de Drive/pastas e identificadores Google Cloud deste documento são fictícios. Resultados e decisões descritos referem-se ao projeto operacional.


> Procedimento v3 preservado para histórico. O ensaio v3 parou na ACL da raiz Argentina (política de 3 membros por missão). Usar a [correção v4](correcao-acl-cloud-shell-07c-v4.md). Não executar novamente o pacote v3 nem reutilizar seu aceite.

## Diagnóstico comprovado no código v2

O arquivo que provocou o erro é **`.local/approval.json`**, no diretório de estado da v2. A operação foi `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)`, chamada por `write_new` ao final de `authorize`. Como a primeira autorização foi preservada, uma segunda criação recebe `FileExistsError`, `errno=17` (`EEXIST`). O arquivo antigo não foi truncado nem sobrescrito.

`prepare_offline_report_write` é uma fase desatualizada: `authorize` chama `initialize`, que retorna deixando essa fase definida. Depois valida política/novo aceite e tenta gravar a aprovação, sem atualizar a fase. Não há evidência de que `evidence/offline-check.json` tenha causado o erro informado. O guard `if not ...exists()` desse relatório evita sua recriação no fluxo sequencial reproduzido.

A reprodução usa o ZIP v2 original: preparação → política → primeira autorização → IAM Credentials respondendo 403 em transporte HTTP simulado → segunda autorização. O resultado é exatamente o JSON informado, e a única tentativa de gravação nessa renovação é `.local/approval.json`. Checkpoint, marcador, política, aprovação antiga e relatório permanecem com os mesmos hashes. A falha IAM ocorre antes da construção do adaptador e de qualquer reserva de ID/upload.

A criação exclusiva é uma **proteção intencional**. A falta de renovação sem sobrescrita e a fase incorreta são **defeitos do executor**, não justificativas para apagar a aprovação ou trocar `O_EXCL` por truncamento.

## Alterações e limites

- A v3 acrescenta `check-renewal` (verificação offline) e `renew-authorization` (novo aceite explícito).
- `renew-authorization` exige predecessor válido selecionado, preserva seu conteúdo e cria `.local/authorizations/approval-<32 hex>.json`, com criação exclusiva. Não há arquivo de aprovação ativo escolhido automaticamente.
- `execute` exige `--approval-file` com o registro exato, manifesto v3 e validade vigentes. O registro v2 não é aceito para execução v3. Aprovação expirada só serve como histórico; nunca se reaproveitam seu prazo ou consentimento.
- `--resume-from DIRETORIO-V2` verifica o manifesto v2 conhecido, o código e os arquivos imutáveis. Plano, mapa, PNGs e compromisso da política devem ser idênticos. Usa **o mesmo checkpoint, journal, volume e lock** da v2, no diretório original. Não transfere ou bifurca o estado.
- Na retomada, checkpoint e marcador devem existir e ser íntegros. Política precisa coincidir com o compromisso original. O checkpoint só é restaurado em temporário isolado, sem migrações.
- Antes de autorizar a recuperação, exige duas missões com `remote_id=null`, `attempts=0`, `state=aguardando`, `ever_verified=0`, `error_code=null` e **nenhum evento** no journal. A inspeção v3 também usa esse critério mais estrito. Qualquer indicação de atividade remota impede esta recuperação e exige outro procedimento aprovado de reconciliação.
- A nova aprovação registra hashes do checkpoint, da identidade do journal (incluindo volume), do predecessor, do manifesto, plano, mapa e política. A identidade do journal é conferida novamente antes das credenciais; renovações seguintes não podem trocar o volume vinculado. O hash do checkpoint no momento da autorização é histórico: checkpoints legítimos posteriores podem mudar durante um ensaio autorizado.
- Falhas locais informam a fase correta. Uma gravação interrompida permanece como arquivo incompleto, sem seleção automática e sem exclusão. Pode-se registrar outro novo aceite a partir de um predecessor válido, com nome novo; não se usa o arquivo parcial como predecessor.

O ZIP e o código v2 permanecem intactos. A recuperação só acrescenta novos registros de autorização e, se solicitado, novas evidências no diretório de estado v2. Os arquivos existentes não são apagados ou substituídos para renovar.

Limites preservados: dois PNGs de 69 bytes; `drive.file` e `drive.metadata.readonly`; credenciais temporárias; sem chave JSON; SHA-256 remoto obtido por `sha256Checksum`; validações de missão/pasta/raiz/ID/nome/tamanho; nenhuma ampliação automática de permissões; retenção sem exclusão remota. O executor de upload e o contrato de idempotência permanecem os mesmos. Testes simulados não substituem o ensaio real nem certificam produção.

## Pacote e identidade

- ZIP: `artifacts/stage07c/cloud-shell-v3/secco-drive-07c-cloud-shell-v3.zip`.
- 32.955 bytes; 25 entradas.
- ZIP SHA-256: `7655fb0d35ff91277c6b4112dcbb1b041631e14f5ec68a0242e729504616385c`.
- Manifesto SHA-256: `f6916d72f32efe0c3f08f740e48cfc9bb7263d821a67af69d88ea31103980d9f`.
- Manifesto v2 aceito como origem: `89ed1e3a19a658468cd74f9562baa0f4dd73be96a5a973a73d389118b89e62de`.
- ZIP v2 preservado: SHA-256 `a6053701405357d914917d7d20efb0ee099f4f8bf47f37c0135913febab24f53`.
- Plano: `33ea1b63f3fcefa26837d30c0118a3d3d8f2c0e6ffbd4ab4bbda54dd7af4f012`.
- Mapa: `ed3b2b8b7567a85e13725b044ea0144caaeb9fb7fd4b23b0156983a6f3006066`.

O ZIP não contém `.env`, banco, migrações, credenciais, tokens, chaves ou e-mails pessoais. Não há dependência nova: reutilize a venv já instalada, inclusive se ela ainda estiver no diretório v1.

| Missão | PNG | SHA-256 | Shared Drive | Folder ID |
|---|---|---|---|---|
| Argentina | `secco-ensaio-77d0936125e58eb2-argentina.png` | `a6b72a19d0e58175a61556e67b622df98f65b6787f8238d3558760048e94ca58` | `0AARGENTINAEXEMPLO1` | `1EXEMPLO_AR_deslocamentos_0000000` (Deslocamento) |
| Portugal | `secco-ensaio-77d0936125e58eb2-portugal.png` | `3459ce0d41c9e499a998178ac583e4c8523e46bc4632646b3a898400a369e8b5` | `0APORTUGALEXEMPLO01` | `1EXEMPLO_PT_deslocamentos_0000000` (Deslocamentos) |

## Comandos permitidos agora — somente offline

Não executar outro processo v2/v3 em paralelo. Não executar novamente `authorize` na v2, apagar sua aprovação, trocar checkpoint, reiniciar o ensaio ou recriar a política. Preserve todos os arquivos. Os caminhos abaixo pressupõem o estado ativo em `$HOME/secco-drive-07c-v2`; se estiver em outro diretório, pare para confirmar o caminho correto.

Envie apenas o ZIP v3 para `$HOME` pelo navegador. Confira e extraia em diretório novo:

```bash
bash <<'INSTALAR_CODIGO_V3_OFFLINE'
set -euo pipefail
umask 077
cd "$HOME"
printf '%s  %s\n' '7655fb0d35ff91277c6b4112dcbb1b041631e14f5ec68a0242e729504616385c' 'secco-drive-07c-cloud-shell-v3.zip' | sha256sum -c -
if [ -e "$HOME/secco-drive-07c-v3" ]; then
  echo 'PARE: diretorio v3 ja existe; preservar e revisar, sem sobrescrever.'
  exit 1
fi
mkdir -m 700 "$HOME/secco-drive-07c-v3"
python3 -m zipfile -e secco-drive-07c-cloud-shell-v3.zip secco-drive-07c-v3
cd "$HOME/secco-drive-07c-v3"
python3 -I -S -B verify_package.py
INSTALAR_CODIGO_V3_OFFLINE
```

O manifesto deve ser exatamente o v3 acima. Faça a verificação offline de renovação usando o estado existente, sem copiar arquivos:

```bash
bash <<'CONFERIR_RENOVACAO_OFFLINE'
set -euo pipefail
set -o noclobber
umask 077
OLD="$HOME/secco-drive-07c-v2"
if [ -x "$OLD/.venv/bin/python" ]; then
  PY="$OLD/.venv/bin/python"
elif [ -x "$HOME/secco-drive-07c/.venv/bin/python" ]; then
  PY="$HOME/secco-drive-07c/.venv/bin/python"
else
  echo 'PARE: interpretador isolado instalado nao encontrado; nao reinstalar automaticamente.'
  exit 1
fi
cd "$HOME/secco-drive-07c-v3"
"$PY" -B probe.py verify --resume-from "$OLD"
CHECK="$OLD/evidence/renewal-check-v3-$(date -u +%Y%m%dT%H%M%SZ).json"
"$PY" -B probe.py check-renewal --resume-from "$OLD" --previous-approval .local/approval.json > "$CHECK" || {
  cat "$CHECK"
  echo 'PARE: verificacao recusada; preservar arquivos e informar o JSON.'
  exit 1
}
cat "$CHECK"
printf 'Evidencia offline: %s\n' "$CHECK"
CONFERIR_RENOVACAO_OFFLINE
```

Resultado obrigatório: `renewal=eligible`, `execution_started=false`, `authorization_created=false` e hashes v3/plano/mapa corretos. Esse resultado é elegibilidade local para nova aprovação, não autorização nem confirmação remota. O lock temporário do arquivo original é compartilhado com v2 e liberado ao terminar. Não foi solicitada credencial ou feita conexão ao Google.

**PARE AQUI.** Entregue o JSON controlado de elegibilidade ao responsável e obtenha novo aceite explícito vinculado ao manifesto v3, dois PNGs/hashes/destinos acima, conta humana fonte, conta de serviço, escopos, prazo curto e retenção. O aceite antigo não é transferido automaticamente. Uma aprovação na conversa também não executa automaticamente nenhum comando.

## Somente depois de uma nova aprovação explícita

Estes comandos são instruções futuras. Não executá-los como parte do diagnóstico ou da atualização. Abra o terminal mantendo entrada interativa para a confirmação. Atribua `OLD` e `PY` novamente se o bloco anterior já terminou:

```bash
OLD="$HOME/secco-drive-07c-v2"
if [ -x "$OLD/.venv/bin/python" ]; then
  PY="$OLD/.venv/bin/python"
elif [ -x "$HOME/secco-drive-07c/.venv/bin/python" ]; then
  PY="$HOME/secco-drive-07c/.venv/bin/python"
else
  echo 'PARE: venv ausente.'
fi
cd "$HOME/secco-drive-07c-v3"
```

Se a venv estiver ausente, não executar os próximos comandos. Substitua a referência pelo identificador real do novo aceite (não usar a referência anterior ou o texto de exemplo). A conta fonte abaixo é a informada pelo responsável; o executor não faz login:

```bash
"$PY" -B probe.py renew-authorization \
  --resume-from "$OLD" \
  --previous-approval .local/approval.json \
  --operator tiago@secco.example \
  --reference 'SUBSTITUIR-PELA-REFERENCIA-DO-NOVO-ACEITE-V3' \
  --minutes 30
```

Confirme digitando `AUTORIZO CLOUD SHELL 07C` somente com o novo aceite. O retorno contém `authorization_file=.local/authorizations/approval-<32 hex>.json`, validade UTC e `execution_started=false`. Esse arquivo é novo e fica no estado v2; a aprovação original não muda. A renovação não obtém token nem envia arquivos. Em erro, pare e preserve inclusive registros incompletos.

Antes de executar, confira arquivo retornado, validade e dados do novo aceite. Copie exatamente o caminho retornado, sem selecionar “o mais recente” automaticamente:

```bash
read -r -p 'authorization_file exato retornado pela nova aprovacao: ' APPROVAL_FILE
"$PY" -B probe.py execute --resume-from "$OLD" --approval-file "$APPROVAL_FILE" --confirm-write
```

Esse último comando pode obter credenciais e fazer os uploads; exige a nova autorização acima. Não deve ser executado agora. Se houver erro IAM/401/403/permissão, pare sem alterar escopos ou permissões. Em timeout ou resultado parcial, preserve o checkpoint e peça revisão; não renove como se não houvesse atividade remota. Não há exclusão remota autorizada.

A repetição para idempotência só ocorre após sucesso, dentro do prazo aprovado, usando exatamente o mesmo `OLD`, `APPROVAL_FILE` e comando. Devem permanecer dois IDs e verificações completas de Folder ID, Drive ID, nome, tamanho e SHA-256 remoto. Uma repetição não pode inicializar estado novo.

## Interrupções e evidências

- `retomada_exige_checkpoint_e_marcador`, corrupção, marcador divergente ou manifesto alterado: parar. Não copiar backup antigo sobre o atual nem fabricar marcador.
- `atividade_remota_possivel_revisao_obrigatoria`: este fluxo não pode renovar; conservar IDs, tentativas e eventos. Necessária revisão/reconciliação separada.
- `ensaio_em_uso`: aguardar o processo conhecido terminar; não apagar lock nem iniciar outro estado.
- `authorization_record_write` com erro: o arquivo antigo segue preservado. Um registro novo parcial não é utilizável. Para tentar outra renovação, obter novo aceite e selecionar explicitamente um predecessor válido preservado. Não apagar o parcial nem usar edição de JSON para torná-lo válido.
- Se o processo interrompeu depois de gravar o registro mas antes de exibir o resultado, não escolher um registro por data automaticamente. Conservar os registros e solicitar revisão de qual aceite/arquivo foi concluído antes de qualquer execução.
- O procedimento presume o checkpoint original atual, sem restauração manual para uma versão anterior, e o relato de falha IAM antes de upload. Metadados locais não provam a ausência de atividade remota diante de rollback deliberado ou perda de histórico. Havendo dúvida, interromper para reconciliação autorizada; não inferir segurança apenas de `safe_to_prepare_fresh_copy`.

Preserve ambos os ZIPs, checksums, manifesto, relatório offline, JSON de elegibilidade, checkpoint e resultados. Não compartilhe `.local`, política com e-mails ou diretório do SDK. A aprovação histórica contém conta humana e fica somente local. Export seguro, sem chamadas externas:

```bash
"$PY" -B probe.py evidence --resume-from "$OLD"
```

O arquivo indicado está em `$OLD/exports/`, não no diretório de código v3. Baixe somente esse ZIP pelo navegador. Não compactar o diretório pessoal, `.local`, venv ou SDK. O export e os registros de autorização são novos; evidências antigas permanecem intactas.

## Código e testes

Alterados `tools/drive_cloud_shell/probe.py`, `verify_package.py`, `README.txt`, `scripts/build_drive_cloud_shell_package.py` e testes de seleção explícita em `tests/test_drive_cloud_shell_package.py`. Criado `tests/test_drive_cloud_shell_renewal.py`. Não houve alteração do adaptador de upload, banco operacional, `.env`, migrações, IAM ou implantação.

Os testes usam SQLite temporário, PNGs sintéticos, credenciais fictícias e transporte HTTP simulado. Rede real e execução do gcloud ficam bloqueadas nos testes de fluxo. Exercitam o erro exato v2, falha IAM, novas renovações, predecessor expirado, recusa de escopo amplo, checkpoint compartilhado, eventos históricos, IDs/tentativas, arquivos ausentes/corrompidos, mudança de volume, cancelamento, lock e gravação parcial. Os testes existentes verificam dois uploads simulados e repetição sem duplicações. O gate declarativo Linux é simulado no Windows; não houve execução local de kernel Linux nesta entrega.

**Resultado final: 69 testes aprovados, zero falhas, dois avisos de depreciação existentes; 104,79 segundos.** Comando: `.venv/Scripts/python.exe -m pytest tests/test_drive_cloud_shell_renewal.py tests/test_drive_cloud_shell_package.py tests/test_drive_cloud_shell_posix.py tests/test_database_isolation.py -q -p no:cacheprovider`. Evidências em `artifacts/stage07c/cloud-shell-v3/tests.log`, `validation.json` e `preservation-check.json`. Os hashes do `.env`, banco operacional, oito migrações e ZIP v2 foram conferidos e permaneceram iguais. Não houve chamada real ao Google, autenticação operacional, upload, alteração IAM, deploy, commit ou push.
