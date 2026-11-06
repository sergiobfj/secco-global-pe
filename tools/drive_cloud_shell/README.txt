SECCO 07C - pacote portatil de preparacao. Upload NAO autorizado por este pacote.

Versao 3: renovacao sem sobrescrever a aprovacao existente. A falha v2 era
os.open(.local/approval.json, O_WRONLY|O_CREAT|O_EXCL), com fase desatualizada.
O registro antigo permanece intacto; renew-authorization cria um nome exclusivo
em .local/authorizations/. execute exige --approval-file selecionado explicitamente.
Nao reutilizar o aceite v2: esta versao tem outro manifesto e requer novo aceite.

Python 3.11+ / Linux / Google Cloud Shell. O runtime externo necessario e HTTPX,
com dependencias transitivas fixadas no requirements.txt. Nao iniciar FastAPI.
Nao copiar .env, banco operacional, tokens, chaves ou credenciais para este diretorio.

1. Conferir SHA-256 do ZIP recebido com o valor entregue fora do pacote.
2. Extrair em diretorio novo. Rodar: python3 -I -S -B verify_package.py
3. Reutilizar o interpretador da venv v2. Nao reinstalar dependencias iguais.
4. Em TODOS os comandos da recuperacao usar --resume-from DIRETORIO-V2.
   O manifesto v2 conhecido, plano, PNGs, mapa e contrato da politica sao conferidos.
   O mesmo checkpoint/lock e a politica permanecem na v2; nao copiar nem bifurcar estado.
5. Rodar check-renewal --resume-from DIRETORIO-V2 --previous-approval .local/approval.json.
   E offline: restaura em temporario, exige checkpoint/marcador existentes, valida
   politica e recusa qualquer ID, tentativa, erro, verificacao ou evento no journal.
   Nao cria aprovacao e nao obtem token. Qualquer pendencia = parar, sem apagar arquivos.
6. PARAR. Solicitar nova aprovacao explicita para este manifesto/plano, arquivos,
   hashes/destinos, conta fonte, dois escopos, validade e retencao sem exclusao.
7. Somente depois do novo aceite, usar renew-authorization, com --resume-from,
   --previous-approval, --operator, --reference e --minutes (maximo 60).
   Exige Linux e nova confirmacao digitada. Retorna authorization_file novo,
   relativo ao diretorio v2. Nao modifica aprovacao antiga, checkpoint ou journal.
8. Somente com novo aceite executar execute --confirm-write --resume-from DIRETORIO-V2
   --approval-file CAMINHO-EXATO-RETORNADO. Nao ha selecao automatica da aprovacao.
9. Repeticao idempotente usa o MESMO estado/lock/aprovacao e os mesmos IDs.
   Nao reinicializar, importar backup anterior, criar estado novo ou apagar arquivos.
10. evidence --resume-from DIRETORIO-V2 gera export em DIRETORIO-V2/exports/,
    excluindo .local, politica com emails e aprovacoes historicas.

Comandos completos e campos de aprovacao estao no guia entregue fora deste ZIP.

Limites: dois PNGs de 69 bytes, um por missao, nomes e destinos fixados pelo plano;
somente drive.file e drive.metadata.readonly. Sem drives.get, lista ampla, download,
PATCH, DELETE, criacao de pastas ou alteracao de permissoes. Nenhuma limpeza remota.

Integridade remota: GET posterior deve retornar sha256Checksum calculado pelo Google,
e conferir Folder ID/Drive ID, nome, tamanho e MIME. Tags da aplicacao e ACK do upload
nao substituem essa verificacao. Hash ausente/divergente = parar, sem sucesso ficticio.

drive.file sob pastas existentes ainda depende de validacao real. Em erro de IAM,
permissao, ACL ou capacidade, PARAR; nao ampliar escopos nem alterar permissoes.
iam_get_access_token: pedir ao administrador verificar iam.serviceAccounts.getAccessToken
(normalmente Service Account Token Creator) na conta alvo. iam_api_desativada: pedir
verificacao manual da IAM Credentials API, sem ativa-la automaticamente.

Em timeout/falha: manter o ultimo ZIP e IDs. Em arquivo de recuperacao perdido,
corrompido ou anterior ao estado remoto, parar para revisao manual. Nao gerar outro plano.
Registros de aprovacao incompletos sao mantidos e nunca selecionados automaticamente.
Uma renovacao nova exige selecionar um predecessor valido e novo aceite; um registro
parcial invalido nao pode ser predecessor. Os erros indicam fase/tipo/errno controlados.
O manifesto detecta alteracao/corrupcao; nao e assinatura digital nem sandbox contra
operador/codigo malicioso. SDK/ambiente e politicas locais precisam ser confiaveis.

Este pacote e preparo/teste sintetico, nao declaracao de prontidao para producao.
