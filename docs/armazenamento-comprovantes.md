# Armazenamento de comprovantes, etapa 05B

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


## Escopo e bloqueio do uso real

A persistência local está implementada exclusivamente para dados e comprovantes sintéticos. Não foi habilitada no ambiente operacional. Nenhum servidor foi iniciado, nenhum serviço externo foi configurado, a .env operacional foi preservada e a migração 006 não foi aplicada ao banco operacional.

O login Google real e as condições de operação continuam pendentes de validação. Mesmo depois de configurar login, esta versão continua exigindo declaração de conteúdo sintético e bloqueia o módulo em produção. Não há OCR, API Drive, orçamento, aprovação financeira ou mudança nos módulos de agenda e Diário.

## Configuração explícita

O padrão permanece RECEIPTS_STORAGE_BACKEND=temporary, conservando o comportamento da 05A. A existência de uma pasta ou o preenchimento de um caminho não ativa a persistência.

Para um ensaio local autorizado, é necessário configurar conjuntamente:

| Variável | Exigência |
| --- | --- |
| APP_ENV | development |
| DEV_NO_AUTH | false |
| RECEIPTS_SYNTHETIC_ENABLED | true |
| RECEIPTS_STORAGE_BACKEND | local |
| RECEIPTS_PRIVATE_DIR | Diretório privado absoluto, fora de todo o projeto e dos diretórios públicos |
| Configuração OIDC e allowlist | Completa e autorizada, conforme docs/autenticacao.md |

Nenhum desses valores foi escrito na .env operacional nesta etapa. A .env.example mantém o modo temporário e o caminho privado vazio. Não invente credenciais para ativar o aplicativo normal. Os testes usam identidades sintéticas assinadas e transporte OIDC mockado, sempre com as proteções reais de autorização ativas.

O diretório pai do volume deve existir. O serviço cria o diretório final com 0700 em POSIX, se necessário, e os objetos com 0600. Diretório relativo, raiz genérica, diretório que contenha o projeto, caminho dentro do projeto, caminho contendo o próprio banco, links simbólicos, junctions ou pontos de redirecionamento são recusados. Diretório POSIX preexistente precisa pertencer ao usuário do processo e não permitir acesso de grupo/outros.

Em testes, o volume deve ser subordinado à concessão temporária ativa do SQLite. Um caminho persistente externo à concessão falha antes da criação do volume.

## Volume e organização física

O volume é identificado por .volume.json e vinculado ao banco em receipt_storage_volumes. Um volume desconhecido, diretório não vazio sem marcador, marcador de outro banco ou volume ausente quando o banco já possui um vínculo não é adotado silenciosamente. Isso evita inicializar um volume vazio quando um disco deixou de estar montado.

.lock mantém bloqueio do sistema operacional por toda a vida do adaptador. Apenas uma instância de aplicação ou manutenção pode usar o volume. Não use múltiplos workers para o modo local desta etapa. O bloqueio é liberado ao encerrar e o volume permanece em disco. O filesystem precisa suportar hard links e bloqueios locais; NTFS e filesystems POSIX locais adequados são o alvo. Volumes de rede ou filesystems incompatíveis não são suportados e devem falhar sem confirmar armazenamento.

Organização:

- objects/{mission_id}/{expense_id}/{object_key}.bin: objetos confirmados, com chave aleatória de 256 bits independente do ID do anexo.
- .staging/{object_key}.part: escrita intermediária, nunca disponível para download.
- .journal/{object_key}.json: intenção de gravação recuperável, com IDs, formato, tamanho e checksum, sem conteúdo do comprovante.
- .quarantine/: resíduos e objetos sem referência SQLite, isolados de consultas e downloads.

Os nomes físicos não usam o nome original, processo ou nome de pessoa. O nome técnico padronizado continua nos metadados da 005 e permanece pendente enquanto faltarem identificadores, inclusive o processo FACEPE. Não foi inventado código de processo.

O tamanho máximo permanece 5 MB por arquivo, 4 anexos/12 MB por envio e 8 anexos/20 MB por despesa. O volume sintético tem quota total de 100 MB, incluindo resíduos; a quota é técnica, não controle orçamentário. A validação de extensão, MIME e conteúdo JPEG/PNG/PDF da 05A é reutilizada também na escrita do adaptador. SHA-256 e tamanho são verificados antes de confirmar e a cada leitura. As verificações de formatos continuam parciais e não substituem antivírus/CDR.

## Gravação e consistência

