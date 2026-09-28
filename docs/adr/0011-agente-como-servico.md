# ADR 0011: o agente como serviço da plataforma

## Contexto

O enunciado pede um agente conversacional. A Dona Maria, porém, trabalha com
telas: a despensa, a cozinha, as receitas, o cardápio, o preço. Um chat isolado
numa página obriga a explicar de novo o que ela já está vendo ("aquele arroz da
tela de receitas"), e uma tela sem o agente deixa a dúvida sem resposta
exatamente onde ela aparece.

## Decisão

O agente é um serviço que qualquer parte da plataforma chama, com a mesma
API, a mesma memória e as mesmas regras.

- **Em toda tela.** O painel da conversa fica montado no layout raiz: um painel
  lateral de 420 px a partir de 1024 px de largura e uma folha de altura inteira
  no celular. A página `/conversa` mostra a lista e a conversa em tela cheia. Os
  botões de conversar (no cabeçalho, flutuante e na barra inferior) e o
  "Perguntar" dos cards abrem o painel; nenhum deles manda mensagem sozinho.
- **Com o contexto da tela.** A primeira mensagem leva o que ela está vendo
  (tela, e o item ou a receita nas páginas de detalhe); o backend resolve e
  passa ao agente numa linha só (ver a
  [API](../api-do-agente.md#contexto-da-tela)).
- **O backend é dono do turno.** O POST devolve 202, o turno roda numa tarefa do
  backend, e a resposta chega por SSE numerado, com retomada por `?desde=` ou
  `Last-Event-ID`. Fechar a aba não cancela; parar é um pedido explícito.
- **A resposta é mais do que texto.** O fluxo traz o que o agente está
  fazendo (em português, sem nome de ferramenta), cards com os dados da própria
  rota da tela, sugestões de próximo passo e o aviso `estado.alterado`, que faz
  as telas abertas recarregarem o que a conversa mudou.
- **Os cards agem.** Um botão num card manda uma ação (responder uma pergunta da
  cozinha, decidir um prato, avaliar uma receita) que o backend aplica antes de
  chamar o agente.
- **Um contrato para os dois lados.** As formas ficam em `contratos/web/`; o
  backend confere as rotas contra elas, a interface as usa como fixture, e o
  motor falso dos testes de ponta a ponta as serve.
- **A plataforma chama o agente sozinha.** A descoberta de receitas roda em
  segundo plano, numa execução do Hermes com um pedido fixo e limites de
  pesquisas, páginas e tempo, e manda o progresso por SSE para a grade. Uma
  chave (`SABOR_DESCOBERTA`) a desliga, porque cada rodada custa chamadas ao
  modelo; desligada, o botão abre a conversa com o pedido pronto.

## Consequências

- Ela pergunta de onde está, e o agente sabe do que ela fala.
- A conversa e a tela mudam os mesmos dados, pelo mesmo motor: o que se decide
  numa aparece na outra sem sincronização à parte.
- A superfície cresce: máscara no streaming (ADR 0010), retomada, idempotência
  por `id_cliente`, cards com dados de rota, testes de ponta a ponta com um
  motor falso. É o custo de um chat que se comporta como parte do produto.

## Alternativas consideradas

- **Só a página de conversa.** Mais simples, e o agente perde o contexto de
  onde a dúvida nasceu.
- **WebSocket.** Bidirecional sem necessidade: mandar mensagem é um POST
  idempotente, e o que desce é um fluxo numerado que o SSE retoma de graça pelo
  `id`.
- **O navegador falando direto com o Hermes.** Exporia a chave, e a resposta
  chegaria sem máscara, sem cards e sem o turno sobreviver à aba fechada.
