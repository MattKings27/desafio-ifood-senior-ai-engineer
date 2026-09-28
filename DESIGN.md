---
version: alpha
name: Sabor da Maria
description: Identidade do iFood aplicada a uma ferramenta de decisão de preço, não a um cardápio.
colors:
  primary: "#EB0033"
  secondary: "#890019"
  tertiary: "#333333"
  neutral: "#F7F7F7"
  on-primary: "#FFFFFF"
  on-secondary: "#FFFFFF"
  on-tertiary: "#FFFFFF"
  on-neutral: "#333333"
  surface: "#FFFFFF"
  cream: "#F9F2E8"
  ink: "#1A1A1A"
  muted: "#717171"
  success: "#0A7D3E"
  warning: "#B25E09"
  danger: "#C8101E"
  info: "#1A6FD1"
typography:
  display:
    fontFamily: Sora
    fontSize: 2.25rem
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  h1:
    fontFamily: Sora
    fontSize: 1.75rem
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  h2:
    fontFamily: Sora
    fontSize: 1.25rem
    fontWeight: 600
    lineHeight: 1.3
  body-lg:
    fontFamily: Inter
    fontSize: 1.125rem
    fontWeight: 400
    lineHeight: 1.5
  body-md:
    fontFamily: Inter
    fontSize: 1rem
    fontWeight: 400
    lineHeight: 1.5
  body-sm:
    fontFamily: Inter
    fontSize: 0.875rem
    fontWeight: 400
    lineHeight: 1.45
  caption:
    fontFamily: Inter
    fontSize: 0.75rem
    fontWeight: 400
    lineHeight: 1.4
  numero:
    fontFamily: Inter
    fontSize: 1rem
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "0em"
rounded:
  xs: 5px
  sm: 10px
  md: 12px
  lg: 14px
  xl: 20px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.xs}"
    padding: 12px
  button-primary-hover:
    backgroundColor: "{colors.secondary}"
    textColor: "{colors.on-secondary}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    rounded: "{rounded.xs}"
    padding: 12px
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.tertiary}"
    rounded: "{rounded.lg}"
    padding: 16px
  chip:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.tertiary}"
    rounded: "{rounded.full}"
    padding: 8px
  selo-apto:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.success}"
    rounded: "{rounded.full}"
    padding: 8px
  selo-falta-info:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.warning}"
    rounded: "{rounded.full}"
    padding: 8px
  selo-bloqueado:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.danger}"
    rounded: "{rounded.full}"
    padding: 8px
  linha-cmv:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.xs}"
    padding: 12px
  derivacao:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.muted}"
    rounded: "{rounded.xs}"
    padding: 8px
  faixa-destaque:
    backgroundColor: "{colors.cream}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: 16px
  aviso-info:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.info}"
    rounded: "{rounded.sm}"
    padding: 12px
---

## Overview

A interface do Sabor da Maria usa a linguagem visual do iFood, mas não é um
cardápio: é uma ferramenta em que uma pessoa decide quanto cobrar pelo próprio
trabalho. Isso muda duas coisas em relação ao app de consumo.

**Número tem hierarquia de título.** Num app de delivery o preço é secundário à
foto. Aqui o preço *é* o conteúdo: ele aparece grande, com peso, e sempre ao
lado da conta que o produziu.

**Vermelho não é decoração.** No iFood o vermelho marca ação. Aqui ele marca
ação **e** alerta de margem. Usar a cor da marca para "prejuízo" seria
confuso, então prejuízo tem cor própria (`danger`) e o vermelho da marca fica
restrito a ação primária e identidade.

## Procedência dos valores

Esta é a parte que torna "fidelidade visual" verificável em vez de opinião.
Cada valor abaixo está marcado como **medido** ou **inferido**.

### Medidos no site ao vivo

Coleta com Playwright, viewport 1440×900, locale pt-BR, contando estilos
computados de todos os elementos visíveis. Script em
`webapp/scripts/medir-ifood.py`; saída bruta em `.estado/design/medicao.json`.

**Procedência exata, porque aqui ela importa:** `www.ifood.com.br` responde
**HTTP 403** a navegador automatizado (proteção anti-bot) e rende só 47 nós.
Os números abaixo vêm de **`institucional.ifood.com.br`**, que responde 200 e
rende **1.340 nós**: mesmo design system, domínio institucional. Onde o `www`
conseguiu medir alguma coisa (tamanhos de fonte), os valores coincidem.

