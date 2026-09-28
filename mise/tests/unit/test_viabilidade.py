"""O portão. Se algum destes testes cair, a garantia do §2.2 do desafio caiu junto."""

from __future__ import annotations

import pytest

from mise.despensa import Despensa
from mise.dinheiro import Dinheiro
from mise.perfil import Gosto, PerfilCozinha, Posse
from mise.receita import ingrediente as ing
from mise.receita import receita
from mise.viabilidade import (
    TipoRestricao,
    Veredito,
    avaliar,
    checar_equipamentos,
    checar_ingredientes,
    checar_operacional,
    checar_tecnicas,
)


@pytest.fixture
def perfil_vazio() -> PerfilCozinha:
    return PerfilCozinha.inicial()


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
def prato_no_forno():
    return receita(
        "Frango assado",
        [ing("500 g de peito de frango", "peito de frango", 500, "g")],
        modo_preparo=["Leve ao forno a 180 C e asse por 40 minutos."],
        tempo_cozimento_min=60,
    )


@pytest.fixture
def prato_simples():
    return receita(
        "Arroz com ovo",
        [
            ing("1 xícara de arroz", "arroz", 1, "xicara"),
            ing("2 ovos", "ovos", 2, "ovo"),
            ing("sal a gosto", "sal"),
        ],
        modo_preparo=["Cozinhe o arroz na panela por 20 minutos.", "Frite os ovos por 5 minutos."],
    )


# --------------------------------------------------------------------------- #
# A ordenação dos vereditos é a regra que torna tudo monótono
# --------------------------------------------------------------------------- #


def test_severidade_dos_vereditos() -> None:
    assert Veredito.APTO < Veredito.APTO_COM_COMPRA < Veredito.FALTA_INFO < Veredito.BLOQUEADO


def test_so_apto_permite_precificar() -> None:
    assert Veredito.APTO.permite_precificar
    assert Veredito.APTO_COM_COMPRA.permite_precificar
    assert not Veredito.FALTA_INFO.permite_precificar
    assert not Veredito.BLOQUEADO.permite_precificar


def test_rotulos_sao_legiveis() -> None:
    assert Veredito.APTO_COM_COMPRA.rotulo == "APTO COM COMPRA"
    assert Veredito.FALTA_INFO.rotulo == "FALTA INFO"


# --------------------------------------------------------------------------- #
# Equipamentos
# --------------------------------------------------------------------------- #


def test_desconhecido_gera_pergunta_e_nao_bloqueia(prato_no_forno, perfil_vazio) -> None:
    c = checar_equipamentos(prato_no_forno, perfil_vazio)
    assert c.veredito is Veredito.FALTA_INFO
    assert not c.impedimentos
    assert any(p.campo == "forno" for p in c.perguntas)


def test_ausencia_confirmada_bloqueia(prato_no_forno, perfil_vazio) -> None:
    perfil = (
        perfil_vazio.com_equipamento("forno", Posse.NAO_TEM)
        .com_equipamento("air_fryer", Posse.NAO_TEM)
        .com_equipamento("forno_eletrico", Posse.NAO_TEM)
    )
    c = checar_equipamentos(prato_no_forno, perfil)
    assert c.veredito is Veredito.BLOQUEADO
    assert "não tem" in c.impedimentos[0].descricao


def test_substituto_resolve_sem_bloquear(prato_no_forno, perfil_vazio) -> None:
    """Air fryer faz o serviço do forno: bloquear seria errado."""
    perfil = perfil_vazio.com_equipamento("forno", Posse.NAO_TEM).com_equipamento(
        "air_fryer", Posse.TEM
    )
    c = checar_equipamentos(prato_no_forno, perfil)
    assert c.veredito is Veredito.APTO


def test_sem_forno_mas_substituto_em_aberto_pergunta_em_vez_de_bloquear(
    prato_no_forno, perfil_vazio
) -> None:
    """Não bloqueia enquanto ainda há substituto por perguntar."""
    perfil = perfil_vazio.com_equipamento("forno", Posse.NAO_TEM)
    c = checar_equipamentos(prato_no_forno, perfil)
    assert c.veredito is Veredito.FALTA_INFO


def test_equipamento_pressuposto_nao_vira_pergunta(prato_simples, perfil_vazio) -> None:
    """Ninguém pergunta a uma cozinheira se ela tem faca."""
    c = checar_equipamentos(prato_simples, perfil_vazio)
    campos = {p.campo for p in c.perguntas}
    assert "faca" not in campos
    assert "fogao" not in campos


# --------------------------------------------------------------------------- #
# Técnicas
# --------------------------------------------------------------------------- #


