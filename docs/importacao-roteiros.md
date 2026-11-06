# Importação privada de programação oficial

A funcionalidade pública lê grades PDF e XLSX locais. Este repositório contém código genérico e testes sintéticos; documentos oficiais, roteiros individuais, perfis de leitura, bancos, backups e relatórios de importação permanecem em diretório privado **fora do repositório**. Nenhuma programação real é incorporada ao seed. Esta funcionalidade não acessa Google Drive nem executa deploy.

## Preparação e formatos suportados

Instale `requirements-dev.txt` com Python 3.12. Para a aplicação pública, inicialize somente um banco novo com as configurações fictícias descritas no [guia público](distribuicao-publica.md). O banco operacional e a distribuição pública têm migrações com checksums diferentes; não substitua suas configurações, não inicialize a aplicação pública sobre o banco operacional e não execute seu migrador nele.

O comando administrativo de importação é separado do startup: não carrega `.env`, não provisiona contas, não aplica migrações e exige banco local existente, com a estrutura de agenda/permissões da migração 007 ou posterior. Ele pode ser executado pelo responsável autorizado sobre um banco compatível já existente, após revisão privada e backup validado, sem modificar os arquivos de migração.

- **XLSX:** data inicial Excel em C2; dias na linha 3 a partir de C, como datas ou fórmulas `=C2+n`; horas crescentes na coluna B a partir da linha 5. Células mescladas verticalmente e células consecutivas do mesmo compromisso são consolidadas. Sessões não consecutivas são distintas, salvo se o texto contiver o mesmo intervalo explícito. Compromissos simultâneos são mantidos. Fórmulas de datas desconhecidas são recusadas, sem recalcular ou executar fórmulas. Células ocultas recebem aviso para revisão.
- **PDF:** texto extraível, cabeçalhos horizontais de datas e escala horária à esquerda. O ano deve ser fornecido explicitamente. Não há OCR nem interpretação universal de qualquer layout: confira a imagem integral e os blocos extraídos antes de aplicar. Cabeçalhos ou escala irreconhecíveis bloqueiam a leitura.

Rótulos exclusivamente contextuais, como cabeçalhos de cidade, podem ser declarados em um perfil JSON privado: `{"context_labels":["Cidade Fictícia"]}`. A exclusão só ocorre por correspondência completa do rótulo. Dias livres não geram atividades ou sugestões turísticas. Confira também notas e células fora da grade: a extração automática não substitui a leitura integral do documento.

## Precisão dos horários e categorias

Intervalos escritos no texto têm precedência e são identificados como **informados no documento**, sem promover o status a Confirmado. Horários derivados de linhas XLSX são **estimados pela grade**; uma célula isolada não gera automaticamente 30 minutos de duração. Expressões como “confirmar horário” tornam o horário **provisório**. Uma marca de término ocupada na grade pode representar o próprio término; o relatório registra essa ambiguidade sem adicionar duração ao intervalo escrito. Divergências efetivas entre texto e grade bloqueiam a importação daquele item.

Áreas coloridas do PDF nunca preenchem os horários de início/fim: quando reconhecíveis, fornecem apenas uma janela sugerida, explicitamente não confirmada. Uma coluna totalmente colorida não estabelece duração de evento. Campos ausentes permanecem vazios e aparecem no relatório. Datas e horas locais são convertidas para UTC usando o fuso da missão existente; horários ambíguos ou inexistentes por mudança de fuso são recusados pelo validador atual.

Todos os itens importados usam origem **Agenda oficial**, com status inicial **A confirmar**, inclusive refeições institucionais e deslocamentos. A categoria mantém a função da atividade. Turismo/descanso manuais continuam separados; nenhum passeio é inventado. A passagem da data não marca atividade como realizada.

## Dry-run obrigatório

Exemplo fictício em PowerShell, com todos os materiais privados fora do Git:

```powershell
$itineraryPrivate = Join-Path $env:USERPROFILE 'PrivateAgenda'
python scripts/import_itinerary.py --input "$itineraryPrivate/grade-ficticia.xlsx" --database "$itineraryPrivate/app.sqlite3" --mission portugal --source-key ficticia-2031 --profile "$itineraryPrivate/perfil.json" --report "$itineraryPrivate/previa-01.json"
```

Para PDF, acrescente `--year 2031` e use o documento fictício correspondente. A missão selecionada deve existir, com período e fuso corretos. O comando não cria missões, participantes ou permissões. Bancos por URL, UNC ou unidade de rede são recusados; não execute sobre banco remoto ou cópia montada de VPS.

O JSON privado contém os compromissos encontrados, novos, já associados, possíveis duplicações, conflitos, campos ausentes, intervalos simultâneos, referências às células/blocos, valores anteriores e propostos e hashes das tabelas. A saída padrão contém somente contagens e o caminho do relatório. Os relatórios contêm dados reais quando a origem é real: não os publique.