| Token | Valor | Amostras |
|---|---|---|
| `colors.primary` | `rgb(235, 0, 51)` → `#EB0033` | **175 elementos** |
| `colors.secondary` | `rgb(137, 0, 25)` → `#890019` | fundo de hover |
| `colors.tertiary` (texto) | `rgb(51, 51, 51)` → `#333333` | **584 elementos** |
| `colors.muted` candidato | `rgb(173, 173, 173)` → `#ADADAD` | 18, **reprova em contraste** |
| `colors.ink` | `rgb(26, 26, 26)` → `#1A1A1A` | 76 |
| `colors.neutral` | `rgb(247, 247, 247)` → `#F7F7F7` | fundo de seção |
| `colors.cream` | `rgb(249, 242, 232)` → `#F9F2E8` | faixa institucional |
| `rounded.*` | 5px (38×), 10px, 12px, 14px (31×), 15px | distribuição real |
| sombra | `rgba(0,0,0,0.15) 0 0 10px 0` · `rgba(0,0,0,0.13) 0 0 12px -4px` | 13 |
| transição | `0.3s ease` (dominante), 0.25s, 0.4s, 0.5s | 306 |
| escala tipográfica | 16px (560×), 18px, 19px, 28px, 36px, 12px, 14px | base 16px |

**A correção mais importante da coleta:** o vermelho em uso é `#EB0033`, **não**
o `#EA1D2C` que aparece em todo guia de marca de terceiros. A diferença é
pequena no olho e decisiva na acessibilidade (ver **Acessibilidade**).

### A superfície do lojista, que é a que importa aqui

A Dona Maria **é lojista**. A interface dela deve se parecer com a que o iFood dá
a quem vende, não com a que dá a quem compra, e as duas divergem.

Medido em `parceiros.ifood.com.br` (HTTP 200, 433 nós):

| Token | Institucional | **Lojista** | Consequência |
|---|---|---|---|
| radius dominante | 5px (38×), 14px (31×) | **8px (19×)** | cantos mais macios |
| sombra | `0 0 10px` sem deslocamento | **`rgba(0,0,0,0.2) 2px 2px 20px`** | tem deslocamento |
| base tipográfica | 16px (560×) | **14px (84×)** | densidade maior |
| família | só o fallback do sistema | **`iFood RC Textos` (48×), `iFood RC Títulos` (9×)** | nome real, medido |

Cores que só aparecem na superfície do lojista: `#F2F2F2` (fundo de seção, 5×),
`#FCEBEA` (tinta clara de alerta, 3×), `#3E3E3E` (texto secundário, 11×),
`#151515` (tinta forte, 9×), `#EBEBEB` (borda, 3×).

**Duas afirmações minhas anteriores estavam erradas e ficam corrigidas aqui:**

1. Eu disse que a sombra do iFood "não tem deslocamento vertical" e que isso era
   a assinatura dele. Vale para o institucional; a superfície do lojista usa
   `2px 2px 20px`, com deslocamento nos dois eixos.
2. Eu tratei a família tipográfica como não medível e a declarei "inferida". Ela
   é medível, só não no domínio que eu tinha medido. O nome é **`iFood RC
   Textos`** e **`iFood RC Títulos`**.

A fonte continua proprietária e **nenhum arquivo dela é versionado**. O que muda
é a pilha: o nome real vem primeiro, e quem tiver a fonte instalada a vê; quem
não tiver cai em Sora/Inter, que continuam declaradas como aproximação livre.

### Inferidos

- **Tipografia.** A fonte própria do iFood é a *Tipo iFood*, de 2023,
  proprietária. A medição só devolveu a pilha de fallback `system-ui`, porque a
  fonte de marca carrega por `@font-face` em contexto que a coleta não capturou.
  Substituo por **Sora** (títulos) + **Inter** (corpo e números), ambas livres.
  É aproximação declarada, não equivalência.
- **Cores semânticas** (`success`, `warning`, `danger`, `info`). Não há hex
  oficial publicado. Escolhidos para passar AA sobre branco e para não competir
  com o vermelho da marca. O verde começou em `#12A454`, o valor de mercado
  mais comum, e o linter do `design.md` reprovou: **3,25:1**, abaixo dos 4,5:1
  exigidos. Escurecido para `#0A7D3E` (**5,23:1**). É exatamente o tipo de erro
  que passa despercebido a olho nu e some quando a checagem é automática.
- **Escala de espaçamento.** Múltiplos de 4px, convenção de mercado.
- **Cor de borda** `#E6E6E6`. Fica fora do frontmatter de propósito: a spec do
  `design.md` não tem sub-token `borderColor` em componente, e declarar a cor
  sem uso faria o linter acusar token órfão. Ela é definida direto na camada CSS
  como `--cor-borda`.

