# Validação da etapa 2

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


> **Distribuição pública:** nomes, e-mails, domínio Google Workspace, IDs de Drive/pastas e identificadores Google Cloud deste documento são fictícios. Resultados e decisões descritos referem-se ao projeto operacional.


Concluída em 01/11/2026, no fuso America/Sao_Paulo. Python 3.12.8, Windows e Microsoft Edge headless. As telas calculam datas no fuso de cada missão; por isso Lisboa pode já mostrar o dia seguinte ao de Buenos Aires.

## Resultado final

| Verificação | Resultado |
| --- | --- |
| Suíte completa | 123 testes aprovados |
| Regressões da etapa 1 | 60 cenários mantidos, com expectativas atualizadas para as mudanças solicitadas |
| Novos casos | 63 |
| Layouts em navegador | 32 combinações aprovadas |
| Larguras | 360, 390, 768 e 1280 px |
| Rolagem horizontal do documento | Ausente |
| Faixa de dias | Rolagem interna intencional |
| Erros de console nos fluxos normais | Nenhum |
| Navegação sem JavaScript | Consulta, criação, validação e preferência aprovadas |
| Teclado | Skip link, foco e Escape aprovados |
| Falha de rede no envio | Campos preservados e estado não salvo informado |
| SQLite | Integridade e chaves estrangeiras verificadas |
| Inicialização repetida | Sem duplicações |
| Migração 001 | Preservada byte a byte |
| pip check | Sem dependências inconsistentes |
| Compilação | Sem erros |

A suíte continua mostrando dois avisos de depreciação do TestClient, relacionados ao adaptador httpx e a um alias AnyIO. Não foram ocultados. Nenhum erro de aplicação foi encontrado nos testes finais.

## Regressões atualizadas

Os testes anteriores continuam presentes. As expectativas que mudaram por solicitação do projeto foram ajustadas: nome Alan Renato, segunda migração, Planejamento funcional e distinção entre links internos e o link institucional externo. O teste de rollback agora copia todas as migrações existentes antes de acrescentar uma migração inválida de teste.

## Cobertura nova

- Carga dos 20 itens conhecidos, proveniência pendente e ausência de horários ou confirmações inventadas.
- Criação mínima e completa, persistência, edição de data/horário/status e participantes.
- Todos os status e origens suportados.
- Campos opcionais, datas inválidas, limites de texto e links inseguros.
- Isolamento de leitura e escrita por missão, inclusive por chaves estrangeiras.
- Cancelamento sem exclusão e snapshots de histórico.
- Reenvio idempotente, conflito de versão e prevenção de descarte silencioso de valores em reenvios diferentes.
- CSRF, origem externa, tipo e limite de formulário.
- Cookie de preferência, troca de missão e entrada direta em Hoje.
- UTC, data local, horário de verão e horários ambíguos/inexistentes.
- Importação idempotente de eventos legados, preservando a origem.
- Atualização a partir da primeira migração sem perder ID ou e-mail.
- Próximo compromisso considerando apenas confirmação e atividades em curso.
- Atividade realizada sem incremento automático de metas.

## Telas verificadas

Oito telas, em cada uma das quatro larguras:

1. Seleção de missões.
2. Hoje Portugal.
3. Hoje Argentina.
4. Agenda argentina em 18/11.
5. Atividades portuguesas sem data.
6. Detalhes do simpósio.
7. Nova atividade.
8. Edição de atividade.

O teste verifica fonte local, carregamento e proporção da marca oficial, limites do conteúdo e alvos da navegação. Executa criação, edição, recarga, mapa por URL, cancelamento, troca de missão, retorno à missão padrão e troca de dia sem recarregar a estrutura principal.

As capturas e report.json estão em artifacts/stage2/. Exemplos sem atividades sintéticas: agenda-argentina-360.png, hoje-argentina-390.png e hoje-portugal-1280.png.

## Isolamento e correção durante o QA

Na primeira tentativa, o encerramento do processo de prévia não encerrou seu processo filho, e a porta antiga continuou apontando para o banco operacional. Quatro atividades sintéticas foram identificadas por IDs e títulos exatos, exportadas em artifacts/stage2/qa-records-removed.json e removidas exclusivamente com seus vínculos e histórico de teste. Nenhum registro fornecido pela equipe foi removido.

O banco operacional foi conferido depois da correção: duas missões, quatro participantes e 20 itens conhecidos, sem itens sintéticos, sem compromissos confirmados e com integridade preservada.

Para impedir repetição, scripts.serve_qa cria um banco temporário e registra uma identidade exclusiva. O teste de navegador exige essa identidade antes de qualquer escrita. O servidor operacional não oferece os endpoints de QA. Os testes finais foram executados nesse ambiente isolado e o servidor final de QA encerrou pelo endpoint protegido por CSRF.

## Limites concretos

- Testes móveis usam viewports de um navegador real, sem aparelhos físicos.
- O sistema permanece restrito ao computador local, sem acesso remoto ou autenticação.
- Não houve auditoria completa de acessibilidade, instalação PWA ou teste offline.
- Atividades que atravessam a meia-noite precisam ser divididas.
- Fechar ou recarregar um formulário ainda não salvo pode perder seu texto.
- Não existem upload, sincronização, dados financeiros ou integração de conta Google.
- A porta 8000 segue ocupada por um processo anterior que o ambiente de execução não autorizou encerrar. A versão atual foi disponibilizada em http://127.0.0.1:8001. Para reutilizar 8000, é necessário encerrar o processo anterior e iniciar novamente pelo README.

Não houve deploy, commit, push ou alteração de contas externas.