def test_tecnica_desconhecida_pergunta(perfil_vazio) -> None:
    r = receita(
        "Lasanha",
        [ing("massa", "farinha de trigo", 500, "g")],
        modo_preparo=["Prepare o molho bechamel."],
    )
    c = checar_tecnicas(r, perfil_vazio)
    assert c.veredito is Veredito.FALTA_INFO
    assert any(p.campo == "bechamel" for p in c.perguntas)


def test_tecnica_negada_bloqueia(perfil_vazio) -> None:
    r = receita(
        "Lasanha",
        [ing("massa", "farinha de trigo", 500, "g")],
        modo_preparo=["Prepare o molho bechamel."],
    )
    perfil = perfil_vazio.com_tecnica("bechamel", Posse.NAO_TEM)
    c = checar_tecnicas(r, perfil)
    assert c.veredito is Veredito.BLOQUEADO


def test_tecnica_pressuposta_nao_pergunta(prato_simples, perfil_vazio) -> None:
    c = checar_tecnicas(prato_simples, perfil_vazio)
    assert not any(p.campo == "refogar" for p in c.perguntas)


# --------------------------------------------------------------------------- #
# Operacional
# --------------------------------------------------------------------------- #


def test_tempo_desconhecido_pergunta(prato_no_forno, perfil_vazio) -> None:
    c = checar_operacional(prato_no_forno, perfil_vazio)
    assert any(p.campo == "tempo_max_por_fornada_min" for p in c.perguntas)


def test_tempo_insuficiente_bloqueia(prato_no_forno, perfil_vazio) -> None:
    """O passo diz 40 min de forno: vale ele, e não os 60 de cozimento que a receita declara."""
    perfil = perfil_vazio.com_restricao("tempo_max_por_fornada_min", 30)
    c = checar_operacional(prato_no_forno, perfil)
    assert c.veredito is Veredito.BLOQUEADO
    assert c.impedimentos[0].descricao == (
        "pelo passo 1, são 40 minutos no forno; a senhora tem 30 por cozinhada"
    )


def test_tempo_suficiente_passa(prato_no_forno, perfil_vazio) -> None:
    perfil = perfil_vazio.com_restricao("tempo_max_por_fornada_min", 120)
    assert checar_operacional(prato_no_forno, perfil).veredito is Veredito.APTO


def test_receita_sem_tempo_pergunta_primeiro_o_tempo_dela(perfil_vazio) -> None:
    """Sem o limite dela, o portão pergunta o limite; o tempo da receita fica para depois."""
    r = receita(
        "Arroz com ovo",
        [ing("1 xícara de arroz", "arroz", 1, "xicara")],
        modo_preparo=["Cozinhe o arroz na panela.", "Frite os ovos."],
    )
    c = checar_operacional(r, perfil_vazio)
    campos = [p.campo for p in c.perguntas]
    assert campos == ["tempo_max_por_fornada_min"]
    assert c.perguntas[0].motivo == "para saber se arroz com ovo cabe numa cozinhada"


def test_varias_panelas_sem_dizer_que_andam_juntas_nao_pedem_bocas(perfil_vazio) -> None:
    """Frigideira, panela funda e pressão numa receita não são três bocas acesas juntas.

    A conta antiga somava os equipamentos de cozinhar, com o próprio fogão
    contando como panela, e uma boca bloqueava o prato.
    """
    r = receita(
        "Prato de várias panelas",
        [ing("arroz", "arroz", 1, "xicara")],
        modo_preparo=[
            "Na frigideira, doure. Em panela funda, ferva. Na panela de pressão, cozinhe."
        ],
    )
    for bocas in (None, 1):
        perfil = perfil_vazio.com_restricao("bocas_fogao", bocas)
        c = checar_operacional(r, perfil)
        assert not any(i.id == "bocas_fogao" for i in c.impedimentos)
        assert not any(p.campo == "bocas_fogao" for p in c.perguntas)
        assert not c.avisos


def test_outra_panela_sem_saber_o_fogao_pergunta(perfil_vazio) -> None:
    r = receita(
        "Arroz e feijão",
        [ing("arroz", "arroz", 1, "xicara")],
        modo_preparo=["Cozinhe o feijão.", "Em outra panela, refogue o arroz."],
    )
    c = checar_operacional(r, perfil_vazio)
    (bocas,) = (p for p in c.perguntas if p.campo == "bocas_fogao")
    assert bocas.motivo == "Arroz e feijão usa duas panelas no fogo ao mesmo tempo (passo 2)"


# --------------------------------------------------------------------------- #
# Ingredientes
# --------------------------------------------------------------------------- #


def test_tudo_na_despensa_passa(prato_simples, despensa: Despensa) -> None:
    c, usos, faltantes, a_gosto = checar_ingredientes(prato_simples, despensa)
    assert c.veredito is Veredito.APTO
    assert not faltantes
    assert len(usos) == 2
    assert a_gosto == ("sal",)


