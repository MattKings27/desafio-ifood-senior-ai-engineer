# ADR 0010: valor em reais mascarado enquanto a resposta chega

## Contexto

Na web, a resposta do agente aparece enquanto o modelo escreve. O
guard-rail (ADR 0004) confere a resposta inteira, no fim. Se o rascunho mostrasse
os números na hora, a Dona Maria leria um "R$ 2,74" que o guard-rail retiraria
dez segundos depois, e o que se lê primeiro é o que fica na cabeça. Esperar o
texto inteiro para mostrar qualquer coisa deixaria a tela parada durante todo o
turno.

## Decisão

- **O rascunho sai, os valores não.** `gateway/src/gateway/mascara.py` troca, no
  `texto.parcial`, cada valor com "R$", cada valor
  escrito com "reais" ou "real" e os dígitos que sobram colados ao marcador pelo
  caractere U+E000, de uso privado. A tela o desenha como "R$ ···".
- **A cauda ambígua espera.** Um pedaço que ainda pode virar valor ("R", "R$ 7,",
  "4,5 rea") fica retido até o próximo pedaço decidir; no fim do turno, o que
  sobrou sai no último `texto.parcial`.
- **O texto final substitui o rascunho.** O `texto.final` traz a resposta, o que
  o agente escreveu depois da última ferramenta, com cada valor conferido contra as saídas do motor nesta conversa e
  as palavras dela, na mesma regra do plugin do Hermes; o que não tem origem
  vira "[valor retirado]", e o campo `retirados` conta quantos.
- **Turno que não termina bem não revela nada.** Cancelado ou com falha, o turno
  guarda o rascunho mascarado, e ele fica mascarado.
- **Duas portas, a mesma regra.** O navegador aplica a mesma máscara de novo
  sobre o rascunho inteiro (`webapp/src/lib/conversa/mascara.ts`), e se um valor
  escapar do backend, partido em dois pedaços ou por um bug, ele também não
  aparece. `gateway/tests/test_mascara.py` prova que as expressões do backend
  são as mesmas do guard-rail do Hermes.

## Consequências

- Ela vê a resposta se formando e nunca vê um número que depois seria retirado.
  A amostra gravada pelas rotas da web confirma que nenhum dígito de valor saiu no
  rascunho (`docs/transcricoes/chat-web/LEIA.md`).
- Porcentagem e quantidade aparecem no rascunho, porque a máscara, como o
  guard-rail, só cuida de dinheiro.
- A paridade entre `mascara.py` e `mascara.ts` é conferida pelos mesmos exemplos
  (`contratos/web/mascara.json`), lidos pelos testes dos dois lados, e o
  `test_mascara.py` também compara o backend com o plugin.

## Alternativas consideradas

- **Sem streaming.** Correto e lento, porque a tela ficaria parada pelo turno inteiro,
  que chega a dezenas de segundos.
- **Streaming sem máscara, corrigindo no fim.** Mostra o número errado primeiro.
- **Conferir cada pedaço do rascunho contra o motor.** O valor chega picado
  ("R$ 2", depois ",47"), e conferir pedaço por pedaço daria falso positivo e
  falso negativo, e a conferência completa já acontece no fim.
