# Etapa 07C — correção da política de ACL, pacote v4

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


> **Distribuição pública:** nomes, e-mails, domínio Google Workspace, IDs de Drive/pastas e identificadores Google Cloud deste documento são fictícios. Resultados e decisões descritos referem-se ao projeto operacional.


> Substitui o [procedimento v3](renovacao-cloud-shell-07c-v3.md) para a próxima tentativa. **Não executar novamente o pacote v3.** Os aceites v2/v3 não podem ser reutilizados: servem apenas como predecessores históricos de uma nova aprovação v4.

## Diagnóstico

O ensaio real v3 obteve credenciais por impersonação e parou na validação de permissões da **raiz do Drive Argentina**. A causa está no executor, não no Drive:

- `install_policy` (v2/v3) exigia exatamente **3 membros por missão** (`len(v)!=3`): duas pessoas por missão mais a conta de serviço. `configure_policy` pedia dois e-mails por missão.
- Os dois Shared Drives têm **6 participantes autorizados**: os cinco sócios e a conta de serviço. O responsável confirmou que os cinco sócios podem acessar ambos os Drives.
- `GoogleDriveAdapter._acl` recusa qualquer principal fora de `READERS[missao]`. Como a primeira ACL conferida no preflight é a da raiz Argentina, o v3 parou ali.

A v3 relatava essa condição apenas como `permissao`, igual a um 401/403 da API. O rótulo `ACL_FORA_DA_POLITICA` veio do diagnóstico feito fora do repositório; a v4 passa a emiti-lo como código controlado `acl_fora_da_politica`.

**Sem efeito remoto ou local.** Em `ProbeJournal.run`, o `preflight` dos 14 destinos roda antes de `reserve_id`, fora do bloco que grava estado. A falha não reservou ID, não registrou tentativa nem evento, não gravou checkpoint e não criou `result-*.json`. Isso foi reproduzido com o ZIP v3 original, sobre um estado v2 real com o histórico IAM 403:

- única chamada de ACL na raiz Argentina;
- zero `generateIds` e zero POST;
- journal intacto (`safe_to_prepare_fresh_copy=true`);
- todos os arquivos v2 inalterados, exceto o registro de autorização v3.

Teste: `test_v3_acl_failure_is_reproduced_before_any_reservation_and_leaves_state_intact`.

## Política v4

- **Membros:** os cinco sócios mais a conta de serviço `global-pe-drive@exemplo-global-pe.iam.gserviceaccount.com`, **idênticos nas duas missões**. Os cinco sócios são as contas da allowlist de `app/core/workspace_access.py` (fictícias nesta distribuição).
- **Compromisso:** `bff24b4b31b9e5485cff91c1d02c4d4d9de67f9e527c31026e0cb9824061009a`. Substitui `0532899c44715ac60733136237ebfa93d2bbdf5f073986238b90eb9ee92c16ee`, que corresponde a 2 pessoas + conta de serviço por missão.
- **Mudança explícita em relação à v2/v3:** a coordenação (Marcos) e os operadores da outra missão deixam de ser recusados **na ACL do Drive deste ensaio**. A separação de comprovantes entre autores dentro da aplicação não muda.
- **Continua sendo recusado:**
  - qualquer outro usuário;
  - grupo, domínio ou `anyone`;
  - permissão excluída ou papel desconhecido;
  - ACL sem a conta de serviço.
- **Política local:** os e-mails continuam fora do ZIP. Os cinco são digitados no Cloud Shell e conferidos contra o compromisso. O arquivo novo é `.local/access-policy-v4.json`, criado de forma exclusiva. O arquivo antigo `.local/access-policy.json` permanece intacto e não é lido pela v4.

`READERS` da aplicação (`app/core/drive_config.py`) **não foi alterado**. Ele rege o adaptador da aplicação, que ainda está restrito a `MockTransport` (07A). Veja as pendências.

## Alterações

O v3 não foi editado. As fontes `tools/drive_cloud_shell/` e o builder v3 permanecem intactos, e um teste confirma que o builder v3 ainda reproduz o ZIP v3 byte a byte.

