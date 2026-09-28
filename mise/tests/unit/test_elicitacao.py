"""Ordenação de perguntas por ganho de informação."""

from __future__ import annotations

from dataclasses import replace

import pytest

from mise.despensa import Despensa
from mise.elicitacao import CAMPOS_DA_RECEITA, PESO_DESTRAVE, montar_plano, proxima_pergunta
from mise.perfil import Gosto, PerfilCozinha, Posse, contagem
from mise.receita import ingrediente as ing
from mise.receita import receita
from mise.viabilidade import TipoRestricao


def _cozinha() -> PerfilCozinha:
    """O perfil de partida, com o tempo por cozinhada já dito.

    Estes testes medem a ordem das perguntas de equipamento e técnica. Sem o
    tempo dela, "quanto tempo a senhora consegue cozinhar de uma vez?" entra em
    toda receita que vai ao fogo e passa na frente, com razão: decide todas.
    """
    return PerfilCozinha.inicial().com_restricao("tempo_max_por_fornada_min", 240)


def gosta_de(*receitas) -> dict[str, Gosto]:
    """Declara que ela gosta destes pratos.

    Quase todo teste deste arquivo é sobre a ordem das perguntas de equipamento
    e técnica. Sem isto a pergunta de gosto fica aberta em todos os pratos,
    domina o ranking com razão (é a que mais elimina) e esconde o que estes
    testes querem medir.
    """
    return {r.nome: Gosto.GOSTA for r in receitas}


@pytest.fixture
def candidatas():
    return [
        receita(
            "Frango à parmegiana",
            [ing("500 g de frango", "peito de frango", 500, "g")],
            modo_preparo=[
                "Empane e frite por 10 minutos.",
                "Leve ao forno e gratine por 15 minutos.",
            ],
        ),
        receita(
            "Escondidinho",
            [ing("500 g de carne", "carne moida", 500, "g")],
            modo_preparo=["Leve ao forno para gratinar por 20 minutos."],
        ),
        receita(
            "Bolo",
            [ing("2 xícaras de farinha", "farinha de trigo", 2, "xicara")],
            modo_preparo=["Bata na batedeira por 5 minutos.", "Asse no forno por 40 minutos."],
        ),
        receita(
            "Arroz simples",
            [ing("1 xícara de arroz", "arroz", 1, "xicara")],
            modo_preparo=["Refogue e cozinhe na panela por 20 minutos."],
        ),
    ]


def test_pergunta_mais_util_vem_primeiro(candidatas, despensa: Despensa) -> None:
    """O forno aparece em 3 de 4, e tem que vir antes da batedeira."""
    plano = montar_plano(candidatas, _cozinha(), despensa, gostos=gosta_de(*candidatas))
    assert plano.proxima is not None
    assert plano.proxima.campo == "forno"
    assert len(plano.proxima.receitas_afetadas) == 3


def test_sem_o_tempo_dela_a_pergunta_do_tempo_vem_primeiro(candidatas, despensa: Despensa) -> None:
    """O tempo por cozinhada decide as quatro receitas: vem antes do forno, que decide três."""
    plano = montar_plano(
        candidatas, PerfilCozinha.inicial(), despensa, gostos=gosta_de(*candidatas)
    )
    assert plano.proxima is not None
    assert plano.proxima.campo == "tempo_max_por_fornada_min"
    assert len(plano.proxima.receitas_afetadas) == 4


def test_pergunta_da_receita_e_uma_por_receita(despensa: Despensa) -> None:
    """Sem tempo nos passos, o tempo da receita nunca é pergunta, nem com o limite apertado.

    Com duas horas por cozinhada, a receita que não diz o tempo fica de fora, com
    o motivo; com quatro horas ou mais, passa com o aviso (`LIMITE_FOLGADO_MIN`).
    """
    sem_tempo = [
        receita(nome, [ing("a", "arroz", 1, "kg")], modo_preparo=["Cozinhe na panela."])
        for nome in ("Arroz", "Feijão")
    ]
    apertada = _cozinha().com_restricao("tempo_max_por_fornada_min", 120)
    plano = montar_plano(sem_tempo, apertada, despensa, gostos=gosta_de(*sem_tempo))
    do_tempo = [p for p in plano.perguntas if p.campo == "tempo_cozimento_min"]
    assert do_tempo == []
    assert [p.receitas_afetadas for p in do_tempo] not in (
        [("Arroz",), ("Feijão",)],
        [("Feijão",), ("Arroz",)],
    )


