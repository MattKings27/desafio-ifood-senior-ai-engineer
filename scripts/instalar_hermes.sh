#!/usr/bin/env bash
#
# Instala o Hermes Agent, da Nous Research, pelo instalador oficial, preso ao
# commit em que este projeto foi medido (v0.21.4, commit ee8a919f).
#
#   scripts/instalar_hermes.sh             instala; se a versão testada já está aí, não faz nada
#   FORCAR=1 scripts/instalar_hermes.sh    leva um Hermes de outra versão ao commit testado
#   SIMULAR=1 scripts/instalar_hermes.sh   só mostra o comando que rodaria
#
# É o comando da documentação do Hermes, com o instalador do commit testado e
# três opções a mais:
#
#   curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/ee8a919fd2769166d45ebf67f45ff5b1acec69fe/scripts/install.sh | bash -s -- \
#     --commit ee8a919fd2769166d45ebf67f45ff5b1acec69fe --skip-setup
#
# - O commit vai inteiro. O instalador clona só a ponta do main (--depth 1) e,
#   com um commit abreviado que não esteja nela, desiste: "Abbreviated SHAs are
#   not supported" (scripts/install.sh do hermes-agent, em clone_repo).
# - --skip-setup: a chave da Anthropic é da pessoa e entra pelo `hermes setup
#   model`, que pergunta sem mostrar. Este script nunca pede nem imprime chave.
# - --skip-browser e --skip-computer-use: o navegador e o controle do computador
#   ficam desligados no perfil do agente (hermes/config.overlay.yaml). Sem eles,
#   o instalador não baixa o Chromium nem o cua-driver, a parte lenta.
#
# O arquivo do instalador é baixado antes de rodar, e não entregue ao bash pelo
# cano: uma conexão que cai no meio não executa meio instalador. Ele roda com a
# entrada em /dev/null, como no `curl | bash` da documentação: o que precisar
# perguntar (o sudo de pacotes opcionais) pergunta pelo terminal.
#
set -Eeuo pipefail

COMMIT="ee8a919fd2769166d45ebf67f45ff5b1acec69fe"
VERSAO="0.21.4"
# O instalador do próprio commit testado: instalador e código ficam presos juntos, e
# uma versão nova do instalador no site da Nous (que já recusa opções desta) não
# muda nada aqui.
URL="${HERMES_INSTALADOR_URL:-https://raw.githubusercontent.com/NousResearch/hermes-agent/$COMMIT/scripts/install.sh}"
FORCAR="${FORCAR:-0}"
SIMULAR="${SIMULAR:-0}"

azul()  { printf '\033[34m→\033[0m %s\n' "$*"; }
ok()    { printf '\033[32m✓\033[0m %s\n' "$*"; }
aviso() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }
erro()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

# O mesmo lugar em que o bootstrap e o Makefile procuram: o PATH, e depois o
# ~/.local/bin, onde o instalador põe o comando (um terminal aberto antes da
# instalação ainda não o tem no PATH).
achar_hermes() {
  local bin
  bin="$(command -v hermes 2>/dev/null || true)"
  [[ -z "$bin" && -x "$HOME/.local/bin/hermes" ]] && bin="$HOME/.local/bin/hermes"
  printf '%s' "$bin"
}

# "0.21.4", ou nada. O `hermes --version` consulta o GitHub e grava um cache na
# pasta do Hermes; com uma pasta descartável, e a consulta desligada nela, a
# pergunta pela versão não sai para a rede nem escreve no ~/.hermes.
versao_do_hermes() {
  local casa saida
  casa="$(mktemp -d "${TMPDIR:-/tmp}/versao-do-hermes.XXXXXX")"
  printf 'updates:\n  check: false\n' >"$casa/config.yaml"
  saida="$(HERMES_HOME="$casa" "$1" --version 2>/dev/null </dev/null || true)"
  rm -rf "$casa"
  printf '%s\n' "$saida" | sed -n 's/.*v\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\).*/\1/p' | head -1 || true
}

proximos_passos() {
  cat <<FIM

  Próximos passos:
    hermes setup model   escolha Anthropic e cole a sua chave (ela fica em ~/.hermes/.env)
    make bootstrap       perfil do agente, skills, guard-rail, servidor MCP e o gateway
    make verificar       confere tudo e diz o comando que conserta cada item

FIM
}

ARGS=(--commit "$COMMIT" --skip-setup --skip-browser --skip-computer-use)

HERMES_BIN="$(achar_hermes)"
if [[ -n "$HERMES_BIN" ]]; then
  atual="$(versao_do_hermes "$HERMES_BIN")"
  if [[ "$atual" == "$VERSAO" ]]; then
    ok "o Hermes $atual já está instalado ($HERMES_BIN), a versão testada: nada a fazer"
    proximos_passos
    exit 0
  fi
  if [[ "$FORCAR" != "1" ]]; then
    aviso "já há um Hermes em $HERMES_BIN, na versão ${atual:-desconhecida}; o projeto foi testado na $VERSAO (commit ${COMMIT:0:8})"
    aviso "ele fica como está. Para levá-lo ao commit testado: make instalar-hermes FORCAR=1"
    exit 0
  fi
  # Sem --force-commit, o instalador ignora um --commit mais antigo que o checkout.
  ARGS+=(--force-commit)
  azul "levando o Hermes ${atual:-de versão desconhecida} ao commit testado (${COMMIT:0:8}, v$VERSAO)"
else
  azul "instalando o Hermes Agent v$VERSAO (commit ${COMMIT:0:8}) pelo instalador oficial"
fi

if [[ "$SIMULAR" == "1" ]]; then
  ok "simulação: baixaria $URL e rodaria"
  printf '    bash install.sh %s\n' "${ARGS[*]}"
  exit 0
fi

command -v curl >/dev/null || erro "sem o curl não dá para baixar o instalador: instale o curl e rode de novo"
command -v git >/dev/null || erro "o instalador do Hermes clona o repositório com o git: instale o git e rode de novo"

PASTA="$(mktemp -d "${TMPDIR:-/tmp}/instalador-do-hermes.XXXXXX")"
trap 'rm -rf "$PASTA"' EXIT

curl -fsSL --retry 3 "$URL" -o "$PASTA/install.sh" \
  || erro "não deu para baixar o instalador de $URL: confira a internet e rode de novo"
ok "instalador oficial baixado de $URL"
azul "rodando o instalador (alguns minutos na primeira vez): bash install.sh ${ARGS[*]}"

if ! bash "$PASTA/install.sh" "${ARGS[@]}" </dev/null; then
  erro "o instalador do Hermes parou com erro (a mensagem dele está logo acima); corrija e rode 'make instalar-hermes' de novo"
fi

HERMES_BIN="$(achar_hermes)"
[[ -n "$HERMES_BIN" ]] \
  || erro "o instalador terminou, mas o comando hermes não apareceu no PATH nem em ~/.local/bin"
instalada="$(versao_do_hermes "$HERMES_BIN")"
[[ "$instalada" == "$VERSAO" ]] \
  || erro "o Hermes em $HERMES_BIN diz versão '${instalada:-?}', e a testada é a $VERSAO: rode 'make instalar-hermes FORCAR=1'"
ok "Hermes $instalada instalado em $HERMES_BIN (commit ${COMMIT:0:8})"

if ! command -v hermes >/dev/null 2>&1; then
  aviso "o comando hermes ainda não está no PATH deste terminal. Abra um terminal novo (o instalador"
  aviso "acrescentou ~/.local/bin ao seu shell) ou rode: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
proximos_passos
