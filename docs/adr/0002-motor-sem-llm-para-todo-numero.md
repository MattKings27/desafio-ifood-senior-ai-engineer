# ADR 0002: todo número sai de um motor sem LLM

## Contexto

O §2.4 do enunciado é aritmética com dinheiro, com custo unitário a partir da
planilha, custo por porção, preço mínimo, lucro e cenários. Modelo de linguagem
erra conta e erra com convicção, e aqui o erro vira prejuízo de quem vende.

A planilha tem armadilhas que uma divisão direta não vê. Em 6 dos 37 itens a
coluna de unidade mistura grandeza e embalagem ("balde 2kg", "un 500ml"), e as
alcaparras custam R$ 41,00/kg, e não R$ 82,00/kg
(`mise/tests/golden/test_despensa_real.py`, `ARMADILHAS`). A cobertura de
chocolate foi comprada como "1 un" por R$ 79,90, sem peso.

## Decisão

Todo valor em reais sai do pacote `mise`, que não importa cliente de modelo
nenhum.

- Dinheiro é `Decimal` (`mise/src/mise/dinheiro.py`), e cada valor vem com a
  `derivacao`, a conta escrita por extenso, como "1 × 2 kg = 2 kg; R$ 82,00 ÷ 2
  kg = R$ 41,00/kg" (`mise/tests/unit/test_despensa_json.py`).
- A unidade é normalizada antes da divisão. O que a planilha não diz não vira
  pergunta a ela. A cobertura sem peso ganha o peso de uma embalagem de
  supermercado com preço próximo (`mise/src/mise/embalagens.py`), marcado como
  estimativa e com a fonte, e ela corrige quando quiser; sem fonte, o item fica
  sem custo por grama, e a receita que pede o peso dele fica de fora.
- Medida caseira vira grama pela densidade do ingrediente (xícara de 240 ml,
  farinha de trigo a 0,53 g/ml, `mise/src/mise/unidades.py`); sem densidade, a
  conversão recusa. A incerteza se propaga, e acima de 8% o custo sai como faixa e
  o preço usa o topo (`mise/src/mise/cmv.py`).
- O mínimo sem prejuízo é `CMV ÷ 0,90`, arredondado para cima no centavo. Um CMV
  de R$ 8,68 dá mínimo de R$ 9,65, porque a R$ 9,64 ela receberia R$ 8,676
  (`mise/tests/unit/test_preco.py`). O lucro é `0,90·P − CMV`. Os três cenários
  saem de metas fixas de participação do ingrediente no preço (40%, 35% e 30%),
  e nenhum vem marcado como recomendado (`mise/src/mise/preco.py`).
- As ferramentas de custo e de preço leem a receita guardada pelo `receita_id`.
  Receita redigitada com outra quantidade é recusada (ADR 0007).
- A tela desenha o que o motor devolve. `webapp/src/lib/regras-da-interface.test.ts`
  reprova soma, multiplicação, divisão ou formatação sobre um valor em reais no
  código da interface.

## Consequências

- O mesmo pedido dá o mesmo número, com a conta à vista dela. Um teste de
  propriedade prova, para qualquer custo, lucro não negativo no mínimo exibido e
  prejuízo um centavo abaixo (`mise/tests/property/test_preco_invariantes.py`).
- Cada número custa uma chamada de ferramenta, com mais turnos e mais latência
  por resposta.
- O modelo precisa não fazer conta de cabeça. O `SOUL.md` pede, e o guard-rail
  garante (ADR 0004).

## Alternativas consideradas

- **Deixar o modelo calcular com a planilha no contexto.** Rápido de construir,
  errado na primeira armadilha de unidade, e sem como provar a conta depois.
- **Uma ferramenta de calculadora genérica.** O modelo ainda escolheria os
  números de entrada, que é onde o erro mora.
- **`float` em vez de `Decimal`.** Arredondamento binário em centavos, e o
  arredondamento para cima do mínimo deixaria de ser exato.