def test_destravar_vale_mais_que_aparecer(despensa: Despensa) -> None:
    """Uma pergunta que fecha um prato ganha de outra que só avança em vários."""
    fecha = receita(
        "Fecha", [ing("a", "arroz", 1, "kg")], modo_preparo=["Asse no forno por 30 minutos."]
    )
    avanca = [
        receita(
            f"Avança {i}",
            [ing("a", "arroz", 1, "kg")],
            modo_preparo=[
                "Bata na batedeira por 5 minutos.",
                "Faça o molho bechamel por 10 minutos.",
            ],
        )
        for i in range(3)
    ]
    plano = montar_plano([fecha, *avanca], _cozinha(), despensa, gostos=gosta_de(fecha, *avanca))
    assert plano.proxima is not None
    assert plano.proxima.campo == "forno", "fechar um prato vale mais que avançar em três"


def test_ganho_combina_as_duas_metricas() -> None:
    from mise.elicitacao import PerguntaPriorizada
    from mise.viabilidade import Pergunta

    p = PerguntaPriorizada(
        pergunta=Pergunta(TipoRestricao.EQUIPAMENTO, "forno", "tem forno?"),
        receitas_afetadas=("a", "b", "c"),
        receitas_destravadas=("a",),
    )
    assert p.ganho == PESO_DESTRAVE + 3


def test_responder_reduz_as_perguntas(candidatas, despensa: Despensa) -> None:
    perfil = _cozinha()
    gostos = gosta_de(*candidatas)
    antes = montar_plano(candidatas, perfil, despensa, gostos=gostos)

    depois = montar_plano(
        candidatas, perfil.com_equipamento("forno", Posse.TEM), despensa, gostos=gostos
    )
    assert len(depois) < len(antes)
    assert len(depois.aptas) > len(antes.aptas)


def test_prato_bloqueado_nao_gera_pergunta(despensa: Despensa) -> None:
    """Perguntar sobre prato impossível é gastar a paciência dela à toa."""
    r = receita(
        "Impossível",
        [ing("a", "arroz", 1, "kg")],
        modo_preparo=["Asse no forno.", "Faça o molho bechamel."],
    )
    perfil = (
        PerfilCozinha.inicial()
        .com_equipamento("forno", Posse.NAO_TEM)
        .com_equipamento("air_fryer", Posse.NAO_TEM)
        .com_equipamento("forno_eletrico", Posse.NAO_TEM)
    )
    plano = montar_plano([r], perfil, despensa)
    assert plano.bloqueadas == ("Impossível",)
    assert not plano.perguntas, "prato bloqueado não deve gerar pergunta"


def test_prato_apto_nao_gera_pergunta(despensa: Despensa) -> None:
    r = receita(
        "Arroz",
        [ing("1 xícara de arroz", "arroz", 1, "xicara")],
        modo_preparo=["Cozinhe na panela por 20 minutos."],
    )
    perfil = _cozinha()
    plano = montar_plano([r], perfil, despensa, gostos=gosta_de(r))
    assert plano.aptas == ("Arroz",)
    assert not plano.perguntas


def test_desempate_prefere_equipamento_a_tecnica(despensa: Despensa) -> None:
    """Equipamento é binário e rápido; técnica exige ela julgar a si mesma."""
    r = receita(
        "Mista",
        [ing("a", "arroz", 1, "kg")],
        modo_preparo=["Bata na batedeira.", "Faça o molho bechamel."],
    )
    plano = montar_plano([r], PerfilCozinha.inicial(), despensa, gostos=gosta_de(r))
    tipos = [p.pergunta.tipo for p in plano.perguntas]
    assert tipos.index(TipoRestricao.EQUIPAMENTO) < tipos.index(TipoRestricao.TECNICA)


