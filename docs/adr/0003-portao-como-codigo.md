# ADR 0003: o portão de viabilidade é código, não instrução

## Contexto

O §2.2 é o coração do desafio. O agente não pode deixar a Dona Maria
comprar ingrediente e descobrir depois que não consegue cozinhar o prato.
Precisa saber de equipamento, técnica e rotina (bocas do fogão, gás, espaço na
geladeira, energia, tempo por cozinhada) antes de qualquer compra ou preço.

Uma regra escrita no prompt é uma sugestão ao modelo. Ela pode ser esquecida no
vigésimo turno, ou contornada por uma receita da web que traz instrução
escondida.

## Decisão

A viabilidade é uma função do motor (`mise/src/mise/viabilidade.py`), e as
ferramentas que mexem com dinheiro dependem dela na própria assinatura.

- **Cinco conferências**, e o pior resultado vence, sobre ingredientes (com o
  que falta, o preço e o orçamento), equipamentos, técnicas, rotina e gosto. O
  veredito é um de quatro, dá, dá comprando, falta saber ou não dá. Só os dois
  primeiros liberam preço.
- **Perfil com três valores** (`mise/src/mise/perfil.py`), tem, não tem e não
  sabemos. O que toda cozinha costuma ter (fogão, geladeira) começa suposto e
  fica marcado como suposto até ela confirmar.
- **"Não sei" vira pergunta, nunca "tem".** A resposta volta o item para "não
  sabemos", e a conferência pergunta de novo quando uma receita precisa dele.
- **"Não tenho" bloqueia**, inclusive item suposto, com o motivo por extenso.
- **Rotina com a conta:** o tempo ativo no fogo dos passos contra o tempo por
  cozinhada que ela declarou (esperas passivas ficam de fora); "em outra panela"
  pede duas bocas ao mesmo tempo, e com uma só avisa sem bloquear; uma hora ou
  mais de fogo pede botijão reserva; aparelhos potentes ao mesmo tempo são
  conferidos contra o circuito; geladeira desconhecida vira pergunta quando a
  receita precisa.
- **A assinatura impõe a ordem.** `calcular(receita, avaliacao)` levanta erro
  quando a avaliação não libera preço (`mise/src/mise/cmv.py`); registrar compra
  exige cozinha, técnica, rotina e gosto resolvidos; registrar o aceite exige
  preço e custo conferidos (`mise/src/mise/mcp_server.py`).
- **A grade e a conversa só mostram o que dá.** A tela de Receitas separa as
  abas "Dá para fazer", "Falta uma resposta sua" e "Ranking" e, dentro de cada
  uma, agrupa pelo gosto dela ("Gosto de fazer", "Ainda não me disse se gosta",
  "Não gosto de fazer"); a receita que a cozinha dela não permite não aparece em
  aba nenhuma
  (`mise/src/mise/receitas_json.py`).

## Consequências

- Nenhum caminho da conversa chega a preço, compra ou aceite sem a conferência:
  não depende de o modelo lembrar.
- As regras têm casos dourados. `make evals` roda 61 casos do portão e 11
  ataques; mudar um veredito dourado reprova o CI, e cada mudança intencional
  fica justificada na descrição do próprio caso (`evals/casos/portao.yaml`).
- O custo é rigidez, porque toda regra nova precisa de código, teste e caso
  dourado.
  É o preço certo para o que protege dinheiro dela.

## Alternativas consideradas

- **Checklist no `SOUL.md`.** Foi o ponto de partida conceitual e continua lá
  como orientação de conversa, mas sem a assinatura nada impede o modelo de
  pular uma conferência.
- **Dois valores (tem ou não tem).** Transformava silêncio em "tem", e o agente
  chegou a dizer que ela dominava fritar sem ela ter dito
  (`docs/transcricoes/linha-de-base/LEIA.md`).
- **Bloquear tudo que não foi confirmado.** Tornaria a conversa um
  interrogatório; o suposto fica suposto e só vira pergunta quando a receita
  precisa.
