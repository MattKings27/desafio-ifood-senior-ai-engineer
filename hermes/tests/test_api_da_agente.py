"""A etapa "API do agente" do bootstrap, de ponta a ponta, numa casa de mentira.

Roda o script de verdade (`hermes/api_da_agente.sh`) com `HOME` e `HERMES_HOME`
num diretório temporário, um `hermes` falso no lugar do real (ele só anota com
que argumentos foi chamado) e um servidor de API falso numa porta livre, que
aceita só a chave do perfil. Nada aqui encosta no `~/.hermes` de quem roda os
testes nem no gateway do Hermes que está rodando.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import socket
import stat
import subprocess
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from gateway.hermes_cliente import ler_chave_do_env

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "hermes" / "api_da_agente.sh"
PERFIL = "sabor-da-maria"
AVALIACAO = f"{PERFIL}-avaliacao"
_PREFIXO = re.compile(r"^/p/([^/]+)/api/sessions")


class _ServidorDeApi(http.server.BaseHTTPRequestHandler):
    """`/health` aberto; `/p/<perfil>/api/sessions` só com a chave do `.env` daquele perfil."""

    hermes_home: Path

    def do_GET(self) -> None:
        if self.path == "/health":
            self._responder(
                200, {"status": "ok", "platform": "hermes-agent", "version": "0.21.4"}
            )
            return
        achado = _PREFIXO.match(self.path)
        if not achado:
            self._responder(404, {"error": "Unknown or unconfigured profile"})
            return
        chave = ler_chave_do_env(
            self.hermes_home / "profiles" / achado.group(1) / ".env"
        )
        if (
            chave is None
            or self.headers.get("Authorization") != f"Bearer {chave.revelar()}"
        ):
            self._responder(
                401, {"error": {"message": "Invalid gateway API key (API_SERVER_KEY)"}}
            )
            return
        self._responder(200, {"object": "list", "data": []})

    def _responder(self, status: int, corpo: object) -> None:
        dados = json.dumps(corpo).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def log_message(self, *_args: object) -> None:
        return None


@dataclass
class Casa:
    home: Path
    hermes_home: Path
    log_do_hermes: Path
    ambiente: dict[str, str]

    def env(self, perfil: str = PERFIL) -> Path:
        return (
            self.hermes_home / ".env"
            if perfil == "default"
            else self.hermes_home / "profiles" / perfil / ".env"
        )

    def chave(self, perfil: str = PERFIL) -> str:
        chave = ler_chave_do_env(self.env(perfil))
        assert chave is not None, f"sem chave em {self.env(perfil)}"
        return chave.revelar()

    def gateway_como_servico(self, onde: str = "systemd") -> None:
        """O arquivo que o `hermes gateway install` deixa, no Linux ou no macOS."""
        arquivo = (
            self.home / ".config" / "systemd" / "user" / "hermes-gateway.service"
            if onde == "systemd"
            else self.home / "Library" / "LaunchAgents" / "ai.hermes.gateway.plist"
        )
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text("[Unit]\n", encoding="utf-8")

    def rodar(self, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT)],
            env={**self.ambiente, **extra},
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            check=False,
        )


def _porta_fechada() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def casa(tmp_path: Path) -> Iterator[Casa]:
    home = tmp_path / "casa"
    hermes_home = home / ".hermes"
    for perfil in (PERFIL, AVALIACAO):
        (hermes_home / "profiles" / perfil).mkdir(parents=True)

    binarios = tmp_path / "bin"
    binarios.mkdir()
    log = tmp_path / "hermes-falso.log"
    falso = binarios / "hermes"
    falso.write_text(
        '#!/usr/bin/env bash\necho "$*" >> "$HERMES_FALSO_LOG"\nexit "${HERMES_FALSO_SAIDA:-0}"\n',
        encoding="utf-8",
    )
    falso.chmod(0o755)

    manipulador = type("Servidor", (_ServidorDeApi,), {"hermes_home": hermes_home})
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), manipulador)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    base = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("MISE_HERMES_", "HERMES_"))
        and k not in ("SEM_REINICIAR", "PERFIL_HERMES")
    }
    ambiente = {
        **base,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "HERMES_HOME": str(hermes_home),
        "PY": sys.executable,
        "HERMES_BIN": str(falso),
        "HERMES_FALSO_LOG": str(log),
        "MISE_HERMES_URL": f"http://127.0.0.1:{servidor.server_address[1]}",
        "PERFIL_HERMES": PERFIL,
        "ESPERA_DA_API_S": "5",
    }
    try:
        yield Casa(home, hermes_home, log, ambiente)
    finally:
        servidor.shutdown()
        servidor.server_close()


def _chamadas(casa: Casa) -> str:
    return (
        casa.log_do_hermes.read_text(encoding="utf-8")
        if casa.log_do_hermes.exists()
        else ""
    )


def test_sem_reiniciar_gera_as_duas_chaves_e_confere(casa: Casa) -> None:
    feito = casa.rodar(SEM_REINICIAR="1")
    assert feito.returncode == 0, feito.stderr

    padrao, do_perfil = casa.chave("default"), casa.chave(PERFIL)
    assert padrao != do_perfil, "a do padrão dá 401 em /p/<perfil>/: uma por perfil"
    for valor in (padrao, do_perfil):
        assert re.fullmatch(r"[0-9a-f]{64}", valor)
        assert valor not in feito.stdout
        assert valor not in feito.stderr
    for env in (casa.env("default"), casa.env(PERFIL)):
        assert stat.S_IMODE(env.stat().st_mode) == 0o600

    assert "gateway restart" not in _chamadas(casa)
    assert "SEM_REINICIAR=1" in feito.stderr
    assert "o servidor aceitou a chave do perfil" in feito.stdout
    assert "o chat da web já fala com o agente" in feito.stdout


def test_rodar_de_novo_nao_troca_as_chaves(casa: Casa) -> None:
    casa.rodar(SEM_REINICIAR="1")
    antes = (casa.chave("default"), casa.chave(PERFIL))
    feito = casa.rodar(SEM_REINICIAR="1")
    assert feito.returncode == 0, feito.stderr
    assert (casa.chave("default"), casa.chave(PERFIL)) == antes
    assert feito.stdout.count("chave já existia") == 2


def test_preserva_o_resto_do_env(casa: Casa) -> None:
    casa.env(PERFIL).write_text("OUTRA_VARIAVEL=1\n", encoding="utf-8")
    casa.env(PERFIL).chmod(0o600)
    assert casa.rodar(SEM_REINICIAR="1").returncode == 0
    assert casa.env(PERFIL).read_text(encoding="utf-8").startswith("OUTRA_VARIAVEL=1\n")


def test_reinicia_o_gateway_e_avisa_que_o_chat_para(casa: Casa) -> None:
    casa.gateway_como_servico()
    feito = casa.rodar()
    assert feito.returncode == 0, feito.stderr
    assert "gateway restart" in _chamadas(casa)
    assert "o chat da web de todos os perfis fica sem o agente" in feito.stderr
    assert "gateway reiniciado" in feito.stdout
    assert "o chat da web já fala com o agente" in feito.stdout


def test_reinicio_que_falha_so_avisa(casa: Casa) -> None:
    casa.gateway_como_servico()
    feito = casa.rodar(HERMES_FALSO_SAIDA="3")
    assert feito.returncode == 0
    assert "falhou" in feito.stderr


def test_no_macos_o_servico_e_o_do_launchd(casa: Casa) -> None:
    casa.gateway_como_servico("launchd")
    assert casa.rodar().returncode == 0
    assert "gateway restart" in _chamadas(casa)


_SERVICO_DO_SISTEMA = Path("/etc/systemd/system/hermes-gateway.service")
_sem_servico_do_sistema = pytest.mark.skipif(
    _SERVICO_DO_SISTEMA.exists(),
    reason="esta máquina tem o gateway do Hermes como serviço do sistema",
)


@_sem_servico_do_sistema
def test_sem_o_servico_instala_em_vez_de_reiniciar(casa: Casa) -> None:
    """Sem o serviço, o `gateway restart` do Hermes sobe o gateway em primeiro plano e não volta."""
    feito = casa.rodar()
    assert feito.returncode == 0, feito.stderr
    chamadas = _chamadas(casa)
    assert "gateway install" in chamadas
    assert "gateway restart" not in chamadas
    assert "instalado como serviço" in feito.stdout
    assert "o chat da web já fala com o agente" in feito.stdout


@_sem_servico_do_sistema
def test_servico_que_nao_instala_ensina_a_rodar_no_terminal(casa: Casa) -> None:
    feito = casa.rodar(HERMES_FALSO_SAIDA="1")
    assert feito.returncode == 0, "sem o serviço, o resto do bootstrap segue"
    assert "gateway restart" not in _chamadas(casa)
    assert "hermes gateway run" in feito.stderr


def test_sem_hermes_no_path_nao_tenta_reiniciar(casa: Casa, tmp_path: Path) -> None:
    ambiente = dict(casa.ambiente)
    del ambiente["HERMES_BIN"]
    ambiente["PATH"] = os.pathsep.join(
        p
        for p in ambiente.get("PATH", "").split(os.pathsep)
        if not (Path(p) / "hermes").exists()
    )
    casa.ambiente = ambiente
    feito = casa.rodar()
    assert feito.returncode == 0, feito.stderr
    assert "hermes não encontrado" in feito.stderr


def test_servidor_fora_do_ar_so_avisa(casa: Casa) -> None:
    feito = casa.rodar(
        SEM_REINICIAR="1", MISE_HERMES_URL=f"http://127.0.0.1:{_porta_fechada()}"
    )
    assert feito.returncode == 0, (
        "sem o Hermes o bootstrap segue: o resto do app não depende dele"
    )
    assert "ainda não responde" in feito.stderr
    assert "servidor de API fora do ar" in feito.stdout


def test_perfil_de_avaliacao_ganha_a_propria_chave(casa: Casa) -> None:
    assert casa.rodar(SEM_REINICIAR="1").returncode == 0
    feito = casa.rodar(SEM_REINICIAR="1", PERFIL_HERMES=AVALIACAO)
    assert feito.returncode == 0, feito.stderr
    assert len({casa.chave("default"), casa.chave(PERFIL), casa.chave(AVALIACAO)}) == 3
    assert f"o servidor aceitou a chave do perfil {AVALIACAO}" in feito.stdout


def test_perfil_clonado_com_a_chave_do_padrao_ganha_outra(casa: Casa) -> None:
    """`hermes profile create --clone` copia o `.env` do padrão, com a chave junto."""
    assert casa.rodar(SEM_REINICIAR="1").returncode == 0
    copiada = casa.chave("default")
    casa.env(AVALIACAO).write_text(f"API_SERVER_KEY={copiada}\n", encoding="utf-8")
    feito = casa.rodar(SEM_REINICIAR="1", PERFIL_HERMES=AVALIACAO)
    assert feito.returncode == 0, feito.stderr
    assert casa.chave(AVALIACAO) != copiada
    assert copiada not in casa.env(AVALIACAO).read_text(encoding="utf-8")
    assert "chave trocada" in feito.stdout
    assert f"o servidor aceitou a chave do perfil {AVALIACAO}" in feito.stdout


def test_perfil_inexistente_falha_sem_criar_pasta(casa: Casa) -> None:
    feito = casa.rodar(SEM_REINICIAR="1", PERFIL_HERMES="digitado-errado")
    assert feito.returncode != 0
    assert not (casa.hermes_home / "profiles" / "digitado-errado").exists()


def test_sem_o_python_do_ambiente_falha_cedo(casa: Casa, tmp_path: Path) -> None:
    feito = casa.rodar(SEM_REINICIAR="1", PY=str(tmp_path / "nao-existe" / "python"))
    assert feito.returncode != 0
    assert "preparar_ambiente" in feito.stderr
    assert not casa.env("default").exists()


def test_o_bootstrap_chama_a_etapa() -> None:
    texto = (RAIZ / "hermes" / "bootstrap.sh").read_text(encoding="utf-8")
    assert "hermes/api_da_agente.sh" in texto


def test_o_clone_limpo_nunca_reinicia_o_gateway() -> None:
    """Verificar o clone não pode derrubar o chat de quem roda."""
    texto = (RAIZ / "scripts" / "clone_limpo.sh").read_text(encoding="utf-8")
    chamadas = [
        linha
        for linha in texto.splitlines()
        if "hermes/bootstrap.sh" in linha and not linha.lstrip().startswith("#")
    ]
    assert chamadas
    assert all("SEM_REINICIAR=1" in linha for linha in chamadas)
