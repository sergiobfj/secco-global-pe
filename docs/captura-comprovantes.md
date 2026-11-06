# Etapa 05A: captura rápida sintética

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


> **Distribuição pública:** nomes, e-mails, domínio Google Workspace, IDs de Drive/pastas e identificadores Google Cloud deste documento são fictícios. Resultados e decisões descritos referem-se ao projeto operacional.


## Escopo e ativação

Esta entrega é um protótipo local para arquivos e metadados exclusivamente sintéticos. Não autoriza despesas reais. Não há Google Drive, OCR, orçamento, remanejamento, cálculo de reembolso ou relatório final financeiro.

RECEIPTS_SYNTHETIC_ENABLED=false é o padrão. Para experimentar em desenvolvimento, configure intencionalmente RECEIPTS_SYNTHETIC_ENABLED=true, APP_ENV=development e DEV_NO_AUTH=false. É necessária uma sessão OIDC autorizada; o modo local sem login não contorna essa exigência. O login Google real continua pendente da configuração autorizada da etapa 4. Os testes usam identidades assinadas sintéticas, sem contas externas.

Não alteramos a .env privada, não iniciamos servidores e não aplicamos a migração ao banco operacional nesta rodada. A próxima inicialização autorizada da versão nova aplicará a migração 005 automaticamente, pelo mecanismo existente, sem apagar o banco. Faça o backup operacional habitual antes dessa inicialização. Não apague ou edite migrações anteriores.

O diretório não possui repositório ou checkpoint Git. Nenhum commit foi criado.

## Abrir, registrar, conferir

1. Na visão Hoje, toque em Registrar comprovante. O link funciona sem JavaScript.
2. Fotografe pelo seletor nativo, quando suportado, ou selecione JPEG, PNG ou PDF. Um novo arquivo no mesmo seletor substitui a seleção anterior. Os dois seletores podem complementar o envio.
3. Confira a missão e o participante da sessão, revise data e moeda sugeridas, escolha tipo, valor, rubrica e descrição. A data sugerida usa o fuso da missão, mas não representa automaticamente a data efetiva da despesa.
4. Salve como rascunho para completar depois ou escolha preparar para revisão. Aguarde a confirmação do servidor.

O participante é vinculado à identidade autenticada e não pode ser trocado por um ID enviado no formulário. Registros em nome de outra pessoa não fazem parte desta etapa. Trocar missão leva à navegação existente e exige nova conferência antes de iniciar outro registro. Permissão explícita de edição não transforma o usuário em participante ou beneficiário da outra missão.

Os anexos são privados por autor e missão. Outro viajante da mesma missão não pode consultar, alterar ou baixar esses comprovantes. Isso é mais restrito que os módulos de agenda e Diário, que continuam com suas permissões originais.

A moeda pode ser corrigida para EUR, ARS, BRL ou USD; não há conversão cambial. Valores são armazenados como centavos inteiros, aceitando vírgula ou ponto decimal, até duas casas e sem separador de milhar. O financiamento é consultado em mission_participants, nunca editado pelo formulário. Hugo e Bruno continuam custeados, Tiago e Alan continuam fora da subvenção. Não há totais financiados ou concessão automática de reembolso.

## Interface e erros

Com JavaScript há prévia ampliada de imagens, abertura do PDF selecionado em outra aba, checklist do tipo escolhido e envio sem recarregar a tela em erro de validação. Campos e arquivos selecionados permanecem no formulário enquanto a aba continuar aberta. Não há localStorage ou fila offline.

Sem JavaScript, o POST multipart e os links funcionam. As seções dos tipos podem ser expandidas manualmente, com nomes de campo exclusivos. O retorno de validação preserva os campos de texto; o navegador exige selecionar novamente o arquivo. A prévia ampliada depende de JavaScript; o arquivo também pode ser conferido no aparelho antes do envio. Isso é informado na tela.

