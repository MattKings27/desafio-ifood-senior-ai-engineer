""" "Não sei" volta o item ao padrão; a completude conta as seis restrições."""

from __future__ import annotations

from dataclasses import replace

import pytest

from mise.despensa import Despensa
from mise.erros import ErroDeUso, VocabularioDesconhecido
from mise.perfil import (
    FORMATOS_OPERACIONAIS,
    PERGUNTAS_OPERACIONAIS,
    FormatoDaRestricao,
    PerfilCozinha,
    Posse,
    TipoDeCampo,
    contagem,
)
from mise.receita import ingrediente, receita
from mise.taxonomia import EQUIPAMENTOS, TECNICAS
from mise.viabilidade import avaliar

# --------------------------------------------------------------------------- #
# sem_resposta
# --------------------------------------------------------------------------- #


def test_nao_sei_volta_o_equipamento_a_ainda_nao_perguntado() -> None:
    p = PerfilCozinha.inicial().com_equipamento("forno", Posse.NAO_TEM)
    assert "forno" in p.confirmados

    depois = p.sem_resposta("forno")
    assert depois.tem_equipamento("forno") is Posse.DESCONHECIDO
    assert "forno" not in depois.confirmados
    assert depois.respondidos == 0


@pytest.mark.parametrize("antes", [Posse.NAO_TEM, Posse.TEM, None])
def test_nao_sei_do_que_toda_cozinha_tem_fica_em_aberto(antes: Posse | None) -> None:
    """ "Não sei se tenho fogão" é resposta dela: o fogão não volta a "tem" suposto.

    Voltar ao suposto deixava o portão liberar receita de fogão sem ninguém saber
    se havia fogão. Vale a partir do "não tenho", do "tenho" e de nada dito.
    """
    p = PerfilCozinha.inicial()
    if antes is not None:
        p = p.com_equipamento("fogao", antes)
    depois = p.sem_resposta("fogao")
    assert depois.tem_equipamento("fogao") is Posse.DESCONHECIDO
    assert not depois.suposto("fogao")
    assert "fogao" not in depois.confirmados
    assert "fogao" in depois.equipamentos_em_aberto


def test_nao_sei_de_tecnica() -> None:
    p = (
        PerfilCozinha.inicial()
        .com_tecnica("bechamel", Posse.TEM)
        .com_tecnica("fritar", Posse.NAO_TEM)
    )
    depois = p.sem_resposta("bechamel").sem_resposta("fritar")
    assert depois.domina_tecnica("bechamel") is Posse.DESCONHECIDO
    assert depois.domina_tecnica("fritar") is Posse.DESCONHECIDO, (
        "pressuposta também fica em aberto"
    )
    assert depois.confirmados == frozenset()


def test_nao_sei_do_pressuposto_sobrevive_a_ida_e_volta_do_dossie() -> None:
    p = PerfilCozinha.inicial().sem_resposta("fogao").sem_resposta("refogar")
    volta = PerfilCozinha.de_dict(p.para_dict())
    assert volta == p
    assert volta.tem_equipamento("fogao") is Posse.DESCONHECIDO
    assert volta.domina_tecnica("refogar") is Posse.DESCONHECIDO


def test_nao_sei_de_restricao_volta_a_none() -> None:
    p = PerfilCozinha.inicial().com_restricao("bocas_fogao", 4)
    depois = p.sem_resposta("bocas_fogao")
    assert depois.restricoes.bocas_fogao is None
    assert "bocas_fogao" in depois.restricoes.pendencias()


def test_nao_sei_nao_mexe_no_resto() -> None:
    p = (
        PerfilCozinha.inicial()
        .com_equipamento("forno", Posse.TEM)
        .com_equipamento("air_fryer", Posse.NAO_TEM)
        .com_restricao("bocas_fogao", 4)
    )
    depois = p.sem_resposta("forno")
    assert depois.tem_equipamento("air_fryer") is Posse.NAO_TEM
    assert depois.restricoes.bocas_fogao == 4
    assert depois.confirmados == frozenset({"air_fryer"})


