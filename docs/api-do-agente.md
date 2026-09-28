# A API do agente

O agente é um serviço da plataforma, não uma página. Qualquer tela conversa
com ele pela mesma API HTTP, e a resposta chega por SSE, evento por evento,
com os cards e o que o agente está fazendo. Quem é dono do turno é o
backend (`gateway`, FastAPI): o navegador pode fechar a aba, voltar e continuar
de onde parou. A decisão está no
[ADR 0011](adr/0011-agente-como-servico.md).

As formas abaixo são as de [`contratos/web/`](../contratos/web/LEIA.md), que os
testes dos dois lados leem: o backend confere que as rotas devolvem aquelas
formas, e a interface usa os mesmos arquivos como fixture.

## Endereço, envelope e erros

- A API escuta em `http://127.0.0.1:8777` (`MISE_HTTP_HOST`, `MISE_HTTP_PORT`), e
  as rotas ficam em `/api`. O navegador chama `/motor/...`, que o Next repassa
  para `/api/...` (`webapp/next.config.ts`).
- Toda resposta vem num envelope: `{ok, dados, erro, categoria, pergunta}`. O
  conteúdo útil fica em `dados`.
- Só `localhost` e `127.0.0.1` são aceitos no cabeçalho `Host` (mais os nomes de
  `MISE_HOSTS`). Escrita que vem de navegador precisa de uma origem de
  `MISE_CORS` (padrão `http://localhost:3000` e `http://127.0.0.1:3000`). A API
  não tem login: ela serve a máquina dela.

| Situação | HTTP | `categoria` | `erro` |
|---|---|---|---|
| Conversa ou turno que não existe | 404 | `ausente` | "Essa conversa não existe mais." |
| Mensagem vazia ou com mais de 4.000 caracteres | 422 | `uso` | "A mensagem está vazia." |
| Já há um turno respondendo nesta conversa | 409 | `ocupado` | "Ainda estou respondendo a mensagem anterior.", com `dados.turno_id` |
| Mais de 10 mensagens em 60 s na mesma conversa | 429 | `regra` | "Muitas mensagens em pouco tempo...", com `Retry-After` |
| Escrita vinda de outra origem | 403 | `regra` | "Este pedido não veio da tela do Sabor da Maria." |
| Corpo com mais de 1 MiB | 413 | `regra` | "O pedido veio grande demais." |

Duas respostas ficam fora do envelope: `Host` desconhecido recebe 400 do
middleware do Starlette, e um corpo que não passa na validação do esquema
(`id_cliente` ausente, por exemplo) recebe o 422 padrão do FastAPI,
`{"detail": [...]}`.

## Conversas

| Método e rota | Corpo | Resposta em `dados` |
|---|---|---|
| `GET /api/conversas` | | `{atual, conversas: [{id, titulo, previa, atualizado_texto, respondendo}]}` |
| `POST /api/conversas` | `{titulo?}` | a conversa nova, completa (HTTP 200), que passa a ser a atual |
| `GET /api/conversas/{id}` | | `{id, titulo, atual, turno_em_andamento, mensagens}` |
| `PATCH /api/conversas/{id}` | `{titulo?, atual?}` | `{id, titulo, atual}` |
| `DELETE /api/conversas/{id}` | | `{apagada, atual}`; para o turno que estiver rodando |

A lista ([`conversas.json`](../contratos/web/conversas.json)):

```json
{
  "atual": "cv-7f3a",
  "conversas": [
    {
      "id": "cv-7f3a",
      "titulo": "Arroz com frango",
      "previa": "Gravado. Arroz com frango, R$ 18,00 a porção.",
      "atualizado_texto": "hoje, 15:02",
      "respondendo": false
    }
  ]
}
```

A conversa ([`conversa.json`](../contratos/web/conversa.json)) traz as últimas
400 mensagens. Cada mensagem tem `papel` (`senhora`, ou `consultora` quando é
o agente) e `partes`, que são texto (`{tipo: "texto", texto}`) ou card
(`{tipo: "cartao", cartao}`). A mensagem do agente traz também o `estado` do
turno, quantos valores o guard-rail retirou (`retirados`) e as atividades já no
passado ("calculei o custo por porção"). O título automático sai da primeira mensagem; quando ela
renomeia, o título dela fica.

