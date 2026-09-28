"""As quatro restrições que o §2.2 nomeia, ligadas ao portão.

"O agente não pode deixar ela comprar ingrediente e descobrir depois que não
consegue cozinhar." Energia, gás, espaço na geladeira e tempo por cozinhada são
as quatro formas de descobrir tarde demais, e antes destes testes três delas
existiam só como campo: declaradas, serializadas, nunca lidas pelo portão.

Cada teste aqui força o caminho completo: receita com a exigência, perfil com ou
sem a resposta, veredito resultante.
"""

from __future__ import annotations

import pytest

from mise.despensa import Despensa
from mise.perfil import Gosto, PerfilCozinha, Posse
from mise.receita import ingrediente as ing
from mise.receita import receita
from mise.viabilidade import TipoRestricao, Veredito, avaliar, checar_operacional


@pytest.fixture
def perfil_base() -> PerfilCozinha:
    """Tudo resolvido menos as restrições que cada teste exercita."""
    p = PerfilCozinha.inicial()
    p = p.com_equipamentos((e, Posse.TEM) for e in p.equipamentos)
    p = p.com_tecnicas((t, Posse.TEM) for t in p.tecnicas)
    return (
        p.com_restricao("bocas_fogao", 4)
        .com_restricao("tempo_max_por_fornada_min", 240)
        .com_restricao("porcoes_por_fornada", 20)
    )


def _arroz(**extras):
    return receita("Prato", [ing("1 kg de arroz", "arroz", 1, "kg")], **extras)


# --------------------------------------------------------------------------- #
# Energia                                                                      #
# --------------------------------------------------------------------------- #


