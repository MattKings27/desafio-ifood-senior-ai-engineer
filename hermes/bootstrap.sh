#!/usr/bin/env bash
#
# Bootstrap do Sabor da Maria: do repositório clonado ao agente rodando.
#
# Idempotente: rodar de novo é seguro e só conserta o que estiver fora do lugar.
# Tudo vive em `~/.hermes/profiles/sabor-da-maria`. Do perfil `default` do Hermes
# só entra a `API_SERVER_KEY` no `~/.hermes/.env`, se faltar: é ela que abre a
# porta do servidor de API por onde o chat da web fala com o agente (etapa 7).
#
#   ./hermes/bootstrap.sh
#   SEM_REINICIAR=1 ./hermes/bootstrap.sh   sem reiniciar o gateway do Hermes
#
set -Eeuo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PERFIL="${PERFIL_HERMES:-sabor-da-maria}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
DIR_PERFIL="$HERMES_HOME/profiles/$PERFIL"
ESTADO="$RAIZ/.estado"
VENV="$RAIZ/mise/.venv"

azul()  { printf '\033[34m→\033[0m %s\n' "$*"; }
ok()    { printf '\033[32m✓\033[0m %s\n' "$*"; }
aviso() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }
erro()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

trap 'erro "falhou na linha $LINENO"' ERR

# --------------------------------------------------------------------------- #
# 1. Pré-requisitos
# --------------------------------------------------------------------------- #

azul "conferindo pré-requisitos"

command -v python3 >/dev/null || erro "python3 não encontrado"
PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || erro "python 3.11+ necessário (encontrado $PY_VER)"
ok "python $PY_VER"

if command -v uv >/dev/null; then
  UV=uv
elif [[ -x "$HERMES_HOME/bin/uv" ]]; then
  UV="$HERMES_HOME/bin/uv"        # o instalador do Hermes traz um uv gerenciado
else
  aviso "uv não encontrado; usando pip (mais lento)"
  UV=""
fi
[[ -n "$UV" ]] && ok "uv em $UV"

HERMES_BIN="$(command -v hermes || true)"
[[ -z "$HERMES_BIN" && -x "$HOME/.local/bin/hermes" ]] && HERMES_BIN="$HOME/.local/bin/hermes"
if [[ -z "$HERMES_BIN" ]]; then
  aviso "hermes não encontrado no PATH"
  aviso "instale com: make instalar-hermes (o instalador oficial, no commit testado)"
  erro "sem o Hermes não há agente para configurar"
fi
ok "hermes em $HERMES_BIN"

# A versão em que tudo aqui foi medido. O guard-rail depende do nome que o
# Hermes dá às ferramentas MCP e dos argumentos dos hooks; os dois já mudaram de
# forma entre versões. Outra versão menor pode funcionar, mas não foi medida.
HERMES_MEDIDO="0.21"
HERMES_VERSAO="$("$HERMES_BIN" --version 2>/dev/null | sed -n 's/.*v\([0-9][0-9.]*\).*/\1/p' | head -1)"
if [[ "${HERMES_VERSAO%.*}" != "$HERMES_MEDIDO" ]]; then
  aviso "Hermes $HERMES_VERSAO; o projeto foi medido na $HERMES_MEDIDO.x"
  aviso "a medida foi a v0.21.4, commit ee8a919f do hermes-agent"
else
  ok "Hermes $HERMES_VERSAO (medido na $HERMES_MEDIDO.x)"
fi

# --------------------------------------------------------------------------- #
# 2. Ambiente Python
# --------------------------------------------------------------------------- #

azul "preparando o ambiente do motor"

# Os seis pacotes, pelo mesmo script que o CI e a imagem usam. Instalar só
# parte deles fazia o servidor MCP quebrar no import num clone limpo.
"$RAIZ/scripts/preparar_ambiente.sh" "$VENV"
ok "seis pacotes instalados em $(basename "$VENV")"

# --------------------------------------------------------------------------- #
# 3. Perfil isolado do Hermes
# --------------------------------------------------------------------------- #

azul "garantindo o perfil '$PERFIL'"

if [[ ! -d "$DIR_PERFIL" ]]; then
  "$HERMES_BIN" profile create "$PERFIL" --clone \
    --description "Agente de cardapio e precificacao da Dona Maria (desafio iFood)" \
    >/dev/null
  ok "perfil criado"
else
  ok "perfil já existia"
fi

# --------------------------------------------------------------------------- #
# 4. Persona, skills e estado
# --------------------------------------------------------------------------- #

azul "instalando persona e skills"

install -m 644 "$RAIZ/hermes/SOUL.md" "$DIR_PERFIL/SOUL.md"
ok "SOUL.md instalado"

