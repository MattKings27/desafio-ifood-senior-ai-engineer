"""Bordas do portão: orçamento, compras com preço, e o caminho APTO_COM_COMPRA."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from mise.despensa import Despensa
from mise.dinheiro import Dinheiro
from mise.erros import DensidadeDesconhecida
from mise.perfil import Gosto, PerfilCozinha, Posse
from mise.receita import ingrediente as ing
from mise.receita import receita
from mise.viabilidade import (
    Avaliacao,
    Checagem,
    ItemFaltante,
    TipoRestricao,
    Veredito,
    avaliar,
    checar_ingredientes,
)


@pytest.fixture
def perfil() -> PerfilCozinha:
    p = PerfilCozinha.inicial()
    p = p.com_equipamentos((e, Posse.TEM) for e in p.equipamentos)
    p = p.com_tecnicas((t, Posse.TEM) for t in p.tecnicas)
    return p.com_restricao("bocas_fogao", 6).com_restricao("tempo_max_por_fornada_min", 480)


def _com_faltantes(base: Avaliacao, faltantes: tuple[ItemFaltante, ...]) -> Avaliacao:
    return Avaliacao(
        receita_nome=base.receita_nome,
        veredito=Veredito.APTO_COM_COMPRA,
        checagens=(Checagem("ingredientes", Veredito.APTO_COM_COMPRA),),
        usos=base.usos,
        faltantes=faltantes,
    )


def test_custo_das_compras_soma_quando_todos_tem_preco(
    despensa: Despensa, perfil: PerfilCozinha
) -> None:
    r = receita("X", [ing("1 kg de arroz", "arroz", 1, "kg")])
    a = _com_faltantes(
        avaliar(r, perfil, despensa, gosto=Gosto.GOSTA),
        (
            ItemFaltante("linguiça", "200 g", Dinheiro.de("10.00")),
            ItemFaltante("cenoura", "300 g", Dinheiro.de("4.50")),
        ),
    )
    assert a.custo_das_compras == Dinheiro.de("14.50")


def test_resumo_de_apto_com_compra(despensa: Despensa, perfil: PerfilCozinha) -> None:
    r = receita("X", [ing("1 kg de arroz", "arroz", 1, "kg")])
    a = _com_faltantes(
        avaliar(r, perfil, despensa, gosto=Gosto.GOSTA),
        (ItemFaltante("linguiça", "200 g", Dinheiro.de("10.00")),),
    )
    resumo = a.resumo()
    assert resumo == "X: dá, comprando 1 item, R$ 10,00 no total"
    # Com o orçamento conhecido, o resumo confronta a compra com ele (§2.3).
    com_orcamento = replace(a, orcamento_restante=Dinheiro.de("80.00"))
    assert com_orcamento.resumo() == (
        "X: dá, comprando 1 item, R$ 10,00 no total; cabe nos R$ 80,00 que restam do orçamento"
    )


def test_compra_dentro_do_orcamento_nao_bloqueia(despensa: Despensa) -> None:
    r = receita(
        "Com compra",
        [
            ing("1 kg de arroz", "arroz", 1, "kg"),
            ing("200 g de linguiça", "linguiça calabresa", 200, "g"),
        ],
    )
    checagem, _, faltantes, _ = checar_ingredientes(
        r, despensa, orcamento_restante=Dinheiro.de("80.00")
    )
    # sem preço (aqui, sem as referências) nada se pergunta: não dá para confirmar
    assert checagem.veredito is Veredito.BLOQUEADO
    assert faltantes[0].nome == "linguiça calabresa"
    assert not any(p.tipo is TipoRestricao.INGREDIENTE for p in checagem.perguntas)


def test_sem_preco_o_motivo_cita_os_itens_e_nao_pergunta(despensa: Despensa) -> None:
    r = receita(
        "X",
        [
            ing("200 g de trufa", "trufa branca", 200, "g"),
            ing("1 pote de doce de leite", "doce de leite", 1, "unidade"),
        ],
    )
    checagem, _, _, _ = checar_ingredientes(r, despensa)
    assert not checagem.perguntas
    (motivo,) = [i.descricao for i in checagem.impedimentos if i.id == "sem_preco"]
    assert "trufa branca" in motivo
    assert "doce de leite" in motivo
    assert "não dá para confirmar que a compra cabe" in motivo


def test_medida_sem_fonte_deixa_a_receita_de_fora_sem_pergunta(despensa: Despensa) -> None:
    """Receita pede xícara de um item sem medida com fonte: sem número, e sem pergunta."""
    r = receita("X", [ing("1 xícara de couve", "couve", 1, "xicara")])
    checagem, usos, _, _ = checar_ingredientes(r, despensa)
    assert not usos
    assert checagem.veredito is Veredito.BLOQUEADO
    assert not checagem.perguntas
    assert any("não achei em fonte nenhuma" in i.descricao for i in checagem.impedimentos)


def test_medida_desconhecida_nao_vira_pergunta(despensa: Despensa) -> None:
    r = receita("X", [ing("1 punhado de arroz", "arroz", 1, "punhado")])
    checagem, usos, _, _ = checar_ingredientes(r, despensa)
    assert not usos
    assert not checagem.perguntas
    assert checagem.veredito is Veredito.BLOQUEADO


def test_densidade_desconhecida_e_um_erro_de_dados() -> None:
    erro = DensidadeDesconhecida("couve", "xícara")
    assert erro.ingrediente == "couve"


def test_checagem_acumula_o_pior_veredito() -> None:
    c = Checagem("x")
    assert c.veredito is Veredito.APTO
    c.veredito = max(c.veredito, Veredito.APTO_COM_COMPRA)
    assert c.veredito is Veredito.APTO_COM_COMPRA


def test_volume_em_medida_caseira_funciona(despensa: Despensa, perfil: PerfilCozinha) -> None:
    """Óleo é custado por litro: a receita em colheres converte sem densidade."""
    r = receita("Fritura", [ing("2 colheres de óleo", "óleo de soja", 2, "colher de sopa")])
    _, usos, _, _ = checar_ingredientes(r, despensa)
    assert usos[0].quantidade.valor == Decimal("0.03")
    assert usos[0].custo.arredondado() == Dinheiro.de("0.27")


def test_avaliacao_sem_usos_nem_faltantes(despensa: Despensa, perfil: PerfilCozinha) -> None:
    """Receita só de 'a gosto': nada a custear, e mesmo assim é apta."""
    r = receita(
        "Tempero",
        [ing("sal a gosto", "sal"), ing("pimenta a gosto", "pimenta")],
        modo_preparo=["Misture tudo."],
    )
    a = avaliar(r, perfil, despensa, gosto=Gosto.GOSTA)
    assert a.veredito is Veredito.APTO
    assert a.a_gosto == ("sal", "pimenta")
    assert a.custo_das_compras == Dinheiro.zero()
