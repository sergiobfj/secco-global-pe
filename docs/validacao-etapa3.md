# Validação da etapa 3

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


## Resultado

203 testes pytest aprovados: 123 cenários anteriores preservados, 17 casos de isolamento e 63 de Diário/metas. Execução final em Python 3.12.8: 37,87 segundos. Existem dois avisos de depreciação conhecidos do adaptador TestClient/AnyIO, sem falhas.

As expectativas anteriores foram ajustadas apenas onde a nova funcionalidade muda o contrato: três migrações em vez de duas, Diário funcional em vez de placeholder e contadores legados sem classificação excluídos das metas comprovadas. Nenhum cenário anterior foi removido.

pip check: No broken requirements found. compileall de app, scripts e tests aprovado. node --check de app.js e qa-diary.cjs aprovado. Não foram instaladas novas dependências de runtime.

Os resultados brutos estão em checks.json (`artifacts/stage3/checks.json`, não distribuído).

## Banco e preservação

A primeira implementação da etapa foi a política de concessões temporárias. A suíte pytest e todos os fluxos de escrita no navegador rodaram em bancos temporários exclusivos, com configuração operacional recusada explicitamente. O helper de QA e seus endpoints de controle não existem no servidor normal.

Os dois helpers finais encerraram normalmente e removeram seu manifesto. A limpeza das concessões é validada pelos testes, incluindo recusa de marcador adulterado. Não foram executadas exclusões no banco operacional ou limpezas amplas de diretórios.

Após a validação isolada, foi feito backup SQLite consistente antes da única migração operacional aditiva. Todos os valores das colunas anteriores e os registros das migrações anteriores foram comparados e preservados. Resultado operacional:

| Verificação         | Resultado     |
| ------------------- | ------------- |
| integrity_check     | ok            |
| foreign_key_check   | sem violações |
| Missões             | 2             |
| Participantes       | 4             |
| Metas               | 4             |
| Itens de agenda     | 20            |
| Registros no Diário | 0             |
| Evidências          | 0             |
| Classificações      | 0             |
| Migrações aplicadas | 001, 002, 003 |

O backup está em .tools/backups/etapa2-before-stage3.sqlite3. Relatório de comparação: database-integrity.json (`artifacts/stage3/database-integrity.json`, não distribuído). A migração 003 é aditiva; as migrações 001 e 002 conservam seus hashes originais. Inicialização repetida, carga idempotente e integridade são testadas em bases temporárias.

A ausência de resultados iniciais é intencional. Não houve inserção de reuniões realizadas, evidências, aprovações ou textos de QA no banco de uso.

## Navegador e responsividade

Microsoft Edge Chromium 156 em modo headless. Larguras 360, 390, 768 e 1280 pixels. Foram validados 68 layouts: 36 do Diário e 32 da regressão de seleção, Hoje, agenda e formulários anteriores. Sem rolagem horizontal fora da faixa de dias, fontes locais carregadas, proporções oficiais da marca e navegação com alvos de ao menos 44 px.

A inspeção visual cobriu o Diário vazio desktop, formulário vinculado 360 px, formulário de evidência 360 px, registro realizado 390 px e dashboard com resultados 360 px. A identidade SECCO foi mantida, com agenda prioritária e dados secundários abaixo.

Relatórios:

- Diário e metas (`artifacts/stage3/report.json`, não distribuído).
- Regressão da agenda (`artifacts/stage2/report.json`, não distribuído).

Fluxos completos em cada largura:

- Agenda profissional, Registrar resultado e preenchimento de título, organização, data, horário, local e participantes.
- Criação de atividade realizada e persistência após recarregar.
- Reabertura do mesmo registro pela agenda, sem duplicação.
- Referência pendente, classificação pendente e ausência de contagem.
- Conferência de metadados, aprovação explícita e contagem única.
- Cancelamento do Diário e retirada da contagem.
- Console sem erros nos fluxos normais.

Também foram verificados cadastro de rascunho e validação sem JavaScript, skip link por teclado, falha de rede preservando o texto e retorno de Realizada para Rascunho após validação incompleta. A falha de conexão é provocada deliberadamente no teste; não é ocultada como envio concluído.

A regressão cobre preferência e troca de missão, navegação entre dias sem recarregar o shell, criação, edição, mapa por URL, cancelamento, teclado, sem JavaScript e falha de rede. Todos os dados sintéticos ficaram no temporário.

## Capturas principais

As telas vazias e com agenda conhecida foram capturadas antes dos cadastros sintéticos:

- Diário vazio em celular (`artifacts/stage3/diario-vazio-390.png`, não distribuído).
- Diário vazio no desktop (`artifacts/stage3/diario-vazio-1280.png`, não distribuído).
- Formulário vinculado à agenda (`artifacts/stage3/formulario-vinculado-360.png`, não distribuído).
- Visão Hoje da Argentina (`artifacts/stage3/hoje-argentina-390.png`, não distribuído).
- Metadados de evidência (`artifacts/stage3/formulario-evidencia-360.png`, não distribuído).

Cenários sintéticos identificados, sem correspondência com resultados reais:

- Registro realizado de QA (`artifacts/stage3/qa-registro-realizado-390.png`, não distribuído).
- Dashboard com resultado de QA (`artifacts/stage3/qa-dashboard-resultados-360.png`, não distribuído).

## Disponibilidade local

A porta 8001 foi preservada. GETs de saúde, Hoje e Planejamento responderam 200, sem operações de escrita de teste. Nenhuma tentativa de encerrar o processo antigo da porta 8000 foi realizada.

A etapa 3 está disponível em http://127.0.0.1:8002. Saúde, Diário Argentina e Hoje Portugal responderam 200. Essas consultas de disponibilidade foram somente leitura, separadas do QA de escrita isolado. Veja availability.json (`artifacts/stage3/availability.json`, não distribuído).

## Limitações conhecidas

Não há autenticação, autorização de coordenação, upload, inspeção automática de evidências, Google Shared Drive, financeiro, cache ou sincronização offline. Aprovação e conferência são declarações manuais no ambiente local. Sem critério fornecido ou comprovação correspondente, a classificação deve permanecer pendente.

A prevenção de duplicidade protege vínculos, envios, classificações e referências. Não compara semanticamente dois cadastros manuais ou o conteúdo de arquivos, que não são armazenados. O histórico guarda snapshots locais, sem autoria autenticada.

A validação em viewport não substitui teste físico em Android/iOS. Fechar ou recarregar um formulário não salvo ainda pode perder campos. Os testes de proteção não constituem uma sandbox contra código Python hostil ou ferramentas externas.

Não houve deploy, commit, push ou integração de contas externas.
