SECCO 07C - pacote portatil v4. Upload NAO autorizado por este pacote.

Versao 4: corrige somente a politica de ACL. O ensaio v3 parou na validacao de
permissoes da raiz do Drive Argentina, antes de reservar IDs ou enviar arquivos:
o executor aceitava 3 membros por missao, mas os Drives tem 6 participantes
autorizados (cinco socios + conta de servico). O responsavel confirmou que os
cinco socios podem acessar os dois Drives. A v4 exige exatamente esses seis
membros, iguais nas duas missoes, e continua recusando qualquer outro usuario,
grupo, dominio, link publico ou ACL sem a conta de servico.

Nao executar novamente o pacote v3. Nao reutilizar aceites v2/v3: eles servem
somente como predecessores historicos; execute aceita apenas registro v4.

Python 3.11+ / Linux / Google Cloud Shell. Runtime externo: HTTPX, com dependencias
transitivas fixadas no requirements.txt. Nao iniciar FastAPI. Nao copiar .env,
banco operacional, tokens, chaves ou credenciais para este diretorio.

1. Conferir SHA-256 do ZIP recebido com o valor entregue fora do pacote.
2. Extrair em diretorio novo. Rodar: python3 -I -S -B verify_package.py
3. Reutilizar o interpretador da venv ja instalada. Nao reinstalar dependencias.
4. TODA acao de estado exige --resume-from DIRETORIO-V2 (sem ele: v4_exige_resume_from).
   A v4 nunca cria journal proprio. Usa o MESMO checkpoint/marcador/lock da v2.
5. configure-policy --resume-from DIRETORIO-V2: digitar os cinco e-mails dos socios
   (valem para as duas missoes). A conta de servico e acrescentada pelo programa.
   Grava somente .local/access-policy-v4.json (criacao exclusiva). A politica antiga
   .local/access-policy.json permanece intacta e nao e usada.
6. check-renewal --resume-from DIRETORIO-V2 --previous-approval CAMINHO-EXATO.
   Offline: exige checkpoint/marcador, politica v4 e journal sem ID, tentativa, erro,
   verificacao ou evento. Nao cria aprovacao e nao obtem token.
7. PARAR. Solicitar novo aceite explicito para este manifesto v4, politica de seis
   membros, dois PNGs/hashes/destinos, conta fonte, dois escopos, prazo e retencao.
8. Somente depois do novo aceite: renew-authorization com --resume-from,
   --previous-approval, --operator, --reference e --minutes (maximo 60).
   Retorna authorization_file novo. Nao modifica aprovacoes antigas.
9. Somente com novo aceite: execute --confirm-write --resume-from DIRETORIO-V2
   --approval-file CAMINHO-EXATO-RETORNADO. Nao ha selecao automatica.
10. evidence --resume-from DIRETORIO-V2 gera export sem .local, politica ou aceites.

Codigos: acl_fora_da_politica (com acl_mission e acl_resource) = algum membro da ACL
nao confere com a politica v4; PARAR, sem alterar membros. permissao = 401/403 da API;
PARAR, sem ampliar escopos. Nenhum codigo imprime e-mails ou mensagens externas.

Limites: dois PNGs de 69 bytes, um por missao, nomes e destinos fixados pelo plano;
somente drive.file e drive.metadata.readonly. Sem drives.get, lista ampla, download,
PATCH, DELETE, criacao de pastas ou alteracao de permissoes. Nenhuma limpeza remota.
Integridade remota: GET posterior com sha256Checksum do Google, Folder ID, Drive ID,
nome, tamanho e MIME. Hash ausente/divergente = parar, sem sucesso ficticio.

Em timeout/falha: manter checkpoint, IDs e registros. Nao reinicializar, nao gerar
outro plano, nao apagar arquivos. Registros parciais nunca sao selecionados.
O manifesto detecta alteracao/corrupcao; nao e assinatura digital nem sandbox.
Este pacote e preparo/teste sintetico, nao declaracao de prontidao para producao.