## Acessibilidade

Contraste calculado pela fórmula de luminância relativa do WCAG 2.2.

| Par | Contraste | AA texto | AA grande | AAA |
|---|---|---|---|---|
| `#EB0033` sobre branco | **4,58:1** | passa | passa | não |
| `#EA1D2C` sobre branco (brandbook antigo) | 4,46:1 | **falha** | passa | não |
| `#890019` sobre branco | 10,11:1 | passa | passa | passa |
| `#333333` sobre branco | 12,63:1 | passa | passa | passa |
| `#1A1A1A` sobre branco | 17,40:1 | passa | passa | passa |
| branco sobre `#EB0033` | 4,58:1 | passa | passa | não |
| `#ADADAD` sobre branco | 2,24:1 | **falha** | **falha** | não |
| `success` `#0A7D3E` sobre branco | 5,23:1 | passa | passa | não |
| `warning` `#B25E09` sobre branco | 4,67:1 | passa | passa | não |
| `danger` `#C8101E` sobre branco | 5,92:1 | passa | passa | não |
| `info` `#1A6FD1` sobre branco | 4,95:1 | passa | passa | não |

Duas regras saem daí:

1. **O vermelho atual pode ser usado em texto pequeno.** O `#EA1D2C` do
   brandbook antigo não podia: reprovava por 0,04. O rebranding corrigiu isso, e
   é por medir em vez de copiar que descobrimos. Ainda assim, texto corrido longo
   usa `tertiary`; vermelho fica para destaque.
2. **`#ADADAD` nunca recebe texto.** O cinza apagado que o site usa reprova em
   qualquer critério. Para texto secundário uso `muted` (`#717171`, 5,3:1).

A tabela acima confere a paleta de base sobre o branco. A interface usa texto
também sobre o fundo cinza, o creme e as tintas dos chips, e nos dois temas: a
conta completa está em **Tema escuro**, logo abaixo.

## Tema escuro

A senhora escolhe entre **Claro**, **Escuro** e **Automático** na engrenagem de
**Preferências**, no canto direito do cabeçalho, em toda tela e em toda largura
(seção Aparência, ao lado do tamanho do texto e do movimento). O automático
segue o celular ou o computador dela, e acompanha quando ele muda sozinho à
noite.

**Sem piscar.** A escolha fica guardada no navegador (`localStorage`, chave
`tema`). Um script pequeno no `<head>` lê essa escolha, resolve o automático
pelo `prefers-color-scheme` e marca `data-tema` no `<html>` (e a cor da barra do
navegador) antes da primeira pintura. O mesmo script aplica o tamanho do texto
(`data-texto`), a redução de movimento (`data-movimento`) e o modo minimalista
(`data-minimalista`) guardados nas Preferências. Sem JavaScript, o mesmo
conjunto de cores entra pela media query. O teste de contraste confere que os
dois blocos têm os mesmos valores.

**Modo minimalista.** Ligado nas Preferências (Aparência), os cards das listas
ficam só com o essencial e as telas perdem o texto de apoio: a receita mostra a
foto, o nome, o selo e o que falta numa linha; o ingrediente, quanto ela tem e
quanto pagou; o prato, o preço e o lucro por porção; cada pergunta fica numa
linha, com o Responder que abre a resposta ali mesmo. Quem esconde é o CSS, pela
variante `minimalista:` do Tailwind; o detalhe de cada item não usa a variante,
porque é lá que ela vai ver as contas.

**Todas as cores trocam**, inclusive creme, seção e a marca escura. O modo
escuro antigo trocava só os neutros, e o creme continuava claro, como um
remendo na tela escura. No escuro, sombra some no fundo: o cartão fica só com a
borda de 1px, e o que flutua (diálogo, folha, aviso) ganha um contorno de 1px
com uma sombra funda.

**A marca se divide em duas.**

- `marca-fundo`, o `#EB0033` medido, é o preenchimento do botão principal e da
  entrada do Conversar, nos dois temas. Branco sobre ele dá 4,58:1.
- `marca` é a cor de texto, ícone e anel de foco. No claro ela é `#D1002D`,
  porque o `#EB0033` como texto cai para 4,28:1 sobre o fundo cinza e 4,13:1
  sobre o creme. No escuro ela é `#FF5A76`: o `#EB0033` como texto sobre
  `#1C1C1E` dá 3,7:1 e reprova.

