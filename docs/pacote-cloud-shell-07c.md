# Pacote portátil 07C para Google Cloud Shell

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


> **Distribuição pública:** nomes, e-mails, domínio Google Workspace, IDs de Drive/pastas e identificadores Google Cloud deste documento são fictícios. Resultados e decisões descritos referem-se ao projeto operacional.


> Procedimento v1 preservado para histórico. Para corrigir o bloqueio de `prepare` no Linux, usar o [diagnóstico e recuperação v2](diagnostico-cloud-shell-07c-v2.md). Não repetir os comandos v1 nem reaproveitar sua aprovação para a v2.

## Entrega e limites

ZIP preparado: `artifacts/stage07c/cloud-shell/secco-drive-07c-cloud-shell.zip` (29.776 bytes, 25 entradas).

SHA-256 do ZIP: `5e47acd368ee7c29262d5ea2048466c16616bc40ecffd10d6f10ba200b45ae04`.

O pacote contém apenas executor, módulos necessários ao ensaio, dois PNGs, plano/mapa, modelo de aprovação pendente, compromisso de integridade da política, manifesto, requisitos e instruções. Não contém `.env`, SQLite operacional ou sintético, migrações, tokens, chaves, credenciais, e-mails pessoais, caminhos do Windows ou interface/FastAPI. A única identidade Google embutida é a conta de serviço, sem material de autenticação.

O estado SQLite sintético será criado em temporário no Cloud Shell e exportado em `evidence/probe-state.zip`. O bootstrap reaproveita exatamente o run_id, itens, nomes, hashes e destinos originais; não reserva IDs remotos nem envia arquivos. O UUID do volume temporário é local ao novo ambiente, sem alterar o hash do plano. O manifesto do pacote e a declaração `google-cloud-shell` passam a integrar a nova aprovação.

A política restritiva continua a mesma. Para não incluir dados pessoais no ZIP, os quatro e-mails de membros são fornecidos pelo responsável somente no Cloud Shell e conferidos contra um único compromisso agregado SHA-256 da política anterior. Esse compromisso não contém os endereços em texto. A política local não pode adicionar Marcos/outro membro nem trocar operadores de missão para fazer o ensaio passar. Seu arquivo fica em `.local/`, com acesso local restrito, e não é incluído nas evidências exportadas.

**Esta entrega é apenas preparação. A aprovação anterior não é ativada nem transferida automaticamente. É necessário novo aceite explícito para o pacote/ambiente Cloud Shell e uma janela curta antes da execução real.** O modelo permanece `approved=false`; o comando de autorização exige confirmação digitada pelo responsável, conta humana e referência do novo aceite. Não rodar esse comando antes de obter o novo aceite.

## Verificação e instalação mínima — pode executar sem autorização de escrita

Envie **somente o ZIP** para o diretório pessoal do Cloud Shell pelo recurso de upload do navegador. Não envie `.env`, banco, credenciais ou arquivos operacionais. Preserve o nome `secco-drive-07c-cloud-shell.zip` e confira o hash abaixo, recebido por este canal independente do arquivo.

Execute no terminal do Cloud Shell:

```bash
bash <<'PREPARAR_07C'
set -euo pipefail
umask 077
cd "$HOME"
printf '%s  %s\n' '5e47acd368ee7c29262d5ea2048466c16616bc40ecffd10d6f10ba200b45ae04' 'secco-drive-07c-cloud-shell.zip' | sha256sum -c -
python3 -c 'import sys; assert sys.version_info >= (3,11), "Exige Python 3.11+"'
command -v gcloud >/dev/null
if [ -e secco-drive-07c ]; then
  echo 'Diretorio ja existe: parar e conferir o ensaio anterior; nao recriar estado.'
  exit 1
fi
mkdir -m 700 secco-drive-07c
python3 -m zipfile -e secco-drive-07c-cloud-shell.zip secco-drive-07c
cd secco-drive-07c
python3 -I -S -B verify_package.py
python3 -m venv .venv
.venv/bin/python -m pip --isolated install --index-url https://pypi.org/simple --disable-pip-version-check --no-input --no-cache-dir -r requirements.txt
.venv/bin/python -B probe.py prepare
PREPARAR_07C
```