As ações têm área de toque de pelo menos 44 px, inputs de 16 px, colunas flexíveis e layout que se empilha em telas pequenas. Os campos específicos aparecem por tipo, sem tabela larga. A câmera usa input file com capture=environment, sem getUserMedia; o navegador e o aparelho decidem se oferecem fotografia. HEIC não é aceito nesta etapa. Não foram realizados testes físicos de câmera Android/iOS.

## Checklists configuráveis

app/services/receipt_rules.json contém a revisão, os tipos, itens, avisos e campos complementares. A origem é o briefing fornecido, pendente de validação com os documentos FACEPE aplicáveis. Não são regras legais certificadas.

A despesa guarda uma cópia da definição e das respostas usadas. Alterações no catálogo não mudam silenciosamente o histórico salvo. Uma edição do registro adota a versão atual e recalcula a situação. Altere o número de revisão ao modificar regras.

- Passagem aérea: compra, cartões de embarque e passageiro.
- Diária: recibo conforme modelo e comprovação de atividades. Não exige notas individuais de alimentação/hospedagem nessa orientação provisória.
- Inscrição: pagamento e participação; câmbio permanece condicional, com pendência ou declaração de não exigência sujeita à revisão.
- Aplicativo: comprovante, trajeto, data, horário, valor, placa, motorista e passageiro.
- Táxi: alerta de dificuldade e exigências documentais específicas pendentes de confirmação, sem invalidar automaticamente.
- Intermunicipal: bilhete e pagamento.
- Urbano: regras pendentes de confirmação.
- Seguro saúde: apólice, empresa, viajante e demais exigências da regra aplicável.
- Outro: classificação e referência informadas, com revisão pendente.

A marcação é uma declaração orientativa, não confere o conteúdo dos arquivos nem comprova regularidade. Não há aprovação financeira automática.

## Situações

Rascunho aceita metadados incompletos. Preparar para revisão exige data, valor, rubrica, descrição e campos específicos do tipo. Sem arquivo disponível, permanece Pendente de comprovante. Com arquivo e checklist incompleto, fica Pendente de revisão. Tipos táxi, urbano e outro permanecem em revisão por dependerem de classificação ou regras específicas.

Pronto para revisão indica metadados e checklist declarados completos, com anexos temporários disponíveis. Não significa validade financeira, nome oficial concluído, conservação durável ou envio ao Drive. Validado manualmente está reservado no catálogo de status, mas é proibido pelo backend e pela restrição SQLite desta etapa; uma futura etapa precisará implementar a autoridade e os critérios necessários.

## Armazenamento e confirmação

O processo cria um diretório exclusivo secco-receipts-* no temporário do sistema, fora de assets e do projeto. Seu caminho não é público nem configurável para um disco permanente. Durante os testes, fica obrigatoriamente dentro da concessão temporária do banco; nenhum arquivo sintético é colocado em data/ ou no ambiente operacional.

Cada arquivo usa identificador aleatório de 128 bits como nome físico, checksum SHA-256, MIME, extensão, tamanho, nome original e identificação da execução. Não há imagens em texto ou blobs no SQLite. O download exige sessão, permissão da missão e autoria, verifica checksum e usa Content-Disposition attachment, no-store e CSP sandbox. Os nomes originais não viram caminhos ou cabeçalhos de download.

Limites: 5 MB por arquivo, 4 arquivos e 12 MB por envio, 8 anexos e 20 MB por despesa, 100 MB por execução. O multipart usa o parser MIME da biblioteca padrão, limitado em bytes, partes, cabeçalhos e campos; aceita apenas form-data simples, sem partes aninhadas ou codificações de transferência. Não foi adicionada dependência para upload.

Extensão e MIME precisam corresponder. A validação verifica estrutura e CRC/descompressão limitada de PNG, segmentos e dimensões de JPEG, e estrutura básica/xref/finalização de PDF. PDF com ações ativas identificadas, JavaScript, anexos incorporados ou criptografia é recusado. Essas verificações são conservadoras e não substituem antivírus, decodificação completa de JPEG/PDF, CDR ou auditoria de formatos. Elas podem recusar arquivos legítimos mais complexos. O modo é exclusivo para conteúdo sintético e é bloqueado em produção.

