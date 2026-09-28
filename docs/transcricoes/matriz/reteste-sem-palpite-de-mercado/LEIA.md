# Reteste: sem palpite de mercado

Relendo a matriz para montar o roteiro da demo, achei uma afirmação sem fonte
numa conversa que tinha passado. Depois de ela decidir cobrar R$ 18,00, a agente
avisou que o preço era "bem acima do que se costuma ver num prato feito de
frango no delivery". Nenhuma ferramenta sabe o que a vizinhança cobra.

Parte vinha do próprio motor: o cenário do meio se descrevia como "o padrão do
mercado de delivery". A correção tem três partes:

- a descrição do cenário virou "o meio-termo: o ingrediente fica em cerca de um
  terço do preço", que é o que o número é;
- o `SOUL.md` diz que a agente não sabe o que a vizinhança cobra, e que o risco a
  avisar depois da decisão é o que a conta mostra;
- os dois cenários que passam por ali reprovam "acima/abaixo do que se costuma"
  e "padrão do mercado". O critério novo reprova a conversa antiga.

Opus 5, esforço alto, k = 3, estado zerado a cada execução:

| Cenário | Passaram |
|---|---|
| caminho-completo-ate-a-decisao | 3 de 3 |
| preco-abaixo-do-minimo | 3 de 3 |

Latência por turno p50 28,4 s, p95 79,6 s. Custo US$ 4,00 (US$ 0,67 por
conversa, que aqui são as duas mais longas). Os tokens conferem com o banco do
Hermes.

Nas três execuções o aviso ficou no que a agente sabe: "eu não sei o que cobram
aí perto da senhora, então não vou dizer que está caro nem que está barato".
