"""O `make instalar-hermes`, numa casa de mentira e sem rede.

Roda o script de verdade (`scripts/instalar_hermes.sh`) com `HOME` num
diretório temporário, o instalador oficial trocado por um falso servido por
`file://` e, quando o caso pede, um `hermes` falso no PATH. O instalador falso
anota os argumentos e "instala" um `hermes` falso em `~/.local/bin`, como o
oficial faz. Nada aqui baixa coisa alguma nem encosta no `~/.hermes` de quem
roda os testes.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "instalar_hermes.sh"
COMMIT = "ee8a919fd2769166d45ebf67f45ff5b1acec69fe"

HERMES_FALSO = """#!/usr/bin/env bash
# Um hermes que só sabe dizer a versão, e anota onde procurou a pasta dele.
if [[ "${1:-}" == "--version" ]]; then
  {
    echo "HERMES_HOME=${HERMES_HOME:-}"
    if [[ -f "${HERMES_HOME:-/nao-existe}/config.yaml" ]]; then
      echo "config:$(tr '\\n' ' ' < "$HERMES_HOME/config.yaml")"
    fi
  } >> "$HERMES_FALSO_LOG"
  echo "Hermes Agent v%(versao)s (2026.9.21) · upstream ee8a919f"
  echo "Install directory: /opt/hermes-agent"
  exit 0
fi
exit 3
"""

INSTALADOR_FALSO = """#!/usr/bin/env bash
# O instalador oficial de mentira: anota os argumentos e põe um hermes no ~/.local/bin.
{
  echo "args:$*"
  if [[ -t 0 ]]; then echo "entrada:terminal"; else echo "entrada:outra"; fi
} >> "$INSTALADOR_FALSO_LOG"
if [[ -n "${INSTALADOR_FALSO_SAIDA:-}" ]]; then exit "$INSTALADOR_FALSO_SAIDA"; fi
if [[ -z "${INSTALADOR_FALSO_NAO_INSTALA:-}" ]]; then
  destino="${INSTALADOR_FALSO_DESTINO:-$HOME/.local/bin/hermes}"
  mkdir -p "$(dirname "$destino")"
  cp "$HERMES_QUE_O_INSTALADOR_POE" "$destino"
  chmod +x "$destino"
