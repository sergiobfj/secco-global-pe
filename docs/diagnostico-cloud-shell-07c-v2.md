# Diagnóstico do bloqueio de `prepare` — pacote 07C v2

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


> Para o erro posterior de renovação de `.local/approval.json`, consulte o [procedimento v3](renovacao-cloud-shell-07c-v3.md). Não apagar a aprovação v2 nem sobrescrever o estado para renovar.

O manifesto informado (`79fcffb7a3f9605f9aaaa426c7a5b7811aaf69a0aa5dc8228a3141bf1a96f1ed`) corresponde exatamente ao pacote v1 preservado neste projeto.

## Condição encontrada

`configuracao_ou_backup` era o código genérico do `except Exception` de `probe.main`. Ele não identifica, sozinho, uma configuração ou um backup ausente. O pacote anterior omitia o tipo e a fase do erro.

Há um defeito de portabilidade reproduzido nesse pacote: na limpeza do SQLite temporário, o `shutil.rmtree` do CPython/Linux utiliza operações relativas a descritores de diretório, como `os.unlink('probe.sqlite3', dir_fd=topfd)`. O audit hook de `app/core/test_database.py` ignorava `dir_fd`. Interpretava o nome relativo a partir do diretório do pacote, fora da concessão temporária, e lançava `UnsafeTestDatabase`. A mesma interpretação podia bloquear outras operações relativas da limpeza.

A sequência reproduzida é: criar e validar o SQLite sintético → exportar `evidence/probe-state.zip` → criar `evidence/session.json` → conferir o lock → falhar ao limpar o temporário → não gravar `evidence/offline-check.json`. O `RuntimeError` de isolamento era convertido em `configuracao_ou_backup`.

Essa condição foi reproduzida localmente com o ZIP v1 original e os eventos de auditoria POSIX. Não houve execução de kernel Linux local nesta correção. O JSON recebido não permite excluir uma segunda causa no Cloud Shell; o comando opcional abaixo permite confirmar o tipo e as funções exatas no ambiente afetado, sem expor mensagens arbitrárias ou caminhos completos.

```bash
cd "$HOME/secco-drive-07c"
.venv/bin/python -B - <<'DIAGNOSTICAR_LOCAL'
import json, socket, subprocess
from pathlib import Path
def forbidden(*args, **kwargs):
    raise RuntimeError('chamada_externa_bloqueada')
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
subprocess.run = forbidden
import probe
try:
    probe.verify()
    result = probe.initialize()
except Exception as error:
    frames = []
    tb = error.__traceback__
    while tb is not None:
        frames.append({'file': Path(tb.tb_frame.f_code.co_filename).name,
                       'function': tb.tb_frame.f_code.co_name, 'line': tb.tb_lineno})
        tb = tb.tb_next
    result = {'result': 'stopped', 'error_type': type(error).__name__, 'frames': frames}
print(json.dumps(result))
DIAGNOSTICAR_LOCAL
```

O resultado esperado para este defeito contém `UnsafeTestDatabase`, funções de `shutil` como `_rmtree_safe_fd`/`_rmtree_safe_fd_step` e `_audit`/`_protect_filesystem`/`assert_temporary_database`. Se o resultado apontar outra causa, preserve o JSON e pare para análise. Esse diagnóstico repete apenas a preparação local; não pede credencial nem consulta o Google. Pode deixar outro temporário sintético porque a limpeza v1 está defeituosa; não apagar diretórios de `/tmp` por busca genérica.

## Arquivos e ordem dos comandos

Não é necessário fornecer um backup operacional, token, política de membros ou aprovação para `prepare`. No primeiro uso, ele mesmo cria o checkpoint sintético. Em retomadas, o checkpoint existente precisa ser íntegro. O par ZIP/`session.json` provavelmente já existe no caso reproduzido; deve ser conferido, nunca presumido ou apagado.

A ordem anterior — verificar ZIP/manifesto → preparar dependências na venv → `prepare` → política local → nova aprovação → execução — estava correta. A falha não decorre de executar `prepare` antes de `configure-policy`. Nesta entrega, parar após `prepare`: não configurar autorização nem executar o ensaio.

