# Depois das correções da medição

Os 12 cenários, k = 1, `claude-opus-5` com esforço `max`, com tudo o que a
medição anterior apontou já corrigido: perfil sem ferramentas de arquivo, conta
completa do preço proposto, proveniência da receita da web, rendimento
implausível perguntado, auditor independente e busca só em endereço público.

| | antes | depois das primeiras correções | agora |
|---|---|---|---|
| Passaram | 8 de 12 | 9 de 12 | **11 de 12** |
| Números certos apagados | 18 | 10 | **0** |
| Latência por turno (p50 / p95) | 64 s / 142 s | 60 s / 119 s | 51.4 s / 167.5 s |
| Custo por conversa | não medido | não medido | US$ 0.61 |

Custo total da rodada: US$ 7.28 (referência de preços da API da Anthropic, tabela de 24/06/2026; gravação de cache com vida de 5 minutos).
Onde o dinheiro vai: gravação de cache US$ 4.15, saída
US$ 1.77, leitura de cache US$ 1.36, entrada
US$ 0.0010. Os tokens do stream conferem com o banco do Hermes,
sessão por sessão.

## A falha que sobrou, e o reteste

No caminho completo ela disse "vou cobrar 18 reais a porção", e a agente mostrou
a conta certa e perguntou de novo antes de gravar. Era efeito da regra que eu
tinha acabado de escrever ("só grave quando ela disser que decidiu"), que não
separava pergunta de decisão. O `SOUL.md` agora separa: pergunta pede a conta,
decisão é gravada.

`reteste-regra-de-decisao/` roda de novo os dois cenários que essa regra toca,
com o `SOUL.md` corrigido: 2 de 2. No caminho completo, a agente mostrou a conta
dos R$ 18,00, gravou o aceite e disse o risco uma vez. No preço abaixo do mínimo
ela mostrou o prejuízo e não gravou.

Um dos critérios do reteste estava estreito demais: exigia "lucro" ou "sobra", e
a agente disse "a senhora ganha R$ 3,09 por porção". O cenário passou a aceitar
"ganha"; as duas rodadas foram julgadas de novo com `--reavaliar`.
