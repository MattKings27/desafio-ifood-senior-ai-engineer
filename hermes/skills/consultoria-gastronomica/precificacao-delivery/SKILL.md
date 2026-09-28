---
name: precificacao-delivery
description: "Dar o preço preliminar quando ela perguntar quanto cobrar e, com a receita conferida, abrir o custo por porção, explicar a taxa e mostrar três caminhos para ela escolher."
version: 3.1.0
author: Sabor da Maria
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Preço, Custo, Margem, Delivery]
    related_skills: [elicitacao-restricoes, fechamento-cardapio]
---

# Precificação para o delivery

Transformar o custo em preço de venda, explicando a conta de um jeito que ela consiga repetir sozinha, e deixando ela escolher. São dois momentos, e o primeiro nunca espera o segundo.

## O preço preliminar, quando ela perguntar antes da conferência

"Quanto eu cobro?" merece resposta na hora, sem interrogatório antes. Se a receita já foi liberada e ela gosta de fazer, pule para o preço final. `estimar_preco_preliminar(receita_id)` devolve as linhas do custo (ingredientes, mão de obra, gás ou energia, embalagem), cada premissa com a origem (dela, um padrão público com fonte, ou faltando), o piso sem prejuízo, o mínimo só com o ingrediente e três preços com a taxa e o lucro. Diga que é preliminar, diga as premissas que mais pesam e que ela pode trocar as de padrão pelas dela, e termine com uma pergunta só: se ela quer seguir para o preço final. Se o prato ainda não tem receita no catálogo, traga uma pela pesquisa de receitas e diga qual usou. A estimativa não grava nada.

Se a ferramenta recusar, a recusa é informação: receita que ela não consegue fazer não tem preço, e o que segura a receita vem com o motivo. Se o que falta é o gosto dela ou uma resposta da cozinha, faça essa pergunta, uma só; peso, medida, quantidade e preço nunca são pergunta. Quando `avaliar_receita` disser que falta comprar um ingrediente sem preço, chame `buscar_preco_na_web(ingrediente)`: o servidor procura o preço médio em São Paulo nos supermercados, guarda com as fontes, e a próxima avaliação já conta com ele. Se a busca não achar, o item fica sem preço e a receita fica de fora por isso: diga isso a ela, sem pedir o preço e sem prometer procurar de outro jeito. A compra com preço de referência entra na conta dita como preço médio em São Paulo, com os mercados e a data, e o rendimento que a receita não diz vem como estimativa (porções de 350 g): diga as duas coisas, e que o número dela vale mais se ela quiser corrigir.

## O preço final, depois da conferência

Só com a receita liberada pela conferência e o gosto dela confirmado; antes disso as ferramentas abaixo recusam, e a recusa traz o que falta. O gosto e a cozinha se perguntam, um de cada vez; o peso de uma linha, a medida, a quantidade e o preço vêm pré-determinados, com a fonte (a tabela de medidas do IBGE, o preço de referência, a média de preços de São Paulo), e não são pergunta. Diga que são estimativa, de onde vieram e que ela pode corrigir; se ela disser o número dela, grave como na elicitação (o peso de uma linha com `avaliar_receita`, o `receita_id` e a linha com `peso`), porque o dela vale mais. A ordem importa:

1. `calcular_cmv(receita_id)` dá o custo de ingrediente de uma porção, linha a linha. Mostre as duas ou três linhas que mais pesam. "(comprar)" é o que falta comprar, pelo que o prato consome; "(comprado)" é o que ela já comprou, pelo preço que pagou. Quando vier `e_faixa`, diga a faixa e o motivo (medida caseira varia), e que o preço usa o topo.
2. Explique a taxa antes do preço: a plataforma fica com 10%, então o mínimo sem prejuízo é o custo dividido por 0,90. O campo `explicacao_da_taxa` já vem com os números do prato.
3. `cenarios_preco(receita_id)` mostra três caminhos, cada um com o preço, o que chega para ela e o que sobra. Diga a troca em uma frase (o mais barato vende mais e ganha menos por prato) e não diga qual é melhor: ela conhece a clientela.
4. Quando ela propuser um preço, `testar_sensibilidade(preco, receita_id)` mostra a conta daquele preço e quanto de alta no insumo ele aguenta. Pergunte se fica.
5. Quando ela decidir, `registrar_decisao(prato, "aceito", preco=<o dela>)`. Pode ser um preço fora dos três. Abaixo do mínimo, a resposta traz `da_prejuizo` e quanto ela perde por prato: diga uma vez e respeite.

O aceite segue o checklist de produção do prato: `avaliar_receita` diz se ela já pode aceitar (`pode_aceitar`) e o que falta (`falta_para_aceitar`). O que toda cozinha tem (fogão, panela funda, refogar) é suposto até ela confirmar, e só se pergunta agora, quando ela escolheu o preço: se veio `confirmar_a_cozinha`, ou se `registrar_decisao` recusar trazendo a `pergunta` de confirmar a cozinha, faça essa pergunta do jeito que veio, uma pergunta só, e não contorne a recusa. Com o sim dela, grave `registrar_resposta(tipo="cozinha", campo=<receita_id>, resposta="tem")` e registre a decisão de novo, com o mesmo preço. Se ela disser que não tem um dos itens, grave esse item com `nao_tem`, como na elicitação, e conte o que muda no prato. Porções, pesos, quantidades e preços já vêm pré-determinados, com a fonte: não são pergunta. Quando ela perguntar de um deles, diga que é estimado, de onde veio e que ela pode mudar.

Mostre a matemática uma vez, escrita, com os números que as ferramentas devolveram, para ela conseguir refazer sozinha: o mínimo como "o custo ÷ 0,90 = o mínimo (arredondado para cima)" e, para cada caminho, ou ao menos para o que ela escolher, "0,90 × o preço − o custo = o lucro". Dar só os resultados não ensina a conta, e nenhum número sai da sua cabeça.

## De onde vem cada linha

Se ela perguntar, `custo_unitario(ingrediente)` traz o custo por quilo ou litro com a conta da planilha, `converter_medida_culinaria` mostra quanto pesa uma xícara ou colher daquele ingrediente, `consultar_precos_de_mercado` lista as cotações que ela deu e `consultar_gostos` o que ela disse de cada prato. A embalagem não está no custo de ingrediente; na estimativa preliminar ela é uma linha própria. O cliente paga o preço e chega para ela 0,90 dele: diga os dois.

## Exemplo

"O custo de ingrediente de uma porção é ⟨total⟩, e quase tudo é o frango. A plataforma fica com 10%, então abaixo de ⟨mínimo⟩ a senhora paga para trabalhar. Qual desses três caminhos faz mais sentido para a senhora?"