Revise os dois documentos integralmente, os horários, as associações e o impacto. Possíveis duplicações não são mescladas automaticamente. Um vínculo expressamente revisado pode ser informado no perfil como `"links":{"official:CHAVE_DO_RELATORIO":123}`. Ele preserva todos os campos, participantes, versão e autoria do registro anterior e acrescenta somente a associação documental e um registro técnico no histórico. Vínculo não remarca nem completa um registro: se a agenda existente divergir, decida a edição separadamente pela interface autorizada. Vínculos entre missões, múltiplos eventos para o mesmo registro ou substituição de uma chave de criação manual são recusados.

Use sempre a mesma `--source-key` para a mesma edição documental. A chave combina missão, dia, título normalizado e ocorrência; a âncora da célula/bloco também detecta renomeação/remarcação no mesmo ponto. Mudanças simultâneas de título, data e posição não podem ser reconciliadas com segurança sem um identificador externo: revise possíveis itens novos e `missing_source_items`. Itens que saem da origem continuam intactos, nunca são excluídos. Não altere a chave para contornar conflitos.

## Aplicação local revisada

Somente após decisão do responsável, repita as mesmas opções de leitura e acrescente:

```powershell
python scripts/import_itinerary.py --input "$itineraryPrivate/grade-ficticia.xlsx" --database "$itineraryPrivate/app.sqlite3" --mission portugal --source-key ficticia-2031 --profile "$itineraryPrivate/perfil.json" --apply --owner-authorized-local --approved-plan "$itineraryPrivate/previa-01.json" --backup "$itineraryPrivate/backup-01.sqlite3" --report "$itineraryPrivate/aplicacao-01.json"
```

O impacto atual precisa corresponder exatamente à prévia. Uma alteração em qualquer tabela invalida a aprovação. Antes da escrita, o comando cria um backup SQLite consistente em arquivo novo e valida `integrity_check`, chaves estrangeiras e correspondência lógica com a prévia. Toda a importação é transacional: uma falha reverte o lote. Tabelas fora da agenda são conferidas novamente antes do commit SQLite. Diários, metas, finanças, comprovantes, usuários, permissões e migrações não são alterados.

Conflitos bloqueiam o lote por padrão. **Somente com decisão explícita**, `--allow-partial` aplica os novos/vínculos revisados e mantém possíveis duplicações ou conflitos pendentes. O resultado informa criados, atualizados, associados e não aplicados; itens pendentes não contam como importados. Uma edição da origem exige novo dry-run e `--allow-source-updates` para atualizar somente importados ainda idênticos à versão anterior. Uma edição posterior da equipe, inclusive remarcação, bloqueia a atualização automática mesmo com essa opção.

A proveniência versionada ocupa a coluna técnica `request_key` existente; `seed_key` anterior é preservada. São guardados hash do documento, nome, célula/bloco, precisão do horário e impressão da versão importada. A segunda execução deve mostrar `existing` para os itens aplicados, sem novos registros ou novo backup. Alterar o nome do arquivo não muda sua identidade lógica. Nunca edite esses metadados diretamente para forçar atualização.

## Agenda e permissões

Planejamento e Hoje separam Agenda oficial, Turismo / tempo livre e outras atividades. Detalhes mostram origem, precisão do horário e localização disponível; endereços transcritos permitem pesquisa no Maps, identificados como ainda sujeitos à conferência da equipe. Os controles existentes de edição, remarcação e Diário permanecem. O próximo compromisso confirmado mantém sua semântica; na ausência dele, uma previsão documental futura aparece explicitamente “Previsto · a confirmar”.

O comando é administrativo local, destinado ao responsável pelo arquivo SQLite; não é uma nova rota web nem concede privilégios a contas. As rotas continuam permitindo consulta das duas missões e edição apenas na missão autorizada. Coordenação mantém somente consulta. Não há alteração de IAM/ACL ou configuração de serviços.

## Validação e futura transferência

```powershell
python -m pytest tests/test_itinerary_import.py -q
python -m pytest -q -p no:cacheprovider -rfEs
```

As fixtures PDF/XLSX são geradas com dados sintéticos em diretórios temporários protegidos. Nenhum teste requer os documentos privados ou acesso real ao Google Drive. Os skips históricos da cadeia Cloud Shell continuam explicados no [guia público](distribuicao-publica.md), sem contar como aprovados.

Para uma instalação futura, transfira por canal privado somente os documentos necessários, perfil revisado e, conforme a estratégia escolhida, backup operacional consistente ou plano de importação revisto para o banco de destino. Relatórios e backups são evidências privadas, não arquivos públicos de deploy. Um dry-run de outro banco nunca autoriza escrita no destino: gere e revise uma nova prévia local. Esta documentação não implica que os dados ou o sistema estejam disponíveis em VPS.
