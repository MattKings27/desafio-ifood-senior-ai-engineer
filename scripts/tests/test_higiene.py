"""A higiene do texto versionado: acha o que deve, onde deve, e só isso."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import higiene

# Montados por partes, para que este arquivo não carregue o que ele procura.
TRAVESSAO = "\u2014"
MEIA_RISCA = "\u2013"
CASA = "/" + "home/alguem/projeto"
DISCO = "/" + "mnt/d/trabalho"
WINDOWS = "C:" + "\\" + "Users"


@pytest.mark.parametrize(
    "texto",
    [
        f"o preço sobe {TRAVESSAO} e ela perde",
        f"uma frase {MEIA_RISCA} outra",
        f"termina assim {TRAVESSAO}\ne continua na outra linha",
        f"{TRAVESSAO} começa assim",
    ],
)
def test_travessao_separando_ideias_e_achado(texto: str) -> None:
    [achado] = higiene.achados_no_texto("mise/src/mise/a.py", texto)
    assert achado.regra == "travessão separando ideias"


@pytest.mark.parametrize(
    "texto",
    [
        f'semValor = "{TRAVESSAO}",',
        f"propor 2{MEIA_RISCA}3 cenários",
        "um hífen-composto e uma conta a - b",
    ],
)
def test_travessao_como_simbolo_ou_faixa_fica(texto: str) -> None:
    assert higiene.achados_no_texto("webapp/src/componentes/Valor.tsx", texto) == []


@pytest.mark.parametrize(
    "texto", [f"veja {CASA}/a.py", f"cd {DISCO}/repo", f"{WINDOWS}\\alguem"]
)
def test_caminho_de_uma_maquina_e_achado(texto: str) -> None:
    [achado] = higiene.achados_no_texto("docs/como-rodar.md", texto)
    assert achado.regra == "caminho de uma máquina"
    assert achado.linha == 1


@pytest.mark.parametrize(
    "texto",
    [
        "o WSL monta o disco do Windows em /mnt/c",
        r're.compile(r"(?i:\bmotor\b)")',
        "https://exemplo.com.br/home/receitas",
        "ls ~/.hermes/profiles",
    ],
)
def test_caminho_que_nao_e_de_ninguem_fica(texto: str) -> None:
    assert higiene.achados_no_texto("scripts/a.sh", texto) == []


def test_plural_com_parenteses_na_tela_e_achado_com_a_linha() -> None:
    texto = "const aviso = `${n} receita(s) prontas`;\n<p>Faltam item(s)</p>\n"
    achados = higiene.achados_no_texto("webapp/src/componentes/Aviso.tsx", texto)
    assert [(a.regra, a.linha) for a in achados] == [
        ("plural com (s)", 1),
        ("plural com (s)", 2),
    ]


def test_plural_em_codigo_teste_ou_fora_da_tela_fica() -> None:
    assert (
        higiene.achados_no_texto(
            "webapp/src/lib/a.ts", "lista.filter((s) => Boolean(s));"
        )
        == []
    )
    assert higiene.achados_no_texto("webapp/src/lib/a.test.ts", 'it("1 item(s)")') == []
    assert (
        higiene.achados_no_texto("webapp/e2e/fumaca.spec.ts", 'it("1 item(s)")') == []
    )
    assert higiene.achados_no_texto("gateway/src/gateway/a.py", '"1 item(s)"') == []


def test_gravacoes_ficam_como_vieram() -> None:
    sujo = f"a {TRAVESSAO} b em {CASA}"
    assert higiene.achados_no_texto("docs/transcricoes/x/execucao-1.json", sujo) == []
    assert higiene.achados_no_texto("scripts/tests/fixtures/paginas.json", sujo) == []


def test_main_reprova_com_arquivo_e_linha_e_pula_binario(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.md").write_text(
        f"linha boa\numa {TRAVESSAO} ruim\n", encoding="utf-8"
    )
    (tmp_path / "b.bin").write_bytes(b"\0\1" + f" {TRAVESSAO} ".encode())
    arquivos = [str(tmp_path / "a.md"), str(tmp_path / "b.bin")]
    assert higiene.main(arquivos, raiz=tmp_path) == 1
    saida = capsys.readouterr().out
    assert "a.md:2: travessão separando ideias" in saida
    assert "1 achado de higiene" in saida
    assert "b.bin" not in saida


def test_main_aprova_o_que_esta_limpo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.md").write_text(
        "tudo certo: vírgula, dois-pontos e ponto.\n", encoding="utf-8"
    )
    assert higiene.main([str(tmp_path / "a.md")], raiz=tmp_path) == 0
    assert "nada a corrigir" in capsys.readouterr().out


def test_o_repositorio_esta_limpo() -> None:
    """O mesmo que o CI roda: todo o texto versionado passa nas três regras."""
    assert [str(a) for a in higiene.conferir(higiene.arquivos_versionados())] == []
