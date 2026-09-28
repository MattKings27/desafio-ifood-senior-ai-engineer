---
name: fechamento-cardapio
description: "Conferir se os pratos que ela aceitou formam um cardápio que a cozinha, o tempo e os R$ 80,00 dela aguentam, e registrar as compras que ela fizer."
version: 3.1.0
author: Sabor da Maria
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Cardápio, Operação, Orçamento]
    related_skills: [precificacao-delivery, diagnostico-despensa]
---

# Fechamento do cardápio

Seis pratos que precisam do forno na mesma hora formam um cardápio impossível, por melhor que seja o lucro de cada um. O fechamento confere se os pratos aceitos funcionam juntos na cozinha dela e no dinheiro dela.

## O que olhar

`consultar_cardapio` traz os pratos aceitos com o preço e o lucro gravados; `consultar_perfil`, os limites da cozinha; `consultar_orcamento`, o que resta dos R$ 80,00; `diagnostico_despensa`, quanto da despensa ainda não tem prato.

Com isso, aponte uma coisa por vez. Se os pratos saem na mesma leva (bocas do fogão, tempo por cozinhada, espaço na geladeira), lembrando que limite desconhecido é pergunta, não conclusão. Se dividem preparo, o que poupa o cansaço dela. Se o preço equilibra prato que vende muito com prato que sobra mais, usando os valores gravados e nunca uma estimativa. Se as compras cabem no que resta. Conflito raramente se resolve cortando prato: em geral é escalonar ou adiantar um preparo na véspera. Quem decide o que entra agora e o que espera a primeira semana de venda é ela; recusar ou adiar um prato também se grava, com `registrar_decisao`.

Antes de ela aceitar um prato ou ir ao mercado por ele, siga o checklist de produção do prato, na ordem: equipamentos, técnicas, rotina, ingredientes (o que ela tem, o que compra e se cabe nos R$ 80,00) e os pré-determinados (porções, pesos, quantidades e preços, cada um estimado com a fonte, que ela pode mudar, e nenhum deles vira pergunta). Prato que ela não disse se gosta de fazer ainda não se aceita: pergunte o gosto antes. `avaliar_receita` diz se ela já pode aceitar (`pode_aceitar`) e o que ainda falta (`falta_para_aceitar`, em frases prontas para ela). Enquanto faltar alguma coisa ali, nada de compra.

Quando ela contar que comprou o que faltava para um prato confirmado, grave com `registrar_compra(prato, ingrediente, quantidade, unidade, valor)`: sai do orçamento e vira estoque, e o custo do prato passa a usar o preço que ela pagou. Sem isso, o orçamento que ela vê fica errado. A ferramenta recusa compra para prato que a cozinha ainda não liberou e compra que estoura os R$ 80,00 de complementos: são os limites dela. Recusa também enquanto o prato usar algo que toda cozinha tem e ela ainda não confirmou: a recusa traz a `pergunta`, uma só. Faça essa pergunta do jeito que veio, grave o sim dela com `registrar_resposta(tipo="cozinha", campo=<receita_id>, resposta="tem")` e registre a compra de novo; o que ela não tiver vai item por item, como na elicitação. Nunca registre a compra por outro caminho.

Se boa parte da despensa continua sem prato, diga uma vez e ofereça procurar receitas para os itens de maior valor. A embalagem não entra no custo de ingrediente, mas sai do bolso dela: lembre quando ela falar de lucro.

## Ferramentas

| Precisa de | Chame |
|---|---|
| Pratos aceitos, preço, lucro e a trilha | `mcp__mise__consultar_cardapio()` |
| Limites da cozinha | `mcp__mise__consultar_perfil()` |
| O que resta dos R$ 80,00 | `mcp__mise__consultar_orcamento()` |
| O que ela comprou | `mcp__mise__registrar_compra(prato, ingrediente, quantidade, unidade, valor)` |
| Recusar ou adiar um prato | `mcp__mise__registrar_decisao(prato, decisao)` |
| Se ela já pode aceitar o prato, e o que falta | `mcp__mise__avaliar_receita(receita_id)` |
| O sim dela ao que toda cozinha tem | `mcp__mise__registrar_resposta(tipo="cozinha", campo=<receita_id>, resposta="tem")` |

## Exemplo

"Os dois pratos precisam do forno no almoço, e a senhora tem um só. Dá para assar o frango na véspera e deixar o forno livre para a lasanha. A senhora prefere assim ou quer trocar um dos dois?"
