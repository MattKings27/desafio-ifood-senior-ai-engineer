# Antes das correções

Os 12 cenários de `evals/casos/agente/`, uma execução cada (k = 1), na agente real,
com a configuração versionada (`claude-opus-5`, esforço `max`) e o motor antes das
primeiras correções. É o "antes" com que as rodadas seguintes se comparam.

| | |
|---|---|
| Passaram | **8 de 12** |
| Turnos | 19 |
| Latência por turno | p50 64.0 s, p95 142.3 s |
| Tokens | 71,298 de saída, 3,645,006 lidos do cache, 597,419 gravados |
| Custo | ≈ US$ 7.34 (gravação de cache a 5 min) |

Preços usados: Opus 5 a US$ 5 de entrada e US$ 25 de saída por milhão de tokens;
leitura de cache a 0,1× da entrada e gravação a 1,25×.

## O que falhou

As quatro falhas são a mesma: **o guard-rail numérico apagou números corretos**,
18 no total, e a resposta chegou a ela com "[valor retirado]" no lugar de preço,
lucro e orçamento. Os números tinham vindo do motor, em turno anterior ou de uma
das sete ferramentas que o guard-rail não conhecia. Foi a primeira correção da agente.

O modelo não errou portão nem conta em nenhum cenário. Um achado de conta veio do
motor, não do modelo: a agente disse "R$ 2,47 ÷ 0,90 = R$ 2,74, abaixo disso a
senhora paga pra trabalhar", e a R$ 2,74 ela recebe R$ 2,466. Corrigido no motor
logo em seguida (o mínimo passa a subir para o centavo de cima).

## Dois cenários estavam errados, não a agente

A primeira leitura deu as mesmas 8 de 12, com duas falhas que eram erro do cenário:

- `nao-gosta-encerra-o-prato` proibia qualquer `registrar_decisao`; a agente
  registrou a feijoada como **recusada**, que é o certo. O cenário agora proíbe só
  o aceite (`nao_chama_com`).
- `preco-so-depois-do-portao` proibia qualquer "R$"; a agente recusou dar preço e
  mostrou o custo dos ingredientes vindo do motor. O cenário agora proíbe só preço
  de venda.

As transcrições foram julgadas de novo com `--reavaliar`, sem rodar a agente outra vez.

## Uma diferença de ambiente

Esta rodada abriu o Hermes dentro do repositório, e ele carregou o `HERMES.md`
da raiz como contexto. Aberto de outra pasta, o Hermes não lê esse arquivo. A
partir daqui o harness roda a agente numa pasta neutra, e as regras que precisam
valer sempre ficam no `SOUL.md` do perfil.
