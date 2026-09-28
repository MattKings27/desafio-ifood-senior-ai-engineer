"""CMV e modelo de receita, incluindo as três recusas do motor."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from mise.cmv import LIMIAR_FAIXA, calcular
from mise.despensa import Despensa
from mise.dinheiro import Dinheiro
from mise.erros import (
    CustoIndeterminado,
    QuantidadeInvalida,
    ViabilidadeNaoConfirmada,
    VocabularioDesconhecido,
)
from mise.perfil import Gosto, PerfilCozinha, Posse
from mise.receita import Receita
from mise.receita import ingrediente as ing
from mise.receita import receita as _receita
from mise.viabilidade import ItemFaltante, avaliar


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
def perfil() -> PerfilCozinha:
    p = PerfilCozinha.inicial()
    p = p.com_equipamentos((e, Posse.TEM) for e in p.equipamentos)
    p = p.com_tecnicas((t, Posse.TEM) for t in p.tecnicas)
    return p.com_restricao("bocas_fogao", 6).com_restricao("tempo_max_por_fornada_min", 480)


# --------------------------------------------------------------------------- #
# Receita
# --------------------------------------------------------------------------- #


def test_rendimento_minimo_e_uma_porcao() -> None:
    with pytest.raises(QuantidadeInvalida, match="rendimento"):
        receita("X", [ing("a", "arroz", 1, "kg")], rendimento_porcoes=0)


def test_receita_sem_ingredientes_e_rejeitada() -> None:
    with pytest.raises(QuantidadeInvalida, match="sem ingredientes"):
        Receita(nome="Vazia", ingredientes=())


def test_vocabulario_controlado_na_receita() -> None:
    with pytest.raises(VocabularioDesconhecido):
        Receita(
            nome="X",
            ingredientes=(ing("a", "arroz", 1, "kg"),),
            equipamentos=frozenset({"teletransportador"}),
        )
    with pytest.raises(VocabularioDesconhecido):
        Receita(
            nome="X",
            ingredientes=(ing("a", "arroz", 1, "kg"),),
            tecnicas=frozenset({"alquimia"}),
        )


def test_quantidade_negativa_em_ingrediente() -> None:
    with pytest.raises(QuantidadeInvalida):
        ing("a", "arroz", -1, "kg")


def test_a_gosto_e_quantificados_se_separam() -> None:
    r = receita(
        "X",
        [ing("1 kg de arroz", "arroz", 1, "kg"), ing("sal a gosto", "sal")],
    )
    assert len(r.ingredientes_quantificados) == 1
    assert len(r.ingredientes_a_gosto) == 1
    assert r.ingredientes_a_gosto[0].a_gosto


def test_str_de_ingrediente() -> None:
    assert str(ing("x", "arroz", 2, "kg")) == "2 kg de arroz"
    assert str(ing("x", "sal")) == "sal (a gosto)"


def test_str_de_receita() -> None:
    r = receita("Bolo", [ing("a", "arroz", 1, "kg")], rendimento_porcoes=8, fonte="site.com")
    assert "Bolo" in str(r)
    assert "site.com" in str(r)
    assert "8" in str(r)


def test_procedencia() -> None:
    sem = receita("X", [ing("a", "arroz", 1, "kg")])
    com = receita("X", [ing("a", "arroz", 1, "kg")], url="https://x.com/r")
    assert not sem.tem_procedencia
    assert com.tem_procedencia


def test_por_porcao_divide_tudo() -> None:
    r = receita(
        "Rende 4",
        [ing("2 kg de arroz", "arroz", 2, "kg"), ing("sal a gosto", "sal")],
        rendimento_porcoes=4,
    )
    uma = r.por_porcao()
    assert uma.rendimento_porcoes == 1
    assert uma.ingredientes[0].quantidade == Decimal("0.5")
    assert uma.ingredientes[1].a_gosto, "a gosto continua a gosto"


def test_por_porcao_e_idempotente() -> None:
    r = receita("X", [ing("1 kg", "arroz", 1, "kg")], rendimento_porcoes=1)
    assert r.por_porcao() is r


def test_deteccao_de_exigencias_no_modo_de_preparo() -> None:
    r = receita(
        "Assado",
        [ing("a", "arroz", 1, "kg")],
        modo_preparo=["Leve ao forno a 180 C.", "Bata no liquidificador."],
    )
    assert "forno" in r.equipamentos
    assert "liquidificador" in r.equipamentos


def test_exigencias_declaradas_sao_preservadas() -> None:
    r = receita("X", [ing("a", "arroz", 1, "kg")], equipamentos=["panela_pressao"])
    assert "panela_pressao" in r.equipamentos


# --------------------------------------------------------------------------- #
# As três recusas do CMV
# --------------------------------------------------------------------------- #


def test_recusa_sem_viabilidade(despensa: Despensa) -> None:
    r = receita(
        "No forno",
        [ing("500 g de frango", "peito de frango", 500, "g")],
        modo_preparo=["Leve ao forno."],
    )
    sem_forno = (
        PerfilCozinha.inicial()
        .com_equipamento("forno", Posse.NAO_TEM)
        .com_equipamento("air_fryer", Posse.NAO_TEM)
        .com_equipamento("forno_eletrico", Posse.NAO_TEM)
    )
    with pytest.raises(ViabilidadeNaoConfirmada) as exc:
        calcular(r, avaliar(r, sem_forno, despensa, gosto=Gosto.GOSTA))
    assert exc.value.veredito == "BLOQUEADO"
    assert exc.value.pendencias


def test_recusa_com_custo_indeterminado(despensa: Despensa, perfil: PerfilCozinha) -> None:
    from mise.viabilidade import Avaliacao, Checagem, Veredito

    r = receita("X", [ing("1 kg de arroz", "arroz", 1, "kg")])
    avaliacao = avaliar(r, perfil, despensa, gosto=Gosto.GOSTA)
    # força um faltante sem preço, mantendo o veredito apto
    manipulada = Avaliacao(
        receita_nome=r.nome,
        veredito=Veredito.APTO_COM_COMPRA,
        checagens=(Checagem("x", Veredito.APTO_COM_COMPRA),),
        usos=avaliacao.usos,
        faltantes=(ItemFaltante("trufa", "50 g"),),
    )
    with pytest.raises(CustoIndeterminado, match="1 ingrediente"):
        calcular(r, manipulada)


def test_faixa_quando_a_incerteza_e_alta(despensa: Despensa, perfil: PerfilCozinha) -> None:
    r = receita("Queijo", [ing("1 xícara de parmesão", "queijo parmesão ralado", 1, "xicara")])
    cmv = calcular(r, avaliar(r, perfil, despensa, gosto=Gosto.GOSTA))
    assert cmv.incerteza_relativa > LIMIAR_FAIXA
    assert cmv.e_faixa
    assert cmv.para_precificar == cmv.maximo


def test_ponto_quando_a_incerteza_e_baixa(despensa: Despensa, perfil: PerfilCozinha) -> None:
    r = receita("Frango", [ing("1 kg de frango", "peito de frango", 1, "kg")])
    cmv = calcular(r, avaliar(r, perfil, despensa, gosto=Gosto.GOSTA))
    assert cmv.incerteza_relativa == 0
    assert not cmv.e_faixa
    assert cmv.para_precificar == cmv.total.arredondado()


# --------------------------------------------------------------------------- #
# Composição
# --------------------------------------------------------------------------- #


def test_compra_complementar_entra_no_cmv(despensa: Despensa, perfil: PerfilCozinha) -> None:
    """O §2.4 manda incluir o custo das compras complementares."""
    from mise.viabilidade import Avaliacao, Checagem, Veredito

    r = receita("X", [ing("1 kg de arroz", "arroz", 1, "kg")], rendimento_porcoes=2)
    base = avaliar(r, perfil, despensa, gosto=Gosto.GOSTA)
    com_compra = Avaliacao(
        receita_nome=r.nome,
        veredito=Veredito.APTO_COM_COMPRA,
        checagens=(Checagem("x", Veredito.APTO_COM_COMPRA),),
        usos=base.usos,
        faltantes=(ItemFaltante("linguiça", "200 g", Dinheiro.de("10.00")),),
    )
    cmv = calcular(r, com_compra)
    # arroz 1kg = 4,98; /2 porções = 2,49. linguiça 10,00 /2 = 5,00.
    assert cmv.total.arredondado() == Dinheiro.de("7.49")


def test_maiores_custos_ordena_por_peso(despensa: Despensa, perfil: PerfilCozinha) -> None:
    r = receita(
        "Misto",
        [
            ing("1 kg de frango", "peito de frango", 1, "kg"),
            ing("10 g de sal", "sal", 10, "g"),
            ing("200 g de mussarela", "mussarela", 200, "g"),
        ],
    )
    cmv = calcular(r, avaliar(r, perfil, despensa, gosto=Gosto.GOSTA))
    nomes = [linha.ingrediente for linha in cmv.maiores_custos(2)]
    assert nomes == ["Peito de frango", "Queijo mussarela"]


def test_a_conta_de_cada_linha_mostra_a_divisao_pelas_porcoes(
    despensa: Despensa, perfil: PerfilCozinha
) -> None:
    """A linha vale uma porção; a conta dela tem que chegar lá, não parar na receita."""
    r = receita("Rende 4", [ing("1 kg de arroz", "arroz", 1, "kg")], rendimento_porcoes=4)
    (linha,) = calcular(r, avaliar(r, perfil, despensa, gosto=Gosto.GOSTA)).linhas
    assert linha.derivacao.endswith("÷ 4 porções")
    uma = receita("Rende 1", [ing("1 kg de arroz", "arroz", 1, "kg")], rendimento_porcoes=1)
    (linha,) = calcular(uma, avaliar(uma, perfil, despensa, gosto=Gosto.GOSTA)).linhas
    assert "porç" not in linha.derivacao


def test_explicacao_menciona_rendimento_quando_houve_divisao(
    despensa: Despensa, perfil: PerfilCozinha
) -> None:
    r = receita("Rende 4", [ing("1 kg de arroz", "arroz", 1, "kg")], rendimento_porcoes=4)
    texto = calcular(r, avaliar(r, perfil, despensa, gosto=Gosto.GOSTA)).explicacao()
    assert "rende 4 porções" in texto


def test_explicacao_nao_menciona_rendimento_de_uma_porcao(
    despensa: Despensa, perfil: PerfilCozinha
) -> None:
    r = receita("Uma", [ing("1 kg de arroz", "arroz", 1, "kg")])
    assert "rende" not in calcular(r, avaliar(r, perfil, despensa, gosto=Gosto.GOSTA)).explicacao()


def test_incerteza_e_ponderada_pelo_custo(despensa: Despensa, perfil: PerfilCozinha) -> None:
    """Uma pitada de sal imprecisa não pode contaminar um prato dominado por carne."""
    r = receita(
        "Carne com pitada",
        [
            ing("1 kg de frango", "peito de frango", 1, "kg"),
            ing("1 pitada de sal", "sal", 1, "pitada"),
        ],
    )
    cmv = calcular(r, avaliar(r, perfil, despensa, gosto=Gosto.GOSTA))
    assert cmv.incerteza_relativa < Decimal("0.001")


def test_linha_do_cmv_carrega_derivacao(despensa: Despensa, perfil: PerfilCozinha) -> None:
    r = receita("X", [ing("1 kg de arroz", "arroz", 1, "kg")])
    linha = calcular(r, avaliar(r, perfil, despensa, gosto=Gosto.GOSTA)).linhas[0]
    assert "R$ 4,98/kg" in linha.derivacao
    assert linha.participacao_texto == linha.derivacao


def test_estoque_parcial_nao_e_cobrado_duas_vezes(
    despensa: Despensa, perfil: PerfilCozinha
) -> None:
    """1 kg de alcatra com 0,8 kg em casa, a R$ 42,50/kg, rende 4.

    O prato consome 0,8 kg da casa (R$ 34,00) e 0,2 kg de reposição, que sem
    cotação sai ao preço que ela pagou (R$ 8,50): R$ 42,50, ou R$ 10,625 por
    porção. Antes, o quilo inteiro entrava como uso **e** os 200 g entravam de
    novo como compra, e o custo saía 20% acima.
    """
    r = receita(
        "Alcatra", [ing("1 kg de alcatra", "miolo de alcatra", 1, "kg")], rendimento_porcoes=4
    )
    avaliacao = avaliar(r, perfil, despensa, gosto=Gosto.GOSTA)

    (faltante,) = avaliacao.faltantes
    assert faltante.parcial
    assert faltante.custo_estimado == Dinheiro.de("8.50")
    assert "planilha" in faltante.premissa or "pagou" in faltante.premissa

    cmv = calcular(r, avaliacao)
    assert [linha.ingrediente for linha in cmv.linhas] == [
        "Miolo de alcatra",
        "Miolo de alcatra (comprar)",
    ]
    assert cmv.total == Dinheiro.de("10.625")
    assert cmv.para_precificar == Dinheiro.de("10.63")


def test_cotacao_por_quilo_separa_consumo_de_desembolso(
    despensa: Despensa, perfil: PerfilCozinha
) -> None:
    """Faltam 200 g; no açougue dela a alcatra sai R$ 50 o quilo e só vende o quilo.

    O prato consome 200 g a R$ 50/kg = R$ 10,00. Ela desembolsa R$ 50,00. O CMV
    leva os R$ 10; o orçamento, os R$ 50.
    """
    from mise.compras import Cotacao, medida

    r = receita(
        "Alcatra", [ing("1 kg de alcatra", "miolo de alcatra", 1, "kg")], rendimento_porcoes=4
    )
    por_quilo = medida(1, "kg", "alcatra")
    avaliacao = avaliar(
        r,
        perfil,
        despensa,
        gosto=Gosto.GOSTA,
        precos={"Miolo de alcatra": Cotacao(Dinheiro.de("50"), por_quilo)},
    )
    (faltante,) = avaliacao.faltantes
    assert faltante.custo_estimado == Dinheiro.de("50")
    assert faltante.custo_no_prato == Dinheiro.de("10")
    assert not faltante.premissa
    # 34,00 da casa + 10,00 da compra = 44,00 ÷ 4
    assert calcular(r, avaliacao).total == Dinheiro.de("11")


def test_cotacao_sem_quantidade_vai_com_a_premissa(
    despensa: Despensa, perfil: PerfilCozinha
) -> None:
    """ "A alcatra sai R$ 10": sem saber por quanto, a conta assume que é o que falta."""
    r = receita(
        "Alcatra", [ing("1 kg de alcatra", "miolo de alcatra", 1, "kg")], rendimento_porcoes=4
    )
    avaliacao = avaliar(
        r, perfil, despensa, gosto=Gosto.GOSTA, precos={"miolo de alcatra": Dinheiro.de("10")}
    )
    (faltante,) = avaliacao.faltantes
    assert faltante.custo_estimado == Dinheiro.de("10")
    assert "quantidade" in faltante.premissa
    linha = calcular(r, avaliacao).linhas[-1]
    assert faltante.premissa in linha.derivacao


def test_o_que_ela_comprou_sai_da_lista_e_entra_no_custo(
    despensa: Despensa, perfil: PerfilCozinha
) -> None:
    """Ela comprou 200 g de alcatra por R$ 11. Não falta mais nada.

    Sem isso a compra registrada continuava como faltante, o orçamento era
    descontado de novo e o prato podia travar por "estourar" um dinheiro que
    já tinha sido gasto.
    """
    from mise.compras import Comprado, medida

    r = receita(
        "Alcatra", [ing("1 kg de alcatra", "miolo de alcatra", 1, "kg")], rendimento_porcoes=4
    )
    duzentos = medida(200, "g", "alcatra")
    assert duzentos is not None
    avaliacao = avaliar(
        r,
        perfil,
        despensa,
        gosto=Gosto.GOSTA,
        orcamento_restante=Dinheiro.de("0"),
        compras={"Miolo de alcatra": Comprado(duzentos, Dinheiro.de("11"))},
    )
    assert not avaliacao.faltantes
    assert avaliacao.permite_precificar
    cmv = calcular(r, avaliacao)
    assert [linha.ingrediente for linha in cmv.linhas] == [
        "Miolo de alcatra",
        "Miolo de alcatra (comprado)",
    ]
    assert cmv.total == Dinheiro.de("11.25")  # (34,00 + 11,00) ÷ 4


def test_explicacao_soma_os_mesmos_centavos_da_tela() -> None:
    """Somando as linhas que ela ouve, chega-se ao total que ela ouve.

    Arredondar cada linha sozinha dava R$ 1,01 + R$ 1,01 com o total de R$ 2,01.
    """
    from mise.cmv import CMV, LinhaCMV

    linhas = tuple(
        LinhaCMV(nome, "1 un", Dinheiro.de("1.005"), "1 un", Decimal(0))
        for nome in ("ovo", "leite")
    )
    texto = CMV("Pudim", linhas, Dinheiro.de("2.01"), Decimal(0)).explicacao()
    assert "ovo: 1 un = R$ 1,01" in texto
    assert "leite: 1 un = R$ 1,00" in texto
    assert "Total: R$ 2,01" in texto