## Turnos

| Método e rota | Corpo | Resposta em `dados` |
|---|---|---|
| `POST /api/conversas/{id}/turnos` | `{texto, contexto?, acao?, id_cliente}` | HTTP 202 `{turno_id}` |
| `GET /api/conversas/{id}/turnos/{turno_id}` | | `{turno_id, estado, ultimo_seq, iniciado_texto}` e, no fim, `terminado_texto` e `erro` |
| `GET /api/conversas/{id}/turnos/{turno_id}/eventos` | | o fluxo SSE (abaixo) |
| `POST /api/conversas/{id}/turnos/{turno_id}/parar` | | HTTP 202 `{turno_id, estado: "cancelando"}`, ou 200 com o estado, se o turno já tinha terminado |

O pedido e as respostas de exemplo
([`conversa-turno.json`](../contratos/web/conversa-turno.json)):

```json
{
  "pedido": {
    "texto": "Tenho forno.",
    "contexto": { "tela": "receita", "tipo": "receita", "id": "arroz-com-frango", "rotulo": "Arroz com frango" },
    "acao": { "tipo": "responder", "tipo_pergunta": "equipamento", "campo": "forno", "resposta": "sim" },
    "id_cliente": "u-5e1d"
  },
  "resposta_202": { "turno_id": "t-88c1" },
  "resposta_409": { "turno_id": "t-88c0" }
}
```

- **Idempotência.** O `id_cliente` identifica o envio. Mandar de novo o mesmo
  `id_cliente` devolve o mesmo `turno_id` enquanto o turno está vivo ou depois
  que ele terminou bem; um turno que falhou abre um novo, sem repetir a
  mensagem dela.
- **Um turno por vez.** Com um turno em andamento, o POST devolve 409 com o
  `turno_id` dele, e a tela se pendura nesse turno em vez de mandar outro.
- **Parar.** O backend pede ao Hermes para parar a execução; se em 10 s ela não
  parou, cancela a tarefa. O turno termina em `turno.cancelado`, ou em
  `turno.concluido` se o Hermes já tinha terminado.
- **Limites.** 4.000 caracteres por mensagem, 10 mensagens por minuto por
  conversa, 900 s por turno (passou disso, o turno falha com a categoria
  `tempo`).

## O fluxo de eventos (SSE)

`GET .../turnos/{turno_id}/eventos` devolve `text/event-stream`. Cada evento é
um quadro `id: <seq>` com uma linha `data:` em JSON; não há campo `event:`, o
tipo vai no próprio JSON. Todo evento tem `seq`, `turno_id` e `tipo`.

- O fluxo abre com o comentário `: conectado` e manda `: keepalive` a cada 10 s
  de silêncio.
- **Retomada.** O cliente manda `Last-Event-ID` ou `?desde=<seq>` e recebe só o
  que veio depois. A tela usa `?desde=`, reconecta com espera crescente (1, 2, 5
  e 10 s) e reabre sozinha quando a aba volta a ficar visível ou a rede volta.
- **Retenção.** Os eventos ficam na memória do backend durante o turno e por
  600 s depois do fim. Mais tarde, a retomada recebe só o evento final,
  reconstruído do banco. Sem nada mais a mandar, a resposta é 204.

| `tipo` | Campos | Quando |
|---|---|---|
| `turno.iniciado` | `conversa_id`, `mensagem_id`, `id_cliente` | primeiro evento |
| `acao.resultado` | `ok`, `texto`, `cartao?` | o botão de um card foi aplicado (ver Ações) |
| `atividade.iniciada` | `atividade_id`, `ferramenta`, `rotulo`, `rotulo_feito` | o agente chamou uma ferramenta; o rótulo é em português e sem valor |
| `atividade.concluida` | `atividade_id`, `ok` | a ferramenta terminou |
| `cartao` | `cartao_id`, `tipo_cartao`, `ref`, `dados`, `gerado_texto` | um card para desenhar |
| `texto.parcial` | `delta` | o rascunho, com os valores em reais mascarados |
| `texto.comentario` | `texto` | não é mais emitido, porque o texto entre ferramentas é bastidor; a tela ainda o entende |
| `estado.alterado` | `recursos` | uma escrita mudou dados; a tela recarrega o que depende deles |
| `texto.final` | `texto`, `retirados` | o texto conferido, que substitui o rascunho |
| `sugestoes` | `opcoes: [{rotulo, texto, acao?}]` | respostas rápidas para o próximo passo |
| `turno.concluido`, `turno.cancelado` | | fim |
| `turno.falhou` | `categoria` (`rede`, `tempo` ou `consultora`, que é falha do lado do agente), `mensagem`, `interrompido?` | fim com erro |

