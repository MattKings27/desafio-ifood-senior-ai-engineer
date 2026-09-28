"""O `make dev`: sobe a API e a interface juntas e derruba as duas ao sair.

Roda o script de verdade numa cópia mínima do repositório (o script, um Python
que chama o do ambiente e um `next` de mentira), com comandos falsos no lugar da
API e da interface. Cada falso diz o próprio PID e o de um filho, e dorme. O
teste manda Ctrl-C (SIGINT) no script e confere que os quatro morreram: é no
neto que o `next dev` costuma deixar um órfão segurando a porta 3000.
"""

from __future__ import annotations

import os
import queue
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
DEV = RAIZ / "scripts" / "dev.sh"

FALSO = (
    "import os, subprocess, sys, time; "
    "neto = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']); "
    "print(sys.argv[1], 'no ar', os.getpid(), neto.pid, flush=True); "
    "time.sleep(float(sys.argv[2])); "
    "sys.exit(int(sys.argv[3]))"
)


def _falso(nome: str, dorme: float = 120, saida: int = 0) -> str:
    return f"exec {shlex.quote(sys.executable)} -c {shlex.quote(FALSO)} {nome} {dorme} {saida}"


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _vivo(pid: int) -> bool:
    """Zumbi conta como morto: já saiu, só falta alguém recolher."""
    try:
        estado = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (FileNotFoundError, IndexError):
        return False
    return estado != "Z"


def _esperar_morte(pids: list[int], prazo: float = 15) -> list[int]:
    limite = time.monotonic() + prazo
    while time.monotonic() < limite:
        vivos = [pid for pid in pids if _vivo(pid)]
        if not vivos:
            return []
        time.sleep(0.1)
    return [pid for pid in pids if _vivo(pid)]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    raiz = tmp_path / "repo"
    (raiz / "scripts").mkdir(parents=True)
    shutil.copy2(DEV, raiz / "scripts" / "dev.sh")
    binarios = raiz / "mise" / ".venv" / "bin"
    binarios.mkdir(parents=True)
    python = binarios / "python"
    # Um invólucro, não um link: por um link o Python não acharia o pyvenv.cfg
    # do ambiente e perderia os pacotes instalados.
    python.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
    python.chmod(0o755)
    proximo = raiz / "webapp" / "node_modules" / ".bin" / "next"
    proximo.parent.mkdir(parents=True)
    proximo.write_text("#!/bin/sh\nexit 0\n")
    proximo.chmod(0o755)
    return raiz


def _ambiente(tmp_path: Path, **extra: str) -> dict[str, str]:
    base = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("MISE_", "DEV_", "HERMES_", "PERFIL_"))
    }
    casa = tmp_path / "casa"
    (casa / ".hermes").mkdir(parents=True, exist_ok=True)
    return {
        **base,
        "HOME": str(casa),
        "HERMES_HOME": str(casa / ".hermes"),
        "MISE_HTTP_PORT": str(_porta_livre()),
        "DEV_PORTA_WEB": str(_porta_livre()),
        "MISE_HERMES_URL": f"http://127.0.0.1:{_porta_livre()}",
        "DEV_CMD_API": _falso("api"),
        "DEV_CMD_WEB": _falso("web"),
        **extra,
    }


class Dev:
    """O script rodando, com a saída lida numa thread para não travar o pipe."""

    def __init__(self, repo: Path, ambiente: dict[str, str]) -> None:
        self.processo = subprocess.Popen(
            ["bash", str(repo / "scripts" / "dev.sh")],
            env=ambiente,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            start_new_session=True,
        )
        self.linhas: list[str] = []
        self._fila: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._ler, daemon=True).start()

    def _ler(self) -> None:
        assert self.processo.stdout is not None
        for linha in self.processo.stdout:
            self._fila.put(linha.rstrip("\n"))
        self._fila.put(None)

    def esperar_linhas(self, *trechos: str, prazo: float = 60) -> None:
        limite = time.monotonic() + prazo
        while not all(any(t in linha for linha in self.linhas) for t in trechos):
            restante = limite - time.monotonic()
            if restante <= 0:
                pytest.fail(f"não apareceu {trechos} em:\n" + "\n".join(self.linhas))
            try:
                linha = self._fila.get(timeout=restante)
            except queue.Empty:
                continue
            if linha is None:
                pytest.fail(
                    f"o script saiu antes de {trechos}:\n" + "\n".join(self.linhas)
                )
            self.linhas.append(linha)

    def terminar(self, prazo: float = 30) -> int:
        codigo = self.processo.wait(timeout=prazo)
        while True:
            linha = self._fila.get(timeout=5)
            if linha is None:
                return codigo
            self.linhas.append(linha)

    def pids(self, nome: str) -> list[int]:
        for linha in self.linhas:
            if linha.startswith(f"[{nome}] {nome} no ar "):
                return [int(p) for p in linha.split()[-2:]]
        pytest.fail(f"sem PID de {nome} em:\n" + "\n".join(self.linhas))

    def matar(self) -> None:
        if self.processo.poll() is None:
            os.killpg(self.processo.pid, signal.SIGKILL)