**Semânticas.** No escuro: sucesso `#4CC38A`, atenção `#F0A04B`, info
`#6AA8FF` e perigo num coral, `#FF8266`, longe do rosa da marca, para bloqueio
não ser lido como botão. No claro, a camada CSS escurece a paleta de base para
o texto passar também sobre a tinta a 10% dos chips e sobre o fundo cinza:
sucesso `#087437`, atenção `#9A4F05`, perigo `#BF0F1C`, info `#155FB5` e
apagado `#666666`. Antes, o chip de atenção dava 4,10:1, o de info 4,33:1 e o
texto de apoio sobre a seção 4,36:1. O cabeçalho deste arquivo continua com a
paleta de base; trocá-lo passa por `make design`, que regenera
`webapp/tokens.tailwind.json`.

A tabela é gerada pela mesma conta que o teste faz, lendo o `globals.css` dos
dois temas (`webapp/src/lib/contraste.test.ts`). Chip é a cor a 10% composta
sobre o fundo indicado, que é como o navegador pinta. Para regenerar depois de
mexer num token: `ATUALIZAR_CONTRASTE=1 npx vitest run src/lib/contraste.test.ts`,
dentro de `webapp/`.

<!-- contraste:inicio -->
| Onde | Frente | Fundo | Claro | Escuro | Mínimo |
|---|---|---|---|---|---|
| Texto corrido sobre o cartão | `texto` | `superficie` | 12,63:1 | 13,90:1 | 4,5:1 |
| Texto corrido sobre o fundo da página | `texto` | `fundo` | 11,79:1 | 15,29:1 | 4,5:1 |
| Texto sobre a faixa creme | `texto` | `creme` | 11,36:1 | 13,25:1 | 4,5:1 |
| Chip neutro | `texto` | `secao` | 11,28:1 | 14,76:1 | 4,5:1 |
| Texto sobre a tinta de alerta | `texto` | `tinta-clara` | 10,95:1 | 12,54:1 | 4,5:1 |
| Títulos e valores sobre o cartão | `tinta` | `superficie` | 17,40:1 | 15,62:1 | 4,5:1 |
| Títulos sobre o fundo da página | `tinta` | `fundo` | 16,24:1 | 17,18:1 | 4,5:1 |
| Texto de apoio sobre o cartão | `apagado` | `superficie` | 5,74:1 | 6,62:1 | 4,5:1 |
| Texto de apoio sobre o fundo | `apagado` | `fundo` | 5,35:1 | 7,28:1 | 4,5:1 |
| Texto de apoio sobre a seção | `apagado` | `secao` | 5,12:1 | 7,03:1 | 4,5:1 |
| Texto de apoio sobre o creme | `apagado` | `creme` | 5,16:1 | 6,31:1 | 4,5:1 |
| Texto de apoio sobre a superfície 2 | `apagado` | `superficie-2` | 5,35:1 | 5,87:1 | 4,5:1 |
| Link e botão secundário sobre o cartão | `marca` | `superficie` | 5,60:1 | 5,65:1 | 4,5:1 |
| Link sobre o fundo da página | `marca` | `fundo` | 5,22:1 | 6,21:1 | 4,5:1 |
| Link sobre a superfície 2 | `marca` | `superficie-2` | 5,22:1 | 5,00:1 | 4,5:1 |
| Botão principal e Conversar | `sobre-marca` | `marca-fundo` | 4,58:1 | 4,58:1 | 4,5:1 |
| Botão principal com o ponteiro em cima | `sobre-marca` | `marca-fundo-escura` | 10,10:1 | 6,21:1 | 4,5:1 |
| Botão de perigo (tirar, apagar) | `superficie` | `perigo` | 6,36:1 | 6,99:1 | 4,5:1 |
| Opção escolhida (segmentado, filtro) | `superficie` | `tinta` | 17,40:1 | 15,62:1 | 4,5:1 |
| Chip da marca | `marca-escura` | `marca` a 10% sobre `superficie` | 8,43:1 | 7,64:1 | 4,5:1 |
| Dá pra fazer, lucro: texto sobre o cartão | `sucesso` | `superficie` | 5,89:1 | 7,68:1 | 4,5:1 |
| Dá pra fazer, lucro: texto sobre o fundo | `sucesso` | `fundo` | 5,50:1 | 8,44:1 | 4,5:1 |
| Dá pra fazer, lucro: chip sobre o cartão | `sucesso` | `sucesso` a 10% sobre `superficie` | 5,09:1 | 6,46:1 | 4,5:1 |
| Dá pra fazer, lucro: chip sobre o fundo | `sucesso` | `sucesso` a 10% sobre `fundo` | 4,77:1 | 7,24:1 | 4,5:1 |
| Falta saber: texto sobre o cartão | `atencao` | `superficie` | 6,00:1 | 7,96:1 | 4,5:1 |
| Falta saber: texto sobre o fundo | `atencao` | `fundo` | 5,60:1 | 8,76:1 | 4,5:1 |
| Falta saber: chip sobre o cartão | `atencao` | `atencao` a 10% sobre `superficie` | 5,20:1 | 6,66:1 | 4,5:1 |
| Falta saber: chip sobre o fundo | `atencao` | `atencao` a 10% sobre `fundo` | 4,87:1 | 7,48:1 | 4,5:1 |
| Não dá, prejuízo: texto sobre o cartão | `perigo` | `superficie` | 6,36:1 | 6,99:1 | 4,5:1 |
| Não dá, prejuízo: texto sobre o fundo | `perigo` | `fundo` | 5,93:1 | 7,69:1 | 4,5:1 |
| Não dá, prejuízo: chip sobre o cartão | `perigo` | `perigo` a 10% sobre `superficie` | 5,33:1 | 5,97:1 | 4,5:1 |
| Não dá, prejuízo: chip sobre o fundo | `perigo` | `perigo` a 10% sobre `fundo` | 4,99:1 | 6,68:1 | 4,5:1 |
| Dá, comprando: texto sobre o cartão | `info` | `superficie` | 6,29:1 | 7,01:1 | 4,5:1 |
| Dá, comprando: texto sobre o fundo | `info` | `fundo` | 5,87:1 | 7,71:1 | 4,5:1 |
| Dá, comprando: chip sobre o cartão | `info` | `info` a 10% sobre `superficie` | 5,43:1 | 5,94:1 | 4,5:1 |
| Dá, comprando: chip sobre o fundo | `info` | `info` a 10% sobre `fundo` | 5,08:1 | 6,66:1 | 4,5:1 |
| Borda de campo de formulário | `borda-campo` | `superficie` | 3,69:1 | 3,67:1 | 3:1 |
| Anel de foco sobre o fundo | `marca` | `fundo` | 5,22:1 | 6,21:1 | 3:1 |
| Barra de proporção sobre o trilho | `marca` | `borda` | 4,69:1 | 4,49:1 | 3:1 |
<!-- contraste:fim -->

