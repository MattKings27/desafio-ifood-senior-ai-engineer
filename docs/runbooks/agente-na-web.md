# O agente na web: como o chat fala com o Hermes

O chat da web não sobe um agente próprio. Ele conversa com o **mesmo** agente
do terminal: o mesmo perfil do Hermes, com a mesma persona, as mesmas skills, o
mesmo guard-rail, a mesma memória e o servidor MCP do motor. O caminho é o
servidor de API que o Hermes 0.21.4 tem dentro do gateway.

```
Navegador ─► Next (/motor/*) ─► FastAPI :8777, dono do turno ─► Hermes :8642 /p/sabor-da-maria/…
                                  (gateway/src/gateway/          (gateway do Hermes)
                                   hermes_cliente.py)
```

O único código do projeto que fala com esse servidor é
`gateway/src/gateway/hermes_cliente.py`. A chave fica no backend: o navegador
nunca fala com o Hermes, e por isso `API_SERVER_CORS_ORIGINS` fica sem valor.

## Ligar (uma vez por máquina)

O servidor de API vem desligado. Ele abre quando o gateway sobe e encontra uma
`API_SERVER_KEY` no `~/.hermes/.env`. São **duas chaves**, e a diferença importa:

| Chave | Onde | Para que serve | Quando passa a valer |
|---|---|---|---|
| do perfil padrão | `~/.hermes/.env` | faz o gateway abrir a porta 8642 | no próximo reinício do gateway |
| do perfil | `~/.hermes/profiles/<perfil>/.env` | autentica `/p/<perfil>/…` | na hora: o Hermes relê o `.env` do perfil a cada pedido |

A chave do perfil padrão **não** vale em `/p/<perfil>/`: dá 401. Cada perfil tem a
sua, os de avaliação inclusive.

O `hermes/api_da_agente.sh`, que o bootstrap chama no fim, cuida das duas:

```bash
make bootstrap                      # tudo, e no fim reinicia o gateway
SEM_REINICIAR=1 make bootstrap      # tudo, menos o reinício
hermes/api_da_agente.sh             # só as chaves (gera o que faltar, reinicia, confere)
SEM_REINICIAR=1 hermes/api_da_agente.sh
make perfil-avaliacao               # o perfil de avaliação ganha a própria chave
```

O script gera a chave com `secrets.token_hex(32)` (64 hexadecimais) direto no
arquivo, em modo 0600, só onde faltar, e nunca imprime o valor. Rodar de novo
não troca chave nenhuma, com uma exceção: `hermes profile create --clone` copia
o `.env` do perfil padrão, então um perfil criado depois que o padrão ganhou
chave nasce com a mesma. Essa o script troca, mexendo só na linha da chave.

> **Reiniciar o gateway interrompe o turno em andamento.** O gateway atende os
> perfis todos no mesmo processo; um turno que estiver rodando naquela hora é
> interrompido, e a conversa da web mostra o agente fora do ar até o gateway
> voltar. `make reiniciar-agente` reinicia e espera o servidor de API responder.

## Conferir

```bash
make agente-status
```

Mostra, sem nenhum segredo: se o gateway está rodando (PID), se as duas chaves
existem (e se não são a mesma), se a porta responde, se o servidor aceitou a
chave do perfil num GET autenticado em `/p/<perfil>/api/sessions`, e o modelo,
o esforço e as reservas do perfil. Sai com 0 só quando o chat pode conversar.

Para ver só a porta, sem chave: `curl -s http://127.0.0.1:8642/health`. Para
qualquer coisa autenticada, use o `make agente-status`: montar um `curl` com a
chave põe o segredo na linha de comando e no histórico do shell.

## Desenvolver

```bash
make dev
```

Confere o ambiente Python, o `webapp/node_modules`, as portas 8777 e 3000 e o
agente, e sobe a API e a interface juntas, com os logs prefixados (`[api]`,
`[web]`). Ctrl-C derruba as duas; se uma cair, o script derruba a outra. O
agente fora do ar é só um aviso: o resto do app funciona, e o chat avisa que
ele está indisponível. Outras portas: `MISE_HTTP_PORT=8778
DEV_PORTA_WEB=3001 make dev`.