def test_mesma_pergunta_agrupa_entre_receitas(candidatas, despensa: Despensa) -> None:
    """O forno é uma pergunta só, não três."""
    plano = montar_plano(
        candidatas, PerfilCozinha.inicial(), despensa, gostos=gosta_de(*candidatas)
    )
    campos = [p.campo for p in plano.perguntas]
    assert campos.count("forno") == 1


def test_justificativa_explica_a_ordem(candidatas, despensa: Despensa) -> None:
    plano = montar_plano(
        candidatas, PerfilCozinha.inicial(), despensa, gostos=gosta_de(*candidatas)
    )
    assert plano.proxima is not None
    assert "decide" in plano.proxima.justificativa()


def test_justificativa_quando_nao_destrava(despensa: Despensa) -> None:
    r = receita(
        "Duas pendências",
        [ing("a", "arroz", 1, "kg")],
        modo_preparo=["Bata na batedeira.", "Faça o molho bechamel."],
    )
    plano = montar_plano([r], PerfilCozinha.inicial(), despensa)
    assert "aparece em" in plano.perguntas[0].justificativa()


def test_proximas_n(candidatas, despensa: Despensa) -> None:
    plano = montar_plano(candidatas, PerfilCozinha.inicial(), despensa)
    assert len(plano.proximas(2)) == 2
    assert plano.proximas(2)[0].ganho >= plano.proximas(2)[1].ganho


def test_plano_vazio_sem_receitas(despensa: Despensa) -> None:
    plano = montar_plano([], PerfilCozinha.inicial(), despensa)
    assert not plano
    assert plano.proxima is None
    assert len(plano) == 0


def test_atalho_proxima_pergunta(candidatas, despensa: Despensa) -> None:
    p = proxima_pergunta(candidatas, _cozinha(), despensa, gostos=gosta_de(*candidatas))
    assert p is not None
    assert p.campo == "forno"
    assert str(p) == p.texto


def test_atalho_pergunta_do_gosto_quando_nada_foi_dito(candidatas, despensa: Despensa) -> None:
    p = proxima_pergunta(candidatas, PerfilCozinha.inicial(), despensa)
    assert p is not None
    assert p.pergunta.tipo is TipoRestricao.GOSTO


def test_resumo_conta_tudo(candidatas, despensa: Despensa) -> None:
    plano = montar_plano(candidatas, PerfilCozinha.inicial(), despensa)
    resumo = plano.resumo()
    assert " aguardando resposta · " in resumo
    assert resumo.endswith("em aberto")
    assert contagem(len(plano.perguntas), "pergunta em aberto", "perguntas em aberto") in resumo


@pytest.mark.parametrize(
    ("n", "trechos"),
    [
        (0, ("0 pratos que dão", "0 que não dão", "0 perguntas em aberto")),
        (1, ("1 prato que dá", "1 que não dá", "1 pergunta em aberto")),
        (2, ("2 pratos que dão", "2 que não dão", "2 perguntas em aberto")),
    ],
)
def test_resumo_no_singular_e_no_plural_sem_palavra_do_sistema(
    n: int, trechos: tuple[str, ...]
) -> None:
    from mise.elicitacao import PerguntaPriorizada, PlanoDeElicitacao
    from mise.viabilidade import Pergunta

    pergunta = PerguntaPriorizada(Pergunta(TipoRestricao.GOSTO, "gosto", "?"), (), ())
    plano = PlanoDeElicitacao(
        perguntas=(pergunta,) * n, aptas=("A",) * n, bloqueadas=("B",) * n, pendentes=("C",) * n
    )
    resumo = plano.resumo()
    for trecho in trechos:
        assert trecho in resumo
    assert "apto" not in resumo.lower()
    assert "bloqueado" not in resumo.lower()


