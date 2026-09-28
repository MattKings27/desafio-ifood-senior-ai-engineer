"""A leitura das linhas melhora, e a receita que já estava no catálogo acompanha.

A receita guardada com regras de leitura mais antigas é lida de novo pelo
servidor, na abertura, a partir das linhas originais que ela guarda: sem buscar
a página, e sem mexer no que ela respondeu.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import receitas_de_teste as rt
from retrieval.quantidades import VERSAO_DA_LEITURA, interpretar_linha

from mise.catalogo import CAMPOS_DA_LEITURA, reler_as_linhas
from mise.dossie import Dossie
from mise.mcp_server import Sessao, abrir_sessao, reler_o_catalogo

FAROFA_URL = "https://www.receiteria.com.br/receita/farofa-de-bacon-com-ovo/"
FAROFA = rt.pagina(
    "Farofa de bacon com ovo",
    [
        "1 e 1/4 de xícara de chá de farinha de milho em flocos (250 gramas)",
        "250 gramas de bacon",
        "1/4 de colher de chá de pimenta-do-reino (ou a gosto)",
        "1/2 colher de chá de sal (ou a gosto)",
    ],
    ["Frite o bacon por 5 minutos.", "Junte a farinha e mexa por 5 minutos."],
)

FARINHA = "1 e 1/4 de xícara de chá de farinha de milho em flocos (250 gramas)"
PIMENTA = "1/4 de colher de chá de pimenta-do-reino (ou a gosto)"
SAL = "1/2 colher de chá de sal (ou a gosto)"

#: Como a leitura de antes gravou as três linhas: a medida grudada no nome.
LIDAS_ANTES: dict[str, dict[str, Any]] = {
    FARINHA: {"nome": "xícara de chá de farinha de milho em flocos"},
    PIMENTA: {"nome": "colher de chá de pimenta-do-reino", "medida": ""},
    SAL: {"nome": "chá de sal", "medida": "colher"},
}


def _como_antes(dados: dict[str, Any], **extra: dict[str, Any]) -> dict[str, Any]:
    """A receita em JSON com as três linhas lidas como antes, e o que mais cada linha tiver."""
    for linha in dados["ingredientes"]:
        linha.update(LIDAS_ANTES.get(linha["texto_original"], {}))
        linha.update(extra.get(linha["texto_original"], {}))
    return dados


def _gravada_com_a_leitura_antiga(
    sessao: Sessao,
    *,
    respostas: list[dict[str, str]] | None = None,
    na_receita: dict[str, dict[str, Any]] | None = None,
) -> str:
    """A farofa no catálogo como a leitura antiga gravou, sem versão. Devolve o slug."""
    guardada = rt.da_web(sessao, FAROFA_URL, FAROFA)
    with sessao.dossie.transacao() as cur:
        linha = cur.execute(
            "SELECT receita, receita_lida FROM catalogo WHERE slug = ?", (guardada.slug,)
        ).fetchone()
        receita = _como_antes(json.loads(linha["receita"]), **(na_receita or {}))
        pagina = _como_antes(json.loads(linha["receita_lida"]))
        cur.execute(
            "UPDATE catalogo SET receita = ?, receita_lida = ?, respostas = ?, "
            "versao_da_leitura = NULL WHERE slug = ?",
            (
                json.dumps(receita, ensure_ascii=False),
                json.dumps(pagina, ensure_ascii=False),
                json.dumps(respostas or [], ensure_ascii=False),
                guardada.slug,
            ),
        )
    return guardada.slug


def _linha_gravada(dossie: Dossie, slug: str, coluna: str, texto: str) -> dict[str, Any]:
    with dossie.cursor() as cur:
        bruto = cur.execute(f"SELECT {coluna} FROM catalogo WHERE slug = ?", (slug,)).fetchone()
    dados = json.loads(bruto[0])
    return next(i for i in dados["ingredientes"] if i["texto_original"] == texto)


def _coluna(dossie: Dossie, slug: str, coluna: str) -> Any:
    with dossie.cursor() as cur:
        return cur.execute(f"SELECT {coluna} FROM catalogo WHERE slug = ?", (slug,)).fetchone()[0]


def test_a_receita_guardada_com_a_leitura_antiga_e_lida_de_novo(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    slug = _gravada_com_a_leitura_antiga(sessao)
    bacon_antes = _linha_gravada(sessao.dossie, slug, "receita", "250 gramas de bacon")

    relidas = reler_o_catalogo(sessao.dossie)

    assert {(r.onde, r.texto_original) for r in relidas} == {
        (onde, texto) for onde in ("receita", "receita_lida") for texto in LIDAS_ANTES
    }
    for relida in relidas:
        assert set(relida.antes) == set(relida.depois) == set(CAMPOS_DA_LEITURA)
        assert relida.receita == "Farofa de bacon com ovo"
    receita = sessao.catalogo.obter(slug)
    assert receita is not None
    lidas = {i.texto_original: i for i in receita.receita.ingredientes}
    assert (lidas[FARINHA].nome, lidas[FARINHA].quantidade, lidas[FARINHA].medida) == (
        "farinha de milho em flocos",
        250,
        "g",
    )
    assert (lidas[PIMENTA].nome, lidas[PIMENTA].medida) == ("pimenta-do-reino", "colher de cha")
    assert (lidas[SAL].nome, lidas[SAL].medida) == ("sal", "colher de cha")
    assert _linha_gravada(sessao.dossie, slug, "receita", "250 gramas de bacon") == bacon_antes
    assert _coluna(sessao.dossie, slug, "receita") == _coluna(sessao.dossie, slug, "receita_lida")
    assert _coluna(sessao.dossie, slug, "versao_da_leitura") == VERSAO_DA_LEITURA


def test_ler_de_novo_na_mesma_versao_nao_faz_nada(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    slug = _gravada_com_a_leitura_antiga(sessao)
    assert reler_o_catalogo(sessao.dossie)
    gravada = _coluna(sessao.dossie, slug, "receita")
    assert reler_o_catalogo(sessao.dossie) == ()
    # Uma versão nova das regras lê de novo, e a linha que já está certa sai igual.
    assert reler_as_linhas(sessao.dossie, interpretar_linha, VERSAO_DA_LEITURA + 1) == ()
    assert _coluna(sessao.dossie, slug, "receita") == gravada
    assert _coluna(sessao.dossie, slug, "versao_da_leitura") == VERSAO_DA_LEITURA + 1


def test_a_pagina_lida_agora_ja_entra_com_a_versao(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    guardada = rt.da_web(sessao, FAROFA_URL, FAROFA)
    assert _coluna(sessao.dossie, guardada.slug, "versao_da_leitura") == VERSAO_DA_LEITURA
    assert reler_o_catalogo(sessao.dossie) == ()


def test_a_linha_que_ela_respondeu_fica_como_ela_disse(tmp_path: Path) -> None:
    """A resposta dela vale na receita; a página guardada, que não tem resposta, é relida."""
    sessao = rt.sessao_nova(tmp_path)
    resposta = {"campo": SAL, "valor": "meia colher de chá", "quando": "2026-09-27T10:00:00+00:00"}
    slug = _gravada_com_a_leitura_antiga(sessao, respostas=[resposta])

    relidas = reler_o_catalogo(sessao.dossie)

    onde = {(r.onde, r.texto_original) for r in relidas}
    assert ("receita", SAL) not in onde
    assert ("receita_lida", SAL) in onde
    assert _linha_gravada(sessao.dossie, slug, "receita", SAL)["nome"] == "chá de sal"
    assert _linha_gravada(sessao.dossie, slug, "receita_lida", SAL)["nome"] == "sal"
    assert _linha_gravada(sessao.dossie, slug, "receita", PIMENTA)["nome"] == "pimenta-do-reino"


def test_a_linha_com_o_item_ou_o_peso_dela_fica(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    slug = _gravada_com_a_leitura_antiga(
        sessao,
        na_receita={PIMENTA: {"item_da_despensa": ""}, FARINHA: {"peso_g": "250"}},
    )
    reler_o_catalogo(sessao.dossie)
    pimenta = _linha_gravada(sessao.dossie, slug, "receita", PIMENTA)
    farinha = _linha_gravada(sessao.dossie, slug, "receita", FARINHA)
    assert (pimenta["nome"], pimenta["item_da_despensa"]) == (
        "colher de chá de pimenta-do-reino",
        "",
    )
    assert (farinha["nome"], farinha["peso_g"]) == (
        "xícara de chá de farinha de milho em flocos",
        "250",
    )
    assert _linha_gravada(sessao.dossie, slug, "receita", SAL)["nome"] == "sal"


def test_a_receita_ditada_nao_passa_pela_leitura(tmp_path: Path) -> None:
    """O que ela ditou chegou com nome e quantidade de quem mandou: a leitura não reescreve."""
    sessao = rt.sessao_nova(tmp_path)
    ditada = rt.ditada(
        sessao,
        nome="Sal da vó",
        rendimento_porcoes=2,
        ingredientes=[
            {"texto": SAL, "nome": "chá de sal", "quantidade": 0.5, "medida": "colher"},
        ],
    )
    with sessao.dossie.transacao() as cur:
        cur.execute("UPDATE catalogo SET versao_da_leitura = NULL WHERE slug = ?", (ditada.slug,))
    gravada = _coluna(sessao.dossie, ditada.slug, "receita")

    assert reler_o_catalogo(sessao.dossie) == ()
    assert _coluna(sessao.dossie, ditada.slug, "receita") == gravada
    assert _coluna(sessao.dossie, ditada.slug, "versao_da_leitura") == VERSAO_DA_LEITURA


def test_a_receita_em_avaliacao_acompanha_a_do_catalogo(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    slug = _gravada_com_a_leitura_antiga(sessao)
    antiga = sessao.receita_por_id(slug)
    sessao.guardar(antiga)
    assert {i.nome for i in sessao.candidatas["Farofa de bacon com ovo"].ingredientes} >= {
        "chá de sal"
    }

    relidas = reler_o_catalogo(sessao.dossie)

    assert {r.texto_original for r in relidas if r.onde == "candidata"} == set(LIDAS_ANTES)
    em_avaliacao = sessao.candidatas["Farofa de bacon com ovo"]
    assert {i.nome for i in em_avaliacao.ingredientes} == {
        "farinha de milho em flocos",
        "bacon",
        "pimenta-do-reino",
        "sal",
    }
    assert sessao.receita_por_id(slug) == em_avaliacao


def test_abrir_a_sessao_le_de_novo_o_catalogo(tmp_path: Path) -> None:
    """É o servidor que relê, na abertura: o do agente e o da tela abrem por `abrir_sessao`."""
    sessao = rt.sessao_nova(tmp_path)
    slug = _gravada_com_a_leitura_antiga(sessao)
    sessao.dossie.fechar()

    reaberta = abrir_sessao(planilha=rt.PLANILHA, banco=tmp_path / "dossie.db")

    receita = reaberta.catalogo.obter(slug)
    assert receita is not None
    assert "chá de sal" not in {i.nome for i in receita.receita.ingredientes}
    assert _coluna(reaberta.dossie, slug, "versao_da_leitura") == VERSAO_DA_LEITURA


def test_a_receita_completada_antes_da_pagina_guardada_rele_so_a_receita(tmp_path: Path) -> None:
    """A receita que ela completou antes de o catálogo guardar a página não tem a página: só ela muda."""
    sessao = rt.sessao_nova(tmp_path)
    resposta = {"campo": SAL, "valor": "meia colher de chá", "quando": "2026-09-27T10:00:00+00:00"}
    slug = _gravada_com_a_leitura_antiga(sessao, respostas=[resposta])
    with sessao.dossie.transacao() as cur:
        cur.execute("UPDATE catalogo SET receita_lida = NULL WHERE slug = ?", (slug,))

    relidas = reler_o_catalogo(sessao.dossie)

    assert {r.onde for r in relidas} == {"receita"}
    assert {r.texto_original for r in relidas} == {FARINHA, PIMENTA}
    assert _coluna(sessao.dossie, slug, "receita_lida") is None


def test_a_receita_em_avaliacao_ja_certa_fica_como_esta(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    guardada = rt.da_web(sessao, FAROFA_URL, FAROFA)
    sessao.guardar(guardada.receita)
    with sessao.dossie.transacao() as cur:
        cur.execute("UPDATE catalogo SET versao_da_leitura = NULL WHERE slug = ?", (guardada.slug,))
        antes = cur.execute("SELECT dados FROM candidatas").fetchone()[0]

    assert reler_o_catalogo(sessao.dossie) == ()
    with sessao.dossie.cursor() as cur:
        assert cur.execute("SELECT dados FROM candidatas").fetchone()[0] == antes
