# Rodada final do agente como serviço

Os 21 cenários, uma execução cada (k = 1), no agente real, com o código desta
entrega, `claude-fable-5-1` com esforço medium, estado zerado a cada execução.
A rodada dividiu a máquina com a suíte de e2e, que roda ao mesmo tempo.

| | |
|---|---|
| Cenários aprovados | **21 de 21** |
| Respostas com jargão interno | 0 de 33 |
| Respostas com valor retirado pelo guard-rail | 0 de 33 |
| Latência por turno (p50 / p95) | 24,0 s / 75,5 s |
| Custo por conversa | US$ 0,62 |
| Custo da rodada | US$ 12,97 |

Preços da referência da API da Anthropic (tabela de 24/06/2026), gravação de
cache a 5 minutos. Os tokens somados das transcrições conferem com os que o
Hermes gravou no banco de sessões.

## O que mudou desde a primeira rodada

O que a [primeira rodada](../primeira-rodada-do-agente-como-servico/LEIA.md)
ensinou: `avaliar_receita` devolve o orçamento com que comparou a compra, o
agente diz que não sabe quando a pergunta foge da cozinha, e dois cenários
deixaram de reprovar frases certas. Entre as duas rodadas também entraram a
leitura das linhas com medida entre o número e a unidade ("1/2 de xícara") e
12 preços de referência conferidos, que tiraram a pergunta de preço de 8 das
13 receitas do catálogo que ainda perguntavam.
