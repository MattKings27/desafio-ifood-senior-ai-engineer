#!/usr/bin/env bash
#
# Etapa "API do agente" do bootstrap: liga o servidor de API do Hermes, que é
# por onde o chat da web fala com o agente.
#
# 1. Gera API_SERVER_KEY onde faltar (Python `secrets`, 64 hexadecimais, arquivo
#    em modo 0600), sem nunca imprimir o valor:
#      - no ~/.hermes/.env, do perfil padrão: é ela que faz o gateway abrir a
#        porta 8642 quando sobe;
#      - no .env do perfil: é ela que autentica /p/<perfil>/. A do padrão dá 401
#        ali, então cada perfil tem a sua, os de avaliação inclusive.
# 2. Reinicia o gateway, onde o servidor de API mora: o chat da web fica sem o
#    agente por alguns segundos e volta sozinho. SEM_REINICIAR=1 pula o
#    reinício, e é assim que o clone limpo e o CI rodam (nunca precisam do Hermes).
#    Numa máquina em que o gateway ainda não é serviço do sistema, em vez de
#    reiniciar, instala o serviço, que já sobe com as chaves novas.
# 3. Confere GET /health e um GET autenticado em /p/<perfil>/api/sessions, e diz
#    se deu certo sem mostrar a chave.
#
#   hermes/api_da_agente.sh                        gera, reinicia e confere
#   SEM_REINICIAR=1 hermes/api_da_agente.sh        gera e confere
#   PERFIL_HERMES=sabor-da-maria-avaliacao ...     outro perfil
#
set -Eeuo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PERFIL="${PERFIL_HERMES:-sabor-da-maria}"
PY="${PY:-$RAIZ/mise/.venv/bin/python}"
if [[ -z "${HERMES_BIN:-}" ]]; then
  HERMES_BIN="$(command -v hermes || true)"
  [[ -z "$HERMES_BIN" && -x "$HOME/.local/bin/hermes" ]] && HERMES_BIN="$HOME/.local/bin/hermes"
fi

azul()  { printf '\033[34m→\033[0m %s\n' "$*"; }
ok()    { printf '\033[32m✓\033[0m %s\n' "$*"; }
aviso() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }
erro()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

trap 'erro "falhou na linha $LINENO"' ERR

# O gateway do Hermes como serviço do sistema: systemd no Linux (e no WSL com
# systemd), launchd no macOS, com os nomes que o Hermes 0.21.4 dá ao serviço
# da pasta padrão (hermes_cli/gateway.py: get_service_name, get_systemd_unit_path
# e get_launchd_plist_path).
gateway_e_servico() {
  [[ -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/hermes-gateway.service" \
    || -f /etc/systemd/system/hermes-gateway.service \
    || -f "$HOME/Library/LaunchAgents/ai.hermes.gateway.plist" ]]
}

[[ -x "$PY" ]] || erro "sem o ambiente Python em $PY: rode scripts/preparar_ambiente.sh"

azul "ligando o servidor de API do agente (perfil $PERFIL)"
"$PY" -m gateway.hermes_operacao garantir-chave --perfil "$PERFIL"

if [[ "${SEM_REINICIAR:-0}" == "1" ]]; then
  aviso "SEM_REINICIAR=1: o gateway não foi reiniciado."
  aviso "A chave do perfil padrão só abre a porta depois de 'make reiniciar-agente' (o chat da web fica sem o agente por alguns segundos)."
  espera=0
elif [[ -z "$HERMES_BIN" ]]; then
  aviso "hermes não encontrado: não dá para reiniciar o gateway daqui"
  espera=0
elif gateway_e_servico; then
  aviso "Reiniciando o gateway do Hermes: o chat da web de todos os perfis fica sem o agente por alguns segundos e volta sozinho."
  if saida="$("$HERMES_BIN" gateway restart 2>&1 </dev/null)"; then
    ok "gateway reiniciado"
  else
    printf '%s\n' "$saida" | tail -5 >&2
    aviso "'hermes gateway restart' falhou; confira com 'hermes gateway status'"
  fi
  # O gateway leva um tempo para subir: conecta o MCP do motor e só então abre
  # a porta. A conferência espera por ela em vez de reprovar de cara.
  espera="${ESPERA_DA_API_S:-90}"
else
  # Sem o serviço, o `hermes gateway restart` do 0.21.4 sobe o gateway em
  # primeiro plano e não volta (_cmd_restart termina em run_gateway): numa
  # máquina nova, o bootstrap ficaria parado aqui para sempre. A instalação do
  # serviço, sem terminal na entrada, já o liga e o sobe, agora e a cada login.
  azul "instalando o gateway do Hermes como serviço do sistema (uma vez por máquina)"
  if saida="$("$HERMES_BIN" gateway install 2>&1 </dev/null)"; then
    ok "gateway do Hermes instalado como serviço e ligado"
    espera="${ESPERA_DA_API_S:-90}"
  else
    printf '%s\n' "$saida" | tail -5 >&2
    aviso "não deu para instalar o gateway como serviço (no WSL sem systemd, por exemplo)."
    aviso "Deixe-o aberto num terminal à parte, e o chat da web fala com o agente enquanto o gateway estiver lá: hermes gateway run"
    espera=0
  fi
fi

if "$PY" -m gateway.hermes_operacao status --perfil "$PERFIL" --esperar "$espera"; then
  ok "o chat da web já fala com o agente"
else
  aviso "o servidor de API ainda não responde; veja docs/runbooks/agente-na-web.md"
fi