## Motion

Duração base **300 ms** com `ease`, medida como dominante no site (306
ocorrências). A escala derivada:

| Uso | Duração |
|---|---|
| Feedback de toque, hover | 150 ms |
| Transição padrão, expandir card | **300 ms** |
| Entrada de painel, troca de tela | 400 ms |
| Contagem de número (preço subindo) | 500 ms |

Tudo respeita `prefers-reduced-motion` e a opção **Reduzir** das Preferências:
com qualquer uma das duas ativa, transições e animações caem para 1 ms.

## Componentes

**Botão primário.** Fundo `marca-fundo` (`#EB0033`), texto branco, radius 8px,
altura 48px. Com o ponteiro em cima vai para `marca-fundo-escura` (`#890019` no
claro). Só ele e a entrada do Conversar usam o vermelho cheio como fundo.

**Card.** Superfície com borda de 1px, radius 12px e a sombra `cartao`
(`1px 1px 10px` a 6% no claro; no escuro, só a borda). Foto quando a receita
ou o ingrediente tiver, servida pela API; gradiente com o ícone do tipo quando
não tiver, na mesma proporção, para a grade não pular.

**Selo de viabilidade.** Chip com radius total, com o texto na língua dela e
nunca o nome interno do veredito: "Dá pra fazer" em `success`, "Dá, comprando"
em `info`, "Falta saber" em `warning`, "Não dá" em `danger`. Nunca em vermelho
de marca, para não confundir bloqueio com ação.

**Linha de custo.** Ingrediente à esquerda, valor à direita em `numero`
(tabular), derivação abaixo em `caption` e `muted`. A derivação nunca é
escondida atrás de tooltip: ela é o produto.

**Cenário de preço.** Três cards lado a lado, sem nenhum marcado como
recomendado. A ausência de destaque é intencional: quem escolhe é a Dona Maria.

## Não fazer

- Vermelho de marca em fundo de alerta de prejuízo: confunde ação com erro.
- Sombra com deslocamento grande. O iFood usa sombra difusa, com deslocamento
  pequeno (2px na superfície do lojista).
- Esconder a derivação de um número atrás de interação. Se o número aparece, a
  conta aparece.
- Marcar um cenário de preço como "recomendado".
- Texto sobre `#ADADAD`.
