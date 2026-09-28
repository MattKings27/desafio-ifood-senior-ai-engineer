"""O caminho completo do custo de uma compra complementar.

O §2.3 do desafio pede, para cada receita viável, "o que falta comprar, o custo
disso e se cabe no orçamento restante". O §2.4 manda incluir esse custo no CMV.

Antes destes testes o sistema fazia a pergunta e não tinha como receber a
resposta: `ItemFaltante.custo_estimado` não era atribuído em lugar nenhum do
repositório, então o ramo que compara com o orçamento era inalcançável e o CMV
somava zero de compra complementar, em silêncio.

Cada teste aqui percorre o caminho real (avaliar, registrar, reavaliar) e não
constrói `ItemFaltante` na mão. Um teste que monta o objeto já preenchido teria
passado o tempo todo, inclusive quando nada preenchia.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from mise.despensa import Despensa
from mise.dinheiro import Dinheiro
from mise.dossie import Dossie, OrigemPreco
from mise.perfil import Gosto, PerfilCozinha, Posse
from mise.receita import ingrediente as ing
from mise.receita import receita
from mise.viabilidade import TipoRestricao, Veredito, avaliar, checar_ingredientes

# Nada disso existe na despensa da Dona Maria, e é o ponto.
AUSENTE = "trufa branca"


@pytest.fixture
def perfil_completo() -> PerfilCozinha:
    base = PerfilCozinha.inicial()
    base = base.com_equipamentos((e, Posse.TEM) for e in base.equipamentos)
    base = base.com_tecnicas((t, Posse.TEM) for t in base.tecnicas)
    return (
        base.com_restricao("bocas_fogao", 4)
        .com_restricao("tempo_max_por_fornada_min", 120)
        .com_restricao("porcoes_por_fornada", 20)
    )


@pytest.fixture
def prato_com_faltante():
    return receita(
        "Risoto de trufa",
        [
            ing("1 xícara de arroz", "arroz", 1, "xicara"),
            ing(f"20 g de {AUSENTE}", AUSENTE, 20, "g"),
        ],
        rendimento_porcoes=4,
        modo_preparo=["Cozinhe o arroz na panela por 25 minutos e finalize com a trufa."],
    )


@pytest.fixture
def dossie(tmp_path) -> Dossie:
    with Dossie(tmp_path / "dossie.db") as d:
        yield d


# --------------------------------------------------------------------------- #
# Sem cotação: pergunta, e nada além disso                                     #
# --------------------------------------------------------------------------- #


def test_sem_preco_o_motor_pergunta(despensa: Despensa, prato_com_faltante) -> None:
    checagem, _, faltantes, _ = checar_ingredientes(prato_com_faltante, despensa)

    # Não é APTO_COM_COMPRA: sem preço em fonte nenhuma o motor não sabe se a
    # compra cabe, e afirmar "apto com compra" seria afirmar mais do que ele sabe.
    # E o preço nunca é pergunta: a receita fica de fora, com o motivo.
    assert checagem.veredito is Veredito.BLOQUEADO
    assert [f.nome for f in faltantes] == [AUSENTE]
    assert faltantes[0].custo_estimado is None
    assert not checagem.perguntas
    assert any(i.id == "sem_preco" for i in checagem.impedimentos)


def test_sem_preco_nao_da_para_falar_de_orcamento(despensa: Despensa, prato_com_faltante) -> None:
    """Recusar-se a comparar é o comportamento certo: não sabemos o valor."""
    checagem, _, _, _ = checar_ingredientes(
        prato_com_faltante, despensa, orcamento_restante=Dinheiro(Decimal("5.00"))
    )
    assert checagem.veredito is Veredito.BLOQUEADO
    assert [i.id for i in checagem.impedimentos] == ["sem_preco"]


# --------------------------------------------------------------------------- #
# Com cotação: o custo chega, e a comparação acontece                          #
# --------------------------------------------------------------------------- #


def test_com_preco_o_custo_chega_ao_faltante(despensa: Despensa, prato_com_faltante) -> None:
    _, _, faltantes, _ = checar_ingredientes(
        prato_com_faltante, despensa, precos={AUSENTE: Dinheiro(Decimal("18.00"))}
    )
    assert faltantes[0].custo_estimado == Dinheiro(Decimal("18.00"))
    assert faltantes[0].custo_conhecido


def test_com_preco_a_pergunta_some(despensa: Despensa, prato_com_faltante) -> None:
    checagem, _, _, _ = checar_ingredientes(
        prato_com_faltante, despensa, precos={AUSENTE: Dinheiro(Decimal("18.00"))}
    )
    assert not any("quanto custa" in p.texto.lower() for p in checagem.perguntas)


def test_compra_que_estoura_o_orcamento_bloqueia(despensa: Despensa, prato_com_faltante) -> None:
    """O §2.3 em uma linha: o preço entra, o orçamento decide, o prato cai."""
    checagem, _, _, _ = checar_ingredientes(
        prato_com_faltante,
        despensa,
        orcamento_restante=Dinheiro(Decimal("10.00")),
        precos={AUSENTE: Dinheiro(Decimal("95.00"))},
    )

    assert checagem.veredito is Veredito.BLOQUEADO
    motivos = " ".join(i.descricao for i in checagem.impedimentos)
    assert "R$ 95,00" in motivos
    assert "R$ 10,00" in motivos


def test_compra_que_cabe_nao_bloqueia(despensa: Despensa, prato_com_faltante) -> None:
    checagem, _, _, _ = checar_ingredientes(
        prato_com_faltante,
        despensa,
        orcamento_restante=Dinheiro(Decimal("80.00")),
        precos={AUSENTE: Dinheiro(Decimal("18.00"))},
    )
    assert checagem.veredito is Veredito.APTO_COM_COMPRA
    assert not checagem.impedimentos


def test_cotacao_casa_sem_depender_de_grafia(despensa: Despensa, prato_com_faltante) -> None:
    """Quem digita a cotação não repete a grafia da receita, e não deveria ter que."""
    _, _, faltantes, _ = checar_ingredientes(
        prato_com_faltante, despensa, precos={"  Trufa Branca  ": Dinheiro(Decimal("18.00"))}
    )
    assert faltantes[0].custo_estimado == Dinheiro(Decimal("18.00"))


# --------------------------------------------------------------------------- #
# O caminho real, atravessando o dossiê                                        #
# --------------------------------------------------------------------------- #


def test_registrar_preco_muda_o_veredito(
    despensa: Despensa, perfil_completo: PerfilCozinha, prato_com_faltante, dossie: Dossie
) -> None:
    """Avaliar, registrar, reavaliar, sem construir `ItemFaltante` na mão.

    É o teste que só passa se a ferramenta, o armazenamento e a checagem
    estiverem de fato conectados. Qualquer um dos três desligado o derruba.
    """
    sobrando = Dinheiro(Decimal("12.00"))

    antes = avaliar(
        prato_com_faltante,
        perfil_completo,
        despensa,
        orcamento_restante=sobrando,
        precos=dossie.precos_conhecidos(),
        gosto=Gosto.GOSTA,
    )
    assert antes.veredito is Veredito.BLOQUEADO
    assert not any(p.tipo is TipoRestricao.INGREDIENTE for p in antes.perguntas)

    dossie.registrar_preco(AUSENTE, Dinheiro(Decimal("95.00")), OrigemPreco.INFORMADO_POR_ELA)

    depois = avaliar(
        prato_com_faltante,
        perfil_completo,
        despensa,
        orcamento_restante=sobrando,
        precos=dossie.precos_conhecidos(),
        gosto=Gosto.GOSTA,
    )
    assert depois.veredito is Veredito.BLOQUEADO
    assert not depois.permite_precificar


def test_cotacao_mais_nova_substitui_a_anterior(dossie: Dossie) -> None:
    """Preço é fato corrente. A cotação de ontem só atrapalharia."""
    dossie.registrar_preco(AUSENTE, Dinheiro(Decimal("95.00")), OrigemPreco.ESTIMADO)
    dossie.registrar_preco(AUSENTE, Dinheiro(Decimal("42.00")), OrigemPreco.INFORMADO_POR_ELA)

    guardado = dossie.preco_de(AUSENTE)
    assert guardado is not None
    assert guardado.valor == Dinheiro(Decimal("42.00"))
    assert guardado.origem is OrigemPreco.INFORMADO_POR_ELA
    assert len(dossie.precos()) == 1


def test_origem_aparece_no_texto(dossie: Dossie) -> None:
    """A conversa precisa distinguir o que ela disse do que a gente chutou."""
    preco = dossie.registrar_preco(
        AUSENTE, Dinheiro(Decimal("42.00")), OrigemPreco.PESQUISADO_NA_WEB
    )
    assert "pesquisado na web" in str(preco)
    assert "R$ 42,00" in str(preco)


def test_preco_negativo_e_recusado(dossie: Dossie) -> None:
    from mise.erros import ErroDeUso

    with pytest.raises(ErroDeUso):
        dossie.registrar_preco(AUSENTE, Dinheiro(Decimal("-1.00")), OrigemPreco.ESTIMADO)


def test_ingrediente_sem_nome_e_recusado(dossie: Dossie) -> None:
    from mise.erros import ErroDeUso

    with pytest.raises(ErroDeUso):
        dossie.registrar_preco("   ", Dinheiro(Decimal("1.00")), OrigemPreco.ESTIMADO)


def test_sem_cotacao_nenhuma_o_mapa_e_vazio(dossie: Dossie) -> None:
    assert dossie.precos_conhecidos() == {}


def test_cotacao_de_outro_ingrediente_nao_vale(despensa: Despensa, prato_com_faltante) -> None:
    """Ter cotação de alguma coisa não é ter cotação desta coisa."""
    _, _, faltantes, _ = checar_ingredientes(
        prato_com_faltante, despensa, precos={"açafrão": Dinheiro(Decimal("9.00"))}
    )
    assert faltantes[0].custo_estimado is None


def test_cmv_inclui_a_compra_como_linha_propria(
    despensa: Despensa, perfil_completo: PerfilCozinha, prato_com_faltante, dossie: Dossie
) -> None:
    """§2.4: o custo da compra complementar entra no CMV, e entra visível.

    Somado por fora, o total não fecharia com as linhas mostradas na tela, e
    numa ferramenta cujo argumento é "a conta está aberta", um total que não
    bate com as próprias parcelas custa mais do que o erro que esconderia.
    """
    from mise.cmv import calcular

    dossie.registrar_preco(AUSENTE, Dinheiro(Decimal("20.00")), OrigemPreco.INFORMADO_POR_ELA)
    avaliacao = avaliar(
        prato_com_faltante,
        perfil_completo,
        despensa,
        orcamento_restante=Dinheiro(Decimal("80.00")),
        precos=dossie.precos_conhecidos(),
        gosto=Gosto.GOSTA,
    )
    assert avaliacao.permite_precificar

    resultado = calcular(prato_com_faltante, avaliacao)

    compra = [linha for linha in resultado.linhas if "(comprar)" in linha.ingrediente]
    assert len(compra) == 1
    # R$ 20,00 divididos pelas 4 porções da receita.
    assert compra[0].custo == Dinheiro(Decimal("5.00"))
    assert "÷ 4 porções" in compra[0].derivacao

    # E o total fecha com a soma das linhas, que é o ponto.
    soma = Dinheiro.zero()
    for linha in resultado.linhas:
        soma = soma + linha.custo
    assert soma == resultado.total


def test_cmv_recusa_enquanto_a_cotacao_faltar(
    despensa: Despensa, perfil_completo: PerfilCozinha, prato_com_faltante
) -> None:
    """Sem preço, o CMV sairia parcial, e parcial apresentado como total mente."""
    from mise.cmv import calcular
    from mise.erros import CustoIndeterminado, ViabilidadeNaoConfirmada

    avaliacao = avaliar(
        prato_com_faltante, perfil_completo, despensa, orcamento_restante=Dinheiro(Decimal("80.00"))
    )
    with pytest.raises((CustoIndeterminado, ViabilidadeNaoConfirmada)):
        calcular(prato_com_faltante, avaliacao)
