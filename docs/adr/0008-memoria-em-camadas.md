# ADR 0008: memória em camadas, com uma fonte de verdade para cada fato

## Contexto

O agente precisa lembrar de muita coisa entre conversas: o que tem na
despensa, o que a cozinha dela permite, o que ela respondeu, as receitas que ela
avaliou, os preços que escolheu. O Hermes oferece memória própria (`MEMORY.md` e
`USER.md`, resumos que o modelo escreve e relê a cada sessão).

Um fato guardado em dois lugares diverge. Se a tela muda a despensa e o resumo
do Hermes continua dizendo o contrário, o agente fala com convicção uma
coisa que já não é verdade. E o `MEMORY.md` tem limite de 2.200 caracteres
(`hermes/config.overlay.yaml`): não cabem equipamentos, técnicas, restrições,
pratos e orçamento.

## Decisão

Cada tipo de memória tem uma casa, e só uma.

| Camada | Onde mora | O que guarda |
|---|---|---|
| De trabalho | a sessão do Hermes (banco de sessões do perfil) | o fio da conversa em curso, com a compressão configurada para preservar o começo e o fim (`compression.protect_first_n: 3`, `protect_last_n: 20`) |
| Episódica | `conversas.db` (`gateway/src/gateway/conversas_db.py`) e os eventos do dossiê | as conversas da web com turnos e eventos; cada mudança na despensa e na cozinha, com quem mudou, quando e o desfazer; decisões e compras só acrescentadas, com estorno em vez de apagar |
| Semântica | o dossiê em SQLite (`mise/src/mise/dossie.py`, `MISE_DOSSIE`) | perfil da cozinha, gostos, receitas do catálogo e em avaliação, avaliações, preços, compras, parâmetros do preço preliminar |
| Derivada | o índice da busca (ADR 0006) | nada próprio: é reconstruído do dossiê quando ele muda |

- O `MEMORY.md` do Hermes fica desligado (`memory.memory_enabled: false`), e a
  revisão periódica que escreveria nele também (`nudge_interval: 0`).
- O `USER.md` fica ligado só para preferência de conversa que ela disser (como
  gosta de ser chamada). O `SOUL.md` diz o que entra ali.
- O agente e a tela leem e escrevem no mesmo dossiê, pelas mesmas funções
  do motor. Quando a conversa muda um dado, o evento `estado.alterado` avisa a
  tela para recarregar.

## Consequências

- Mudar a despensa na tela muda o que o agente sabe no turno seguinte, sem
  resumo para atualizar.
- O histórico permite desfazer e contar a história ("atualizado pela conversa")
  sem perder o que havia antes.
- Um processo novo por turno (o que o `hermes chat --resume` faz) não perde
  nada: o que importa está no banco, não na memória do processo.
- A continuidade entre sessões do Hermes depende do dossiê, não do texto da
  conversa antiga. Quando o contexto passa do limite, a conversa da web continua
  numa sessão nova do Hermes, e os fatos continuam lá.

## Alternativas consideradas

- **Usar o `MEMORY.md` como memória principal.** Pouco espaço, sem estrutura,
  escrito pelo modelo e sem teste; diverge do que a tela mostra.
- **Memória vetorial das conversas.** Recupera o que foi dito, não o que é
  verdade agora: "tenho 2 kg de farinha" de ontem pode estar errado hoje.
- **Estado em memória no processo do servidor MCP.** Foi a primeira versão. Cada
  turno do `hermes chat --resume` é um processo novo, e o prato avaliado num
  turno sumia no seguinte.
