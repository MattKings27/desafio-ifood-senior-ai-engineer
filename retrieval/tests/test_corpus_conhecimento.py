"""A base de cozinha: todo fato com a página, o trecho literal e a data da conferência."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from retrieval.corpus.conhecimento import (
    CATEGORIAS,
    Fato,
    FatoInvalido,
    carregar_fatos,
    trechos_do_conhecimento,
)

FATO = """
- id: geladeira-abaixo-de-5-graus
  titulo: Geladeira para comida pronta
  categoria: conservacao
  texto: Comida pronta fica abaixo de 5 °C.
  trecho: "conservados sob refrigeração a temperaturas inferiores a 5ºC"
  fonte_titulo: Anvisa, RDC nº 216/2004
  fonte_url: https://www.gov.br/anvisa/rdc-216
  verificado_em: 2026-09-26
  palavras: [geladeira, frio]
"""


def _pasta(tmp_path: Path, *arquivos: str) -> Path:
    for numero, conteudo in enumerate(arquivos):
        (tmp_path / f"{numero}.yaml").write_text(conteudo, "utf-8")
    return tmp_path


def test_a_base_de_verdade_segue_a_regra() -> None:
    fatos = carregar_fatos()
    assert 40 <= len(fatos) <= 60
    assert {f.categoria for f in fatos} <= set(CATEGORIAS)
    assert len({f.id for f in fatos}) == len(fatos)
    assert all(f.fonte_url.startswith("https://") for f in fatos)
    assert all(f.verificado_em <= dt.date(2026, 9, 26) for f in fatos)


def test_fato_vira_trecho_com_a_fonte_e_o_trecho_literal(tmp_path: Path) -> None:
    (fato,) = carregar_fatos(_pasta(tmp_path, FATO))
    assert isinstance(fato, Fato)
    assert fato.dominio == "gov.br"
    assert fato.palavras == ("geladeira", "frio")
    trecho = fato.para_trecho()
    assert (trecho.id, trecho.tipo, trecho.rota, trecho.fonte) == (
        "conhecimento:geladeira-abaixo-de-5-graus",
        "conhecimento",
        None,
        "Anvisa, RDC nº 216/2004",
    )
    assert trecho.cabecalho == (
        "Conhecimento de cozinha, conservação dos alimentos, Geladeira para comida pronta:"
    )
    assert trecho.corpo.endswith(
        "Na fonte (gov.br, conferida em 26/09/2026): "
        "“conservados sob refrigeração a temperaturas inferiores a 5ºC”"
    )
    assert trechos_do_conhecimento([fato]) == [trecho]


def test_data_em_texto_tambem_vale(tmp_path: Path) -> None:
    (fato,) = carregar_fatos(_pasta(tmp_path, FATO.replace("2026-09-26", "'2026-09-26'")))
    assert fato.verificado_em == dt.date(2026, 9, 26)


@pytest.mark.parametrize(
    ("troca", "mensagem"),
    [
        (("trecho: ", "trechinho: "), "sem trecho"),
        (("id: geladeira-abaixo-de-5-graus", "id: Geladeira"), "fora do formato"),
        (("categoria: conservacao", "categoria: fofoca"), "categoria desconhecida"),
        (("https://www.gov.br/anvisa/rdc-216", "ftp://x"), "não é página"),
        (("verificado_em: 2026-09-26", "verificado_em: 12"), "data de conferência"),
        (("texto: Comida pronta", "texto: Comida \u2014 pronta"), "travessão"),
        (("texto: Comida pronta", "texto: O CMV da comida pronta"), "palavra"),
    ],
)
def test_fato_fora_da_regra_nao_entra(
    tmp_path: Path, troca: tuple[str, str], mensagem: str
) -> None:
    with pytest.raises(FatoInvalido, match=mensagem):
        carregar_fatos(_pasta(tmp_path, FATO.replace(*troca)))


def test_arquivo_que_nao_e_lista_e_item_que_nao_e_mapa(tmp_path: Path) -> None:
    with pytest.raises(FatoInvalido, match="lista de fatos"):
        carregar_fatos(_pasta(tmp_path, "id: solto"))
    outra = tmp_path / "outra"
    outra.mkdir()
    with pytest.raises(FatoInvalido, match="é um mapa"):
        carregar_fatos(_pasta(outra, "- só um texto"))


def test_id_repetido_entre_arquivos(tmp_path: Path) -> None:
    with pytest.raises(FatoInvalido, match="mesmo id"):
        carregar_fatos(_pasta(tmp_path, FATO, FATO))


def test_pasta_vazia_e_arquivo_vazio(tmp_path: Path) -> None:
    assert carregar_fatos(tmp_path) == ()
    assert carregar_fatos(_pasta(tmp_path, "")) == ()
