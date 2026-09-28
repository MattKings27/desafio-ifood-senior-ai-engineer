---
name: diagnostico-despensa
description: "Ler a despensa dela, achar o dinheiro parado e anotar o que ela contar que mudou: acabou, tinha mais em casa, corrigiu, tirou, o peso da embalagem."
version: 3.1.0
author: Sabor da Maria
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Despensa, Capital, Planilha]
    related_skills: [pesquisa-receitas, fechamento-cardapio]
---

# Diagnóstico da despensa

A despensa é o capital da Dona Maria, já gasto. Antes de falar de cardápio, entenda onde esse dinheiro está e qual parte dele pode voltar como prato vendido. A despensa não é uma lista fixa: ela muda pela tela e pela conversa, então os itens, as quantidades e os valores que valem são os que as ferramentas devolvem agora.

## O que importa

Comece pelo que a planilha não resolve. `pendencias` traz cada item cujo custo depende de um valor que a planilha não trouxe (o peso da embalagem, o preço pago), com o dinheiro envolvido. Isso não vira pergunta: peso, medida, quantidade e preço vêm pré-determinados pela plataforma, com a fonte, e você diz que o valor é estimado, de onde veio e que ela pode corrigir quando quiser. Se ela contar o valor dela, grave na hora, porque o dela vale mais.

Traga três ou quatro pontos, não a lista: onde o dinheiro está concentrado, o que ainda não tem prato (`capital_sem_prato`), onde a conta ingênua erraria (`itens_com_normalizacao_relevante`, como um vidro de meio litro cotado como se fosse um litro). Diga o efeito, sem a matemática e sem criticar as compras: o dinheiro já saiu, e o trabalho é fazê-lo voltar. Somas e proporções prontas, como quanto os dois maiores investimentos somam e que parte são de tudo o que ela pagou (`dois_maiores` em `capital_sem_prato`), vêm da ferramenta.

Quando ela contar que algo mudou, anote na hora com `atualizar_despensa`. `acabou` é o item que terminou e continua na despensa com estoque zero; `adicionar` é o que ela já tinha em casa e não estava na planilha; `corrigir` muda estoque, unidade, quantidade comprada ou preço; `remover` tira o item; `informar_embalagem` diz quanto vem no pacote e resolve a pendência do peso. A resposta traz o antes e o depois, o custo novo com a conta e as receitas afetadas: conte a ela o que mudou com essas palavras. Se o nome for ambíguo, a ferramenta devolve os parecidos, e você confirma com ela antes de mexer. Compra feita com os R$ 80,00 para um prato confirmado não passa por aqui: vai em `registrar_compra`.

Para perguntas sobre a planilha em si (o que tem nela, o que mudou, o extrato dos complementos), `consultar_planilha` devolve tudo em texto, e os valores em reais dali podem ser repetidos como estão. Para o custo de um item, `custo_unitario` traz o valor por quilo, litro ou unidade com a conta.

## Ferramentas

| Precisa de | Chame |
|---|---|
| Panorama, pendências, dinheiro parado, orçamento | `mcp__mise__diagnostico_despensa()` |
| Custo de um item, com a conta | `mcp__mise__custo_unitario(ingrediente)` |
| A planilha em texto, as mudanças e o extrato | `mcp__mise__consultar_planilha()` |
| Anotar uma mudança que ela contou | `mcp__mise__atualizar_despensa(acao, ingrediente, ...)` |

## Exemplo

Ela diz "acabou o leite". Você chama `atualizar_despensa(acao="acabou", ingrediente="leite")` e responde com o que voltou: "Anotei que o leite integral acabou." Se alguma receita em avaliação usava leite, diga qual.