O turno de exemplo ([`chat-eventos.jsonl`](../contratos/web/chat-eventos.jsonl)),
com o rascunho mascarado e o texto final conferido:

```json
{"seq": 1, "turno_id": "t-88c1", "tipo": "turno.iniciado", "conversa_id": "cv-7f3a"}
{"seq": 2, "turno_id": "t-88c1", "tipo": "atividade.iniciada", "atividade_id": "at-1", "ferramenta": "avaliar_receita", "rotulo": "conferindo se a senhora consegue fazer arroz com frango", "rotulo_feito": "conferi se a senhora consegue fazer arroz com frango"}
{"seq": 3, "turno_id": "t-88c1", "tipo": "atividade.concluida", "atividade_id": "at-1", "ok": true}
{"seq": 4, "turno_id": "t-88c1", "tipo": "cartao", "cartao_id": "k-2", "tipo_cartao": "viabilidade", "ref": {"rota": "/api/receitas/arroz-com-frango"}, "gerado_texto": "conta de hoje, 15:10", "dados": {"slug": "arroz-com-frango", "veredito_rotulo": "Dá pra fazer"}}
{"seq": 5, "turno_id": "t-88c1", "tipo": "texto.parcial", "delta": "Dá pra fazer. A porção sai  de ingrediente"}
{"seq": 6, "turno_id": "t-88c1", "tipo": "estado.alterado", "recursos": ["receitas", "perfil"]}
{"seq": 7, "turno_id": "t-88c1", "tipo": "texto.final", "texto": "Dá pra fazer. A porção sai R$ 2,47 de ingrediente.", "retirados": 0}
{"seq": 8, "turno_id": "t-88c1", "tipo": "sugestoes", "opcoes": [{"rotulo": "Quanto cobrar?", "texto": "Quanto eu cobro por porção?"}]}
{"seq": 9, "turno_id": "t-88c1", "tipo": "turno.concluido"}
```

### A máscara no rascunho

Enquanto o modelo escreve, nenhum valor em reais sai para a tela: cada "R$ 2,47"
e cada "24 reais" do rascunho vira o caractere ``, que a tela desenha como
"R$ ···". A cauda que ainda pode virar valor ("R", "R$ 7,", "4,5 rea") fica
retida até se decidir. O `texto.final` só sai quando o turno termina bem, já com
cada valor conferido contra as saídas do motor e as palavras dela; o que não tem
origem vira "[valor retirado]", e `retirados` diz quantos foram. Um turno
cancelado ou que falhou guarda o rascunho mascarado, para sempre mascarado. A
decisão está no [ADR 0010](adr/0010-mascara-durante-o-streaming.md).

## Cards

Um card é `{cartao_id, tipo_cartao, ref: {rota, parametros}, gerado_texto,
dados}`. São 15 tipos, um exemplo de cada em
[`contratos/web/cartoes/`](../contratos/web/cartoes/custo_porcao.json):