Arquivos novos:

- `tools/drive_cloud_shell_v4/probe.py`, `verify_package.py` e `README.txt`: cópia do v3 com diferenças pontuais. O diff está em `artifacts/stage07c/cloud-shell-v4/probe-v3-to-v4.diff`.
- `scripts/build_drive_cloud_shell_package_v4.py`: deriva do `payload()` v3 e só aceita gerar o pacote se adaptador, journal, plano, mapa e PNGs forem byte a byte iguais ao ZIP v3 preservado.
- `tests/test_drive_cloud_shell_v4.py`.

Em relação ao ZIP v3, mudam somente `probe.py`, `verify_package.py`, `README.txt`, `policy-contract.json`, `approval.template.json` e `MANIFEST.json`. O adaptador de upload, o contrato de idempotência, os escopos e o plano são os mesmos.

Comportamento v4:

1. **Retomada obrigatória.** Toda ação de estado exige `--resume-from DIRETORIO-V2` (`prepare`, `configure-policy`, `authorize`, `check-renewal`, `renew-authorization`, `execute`, `evidence`). Sem esse parâmetro, o executor para com `v4_exige_resume_from` antes de criar qualquer arquivo. A v4 nunca inicializa ou bifurca journal e usa o mesmo checkpoint, marcador e lock da v2.
2. **Vínculo da política.** `--resume-from` exige que a v2 tenha o compromisso antigo e que a v4 declare substituir exatamente esse compromisso (`vinculo_da_politica`).
3. **Predecessor.** Aceites v2 e v3 são aceitos **somente como histórico** vinculado à política antiga. Aceites v4 são aceitos somente com a política nova. O novo registro grava manifesto, política, arquivo e hash do predecessor.
4. **Execução.** `execute` só aceita registro com manifesto v4 **e** política v4. Registros v2 ou v3, ou registros forjados com apenas um dos dois vínculos, param com `vinculo_da_aprovacao` antes de credenciais.
5. **Diagnóstico de ACL.** Quando um principal está fora da política, o código é `acl_fora_da_politica`, com `acl_mission` e `acl_resource` (`drive_root`/`folder`/`file`). Um 401/403 continua sendo `permissao`. Nenhum e-mail ou mensagem externa é impresso.

Limites mantidos:

- dois PNGs de 69 bytes;
- somente `drive.file` e `drive.metadata.readonly`;
- token temporário, sem chave JSON;
- `sha256Checksum` remoto e conferência de pasta, raiz, ID, nome e tamanho;
- nenhuma alteração de permissões, exclusão ou limpeza remota.

## Pacote e identidade

- ZIP: `artifacts/stage07c/cloud-shell-v4/secco-drive-07c-cloud-shell-v4.zip` (34.093 bytes, 25 entradas, build determinístico).
- ZIP SHA-256: `47b891fa9a90b05ff746a6bc7036078c6146c77ab08c5e6c4b6f850fc4fa7cf1`.
- Manifesto SHA-256: `f5f885a3e01184779a2173df4a4bdba5e7f16a77651dbf34bb060d2b24a9b78c`.
- Política: `bff24b4b31b9e5485cff91c1d02c4d4d9de67f9e527c31026e0cb9824061009a`, com 6 membros por missão.
- Origem aceita: estado v2, manifesto `89ed1e3a19a658468cd74f9562baa0f4dd73be96a5a973a73d389118b89e62de`.
- Predecessores históricos: v2 (`89ed1e3a…`) e v3 (`f6916d72f32efe0c3f08f740e48cfc9bb7263d821a67af69d88ea31103980d9f`).
- ZIPs v1/v2/v3 preservados com os hashes anteriores.
- Plano `33ea1b63f3fcefa26837d30c0118a3d3d8f2c0e6ffbd4ab4bbda54dd7af4f012` e mapa `ed3b2b8b7567a85e13725b044ea0144caaeb9fb7fd4b23b0156983a6f3006066`, iguais aos da v3.