A escrita do arquivo é exclusiva, com flush/fsync e conferência do checksum antes do estado Recebido temporariamente. Isso confirma somente a execução atual, sem promessa de durabilidade. Sync_status permanece pendente por restrição de banco. Nenhuma tela anuncia envio ao Google Drive.

O encerramento normal limpa somente a pasta pertencente à execução, validando caminho e marcador. A queda abrupta do processo pode deixar temporários; não há rotina de busca e exclusão ampla. A política do sistema operacional também pode removê-los. Após reinício, os metadados permanecem no SQLite, mas anexos de outra execução são apresentados como indisponíveis. A situação efetiva regride para pendência e o download responde 410. Não diga ao usuário que pode fechar com segurança baseado nesse armazenamento.

Falha de arquivo preserva os metadados e o vínculo do anexo com estado Falha; o detalhe informa o problema. Reenviar o mesmo conteúdo na edição recupera esse vínculo sem duplicá-lo. Falha transacional do SQLite reverte registros e remove os arquivos recém-criados, quando possível. Falhas de compensação podem deixar arquivos órfãos temporários, sujeitos à limpeza da execução e à quota. Não são tratados como salvos ou sincronizados.

Cada submissão possui chave idempotente vinculada a usuário, missão e payload; repetir o mesmo envio retorna o registro existente. Conteúdo repetido na mesma despesa é deduplicado pelo checksum. Alterações divergentes com a mesma chave e edições com versão antiga retornam conflito. O histórico registra autoria, metadados, situação e checksums, sem bytes dos anexos.

## Nome oficial

O nome preparado segue processo_pais_AAAA-MM-DD_rubrica_tipo_valormoeda_pessoa_id.ext. Componentes são normalizados para caracteres ASCII seguros e o ID único impede colisões. O nome físico temporário permanece opaco.

O processo é opcional e vazio em receipt_mission_config, pois depende do Termo de Outorga. Não há código inventado ou campo que aceite um processo arbitrário do formulário. Sem processo, rubrica, data, valor ou outros componentes obrigatórios, official_name fica nulo e name_status fica pendente. Mesmo um nome preparado continua provisório até revisão do documento aplicável e da futura integração.

## Banco e arquitetura

005_receipts.sql adiciona receipt_mission_config, expenses, expense_checklists, expense_attachments, expense_history e expense_submissions. Não cria novas missões, participantes ou identidades. Relações compostas impedem anexo e participante de outra missão. A autoria é obrigatória, criada a partir da sessão. As rotas reutilizam a autorização por missão e validam CSRF contra cookie e sessão, origem e limites no backend.

Módulos: core/receipt_upload.py para leitura limitada; services/receipts.py e receipt_rules.json para regras; services/receipt_storage.py para temporários; repositories/receipts.py para transações e histórico; routers/receipts.py para HTML e envio progressivo; templates/receipt* e static/css/receipts.css + static/js/receipts.js para a interface.

As migrações 001 a 004 permanecem preservadas. Os 289 cenários anteriores continuam na suíte, com expectativa de quantidade de migrações atualizada para 5.

## Pendências de integração

Confirmar Termos de Outorga, processos, rubricas, checklists e autoridade para revisão. Configurar login Google real de forma autorizada. Em outra etapa, implementar Shared Drive com escopos e permissões mínimos, idempotência remota, confirmação da API, recuperação de falhas e referência estável. Definir tratamento seguro dos arquivos, retenção, antivírus/CDR, privacidade e confirmação durável antes de permitir comprovantes reais.

Fontes técnicas consultadas: [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) para defesa em camadas e armazenamento privado. A validação de formatos é parcial e o produto permanece deliberadamente sintético.
