# Rodada final da versão anterior

Os 12 cenários, duas execuções cada (k = 2), na agente real, com o código da
versão anterior à consultora como serviço (antes do chat na web, do catálogo por
`receita_id` e da busca na plataforma), `claude-opus-5` com esforço alto, estado
zerado a cada execução e a agente rodando fora do repositório.

| | |
|---|---|
| pass^2 (cenários certos nas duas) | **12 de 12** |
| Conversas certas | 24 de 24 |
| Respostas com jargão interno | 0 de 38 |
| Respostas com valor retirado pelo guard-rail | 0 de 38 |
| Latência por turno (p50 / p95) | 40,3 s / 132,7 s |
| Custo por conversa | US$ 0,45 |
| Custo da rodada | US$ 10,82 |

Preços da referência da API da Anthropic (tabela de 24/06/2026), gravação de
cache a 5 minutos. Os tokens somados das transcrições conferem com os que o
Hermes gravou no banco de sessões.

## O que mudou desde a matriz

Depois da matriz, percorri a interface e as transcrições como a Dona Maria
percorreria. O harness ganhou uma checagem que vale para toda resposta de todo
cenário: jargão interno ("motor", "portão", "APTO", "FALTA INFO", "BLOQUEADO",
"veredito", "CMV", "food cost") reprova. Na matriz, com o Opus 5 em esforço
alto, 42 de 95 respostas diziam "motor".

A primeira rodada com esse código (`primeira-rodada/`) deu 9 de 12:
as quatro conversas que falharam, falharam só por jargão, 5 das 38 respostas
dizendo "o motor calculou". A instrução nova proibia a palavra, mas o próprio
`SOUL.md` e as skills a usavam 12 vezes, e três descrições de ferramenta também.
O modelo repete o vocabulário que lê. Trocadas por "as ferramentas" e "a conta",
e com uma forma de citar a fonte ("pela conta da sua planilha"), esta rodada não
teve nenhuma.

Nas outras rodadas daquela versão, que parei antes do fim porque o código mudou
no meio, apareceram duas falhas de comportamento que também viraram correção:

- somar de cabeça os dois maiores itens parados ("mais de R$ 161"), que o
  guard-rail apagou: a soma agora vem pronta da ferramenta;
- confirmar uma compra sem dizer se ela cabe nos R$ 80: o resumo da avaliação
  agora diz que cabe no que resta.