@pytest.mark.parametrize(
    ("sinal", "codigo"), [(signal.SIGINT, 130), (signal.SIGTERM, 143)]
)
def test_sobe_os_dois_prefixados_e_derruba_tudo_ao_sair(
    repo: Path, tmp_path: Path, sinal: signal.Signals, codigo: int
) -> None:
    dev = Dev(repo, _ambiente(tmp_path))
    try:
        dev.esperar_linhas("[api] api no ar", "[web] web no ar")
        filhos = dev.pids("api") + dev.pids("web")
        assert all(_vivo(pid) for pid in filhos)
        os.kill(dev.processo.pid, sinal)
        assert dev.terminar() == codigo
        assert _esperar_morte(filhos) == [], "sobrou processo (ou neto) segurando porta"
    finally:
        dev.matar()
    texto = "\n".join(dev.linhas)
    assert "o app sobe sem o agente" in texto, "agente fora do ar é aviso, não bloqueio"
    assert "Ctrl-C derruba as duas" in texto


def test_sem_o_comando_setsid_o_python_abre_a_sessao(
    repo: Path, tmp_path: Path
) -> None:
    """O macOS não traz o setsid: o Python do ambiente faz o mesmo, e o Ctrl-C derruba tudo."""
    binarios = tmp_path / "sem-setsid"
    binarios.mkdir()
    for comando in ("bash", "dirname", "seq", "sleep"):
        caminho = shutil.which(comando)
        assert caminho is not None
        (binarios / comando).symlink_to(caminho)
    dev = Dev(repo, _ambiente(tmp_path, PATH=str(binarios)))
    try:
        dev.esperar_linhas("[api] api no ar", "[web] web no ar")
        filhos = dev.pids("api") + dev.pids("web")
        assert all(_vivo(pid) for pid in filhos)
        os.kill(dev.processo.pid, signal.SIGINT)
        assert dev.terminar() == 130
        assert _esperar_morte(filhos) == [], "sobrou processo (ou neto) segurando porta"
    finally:
        dev.matar()


_MOSTRA_A_DESCOBERTA = (
    "import os, sys, time; "
    "print('api', os.environ.get('SABOR_DESCOBERTA'), flush=True); "
    "time.sleep(120)"
)


@pytest.mark.parametrize(
    ("valor", "esperado"), [(None, "ligada"), ("desligada", "desligada")]
)
def test_a_busca_automatica_vem_ligada_e_se_desliga(
    repo: Path, tmp_path: Path, valor: str | None, esperado: str
) -> None:
    """Cada rodada custa: fora do `make dev` ela nasce desligada, e aqui dá para desligar."""
    ambiente = _ambiente(
        tmp_path,
        DEV_CMD_API=f"exec {shlex.quote(sys.executable)} -c {shlex.quote(_MOSTRA_A_DESCOBERTA)}",
    )
    ambiente.pop("SABOR_DESCOBERTA", None)
    if valor is not None:
        ambiente["SABOR_DESCOBERTA"] = valor
    dev = Dev(repo, ambiente)
    try:
        dev.esperar_linhas(f"[api] api {esperado}", "[web] web no ar")
    finally:
        os.kill(dev.processo.pid, signal.SIGTERM)
        dev.terminar()
        dev.matar()
    assert f"busca automática de receitas: {esperado}" in "\n".join(dev.linhas)


def test_um_que_cai_derruba_o_outro(repo: Path, tmp_path: Path) -> None:
    dev = Dev(repo, _ambiente(tmp_path, DEV_CMD_API=_falso("api", dorme=1.5, saida=3)))
    try:
        dev.esperar_linhas("[api] api no ar", "[web] web no ar")
        web = dev.pids("web")
        assert dev.terminar() == 3
        assert _esperar_morte(web) == []
    finally:
        dev.matar()
    assert any("o serviço 'api' parou (saída 3)" in linha for linha in dev.linhas)


def test_porta_ocupada_para_antes_de_subir(repo: Path, tmp_path: Path) -> None:
    ambiente = _ambiente(tmp_path)
    with socket.socket() as ocupada:
        ocupada.bind(("127.0.0.1", int(ambiente["MISE_HTTP_PORT"])))
        ocupada.listen()
        dev = Dev(repo, ambiente)
        try:
            assert dev.terminar() == 1
        finally:
            dev.matar()
    texto = "\n".join(dev.linhas)
    assert f"a porta {ambiente['MISE_HTTP_PORT']} já está em uso" in texto
    assert "[api]" not in texto


def test_sem_node_modules(repo: Path, tmp_path: Path) -> None:
    shutil.rmtree(repo / "webapp" / "node_modules")
    dev = Dev(repo, _ambiente(tmp_path))
    try:
        assert dev.terminar() == 1
    finally:
        dev.matar()
    assert any("npm ci" in linha for linha in dev.linhas)


def test_sem_o_ambiente_python(repo: Path, tmp_path: Path) -> None:
    shutil.rmtree(repo / "mise")
    dev = Dev(repo, _ambiente(tmp_path))
    try:
        assert dev.terminar() == 1
    finally:
        dev.matar()
    assert any("preparar_ambiente" in linha for linha in dev.linhas)


def test_ambiente_que_nao_importa_o_gateway(repo: Path, tmp_path: Path) -> None:
    (repo / "mise" / ".venv" / "bin" / "python").write_text("#!/bin/sh\nexit 1\n")
    dev = Dev(repo, _ambiente(tmp_path))
    try:
        assert dev.terminar() == 1
    finally:
        dev.matar()
    assert any("não importa o gateway" in linha for linha in dev.linhas)