| Missão | PNG (69 bytes) | SHA-256 | Shared Drive | Folder ID |
|---|---|---|---|---|
| Argentina | `secco-ensaio-77d0936125e58eb2-argentina.png` | `a6b72a19d0e58175a61556e67b622df98f65b6787f8238d3558760048e94ca58` | `0AARGENTINAEXEMPLO1` | `1EXEMPLO_AR_deslocamentos_0000000` (Deslocamento) |
| Portugal | `secco-ensaio-77d0936125e58eb2-portugal.png` | `3459ce0d41c9e499a998178ac583e4c8523e46bc4632646b3a898400a369e8b5` | `0APORTUGALEXEMPLO01` | `1EXEMPLO_PT_deslocamentos_0000000` (Deslocamentos) |

O ZIP não contém `.env`, banco, migrações, credenciais, tokens, chaves ou e-mails pessoais (somente o da conta de serviço). Não há dependência nova: reutilize a venv já instalada.

## Comandos permitidos agora — somente offline

Não executar nenhum processo v3 nem outro processo em paralelo. Não apagar, editar ou mover:

- o checkpoint;
- o marcador;
- a política antiga;
- os aceites v2/v3;
- as evidências.

Os caminhos pressupõem o estado ativo em `$HOME/secco-drive-07c-v2`. Se for outro diretório, pare e confirme.

Envie apenas o ZIP v4 para `$HOME` pelo navegador. Confira e extraia em diretório novo:

```bash
bash <<'INSTALAR_CODIGO_V4_OFFLINE'
set -euo pipefail
umask 077
cd "$HOME"
printf '%s  %s\n' '47b891fa9a90b05ff746a6bc7036078c6146c77ab08c5e6c4b6f850fc4fa7cf1' 'secco-drive-07c-cloud-shell-v4.zip' | sha256sum -c -
if [ -e "$HOME/secco-drive-07c-v4" ]; then
  echo 'PARE: diretorio v4 ja existe; preservar e revisar, sem sobrescrever.'
  exit 1
fi
mkdir -m 700 "$HOME/secco-drive-07c-v4"
python3 -m zipfile -e secco-drive-07c-cloud-shell-v4.zip secco-drive-07c-v4
cd "$HOME/secco-drive-07c-v4"
python3 -I -S -B verify_package.py
INSTALAR_CODIGO_V4_OFFLINE
```

O manifesto deve ser exatamente `f5f885a3…b78c`. Os passos seguintes são **interativos**: digite-os diretamente no terminal, sem heredoc, porque `configure-policy` lê os e-mails do teclado.

```bash
OLD="$HOME/secco-drive-07c-v2"
if [ -x "$OLD/.venv/bin/python" ]; then PY="$OLD/.venv/bin/python"
elif [ -x "$HOME/secco-drive-07c/.venv/bin/python" ]; then PY="$HOME/secco-drive-07c/.venv/bin/python"
else echo 'PARE: venv ausente; nao reinstalar automaticamente.'; fi
cd "$HOME/secco-drive-07c-v4"
"$PY" -B probe.py verify --resume-from "$OLD"
"$PY" -B probe.py configure-policy --resume-from "$OLD"
```

`verify` deve mostrar o manifesto v4. `configure-policy` pede os **cinco e-mails dos sócios**, um por vez. Eles valem para as duas missões, a ordem é indiferente e a conta de serviço é acrescentada pelo programa. O retorno deve ser `policy=verified`, `members_per_mission=6`, `policy_file=.local/access-policy-v4.json`.

Se aparecer `politica_nao_confere`, nada foi gravado: confira a grafia e repita. Não altere o compromisso nem os membros do Drive.

Em seguida, a verificação offline de renovação. Liste os registros existentes e informe **exatamente** o registro v3 usado no `execute` interrompido. Ele foi retornado pelo `renew-authorization` v3. Não escolha "o mais recente" automaticamente. Se houver dúvida sobre qual registro é, pare. O aceite v2 `.local/approval.json` também é aceito como predecessor histórico.

