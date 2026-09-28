"""Tentativas de arrancar do motor um número plausível e errado.

Um erro que levanta exceção é barato: aparece no log, alguém conserta. O erro
caro é o que devolve `R$ 12,40` quando o certo era `R$ 3,10`: ninguém
desconfia, a Dona Maria põe no cardápio e perde dinheiro em toda venda.

Cada teste aqui reproduz uma forma de obter esse tipo de número. Todos já
falharam de verdade em algum momento do desenvolvimento.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from mise.cmv import calcular
from mise.despensa import Despensa
from mise.dinheiro import Dinheiro
from mise.erros import MassaDesconhecida, ViabilidadeNaoConfirmada
from mise.perfil import Gosto, PerfilCozinha, Posse
from mise.receita import Receita
from mise.receita import ingrediente as ing
from mise.receita import receita as _receita
from mise.unidades import Dimensao, Quantidade
from mise.viabilidade import avaliar, checar_ingredientes


def receita(*args: Any, **kwargs: Any) -> Receita:
    """Receita com preparo de panela, que tudo aqui pressupõe.

    Estes testes são sobre custo. O portão exige modo de preparo para conferir
    equipamento, e o tempo no fogo para conferir a cozinhada; sem eles o prato
    fica em "falta informação", que é outra história e tem os próprios testes
    em `test_viabilidade` e `test_restricoes_operacionais`.
    """
    kwargs.setdefault("modo_preparo", ("Cozinhe tudo na panela por 20 minutos.",))
    return _receita(*args, **kwargs)


@pytest.fixture
def perfil_permissivo() -> PerfilCozinha:
    base = PerfilCozinha.inicial()
    base = base.com_equipamentos((e, Posse.TEM) for e in base.equipamentos)
    base = base.com_tecnicas((t, Posse.TEM) for t in base.tecnicas)
    return base.com_restricao("bocas_fogao", 6).com_restricao("tempo_max_por_fornada_min", 480)


def test_massa_de_embalagem_opaca_nao_vira_contagem(despensa: Despensa) -> None:
    """Regressão: "200 g de cobertura" virava 200 embalagens = R$ 15.980,00.

    A despensa custa a cobertura por peça (R$ 79,90/un) porque a planilha não
    diz quanto pesa. Quando a receita pedia gramas, a quantidade era tratada
    como contagem e as dimensões "batiam", e a guarda de massa desconhecida
    nunca disparava. O erro tinha fator 5.000×.
    """
    item = despensa["Cobertura de chocolate"]
    # Agora o peso vem estimado pela página do supermercado (cerca de 1 kg), com a fonte.
    assert item.embalagem_estimada is not None

    r = receita("Bolo", [ing("200 g de cobertura", "Cobertura de chocolate", 200, "g")])
    checagem, usos, _, _ = checar_ingredientes(r, despensa)

    (uso,) = usos
    # 200 g de uma embalagem de cerca de 1 kg: R$ 15,98, nunca 200 embalagens.
    assert uso.custo.arredondado() == Dinheiro.de("15.98")
    assert uso.custo.valor < Decimal(80), "o erro de 5.000× não pode voltar"
    assert not checagem.perguntas

    # Sem fonte para o peso, a guarda continua: massa de embalagem opaca não vira contagem.
    from mise.despensa import LinhaDaDespensa, montar_ingrediente

    pote, _ = montar_ingrediente(
        LinhaDaDespensa("Doce de leite", Decimal(1), "un", Decimal(1), Decimal("20.00"))
    )
    assert pote.embalagem_opaca
    with pytest.raises(MassaDesconhecida):
        pote.custo_de(Quantidade(Decimal("0.2"), Dimensao.MASSA))
    del item


def test_item_contado_de_verdade_continua_funcionando(despensa: Despensa) -> None:
    """A correção não pode quebrar ovos: 2 ovos são 2 ovos, e custam R$ 1,60."""
    r = receita("Omelete", [ing("2 ovos", "ovos", 2, "ovo")])
    _, usos, _, _ = checar_ingredientes(r, despensa)
    assert len(usos) == 1
    assert usos[0].custo.arredondado() == Dinheiro.de("1.60")


def test_nao_da_para_precificar_sem_passar_pelo_portao(
    despensa: Despensa, perfil_permissivo: PerfilCozinha
) -> None:
    """A assinatura de `calcular` exige uma avaliação; não há atalho."""
    r = receita(
        "Prato no forno",
        [ing("500 g de frango", "peito de frango", 500, "g")],
        modo_preparo=["Leve ao forno."],
    )
    perfil_sem_forno = (
        PerfilCozinha.inicial()
        .com_equipamento("forno", Posse.NAO_TEM)
        .com_equipamento("air_fryer", Posse.NAO_TEM)
        .com_equipamento("forno_eletrico", Posse.NAO_TEM)
    )
    avaliacao = avaliar(r, perfil_sem_forno, despensa, gosto=Gosto.GOSTA)

    with pytest.raises(ViabilidadeNaoConfirmada):
        calcular(r, avaliacao)


def test_rendimento_ignorado_multiplicaria_o_cmv(
    despensa: Despensa, perfil_permissivo: PerfilCozinha
) -> None:
    """Esquecer de dividir pelo rendimento infla o CMV pelo número de porções."""
    ingredientes = [ing("1 kg de frango", "peito de frango", 1, "kg")]
    uma = receita("Porção única", ingredientes, rendimento_porcoes=1)
    seis = receita("Rende seis", ingredientes, rendimento_porcoes=6)

    cmv_uma = calcular(uma, avaliar(uma, perfil_permissivo, despensa, gosto=Gosto.GOSTA))
    cmv_seis = calcular(seis, avaliar(seis, perfil_permissivo, despensa, gosto=Gosto.GOSTA))

    assert cmv_uma.total.arredondado() == Dinheiro.de("14.00")
    assert cmv_seis.total.arredondado() == Dinheiro.de("2.33")
    assert cmv_seis.rendimento_original == 6


def test_volume_como_massa_inflaria_farinha(despensa: Despensa) -> None:
    """Tratar ml como g cobraria +89% na farinha de trigo."""
    r = receita("Massa", [ing("1 xícara de farinha", "farinha de trigo", 1, "xicara")])
    _, usos, _, _ = checar_ingredientes(r, despensa)

    correto = usos[0].custo
    errado = despensa["Farinha de trigo"].custo.valor * Decimal("0.240")

    assert correto.arredondado() == Dinheiro.de("0.66")
    assert errado.arredondado() == Dinheiro.de("1.24")
    assert errado.valor / correto.valor > Decimal("1.85")


def test_ingrediente_parecido_nao_e_substituido_em_silencio(despensa: Despensa) -> None:
    """'farinha de rosca' não pode virar 'Farinha de trigo'."""
    r = receita("Empanado", [ing("100 g de farinha de rosca", "farinha de rosca", 100, "g")])
    _, usos, faltantes, _ = checar_ingredientes(r, despensa)

    assert not usos, "não pode custear com o ingrediente errado"
    assert [f.nome for f in faltantes] == ["farinha de rosca"]


def test_a_gosto_nao_some_da_conta(despensa: Despensa, perfil_permissivo: PerfilCozinha) -> None:
    """Sal a gosto tem custo desprezível, mas aparece, em vez de sumir."""
    r = receita(
        "Arroz",
        [ing("1 xícara de arroz", "arroz", 1, "xicara"), ing("sal a gosto", "sal")],
    )
    cmv = calcular(r, avaliar(r, perfil_permissivo, despensa, gosto=Gosto.GOSTA))
    assert "sal" in cmv.itens_a_gosto
    assert "a gosto" in cmv.explicacao()


def test_incerteza_alta_vira_faixa_e_precifica_pelo_topo(
    despensa: Despensa, perfil_permissivo: PerfilCozinha
) -> None:
    """Medida caseira imprecisa não pode virar preço com precisão de centavo."""
    r = receita(
        "Queijo ralado puro",
        [ing("1 xícara de parmesão", "queijo parmesão ralado", 1, "xicara")],
    )
    cmv = calcular(r, avaliar(r, perfil_permissivo, despensa, gosto=Gosto.GOSTA))

    assert cmv.e_faixa, "±18% de densidade não pode virar número único"
    assert cmv.minimo.valor < cmv.total.valor < cmv.maximo.valor
    assert cmv.para_precificar == cmv.maximo, "na dúvida, o preço usa o topo"
