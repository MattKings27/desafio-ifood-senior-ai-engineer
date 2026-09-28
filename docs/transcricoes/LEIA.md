# Transcrições do agente

Conversas reais do agente rodando no Hermes, gravadas pelo harness de
cenários (`make evals-agente`, código em `evals/src/evals/agente/`). Cada
`execucao-N.json` guarda os turnos de uma conversa: o que ela disse, cada
ferramenta chamada com entrada e saída, a resposta, a latência e os tokens. O
`resumo.json` de cada pasta junta a rodada: cenários aprovados, latência p50 e
p95, tokens e custo. Cada pasta tem um `LEIA.md` com o que falhou e por quê.

Estas conversas também são teste: o guard-rail numérico relê todas elas
(`hermes/plugins/guardrail-numerico/test_guardrail.py`) e prova que a conferência
atual, que também lê valor escrito por extenso ("24 reais"), não retira nenhum
valor que a versão medida deixava passar.

## As rodadas, em ordem

As oito primeiras são da versão anterior do produto, com o modelo da época; as
do agente como serviço vêm depois. A medição final fica no README.

| Pasta | O que é | Modelo e esforço | Cenários aprovados |
|---|---|---|---|
| [`linha-de-base/`](linha-de-base/LEIA.md) | primeira execução real, 1 cenário | Opus 5, máximo | 1 de 1 |
| [`antes-das-correcoes/`](antes-das-correcoes/LEIA.md) | 12 cenários, k = 1 | Opus 5, máximo | 8 de 12 |
| [`depois-das-primeiras-correcoes/`](depois-das-primeiras-correcoes/LEIA.md) | 12 cenários, k = 1 | Opus 5, máximo | 9 de 12 |
| [`depois-das-correcoes-da-medicao/`](depois-das-correcoes-da-medicao/LEIA.md) | 12 cenários, k = 1, e um reteste | Opus 5, máximo | 11 de 12 |
| [`incidente-servidor-fora-do-ar/`](incidente-servidor-fora-do-ar/LEIA.md) | registro de falha de infraestrutura, não é medida da agente | Opus 5 | 4 de 12 |
| [`matriz/`](matriz/LEIA.md) | 12 cenários, k = 5, três configurações, e um reteste | Opus 5 alto e máximo, Sonnet 5 alto | 11, 9 e 5 de 12 |
| [`rodada-final-da-versao-anterior/`](rodada-final-da-versao-anterior/LEIA.md) | 12 cenários, k = 2 | Opus 5, alto | 12 de 12 |
| [`chat-web/`](chat-web/LEIA.md) | dois turnos pela API da web, evento por evento | Opus 5, alto | amostra |
| [`primeira-rodada-do-agente-como-servico/`](primeira-rodada-do-agente-como-servico/LEIA.md) | 21 cenários, k = 1 | Fable 5.1, medium | 15 de 21 |
| [`rodada-final-do-agente-como-servico/`](rodada-final-do-agente-como-servico/LEIA.md) | 21 cenários, k = 1, antes da regra de perguntar só o gosto e a cozinha | Fable 5.1, medium | 21 de 21 |
| [`rodada-da-entrega/`](rodada-da-entrega/LEIA.md) | 23 cenários, k = 1, com o código da entrega | Fable 5.1, medium | 20 de 23 |
| [`reteste-da-entrega/`](reteste-da-entrega/LEIA.md) | as 3 que falharam e a conversa do "Responder agora" | Fable 5.1, medium | 4 de 4 |
| [`entrevista-da-cozinha/`](entrevista-da-cozinha/LEIA.md) | a conversa do "Responder agora", com o catálogo primeiro | Fable 5.1, medium | 1 de 1 |

Os números de cada rodada estão no `resumo.json` da pasta; os da amostra do chat
da web, no `LEIA.md` dela.

## Redação

As conversas foram gravadas numa máquina de desenvolvimento, e a saída das
ferramentas trazia caminhos absolutos dessa máquina e o nome de um canal de
mensagens que saiu do escopo do projeto. Antes de versionar,
`scripts/redigir_transcricoes.py` troca cada um por um marcador:

| Marcador | O que substitui |
|---|---|
| `<repo>` | a raiz de uma cópia do repositório; o resto do caminho fica |
| `<home>` | a pasta pessoal e outras pastas locais fora do repositório; o perfil do Hermes fica legível (`<home>/.hermes/profiles/...`) e qualquer outro caminho da pasta pessoal vira `<home>/…` |
| `[canal]` | o nome do canal de mensagens, inclusive dentro de páginas de receita que o agente leu |

Nada mais muda: o JSON é regravado no mesmo formato, e um teste
(`scripts/tests/test_redigir_transcricoes.py`) prova que a redação troca só
esses trechos e que nenhuma transcrição do repositório ficou sem redigir. Na
primeira passada foram 442 trechos em 122 arquivos. Duas pastas também mudaram
de nome, para o nome dizer o que a rodada foi.

Depois de gravar uma rodada nova:

```bash
mise/.venv/bin/python scripts/redigir_transcricoes.py             # redige docs/transcricoes
mise/.venv/bin/python scripts/redigir_transcricoes.py --conferir  # só confere
```