DIR_SKILLS="$DIR_PERFIL/skills/consultoria-gastronomica"
if [[ -d "$RAIZ/hermes/skills/consultoria-gastronomica" ]]; then
  mkdir -p "$DIR_SKILLS"
  cp -r "$RAIZ/hermes/skills/consultoria-gastronomica/." "$DIR_SKILLS/"
  ok "$(find "$DIR_SKILLS" -name SKILL.md | wc -l) skill(s) instalada(s)"
else
  aviso "nenhuma skill em hermes/skills/ ainda"
fi

DIR_PLUGIN="$DIR_PERFIL/plugins/guardrail-numerico"
if [[ -d "$RAIZ/hermes/plugins/guardrail-numerico" ]]; then
  mkdir -p "$DIR_PLUGIN"
  cp "$RAIZ/hermes/plugins/guardrail-numerico/plugin.yaml" \
     "$RAIZ/hermes/plugins/guardrail-numerico/__init__.py" "$DIR_PLUGIN/"
  # O validador do próprio Hermes é o portão de qualidade do plugin.
  if "$HERMES_BIN" plugins validate "$DIR_PLUGIN" >/dev/null 2>&1; then
    "$HERMES_BIN" -p "$PERFIL" plugins enable guardrail-numerico >/dev/null 2>&1 || true
    ok "plugin guardrail-numerico instalado, validado e habilitado"
  else
    aviso "plugin instalado mas não passou em 'hermes plugins validate'"
  fi
fi

mkdir -p "$ESTADO"

# --------------------------------------------------------------------------- #
# 5. Servidor MCP, overlay e skills no perfil
# --------------------------------------------------------------------------- #

azul "registrando o servidor MCP, o overlay e as skills no perfil"

# O caminho real, não o link: o Python monta o ambiente a partir do caminho por
# onde foi chamado, e chamado pelo link em disco do Windows cada import ainda
# atravessava a ponte (o servidor levou 69 s para subir; pelo caminho real, 9 s).
VENV_REAL="$(readlink -f "$VENV")"

# O servidor MCP `mise`, a fusão do config.overlay.yaml e a lista de skills
# genéricas desligadas (todas as do perfil menos as da consultoria), calculada
# de novo a cada execução. Idempotente; detalhes em hermes/configurar_perfil.py.
"$VENV_REAL/bin/python" "$RAIZ/hermes/configurar_perfil.py" \
  "$DIR_PERFIL/config.yaml" "$VENV_REAL" "$RAIZ"
ok "servidor MCP registrado, overlay aplicado e skills genéricas desligadas"

# --------------------------------------------------------------------------- #
# 6. Verificação
# --------------------------------------------------------------------------- #

azul "verificando"

MISE_PLANILHA="$RAIZ/dados/despensa_dona_maria.xlsx" \
MISE_DOSSIE="$ESTADO/dossie.db" \
"$VENV/bin/python" -c "
from mise.mcp_server import abrir_sessao, construir_servidor
from gateway.politica import pilha_padrao, ESCOPOS
s = abrir_sessao()
srv = construir_servidor(s, middleware=pilha_padrao())
assert len(s.despensa) == 37, f'esperava 37 itens, veio {len(s.despensa)}'
print(f'  despensa: {len(s.despensa)} itens, {s.despensa.total_investido} investidos')
print(f'  pendências: {len(s.despensa.pendencias)}')
print(f'  ferramentas: {len(ESCOPOS)} classificadas na allowlist')
s.dossie.fechar()
"
ok "motor carrega a planilha real"

# --------------------------------------------------------------------------- #
# 7. API do agente
# --------------------------------------------------------------------------- #

# O chat da web fala com o agente pelo servidor de API do Hermes. A etapa gera
# as chaves que faltarem, sem mostrá-las, e reinicia o gateway, o que deixa o
# chat sem o agente por alguns segundos. SEM_REINICIAR=1 pula o reinício. Detalhes em hermes/api_da_agente.sh e docs/runbooks/agente-na-web.md.
HERMES_HOME="$HERMES_HOME" PERFIL_HERMES="$PERFIL" PY="$VENV_REAL/bin/python" \
  HERMES_BIN="$HERMES_BIN" "$RAIZ/hermes/api_da_agente.sh"

cat <<FIM

$(printf '\033[32m✓ tudo pronto\033[0m')

  Conversar com o agente:
    hermes -p $PERFIL

  Conferir a integração MCP:
    hermes -p $PERFIL mcp test mise

  Conferir tudo, com o comando que conserta cada item:
    make verificar

  Conversar pela web (API, interface e o agente, em http://localhost:3000):
    make demo         ou make dev, para desenvolver; estado do agente: make agente-status

  Rodar os testes:
    make test

  Estado da consultoria (dossiê, auditoria):
    $ESTADO/

FIM
