# ADR 0004: o guard-rail numérico confere cada valor da resposta

## Contexto

O motor calcula certo (ADR 0002), mas quem escreve a resposta é o modelo. Ele
pode somar dois números do motor de cabeça, arredondar diferente, oferecer um
"preço de exemplo" que ninguém calculou ou repetir um número de uma página da
web. Instrução no `SOUL.md` reduz isso; não elimina. Nas medições da versão
anterior, pensar mais levava a mais conta de cabeça
(`docs/transcricoes/matriz/LEIA.md`).

## Decisão

Um plugin do Hermes, `hermes/plugins/guardrail-numerico`, confere a resposta
antes de ela chegar à Dona Maria.

- **O que confere.** Todo valor com "R$" e todo valor escrito com "reais" ou
  "real" ("24 reais"), menos proporção ("1 em cada 8 reais"). Porcentagem e
  quantidade não são conferidas.
- **Contra o quê.** As saídas de qualquer ferramenta do servidor `mise` na
  sessão inteira, lidas do banco de sessões do Hermes só para leitura (seguindo
  a sessão de origem depois de uma compressão), mais as saídas do turno atual e
  as palavras dela. A tolerância é de R$ 0,02, para arredondamento não virar
  acusação. Se o banco não abre, o histórico conta como vazio e a conferência
  fica mais rígida, nunca mais frouxa.
- **O que faz com o valor sem origem.** Troca por "[valor retirado]" e
  acrescenta uma nota que não acusa ninguém, "Tirei 1 valor desta resposta que eu não
  consegui conferir na conta do sistema. Me peça de novo que eu trago o número
  com a conta aberta."
- **Mais duas guardas no mesmo plugin.** A saída das ferramentas de web chega ao
  modelo embrulhada como dado não confiável, e a ferramenta que reescreveria as
  próprias skills (`skill_manage`) é barrada antes de rodar.
- Os hooks usados são os do Hermes 0.21, `on_session_start`, `pre_tool_call`,
  `post_tool_call`, `transform_tool_result` e `transform_llm_output`.

## Consequências

- Número sem origem não chega a ela, qualquer que seja o motivo do erro.
- O custo é o falso positivo. Na primeira medição, o plugin olhava só o turno
  atual e não conhecia sete ferramentas, e apagou 18 números certos
  (`docs/transcricoes/antes-das-correcoes/LEIA.md`). Hoje ele lê a sessão inteira
  e reconhece qualquer ferramenta do motor pelo nome; na última rodada da versão
  anterior, 0 de 38 respostas tiveram valor retirado
  (`docs/transcricoes/rodada-final-da-versao-anterior/LEIA.md`).
- As conversas gravadas em `docs/transcricoes/` viraram teste de regressão. O
  `test_guardrail.py` as relê turno a turno e prova que a conferência atual, que
  passou a ler "reais" por extenso, não retira nenhum valor que a versão medida
  deixava passar.
- O plugin não pega número sem unidade monetária nem porcentagem. O motor e
  o `SOUL.md` cobrem esses casos, e a avaliação do agente reprova o marcador
  "[valor retirado]" em qualquer cenário.

## Alternativas consideradas

- **Confiar só na instrução.** Medido, não bastou.
- **Bloquear a resposta inteira.** Ela ficaria sem resposta por causa de um
  número; retirar só o valor preserva o resto e diz o que aconteceu.
- **Pedir ao modelo para se corrigir num segundo turno.** Dobra a latência e o
  custo e continua dependendo do modelo acertar.