## Correção e pacote novo

A v2 resolve caminhos relativos usando a identidade do descritor (`fstat` e `/proc/self/fd` no Linux). Se não puder comprovar que o descritor é de um diretório válido, recusa a operação. As verificações de concessão temporária, propriedade do diretório, banco operacional, links e isolamento SQLite continuam ativas. Não foi desabilitado o audit hook.

Além disso, o executor passa a informar fase, tipo e código controlados, com `errno` quando aplicável, sem imprimir texto arbitrário de exceções. O comando novo `inspect-backup` restaura uma cópia em temporário e informa IDs/tentativas sem modificar o ZIP de origem. Ele não autentica nem acessa a rede.

- ZIP: `artifacts/stage07c/cloud-shell-v2/secco-drive-07c-cloud-shell-v2.zip`.
- SHA-256: `a6053701405357d914917d7d20efb0ee099f4f8bf47f37c0135913febab24f53`.
- Manifesto SHA-256: `89ed1e3a19a658468cd74f9562baa0f4dd73be96a5a973a73d389118b89e62de`.
- 30.901 bytes; 25 entradas; dois PNGs de 69 bytes. Nenhum banco, `.env`, credencial, token ou e-mail pessoal incluído.
- Plano, hashes dos PNGs, mapa dos 14 destinos, escopos e retenção continuam iguais. A v1 permanece preservada.

**A aprovação anterior não vale para o novo manifesto. Não copiar `.local/approval.json`, não executar `authorize` ou `execute`.** Uma futura execução depende de nova aprovação explícita vinculada à v2, aos hashes/destinos e à validade. Esta correção não autoriza uploads.

## Continuação segura no Cloud Shell

Os comandos abaixo pressupõem o diretório v1 `$HOME/secco-drive-07c` criado pelo procedimento original. Se foi usado outro diretório, pare e confirme o caminho antes de adaptar. Certifique-se de que nenhum executor antigo esteja rodando. Envie apenas o ZIP v2 para `$HOME`, mantendo a v1 e suas evidências intactas.

Primeiro, verifique e extraia em diretório novo. Reutilize a venv já instalada; as dependências são idênticas, portanto não há instalação nem chamada de rede necessária:

```bash
bash <<'EXTRAIR_V2'
set -euo pipefail
umask 077
cd "$HOME"
printf '%s  %s\n' 'a6053701405357d914917d7d20efb0ee099f4f8bf47f37c0135913febab24f53' 'secco-drive-07c-cloud-shell-v2.zip' | sha256sum -c -
test -x "$HOME/secco-drive-07c/.venv/bin/python"
if [ -e "$HOME/secco-drive-07c-v2" ]; then
  echo 'PARE: diretorio v2 ja existe. Preservar e revisar; nao sobrescrever.'
  exit 1
fi
mkdir -m 700 "$HOME/secco-drive-07c-v2"
python3 -m zipfile -e secco-drive-07c-cloud-shell-v2.zip secco-drive-07c-v2
cd "$HOME/secco-drive-07c-v2"
python3 -I -S -B verify_package.py
EXTRAIR_V2
```

O manifesto deve retornar `89ed1e3a19a658468cd74f9562baa0f4dd73be96a5a973a73d389118b89e62de`. Em seguida, inspecione o estado v1 e transfira somente uma cópia do checkpoint/marker se não houve reserva de IDs ou tentativa remota. O código abaixo para se qualquer arquivo estiver ausente, corrompido, divergente ou indicar atividade remota:

```bash
bash <<'RECUPERAR_E_PREPARAR_OFFLINE'
set -euo pipefail
umask 077
OLD="$HOME/secco-drive-07c"
PY="$OLD/.venv/bin/python"
cd "$HOME/secco-drive-07c-v2"
test -f "$OLD/evidence/probe-state.zip"
test -f "$OLD/evidence/session.json"
mkdir -m 700 evidence
"$PY" -B probe.py inspect-backup --archive "$OLD/evidence/probe-state.zip" > evidence/previous-state-check.json
cat evidence/previous-state-check.json
"$PY" -B - <<'COPIAR_ESTADO_VALIDADO'
import json
from pathlib import Path
old = Path.home() / 'secco-drive-07c' / 'evidence'
out = Path('evidence')
report = json.loads((out / 'previous-state-check.json').read_text())
plan = json.loads(Path('plan.json').read_text())
if report.get('safe_to_prepare_fresh_copy') is not True:
    raise SystemExit('PARE: existem IDs/tentativas/estado remoto; revisao necessaria.')
expected = {'plan_sha256': plan['plan_sha256'], 'archive': 'probe-state.zip'}
sources = [old / name for name in ('probe-state.zip', 'session.json')]
if any(p.is_symlink() or not p.is_file() for p in sources):
    raise SystemExit('PARE: origem ausente ou link nao permitido.')
if json.loads((old / 'session.json').read_text()) != expected:
    raise SystemExit('PARE: marcador de sessao divergente.')
for source in sources:
    with (out / source.name).open('xb') as target:
        target.write(source.read_bytes())
print('Checkpoint e marcador copiados; origem preservada; aprovacao nao copiada.')
COPIAR_ESTADO_VALIDADO
"$PY" -B probe.py prepare
RECUPERAR_E_PREPARAR_OFFLINE
```

Se o checkpoint ou o marcador v1 estiver ausente, não fabricar os arquivos nem iniciar outro estado: informe qual faltou. Isso exige revisar em que ponto a primeira preparação parou. Se a inspeção indicar IDs ou tentativas, não prosseguir automaticamente, mesmo que a falha inicial parecesse apenas local. Os comandos não apagam nem sobrescrevem o estado anterior; uma falha parcial deve ser revisada antes de repetir o bloco.

Resultado esperado: `mode=offline`, `platform=linux`, `files=2`, `bytes_each=69`, duas missões com `remote_id=null`, `state=aguardando`, `attempts=0`. O arquivo `evidence/offline-check.json` deve existir. Preserve esse arquivo, `evidence/previous-state-check.json`, checkpoint, marcador e ZIPs v1/v2. Em erro, envie somente o JSON controlado (`code`, `phase`, `error_type`, `errno`); não envie tokens, `.local` ou diretório do SDK.

**PARE após a preparação offline. Não executar comandos de autorização ou upload.** Nenhuma mudança de IAM, escopo, `.env`, banco operacional, migração, aplicação ou implantação faz parte da solução.

## Validação local

**52 testes aprovados, zero falhas, dois avisos de depreciação existentes; 21,00 segundos.** Comando: `.venv/Scripts/python.exe -m pytest tests/test_drive_cloud_shell_posix.py tests/test_drive_cloud_shell_package.py tests/test_database_isolation.py -q -p no:cacheprovider`. Resultados em `artifacts/stage07c/cloud-shell-v2/tests.log` e `validation.json`. Os hashes do `.env`, banco operacional, oito migrações e ZIP v1 foram conferidos e permaneceram iguais aos anteriores.

Os testes do pacote exercitam v1/v2 com os mesmos eventos relativos POSIX, sucesso da correção, verificação do manifesto, dependências ausentes, corrupção de checkpoint e recusa de reinicialização segura quando existem IDs/tentativas. Os testes de isolamento continuam verificando a recusa de bancos persistentes/operacionais, `ATTACH`, links e alterações fora da concessão. Todas as operações SQLite efetivas usaram temporários sintéticos. A validação real da limpeza no kernel Linux continua sendo o `prepare` acima; nenhuma chamada ao Google foi feita nesta correção.

Arquivos de código alterados: `app/core/test_database.py`, `scripts/build_drive_cloud_shell_package.py`, `tools/drive_cloud_shell/probe.py`, `tools/drive_cloud_shell/verify_package.py` e `tools/drive_cloud_shell/README.txt`. Criado `tests/test_drive_cloud_shell_posix.py`. Documentação: este diagnóstico e o aviso de substituição em `docs/pacote-cloud-shell-07c.md`. Artefatos novos ficam exclusivamente em `artifacts/stage07c/cloud-shell-v2/`.