| Variável | Padrão | O que faz |
|---|---|---|
| `MISE_HERMES_URL` | `http://127.0.0.1:8642` | onde está o servidor de API |
| `MISE_HERMES_PERFIL` | `sabor-da-maria` | o perfil (vira o prefixo `/p/<perfil>`) |
| `MISE_HERMES_CHAVE` | (vazia) | a chave; quando existe, vence o `.env` do perfil |
| `HERMES_HOME` | `~/.hermes` | onde procurar o `.env` do perfil, como o próprio Hermes |
| `MISE_CONVERSAS` | `conversas.db` ao lado do dossiê | o banco das conversas da web (o histórico que a tela mostra) |
| `MISE_CONVERSA_LIMITE_TOKENS` | `150000` | contexto a partir do qual a conversa segue numa sessão nova do Hermes |
| `MISE_FUSO` | `America/Sao_Paulo` | o fuso dos textos de data ("hoje, 14:32") |
| `MISE_HOSTS` | (vazia) | nomes aceitos no `Host` além de `localhost` e `127.0.0.1` |
| `MISE_CORS` | `http://localhost:3000,http://127.0.0.1:3000` | origens do navegador que podem escrever (e o CORS) |

## Quando não funciona

**"servidor de API fora do ar"**. O gateway está parado (`hermes gateway
status`), ou subiu antes de existir a chave do perfil padrão. Gerada a chave,
falta reiniciar: `make reiniciar-agente`. Se outra coisa ocupa a 8642
(`ss -ltnp | grep 8642`), o Hermes registra `api_server_port_in_use` e não tenta
de novo sozinho: libere a porta e reinicie.

**401 (a chave foi recusada)**. A chave enviada não é a do perfil. Causas, da mais
comum para a menos: usar a do perfil padrão num `/p/<perfil>/`; um
`MISE_HERMES_CHAVE` antigo no ambiente, que vence o arquivo; a linha do `.env`
editada à mão. O `make agente-status` diz de onde a chave veio.

**404 "Unknown or unconfigured profile"**. O gateway não conhece o perfil: ele foi
criado depois que o gateway subiu. Reinicie o gateway.

**429 "Too many concurrent runs"**. Passou do limite de turnos simultâneos do
servidor de API (`gateway.api_server.max_concurrent_runs`, 10 por padrão). O
cliente levanta `AgenteOcupada` com o `Retry-After` em `espera_s`: espere e tente
de novo, sem martelar.

**O Hermes se recusa a abrir a porta** ("placeholder or too short"). A chave tem
menos de 16 caracteres ou é um valor de exemplo (`changeme`, `***`). O script do
bootstrap gera 64 caracteres; uma linha antiga inutilizável fica no arquivo e a
nova vai no fim, que é a que vale.

**400 ou 403 da API do motor**. A API só atende `localhost` e `127.0.0.1` (400 com
outro `Host`, a defesa contra DNS rebinding) e só aceita escrita de navegador das
origens de `MISE_CORS` (403). Abrindo a interface pelo celular, na rede de casa
(`http://192.168.x.y:3000`), ponha essa origem em `MISE_CORS` antes de `make dev`.

**Trocar uma chave**. Apague a linha `API_SERVER_KEY` do `.env` e rode
`hermes/api_da_agente.sh` de novo. A do perfil vale na hora; a do padrão, só
depois de reiniciar o gateway.

**Logs**. O gateway roda como serviço do systemd do usuário:
`journalctl --user -u hermes-gateway`. Os de cada perfil ficam em
`~/.hermes/profiles/<perfil>/logs/` (`agent.log`, `errors.log`). Nunca cole
trecho de `.env` em lugar nenhum.

## O que o Hermes faz e o chat precisa saber

Lido no código do Hermes 0.21.4 (commit ee8a919f), em `gateway/platforms/`:

- **Fechar a conexão do `chat/stream` interrompe o turno** (`api_server.py:3468`).
  Quem não pode perder o turno quando a aba fecha consome o stream numa tarefa
  própria do backend.
- **`/v1/runs/{id}/events` aceita um assinante só.** Quando ele cai, o Hermes
  descarta o buffer (`api_server_runs.py:1055`) e uma nova assinatura dá 404. O
  run continua, e o resultado sai por `GET /v1/runs/{id}` (`output`, `usage`).
- **Parar vale também para o `chat/stream`**: todo evento traz o `run_id`, e
  `POST /v1/runs/{run_id}/stop` responde por ele enquanto o turno roda.
- **A sessão muda de id depois de uma compressão.** O `run.completed` e o
  `/api/sessions/{id}/messages` trazem o id novo (`api_server.py:3415`); adote-o.
- **O `system_message` entra no fim do system prompt a cada requisição**
  (`agent/turn_context.py:1222`). Mudá-lo no meio da sessão é editar o
  histórico: esfria o cache e, no Fable 5.1 e no Opus 5.5, invalida o raciocínio
  guardado. Mande sempre o mesmo, desde o primeiro turno da sessão.
- **Keepalive a cada 10 s** (`: keepalive`), então um minuto sem nenhum byte é
  conexão morta; é o prazo que o cliente usa.
- **`clarify` não trava o turno na API.** O toolset padrão da plataforma
  `api_server` é `hermes-api-server`, que tira o `clarify` (`toolsets.py:192-196`,
  `hermes_cli/platforms.py:35`); resolvendo os toolsets com a configuração do
  perfil, a API fica com `memory, mise, session_search, skills, todo, vision,
  web`. E mesmo que ele fosse ligado à mão, o servidor de API nunca instala um
  `clarify_callback` (`api_server.py:2170-2253`, também usado pelo `/v1/runs` em
  `api_server_runs.py:914`), e sem callback a ferramenta devolve erro na hora
  (`tools/clarify_tool.py:17,226`). Por isso o overlay não precisa desligar o
  `clarify`: na API, nenhum turno fica esperando uma resposta que não vem.

## Modelos: o que o Hermes manda para a Anthropic

Também lido no código (`agent/anthropic_adapter.py`) e conferido numa sonda com o
perfil de avaliação, em 2026-09-25:

- Para Claude 4.6 em diante, inclusive `claude-fable-5-1` e `claude-opus-5-5`:
  `thinking: {type: "adaptive", display: "summarized"}` e
  `output_config: {effort}`, com o esforço do perfil (`ultra` vira `max`,
  `minimal` vira `low`) (`anthropic_adapter.py:67,574-592`).
- `tool_choice` é sempre `auto` com ferramentas; nada força ferramenta, que os
  dois modelos recusariam com 400 (`anthropic_adapter.py:602`).
- Raciocínio de volta só no último turno do assistente; os anteriores saem sem
  os blocos de raciocínio (`anthropic_message_convert.py:593`). Sem o cabeçalho
  `thinking-binding-controls`: se a API recusar um bloco, o Hermes tira o
  raciocínio e tenta uma vez (`agent/turn_recovery.py:485`).
- Recusa (`stop_reason: refusal`) vira `content_filter`
  (`agent/transports/anthropic.py:38`): nunca repete no mesmo modelo, tenta uma
  vez a cadeia `fallback_providers` do `config.yaml` e, sem reserva, responde um
  texto em inglês começando com "⚠️" (`agent/turn_truncation.py:647,663`). O
  esforço da reserva vem de `agent.reasoning_overrides`.
- **Atenção com o Opus 5.5:** a lista de modelos em que não se desliga o
  raciocínio tem só `claude-fable` (`anthropic_adapter.py:93`). As tarefas
  auxiliares que pedem raciocínio desligado (o título da sessão, por exemplo)
  mandam `thinking: {type: "disabled"}` ao Opus 5.5 e levam 400; o Hermes tenta
  de novo sem o campo e segue, gastando duas chamadas perdidas. Um
  `reasoning_effort: none` no perfil faria o mesmo com cada turno.