def test_dois_aparelhos_de_potencia_geram_pergunta(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Bata na batedeira.", "Leve à air fryer por 20 minutos."])
    c = checar_operacional(r.com_exigencias_detectadas(), perfil_base)

    assert c.veredito is Veredito.FALTA_INFO
    assert any(p.campo == "energia_aparelhos_simultaneos" for p in c.perguntas)


def test_um_aparelho_so_nao_pergunta_nada(perfil_base: PerfilCozinha) -> None:
    """Sem disputa de disjuntor, perguntar seria ruído."""
    r = _arroz(modo_preparo=["Bata na batedeira."])
    c = checar_operacional(r.com_exigencias_detectadas(), perfil_base)
    assert not any(p.campo == "energia_aparelhos_simultaneos" for p in c.perguntas)


def test_instalacao_que_nao_aguenta_bloqueia(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Bata na batedeira.", "Leve à air fryer por 20 minutos."])
    perfil = perfil_base.com_restricao("energia_aparelhos_simultaneos", 1)

    c = checar_operacional(r.com_exigencias_detectadas(), perfil)
    assert c.veredito is Veredito.BLOQUEADO
    assert any("disjuntor" in i.evidencia for i in c.impedimentos)


def test_instalacao_que_aguenta_libera(perfil_base: PerfilCozinha) -> None:
    r = _arroz(
        modo_preparo=["Bata na batedeira por 5 minutos.", "Leve à air fryer por 20 minutos."]
    )
    perfil = perfil_base.com_restricao("energia_aparelhos_simultaneos", 3)

    c = checar_operacional(r.com_exigencias_detectadas(), perfil)
    assert c.veredito is Veredito.APTO


def test_fogao_a_gas_nao_conta_como_energia(perfil_base: PerfilCozinha) -> None:
    """Fogão a gás não disputa disjuntor com nada."""
    r = _arroz(modo_preparo=["Refogue na panela.", "Cozinhe em fogo baixo."])
    perfil = perfil_base.com_restricao("energia_aparelhos_simultaneos", 1)

    c = checar_operacional(r.com_exigencias_detectadas(), perfil)
    assert not any(i.id == "energia_aparelhos_simultaneos" for i in c.impedimentos)


# --------------------------------------------------------------------------- #
# Gás                                                                          #
# --------------------------------------------------------------------------- #


def test_fornada_longa_no_fogo_pergunta_do_botijao(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Cozinhe em fogo baixo."], tempo_cozimento_min=90)
    c = checar_operacional(r.com_exigencias_detectadas(), perfil_base)

    assert any(p.campo == "tem_gas_sobrando" for p in c.perguntas)


def test_fornada_curta_nao_pergunta_do_botijao(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Cozinhe em fogo baixo."], tempo_cozimento_min=20)
    c = checar_operacional(r.com_exigencias_detectadas(), perfil_base)

    assert not any(p.campo == "tem_gas_sobrando" for p in c.perguntas)


def test_sem_reserva_de_gas_bloqueia_fornada_longa(perfil_base: PerfilCozinha) -> None:
    """Acabar o gás no meio estraga o pedido já vendido, não só a fornada."""
    r = _arroz(modo_preparo=["Cozinhe em fogo baixo."], tempo_cozimento_min=90)
    perfil = perfil_base.com_restricao("tem_gas_sobrando", False)

    c = checar_operacional(r.com_exigencias_detectadas(), perfil)
    assert c.veredito is Veredito.BLOQUEADO
    assert any("botijão de reserva" in i.descricao for i in c.impedimentos)


def test_com_reserva_de_gas_libera(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Cozinhe em fogo baixo."], tempo_cozimento_min=90)
    perfil = perfil_base.com_restricao("tem_gas_sobrando", True)

    c = checar_operacional(r.com_exigencias_detectadas(), perfil)
    assert not any(i.id == "tem_gas_sobrando" for i in c.impedimentos)


def test_receita_sem_fogo_nao_pergunta_de_gas(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Bata na batedeira."], tempo_cozimento_min=120)
    c = checar_operacional(r.com_exigencias_detectadas(), perfil_base)

    assert not any(p.campo == "tem_gas_sobrando" for p in c.perguntas)


# --------------------------------------------------------------------------- #
# Geladeira                                                                    #
# --------------------------------------------------------------------------- #


def test_preparo_que_gela_pergunta_do_espaco(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Leve à geladeira por 4 horas."])
    c = checar_operacional(r.com_exigencias_detectadas(), perfil_base)

    assert any(p.campo == "espaco_geladeira_litros" for p in c.perguntas)


def test_geladeira_sem_espaco_bloqueia(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Leve à geladeira por 4 horas."])
    perfil = perfil_base.com_restricao("espaco_geladeira_litros", 0)

    c = checar_operacional(r.com_exigencias_detectadas(), perfil)
    assert c.veredito is Veredito.BLOQUEADO
    assert any("espaço na geladeira" in i.descricao for i in c.impedimentos)


def test_geladeira_com_espaco_libera(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Leve à geladeira por 4 horas."])
    perfil = perfil_base.com_restricao("espaco_geladeira_litros", 15)

    c = checar_operacional(r.com_exigencias_detectadas(), perfil)
    assert not any(i.id == "espaco_geladeira_litros" for i in c.impedimentos)


def test_receita_sem_frio_nao_pergunta_de_geladeira(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Refogue na panela."])
    c = checar_operacional(r.com_exigencias_detectadas(), perfil_base)

    assert not any(p.campo == "espaco_geladeira_litros" for p in c.perguntas)


# --------------------------------------------------------------------------- #
# As quatro juntas, pelo caminho real                                          #
# --------------------------------------------------------------------------- #


def test_a_pior_restricao_manda(perfil_base: PerfilCozinha, despensa: Despensa) -> None:
    """Uma receita que esbarra em gás e geladeira ao mesmo tempo é bloqueada."""
    r = receita(
        "Prato difícil",
        [ing("1 kg de arroz", "arroz", 1, "kg")],
        modo_preparo=["Cozinhe em fogo baixo.", "Leve à geladeira por 4 horas."],
        tempo_cozimento_min=90,
    ).com_exigencias_detectadas()
    perfil = perfil_base.com_restricao("tem_gas_sobrando", False).com_restricao(
        "espaco_geladeira_litros", 0
    )

    a = avaliar(r, perfil, despensa, gosto=Gosto.GOSTA)
    assert a.veredito is Veredito.BLOQUEADO
    assert not a.permite_precificar

    ids = {i.id for i in a.impedimentos if i.tipo is TipoRestricao.OPERACIONAL}
    assert ids == {"tem_gas_sobrando", "espaco_geladeira_litros"}


def test_tudo_respondido_e_dentro_do_limite_aprova(
    perfil_base: PerfilCozinha, despensa: Despensa
) -> None:
    r = receita(
        "Prato tranquilo",
        [ing("1 kg de arroz", "arroz", 1, "kg")],
        modo_preparo=["Cozinhe em fogo baixo.", "Leve à geladeira por 4 horas."],
        tempo_cozimento_min=90,
    ).com_exigencias_detectadas()
    perfil = (
        perfil_base.com_restricao("tem_gas_sobrando", True)
        .com_restricao("espaco_geladeira_litros", 20)
        .com_restricao("energia_aparelhos_simultaneos", 2)
    )

    a = avaliar(r, perfil, despensa, gosto=Gosto.GOSTA)
    assert a.veredito is Veredito.APTO
    assert a.permite_precificar


# --------------------------------------------------------------------------- #
# Tempo ativo contra o tempo por cozinhada                                     #
# --------------------------------------------------------------------------- #


def _com_limite(perfil: PerfilCozinha, minutos: int | None) -> PerfilCozinha:
    return perfil.com_restricao("tempo_max_por_fornada_min", minutos)


def test_tempo_ativo_acima_do_limite_bloqueia_com_a_conta(perfil_base: PerfilCozinha) -> None:
    r = _arroz(
        modo_preparo=[
            "Cozinhe o feijão na panela de pressão por 40 minutos.",
            "Junte as carnes e cozinhe em fogo baixo por 50 minutos.",
        ]
    )
    c = checar_operacional(r, _com_limite(perfil_base, 60))
    assert c.veredito is Veredito.BLOQUEADO
    (impedimento,) = c.impedimentos
    assert impedimento.id == "tempo_max_por_fornada_min"
    assert impedimento.descricao == (
        "pelos passos, 40 + 50 = 90 minutos no fogo; a senhora tem 60 por cozinhada"
    )
    assert "as esperas não contam" in impedimento.evidencia


def test_um_passo_so_diz_qual_passo(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Tempere.", "Asse no forno por 90 minutos."])
    c = checar_operacional(r, _com_limite(perfil_base, 60))
    assert [i.descricao for i in c.impedimentos] == [
        "pelo passo 2, são 90 minutos no forno; a senhora tem 60 por cozinhada"
    ]


def test_espera_passiva_nao_conta_no_tempo(perfil_base: PerfilCozinha) -> None:
    """Doze horas de marinada e 40 minutos de forno cabem em uma hora de cozinhada."""
    r = _arroz(
        modo_preparo=[
            "Tempere o frango e deixe marinar por 12 horas na geladeira.",
            "Asse no forno por 40 minutos.",
        ],
        tempo_total_min=760,
    )
    perfil = _com_limite(perfil_base, 60).com_restricao("espaco_geladeira_litros", 20)
    c = checar_operacional(r, perfil)
    assert c.veredito is Veredito.APTO


def test_sem_tempo_nos_passos_usa_o_cozimento_declarado(perfil_base: PerfilCozinha) -> None:
    r = _arroz(
        modo_preparo=["Cozinhe o feijão em fogo baixo até desmanchar."], tempo_cozimento_min=180
    )
    perfil = _com_limite(perfil_base, 60).com_restricao("tem_gas_sobrando", True)
    c = checar_operacional(r, perfil)
    assert [i.descricao for i in c.impedimentos] == [
        "a receita diz que o cozimento leva 180 minutos; a senhora tem 60 por cozinhada"
    ]
    assert c.impedimentos[0].evidencia == "tempo de cozimento que a receita declara"


def test_tempo_dentro_do_limite_passa(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Cozinhe o arroz na panela por 20 minutos."])
    assert checar_operacional(r, _com_limite(perfil_base, 60)).veredito is Veredito.APTO


def test_tempo_desconhecido_com_o_limite_dito_pergunta_o_tempo_da_receita(
    perfil_base: PerfilCozinha,
) -> None:
    r = receita(
        "Risoto",
        [ing("1 xícara de arroz", "arroz", 1, "xicara")],
        modo_preparo=["Cozinhe o arroz."],
    )
    c = checar_operacional(r, _com_limite(perfil_base, 60))
    # O tempo da receita nunca é pergunta: sem ele, não dá para confirmar que cabe.
    assert c.veredito is Veredito.BLOQUEADO
    assert not c.perguntas
    (impedimento,) = c.impedimentos
    assert impedimento.id == "tempo_max_por_fornada_min"
    assert impedimento.descricao == (
        "a receita não diz quanto tempo fica no fogo, no forno ou com aparelho ligado; com 1 "
        "hora por cozinhada, não dá para confirmar que cabe"
    )


def test_tempo_total_dentro_do_limite_dispensa_a_pergunta(perfil_base: PerfilCozinha) -> None:
    """Se nem o total, com as esperas, passa do limite, o tempo de fogo também não passa."""
    curto = _arroz(modo_preparo=["Cozinhe o arroz."], tempo_total_min=25)
    assert checar_operacional(curto, _com_limite(perfil_base, 60)).veredito is Veredito.APTO

    longo = _arroz(modo_preparo=["Cozinhe o arroz."], tempo_total_min=90)
    c = checar_operacional(longo, _com_limite(perfil_base, 60))
    assert not c.perguntas
    assert "a receita diz 90 minutos no total" in c.impedimentos[0].descricao


def test_sem_passos_o_tempo_espera_o_modo_de_preparo(perfil_base: PerfilCozinha) -> None:
    """Sem passos, o portão já pergunta como ela faz: perguntar o tempo seria perguntar duas vezes."""
    sem_passos = _arroz(tempo_preparo_min=180)
    c = checar_operacional(sem_passos, _com_limite(perfil_base, 60))
    assert not any(p.campo.startswith("tempo") for p in c.perguntas)
    assert not c.impedimentos


def test_receita_que_nao_liga_nada_nao_tem_tempo_a_conferir(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Misture tudo e sirva."])
    for limite in (None, 5):
        c = checar_operacional(r, _com_limite(perfil_base, limite))
        assert not any(p.campo.startswith("tempo") for p in c.perguntas)
        assert not c.impedimentos


def test_sem_o_limite_dela_pergunta_o_limite_com_o_tempo_da_receita(
    perfil_base: PerfilCozinha,
) -> None:
    r = _arroz(modo_preparo=["Asse no forno por 40 minutos."])
    c = checar_operacional(r, _com_limite(perfil_base, None))
    (pergunta,) = c.perguntas
    assert pergunta.campo == "tempo_max_por_fornada_min"
    assert pergunta.motivo == "Prato fica 40 minutos no forno"


def test_sem_o_limite_dela_o_cozimento_declarado_nao_diz_onde(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Cozinhe o arroz."], tempo_cozimento_min=30)
    (pergunta,) = checar_operacional(r, _com_limite(perfil_base, None)).perguntas
    assert pergunta.motivo == "Prato fica 30 minutos no fogo ou no forno"


# --------------------------------------------------------------------------- #
# Bocas: outra panela ao mesmo tempo                                           #
# --------------------------------------------------------------------------- #

_OUTRA_PANELA = [
    "Cozinhe o macarrão em água fervente por 10 minutos.",
    "Em outra panela, refogue o alho e junte o tomate; cozinhe por 15 minutos.",
]


def test_outra_panela_com_duas_bocas_passa(perfil_base: PerfilCozinha) -> None:
    perfil = perfil_base.com_restricao("bocas_fogao", 2)
    c = checar_operacional(_arroz(modo_preparo=_OUTRA_PANELA), perfil)
    assert c.veredito is Veredito.APTO
    assert not c.avisos


def test_outra_panela_com_uma_boca_avisa_sem_bloquear(perfil_base: PerfilCozinha) -> None:
    perfil = perfil_base.com_restricao("bocas_fogao", 1)
    c = checar_operacional(_arroz(modo_preparo=_OUTRA_PANELA), perfil)
    assert c.veredito is Veredito.APTO
    (aviso,) = c.avisos
    assert (aviso.tipo, str(aviso)) == (
        "bocas",
        "O passo 2 pede outra panela no fogo ao mesmo tempo. Com uma boca, a senhora faz uma "
        "parte depois da outra e leva mais tempo.",
    )


def test_outra_panela_sem_saber_as_bocas_pergunta(perfil_base: PerfilCozinha) -> None:
    perfil = perfil_base.com_restricao("bocas_fogao", None)
    c = checar_operacional(_arroz(modo_preparo=_OUTRA_PANELA), perfil)
    (pergunta,) = c.perguntas
    assert pergunta.campo == "bocas_fogao"
    assert pergunta.motivo == "Prato usa duas panelas no fogo ao mesmo tempo (passo 2)"


def test_o_fogao_nao_conta_como_panela(perfil_base: PerfilCozinha) -> None:
    """Refogar na panela e selar na frigideira, um depois do outro, não pede duas bocas."""
    r = _arroz(
        modo_preparo=[
            "Refogue a cebola na panela por 5 minutos.",
            "Sele o frango na frigideira por 10 minutos.",
        ]
    )
    for bocas in (None, 1):
        c = checar_operacional(r, perfil_base.com_restricao("bocas_fogao", bocas))
        assert c.veredito is Veredito.APTO
        assert not c.avisos


def test_aviso_chega_a_avaliacao_e_nao_muda_o_veredito(
    perfil_base: PerfilCozinha, despensa: Despensa
) -> None:
    perfil = (
        perfil_base.com_restricao("bocas_fogao", 1)
        .com_restricao("tem_gas_sobrando", True)
        .com_restricao("espaco_geladeira_litros", 20)
        .com_restricao("energia_aparelhos_simultaneos", 2)
    )
    r = receita(
        "Arroz e feijão", [ing("1 kg de arroz", "arroz", 1, "kg")], modo_preparo=_OUTRA_PANELA
    )
    a = avaliar(r, perfil, despensa, gosto=Gosto.GOSTA)
    assert a.veredito is Veredito.APTO
    assert [aviso.tipo for aviso in a.avisos] == ["bocas"]
    assert "dá pra fazer hoje" in a.resumo()


# --------------------------------------------------------------------------- #
# Geladeira pelos passos                                                       #
# --------------------------------------------------------------------------- #


def test_deixar_gelar_pede_espaco_na_geladeira(perfil_base: PerfilCozinha) -> None:
    """ "Deixe gelar" não dizia geladeira, e o portão não perguntava do espaço."""
    r = _arroz(modo_preparo=["Misture tudo.", "Cubra e deixe gelar por 2 horas."])
    c = checar_operacional(r, perfil_base)
    (pergunta,) = (p for p in c.perguntas if p.campo == "espaco_geladeira_litros")
    assert pergunta.motivo == "Prato precisa de espaço na geladeira (passo 2)"


def test_sem_espaco_bloqueia_citando_o_passo(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Misture tudo.", "Cubra e deixe gelar por 2 horas."])
    perfil = perfil_base.com_restricao("espaco_geladeira_litros", 0)
    c = checar_operacional(r, perfil)
    assert [i.descricao for i in c.impedimentos] == [
        "a receita precisa de espaço na geladeira (passo 2) e a senhora disse que não sobra"
    ]


def test_geladeira_pedida_sem_passo_que_diga_bloqueia_sem_citar_passo(
    perfil_base: PerfilCozinha,
) -> None:
    """A receita declara a geladeira, e nenhum passo leva a ela: bloqueia sem inventar passo."""
    r = _arroz(modo_preparo=["Misture tudo."], equipamentos=["geladeira"])
    perfil = perfil_base.com_restricao("espaco_geladeira_litros", 0)
    c = checar_operacional(r, perfil)
    assert [i.descricao for i in c.impedimentos] == [
        "a receita precisa de espaço na geladeira e a senhora disse que não sobra"
    ]


def test_retirar_da_geladeira_nao_ocupa_a_geladeira() -> None:
    from mise.passos import passos_com_frio

    r = _arroz(modo_preparo=["Retire da geladeira e sirva.", "Leve à geladeira por 1 hora."])
    assert passos_com_frio(r) == (2,)


# --------------------------------------------------------------------------- #
# Gás pelo tempo no fogão                                                      #
# --------------------------------------------------------------------------- #


def test_forno_longo_nao_pergunta_do_botijao_do_fogao(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Asse no forno por 90 minutos."])
    c = checar_operacional(r, perfil_base)
    assert not any(p.campo == "tem_gas_sobrando" for p in c.perguntas)


def test_fogo_longo_pelos_passos_pergunta_do_botijao(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Cozinhe em fogo baixo por 2 horas."])
    c = checar_operacional(r, perfil_base)
    (gas,) = (p for p in c.perguntas if p.campo == "tem_gas_sobrando")
    assert gas.motivo == "Prato fica 120 minutos no fogo, e ficar sem gás no meio estraga o pedido"


# --------------------------------------------------------------------------- #
# Passo que não diz o tempo, panelas juntas e o que não é frio                 #
# --------------------------------------------------------------------------- #


def test_passo_sem_tempo_nao_esconde_o_cozimento_declarado(perfil_base: PerfilCozinha) -> None:
    """Três minutos de alho não são o tempo da feijoada: o cozimento declarado cobre a receita."""
    r = _arroz(
        modo_preparo=[
            "Cozinhe o feijão com as carnes em fogo baixo até desmanchar.",
            "Refogue o alho por 3 minutos.",
        ],
        tempo_cozimento_min=180,
    )
    perfil = _com_limite(perfil_base, 60).com_restricao("tem_gas_sobrando", True)
    c = checar_operacional(r, perfil)
    assert [i.descricao for i in c.impedimentos] == [
        "a receita diz que o cozimento leva 180 minutos; a senhora tem 60 por cozinhada"
    ]


def test_passo_sem_tempo_e_sem_cozimento_pergunta(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Cozinhe o feijão até ficar macio.", "Refogue o alho por 3 minutos."])
    c = checar_operacional(r, _com_limite(perfil_base, 60))
    assert not c.perguntas
    assert [i.id for i in c.impedimentos] == ["tempo_max_por_fornada_min"]


def test_o_que_os_passos_dizem_ja_passa_do_limite_bloqueia(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Asse no forno por 50 minutos.", "Cozinhe o molho até engrossar."])
    c = checar_operacional(r, _com_limite(perfil_base, 30))
    assert [i.descricao for i in c.impedimentos] == [
        "pelos passos, só o que eles dizem já soma 50 minutos no forno e o passo 2 não diz o "
        "tempo; a senhora tem 30 por cozinhada"
    ]


def test_sem_passos_mas_com_o_forno_do_nome_pergunta_o_tempo(perfil_base: PerfilCozinha) -> None:
    """Sem passos e com o forno do nome, ninguém pergunta como ela faz: o tempo fica aberto."""
    r = receita("Frango assado", [ing("1 kg de frango", "frango", 1, "kg")])
    assert "forno" in r.equipamentos
    c = checar_operacional(r, _com_limite(perfil_base, 60))
    assert not c.perguntas
    assert [i.id for i in c.impedimentos] == ["tempo_max_por_fornada_min"]


def test_tempo_total_zero_nao_e_tempo(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Cozinhe o arroz."], tempo_total_min=0)
    c = checar_operacional(r, _com_limite(perfil_base, 60))
    assert not c.perguntas
    assert "a receita não diz quanto tempo" in c.impedimentos[0].descricao


_DUAS_PANELAS = [
    "Cozinhe o arroz na panela por 35 minutos.",
    "Em outra panela, cozinhe o feijão por 30 minutos.",
]


def test_com_duas_bocas_as_panelas_juntas_cabem(perfil_base: PerfilCozinha) -> None:
    """35 + 30 é o tempo de quem faz uma depois da outra; com duas bocas, são 35."""
    perfil = (
        _com_limite(perfil_base, 60)
        .com_restricao("bocas_fogao", 2)
        .com_restricao("tem_gas_sobrando", True)
    )
    c = checar_operacional(_arroz(modo_preparo=_DUAS_PANELAS), perfil)
    assert c.veredito is Veredito.APTO


def test_com_uma_boca_a_soma_vale(perfil_base: PerfilCozinha) -> None:
    perfil = _com_limite(perfil_base, 60).com_restricao("bocas_fogao", 1)
    c = checar_operacional(_arroz(modo_preparo=_DUAS_PANELAS), perfil)
    assert [i.descricao for i in c.impedimentos] == [
        "pelos passos, 35 + 30 = 65 minutos no fogo; a senhora tem 60 por cozinhada"
    ]
    assert [a.tipo for a in c.avisos] == ["bocas"]


def test_sem_saber_as_bocas_o_tempo_nao_bloqueia(perfil_base: PerfilCozinha) -> None:
    """Com duas bocas caberia: a pergunta das bocas decide, e o tempo não bloqueia antes dela."""
    perfil = (
        _com_limite(perfil_base, 60)
        .com_restricao("bocas_fogao", None)
        .com_restricao("tem_gas_sobrando", True)
    )
    c = checar_operacional(_arroz(modo_preparo=_DUAS_PANELAS), perfil)
    assert not c.impedimentos
    assert [p.campo for p in c.perguntas] == ["bocas_fogao"]


def test_nem_com_as_panelas_juntas_cabe(perfil_base: PerfilCozinha) -> None:
    perfil = _com_limite(perfil_base, 30).com_restricao("bocas_fogao", 2)
    c = checar_operacional(_arroz(modo_preparo=_DUAS_PANELAS), perfil)
    assert [i.descricao for i in c.impedimentos] == [
        "pelos passos, 35 + 30 = 65 minutos no fogo; mesmo com as duas panelas ao mesmo "
        "tempo, são 35 minutos; a senhora tem 30 por cozinhada"
    ]


def test_minimo_com_panelas_juntas_quando_um_passo_nao_diz_o_tempo(
    perfil_base: PerfilCozinha,
) -> None:
    passos = [*_DUAS_PANELAS, "Refogue o alho e junte tudo."]
    perfil = _com_limite(perfil_base, 30).com_restricao("bocas_fogao", 2)
    c = checar_operacional(_arroz(modo_preparo=passos), perfil)
    assert [i.descricao for i in c.impedimentos] == [
        "pelos passos, só o que eles dizem já soma 35 minutos no fogo, com as duas panelas ao "
        "mesmo tempo, e o passo 3 não diz o tempo; a senhora tem 30 por cozinhada"
    ]


def test_antecedencia_nao_e_tempo_de_forno(perfil_base: PerfilCozinha) -> None:
    """ "30 minutos antes de assar" é espera: não soma com os 40 de forno."""
    r = _arroz(
        modo_preparo=[
            "Retire a carne da geladeira 30 minutos antes de assar.",
            "Asse no forno por 40 minutos.",
        ]
    )
    c = checar_operacional(r, _com_limite(perfil_base, 60))
    assert c.veredito is Veredito.APTO, c.impedimentos


def test_dica_de_congelar_nao_pede_espaco_nem_freezer(
    perfil_base: PerfilCozinha, despensa: Despensa
) -> None:
    r = _arroz(modo_preparo=["Cozinhe o arroz por 20 minutos.", "Se sobrar, pode congelar."])
    perfil = perfil_base.com_restricao("espaco_geladeira_litros", 0).com_equipamento(
        "freezer", Posse.DESCONHECIDO
    )
    a = avaliar(r, perfil, despensa, gosto=Gosto.GOSTA)
    assert "freezer" not in r.equipamentos
    assert not any(i.id == "espaco_geladeira_litros" for i in a.impedimentos)


def test_tirar_da_geladeira_nao_ocupa_espaco(perfil_base: PerfilCozinha) -> None:
    r = _arroz(modo_preparo=["Retire o frango da geladeira.", "Asse no forno por 40 minutos."])
    perfil = perfil_base.com_restricao("espaco_geladeira_litros", 0)
    c = checar_operacional(r, perfil)
    assert not any(i.id == "espaco_geladeira_litros" for i in c.impedimentos)


def test_geladeira_do_nome_continua_valendo(perfil_base: PerfilCozinha) -> None:
    r = receita(
        "Torta de geladeira",
        [ing("1 kg de arroz", "arroz", 1, "kg")],
        modo_preparo=["Monte as camadas e sirva."],
    )
    c = checar_operacional(r, perfil_base.com_restricao("espaco_geladeira_litros", 0))
    assert [i.descricao for i in c.impedimentos] == [
        "a receita precisa de espaço na geladeira e a senhora disse que não sobra"
    ]