1. Sessão, missão, participante, CSRF, metadados e arquivo são validados.
2. A transação SQLite verifica versão e chave idempotente. Uma chave aleatória nova é alocada.
3. O journal é escrito exclusivamente e sincronizado. O conteúdo é escrito em .part com criação exclusiva, flush e fsync.
4. A publicação usa hard link no mesmo volume para criar o destino sem sobrescrever. O staging é removido e a integridade do objeto final é conferida.
5. A referência e o estado Armazenado são gravados no SQLite na transação da despesa. Depois do commit, a limpeza do journal é tentada. Falha nessa limpeza nunca apaga um objeto já confirmado.

Falha de disco não produz estado armazenado. Os metadados podem ficar salvos com Erro de armazenamento, e a interface informa a pendência. Falha de banco antes do commit tenta compensar os objetos recém-criados. Se a compensação falhar ou o processo cair, o journal e a reconciliação permitem localizar os resíduos. Nenhum arquivo parcial é apresentado como comprovante disponível.

A chave de envio continua idempotente. Mesmo conteúdo na mesma despesa reaproveita o vínculo, sem anexos duplicados. Um reenvio para recuperar anexo perdido ou excluído recebe uma chave física nova. Não há sobrescrita de objetos existentes. O fluxo usa a serialização de escrita SQLite e bloqueio do adaptador; versão antiga resulta em conflito e não apaga o arquivo atual.

## Reinício e reconciliação

No startup explicitamente configurado, o adaptador confere o volume e reconcilia antes de aceitar requisições. A referência válida vem do SQLite, nunca só do nome ou da existência de um arquivo.

- Referência confirmada com journal residual e objeto íntegro: conclui a limpeza e registra recuperação.
- Referência confirmada com staging íntegro e destino ausente: pode concluir a publicação.
- Referência confirmada com conteúdo ausente, incompleto ou checksum inválido: marca Erro e impede download.
- Arquivo sem referência ou staging de transação não confirmada: move para quarentena e registra evento.
- Exclusão anteriormente autorizada e interrompida: termina a remoção e registra conclusão.
- Metadados locais inválidos ou links inesperados: não são seguidos; exigem revisão manual.

A limpeza automática não faz busca fora do volume identificado nem apaga comprovantes válidos com base em um nome. A quarentena não é um arquivo de comprovantes disponível ao viajante. Para impedir resíduos permanentes sem mecanismo de tratamento, há manutenção explícita com histórico. Com a aplicação parada e configuração sintética autorizada, o operador local pode executar:

    .venv/Scripts/python.exe -m scripts.reconcile_receipts --apply --confirm-synthetic

Para remover a quarentena de forma intencional:

    .venv/Scripts/python.exe -m scripts.reconcile_receipts --apply --confirm-synthetic --purge-quarantine

O script não migra, não inicia servidor e não cria usuários. Não foi executado contra o ambiente operacional nesta entrega. Ele exige o banco já migrado e o volume correspondente; o bloqueio recusa manutenção concorrente com a aplicação. A autorização dessa manutenção é a do operador do sistema operacional que controla o banco e o diretório privado, com flags explícitas. A purga registra solicitação antes da remoção e conclusão depois, permitindo repetição em caso de interrupção. Não faça purga após restauração sem verificar o conjunto de backup; arquivos na quarentena podem ser necessários para diagnóstico.

## Exclusão pelo viajante

O detalhe do anexo oferece uma seção de exclusão com confirmação explícita. A operação POST exige sessão válida, participante da missão, permissão de escrita, autoria do registro, CSRF e versão atual. Outra pessoa da mesma missão não recebe acesso aos comprovantes do autor.

A intenção é gravada e confirmada no SQLite antes de remover o arquivo. Enquanto Exclusão pendente, o download já está bloqueado. A conclusão mantém o anexo como tombstone, sem apagar metadados ou histórico. O histórico guarda o solicitante e a reconciliação respeita essa intenção autorizada. Se houver falha de disco, a intenção permanece recuperável. Reinício não exige inventar um usuário para a ação automática.

A exclusão física não promete apagamento forense em SSD, snapshots ou backups. Políticas legais de retenção ainda precisam ser definidas antes do uso real.

## Interface e acesso

A captura permanece Hoje → Registrar comprovante → selecionar/fotografar → preencher → salvar. Não depende de JavaScript para navegar ou enviar. No modo local persistente, a confirmação distingue Rascunho, Armazenado localmente, Pendente de sincronização e Erro de armazenamento. O estado financeiro e o estado do arquivo são separados. Persistência não implica aprovação ou reembolso.

