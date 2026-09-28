# Primeira rodada do agente como serviço

Os 21 cenários, uma execução cada (k = 1), no agente real, com o código do
agente como serviço (chat na web, catálogo por `receita_id`, busca na plataforma,
preço de referência conferido e confirmação da cozinha antes do aceite),
`claude-fable-5-1` com esforço medium, estado zerado a cada execução.

| | |
|---|---|
| Cenários aprovados | **15 de 21** |
| Respostas com jargão interno | 0 de 33 |
| Respostas com valor retirado pelo guard-rail | 3 de 33 |
| Latência por turno (p50 / p95) | 20,2 s / 56,5 s |
| Custo por conversa | US$ 0,50 |
| Custo da rodada | US$ 10,48 |

Preços da referência da API da Anthropic (tabela de 24/06/2026), gravação de
cache a 5 minutos. Os tokens somados das transcrições conferem com os que o
Hermes gravou no banco de sessões.

## O que falhou, e o que mudou por causa disso

- **O orçamento sem origem (3 cenários).** O agente escreveu "cabe nos R$ 80"
  e o guard-rail retirou o número, porque nenhuma saída de ferramenta da
  sessão dizia qual era o orçamento: `avaliar_receita` dizia se cabia, mas
  não com que valor comparou. O guard-rail estava certo em retirar. Agora
  `avaliar_receita` devolve o `orcamento` (o inicial, o gasto e o que resta),
  e o número passa a ter origem.
- **"Não gosto" gravado pela avaliação (1 cenário).** Ela disse que detesta
  fazer feijoada, e o agente gravou pela `registrar_avaliacao_da_receita`, que
  escreve o gosto na mesma tabela `gostos` que o portão lê. O efeito é o mesmo
  de `registrar_gosto`. O cenário passou a aceitar qualquer das duas, e o
  harness ganhou a alternativa `a|b` para isso.
- **Resposta de memória fora da cozinha (1 cenário).** "Qual a capital da
  França?" teve "Paris." como resposta, sem fonte. A regra do `SOUL.md` falava
  só de conhecimento de cozinha; agora vale para qualquer assunto: sem fonte,
  o agente diz que não sabe e oferece procurar.
- **Regex largo demais (1 cenário).** O prato de forno foi bloqueado certo, e
  a resposta dizia "o que dá para fazer é outra coisa: uma receita que vá só no
  fogão". O cenário proibia qualquer "dá para fazer"; agora ignora "o que dá
  para fazer" e "se dá para fazer", que não dizem que o prato bloqueado dá.