| Ferramenta que o agente chamou | `tipo_cartao` | Rota que dá os dados |
|---|---|---|
| `diagnostico_despensa` | `despensa_resumo` | `/api/visao-geral` |
| `custo_unitario`, `atualizar_despensa` | `ingrediente` | `/api/despensa/itens/{id}` |
| `consultar_orcamento`, `registrar_compra`, `registrar_preco_mercado` | `orcamento` | `/api/orcamento` |
| `buscar_receita_na_web` | `receita` | `/api/receitas/{slug}` |
| `avaliar_receita` | `viabilidade` | `/api/receitas/{slug}` |
| `comparar_candidatas` | `comparacao` | `/api/receitas?aba=pode_fazer` |
| `registrar_avaliacao_da_receita` | `avaliacao_da_receita` | `/api/receitas/{slug}/avaliacao` |
| `proxima_pergunta` | `pergunta` | nenhuma, o plano de perguntas é refeito |
| `registrar_resposta` (equipamento, técnica ou rotina) | `cozinha_atualizada` | `/api/perfil` |
| `calcular_cmv` | `custo_porcao` | `/api/receitas/{slug}/custo` |
| `cenarios_preco` | `cenarios` | `/api/precos` |
| `testar_sensibilidade` | `ponto_de_preco` | `/api/preco-em` |
| `estimar_preco_preliminar` | `preco_preliminar` | `/api/receitas/{slug}/estimativa` |
| `registrar_decisao` | `decisao` | `/api/cardapio` |
| `consultar_conhecimento` | `fontes` ("De onde eu tirei isso") | nenhuma, a busca é refeita |

- Os dados do card não vêm da resposta da ferramenta. Quando a ferramenta
  termina bem, o backend chama a própria rota da tela, no mesmo processo, e usa
  o `dados` dela: o card mostra exatamente o que a tela mostraria. Rota que
  recusa não gera card; rota que ainda não existe gera o card com os dados
  mínimos do motor.
- Dentro de um turno, o mesmo card sai uma vez; se os dados mudam, ele sai de
  novo com o mesmo `cartao_id`, e a tela troca.
- Card com dinheiro traz `gerado_texto` ("conta de hoje, 15:10"). No histórico,
  a tela o mostra como uma foto datada, com o botão "Refazer a conta".
- A tela ignora `tipo_cartao` que não conhece.

## Ações

O botão de um card manda uma `acao` no próprio POST do turno. O backend aplica a
ação antes de chamar o agente, emite `acao.resultado` e, se deu certo,
`estado.alterado`; o agente recebe uma nota entre colchetes dizendo o que
foi feito, sem valor em reais.

| `acao.tipo` | Campos | O que faz |
|---|---|---|
| `responder` | `tipo_pergunta`, `campo`, `resposta`, `receita_id?` | grava a resposta de uma pergunta da cozinha, da rotina ou do gosto; com `receita_id`, a correção dela num valor da própria receita |
| `decidir` | `prato`, `decisao`, `preco?` | grava a decisão sobre um prato; o mesmo `id_cliente` não grava duas vezes |
| `avaliar` | `receita_id`, `gosta?`, `estrelas?`, `notas?` | grava gosto, estrelas e notas da receita |

Ação desconhecida, inválida ou recusada pelo motor ou pelo auditor volta com
`ok: false` e um texto para ela, sem derrubar o turno.

## Contexto da tela

Cada tela manda, junto com a primeira mensagem, o que ela está vendo:
`contexto: {tela?, tipo, id, rotulo?}`. O `tipo` pode ser `ingrediente`,
`pendencia`, `receita`, `prato`, `equipamento`, `tecnica`, `restricao` ou
`tela`.

O backend trata o contexto como dado do navegador, não confiável: só guarda o
que consegue resolver no dossiê (o item existe, a receita existe), usa o nome
que ele mesmo tem, tira qualquer valor em reais e descarta em silêncio o que não
reconhece. O que chega ao agente é uma linha depois da mensagem dela, por
exemplo `[a senhora está vendo a receita Arroz com frango]`, e a instrução fixa
da web explica a ele o que são essas linhas.

## Estado do agente

`GET /api/chat/estado` sempre responde 200:
`{disponivel, perfil, modelo, motivo?, aviso?}`, com cache de 5 s. A tela usa
para mostrar a faixa de "O agente está fora do ar agora" e, nas Preferências, o
modelo em uso. O `aviso` aparece quando o servidor MCP do perfil do Hermes
aponta para outro dossiê que não o da API.

## Como o backend fala com o Hermes

Só `gateway/src/gateway/hermes_cliente.py` fala com o servidor de API do Hermes
(`MISE_HERMES_URL`, padrão `http://127.0.0.1:8642`, prefixo `/p/<perfil>`). A
chave vem de `MISE_HERMES_CHAVE` ou da `API_SERVER_KEY` do `.env` do perfil, e
nunca chega ao navegador.