def test_nao_sei_do_que_nao_existe_e_recusado() -> None:
    with pytest.raises(VocabularioDesconhecido, match="item da cozinha"):
        PerfilCozinha.inicial().sem_resposta("teletransportador")


def test_nao_sei_sobrevive_a_ida_e_volta_do_dossie() -> None:
    p = PerfilCozinha.inicial().com_equipamento("forno", Posse.TEM).sem_resposta("forno")
    assert PerfilCozinha.de_dict(p.para_dict()) == p


# --------------------------------------------------------------------------- #
# suposto, contagens e resumo
# --------------------------------------------------------------------------- #


def test_suposto_e_so_o_tem_que_ninguem_perguntou() -> None:
    p = PerfilCozinha.inicial()
    assert p.suposto("fogao")
    assert p.suposto("refogar")
    assert not p.suposto("forno"), "desconhecido não é suposto"
    assert not p.com_equipamento("fogao", Posse.TEM).suposto("fogao"), "ela disse"
    assert not p.suposto("inexistente")


def test_cada_item_e_respondido_suposto_ou_em_aberto() -> None:
    """As três contagens somam o vocabulário inteiro, antes e depois do "não sei"."""
    total = len(EQUIPAMENTOS) + len(TECNICAS)
    p = (
        PerfilCozinha.inicial()
        .com_equipamento("forno", Posse.TEM)
        .com_tecnica("fritar", Posse.NAO_TEM)
    )
    for perfil in (PerfilCozinha.inicial(), p, p.sem_resposta("forno"), p.sem_resposta("fritar")):
        assert perfil.respondidos + perfil.supostos + perfil.em_aberto == total


def test_fracao_respondida_tem_quatro_casas() -> None:
    p = PerfilCozinha.inicial()
    assert p.fracao_respondida == 0.0
    um = p.com_equipamento("forno", Posse.TEM)
    assert um.fracao_respondida == round(1 / (len(EQUIPAMENTOS) + len(TECNICAS)), 4) == 0.0159


def test_resumo_para_a_tela_fala_com_ela() -> None:
    p = PerfilCozinha.inicial()
    assert p.resumo_para_a_tela() == (
        f"0 respondidos pela senhora · {p.supostos} supostos · {p.em_aberto} ainda não perguntei"
    )
    um = p.com_equipamento("forno", Posse.TEM)
    assert um.resumo_para_a_tela().startswith("1 respondido pela senhora · ")


def test_nao_sei_sai_a_parte_no_resumo_e_o_progresso_diz_de_quantos() -> None:
    p = PerfilCozinha.inicial()
    assert p.resumo_para_a_tela(nao_sabe=2) == (
        f"0 respondidos pela senhora · {p.supostos} supostos · 2 que a senhora não sabe · "
        f"{p.em_aberto - 2} ainda não perguntei"
    )
    total = len(EQUIPAMENTOS) + len(TECNICAS)
    assert p.progresso_para_a_tela() == f"0 de {total} respondidos pela senhora"
    um = p.com_equipamento("forno", Posse.NAO_TEM)
    assert um.progresso_para_a_tela() == f"1 de {total} respondidos pela senhora"


# --------------------------------------------------------------------------- #
# Plural: só o um vai no singular
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("n", "texto"), [(0, "0 receitas"), (1, "1 receita"), (2, "2 receitas")])
def test_contagem_so_o_um_e_singular(n: int, texto: str) -> None:
    assert contagem(n, "receita", "receitas") == texto


