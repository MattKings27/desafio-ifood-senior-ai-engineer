"""O preço procurado pelo servidor nos mercados de São Paulo, sem rede.

As respostas dos mercados foram gravadas numa busca de verdade por "coxa e
sobrecoxa de frango" (`fixtures/precos_coxa_e_sobrecoxa.json`, só com os campos
que o código lê). A procura roda a escolha de verdade (`retrieval.precos`)
sobre elas: o preço médio sai de mais de um mercado, fica guardado no dossiê, e
entra na conta da receita sem perguntar nada a ela.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from mise.dossie import Dossie
from mise.mcp_server import Sessao
from mise.precos_na_web import (
    ESPERA_PARA_TENTAR_DE_NOVO,
    PrecosNaWeb,
    ligada,
    registro_do_preco,
)
from mise.receita import IngredienteReceita, Receita

GRAVADAS = Path(__file__).parent / "fixtures" / "precos_coxa_e_sobrecoxa.json"


def _leitor_gravado() -> Any:
    from retrieval.precos import PrecoNaoVeio

    respostas: dict[str, str] = json.loads(GRAVADAS.read_text("utf-8"))["respostas"]

    def ler(url: str, _cabecalhos: Mapping[str, str]) -> str:
        if url not in respostas:
            raise PrecoNaoVeio(f"não gravada: {url}")
        return respostas[url]

    return ler


def _pesquisador_gravado() -> Any:
    from retrieval.precos import Pesquisa

    pesquisa = Pesquisa(ler=_leitor_gravado(), hoje=dt.date(2026, 9, 27))

    def pesquisar(
        nome: str, dimensoes: Sequence[str], prazo: float
    ) -> tuple[str, list[dict[str, Any]]]:
        dimensao, fontes = pesquisa.pelo_nome(nome, dimensoes, prazo)
        return dimensao, [f.registro() for f in fontes]

    return pesquisar


@pytest.fixture
def dossie(tmp_path: Path) -> Dossie:
    return Dossie(tmp_path / "dossie.db")


def test_coxa_e_sobrecoxa_tem_preco_medio_de_mais_de_um_mercado(dossie: Dossie) -> None:
    precos = PrecosNaWeb(dossie, _pesquisador_gravado())
    achado = precos.procurar("coxa e sobrecoxa de frango")
    assert achado.referencia is not None
    referencia = achado.referencia
    sites = {f.site for f in referencia.na_media}
    assert len(sites) >= 2, sites
    assert referencia.a_granel
    assert referencia.texto.startswith("preço médio em São Paulo: R$ ")
    assert all(
        f.api.startswith("https://") and f.trecho.startswith('"Price":') for f in referencia.fontes
    )
    # O que é outro produto ficou de fora: sem osso, temperada, espetinho.
    produtos = " ".join(f.produto for f in referencia.fontes).casefold()
    for outro in ("sem osso", "temperad", "espetinho", "desossad"):
        assert outro not in produtos
    resposta = achado.json()
    assert resposta["achou"] is True
    assert resposta["titulo"] == "Preço médio em São Paulo"
    assert len(resposta["fontes"]) >= 2
    # Ficou guardado e entra nas referências que o motor lê.
    assert [p.ingrediente for p in precos.referencias().de("coxa e sobrecoxa de frango")] == [
        "coxa e sobrecoxa de frango"
    ]


def test_o_guardado_nao_e_procurado_de_novo(dossie: Dossie) -> None:
    chamadas: list[str] = []
    gravado = _pesquisador_gravado()

    def contar(nome: str, dimensoes: Sequence[str], prazo: float) -> Any:
        chamadas.append(nome)
        return gravado(nome, dimensoes, prazo)

    precos = PrecosNaWeb(dossie, contar)
    assert precos.procurar("coxa e sobrecoxa de frango").agora
    de_novo = PrecosNaWeb(dossie, contar).procurar("Coxa e Sobrecoxa de Frango")
    assert de_novo.referencia is not None
    assert not de_novo.agora
    assert chamadas == ["coxa e sobrecoxa de frango"]


def test_o_que_nao_achou_espera_antes_de_procurar_de_novo(tmp_path: Path) -> None:
    agora = [dt.datetime(2026, 9, 27, 12, tzinfo=dt.UTC)]
    dossie = Dossie(tmp_path / "dossie.db", relogio=lambda: agora[0])
    chamadas: list[str] = []

    def nada(nome: str, dimensoes: Sequence[str], _prazo: float) -> Any:
        chamadas.append(nome)
        return dimensoes[0], []

    precos = PrecosNaWeb(dossie, nada)
    primeira = precos.procurar("trufa branca")
    assert primeira.referencia is None
    assert primeira.json()["achou"] is False
    assert "não pergunte o preço a ela" in primeira.json()["texto"]
    assert precos.procurar("trufa branca").agora is False
    agora[0] += ESPERA_PARA_TENTAR_DE_NOVO
    assert precos.procurar("trufa branca").agora is True
    assert chamadas == ["trufa branca", "trufa branca"]


def test_a_falha_de_rede_deixa_sem_preco(dossie: Dossie) -> None:
    def quebrada(_nome: str, _dimensoes: Sequence[str], _prazo: float) -> Any:
        raise OSError("sem rede")

    achado = PrecosNaWeb(dossie, quebrada).procurar("tomate cereja")
    assert achado.referencia is None


def test_varios_com_um_prazo_so(dossie: Dossie) -> None:
    precos = PrecosNaWeb(dossie, _pesquisador_gravado())
    achados = precos.procurar_varios(
        [("coxa e sobrecoxa de frango", ("massa",)), ("trufa branca", ("massa",))], prazo=5
    )
    assert sorted(a.ingrediente for a in achados) == ["coxa e sobrecoxa de frango", "trufa branca"]
    assert precos.procurar_varios([]) == []


def test_o_registro_diz_a_embalagem() -> None:
    kg = {"a_granel": True, "unidade": "kg", "quantidade": "1"}
    un = {"a_granel": False, "unidade": "un", "quantidade": "1"}
    g = {"a_granel": False, "unidade": "g", "quantidade": "500"}
    assert registro_do_preco("x", "massa", [kg])["embalagem"] == "quilo"
    assert registro_do_preco("x", "contagem", [un])["embalagem"] == "unidade"
    assert registro_do_preco("x", "massa", [g, kg])["embalagem"] == "pacote"


def test_a_chave_de_desligar() -> None:
    assert ligada({})
    assert not ligada({"SABOR_PRECOS_NA_WEB": "desligada"})


# --------------------------------------------------------------------------- #
# Na sessão: a ferramenta e a procura ao guardar ou avaliar                    #
# --------------------------------------------------------------------------- #

PLANILHA = Path(__file__).resolve().parents[3] / "dados" / "despensa_dona_maria.xlsx"


def _sessao(tmp_path: Path, *, ligada: bool) -> Sessao:
    from mise.despensa import carregar_despensa

    return Sessao(
        planilha=carregar_despensa(PLANILHA),
        dossie=Dossie(tmp_path / "dossie.db"),
        pesquisar_precos_ao_guardar=ligada,
        pesquisador_de_precos=_pesquisador_gravado(),
    )


def _receita() -> Receita:
    return Receita(
        nome="Frango assado de coxa",
        ingredientes=(
            IngredienteReceita(
                texto_original="1 kg de coxa e sobrecoxa de frango",
                nome="coxa e sobrecoxa de frango",
                quantidade=Decimal(1),
                medida="kg",
            ),
        ),
        rendimento_porcoes=4,
        modo_preparo=("Asse no forno por 40 minutos.",),
    )


def test_a_ferramenta_procura_e_a_conta_passa_a_ter_o_preco(tmp_path: Path) -> None:
    sessao = _sessao(tmp_path, ligada=False)
    receita = _receita()
    antes = sessao.avaliar(receita)
    (falta,) = [f for f in antes.faltantes if "coxa" in f.nome]
    assert not falta.custo_conhecido
    resposta = sessao.buscar_preco_na_web("coxa e sobrecoxa de frango")
    assert resposta["achou"] is True
    depois = sessao.avaliar(receita)
    (falta,) = [f for f in depois.faltantes if "coxa" in f.nome]
    assert falta.custo_conhecido
    assert falta.referencia is not None
    # Pedir de novo devolve o que já está nas referências, sem procurar.
    assert sessao.buscar_preco_na_web("coxa e sobrecoxa de frango")["achou"] is True
    with pytest.raises(Exception, match="qual ingrediente"):
        sessao.buscar_preco_na_web("  ")


def test_ao_guardar_procura_o_que_falta_sem_preco_so_quando_ligada(tmp_path: Path) -> None:
    desligada = _sessao(tmp_path / "a", ligada=False)
    assert desligada.precificar_o_que_falta(_receita()) == []
    ligada_ = _sessao(tmp_path / "b", ligada=True)
    procurados = ligada_.precificar_o_que_falta(_receita())
    assert procurados == ["coxa e sobrecoxa de frango"]
    avaliacao = ligada_.avaliar(_receita())
    (falta,) = [f for f in avaliacao.faltantes if "coxa" in f.nome]
    assert falta.custo_conhecido
    # O que já tem preço não é procurado de novo.
    assert ligada_.precificar_o_que_falta(_receita()) == []