| Chamada | Para quê |
|---|---|
| `POST /p/<perfil>/api/sessions` | abrir a sessão do Hermes de uma conversa |
| `POST /p/<perfil>/api/sessions/{id}/chat/stream` | mandar a mensagem e ler o fluxo do turno |
| `POST /p/<perfil>/v1/runs/{run_id}/stop` | parar o turno |
| `GET /health` e `GET /p/<perfil>/api/sessions?limit=1` | o estado do agente |

- O POST do turno responde 202 assim que a tarefa do turno começa. A conexão com
  o Hermes pertence a essa tarefa, não ao navegador: fechar a aba não cancela
  nada, e o Hermes interromperia o turno se a conexão dele caísse.
- A instrução da web (`INSTRUCAO_DA_WEB`, em `gateway/src/gateway/conversa.py`)
  é a mesma em todo turno, para não mexer no histórico que o modelo já leu.
- Passando de 150.000 tokens de contexto (`MISE_CONVERSA_LIMITE_TOKENS`), a
  conversa segue numa sessão nova do Hermes, com uma nota de retomada; os fatos
  continuam no dossiê.
- Se o backend reinicia no meio de um turno, na volta o turno vira
  `interrompido` e a conversa ganha uma mensagem dizendo isso.

## Descoberta de receitas em segundo plano

A plataforma também chama o agente sozinha, para encher a grade de receitas
sem ela pedir uma por uma (`gateway/src/gateway/descoberta.py`).

| Método e rota | Resposta |
|---|---|
| `POST /api/receitas/descoberta` | 202 com `{execucao_id, estado, texto, eventos}`; 409 `ocupado` com a rodada que já está rodando; 501 `regra` com a busca automática desligada |
| `GET /api/receitas/descoberta/eventos?execucao=` | SSE com `progresso`, `receita.encontrada` (com a aba onde a receita cai) e `fim`, com a mesma retomada por `?desde=` ou `Last-Event-ID` |

- **O pedido é fixo.** Uma execução nova do Hermes (`POST /v1/runs`, numa
  sessão só dela) com as instruções de `hermes/prompts/descoberta.md`: pegar a
  pauta (`pauta_de_descoberta`: primeiro os pratos clássicos que a despensa
  dela cobre, depois o dinheiro parado), fazer até 8 pesquisas, trazer até 20
  páginas por `buscar_receita_na_web`, até 3 de cada pesquisa, primeiro dos
  sites de receita mais populares, e parar, sem conversar com ninguém. O
  esforço de raciocínio dessa tarefa é baixo.
- **Quem escreve no catálogo é o servidor**, como na conversa; a receita que
  entrou durante a rodada fica marcada com a origem "descoberta".
- **Limites de verdade:** passou de 8 pesquisas, 20 páginas ou cerca de 16
  minutos (35 segundos por pesquisa ou página), o backend pede ao Hermes para
  parar. Uma rodada por vez, e ela espera um turno
  de conversa em andamento terminar.
- **Chave de desligar.** Cada rodada custa chamadas ao modelo:
  `SABOR_DESCOBERTA=ligada` liga, e o `make dev` liga. Desligada, a rota
  responde 501 com o motivo, e a tela abre a conversa com o pedido escrito. Os
  testes e o CI rodam desligados.
- **Quem dispara é a tela:** o botão "Procurar mais receitas" e a primeira
  visita com o catálogo vazio. Ler a grade nunca dispara nada.

## Um turno pela linha de comando

Com a API no ar (`make dev` ou `make api`):

```bash
API=http://127.0.0.1:8777/api
conversa=$(curl -s -X POST "$API/conversas" -H 'Content-Type: application/json' -d '{}' \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["dados"]["id"])')
turno=$(curl -s -X POST "$API/conversas/$conversa/turnos" -H 'Content-Type: application/json' \
  -d '{"texto": "O que eu tenho parado na despensa?", "id_cliente": "linha-de-comando-1"}' \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["dados"]["turno_id"])')
curl -N "$API/conversas/$conversa/turnos/$turno/eventos"
```

Sem cabeçalho `Origin`, o pedido não é de navegador, e a regra de origem não se
aplica. Uma gravação real de dois turnos, com a retomada por `Last-Event-ID`
no meio, está em
[`docs/transcricoes/chat-web/`](transcricoes/chat-web/LEIA.md).
