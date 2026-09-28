"""O que toda cozinha tem também passa pelo portão.

Fogão, panela, geladeira, faca: ninguém pergunta, e o portão supõe que ela tem.
Mas suposto não é certeza. Quando ela mesma diz "não tenho fogão", a receita de
fogão não pode aparecer como "dá pra fazer"; quando diz "não sei", o portão
pergunta em vez de supor. Sem resposta nenhuma, continua suposto, e a tela
mostra isso como suposto.
"""

from __future__ import annotations

import pytest

from mise.despensa import Despensa
from mise.perfil import Gosto, PerfilCozinha, Posse
from mise.receita import ingrediente as ing
from mise.receita import receita
from mise.viabilidade import (
    TipoRestricao,
    Veredito,
    avaliar,
    checar_equipamentos,
    checar_tecnicas,
)


def _arroz(*passos: str):  # type: ignore[no-untyped-def]
    return receita(
        "Arroz refogado",
        [ing("1 xícara de arroz", "arroz", 1, "xicara")],
        modo_preparo=passos or ("Refogue o arroz e cozinhe em fogo baixo por 20 minutos.",),
    )


# --------------------------------------------------------------------------- #
# Equipamento pressuposto
# --------------------------------------------------------------------------- #


def test_sem_resposta_o_pressuposto_passa_como_suposto() -> None:
    perfil = PerfilCozinha.inicial()
    assert perfil.suposto("fogao")
    c = checar_equipamentos(_arroz(), perfil)
    assert c.veredito is Veredito.APTO


def test_nao_tenho_fogao_bloqueia_com_o_motivo() -> None:
    perfil = PerfilCozinha.inicial().com_equipamento("fogao", Posse.NAO_TEM)
    c = checar_equipamentos(_arroz(), perfil)
    assert c.veredito is Veredito.BLOQUEADO
    (impedimento,) = c.impedimentos
    assert (impedimento.tipo, impedimento.id) == (TipoRestricao.EQUIPAMENTO, "fogao")
    assert impedimento.descricao == "a receita precisa de fogão e a senhora não tem"


def test_nao_sei_do_fogao_vira_pergunta() -> None:
    perfil = PerfilCozinha.inicial().sem_resposta("fogao")
    c = checar_equipamentos(_arroz(), perfil)
    assert c.veredito is Veredito.FALTA_INFO
    (pergunta,) = c.perguntas
    assert (pergunta.campo, pergunta.texto) == ("fogao", "A senhora tem fogão aí na cozinha?")
    assert pergunta.motivo == "Arroz refogado precisa de fogão"


def test_nao_tenho_geladeira_bloqueia_o_que_vai_ao_frio() -> None:
    mousse = receita(
        "Mousse",
        [ing("1 lata de creme de leite", "creme de leite", 1, "lata")],
        modo_preparo=["Misture e deixe gelar por 2 horas."],
    )
    perfil = PerfilCozinha.inicial().com_equipamento("geladeira", Posse.NAO_TEM)
    c = checar_equipamentos(mousse, perfil)
    assert [i.descricao for i in c.impedimentos] == [
        "a receita precisa de geladeira e a senhora não tem"
    ]


def test_pressuposto_com_substituto_que_ela_tem_passa() -> None:
    """Sem batedor de arame, a batedeira faz o serviço."""
    receita_de_fouet = receita(
        "Creme", [ing("2 ovos", "ovos", 2, "ovo")], modo_preparo=["Bata com o fouet."]
    )
    perfil = (
        PerfilCozinha.inicial()
        .com_equipamento("fouet", Posse.NAO_TEM)
        .com_equipamento("batedeira", Posse.TEM)
    )
    assert checar_equipamentos(receita_de_fouet, perfil).veredito is Veredito.APTO


def test_pressuposto_negado_pergunta_pelo_substituto_em_aberto() -> None:
    receita_de_fouet = receita(
        "Creme", [ing("2 ovos", "ovos", 2, "ovo")], modo_preparo=["Bata com o fouet."]
    )
    perfil = PerfilCozinha.inicial().com_equipamento("fouet", Posse.NAO_TEM)
    c = checar_equipamentos(receita_de_fouet, perfil)
    assert c.veredito is Veredito.FALTA_INFO
    assert [p.campo for p in c.perguntas] == ["batedeira"]


def test_nao_tenho_fogao_bloqueia_pelo_portao_inteiro(despensa: Despensa) -> None:
    """Pelo caminho real: o bloqueio vence, e o resumo diz o motivo a ela."""
    perfil = (
        PerfilCozinha.inicial()
        .com_equipamento("fogao", Posse.NAO_TEM)
        .com_restricao("tempo_max_por_fornada_min", 60)
    )
    a = avaliar(_arroz(), perfil, despensa, gosto=Gosto.GOSTA)
    assert a.veredito is Veredito.BLOQUEADO
    assert not a.permite_precificar
    assert "precisa de fogão e a senhora não tem" in a.resumo()


# --------------------------------------------------------------------------- #
# Técnica pressuposta
# --------------------------------------------------------------------------- #


def test_tecnica_pressuposta_sem_resposta_passa() -> None:
    assert checar_tecnicas(_arroz(), PerfilCozinha.inicial()).veredito is Veredito.APTO


def test_nao_faco_refogar_bloqueia() -> None:
    perfil = PerfilCozinha.inicial().com_tecnica("refogar", Posse.NAO_TEM)
    c = checar_tecnicas(_arroz(), perfil)
    assert c.veredito is Veredito.BLOQUEADO
    assert [i.descricao for i in c.impedimentos] == [
        "a receita pede refogar, que a senhora disse não fazer"
    ]


def test_nao_sei_se_faco_refogar_pergunta() -> None:
    perfil = PerfilCozinha.inicial().sem_resposta("refogar")
    c = checar_tecnicas(_arroz(), perfil)
    assert c.veredito is Veredito.FALTA_INFO
    assert [(p.campo, p.texto) for p in c.perguntas] == [
        ("refogar", "A senhora tem prática com refogar?")
    ]


@pytest.mark.parametrize("posse", [Posse.TEM, Posse.NAO_TEM])
def test_o_que_ela_disse_do_pressuposto_vale_como_qualquer_resposta(posse: Posse) -> None:
    perfil = PerfilCozinha.inicial().com_equipamento("fogao", posse)
    c = checar_equipamentos(_arroz(), perfil)
    assert (c.veredito is Veredito.APTO) is (posse is Posse.TEM)
