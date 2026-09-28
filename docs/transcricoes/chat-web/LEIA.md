# Chat da web, pelas rotas do backend

`amostra-1.jsonl` são dois turnos reais de uma conversa, gravados em 2026-09-25
pelas rotas da web (`POST /api/conversas/{id}/turnos` e o SSE de
`.../turnos/{t}/eventos`), com a agente de verdade: o servidor de API do Hermes
0.21.4, perfil `sabor-da-maria-avaliacao` (Opus 5, esforço alto), e a API do
motor apontando para o mesmo dossiê do servidor `mise` desse perfil. Uma linha
por evento normalizado, como a tela recebe, com `turno` e `t` (segundos desde o
`POST` do turno) acrescentados.

| | Turno 1 | Turno 2 |
|---|---|---|
| Pergunta | "Oi! O que tem de mais caro parado na minha despensa?" | "E quanto sai o quilo da alcaparra, de verdade?" |
| Atividade | olhando sua despensa | conferindo o custo de alcaparras |
| Card | `despensa_resumo` | `ingrediente` |
| Primeiro `texto.parcial` | 3,0 s | até 4,5 s (ver abaixo) |
| `texto.final` e fim | 13,7 s | 6,6 s |
| Valores retirados | 0 | 0 |

O que a amostra mostra:

- nenhum dígito de valor em reais sai no rascunho: cada "R$ …" chega como o
  sentinela (U+E000), e o `texto.final` traz os valores, conferidos contra as
  saídas do motor;
- as ferramentas de bastidor do Hermes (`skill_view`, `tool_describe`) e o
  raciocínio não aparecem; a atividade vem em pt-BR, sem nome de ferramenta;
- os dois cards saem com os dados do motor. As rotas deles (`/api/visao-geral`
  e `/api/despensa/itens/{id}`) ainda não existiam, então os dados são os
  mínimos, com os nomes de campo do contrato;
- no turno 2, o cliente fechou o SSE depois do quarto evento, de propósito, e
  voltou 2 s depois com `Last-Event-ID: 4`. O turno continuou no backend
  enquanto ninguém ouvia: os eventos 5 a 26 chegaram de uma vez na volta. Por
  isso o primeiro `texto.parcial` aparece em 4,5 s, a hora da reconexão.
