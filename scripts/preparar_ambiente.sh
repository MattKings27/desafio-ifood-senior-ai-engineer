#!/usr/bin/env bash
#
# Monta o ambiente Python do projeto, num venv.
#
# O bootstrap, o clone limpo e a imagem Docker chamam este script, e nenhum
# deles lista pacote por conta própria. Quando cada porta tinha a sua lista, o
# bootstrap instalava dois pacotes de seis, o gateway importava `telemetria`, e
# o agente subia sem nenhuma ferramenta do motor. Só funcionava na máquina de
# quem escreveu, porque o venv dela tinha sido remendado à mão. O CI é a
# exceção: não usa venv, e instala os mesmos seis pacotes de PACOTES com pip,
# no Python do runner.
#
#   scripts/preparar_ambiente.sh [VENV] [--sem-dev]
#
# VENV padrão: mise/.venv. `--sem-dev` pula ferramentas de teste (imagem Docker).
#
set -Eeuo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$RAIZ/mise/.venv"
VENV_PADRAO=1
DEV=1
for arg in "$@"; do
  case "$arg" in
    --sem-dev) DEV=0 ;;
    -*) echo "opção desconhecida: $arg" >&2; exit 2 ;;
    *) VENV="$arg"; VENV_PADRAO=0 ;;
  esac
done

# No WSL, com o repositório num disco do Windows (/mnt/c, /mnt/d), cada `stat`
# atravessa a ponte entre os dois sistemas e custa milissegundos. Importar o
# pacote `mcp` faz mais de mil deles: o servidor do motor chegou a levar mais de
# um minuto para subir, o Hermes desistiu da conexão e o agente conversou sem
# nenhuma ferramenta, sem aviso. O ambiente vai para o disco do Linux, e
# `mise/.venv` vira um link para ele, para o resto do projeto não mudar.
if (( VENV_PADRAO )) && grep -qi microsoft /proc/version 2>/dev/null && [[ "$RAIZ" == /mnt/[a-z]/* ]]; then
  RAPIDO="${XDG_CACHE_HOME:-$HOME/.cache}/sabor-da-maria/$(printf '%s' "$RAIZ" | sha256sum | cut -c1-12)/venv"
  if [[ -d "$VENV" && ! -L "$VENV" ]]; then
    # Um ambiente que já existe não é movido nem apagado por este script: pode
    # estar em uso, e o Windows nem deixa. Segue com ele, avisando.
    echo "aviso: o ambiente $VENV está no disco do Windows e deixa o servidor do" >&2
    echo "motor lento para subir. Apague a pasta e rode de novo para criá-lo no disco" >&2
    echo "do Linux ($RAPIDO)." >&2
  else
    mkdir -p "$(dirname "$RAPIDO")"
    [[ -L "$VENV" ]] || ln -s "$RAPIDO" "$VENV"
    VENV="$RAPIDO"
  fi
fi

# A ordem não importa para o resolvedor, mas todos vão no MESMO comando: os
# pacotes locais dependem uns dos outros por nome (`mise`, `retrieval`), e um
# `pip install` separado iria procurar esses nomes no PyPI.
PACOTES=(mise gateway retrieval telemetria auditor evals)

alvos=()
for p in "${PACOTES[@]}"; do
  if (( DEV )); then alvos+=(-e "$RAIZ/$p[dev]"); else alvos+=("$RAIZ/$p"); fi
done

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
if command -v uv >/dev/null; then UV=uv
elif [[ -x "$HERMES_HOME/bin/uv" ]]; then UV="$HERMES_HOME/bin/uv"
else UV=""; fi

if [[ ! -x "$VENV/bin/python" ]]; then
  if [[ -n "$UV" ]]; then "$UV" venv --python 3.12 "$VENV" -q
  else python3 -m venv "$VENV"; fi
fi

if [[ -n "$UV" ]]; then
  VIRTUAL_ENV="$VENV" "$UV" pip install -q "${alvos[@]}"
else
  "$VENV/bin/python" -m pip install -q --upgrade pip
  "$VENV/bin/python" -m pip install -q "${alvos[@]}"
fi

# Prova de que o ambiente serve para as três portas, e não só para os testes:
# o servidor MCP que o Hermes sobe, a API que a interface chama e o avaliador.
"$VENV/bin/python" - <<'PYTHON'
import importlib

for modulo in (
    "mise.mcp_server",
    "gateway.principal",
    "gateway.http",
    "gateway.politica",
    "retrieval.busca",
    "retrieval.indice",
    "telemetria.rastro",
    "auditor",
    "evals",
):
    importlib.import_module(modulo)
print("ambiente pronto: 6 pacotes, 9 pontos de entrada importam")
PYTHON