@pytest.mark.parametrize(
    ("destravadas", "afetadas", "texto"),
    [
        (("A",), ("A",), "responder isso decide 1 prato na hora (A)"),
        (("A", "B"), ("A", "B"), "responder isso decide 2 pratos na hora (A, B)"),
        ((), ("A",), "aparece em 1 prato candidato"),
        ((), ("A", "B"), "aparece em 2 pratos candidatos"),
    ],
)
def test_justificativa_no_singular_e_no_plural(
    destravadas: tuple[str, ...], afetadas: tuple[str, ...], texto: str
) -> None:
    from mise.elicitacao import PerguntaPriorizada
    from mise.viabilidade import Pergunta

    pergunta = PerguntaPriorizada(
        Pergunta(TipoRestricao.GOSTO, "gosto", "?"), afetadas, destravadas
    )
    assert pergunta.justificativa() == texto


def test_entrevista_converge(candidatas, despensa: Despensa) -> None:
    """Respondendo sempre 'sim', a entrevista termina: não entra em laço.

    Cobre as cinco checagens. O risco que este teste existe para pegar é uma
    pergunta que se repete porque a resposta não tem onde ser guardada: foi
    exatamente o que acontecia com preço antes de haver onde registrá-lo, e o
    sintoma seria a entrevista nunca convergir.
    """
    perfil = PerfilCozinha.inicial()
    gostos: dict[str, Gosto] = {}
    receitas = {r.nome: r for r in candidatas}
    # Sem o tempo nos passos, a receita pergunta quanto tempo fica no fogo, e a
    # resposta volta nela, como na conversa real.
    receitas["Arroz simples"] = receita(
        "Arroz simples",
        [ing("1 xícara de arroz", "arroz", 1, "xicara")],
        modo_preparo=["Refogue e cozinhe na panela."],
    )

    for _ in range(30):
        plano = montar_plano(list(receitas.values()), perfil, despensa, gostos=gostos)
        if not plano:
            break
        p = plano.proxima
        assert p is not None
        if p.campo == "tempo_cozimento_min":
            assert p.campo in CAMPOS_DA_RECEITA
            for nome in p.receitas_afetadas:
                receitas[nome] = replace(receitas[nome], tempo_cozimento_min=25)
        elif p.pergunta.tipo is TipoRestricao.EQUIPAMENTO:
            perfil = perfil.com_equipamento(p.campo, Posse.TEM)
        elif p.pergunta.tipo is TipoRestricao.TECNICA:
            perfil = perfil.com_tecnica(p.campo, Posse.TEM)
        elif p.pergunta.tipo is TipoRestricao.OPERACIONAL:
            perfil = perfil.com_restricao(p.campo, 240)
        elif p.pergunta.tipo is TipoRestricao.GOSTO:
            # A pergunta de gosto é por prato, e vale para todos os que ela
            # afeta: é assim que a conversa real acontece.
            gostos.update(dict.fromkeys(p.receitas_afetadas, Gosto.GOSTA))
        else:
            break
    else:
        pytest.fail("a entrevista não convergiu em 30 perguntas")

    plano = montar_plano(list(receitas.values()), perfil, despensa, gostos=gostos)
    assert len(plano.aptas) == len(candidatas)


def test_gosto_vem_antes_de_equipamento(candidatas, despensa: Despensa) -> None:
    """A pergunta mais barata e que mais elimina vem primeiro.

    Perguntar sobre bocas de fogão e depois descobrir que ela não gosta de fazer
    o prato gastou o tempo dela à toa.
    """
    plano = montar_plano(candidatas, PerfilCozinha.inicial(), despensa)
    assert plano.proxima is not None
    assert plano.proxima.pergunta.tipo is TipoRestricao.GOSTO


def test_nao_gostar_bloqueia_sem_gerar_pergunta(despensa: Despensa) -> None:
    """Prato que ela não quer fazer sai da conversa, não vira entrevista."""
    r = receita("Arroz", [ing("1 xícara de arroz", "arroz", 1, "xicara")])
    plano = montar_plano([r], PerfilCozinha.inicial(), despensa, gostos={"Arroz": Gosto.NAO_GOSTA})
    assert plano.bloqueadas == ("Arroz",)
    assert not plano.perguntas