```bash
ls -l "$OLD/.local/authorizations/"
read -r -p 'Registro v3 exato (.local/authorizations/approval-<32 hex>.json): ' PREVIOUS
CHECK="$OLD/evidence/renewal-check-v4-$(date -u +%Y%m%dT%H%M%SZ).json"
if [ -e "$CHECK" ]; then echo 'PARE: evidencia ja existe.'; else
  "$PY" -B probe.py check-renewal --resume-from "$OLD" --previous-approval "$PREVIOUS" > "$CHECK"; echo "exit=$?"; cat "$CHECK"
fi
```

Resultado obrigatório:

- `renewal=eligible`, `execution_started=false` e `authorization_created=false`;
- `manifest_sha256=f5f885a3…`;
- `policy_sha256=bff24b4b…` e `members_per_mission=6`;
- `previous_policy_sha256=0532899c…` e `previous_package_manifest_sha256=f6916d72…` (ou `89ed1e3a…`, se o predecessor for o v2);
- plano e mapa corretos.

Isso é elegibilidade local, não autorização. Não houve credencial nem conexão ao Google.

**PARE AQUI.** Entregue esse JSON ao responsável e obtenha um **novo aceite explícito v4**. O aceite deve citar:

- o manifesto `f5f885a3…` e o ZIP `47b891fa…`;
- a política de seis membros, com as cinco contas listadas nominalmente e a conta de serviço;
- os dois PNGs, seus hashes e destinos acima;
- a conta humana fonte e a conta de serviço;
- os dois escopos;
- prazo curto e retenção sem exclusão;
- o predecessor escolhido.

O aceite v3 não é transferido. Uma aprovação na conversa também não executa nenhum comando.

## Somente depois do novo aceite explícito v4

Estes comandos são instruções futuras e não fazem parte desta entrega. Mantenha o terminal interativo e as variáveis `OLD`, `PY` e `PREVIOUS` acima. Substitua a referência pelo identificador real do novo aceite:

```bash
"$PY" -B probe.py renew-authorization \
  --resume-from "$OLD" \
  --previous-approval "$PREVIOUS" \
  --operator tiago@secco.example \
  --reference 'SUBSTITUIR-PELA-REFERENCIA-DO-NOVO-ACEITE-V4' \
  --minutes 30
```

Confirme digitando `AUTORIZO CLOUD SHELL 07C`. O retorno traz `authorization_file=.local/authorizations/approval-<32 hex>.json`, novo, com `execution_started=false`. Os aceites antigos não mudam. Confira arquivo, validade e dados do aceite, e copie exatamente o caminho retornado:

```bash
read -r -p 'authorization_file exato retornado pela aprovacao v4: ' APPROVAL_FILE
"$PY" -B probe.py execute --resume-from "$OLD" --approval-file "$APPROVAL_FILE" --confirm-write
```

Esse último comando obtém credenciais e pode fazer os dois uploads. Exige a aprovação v4.

| Retorno | Ação |
|---|---|
| `acl_fora_da_politica` (com `acl_mission`/`acl_resource`) | Parar. Algum membro da ACL não confere com os seis aprovados. Não adicionar nem remover membros. Nenhum ID é reservado, o journal continua íntegro e uma nova tentativa exige revisão e novo aceite (testado). |
| `permissao` | 401/403 da API. Parar sem ampliar escopos ou alterar IAM. |
| `iam_get_access_token` / `iam_api_desativada` | Mesma orientação da v3. |
| Timeout ou resultado parcial | Preservar o checkpoint e pedir revisão. Não renovar como se não houvesse atividade remota. |

A repetição para idempotência só ocorre após sucesso, dentro do prazo, com o mesmo `OLD`, `APPROVAL_FILE` e comando. Devem permanecer dois IDs e verificações completas. Não há exclusão remota autorizada.

Export seguro, sem chamadas externas:

```bash
"$PY" -B probe.py evidence --resume-from "$OLD"
```

O ZIP fica em `$OLD/exports/`. Ele exclui `.local`, as políticas com e-mails e os aceites.

## Interrupções offline