O verificador funciona antes da instalação e usa apenas a biblioteca padrão. A dependência direta é `httpx==0.28.1`; os seis pacotes transitivos necessários também estão fixados: httpcore, anyio, certifi, idna, h11 e typing_extensions. Não há FastAPI, dotenv, JWT, SDK Google Python, compilador ou ferramenta adicional a instalar. Não ativar a venv no shell: usar seu interpretador explicitamente mantém o SDK `gcloud` no ambiente original do Cloud Shell.

`prepare` não pede token, não consulta Google nem executa migração. Confere os dois PNGs, os hashes, o plano e os destinos, testa o lock do sistema e restaura o ZIP apenas em diretório temporário. O JSON deve mostrar `mode=offline`, `files=2`, `bytes_each=69`, dois `remote_id=null` e zero tentativas. Guardar `evidence/offline-check.json` e o ZIP. No Cloud Shell a saída deve indicar plataforma `linux`. Qualquer falha nessa etapa exige parar antes da autorização.

Se Python/venv, SDK, acesso a PyPI ou uma versão fixada estiverem indisponíveis, parar e informar a falha. Não usar `sudo`, instalar SDK automaticamente, desativar TLS/proxy ou buscar credencial alternativa. O ensaio não foi validado contra o Google nesta preparação.

### Política local de acesso

Ainda sem qualquer escrita remota:

```bash
cd "$HOME/secco-drive-07c"
.venv/bin/python -B probe.py configure-policy
```

Forneça os dois e-mails pessoais **já aprovados** de Argentina e depois os dois de Portugal, conforme a política do projeto. A conta de serviço é acrescentada pelo programa. A ordem dos dois membros dentro da missão é indiferente. A política precisa coincidir exatamente com o compromisso original; caso contrário, a operação é recusada. Não passar e-mails ou tokens como variáveis de ambiente para contornar a validação. O programa não pede tokens ou senhas.

O arquivo `.local/access-policy.json` contém os e-mails informados e deve permanecer local, fora do ZIP original e das evidências. A existência desse arquivo não concede permissões no Google. Não copiar a política/credenciais do SDK para outra sessão ou compactar todo o diretório para compartilhar.

**PARE AQUI e solicite nova autorização explícita.** Confira com o responsável: hash do pacote, plano, destinos, conta humana fonte, scopes, validade e retenção. A mudança de ambiente exige esse novo vínculo, ainda que o conteúdo dos PNGs não tenha mudado.

## Autorização e execução — somente após novo aceite explícito

Após a aprovação nova, confirme visualmente que a conta humana já autenticada é a indicada pelo responsável. O script fonte usa a conta explicitamente e não fará login. Para este ambiente a conta informada foi `tiago@secco.example`; esse endereço **não está dentro do ZIP**. Se o SDK não possuir a conta, parar.

Registre a referência real do novo aceite, substituindo o texto abaixo; não usar a aprovação antiga nem o texto de exemplo como prova de aceite:

```bash
cd "$HOME/secco-drive-07c"
.venv/bin/python -B probe.py authorize --operator tiago@secco.example --reference 'SUBSTITUIR-PELA-REFERENCIA-DO-NOVO-ACEITE' --minutes 30
```

Esse comando só funciona em Linux, verifica/restaura novamente o plano e exige digitar `AUTORIZO CLOUD SHELL 07C`. Não solicita token nem faz chamada ao Google. Salva `.local/approval.json` com manifesto do pacote, ambiente, hash da política, plano/mapa, scopes e validade UTC. O arquivo contém a conta humana local e não será exportado com as evidências. O limite é 60 minutos; 30 minutos é a proposta deste procedimento.

Scopes únicos: `https://www.googleapis.com/auth/drive.file` e `https://www.googleapis.com/auth/drive.metadata.readonly`. Token alvo: conta de serviço `global-pe-drive@exemplo-global-pe.iam.gserviceaccount.com`, até 900 segundos, somente em memória. Não há JSON de chave, uso de token do login da aplicação ou fallback para escopo mais amplo.