fi
echo "Installation Complete!"
"""


def _hermes_falso(destino: Path, versao: str) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(HERMES_FALSO % {"versao": versao}, encoding="utf-8")
    destino.chmod(0o755)
    return destino


def _path_sem_hermes() -> list[str]:
    """O PATH de quem roda os testes, menos as pastas que têm um `hermes` de verdade."""
    return [
        pasta
        for pasta in os.environ.get("PATH", "").split(os.pathsep)
        if pasta and not (Path(pasta) / "hermes").exists()
    ]


@dataclass
class Casa:
    home: Path
    binarios: Path
    log_do_instalador: Path
    log_do_hermes: Path
    ambiente: dict[str, str]

    def rodar(self, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT)],
            env={**self.ambiente, **extra},
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
            stdin=subprocess.DEVNULL,
        )

    def chamadas_do_instalador(self) -> list[str]:
        if not self.log_do_instalador.exists():
            return []
        return self.log_do_instalador.read_text(encoding="utf-8").splitlines()

    def com_hermes_no_path(self, versao: str) -> Path:
        return _hermes_falso(self.binarios / "hermes", versao)


@pytest.fixture
def casa(tmp_path: Path) -> Casa:
    home = tmp_path / "casa"
    home.mkdir()
    binarios = tmp_path / "bin"
    binarios.mkdir()
    instalador = tmp_path / "install.sh"
    instalador.write_text(INSTALADOR_FALSO, encoding="utf-8")
    instalado = _hermes_falso(tmp_path / "o-que-o-instalador-poe" / "hermes", "0.21.4")

    ambiente = {
        chave: valor
        for chave, valor in os.environ.items()
        if not chave.startswith(("HERMES_", "FORCAR", "SIMULAR", "INSTALADOR_FALSO"))
    }
    ambiente.update(
        {
            "HOME": str(home),
            "PATH": os.pathsep.join([str(binarios), *_path_sem_hermes()]),
            "TMPDIR": str(tmp_path),
            "HERMES_INSTALADOR_URL": instalador.as_uri(),
            "INSTALADOR_FALSO_LOG": str(tmp_path / "instalador.log"),
            "HERMES_FALSO_LOG": str(tmp_path / "hermes.log"),
            "HERMES_QUE_O_INSTALADOR_POE": str(instalado),
        }
    )
    return Casa(
        home, binarios, tmp_path / "instalador.log", tmp_path / "hermes.log", ambiente
    )


def test_sem_hermes_roda_o_instalador_oficial_no_commit_testado(casa: Casa) -> None:
    feito = casa.rodar()
    assert feito.returncode == 0, feito.stderr

    [args, entrada] = casa.chamadas_do_instalador()
    assert args == (
        f"args:--commit {COMMIT} --skip-setup --skip-browser --skip-computer-use"
    )
    assert entrada == "entrada:outra", (
        "roda como o `curl | bash`, sem o terminal na entrada"
    )
    assert "Hermes 0.21.4 instalado" in feito.stdout
    assert "hermes setup model" in feito.stdout
    assert "make bootstrap" in feito.stdout


def test_avisa_quando_o_hermes_novo_nao_esta_no_path(casa: Casa) -> None:
    feito = casa.rodar()
    assert feito.returncode == 0, feito.stderr
    assert "ainda não está no PATH deste terminal" in feito.stderr
    assert "terminal novo" in feito.stderr


def test_ja_instalado_na_versao_testada_nao_faz_nada(casa: Casa) -> None:
    casa.com_hermes_no_path("0.21.4")
    feito = casa.rodar()
    assert feito.returncode == 0, feito.stderr
    assert "já está instalado" in feito.stdout
    assert "nada a fazer" in feito.stdout
    assert casa.chamadas_do_instalador() == []


def test_rodar_duas_vezes_instala_uma(casa: Casa) -> None:
    assert casa.rodar().returncode == 0
    segunda = casa.rodar()
    assert segunda.returncode == 0, segunda.stderr
    assert "já está instalado" in segunda.stdout
    assert len(casa.chamadas_do_instalador()) == 2, (
        "uma chamada: os argumentos e a entrada"
    )


def test_perguntar_a_versao_nao_escreve_na_pasta_do_hermes(casa: Casa) -> None:
    """O `hermes --version` roda numa pasta descartável, com a consulta ao GitHub desligada."""
    casa.com_hermes_no_path("0.21.4")
    assert casa.rodar().returncode == 0
    anotado = casa.log_do_hermes.read_text(encoding="utf-8")
    [pasta] = re.findall(r"^HERMES_HOME=(.*)$", anotado, flags=re.MULTILINE)
    assert pasta, "sem HERMES_HOME, o Hermes gravaria o cache em ~/.hermes"
    assert not pasta.startswith(str(casa.home))
    assert re.search(r"updates:\s+check: false", anotado)
    assert not Path(pasta).exists(), "a pasta descartável é apagada"
    assert not (casa.home / ".hermes").exists()


def test_outra_versao_fica_como_esta_sem_forcar(casa: Casa) -> None:
    casa.com_hermes_no_path("0.22.0")
    feito = casa.rodar()
    assert feito.returncode == 0, feito.stderr
    assert "0.22.0" in feito.stderr
    assert "FORCAR=1" in feito.stderr
    assert casa.chamadas_do_instalador() == []


def test_forcar_leva_outra_versao_ao_commit_testado(casa: Casa) -> None:
    hermes = casa.com_hermes_no_path("0.22.0")
    # O instalador de verdade troca o checkout por trás do mesmo comando.
    feito = casa.rodar(FORCAR="1", INSTALADOR_FALSO_DESTINO=str(hermes))
    assert feito.returncode == 0, feito.stderr
    [args, _entrada] = casa.chamadas_do_instalador()
    assert args == (
        f"args:--commit {COMMIT} --skip-setup --skip-browser --skip-computer-use"
        " --force-commit"
    ), "sem --force-commit, o instalador ignora um commit mais antigo que o checkout"
    assert "Hermes 0.21.4 instalado" in feito.stdout


def test_versao_errada_depois_de_instalar_para_com_erro(
    casa: Casa, tmp_path: Path
) -> None:
    errado = _hermes_falso(tmp_path / "errado" / "hermes", "0.20.0")
    feito = casa.rodar(HERMES_QUE_O_INSTALADOR_POE=str(errado))
    assert feito.returncode != 0
    assert "0.20.0" in feito.stderr
    assert "FORCAR=1" in feito.stderr


def test_instalador_que_falha_para_com_erro(casa: Casa) -> None:
    feito = casa.rodar(INSTALADOR_FALSO_SAIDA="7")
    assert feito.returncode != 0
    assert "parou com erro" in feito.stderr


def test_instalador_que_nao_poe_o_comando_para_com_erro(casa: Casa) -> None:
    feito = casa.rodar(INSTALADOR_FALSO_NAO_INSTALA="1")
    assert feito.returncode != 0
    assert "não apareceu" in feito.stderr


def test_sem_rede_para_antes_de_rodar_qualquer_coisa(
    casa: Casa, tmp_path: Path
) -> None:
    feito = casa.rodar(HERMES_INSTALADOR_URL=(tmp_path / "nao-existe.sh").as_uri())
    assert feito.returncode != 0
    assert "não deu para baixar" in feito.stderr
    assert casa.chamadas_do_instalador() == []


def test_simular_mostra_o_comando_e_nao_baixa_nada(casa: Casa, tmp_path: Path) -> None:
    feito = casa.rodar(
        SIMULAR="1", HERMES_INSTALADOR_URL=(tmp_path / "nao-existe.sh").as_uri()
    )
    assert feito.returncode == 0, feito.stderr
    assert f"--commit {COMMIT} --skip-setup" in feito.stdout
    assert casa.chamadas_do_instalador() == []


def test_nunca_pede_nem_mostra_chave(casa: Casa) -> None:
    feito = casa.rodar()
    saida = feito.stdout + feito.stderr
    assert "ANTHROPIC_API_KEY=" not in saida
    assert "--api-key" not in SCRIPT.read_text(encoding="utf-8")


def test_o_commit_e_a_versao_sao_os_que_o_projeto_mediu() -> None:
    """O script, o bootstrap e o overlay falam do mesmo Hermes."""
    script = SCRIPT.read_text(encoding="utf-8")
    assert f'COMMIT="{COMMIT}"' in script
    assert 'VERSAO="0.21.4"' in script
    bootstrap = (RAIZ / "hermes" / "bootstrap.sh").read_text(encoding="utf-8")
    assert f"commit {COMMIT[:8]}" in bootstrap
    assert "v0.21.4" in bootstrap
    overlay = (RAIZ / "hermes" / "config.overlay.yaml").read_text(encoding="utf-8")
    assert "Hermes 0.21.4" in overlay


def test_o_makefile_expoe_o_alvo() -> None:
    makefile = (RAIZ / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^instalar-hermes:.*## ", makefile, flags=re.MULTILINE)
    assert "scripts/instalar_hermes.sh" in makefile
