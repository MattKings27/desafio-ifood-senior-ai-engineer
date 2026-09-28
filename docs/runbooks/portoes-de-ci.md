# Como um portão entra, sobe e desce

Todo portão do CI está num de dois estados, **aviso** ou **obrigatório**, e o
que só roda na máquina fica marcado como **local**. A diferença é uma só,
obrigatório reprova o PR, e aviso não.

A regra que organiza isto é que **aviso é o estado de repouso; obrigatório se
conquista.** E a simétrica, que costuma faltar: **nenhum portão continua
obrigatório por inércia, e nenhum continua rebaixado por inércia.**

O problema que isto resolve é conhecido. Portão que nasce bloqueando é desligado
na primeira sexta-feira ruim, e nunca mais volta. Portão que nasce avisando fica
avisando para sempre, e vira ruído que todo mundo aprende a ignorar. Os dois
acabam no mesmo lugar: um portão que não decide nada.

## Estado de cada portão

| Portão | Onde | Estado | Por quê |
|---|---|---|---|
| ruff (lint e formatação) | `ci.yml`, job dos seis pacotes | **obrigatório** | Determinístico, rápido, sem falso positivo |
| mypy `--strict` | idem | **obrigatório** | O motor inteiro foi escrito sob ele |
| pytest com piso de cobertura | idem, em Python 3.11, 3.12 e 3.13 | **obrigatório** | 95% em cinco pacotes e 90% no `evals` (`fail_under` de cada `pyproject.toml`) |
| Plugin do guard-rail, instruções do agente e testes dos portões | idem | **obrigatório** | `hermes/plugins`, `hermes/tests` e `scripts/tests` |
| Higiene do texto versionado | idem | **obrigatório** | `scripts/higiene.py`, o mesmo do `make higiene`, contra travessão separando ideias, caminho da máquina de quem escreveu e plural com "(s)" na tela |
| Clone limpo | `clone-limpo` | **obrigatório** | Sobe tudo do zero a partir do commit, como quem avalia |
| Imagem Docker sobe e responde | `imagem` | **obrigatório** | Confere 37 itens e R$ 663,39 pela API da imagem |
| Interface: tipos, ESLint sem aviso, vitest com 95% e build | `interface` | **obrigatório** | |
| Interface de ponta a ponta, com axe | `interface-ponta-a-ponta` | **obrigatório** | Playwright em 390 e 1280 px, nos dois temas |
| Lint do DESIGN.md (WCAG) | `design` | **obrigatório** | Já pegou um erro real: verde de sucesso a 3,25:1 |
| Tokens em dia com o DESIGN.md | `design` | **obrigatório** | Comparação de arquivo, sem ambiguidade |
| Cobertura do diff a 80% | `cobertura-do-diff`, só em PR | **obrigatório** | Provado neste repositório antes de ser ligado |
| gitleaks | `seguranca.yml` | **obrigatório** | Segredo versionado não tem tolerância aceitável |
| pip-audit e npm audit | `seguranca.yml` | **aviso** | CVE em dependência transitiva aparece sem mudança nossa e trava PR alheio ao problema |
| CodeQL | `seguranca.yml` | **aviso** | Roda só com o repositório público |
| `hermes plugins validate` | `make plugin` | **local** | Instalar o Hermes no CI custa desproporcional ao que o portão pega |

## Para subir um portão de aviso para obrigatório

1. Rodar em aviso com resultado limpo por uma sequência inteira de PRs.
2. Escrever, no cabeçalho do workflow, o que ele pega e o que **não** pega.
3. Documentar a válvula de escape antes de ligar, não depois.
4. Mudar de estado num PR só disso, com o motivo no corpo.

## Para rebaixar

Mesmo caminho, na direção oposta. Se um portão obrigatório começa a ficar
vermelho por motivo que não é o que ele deveria pegar, ele desce para aviso num
PR próprio, com o motivo registrado no cabeçalho do workflow. Rebaixar é uma
decisão escrita, não um `continue-on-error` acrescentado às pressas.

## Sem veredito é vermelho

O portão de cobertura do diff tem três saídas, não duas: `0` aprovado, `1`
reprovado, `2` não consegui decidir. O `2` é vermelho.

A razão é que um scanner que falha em silêncio produz a mesma tela verde de um
repositório limpo, e é pior do que não ter scanner nenhum: gera confiança sem
base. O mesmo padrão está no `pip-audit` e no `npm audit`: "rodou e não achou"
e "não rodou" são resultados diferentes e têm cores diferentes.

## Por que a cobertura tem duas camadas

Uma pergunta cada.

O **piso global** (`fail_under` no `pyproject.toml` de cada pacote: 95%, e 90%
no `evals`) responde *"o projeto está coberto?"*. É o número que não pode cair.

A **cobertura do diff** de 80% responde *"o que você acabou de escrever está
coberto?"*. É outra pergunta, e com a cobertura global alta o piso não consegue
respondê-la: código novo sem teste se dilui na massa.

Isto não é teórico. Foi medido aqui antes de o portão ser ligado, com uma
função sem teste acrescentada ao `preco.py`:

```
piso global .......... 97,83%  passou
cobertura do diff .... 25,0%   reprovou, apontando preco.py:297-299
```

O piso global sozinho teria deixado entrar.

## A válvula de escape

Label `coverage-override` no PR, **mais** uma seção `## Coverage override
justification` no corpo com pelo menos uma justificativa de verdade.

A label sozinha não basta, e a ausência da justificativa **falha alto** em vez de
simplesmente não aplicar o override, para a exigência ficar visível em vez de
virar um silêncio que ninguém percebe.