| Código | Ação |
|---|---|
| `v4_exige_resume_from` | Repetir o comando com `--resume-from "$OLD"`. Nenhum arquivo foi criado. |
| `politica_v4_nao_configurada` | Executar `configure-policy` antes. |
| `politica_v4_ja_registrada` | A política já existe. Não apagar; `check-renewal` confere o conteúdo. |
| `politica_nao_confere` | Parar, preservando os arquivos. Pode indicar e-mail incorreto ou arquivo local adulterado. |
| `vinculo_da_politica` / `manifesto_v2_nao_confere` / `vinculo_do_plano` | O diretório de origem não é o estado v2 esperado. Parar. |
| `vinculo_da_aprovacao_anterior` | Predecessor inválido. Escolher outro registro preservado válido; nunca editar o JSON. |
| `atividade_remota_possivel_revisao_obrigatoria` | Reconciliação separada é obrigatória. Não renovar. |
| `ensaio_em_uso` | Aguardar o processo conhecido. Não apagar o lock. |

## Validação local

- **Pacote v4 e suítes existentes:** 103 testes aprovados, zero falhas, dois avisos de depreciação existentes, em 366 s. São 34 testes novos da v4 e os 69 anteriores (renovação v3, pacote, POSIX, isolamento), sem alteração.
- **Comando:** `.venv/Scripts/python.exe -m pytest tests/test_drive_cloud_shell_v4.py tests/test_drive_cloud_shell_renewal.py tests/test_drive_cloud_shell_package.py tests/test_drive_cloud_shell_posix.py tests/test_database_isolation.py -q -p no:cacheprovider`.
- **Evidências:** `artifacts/stage07c/cloud-shell-v4/tests.log`, `validation.json` e `preservation-check.json`.
- **Suíte completa do projeto:** 792 testes aprovados, zero falhas, em 587 s (`full-suite.log`).

Os testes v4 cobrem:

- a cadeia v2 → falha ACL v3 → v4 no **mesmo** journal;
- nova política e novo aceite;
- recusa dos aceites v2/v3 e de registros forjados na execução;
- dois uploads simulados, com repetição sem duplicar;
- ACL com usuário estranho, grupo, `anyone` ou sem a conta de serviço: `acl_fora_da_politica` antes de qualquer reserva, com estado ainda renovável;
- 403, que permanece `permissao`;
- política errada, duplicada, com a conta de serviço digitada ou adulterada;
- regras de predecessor e journal com atividade;
- recusa sem `--resume-from`;
- determinismo e privacidade do ZIP;
- reprodutibilidade do v3.

Uma verificação de mutação confirmou que cada proteção nova faz algum teste falhar quando removida. Os testes usam SQLite temporário, PNGs sintéticos, credenciais fictícias e `MockTransport`. O gate Linux é declarativo no Windows.

Registro da implementação local, anterior à execução operacional v4 informada pelo responsável: **não houve nessa rodada:** execução no Cloud Shell ou em kernel Linux, chamada ao Google, autenticação real, upload, alteração IAM/ACL, deploy, commit ou push. `.env`, o banco operacional, as oito migrações e os ZIPs v1/v2/v3 foram conferidos e permaneceram iguais.

## Pendências e decisões

1. **Lista dos cinco sócios.** O compromisso foi derivado das cinco contas da allowlist do Workspace, que inclui a coordenação. Se algum dos seis participantes reais for outra conta, a v4 para com `acl_fora_da_politica` (falha segura) e o compromisso precisa ser refeito. O novo aceite deve listar as contas nominalmente.
2. **Aplicação.** `READERS` e `docs/integracao-google-drive.md` ainda descrevem a política antiga (2 + conta de serviço por missão). Antes de ativar a sincronização real da aplicação, alinhar a política e revisar os testes que hoje esperam a recusa de Marcos/Hugo na ACL Argentina (`test_unsafe_inherited_permissions_block_upload`).
3. A janela entre a conferência de ACL e o upload, e a necessidade de auditoria administrativa dos Drives, continuam como descritas na integração.
