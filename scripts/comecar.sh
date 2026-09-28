#!/usr/bin/env bash
# Do clone ao site, num comando: instala o Hermes Agent no commit testado,
# guarda a chave da Anthropic, monta o agente, instala a interface, confere tudo
# e sobe o site em http://localhost:3000. O que já está feito é pulado, então
# rodar de novo depois de um `git pull` só refaz o que mudou.
#
#   make comecar                                  # pede a chave, se faltar
#   ANTHROPIC_API_KEY=... make comecar            # grava a chave sem mostrá-la
#   SIMULAR=1 make comecar                        # só mostra os passos
#
# A chave nunca aparece na tela: vai direto para o ~/.hermes/.env, com
# permissão só do dono, e o resto do projeto confere apenas se ela existe.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"
export PATH="$HOME/.local/bin:$PATH"
ENV_HERMES="${HERMES_HOME:-$HOME/.hermes}/.env"
SIMULAR="${SIMULAR:-}"

passo() { printf '\n\033[1m%s\033[0m\n' "$1"; }
rodar() {
  if [[ -n "$SIMULAR" ]]; then
    echo "  (simulado) $*"
  else
    "$@"
  fi
}

passo "1/6 O Hermes Agent no commit testado"
rodar make instalar-hermes

passo "2/6 A chave da Anthropic"
if grep -q '^ANTHROPIC_API_KEY=.' "$ENV_HERMES" 2>/dev/null; then
  echo "✓ já está no $ENV_HERMES (só a presença é conferida)"
elif [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  if [[ -n "$SIMULAR" ]]; then
    echo "  (simulado) gravaria a chave de ANTHROPIC_API_KEY no $ENV_HERMES"
  else
    mkdir -p "$(dirname "$ENV_HERMES")"
    (umask 077 && printf 'ANTHROPIC_API_KEY=%s\n' "$ANTHROPIC_API_KEY" >>"$ENV_HERMES")
    echo "✓ gravada no $ENV_HERMES, sem aparecer na tela"
  fi
else
  echo "Escolha Anthropic e cole a chave quando o Hermes pedir."
  rodar hermes setup model
fi

passo "3/6 O agente: perfil, skills, guard-rail, MCP e o servidor de API"
rodar make bootstrap

passo "4/6 A interface"
if [[ -d webapp/node_modules ]]; then
  echo "✓ dependências já instaladas"
else
  rodar bash -c "cd webapp && npm ci"
fi

passo "5/6 A conferência"
rodar make verificar

passo "6/6 O site em http://localhost:3000 (Ctrl+C para parar)"
rodar make demo