def _perfil_com(respondidos: int, supostos: int) -> PerfilCozinha:
    """Um perfil com exatamente essas contagens: o resto fica em aberto.

    O estado é montado direto, sem resposta dela: `com_equipamentos` conta como
    resposta, e o suposto é justamente o que ninguém respondeu.
    """
    inicial = PerfilCozinha.inicial()
    ficam = set(("faca", "tabua")[:supostos])
    p = replace(
        inicial,
        equipamentos={
            e: Posse.TEM if e in ficam else Posse.DESCONHECIDO for e in inicial.equipamentos
        },
        tecnicas=dict.fromkeys(inicial.tecnicas, Posse.DESCONHECIDO),
    )
    for id_ in ("forno", "batedeira")[:respondidos]:
        p = p.com_equipamento(id_, Posse.NAO_TEM)
    assert (p.respondidos, p.supostos) == (respondidos, supostos)
    return p


@pytest.mark.parametrize(
    ("n", "respondido", "suposto"),
    [(0, "respondidos", "supostos"), (1, "respondido", "suposto"), (2, "respondidos", "supostos")],
)
def test_resumos_do_perfil_no_singular_e_no_plural(n: int, respondido: str, suposto: str) -> None:
    p = _perfil_com(respondidos=n, supostos=n)
    assert p.resumo() == (
        f"{n} {respondido} por ela · {n} {suposto} de qualquer cozinha · {p.em_aberto} em aberto"
    )
    assert p.resumo_para_a_tela() == (
        f"{n} {respondido} pela senhora · {n} {suposto} · {p.em_aberto} ainda não perguntei"
    )


def test_uma_resposta_e_um_respondido() -> None:
    """ "1 respondidos por ela" saía no resumo do agente e na tela."""
    um = PerfilCozinha.inicial().com_equipamento("forno", Posse.TEM)
    assert um.resumo().startswith("1 respondido por ela · ")
    assert um.resumo_para_a_tela().startswith("1 respondido pela senhora · ")


# --------------------------------------------------------------------------- #
# completude
# --------------------------------------------------------------------------- #


def test_completude_conta_as_seis_restricoes() -> None:
    """A conta antiga somava 3 − pendências: com as seis em aberto, a parte das restrições dava −3."""
    p = PerfilCozinha.inicial()
    campos = len(PERGUNTAS_OPERACIONAIS)
    total = len(p.equipamentos) + len(p.tecnicas) + campos
    resolvidos = sum(1 for x in p.equipamentos.values() if x.resolvido) + sum(
        1 for x in p.tecnicas.values() if x.resolvido
    )
    assert p.completude == resolvidos / total


def test_cada_restricao_respondida_move_a_completude() -> None:
    """Antes, responder as três primeiras não movia nada: a parte das restrições estava negativa."""
    p = PerfilCozinha.inicial()
    anterior = p.completude
    for campo, valor in (
        ("bocas_fogao", 4),
        ("tempo_max_por_fornada_min", 120),
        ("porcoes_por_fornada", 20),
        ("tem_gas_sobrando", True),
        ("espaco_geladeira_litros", 20),
        ("energia_aparelhos_simultaneos", 2),
    ):
        p = p.com_restricao(campo, valor)
        assert p.completude > anterior, campo
        anterior = p.completude


def test_nao_sei_devolve_a_completude() -> None:
    p = PerfilCozinha.inicial()
    com_forno = p.com_equipamento("forno", Posse.TEM)
    assert com_forno.completude > p.completude
    assert com_forno.sem_resposta("forno").completude == p.completude


# --------------------------------------------------------------------------- #
# Formato das restrições
# --------------------------------------------------------------------------- #


def test_toda_restricao_tem_formato() -> None:
    assert set(FORMATOS_OPERACIONAIS) == set(PERGUNTAS_OPERACIONAIS)
    assert FORMATOS_OPERACIONAIS["tem_gas_sobrando"].tipo is TipoDeCampo.SIM_NAO
    for campo, formato in FORMATOS_OPERACIONAIS.items():
        if formato.tipo is TipoDeCampo.INTEIRO:
            assert formato.unidade, campo
            assert formato.minimo is not None
            assert formato.maximo is not None
            assert formato.minimo < formato.maximo


def test_geladeira_sem_espaco_e_resposta_valida() -> None:
    """Zero litros bloqueia o que precisa gelar: tem de caber na faixa."""
    assert FORMATOS_OPERACIONAIS["espaco_geladeira_litros"].conferir(0) == 0


