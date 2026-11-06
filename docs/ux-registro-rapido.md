# Fluxo futuro de registro rápido de comprovantes

> **Distribuição pública:** participantes, e-mails, domínio Workspace, IDs de Drive/pastas e projeto Cloud são fictícios. Documentos de validação preservam registros do desenvolvimento operacional; seus números não são resultados desta cópia pública. A validação da distribuição está em `docs/distribuicao-publica.md`.


Este documento prepara a experiência. A etapa atual não oferece captura, upload, armazenamento de documentos, lançamento financeiro ou sincronização.

## Entrada

Na visão Hoje da missão, a futura ação principal poderá oferecer “Registrar comprovante”, a um toque do polegar. Essa ação só deve aparecer como disponível quando o fluxo real estiver implementado. Hoje não existe botão que simula captura ou conclusão.

A navegação já fornece o contexto da missão escolhida. O cookie atual serve somente como preferência em desenvolvimento. Ele não identifica a pessoa nem autoriza despesas.

## Sequência prevista

1. Abrir o aplicativo na visão Hoje.
2. Tocar em Registrar comprovante.
3. Abrir a câmera ou selecionar um arquivo.
4. Conferir as sugestões automáticas e completar o checklist obrigatório do tipo de despesa.
5. Confirmar somente quando o registro e os arquivos realmente cumprirem os requisitos aplicáveis.

A câmera deve permitir refazer a foto e conferir a legibilidade. Selecionar arquivo permanece como alternativa. Antes de enviar, informar missão, responsável, estado do registro e dados que serão persistidos.

## Sugestões automáticas, sempre revisáveis

| Informação              | Fonte futura                                          | Limite                                                   |
| ----------------------- | ----------------------------------------------------- | -------------------------------------------------------- |
| Missão                  | Contexto e preferência, depois vínculos autorizados   | A preferência não concede autorização.                   |
| Participante            | Identidade autenticada                                | Não inferir a pessoa pelo aparelho ou cookie atual.      |
| Data local              | Fuso da missão                                        | Pode divergir da data do documento e precisa de revisão. |
| Moeda                   | País da missão, EUR ou ARS como sugestão              | Pode divergir da moeda do documento.                     |
| Descrição               | Preenchimento manual, com sugestões opcionais futuras | Deve descrever a despesa efetiva.                        |
| Nome técnico do arquivo | Identificador único gerado no servidor                | Sem exigir que o viajante renomeie arquivos.             |

OCR e extração automática, se adotados, devem apresentar valores como sugestões com revisão humana. Nenhum campo obrigatório pode desaparecer apenas por ter sido inferido.

## Checklist e integridade

Os campos, documentos e regras legalmente necessários dependem do edital, do tipo de despesa e do checklist de prestação de contas validado com a FACEPE. Eles ainda precisam ser especificados e versionados antes de implementar a parte financeira. Este documento não substitui nem inventa requisitos do edital.

A redução de cliques deve vir de contexto, padrões revisáveis, agrupamento e preenchimento assistido. Ela não pode eliminar exigências legais ou permitir a confirmação de um registro incompleto.

Cada checklist deve indicar os requisitos faltantes de forma objetiva. A confirmação financeira fica bloqueada até que os requisitos estejam cumpridos. Se for permitido salvar um rascunho, a interface deve distinguir claramente rascunho de registro completo.

## Estados propostos para a etapa futura

| Estado                      | Comunicação ao usuário                                                    |
| --------------------------- | ------------------------------------------------------------------------- |
| Rascunho incompleto         | Mostra os requisitos faltantes, sem afirmar que o registro foi concluído. |
| Completo e salvo localmente | Informa que os dados ainda podem não estar sincronizados.                 |
| Envio pendente              | Mostra a pendência de sincronização.                                      |
| Sincronizado                | Somente após confirmação verificável do servidor e do arquivo.            |
| Falha no envio              | Preserva o preenchimento e permite tentar novamente sem duplicar.         |

Esses estados são proposta de UX. Não foram implementados nesta etapa. O sistema atual grava a agenda diretamente no servidor local, sem fila offline.

## Arquitetura preparada

- O contexto da missão já existe na URL e no banco.
- A visão Hoje concentra consulta e ações, com componentes acessíveis no celular.
- Os formulários da agenda demonstram validação progressiva e preservação dos campos em erros, mas não são reutilizados como modelo financeiro.
- Reenvios da agenda já utilizam uma chave idempotente e controle de versão. O fluxo financeiro deverá ter garantias próprias para transações e arquivos.
- A futura identidade autenticada, autorização por missão, autoria, moeda, checklist e documento serão modelados em migrações aditivas.
- O nome técnico deverá ser gerado automaticamente, por exemplo com UUID e extensão validada, sem depender de dados pessoais.
- Permissões de câmera, política de armazenamento, limites, tipos de arquivo e segurança de conteúdo serão definidos antes do upload real.
- Auditoria financeira, integridade dos documentos e comprovação não podem ser confundidas com o histórico operacional da agenda atual.

## Critério de aceite futuro

O usuário consegue registrar o comprovante com poucas interações, revisando as sugestões e cumprindo o checklist. A interface informa com precisão o que foi salvo, o que está incompleto, o que foi sincronizado e o que ainda exige ação.