Não há URL pública, montagem estática ou caminho físico nas respostas HTTP. O download usa a rota existente com sessão, autorização e autoria, verifica checksum e força Content-Disposition attachment, no-store e CSP sandbox. O caminho físico é derivado apenas de IDs internos validados. Google tokens, bytes de comprovantes e caminhos privados não são adicionados a logs ou respostas.

## Migração e preparação para Drive

006_receipt_storage.sql é aditiva e cria receipt_storage_volumes, receipt_local_objects e receipt_storage_events. Não modifica 005 nem atualiza despesas existentes. A inicialização normal futura aplicará a migração pelo mecanismo versionado existente, somente quando autorizada; ela não foi aplicada ao banco operacional nesta execução.

As colunas legadas de recepção da 005 são preservadas. Para persistência, receipt_local_objects é a fonte do novo estado local e da chave física. storage_session legado recebe o ID estável do volume; a interface não confunde o antigo enum de recepção temporária com armazenamento permanente. Anexos temporários antigos não são copiados nem promovidos automaticamente. A troca de adaptador pode exigir reenvio sintético explícito.

sync_state permanece pendente e remote_reference permanece nulo por restrições SQLite. Não existe processo de sincronização ou estado remoto concluído fictício. storage_contracts.py define ReceiptStorage, StoredReceipt e um contrato SharedDriveAdapter, sem implementação ou credenciais. A futura integração precisará de confirmação real de ID/checksum remoto, idempotência, fila e tratamento de falhas antes de permitir outro estado.

## Segurança e backup para implantação futura

Nenhuma VPS foi configurada. A futura instalação deverá usar usuário de serviço dedicado, diretório fora de webroots, permissões POSIX 0700/0600 e volume local persistentemente montado. Em Windows, ACLs NTFS devem restringir o diretório ao usuário do serviço e administradores autorizados; a biblioteca padrão não audita ACLs completas. O módulo atual permanece sintético e bloqueado em produção justamente sem considerar essas condições como validadas.

Não há criptografia em repouso implementada pelo aplicativo. A implantação futura precisará avaliar criptografia de disco e backups, segurança de chaves, ACLs, retenção, espaço livre, monitoramento e testes de restauração. Nenhuma defesa do aplicativo protege contra comprometimento do usuário do sistema operacional que controla o volume e o SQLite.

Backup precisa preservar o conjunto coerente: SQLite, marcador do volume, objects, journal/staging necessários à recuperação e histórico, com manifestos/checksums. Planeje pausar gravações, exclusões e purgas, obter backup consistente via SQLite Backup API e copiar/snapshotar o volume no mesmo ponto lógico. Não copie apenas o arquivo SQLite vivo nem apenas os anexos. Use cópia cifrada, independente do disco principal, retenção definida e acesso restrito. Teste a restauração do conjunto em ambiente isolado, incluindo o vínculo volume/banco e a integridade dos arquivos, antes de apagar backups antigos.

flush/fsync, publicação exclusiva e journal suportam consistência e reinício de processo, mas não garantem recuperação contra perda física do disco, filesystem defeituoso ou corte de energia em qualquer hardware. Em POSIX, diretórios são sincronizados; a biblioteca padrão Windows não fornece a mesma confirmação de fsync de diretório. A validação desta entrega cobre reinício da aplicação e falhas simuladas, não certificação de durabilidade contra perda de energia. Persistência local não substitui backup.

Fontes técnicas: [Python os e fsync](https://docs.python.org/3/library/os.html), [SQLite Online Backup API](https://www.sqlite.org/backup.html), [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).

## Arquivos da etapa

Novos: app/core/storage_paths.py; app/db/migrations/006_receipt_storage.sql; app/services/storage_contracts.py; app/services/local_receipt_storage.py; scripts/reconcile_receipts.py; tests/test_persistent_receipts.py; este documento; docs/validacao-etapa05b.md.

Alterados: app/core/config.py; app/main.py; app/services/receipt_storage.py; app/repositories/receipts.py; app/routers/receipts.py; app/templates/receipt_form.html; receipt_detail.html; receipts.html; .env.example; README.md. Os três arquivos de testes anteriores receberam somente a expectativa de seis migrações, preservando os 361 cenários.

Não existe checkpoint Git nesta pasta. As migrações 001 a 005, o banco operacional, a .env privada e o código de agenda/Diário foram preservados. Os relatórios de testes completos ficam em artifacts/stage05b.
