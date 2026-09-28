# Amostra real do servidor de API do Hermes

`chat-stream-amostra.jsonl` é um turno real, gravado em 2026-09-25 pelo
`gateway.hermes_cliente.ClienteHermes.stream_chat` contra o Hermes 0.21.4
(perfil `sabor-da-maria`, Opus 5 com esforço alto). Uma linha por evento SSE,
com `t` (segundos desde o envio), o nome do evento e os dados. Campos com mais
de 400 caracteres aparecem resumidos como `<N chars>`.

O que ela mostra, e que o backend do chat (`gateway.conversa` e
`gateway.eventos_do_turno`) trata:

- Os argumentos da ferramenta chegam em `tool.started.args`; `tool.completed`
  vem com `args: null`. O card nasce dos argumentos do início e é confirmado
  no fim.
- `tool.progress` com `tool_name: "_thinking"` traz o resumo do raciocínio em
  texto corrido. Nunca aparece para ela: pode ter valor não conferido.
- `assistant.commentary` repete texto já transmitido (`already_streamed: true`).
- `run.completed.messages` traz a conversa inteira do turno, com as saídas das
  ferramentas; é dali que sai a segunda conferência dos valores.
- Todo evento tem `session_id`, `run_id` e `seq` do Hermes.
- Primeiro texto em 3,7 s e turno completo em 19,6 s, com o servidor do motor
  já conectado no gateway (pelo CLI eram uns 40 s).
