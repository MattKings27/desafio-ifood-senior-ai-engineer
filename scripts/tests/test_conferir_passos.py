"""A conferência dos passos: sem rede, com o JSON-LD gravado de cada receita do catálogo.

`python scripts/conferir_passos.py` busca as páginas de verdade e lê o catálogo
da API no ar. Aqui a mesma prova roda com o que foi gravado: o objeto Recipe
de cada página e os passos que a plataforma tinha guardado. Se o extrator
voltar a perder um passo, juntar dois ou esquecer uma seção, o teste reprova.

Os padrões sintéticos (`fixtures/passos/padroes/`) trazem o resultado escrito à
mão: provam o leitor de referência e o extrator ao mesmo tempo.
"""

from __future__ import annotations

import io
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any, Self

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import conferir_passos as conferencia

PASTA = Path(__file__).parent / "fixtures" / "passos"
PADROES = sorted((PASTA / "padroes").glob("*.json"))
URL = "https://www.exemplo.com.br/receita/bolo"

#: A receita do catálogo que a plataforma guardou com o passo errado, antes da
#: correção: o feijão do Receitas Nestlé, que ficou com o nome da seção.
FEIJAO_DA_NESTLE = "6e4c00239f0364e8"


def _gravadas() -> list[conferencia.Resultado]:
    receitas, ler = conferencia.ler_gravadas(PASTA)
    return conferencia.conferir_todas(receitas, ler)


def test_toda_receita_gravada_do_catalogo_sai_do_extrator_como_na_pagina() -> None:
    resultados = _gravadas()
    assert len(resultados) >= 10, "o catálogo gravado tem as receitas do ar"
    assert [
        (r.receita.slug, r.extrator, r.falha) for r in resultados if not r.extrator_ok
    ] == []
    assert all(r.esperados for r in resultados), "toda receita gravada tem passos"


def test_o_guardado_que_diverge_e_so_o_feijao_que_perdeu_os_passos() -> None:
    """O guardado foi lido antes da correção: a conferência aponta onde ele erra."""
    divergem = {r.receita.slug: r.guardado for r in _gravadas() if r.guardado}
    assert list(divergem) == [FEIJAO_DA_NESTLE]
    assert "veio «Modo de Preparo»" in divergem[FEIJAO_DA_NESTLE]


@pytest.mark.parametrize("arquivo", PADROES, ids=lambda arquivo: arquivo.stem)
def test_padrao_do_json_ld(arquivo: Path) -> None:
    caso = json.loads(arquivo.read_text("utf-8"))
    esperado = [conferencia.Passo(p["texto"], p["secao"]) for p in caso["esperado"]]
    pagina = conferencia.pagina_de(caso["jsonld"])
    receita = conferencia.receita_da_pagina(pagina)
    assert receita is not None
    lidos = conferencia.passos_da_pagina(receita["recipeInstructions"])
    assert [p.como_mostrado() for p in lidos] == esperado, "o leitor de referência"
    assert conferencia.do_extrator(pagina, URL) == esperado, "o extrator"


def test_os_padroes_cobrem_cada_forma() -> None:
    nomes = {arquivo.stem for arquivo in PADROES}
    assert {
        "secao_com_passos",
        "secao_sem_titulo",
        "passo_name_copia_do_text",
        "passo_name_abre_secao",
        "textos_soltos",
        "textos_com_html",
        "listas_aninhadas",
        "texto_unico_numerado",
        "passo_unico_com_quebras",
    } <= nomes


def test_o_nome_da_secao_fica_registrado_mesmo_sem_titulo() -> None:
    lidos = conferencia.passos_da_pagina(
        [
            {
                "@type": "HowToSection",
                "name": "Modo de Preparo",
                "itemListElement": ["Mexa."],
            }
        ]
    )
    assert lidos == [conferencia.PassoDaPagina("Mexa.", "Modo de Preparo", None)]


# --------------------------------------------------------------------------- #
# A comparação e o relatório                                                   #
# --------------------------------------------------------------------------- #


def test_diferenca_diz_o_primeiro_passo_que_nao_bate() -> None:
    passo = conferencia.Passo
    assert conferencia.diferenca([passo("a")], [passo("a")]) == ""
    assert conferencia.diferenca(
        [passo("a"), passo("b")], [passo("a"), passo("c")]
    ) == ("passo 2: a página diz «b», veio «c»")
    assert conferencia.diferenca([passo("a", "Massa")], [passo("a")]) == (
        "passo 1: a página põe na seção Massa, veio sem título"
    )
    assert (
        conferencia.diferenca([passo("a", "Massa")], [passo("a")], com_secao=False)
        == ""
    )
    assert conferencia.diferenca([passo("a")], [passo("a"), passo("b")]) == (
        "a página tem 1 passos, veio 2"
    )
    longo = "x" * 200
    assert "…" in conferencia.diferenca([passo(longo)], [passo("y")])


