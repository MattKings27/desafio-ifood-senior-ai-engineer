---
name: pesquisa-receitas
description: "Achar receitas reais na internet que usem a despensa dela, trazer para o catálogo, mostrar só as que ela consegue fazer e perguntar, de cada uma, se ela gosta de fazer, gravando a resposta."
version: 3.2.0
author: Sabor da Maria
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Receitas, Web, Catálogo, Avaliação]
    related_skills: [elicitacao-restricoes, precificacao-delivery]
    requires_tools: [web_search]
---

# Pesquisa de receitas

Receita real tem endereço. Ela vai apostar dinheiro no prato, e o que não tem fonte não se confere. Por isso a receita da internet entra pela página que o servidor lê, com o site e o autor, e daí em diante é chamada pelo `receita_id`.

## O caminho de uma receita

A ordem aqui importa, porque cada passo usa o que o anterior devolveu:

1. `web_search` acha as páginas. `pauta_de_descoberta` traz as buscas prontas, na ordem: primeiro os pratos clássicos que a despensa dela já cobre (`pratos_para_procurar`, "receita de feijão tropeiro"), que costumam sair sem compra; depois o que ela já pagou e ainda não tem prato (`capital_sem_prato` e `maiores_investimentos` do diagnóstico). Não busque "receitas fáceis".
2. `buscar_receita_na_web(url)` lê a página, guarda no catálogo e devolve o `receita_id`. Se o site não publica a receita em formato estruturado, a ferramenta recusa e diz o motivo: tente outro site, nunca reescreva de memória.
3. `avaliar_receita(receita_id=...)` confere ingredientes, equipamento, técnica e rotina, e põe a receita em avaliação.

## O que apresentar

Mostre duas ou três receitas, cada uma com o nome do site e o link. As que a conferência liberou aparecem como possíveis ("dá pra fazer", "dá, comprando"), com o que ela já tem e o que falta comprar; `comparar_candidatas` põe lado a lado quanto da despensa cada uma aproveita e quanto sai do bolso. As que dependem de uma resposta dela aparecem com o que falta, uma de cada vez, sem prometer que dão: primeiro se ela gosta de fazer; se gosta, a pergunta da cozinha que segura o prato. No começo quase todas estão assim, porque a conferência ainda não sabe quanto tempo ela tem nem o que tem na cozinha: isso é "ainda não confirmei", nunca "nada dá". A que não dá não entra na lista; se ela perguntar por essa, diga o motivo em uma frase.

## "O que eu consigo fazer?"

A resposta sai inteira das ferramentas, nunca da memória, do nome do prato ou do que parece óbvio. Chame `comparar_candidatas()` e responda só com o `catalogo` que ela devolve, que tem as mesmas contas da tela de receitas. Para uma receita só, `avaliar_receita(receita_id)` diz o mesmo daquela receita. Separe sempre em três grupos, com estas palavras:

- **Dá para fazer**: só as de `da_para_fazer`, cada uma com o `como` que veio ("com o que a senhora tem", ou comprando quanto, dentro do que resta dos R$ 80,00).
- **Usa só o que a senhora tem, falta confirmar**: as de `usa_so_o_que_tem`. Não pedem compra nenhuma, mas ainda não estão liberadas: diga o que falta ela confirmar, com o `falta_responder` de cada uma, e ofereça fazer a pergunta agora.
- **Precisa comprar**: as de `precisa_comprar`, com o `falta_comprar` de cada uma. As de `linha_sem_leitura` têm uma linha que a leitura não entendeu: diga isso, sem pedir a ela quanto vai.

O `texto` do `catalogo` é o resumo pronto ("7 receitas usam só o que a senhora tem; falta só a senhora me dizer ..."): use ele, sem trocar os números. Nunca passe uma receita de um grupo para outro por conta própria: a de `usa_so_o_que_tem` só vira "dá para fazer" depois que ela responde e a conferência libera. Com `da_para_fazer` vazio e `usa_so_o_que_tem` com receitas, a verdade é "ainda falta a senhora me confirmar", não "nada dá". Com o catálogo vazio, diga que ainda não há receita trazida e ofereça procurar.