**Somente após esse novo aceite**, execute:

```bash
bash <<'EXECUTAR_07C_AUTORIZADO'
set -euo pipefail
umask 077
cd "$HOME/secco-drive-07c"
.venv/bin/python -B probe.py execute --confirm-write | tee evidence/console-first-run.json
EXECUTAR_07C_AUTORIZADO
```

O processo valida aprovação/política antes de obter credencial. IAM Credentials emite token curto após captura do token fonte pelo processo, sem impressão/gravação. Preflight confere os 14 Folder IDs por `files.get` e as ACLs/capacidades. Um ID por missão é persistido e exportado no ZIP **antes** do POST. Envia no máximo um PNG por missão. GET posterior verifica ID, Folder ID, Drive ID, nome, MIME, tamanho, `sha256Checksum` e ACL. O hash remoto é o campo retornado pelo Google, não uma tag do aplicativo ou ACK de criação.

| Missão | Nome sintético | Pasta / Folder ID | Tamanho |
|---|---|---|---|
| Argentina | `secco-ensaio-77d0936125e58eb2-argentina.png` | Deslocamento / `1EXEMPLO_AR_deslocamentos_0000000` | 69 bytes |
| Portugal | `secco-ensaio-77d0936125e58eb2-portugal.png` | Deslocamentos / `1EXEMPLO_PT_deslocamentos_0000000` | 69 bytes |

Argentina SHA-256: `a6b72a19d0e58175a61556e67b622df98f65b6787f8238d3558760048e94ca58`.

Portugal SHA-256: `3459ce0d41c9e499a998178ac583e4c8523e46bc4632646b3a898400a369e8b5`.

Hash do plano preservado: `33ea1b63f3fcefa26837d30c0118a3d3d8f2c0e6ffbd4ab4bbda54dd7af4f012`.

Hash do mapa preservado: `ed3b2b8b7567a85e13725b044ea0144caaeb9fb7fd4b23b0156983a6f3006066`.

Se `result=verified`, `verified_count=2`, `known_remote_file_count=2` e `remote_count_complete=true`, confira os dois IDs e `remote_checks`. Esse contador refere-se somente aos dois itens do ensaio, não a todo o Drive. Um ID reservado isoladamente não comprova criação; `reserved_ids_count` é separado. Em resultado parcial/erro, a contagem remota é incompleta e não se deve declarar que inexistem arquivos remotos sem confirmação.

### Repetição idempotente

Somente após sucesso da primeira execução, dentro da mesma aprovação e sem alterar o diretório/ZIP:

```bash
bash <<'REPETIR_07C_AUTORIZADO'
set -euo pipefail
cd "$HOME/secco-drive-07c"
.venv/bin/python -B probe.py execute --confirm-write | tee evidence/console-idempotency.json
REPETIR_07C_AUTORIZADO
```

Devem permanecer os mesmos dois IDs, cada item verificado e nenhuma criação adicional. Não recriar o pacote/estado nem usar outra pasta para repetir. O executor preserva o ZIP e se recusa a reinicializar se o estado sumir depois do marcador de inicialização. Se o ZIP/journal for perdido, estiver corrompido ou for anterior ao estado remoto, parar para revisão administrativa; não gerar novos IDs por tentativa.

### Falhas e ações manuais

