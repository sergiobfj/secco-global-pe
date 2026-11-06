# Diário de Atividades e metas

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


## Uso rápido

Agenda → compromisso profissional → Registrar resultado → revisar, descrever o que aconteceu e os resultados → Salvar registro. O status começa em Rascunho. Escolher Realizada é uma decisão explícita, com campos mínimos obrigatórios.

Sem compromisso anterior, use Diário → Registrar atividade. Os tipos são Reunião empresarial, Visita institucional, Participação em evento, Networking profissional, Apresentação do GeoCarbo e Outra atividade profissional. Não há CRM, contatos comerciais, funil ou pipeline.

Título, data, descrição e resultados são obrigatórios para Realizada. O rascunho pode ficar incompleto. Horário é opcional. Organização, local, participantes, objetivo e próximos passos ficam em uma seção progressiva. Os participantes precisam pertencer à missão.

## Vínculo com planejamento

O vínculo itinerary_item_id é opcional, único e não pode atravessar missões. Institucional e Evento permitem iniciar o Diário a partir dos detalhes. Turismo, alimentação, transporte e descanso não geram registros profissionais automaticamente.

O formulário aproveita título, data, início, organização, local e participantes conhecidos. A descrição planejada aparece como objetivo, sem ser copiada para a descrição do que efetivamente ocorreu. Os resultados começam vazios. Organizações institucionais conhecidas da carga podem ser aproveitadas quando o título original permanece igual.

Criar um registro não altera o status da agenda. Um compromisso Realizado também não cria registro ou soma metas sozinho. A agenda mostra Registro no Diário e o detalhe passa a oferecer Abrir registro do Diário. A restrição única e as transações impedem dois Diários para o mesmo compromisso, inclusive em envios concorrentes.

Cadastros manuais distintos não têm deduplicação semântica automática. A equipe deve evitar registrar o mesmo encontro por duas vias. A aplicação protege vínculo, chave de envio, classificação e referências de comprovação contra duplicação.

## Metas aprovadas

| Missão    | Reuniões qualificadas | Resultado formal                     |
| --------- | --------------------- | ------------------------------------ |
| Portugal  | 10                    | 3 LOIs                               |
| Argentina | 8                     | 3 manifestações formais de interesse |

Reuniões realizadas é a quantidade de Diários do tipo Reunião empresarial com status Realizada. Esse indicador é diferente de Reuniões qualificadas. Nenhuma atividade apenas agendada entra em ambos.

Para uma classificação entrar na meta, todas as condições abaixo precisam existir:

1. Registro Realizada, com a versão atual.
2. Meta pertencente à missão e classificação única por registro e tipo de meta.
3. Justificativa e referência do critério da proposta ou orientação efetivamente recebida.
4. Aprovação informada, com responsável e instante de registro.
5. Evidência do próprio registro, com referência externa conferida, identificador, responsável, nota e instante da conferência.
6. A aprovação corresponde à versão atual dessa evidência.

Para reunião qualificada, o tipo do Diário deve ser Reunião empresarial. Isso define a categoria, sem inventar critérios substantivos de qualificação. Os critérios da proposta ainda não foram fornecidos e precisam ser indicados e validados pela coordenação.

LOI exige evidência Carta de intenção. Manifestação de interesse exige Documento, Carta de intenção ou Confirmação institucional correspondente. A escolha do tipo não verifica o conteúdo automaticamente; a conferência manual deve comprovar a correspondência.

Rascunhos, cancelados, decisões pendentes/rejeitadas e evidências pendentes/invalidadas não contam. A visão SQL eligible_goal_claims é a fonte comum dos totais, sem contadores editáveis ou incremento paralelo. Dados antigos de mission_results são preservados, mas não entram como resultados comprovados sem reclassificação pelo Diário.

## Revisão e concorrência

O registro, a evidência e a classificação possuem version. Edição desatualizada recebe HTTP 409 e mantém os campos para comparação. A criação do Diário e da referência possui chave de envio; repetição idêntica não duplica o registro.

Alterar o Diário devolve todas as suas classificações para Pendente de validação. Alterar uma evidência devolve as classificações relacionadas para pendência. A classificação verifica a versão do Diário e o conjunto de versões das referências visto no formulário. A transação verifica novamente a versão da evidência selecionada. A visão SQL também exige correspondência de versões, impedindo aprovações antigas de aparecerem nos indicadores.

O histórico conserva snapshots de registros, referências e decisões, com instante UTC. Não há exclusão física na interface. Cancelar preserva os fatos e retira os resultados dos indicadores elegíveis.

## Evidências sem upload

Tipos: fotografia, certificado, lista de presença, documento, carta de intenção e confirmação institucional.

Nesta etapa, os registros contêm somente metadados e vínculos. Nenhum arquivo é capturado, enviado ou armazenado. A interface informa Upload oficial pendente de integração. A futura integração com Google Shared Drive deverá acrescentar identificadores de armazenamento e controles de acesso, sem alterar a relação entre missão, Diário e evidência.

Uma referência pendente pode conter apenas título e tipo. Para marcar Referência externa conferida, informe link HTTPS do documento existente, identificador único, pessoa que conferiu e nota do que foi conferido. URLs com credenciais são recusadas. A aplicação não faz download nem solicita acesso a contas externas.

A referência e o identificador são únicos por missão. Documentos formais não podem ser reutilizados silenciosamente para duplicar resultados. Identificadores e links diferentes do mesmo documento real ainda exigem atenção da equipe; não existe comparação de conteúdo de arquivos nesta etapa.

## Limites de confiança

A etapa 4 acrescenta a estrutura de autenticação Google e identifica quem registra as informações quando há sessão verificada. O login externo ainda depende de configuração e validação real. Responsável pela validação e Quem conferiu continuam sendo declarações manuais de decisões recebidas. Não demonstram identidade autenticada, assinatura, anuência formal automatizada ou validação da FACEPE. Mantenha pendente quando não houver decisão efetivamente recebida ou comprovação disponível.

A aplicação permanece exclusiva ao desenvolvimento local. Nenhum dado financeiro foi implementado. O fluxo depende do servidor; fechar um formulário ainda não salvo pode perder os campos. Não há sincronização offline.