def test_forma_descreve_o_recipe_instructions() -> None:
    assert conferencia.forma("Cozinhe.\nSirva.") == "texto com quebra de linha"
    assert (
        conferencia.forma([{"@type": "HowToStep", "text": "a"}] * 3)
        == "3 × HowToStep(text)"
    )
    assert conferencia.forma(
        [
            {"@type": "HowToSection", "name": "Massa", "itemListElement": [
                {"@type": "HowToStep", "itemListElement": {"@type": "HowToDirection", "text": "a"}},
            ]},
            {"@type": "HowToStep", "name": "Cobertura", "text": "b"},
        ]
    ) == "HowToSection «Massa» [HowToStep(itemListElement) > HowToDirection(text)], HowToStep(name+text)"  # fmt: skip
    assert conferencia.forma(None) == "nada"
    assert conferencia.forma(7) == "int"


def test_main_com_as_gravadas_da_uma_linha_por_receita(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert conferencia.main(["--gravadas", "--pasta", str(PASTA)]) == 0
    saida = capsys.readouterr().out
    linhas = [
        linha for linha in saida.splitlines() if linha.startswith(("ok", "diverge"))
    ]
    assert len(linhas) == len(list(PASTA.glob("*.json")))
    feijao = next(linha for linha in linhas if FEIJAO_DA_NESTLE in linha)
    assert feijao.startswith("diverge")
    assert "HowToSection «Modo de Preparo»" in feijao
    assert "«Modo de Preparo» sem título" in feijao
    assert "extrator: ok" in feijao
    assert "com o guardado diferente da página" in saida


def test_extrator_que_diverge_reprova(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        conferencia,
        "do_extrator",
        lambda _pagina, _url: [conferencia.Passo("Modo de Preparo")],
    )
    assert conferencia.main(["--gravadas", "--pasta", str(PASTA)]) == 1
    assert "extrator: diverge (passo 1:" in capsys.readouterr().out


def test_extrator_que_recusa_a_pagina_reprova() -> None:
    sem_ingrediente = conferencia.pagina_de(
        {"@type": "Recipe", "name": "Vazia", "recipeInstructions": ["Mexa."]}
    )
    resultado = conferencia.conferir(
        conferencia.ReceitaDoCatalogo(URL), sem_ingrediente
    )
    assert not resultado.extrator_ok
    assert resultado.extrator.startswith("o extrator recusou a página")


def test_pagina_sem_json_ld_nao_tem_com_o_que_comparar() -> None:
    resultado = conferencia.conferir(
        conferencia.ReceitaDoCatalogo(URL), "<html></html>"
    )
    assert resultado.sem_json_ld
    assert resultado.linha().startswith("sem-json")


def test_pagina_que_nao_vem_reprova(capsys: pytest.CaptureFixture[str]) -> None:
    def cair(_url: str) -> str:
        raise OSError("fora do ar")

    receitas = [conferencia.ReceitaDoCatalogo(URL, slug="abc")]
    (resultado,) = conferencia.conferir_todas(receitas, cair)
    assert not resultado.extrator_ok
    assert resultado.linha() == f"FALHA    abc  {URL}  (a página não veio: fora do ar)"


def test_bloco_quebrado_e_o_primeiro_recipe_do_grafo() -> None:
    pagina = (
        '<script type="application/ld+json">{quebrado</script>'
        "<script type='application/ld+json'>"
        '{"@graph": [{"@type": "WebSite"}, {"@type": ["Recipe"], "name": "Primeira"},'
        ' {"@type": "Recipe", "name": "Segunda"}]}</script>'
    )
    receita = conferencia.receita_da_pagina(pagina)
    assert receita is not None
    assert receita["name"] == "Primeira"


# --------------------------------------------------------------------------- #
# O catálogo da API no ar: só leitura                                          #
# --------------------------------------------------------------------------- #


def _api_falsa(pedidos: list[str]) -> conferencia.LerJson:
    detalhe = {
        "fonte": {"url": URL},
        "passos": [{"ordem": 1, "texto": "Mexa.", "secao": None, "requisitos": []}],
    }

    def ler(url: str) -> Any:
        pedidos.append(url)
        if "?aba=" in url:
            aba = url.rsplit("=", 1)[1]
            itens = [{"slug": "bolo"}] if aba in {"pode_fazer", "ranking"} else []
            return {"ok": True, "dados": {"aba": aba, "itens": itens}}
        return {"ok": True, "dados": detalhe}

    return ler


def test_catalogo_da_api_le_cada_aba_e_cada_receita_uma_vez() -> None:
    pedidos: list[str] = []
    (receita,) = conferencia.catalogo_da_api("http://api:8777/", _api_falsa(pedidos))
    assert receita == conferencia.ReceitaDoCatalogo(
        URL, "bolo", (conferencia.Passo("Mexa."),), com_secao=True
    )
    assert pedidos == [
        *(f"http://api:8777/api/receitas?aba={aba}" for aba in conferencia.ABAS),
        "http://api:8777/api/receitas/bolo",
    ]


class _Resposta(io.BytesIO):
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_a_api_so_recebe_get(monkeypatch: pytest.MonkeyPatch) -> None:
    metodos: list[str] = []

    def abrir(requisicao: urllib.request.Request, timeout: float) -> _Resposta:
        assert timeout > 0
        metodos.append(requisicao.get_method())
        return _Resposta(b'{"ok": true, "dados": {"itens": []}}')

    monkeypatch.setattr(urllib.request, "urlopen", abrir)
    assert conferencia.catalogo_da_api("http://api:8777") == []
    assert metodos == ["GET"] * len(conferencia.ABAS)


def test_sem_api_no_ar_diz_e_reprova(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fora(_api: str) -> list[conferencia.ReceitaDoCatalogo]:
        raise OSError("conexão recusada")

    monkeypatch.setattr(conferencia, "catalogo_da_api", fora)
    assert conferencia.main(["--api", "http://api:1"]) == 1
    assert "não consegui ler o catálogo em http://api:1" in capsys.readouterr().out


def test_ler_da_rede_usa_a_busca_da_plataforma(monkeypatch: pytest.MonkeyPatch) -> None:
    from retrieval import busca

    monkeypatch.setattr(busca, "baixar", lambda url: f"<html>{url}</html>")
    assert conferencia.ler_da_rede(URL) == f"<html>{URL}</html>"

    def recusar(_url: str) -> str:
        raise busca.UrlRecusada("HTTP 404, não adianta repetir")

    monkeypatch.setattr(busca, "baixar", recusar)
    with pytest.raises(OSError, match="HTTP 404"):
        conferencia.ler_da_rede(URL)


# --------------------------------------------------------------------------- #
# A gravação                                                                    #
# --------------------------------------------------------------------------- #


def _pagina_do_bolo() -> str:
    return (
        "<html><script type='application/ld+json'>"
        + json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "Recipe",
                "name": "Bolo",
                "description": "não é gravada",
                "recipeIngredient": ["2 ovos"],
                "recipeInstructions": [
                    {
                        "@type": "HowToSection",
                        "name": "Massa",
                        "itemListElement": ["Bata."],
                    }
                ],
            }
        )
        + "</script></html>"
    )


