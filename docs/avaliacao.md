# Avaliação

Quatro camadas, da mais barata à mais cara. As três primeiras rodam sem rede e
sem chave, no CI; a última chama o modelo de verdade e custa dinheiro.

| Camada | Comando | O que prova | Custo |
|---|---|---|---|
| Casos do portão e ataques | `make evals` | as decisões do motor não mudam sem querer | nenhum |
| Conjunto dourado da busca | `make evals-recuperacao` | a busca acha o trecho certo e diz "não sei" quando deve | nenhum |
| Juiz da conversa | `make evals` (juiz por regra) | mede quanto o juiz concorda com rótulos humanos | nenhum |
| Cenários do agente real | `make perfil-avaliacao && make evals-agente` | o agente no Hermes segue o caminho certo | API da Anthropic |

## Casos do portão e ataques

`evals/casos/portao.yaml` tem 61 casos dourados, 25 que dão, 10 que dão
comprando, 8 que pedem uma resposta dela e 18 que não dão. Cada caso fixa o
veredito e, quando importa, se o preço é liberado, a pergunta, o impedimento, o
aviso ou a situação de cada ingrediente. Qualquer diferença reprova (`make evals` sai com
1), e uma mudança intencional fica justificada na descrição do próprio caso.

`evals/src/evals/adversarial.py` tem 11 ataques, cada um tentando fazer o
sistema decidir errado, com preço sem passar pelo portão, custo com item sem
cotação, instrução escondida no JSON-LD de uma página, receita da web sem
procedência, página que não é receita, preço negativo no dossiê, rendimento
zero para baratear, gosto ignorado com o resto perfeito, receita digitada com
endereço que ninguém leu, quantidade trocada entre a conferência e o custo e
aceite apoiado no que toda cozinha tem, sem ela ter confirmado.

O CI roda os mesmos casos por `evals/tests/test_evals.py`.

## Conjunto dourado da busca

57 perguntas com o trecho esperado, 11 delas fora da plataforma, medidas por
revocação em 5, MRR em 10, nDCG em 10 e acerto de abstenção, com a ablação
entre trigramas com hash e o modelo multilíngue. Resultado, reprodução e
calibração em [`rag.md`](rag.md).

## O juiz da conversa

`evals/src/evals/juiz.py` mede o juiz contra rótulos humanos: 10 respostas no
conjunto de ajuste e 6 reservadas, metade boas e metade ruins, com falso
positivo e falso negativo contados à parte. Um juiz só é utilizável com
concordância de 80% ou mais no conjunto reservado.

- O `make evals` usa o juiz por regra (`JuizDeterministico`). Ele é reportado e
  não bloqueia: qualidade de conversa é julgamento, e o que bloqueia merge é o
  que é determinístico. Hoje ele acerta 100% do ajuste, sobreajustado por
  construção, e 67% do reservado, abaixo do limiar: deixa passar a precisão
  inventada ("exatamente R$ 4,3271" sobre uma medida de xícara) e reprova uma
  recusa certa por orçamento. Por isso ele só informa. As regras não foram
  ajustadas ao reservado, que deixaria de medir alguma coisa.
- O juiz de modelo (`JuizDeModelo`) usa o Haiku 4.5 com `temperature: 0` e só
  roda com `ANTHROPIC_API_KEY`. Nenhum alvo do Makefile o chama hoje.

## Cenários do agente real

`evals/casos/agente/` tem 24 cenários, do §2.1 ao §2.4, mais a conversa que descobre o que ela consegue cozinhar, cumprimento sem despejar, conhecimento com
fonte, "não sei", contexto da tela e ataque por receita. O harness
(`evals/src/evals/agente/`):

1. roda num perfil descartável do Hermes (`make perfil-avaliacao` cria o
   `sabor-da-maria-avaliacao`; o harness recusa perfil sem esse sufixo);
2. zera o estado a cada execução: dossiê e trilha de auditoria novos numa pasta
   temporária, memória do Hermes apagada, e o agente rodando fora do
   repositório;
3. confere a conexão do servidor MCP antes de gastar com o modelo;
4. manda cada fala por `hermes chat --format stream-json` e completa as saídas
   das ferramentas pelo banco de sessões do Hermes;
5. confere a **trajetória** antes do texto: as ferramentas exigidas, na ordem;
   as proibidas, inclusive com certos argumentos; as 11 ferramentas fora do
   papel, que reprovam em qualquer cenário; jargão interno ("motor", "portão",
   "CMV") e o marcador "[valor retirado]", que também reprovam; e expressões que
   a resposta deve ou não conter.

Um cenário passa só se passar nas k execuções (`pass^k`). Latência por turno
(p50 e p95) e tokens vêm do próprio fluxo do Hermes e são conferidos contra o
banco de sessões; o custo usa a tabela de preços de `telemetria/src/telemetria/custo.py`.

```bash
make perfil-avaliacao                          # uma vez: o perfil descartável
make evals-agente K=2                          # todos os cenários, duas execuções cada
make evals-agente CENARIOS=evals/casos/agente/orcamento-de-80.yaml
make evals-agente MODELO=claude-opus-5-5 ESFORCO=high SAIDA=/tmp/rodada
```

As transcrições vão para `docs/transcricoes/` (ou para `SAIDA`) e precisam da
redação antes de versionar (`docs/transcricoes/LEIA.md`). O histórico das
rodadas anteriores está lá.

## O que custa dinheiro

Só o que chama o modelo: `make evals-agente`, `make chat`, as conversas pela
web e cada rodada da busca automática de receitas (desligada nos testes e no
CI). `make test`, `make evals`, `make evals-recuperacao` e o CI não usam chave.
O `make conferir-conhecimento` e o vetorizador neural precisam de rede, mas não
de chave.