Conte o que a conferência avisou: `opcionais` (o que ficou de fora), `linhas_nao_entendidas` (a linha que a leitura não entendeu, que você cita sem pedir a ela a quantidade) e `avisos` (o que não impede o prato, mas muda o dia dela). Rendimento que a página não diz não é pergunta: a conferência estima pelo peso dos ingredientes e por porções de 350 g, e diz "estimativa, a senhora pode mudar"; repita assim, e se ela disser outro número, ele volta em `avaliar_receita` com o `receita_id` e só esse campo. Preço também não é pergunta: o que falta comprar vem com o preço estimado e a fonte (o `preco_de_referencia` de cada compra, com o site e a data que vieram no texto). Diga que é estimativa, de onde veio e que ela pode corrigir, porque o preço dela vale mais; se ela disser o dela, grave com `registrar_preco_mercado`. Se a ferramenta não trouxer preço nenhum para um item, diga que ainda não há preço para ele, sem perguntar a ela quanto custa.

## O que ela acha

Toda receita que você apresenta leva a pergunta do gosto, sempre, mesmo quando ela não falou nada sobre isso: "a senhora gosta de fazer esse prato?", junto com se ela vê algum impedimento, numa pergunta só, sobre o mesmo prato. Com duas ou três receitas na mesma resposta, pergunte da primeira e siga para a próxima depois que ela responder. O gosto vem antes da cozinha: se ela não gosta, não pergunte equipamento, técnica nem rotina daquele prato.

Grave a resposta na hora, com `registrar_avaliacao_da_receita(receita_id, gosta, estrelas, notas)`: é ela que separa, na tela de receitas, "Gosto de fazer" de "Não gosto de fazer", e a resposta traz a pontuação com a conta e a posição no ranking dela, que se diz com essa conta. As estrelas vêm como oferta, não como outra pergunta: se ela quiser, dá uma nota de 1 a 5 em sabor, facilidade, tempo, entrega e apelo de venda. O impedimento vai em `registrar_gosto(prato, gosta, impedimento)`, porque bloqueia o prato mesmo quando ela gosta: gostar de fazer e conseguir fazer são coisas diferentes. As duas gravam o gosto no mesmo lugar. O que ela já disse de cada prato está em `consultar_gostos`: se ela já disse, não pergunte de novo.

Dúvida de técnica que aparecer no caminho se responde com `consultar_conhecimento`, citando a fonte que vier.

## Receita que ela dita

Se ela contar como faz, monte a receita com as palavras dela, com o modo de preparo, e passe inteira em `avaliar_receita(receita=...)`. Sem modo de preparo a conferência pergunta como ela faz, porque é dele que sai o equipamento.

## Ferramentas

| Precisa de | Chame |
|---|---|
| Achar páginas | `web_search` |
| Trazer a receita para o catálogo | `mcp__mise__buscar_receita_na_web(url)` |
| Ela consegue fazer? | `mcp__mise__avaliar_receita(receita_id)` |
| Lado a lado, e o que ela consegue fazer (o `catalogo`) | `mcp__mise__comparar_candidatas()` |
| Gosto, estrelas e notas | `mcp__mise__registrar_avaliacao_da_receita(receita_id, ...)` |
| Impedimento | `mcp__mise__registrar_gosto(prato, gosta, impedimento)` |
| O que ela já disse dos pratos | `mcp__mise__consultar_gostos()` |
| Pauta de busca pela despensa | `mcp__mise__pauta_de_descoberta()` |
| Dúvida de técnica, com fonte | `mcp__mise__consultar_conhecimento(pergunta)` |

## Exemplos

"Achei um arroz com frango no ⟨site⟩ que usa o arroz e o frango que a senhora já tem: ⟨link⟩. Com o que a senhora tem, dá pra fazer. A senhora gosta de fazer esse prato? Se quiser, me dá uma nota de 1 a 5 para o sabor e a facilidade."

Quando ela perguntar de onde saiu um preço: "Esse preço do creme de leite é estimado: ⟨o texto da referência, com o site e a data⟩. Se a senhora paga outro valor, me diga que eu anoto o seu."

Para "o que eu consigo fazer?", com os nomes e os números que o `catalogo` trouxe: "Dá para fazer agora: ⟨receitas de da_para_fazer, com o como de cada uma⟩. Usam só o que a senhora tem, e falta a senhora me confirmar ⟨o falta_responder delas⟩: ⟨receitas de usa_so_o_que_tem⟩. Precisam de compra: ⟨receita⟩, que pede ⟨falta_comprar⟩. Quer que eu faça a pergunta que libera mais receitas?"
