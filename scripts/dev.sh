#!/usr/bin/env bash
#
# O app inteiro para desenvolver: a API do motor e a interface, juntas, com os
# logs prefixados, e as duas derrubadas ao sair (Ctrl-C, erro, ou uma delas cair).
#
# Antes de subir, confere o que costuma faltar: o ambiente Python, o
# webapp/node_modules, as portas livres e o agente (o servidor de API do Hermes).
# O agente fora do ar não impede de subir: o resto do app funciona, e o chat avisa
# que ele está indisponível. Como ligá-lo: docs/runbooks/agente-na-web.md.
#
#   make dev
#   MISE_HTTP_PORT=8778 DEV_PORTA_WEB=3001 scripts/dev.sh     outras portas
#
# Cada serviço sobe na própria sessão (setsid): o Ctrl-C chega só a este script,
# que derruba os dois grupos inteiros, e o `next dev` não fica órfão segurando
# a porta 3000. DEV_CMD_API e DEV_CMD_WEB trocam os comandos (os testes usam).
#
set -Eeuo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$RAIZ/mise/.venv/bin/python"
PORTA_API="${MISE_HTTP_PORT:-8777}"
PORTA_WEB="${DEV_PORTA_WEB:-3000}"
PERFIL="${PERFIL_HERMES:-sabor-da-maria}"

# Os mesmos caminhos que o Makefile exporta para `make api`.
export MISE_PLANILHA="${MISE_PLANILHA:-$RAIZ/dados/despensa_dona_maria.xlsx}"
export MISE_DOSSIE="${MISE_DOSSIE:-$RAIZ/.estado/dossie.db}"
export MISE_AUDITORIA="${MISE_AUDITORIA:-$RAIZ/.estado/auditoria.jsonl}"
# Num clone novo, o catálogo começa com as receitas já lidas, sem resposta dela.
export MISE_CATALOGO_INICIAL="${MISE_CATALOGO_INICIAL:-$RAIZ/dados/catalogo_inicial.json}"

# A busca automática de receitas pede ao agente, em segundo plano, receitas
# da internet, e cada rodada gasta a API do modelo. Aqui ela vem ligada; sem a
# variável (os testes, o CI, `make api`) fica desligada.
# `SABOR_DESCOBERTA=desligada make dev` desliga.
export SABOR_DESCOBERTA="${SABOR_DESCOBERTA:-ligada}"

if [[ -t 1 ]]; then
  pintar() { printf '\033[%sm%s\033[0m' "$1" "$2"; }
else
  pintar() { printf '%s' "$2"; }
fi
ok()    { printf '%s %s\n' "$(pintar 32 ✓)" "$*"; }
aviso() { printf '%s %s\n' "$(pintar 33 !)" "$*" >&2; }
erro()  { printf '%s %s\n' "$(pintar 31 ✗)" "$*" >&2; exit 1; }

porta_ocupada() { (: <"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

# --------------------------------------------------------------------------- #
# O que costuma faltar                                                         #
# --------------------------------------------------------------------------- #

[[ -x "$PY" ]] || erro "sem o ambiente Python em mise/.venv: rode scripts/preparar_ambiente.sh"
"$PY" -c "import gateway.http" 2>/dev/null \
  || erro "o ambiente Python não importa o gateway: rode scripts/preparar_ambiente.sh"
ok "ambiente Python"

[[ -x "$RAIZ/webapp/node_modules/.bin/next" ]] \
  || erro "sem webapp/node_modules: rode (cd webapp && npm ci)"
ok "webapp/node_modules"

for porta in "$PORTA_API" "$PORTA_WEB"; do
  if porta_ocupada "$porta"; then
    erro "a porta $porta já está em uso (outro 'make api' ou 'make web' rodando?); pare-o ou use MISE_HTTP_PORT / DEV_PORTA_WEB"
  fi
done
ok "portas $PORTA_API (API) e $PORTA_WEB (interface) livres"
ok "busca automática de receitas: $SABOR_DESCOBERTA"

if ! "$PY" -m gateway.hermes_operacao status --perfil "$PERFIL" --curto; then
  aviso "o app sobe sem o agente, mas o chat não responde: veja 'make agente-status' e docs/runbooks/agente-na-web.md"
fi

# --------------------------------------------------------------------------- #
# Subir, prefixar, derrubar                                                    #
# --------------------------------------------------------------------------- #

printf -v CMD_API_PADRAO 'MISE_HTTP_PORT=%q exec %q -m gateway.http' "$PORTA_API" "$PY"
printf -v CMD_WEB_PADRAO 'cd %q && MISE_API=%q exec node_modules/.bin/next dev -p %q' \
  "$RAIZ/webapp" "http://127.0.0.1:$PORTA_API" "$PORTA_WEB"
CMD_API="${DEV_CMD_API:-$CMD_API_PADRAO}"
CMD_WEB="${DEV_CMD_WEB:-$CMD_WEB_PADRAO}"

# O macOS não traz o comando setsid; lá, o Python do ambiente abre a sessão
# (os.setsid) e vira o comando, no mesmo processo, como o setsid faz.
if command -v setsid >/dev/null 2>&1; then
  SESSAO_NOVA=(setsid)
else
  SESSAO_NOVA=("$PY" -c 'import os, sys; os.setsid(); os.execvp(sys.argv[1], sys.argv[1:])')
fi

PIDS=()
NOMES=()

prefixar() {
  local prefixo linha
  prefixo="$(pintar "$2" "[$1]")"
  while IFS= read -r linha || [[ -n "$linha" ]]; do
    printf '%s %s\n' "$prefixo" "$linha"
  done
}

subir() {
  "${SESSAO_NOVA[@]}" bash -c "$3" > >(prefixar "$1" "$2") 2>&1 </dev/null &
  PIDS+=("$!")
  NOMES+=("$1")
}

derrubar() {
  local pid vivos
  (( ${#PIDS[@]} )) || return 0
  for pid in "${PIDS[@]}"; do kill -TERM -- "-$pid" 2>/dev/null || true; done
  # Até 10 s para saírem por conta própria (o uvicorn fecha conexões, o next
  # libera a porta); quem sobrar leva KILL.
  for _ in $(seq 1 50); do
    vivos=0
    for pid in "${PIDS[@]}"; do kill -0 -- "-$pid" 2>/dev/null && vivos=1; done
    (( vivos )) || break
    sleep 0.2
  done
  for pid in "${PIDS[@]}"; do kill -KILL -- "-$pid" 2>/dev/null || true; done
}

trap derrubar EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

subir api 34 "$CMD_API"
subir web 35 "$CMD_WEB"
ok "API em http://127.0.0.1:$PORTA_API e interface em http://127.0.0.1:$PORTA_WEB (Ctrl-C derruba as duas)"

# Um cair derruba o outro: meio app no ar só engana quem está testando.
while true; do
  for i in "${!PIDS[@]}"; do
    if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
      codigo=0
      wait "${PIDS[$i]}" || codigo=$?
      aviso "o serviço '${NOMES[$i]}' parou (saída $codigo); derrubando o outro"
      exit $(( codigo == 0 ? 1 : codigo ))
    fi
  done
  sleep 0.5
done