def test_ingrediente_ausente_vira_compra(despensa: Despensa) -> None:
    r = receita(
        "Frango com calabresa",
        [
            ing("500 g de frango", "peito de frango", 500, "g"),
            ing("200 g de linguiça calabresa", "linguiça calabresa", 200, "g"),
        ],
    )
    c, _, faltantes, _ = checar_ingredientes(r, despensa)
    # Sem preço (aqui, sem as referências), nada se pergunta: a receita fica de fora.
    assert c.veredito is Veredito.BLOQUEADO
    assert not c.perguntas
    assert [f.nome for f in faltantes] == ["linguiça calabresa"]


def test_ingrediente_opcional_ausente_nao_vira_compra(despensa: Despensa) -> None:
    r = receita(
        "Frango",
        [
            ing("500 g de frango", "peito de frango", 500, "g"),
            ing("cebolinha para decorar", "cebolinha francesa", 10, "g", opcional=True),
        ],
    )
    _, _, faltantes, _ = checar_ingredientes(r, despensa)
    assert not faltantes


def test_embalagem_opaca_usa_o_peso_estimado_e_nao_pergunta(despensa: Despensa) -> None:
    """A cobertura de chocolate: o peso vem estimado pela página do supermercado, com a fonte.

    Nunca "1 un" tratado como 1 g ou como 1 kg sem fonte: 200 g da embalagem de
    cerca de 1 kg por R$ 79,90 custam R$ 15,98, e a conta diz que o peso é estimativa.
    """
    r = receita(
        "Bolo de chocolate",
        [ing("200 g de cobertura de chocolate", "Cobertura de chocolate", 200, "g")],
    )
    c, usos, _, _ = checar_ingredientes(r, despensa)
    assert c.veredito is Veredito.APTO
    assert not c.perguntas
    assert str(usos[0].custo.arredondado()) == "R$ 15,98"


def test_estoque_insuficiente_vira_compra(despensa: Despensa) -> None:
    """Ela tem 2 kg de frango; a receita pede 5 kg."""
    r = receita("Frangaço", [ing("5 kg de frango", "peito de frango", 5, "kg")])
    _, _, faltantes, _ = checar_ingredientes(r, despensa)
    assert faltantes
    assert "faltam" in faltantes[0].quantidade_texto


def test_compra_alem_do_orcamento_bloqueia(despensa: Despensa) -> None:
    r = receita("Prato caro", [ing("1 kg de trufa", "trufa negra", 1, "kg")])
    c, _, faltantes, _ = checar_ingredientes(r, despensa, orcamento_restante=Dinheiro.de("80.00"))
    # sem preço em fonte nenhuma, não se pergunta: não dá para confirmar que cabe
    assert c.veredito is Veredito.BLOQUEADO
    assert not c.perguntas
    assert faltantes and not faltantes[0].custo_conhecido


# --------------------------------------------------------------------------- #
# Combinação: a parte que não pode falhar
# --------------------------------------------------------------------------- #


def test_veredito_e_o_pior_das_checagens(prato_no_forno, perfil_vazio, despensa) -> None:
    a = avaliar(prato_no_forno, perfil_vazio, despensa, gosto=Gosto.GOSTA)
    assert a.veredito == max(c.veredito for c in a.checagens)


def test_bloqueio_vence_falta_info(prato_no_forno, perfil_vazio, despensa) -> None:
    """Quando já se sabe que é impossível, não se continua perguntando."""
    perfil = (
        perfil_vazio.com_equipamento("forno", Posse.NAO_TEM)
        .com_equipamento("air_fryer", Posse.NAO_TEM)
        .com_equipamento("forno_eletrico", Posse.NAO_TEM)
    )
    a = avaliar(prato_no_forno, perfil, despensa, gosto=Gosto.GOSTA)
    assert a.veredito is Veredito.BLOQUEADO
    assert a.perguntas, "as perguntas continuam registradas"
    assert not a.permite_precificar


def test_perfil_completo_aprova(prato_simples, perfil_completo, despensa) -> None:
    a = avaliar(prato_simples, perfil_completo, despensa, gosto=Gosto.GOSTA)
    assert a.veredito is Veredito.APTO
    assert a.permite_precificar
    assert "dá pra fazer hoje" in a.resumo()


