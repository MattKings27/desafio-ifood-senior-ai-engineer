"""Testes do portão de cobertura do diff.

Um portão sem teste é a coisa exata que o portão existe para impedir. Os casos
que mais importam aqui não são os felizes: são os que decidem entre "reprovou"
e "não consegui decidir", porque confundir os dois transforma um scanner quebrado
numa tela verde.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cobertura_do_diff as portao

# --------------------------------------------------------------------------- #
# Compressão de faixas                                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ([], ""),
        ([7], "7"),
        ([3, 4, 5], "3-5"),
        ([3, 4, 5, 9], "3-5, 9"),
        ([1, 3, 5], "1, 3, 5"),
        ([1, 2, 4, 5, 6, 10], "1-2, 4-6, 10"),
    ],
)
def test_faixas_agrupa_consecutivos(entrada: list[int], esperado: str) -> None:
    assert portao._faixas(entrada) == esperado


# --------------------------------------------------------------------------- #
# Leitura do XML de cobertura                                                  #
# --------------------------------------------------------------------------- #


def _escrever_xml(
    destino: Path, origem: str, arquivo: str, linhas: dict[int, int]
) -> Path:
    marcas = "".join(
        f'<line number="{n}" hits="{h}"/>' for n, h in sorted(linhas.items())
    )
    destino.write_text(
        '<?xml version="1.0" ?>'
        f"<coverage><sources><source>{origem}</source></sources>"
        f'<packages><package><classes><class filename="{arquivo}">'
        f"<lines>{marcas}</lines></class></classes></package></packages></coverage>",
        encoding="utf-8",
    )
    return destino


def test_linhas_medidas_resolve_caminho_relativo_a_raiz(tmp_path, monkeypatch) -> None:
    """O XML guarda o caminho relativo à `source`; o git, relativo à raiz."""
    raiz = tmp_path
    (raiz / "pacote" / "src").mkdir(parents=True)
    monkeypatch.chdir(raiz)

    xml = _escrever_xml(
        raiz / "cov.xml",
        origem=str(raiz / "pacote" / "src"),
        arquivo="modulo.py",
        linhas={10: 1, 11: 0},
    )
    medidas = portao.linhas_medidas([xml])

    assert medidas["pacote/src/modulo.py"] == {10: True, 11: False}
    # O nome cru também é registrado, porque nem todo relatório traz `source`.
    assert "modulo.py" in medidas


def test_linhas_medidas_une_relatorios_com_ou(tmp_path, monkeypatch) -> None:
    """Coberta num relatório e não no outro conta como coberta."""
    monkeypatch.chdir(tmp_path)
    a = _escrever_xml(tmp_path / "a.xml", str(tmp_path), "m.py", {5: 0})
    b = _escrever_xml(tmp_path / "b.xml", str(tmp_path), "m.py", {5: 1})

    assert portao.linhas_medidas([a, b])["m.py"][5] is True
    assert portao.linhas_medidas([b, a])["m.py"][5] is True


def test_relatorio_ausente_nao_decide(tmp_path) -> None:
    with pytest.raises(portao.NaoDecidiu, match="ausente"):
        portao.linhas_medidas([tmp_path / "nao-existe.xml"])


def test_xml_corrompido_nao_decide(tmp_path) -> None:
    ruim = tmp_path / "ruim.xml"
    ruim.write_text("<coverage><nao fecha", encoding="utf-8")
    with pytest.raises(portao.NaoDecidiu, match="XML"):
        portao.linhas_medidas([ruim])


# --------------------------------------------------------------------------- #
# Leitura do diff                                                              #
# --------------------------------------------------------------------------- #


def _repo(tmp_path: Path) -> Path:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q", "-b", "principal")
    git("config", "user.email", "teste@exemplo.invalido")
    git("config", "user.name", "Teste")
    (tmp_path / "m.py").write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    return tmp_path


def test_linhas_alteradas_pega_so_o_lado_novo(tmp_path, monkeypatch) -> None:
    raiz = _repo(tmp_path)
    monkeypatch.chdir(raiz)

    (raiz / "m.py").write_text("a = 1\nb = 22\nc = 3\nd = 4\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=raiz, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "muda"], cwd=raiz, check=True, capture_output=True
    )

    alteradas = portao.linhas_alteradas("principal~1", "HEAD")
    # Linha 2 reescrita e linha 4 acrescentada. A 1 e a 3 não foram tocadas.
    assert alteradas["m.py"] == {2, 4}


def test_arquivo_novo_conta_inteiro(tmp_path, monkeypatch) -> None:
    raiz = _repo(tmp_path)
    monkeypatch.chdir(raiz)

    (raiz / "novo.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=raiz, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "novo"], cwd=raiz, check=True, capture_output=True
    )

    assert portao.linhas_alteradas("principal~1", "HEAD")["novo.py"] == {1, 2}


def test_base_inexistente_nao_decide(tmp_path, monkeypatch) -> None:
    """Clone raso em CI cai aqui. Tem que virar 'não decidi', não 'passou'."""
    raiz = _repo(tmp_path)
    monkeypatch.chdir(raiz)
    with pytest.raises(portao.NaoDecidiu, match="git diff falhou"):
        portao.linhas_alteradas("origin/nao-existe", "HEAD")


# --------------------------------------------------------------------------- #
# Veredito de ponta a ponta                                                    #
# --------------------------------------------------------------------------- #


def _rodar(monkeypatch, argumentos: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["cobertura_do_diff.py", *argumentos])
    return portao.main()


def test_reprova_quando_linha_nova_nao_tem_teste(tmp_path, monkeypatch, capsys) -> None:
    raiz = _repo(tmp_path)
    monkeypatch.chdir(raiz)
    (raiz / "m.py").write_text("a = 1\nb = 2\nc = 3\nd = 4\ne = 5\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=raiz, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "duas novas"],
        cwd=raiz,
        check=True,
        capture_output=True,
    )
    xml = _escrever_xml(raiz / "cov.xml", str(raiz), "m.py", {4: 0, 5: 0})

    assert _rodar(monkeypatch, ["--base", "principal~1", str(xml)]) == 1
    assert "0.0%" in capsys.readouterr().out


def test_aprova_quando_linha_nova_tem_teste(tmp_path, monkeypatch) -> None:
    raiz = _repo(tmp_path)
    monkeypatch.chdir(raiz)
    (raiz / "m.py").write_text("a = 1\nb = 2\nc = 3\nd = 4\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=raiz, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "uma nova"],
        cwd=raiz,
        check=True,
        capture_output=True,
    )
    xml = _escrever_xml(raiz / "cov.xml", str(raiz), "m.py", {4: 1})

    assert _rodar(monkeypatch, ["--base", "principal~1", str(xml)]) == 0


def test_markdown_alterado_nao_exige_cobertura(tmp_path, monkeypatch, capsys) -> None:
    """PR só de documentação não pode ser reprovado por falta de teste."""
    raiz = _repo(tmp_path)
    monkeypatch.chdir(raiz)
    (raiz / "LEIA.md").write_text("texto\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=raiz, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "doc"], cwd=raiz, check=True, capture_output=True
    )
    xml = _escrever_xml(raiz / "cov.xml", str(raiz), "m.py", {1: 1})

    assert _rodar(monkeypatch, ["--base", "principal~1", str(xml)]) == 0
    assert "nenhuma linha executável" in capsys.readouterr().out


def test_sem_veredito_sai_com_dois(tmp_path, monkeypatch, capsys) -> None:
    """O caso que mais importa: não conseguir decidir nunca é verde."""
    raiz = _repo(tmp_path)
    monkeypatch.chdir(raiz)

    assert _rodar(monkeypatch, ["--base", "origin/fantasma", "cov.xml"]) == 2
    assert "sem veredito" in capsys.readouterr().err


def test_linha_nao_executavel_fica_de_fora(tmp_path, monkeypatch, capsys) -> None:
    """Comentário e linha em branco não entram na conta e não puxam o número."""
    raiz = _repo(tmp_path)
    monkeypatch.chdir(raiz)
    (raiz / "m.py").write_text(
        "a = 1\nb = 2\nc = 3\n# comentario\n\nd = 4\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=raiz, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "mistura"],
        cwd=raiz,
        check=True,
        capture_output=True,
    )
    # Só a 6 é executável; 4 e 5 não aparecem no relatório.
    xml = _escrever_xml(raiz / "cov.xml", str(raiz), "m.py", {6: 1})

    assert _rodar(monkeypatch, ["--base", "principal~1", str(xml)]) == 0
    assert "1/1 linhas = 100.0%" in capsys.readouterr().out