@pytest.mark.parametrize(
    ("campo", "valor", "esperado"),
    [
        ("bocas_fogao", 4, 4),
        ("bocas_fogao", 4.0, 4),
        ("bocas_fogao", None, None),
        ("tem_gas_sobrando", True, True),
        ("tem_gas_sobrando", False, False),
        ("tem_gas_sobrando", None, None),
        # O tempo por cozinhada chega em horas e é guardado em minutos.
        ("tempo_max_por_fornada_min", 12, 720),
        ("tempo_max_por_fornada_min", 1.5, 90),
        ("tempo_max_por_fornada_min", 0.5, 30),
        ("tempo_max_por_fornada_min", None, None),
    ],
)
def test_valor_no_tipo_da_restricao(campo: str, valor: object, esperado: object) -> None:
    assert FORMATOS_OPERACIONAIS[campo].conferir(valor) == esperado


@pytest.mark.parametrize(
    ("campo", "valor", "trecho"),
    [
        ("bocas_fogao", 80, "entre 1 e 8 bocas"),
        ("bocas_fogao", 0, "entre 1 e 8 bocas"),
        ("bocas_fogao", 4.5, "número inteiro"),
        ("bocas_fogao", True, "número inteiro"),
        ("bocas_fogao", float("inf"), "número inteiro"),
        ("bocas_fogao", "4", "número inteiro"),
        ("tem_gas_sobrando", 1, "sim ou não"),
        ("tem_gas_sobrando", "sim", "sim ou não"),
        ("tempo_max_por_fornada_min", 13, "entre meia hora e 12 horas"),
        ("tempo_max_por_fornada_min", 0.25, "entre meia hora e 12 horas"),
        ("tempo_max_por_fornada_min", 0, "maior que zero"),
        ("tempo_max_por_fornada_min", "2", "quantas horas"),
        ("tempo_max_por_fornada_min", True, "quantas horas"),
        ("tempo_max_por_fornada_min", float("nan"), "quantas horas"),
    ],
)
def test_valor_fora_do_tipo_ou_da_faixa_e_recusado(campo: str, valor: object, trecho: str) -> None:
    with pytest.raises(ErroDeUso, match=trecho):
        FORMATOS_OPERACIONAIS[campo].conferir(valor)


def test_formato_sem_faixa_aceita_qualquer_inteiro() -> None:
    livre = FormatoDaRestricao(TipoDeCampo.INTEIRO, "vezes")
    assert livre.conferir(10_000) == 10_000


@pytest.mark.parametrize(
    ("passos", "trecho"),
    [
        (
            ["Cozinhe o arroz por 20 minutos.", "Em outra panela, refogue o alho por 5 minutos."],
            "O passo 2 pede outra panela",
        ),
        (
            [
                "Em outra panela, doure a cebola por 5 minutos.",
                "Cozinhe o arroz por 20 minutos.",
                "Numa frigideira à parte, sele o frango por 10 minutos.",
            ],
            "Os passos 1 e 3 pedem outra panela",
        ),
    ],
)
def test_aviso_das_bocas_no_singular_e_no_plural(
    despensa: Despensa, passos: list[str], trecho: str
) -> None:
    """Com uma boca só, o aviso diz quais passos pedem outra panela, sem "(s)" e sem bloquear."""
    r = receita(
        "Frango", [ingrediente("500 g de frango", "peito de frango", 500, "g")], modo_preparo=passos
    )
    perfil = PerfilCozinha.inicial().com_restricao("bocas_fogao", 1)
    avaliacao = avaliar(r, perfil, despensa)
    (aviso,) = avaliacao.avisos
    assert aviso.texto.startswith(trecho)
    assert "Com uma boca, a senhora faz uma parte depois da outra" in aviso.texto
    assert "(s)" not in aviso.texto
    assert "bocas_fogao" not in {i.id for i in avaliacao.impedimentos}