| Código / situação | Ação obrigatória |
|---|---|
| `credenciais_fonte` | Parar. Conferir SDK e conta humana já autenticada. Não enviar token pela conversa nem automatizar login. |
| `iam_get_access_token` | Parar. Pedir ao administrador verificar `iam.serviceAccounts.getAccessToken`, normalmente por Service Account Token Creator na conta alvo. Qualquer concessão exige ação manual autorizada fora do executor. |
| `iam_api_desativada` | Parar. Pedir verificação manual da IAM Credentials API; o programa não a ativa. |
| 401/403, ACL ou `canAddChildren` | Parar sem avançar. Rever a pendência com o responsável, sem ampliar scopes ou alterar IAM/ACL automaticamente. |
| `drive.file` incompatível com pai existente | Compatibilidade ainda pendente de validação real. Parar; não trocar pai nem usar `drive`/`drive.readonly`. |
| Timeout / 429 / 5xx | Conservar o ZIP e as evidências. Não há retry automático. A retomada autorizada usa o mesmo diretório/IDs, após revisão do responsável. |
| Hash remoto ausente/divergente | Não há sucesso. Conservar estado e parar, mesmo que tamanho/tags coincidam. |
| Backup / lock / manifesto / validade | Parar antes de escrever. Não desabilitar a proteção nem apagar lock de processo vivo. |

Em falha antes de completar os dois itens, **não execute o bloco de repetição automaticamente**. Conserve o resultado e informe o código. `set -o pipefail` preserva a falha mesmo com `tee`. Nenhum comando do pacote concede papéis, ativa APIs, altera ACLs, exclui arquivos ou cria pastas no Drive.

## Evidências e retenção

Depois de sucesso ou falha, exporte apenas o conjunto seguro:

```bash
cd "$HOME/secco-drive-07c"
.venv/bin/python -B probe.py evidence
ls -l exports/
```

O comando imprime `exports/evidence-<UTC>.zip`. Baixe **esse arquivo** pelo recurso Download do Cloud Shell e preserve também o ZIP original e seu checksum. O export contém plano/mapa/manifesto, resultado offline, último checkpoint e JSONs controlados com IDs, campos remotos e hashes. Exclui `.local`, aprovação com conta humana, lista pessoal de membros, SDK, venv, tokens e credenciais. Não compactar `$HOME`, o diretório do SDK ou o diretório inteiro do pacote.

Os PNGs devem permanecer nos Drives. Não há limpeza remota; exclusão futura exige autorização separada. O ambiente operacional continua sem alterações: nenhum `.env`, SQLite, migração, aplicação ou deploy é necessário ao ensaio.

## Testes e compatibilidade

Foram aprovados **19 testes locais**, zero falhas, com dois avisos de depreciação já existentes no ambiente de testes do projeto. Cobrem build determinístico, lista exata de arquivos, ausência de identificadores pessoais/chaves/bancos, verificador sem site-packages, import mínimo, PNGs/plano/restore, rejeição de alterações, política vinculada, nova aprovação, validade/ambiente/pacote/scopes, execução com dois uploads simulados, repetição sem duplicação e export sem dados pessoais.

O pacote usa Python 3.11+, biblioteca padrão portátil, paths relativos e implementações de lock para POSIX/Windows. O ZIP tem nomes POSIX e metadados Unix. Não há paths do Windows no conteúdo. Não foi possível executar um kernel Linux local: WSL retornou indisponibilidade de registro; não houve instalação/contorno. Os testes não falsificam uma execução Linux real: os casos que alteram `sys.platform` só exercitam o gate declarativo com rede/SDK mockados. Por isso a etapa `prepare` executa o teste real de lock/SQLite/restore no Cloud Shell e deve passar antes de qualquer nova autorização.

Não houve instalação local, chamada real às APIs Google, autenticação ou upload nesta preparação. Evidências locais: `artifacts/stage07c/cloud-shell/tests.log`, `package-inventory.json` e `validation.json`.

## Checklist curto

- [ ] Hash externo do ZIP confere; manifesto íntegro; Python 3.11+/SDK disponíveis.
- [ ] Instalação isolada concluída; `prepare` passou no Linux e os dois PNGs/hashes/destinos coincidem.
- [ ] Política pessoal local confere com os membros previamente aprovados; nenhuma credencial foi copiada.
- [ ] Novo aceite explícito Cloud Shell, conta fonte, manifesto/plano, scopes, prazo e retenção registrado antes de `authorize`/`execute`.
- [ ] Após o ensaio autorizado: dois IDs e hashes remotos verificados, repetição preservou IDs, evidências baixadas, nenhum arquivo excluído.
