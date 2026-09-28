---
name: elicitacao-restricoes
description: "Descobrir, uma pergunta por vez e depois do gosto, se a cozinha dela aguenta cada prato: equipamento, técnica, fogão, gás, geladeira, energia e tempo, aceitando o não sei."
version: 3.1.0
author: Sabor da Maria
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Cozinha, Entrevista, Viabilidade]
    related_skills: [pesquisa-receitas, precificacao-delivery]
---

# Elicitação de restrições

O erro que esta skill evita: ela comprar ingrediente e descobrir, com a comida na bancada, que não dá para terminar. Equipamento, técnica e os limites da rotina (bocas do fogão, gás, espaço na geladeira, energia, tempo de cozinha) se descobrem na conversa, antes de qualquer compra ou preço.

## O que importa

Pergunte só o que é dela: se gosta de fazer e se vê impedimento, equipamento e utensílio, técnica e os limites da rotina. O gosto vem primeiro: se ela não gosta de fazer o prato, nenhuma pergunta da cozinha é feita por ele. Peso, medida, quantidade, rendimento e preço nunca são pergunta, nem se o item da receita é o parecido que ela tem: a conferência estabelece esses números pela receita e pela pesquisa (preço de referência de supermercado, média de preços de São Paulo, tabela de medidas do IBGE, o pacote da planilha dela, a estimativa do rendimento, o tempo que a própria receita diz), com a fonte, e você diz que é estimativa e que ela pode corrigir. Deixe `proxima_pergunta` escolher: ela devolve a pergunta que decide mais pratos agora, com o motivo e as opções de resposta. Se for de equipamento, técnica ou rotina, faça essa pergunta, uma por vez, com o motivo em palavras simples ("pergunto porque o frango assado depende disso"); se for de outro assunto, não pergunte, e diga o que a conferência estimou. As perguntas de rotina são sobre a vida dela, não campo de cadastro: "quanto tempo a senhora consegue ficar cozinhando de uma vez, sem se cansar?".

Grave a resposta na hora com `registrar_resposta`, usando exatamente o `tipo` e o `campo` que vieram na pergunta. A resposta traz `impacto`: as receitas que passaram a dar, as que deixaram de dar e as que ainda esperam uma resposta. Conte isso a ela.

"Não sei" é resposta. Grave como `nao_sei`: o item fica em aberto, nunca vira "não tem", e a pergunta volta sozinha quando uma receita precisar dele. Não insista nem repita a pergunta sem um motivo novo. Resposta que não dá para entender ("mais ou menos", "talvez") a ferramenta recusa de propósito, para não adivinhar: pergunte de outro jeito.

"Não tenho" bloqueia as receitas que precisam do item, inclusive o que toda cozinha costuma ter: sem fogão, o que vai ao fogo não dá, e isso se diz com clareza. Sem forno, a conferência pergunta pelo que faz o papel dele (air fryer, forno elétrico); faça a pergunta que ela fizer antes de dar o prato por perdido.

Grave também o que ela contar sem você perguntar ("comprei uma air fryer", "não tenho liquidificador"). Antes de perguntar qualquer coisa, olhe `consultar_perfil`: `ela_confirmou` é o que ela já respondeu, `pressuposto` é suposição (nunca "a senhora disse"), `ela_disse_que_nao_sabe` é o que ela respondeu que não sabe.

Aceite o que ela diz sobre técnica: se disse que não faz, ofereça outro prato; se disse que faz, não peça prova.

## O que toda cozinha tem, confirmado antes do aceite

Fogão, frigideira, panela funda, faca, tábua, geladeira, ralador, peneira e fouet, e refogar, fazer arroz e feijão, fritar, assar, molho de tomate, bolo caseiro e brigadeiro começam como supostos: não pergunte item por item, nem no começo da conversa, nem na pesquisa. Suposto não é certeza, e por isso o aceite e a compra pedem que ela confirme o que a receita usa, uma vez só, na hora em que ela for aceitar o prato ou comprar para ele. Siga o checklist do prato: `avaliar_receita` traz `pode_aceitar`, `falta_para_aceitar` (o que ainda segura, em frases prontas para ela) e `confirmar_a_cozinha`, com a `pergunta` pronta ("Antes de aceitar, a senhora confirma que tem fogão e panela funda e que sabe refogar?"); a recusa de `registrar_decisao` e de `registrar_compra` traz a mesma pergunta. Faça essa pergunta do jeito que veio, uma pergunta só, e nunca contorne a recusa.

