# Rodada da entrega

Os 23 cenários, uma execução cada (k = 1), no agente real, com o código da
entrega em que à Dona Maria só se pergunta o gosto e a cozinha, o preço do que
falta é a média de mercados de São Paulo e a cotação de um ingrediente novo é
feita na hora pelo servidor. Modelo `claude-fable-5-1` com esforço medium,
estado zerado a cada execução.

| | |
|---|---|
| Cenários aprovados | **20 de 23** |
| Respostas com jargão interno | 0 de 37 |
| Respostas com valor retirado pelo guard-rail | 1 de 37 |
| Latência por turno (p50 / p95) | 19,1 s / 85,9 s |
| Custo por conversa | US$ 0,53 |
| Custo da rodada | US$ 12,30 |

Preços da referência da API da Anthropic (tabela de 24/06/2026), gravação de
cache a 5 minutos. Os tokens somados das transcrições conferem com os que o
Hermes gravou no banco de sessões.

## O que falhou, e o que mudou por causa disso

No caminho até a decisão, o agente sugeriu dois preços de exemplo com número,
que nenhuma conta sustentava, e o guard-rail retirou os dois antes de a
resposta chegar a ela. O guard-rail fez o trabalho dele, e o `SOUL.md` passou a
dizer que nem como exemplo se sugere preço com número: o agente oferece fazer a
conta do preço que ela disser.

Nos outros dois cenários a resposta estava certa e o cenário é que recusava a
frase. Perguntada de onde veio o preço, a resposta disse que era estimativa e
ofereceu anotar o preço dela ("me diga e eu anoto o seu preço, que vale mais que
a média"), e o cenário só aceitava "corrigir", "mudar" ou "trocar". Sem fogão, a
resposta disse "o que dá para fazer é procurar uma receita de micro-ondas", que
não diz que o prato bloqueado dá. Os dois cenários passaram a aceitar essas
frases, sem aceitar a pergunta de preço nem o prato bloqueado como possível.

O reteste dos três, com essas correções, e o cenário novo da conversa que o
botão "Responder agora" começa estão em [`../reteste-da-entrega/`](../reteste-da-entrega/LEIA.md).
