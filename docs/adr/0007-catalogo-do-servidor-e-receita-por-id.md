# ADR 0007: o catálogo é escrito só pelo servidor, e a receita anda pelo id

## Contexto

O §2.1 pede receitas reais da internet. Um modelo que "lembra" de uma receita
pode inventar o rendimento, trocar uma quantidade ou atribuir a um site o que o
site não publicou. Pior: se o modelo copia a receita de uma ferramenta para a
outra, cada cópia é uma chance de mudar um número, e o custo por porção passa a
ser o de uma receita que ninguém leu.

## Decisão

- **Só o código do servidor escreve no catálogo** (`mise/src/mise/catalogo.py`).
  A ferramenta `buscar_receita_na_web` recebe um endereço, busca a página pelo
  abridor seguro (`retrieval/src/retrieval/rede.py`: só endereço público, cada
  redirecionamento conferido de novo), lê a receita estruturada
  da página (JSON-LD ou microdata, sem adivinhar pelo HTML) e grava com a
  procedência: endereço canônico, site, autor, foto e tempos.
- **A receita ganha um `receita_id`** (para receita da web, os primeiros 16
  hexadecimais do SHA-256 do endereço canônico, que é único na tabela). As
  ferramentas de avaliação, custo e preço recebem o `receita_id` e leem a
  receita guardada. Uma receita redigitada com outra quantidade é recusada, com
  o que mudou e o recado para usar o id (`calcular_cmv`,
  `mise/src/mise/ferramentas/preco.py`).
- **A origem fica registrada:** descoberta, trazida por ela pelo endereço, vinda
  da conversa, ou ditada por ela. Receita ditada entra como ditada; receita
  digitada com um endereço que ninguém leu não vira "da internet".
- **Página sem receita estruturada não entra.** O extrator tenta JSON-LD e
  depois microdata; sem nenhum dos dois, a busca falha dizendo o que fazer, e a
  conversa segue com ela ditando a receita, se ela quiser.

## Consequências

- A receita que a tela mostra, a que a conversa cita e a que o custo usa são a
  mesma linha do banco, com o link da fonte.
- O modelo não precisa carregar a receita inteira entre turnos: passa o id.
- Receita de site sem dados estruturados fica de fora. É uma perda de cobertura
  aceita em troca de nunca apresentar uma receita que o servidor não leu.
- O que chega da web é dado, não instrução: o texto das páginas entra
  embrulhado como conteúdo não confiável (ADR 0004). Os casos adversariais de
  `evals/src/evals/adversarial.py` cobrem instrução escondida no JSON-LD de uma
  página, página que não é receita, receita digitada com um endereço que ninguém
  leu e quantidade trocada entre a conferência e o custo.

## Alternativas consideradas

- **O modelo escreve a receita no catálogo.** Mais simples, e abre a porta para
  receita inventada com cara de receita buscada.
- **Guardar só a URL e reler a página a cada custo.** A página muda ou sai do
  ar; o custo de ontem deixaria de ser reproduzível.
- **Heurística sobre o HTML.** Aumenta a cobertura e troca "não sei ler esta
  página" por uma lista de ingredientes errada.