Com o sim dela, grave `registrar_resposta(tipo="cozinha", campo=<receita_id>, resposta="tem")`, e então o aceite ou a compra. Se ela disser que não tem um dos itens, grave esse item sozinho, como equipamento ou técnica, com `nao_tem` (ou `nao_sei`), conte o que isso muda no prato, e o resto vai com `tipo="cozinha"`. Só o sim dela vai por `tipo="cozinha"`: nunca confirme por ela. O que ela confirmou vale para todas as receitas e não se pergunta de novo (está em `ela_confirmou`, no `consultar_perfil`).

Porções, pesos, medidas, quantidades e preços são pré-determinados pela plataforma, com a fonte: não são pergunta. Quando ela perguntar de um deles, diga que é estimado, de onde veio e que ela pode mudar quando quiser; o que ela disser de volta vai para a ferramenta da tabela abaixo.

## Onde cada resposta vai

As linhas de peso, preço, embalagem, rendimento, tempo da receita e linha que não foi entendida são para quando ela corrige um valor estimado ou conta o dela sem você perguntar: nunca para você perguntar.

| A resposta é sobre | Grave com | Resposta |
|---|---|---|
| Equipamento ou técnica | `mcp__mise__registrar_resposta(tipo, campo, resposta)` | `tem`, `nao_tem` ou `nao_sei` |
| Rotina: `bocas_fogao`, `espaco_geladeira_litros`, `porcoes_por_fornada`, `energia_aparelhos_simultaneos` | `mcp__mise__registrar_resposta(tipo="operacional", campo, resposta)` | um número, ou `nao_sei` |
| Quanto tempo ela cozinha de uma vez (`tempo_max_por_fornada_min`) | `mcp__mise__registrar_resposta(tipo="operacional", campo="tempo_max_por_fornada_min", resposta)` | em horas, como ela disse: "2 horas", "1,5 hora", "1h30"; um número sozinho é em horas, ou `nao_sei` |
| Gás sobrando | `mcp__mise__registrar_resposta(tipo="operacional", campo="tem_gas_sobrando", resposta)` | `sim`, `não` ou `nao_sei` |
| Gosto de um prato, perguntado de toda receita que você apresenta e antes da cozinha | `mcp__mise__registrar_avaliacao_da_receita(receita_id, gosta)`, ou `mcp__mise__registrar_gosto(prato, gosta, impedimento)` quando ela contar um impedimento: as duas gravam o gosto no mesmo lugar | `gosta` verdadeiro ou falso |
| Modo de preparo da receita que ela dita | `mcp__mise__avaliar_receita(receita_id, receita)`, com a `receita` levando só o que ela contou | o que ela disse |
| Correção dela: o tempo de cozimento (`tempo_cozimento_min`), quanto vai de uma linha que não foi entendida, ou o rendimento | `mcp__mise__avaliar_receita(receita_id, receita)`, com a `receita` levando só o que ela corrigiu | o que ela disse |
| Correção dela: o peso de uma linha da receita (o da medida do IBGE, por exemplo) | `mcp__mise__avaliar_receita(receita_id, receita)`, com a `receita` levando só essa linha: o mesmo `texto` da linha, o `nome`, `peso` e `por_unidade` (`true` quando é o peso de uma unidade; `false` quando é o da linha inteira, "as duas colheres dão 20 gramas") | o peso que ela disse ("300 g", "0,3 kg") |
| Correção dela: o preço do que falta comprar | `mcp__mise__registrar_preco_mercado(ingrediente, valor, quantidade, unidade)` | o preço e por quanto ele compra ("a lata", "o quilo") |
| Correção dela: o peso da embalagem de um item da despensa | `mcp__mise__atualizar_despensa(acao="informar_embalagem", ingrediente, conteudo_da_embalagem)` | "1 kg", "400 g" |
| O sim dela ao que toda cozinha tem, antes de aceitar ou comprar | `mcp__mise__registrar_resposta(tipo="cozinha", campo=<receita_id>, resposta="tem")`; com `campo="toda_cozinha"`, tudo o que ainda é suposto | `tem` |
| Um item do que toda cozinha tem que ela não tem | `mcp__mise__registrar_resposta(tipo="equipamento" ou "tecnica", campo=<id>, resposta)`, e o resto com `tipo="cozinha"` | `nao_tem` ou `nao_sei` |

## Exemplo

Depois que ela disse que gosta de fazer o frango assado: "A senhora tem forno? Pergunto porque o frango assado depende dele. Se não tiver, eu vejo se a air fryer resolve."

Na hora de aceitar, com a pergunta que veio da conferência: "Antes de aceitar, a senhora confirma que tem fogão e panela funda e que sabe refogar?"