def test_gravar_guarda_o_minimo_e_confere_de_novo_sem_rede(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    catalogo = [
        conferencia.ReceitaDoCatalogo(
            URL, "bolo", (conferencia.Passo("Bata.", "Massa"),), True
        )
    ]
    monkeypatch.setattr(conferencia, "catalogo_da_api", lambda _api: catalogo)
    monkeypatch.setattr(conferencia, "ler_da_rede", lambda _url: _pagina_do_bolo())
    assert conferencia.main(["--gravar", "--pasta", str(tmp_path)]) == 0
    gravado = json.loads((tmp_path / "bolo.json").read_text("utf-8"))
    assert set(gravado["receita"]) == set(conferencia.CHAVES_GRAVADAS)
    assert gravado["guardados"] == [{"texto": "Bata.", "secao": "Massa"}]
    capsys.readouterr()
    assert conferencia.main(["--gravadas", "--pasta", str(tmp_path)]) == 0
    assert capsys.readouterr().out.startswith("ok       bolo")


def test_endereco_passado_a_mao_nao_tem_guardado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(conferencia, "ler_da_rede", lambda _url: _pagina_do_bolo())
    assert conferencia.main([URL, "--gravar", "--pasta", str(tmp_path)]) == 0
    assert "guardado: sem guardado" in capsys.readouterr().out
    (arquivo,) = tmp_path.glob("*.json")
    assert arquivo.name == "www-exemplo-com-br-receita-bolo.json"
    assert json.loads(arquivo.read_text("utf-8"))["guardados"] is None
    receitas, ler = conferencia.ler_gravadas(tmp_path)
    assert receitas == [conferencia.ReceitaDoCatalogo(URL)]
    with pytest.raises(ValueError, match="não foi gravada"):
        ler("https://outra.com.br/")


def test_nada_se_grava_quando_o_extrator_diverge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(conferencia, "ler_da_rede", lambda _url: _pagina_do_bolo())
    monkeypatch.setattr(conferencia, "do_extrator", lambda _pagina, _url: [])
    assert conferencia.main([URL, "--gravar", "--pasta", str(tmp_path)]) == 1
    assert not list(tmp_path.glob("*.json"))


def test_gravar_pagina_sem_receita_e_recusado(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="não traz receita"):
        conferencia.gravar(
            conferencia.ReceitaDoCatalogo(URL),
            "<html></html>",
            tmp_path,
            conferencia.dt.date.today(),
        )