def test_resumo_de_cada_veredito(prato_no_forno, perfil_vazio, perfil_completo, despensa) -> None:
    """O resumo é o que a tela mostra: as palavras dela, não o nome do veredito."""
    falta = avaliar(prato_no_forno, perfil_vazio, despensa, gosto=Gosto.GOSTA).resumo()
    assert "antes de decidir, preciso saber" in falta
    assert "FALTA INFO" not in falta
    perfil = (
        perfil_vazio.com_equipamento("forno", Posse.NAO_TEM)
        .com_equipamento("air_fryer", Posse.NAO_TEM)
        .com_equipamento("forno_eletrico", Posse.NAO_TEM)
    )
    assert "esse não dá" in avaliar(prato_no_forno, perfil, despensa, gosto=Gosto.GOSTA).resumo()


def test_custo_das_compras_e_none_quando_falta_preco(despensa, perfil_completo) -> None:
    r = receita("X", [ing("1 kg de trufa", "trufa negra", 1, "kg")])
    a = avaliar(r, perfil_completo, despensa, gosto=Gosto.GOSTA)
    assert a.custo_das_compras is None


def test_custo_das_compras_zero_sem_faltantes(prato_simples, perfil_completo, despensa) -> None:
    a = avaliar(prato_simples, perfil_completo, despensa, gosto=Gosto.GOSTA)
    assert a.custo_das_compras == Dinheiro.zero()


def test_impedimentos_e_perguntas_agregam_todas_as_checagens(
    prato_no_forno, perfil_vazio, despensa
) -> None:
    a = avaliar(prato_no_forno, perfil_vazio, despensa, gosto=Gosto.GOSTA)
    assert len(a.perguntas) == sum(len(c.perguntas) for c in a.checagens)
    assert len(a.impedimentos) == sum(len(c.impedimentos) for c in a.checagens)


def test_tipos_de_restricao_sao_distintos() -> None:
    tipos = {
        TipoRestricao.INGREDIENTE,
        TipoRestricao.EQUIPAMENTO,
        TipoRestricao.TECNICA,
        TipoRestricao.OPERACIONAL,
    }
    assert len(tipos) == 4


def test_str_de_impedimento_e_pergunta(prato_no_forno, perfil_vazio, despensa) -> None:
    a = avaliar(prato_no_forno, perfil_vazio, despensa, gosto=Gosto.GOSTA)
    assert str(a.perguntas[0]) == a.perguntas[0].texto


# --------------------------------------------------------------------------- #
# O portão não aprova o que não conferiu
# --------------------------------------------------------------------------- #


def test_sem_modo_de_preparo_pergunta_como_ela_faz(perfil_completo, despensa) -> None:
    """Um bolo colado só com ingredientes passava como apto sem ninguém perguntar do forno."""
    r = receita("Bolo de cenoura", [ing("2 xícaras de farinha", "farinha de trigo", 2, "xicara")])
    a = avaliar(r, perfil_completo, despensa, gosto=Gosto.GOSTA)
    assert a.veredito is Veredito.FALTA_INFO
    assert not a.permite_precificar
    (pergunta,) = a.perguntas
    assert pergunta.campo == "modo_preparo"
    assert "Como a senhora faz bolo de cenoura" in pergunta.texto


def test_sem_forno_pergunta_pelo_substituto_e_nao_pelo_forno(despensa) -> None:
    """ "Não tenho forno" levava de volta a "a senhora tem forno?"."""
    r = receita(
        "Frango assado",
        [ing("1 kg de frango", "peito de frango", 1, "kg")],
        modo_preparo=["Leve ao forno por 50 minutos."],
    )
    perfil = PerfilCozinha.inicial().com_equipamentos([("forno", Posse.NAO_TEM)])
    campos = [p.campo for p in avaliar(r, perfil, despensa, gosto=Gosto.GOSTA).perguntas]
    assert "forno" not in campos
    assert "air_fryer" in campos

    perfil = perfil.com_equipamentos([("air_fryer", Posse.NAO_TEM)])
    campos = [p.campo for p in avaliar(r, perfil, despensa, gosto=Gosto.GOSTA).perguntas]
    assert "forno_eletrico" in campos

    perfil = perfil.com_equipamentos([("forno_eletrico", Posse.NAO_TEM)])
    assert avaliar(r, perfil, despensa, gosto=Gosto.GOSTA).veredito is Veredito.BLOQUEADO


def test_air_fryer_salva_o_prato_sem_forno(despensa) -> None:
    r = receita(
        "Frango assado",
        [ing("1 kg de frango", "peito de frango", 1, "kg")],
        modo_preparo=["Leve ao forno por 50 minutos."],
    )
    perfil = PerfilCozinha.inicial().com_equipamentos(
        [("forno", Posse.NAO_TEM), ("air_fryer", Posse.TEM)]
    )
    campos = [p.campo for p in avaliar(r, perfil, despensa, gosto=Gosto.GOSTA).perguntas]
    assert not any(c in {"forno", "air_fryer", "forno_eletrico"} for c in campos)
