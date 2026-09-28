#!/usr/bin/env bash
#
# O repositório visto por quem acabou de cloná-lo.
#
# Clona o commit atual num diretório vazio e sobe tudo do zero: venv novo, os
# seis pacotes, os testes. Nada do ambiente de quem desenvolve vaza para dentro,
# e é esse o ponto: um venv remendado à mão escondeu por semanas que o gateway
# não subia fora desta máquina.
#
#   scripts/clone_limpo.sh               ambiente + testes
#   scripts/clone_limpo.sh --com-hermes  também instala o agente num perfil
#                                        descartável e testa o servidor MCP
#
# Testa o que está commitado. Mudança fora de commit não entra no clone, de
# propósito: é o que o avaliador recebe.
#
set -Eeuo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COM_HERMES=0
[[ "${1:-}" == "--com-hermes" ]] && COM_HERMES=1

ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
etapa(){ printf '\n\033[34m── %s\033[0m\n' "$*"; }
falha(){ printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

DESTINO="$(mktemp -d "${TMPDIR:-/tmp}/clone-limpo.XXXXXX")"
PERFIL="sabor-da-maria-verificacao"
limpar() {
  if (( COM_HERMES )) && command -v hermes >/dev/null; then
    hermes profile delete -y "$PERFIL" >/dev/null 2>&1 || true
  fi
  rm -rf "$DESTINO"
}
trap limpar EXIT

etapa "clonando $(git -C "$RAIZ" rev-parse --short HEAD)"
git clone -q --no-local "$RAIZ" "$DESTINO/repo"
cd "$DESTINO/repo"
ok "clone em $DESTINO/repo"

etapa "permissões de execução"
# Todo arquivo com shebang precisa do bit no índice do git. O sistema de
# arquivos do Windows não guarda o bit, e o README manda rodar
# `./hermes/bootstrap.sh`, que sem ele falha antes da primeira linha.
sem_bit=()
while IFS= read -r -d '' arquivo; do
  if [[ "$(head -c 2 "$arquivo")" == "#!" ]] \
     && [[ "$(git ls-files -s -- "$arquivo" | cut -c1-6)" != "100755" ]]; then
    sem_bit+=("$arquivo")
  fi
done < <(git ls-files -z -- '*.sh' '*.py' '.githooks/*')
(( ${#sem_bit[@]} == 0 )) || falha "sem bit de execução no git: ${sem_bit[*]}"
ok "todo script com shebang é executável"

etapa "ambiente Python do zero"
scripts/preparar_ambiente.sh
ok "ambiente montado só com o que está declarado"

etapa "testes"
make test
ok "make test passou no clone"

if (( COM_HERMES )); then
  etapa "agente num perfil descartável ($PERFIL)"
  command -v hermes >/dev/null || falha "hermes não está no PATH"
  # SEM_REINICIAR=1: verificar o clone não pode derrubar o chat de quem roda.
  SEM_REINICIAR=1 PERFIL_HERMES="$PERFIL" ./hermes/bootstrap.sh
  saida="$(hermes -p "$PERFIL" mcp test mise 2>&1)" || { echo "$saida"; falha "mcp test mise falhou"; }
  echo "$saida" | tail -5
  ok "o Hermes enxerga as ferramentas do motor"
fi

printf '\n\033[32m✓ clone limpo aprovado\033[0m\n'
