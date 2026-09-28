"""A receita passo a passo: requisitos com a evidência, limites e perguntas com opções."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mise.passos import (
    Limite,
    OrigemDoRequisito,
    PassosDaReceita,
    Requisito,
    TipoDeLimite,
    TipoDeRequisito,
    _Texto,
    avaliar_passos,
    como_responder,
    detalhar,
    exigencias,
    extrair_limites,
    perguntas_com_opcoes,
)
from mise.perfil import PerfilCozinha, Posse
from mise.receita import IngredienteReceita, Receita, ingrediente, receita
from mise.taxonomia import EQUIPAMENTOS, TECNICAS, _normalizar
from mise.viabilidade import Pergunta, TipoRestricao, avaliar

CONTRATO = Path(__file__).resolve().parents[3] / "contratos" / "web" / "receita.json"

FRANGO = ingrediente("500 g de peito de frango", "peito de frango", 500, "g")


def _limites(texto: str) -> list[tuple[str, int | None, int | None, str, str, str | None]]:
    return [
        (lim.tipo.value, lim.minutos, lim.graus, lim.texto, lim.trecho, lim.equipamento)
        for lim in extrair_limites(texto)
    ]


# --------------------------------------------------------------------------- #
# Limites de cada passo
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        (
            "Acrescente o arroz e a água e cozinhe por 20 minutos.",
            [("tempo", 20, None, "20 min no fogo", "20 minutos", "fogao")],
        ),
        (
            "Leve ao forno a 180 C por 40 minutos.",
            [
                ("temperatura", None, 180, "forno a 180 °C", "180 C", "forno"),
                ("tempo", 40, None, "40 min no forno", "40 minutos", "forno"),
            ],
        ),
        (
            "Pré-aqueça o forno a 200 °C e asse por 1 hora e meia.",
            [
                ("temperatura", None, 200, "forno a 200 °C", "200 °C", "forno"),
                ("tempo", 90, None, "1 h 30 min no forno", "1 hora e meia", "forno"),
            ],
        ),
        (
            "Leve à geladeira por 4 horas.",
            [("geladeira", 240, None, "4 h na geladeira", "4 horas", "geladeira")],
        ),
        (
            "Cozinhe por 10 minutos, deixe esfriar e leve à geladeira por 4 horas.",
            [
                ("tempo", 10, None, "10 min no fogo", "10 minutos", "fogao"),
                ("geladeira", 240, None, "4 h na geladeira", "4 horas", "geladeira"),
            ],
        ),
        (
            "Deixe gelar por no mínimo 6 horas.",
            [("geladeira", 360, None, "6 h na geladeira", "6 horas", "geladeira")],
        ),
        (
            "Bata na batedeira por 5 minutos e leve ao freezer por 1h30.",
            [
                ("tempo", 5, None, "5 min na batedeira", "5 minutos", "batedeira"),
                ("congelador", 90, None, "1 h 30 min no congelador", "1h30", "freezer"),
            ],
        ),
        (
            "Deixe crescer por uma hora ou até dobrar de volume.",
            [("descanso", 60, None, "1 h crescendo", "uma hora", None)],
        ),
        (
            "Deixe a massa descansar por meia hora.",
            [("descanso", 30, None, "30 min de descanso", "meia hora", None)],
        ),
        (
            "Deixe o frango marinar por 2 horas.",
            [("descanso", 120, None, "2 h marinando", "2 horas", None)],
        ),
        (
            "Leve ao forno médio (180ºC) por cerca de 40-45 minutos.",
            [
                ("temperatura", None, 180, "forno a 180 °C", "180ºC", "forno"),
                ("tempo", 45, None, "40 a 45 min no forno", "40-45 minutos", "forno"),
            ],
        ),
        (
            "Cozinhe na pressão por 1 hora e 15 minutos.",
            [("tempo", 75, None, "1 h 15 min na pressão", "1 hora e 15 minutos", "fogao")],
        ),
        (
            "Cozinhe em fogo baixo entre 2 e 3 horas.",
            [("tempo", 180, None, "2 a 3 h no fogo", "entre 2 e 3 horas", "fogao")],
        ),
        (
            "Frite de 3 a 4 minutos de cada lado na frigideira.",
            # "Frite", antes da duração, está mais perto que "frigideira", depois.
            [("tempo", 4, None, "3 a 4 min no fogo", "3 a 4 minutos", "fogao")],
        ),
        (
            "Asse por 45 minutos a 1 hora e 15 minutos.",
            [
                (
                    "tempo",
                    75,
                    None,
                    "45 min a 1 h 15 min no forno",
                    "45 minutos a 1 hora e 15 minutos",
                    "forno",
                )
            ],
        ),
        (
            "Aqueça no micro-ondas por 2 minutos.",
            [("tempo", 2, None, "2 min no micro-ondas", "2 minutos", "microondas")],
        ),
        (
            "Coloque na air fryer a 200 graus por 15 minutos.",
            [
                ("temperatura", None, 200, "air fryer a 200 °C", "200 graus", "air_fryer"),
                ("tempo", 15, None, "15 min na air fryer", "15 minutos", "air_fryer"),
            ],
        ),
        (
            "Em outra panela, faça o molho e deixe apurar por 15 minutos.",
            [
                (
                    "outra_panela",
                    None,
                    None,
                    "mais uma boca do fogão ao mesmo tempo",
                    "Em outra panela",
                    "fogao",
                ),
                ("tempo", 15, None, "15 min no fogo", "15 minutos", "fogao"),
            ],
        ),
        (
            "Aqueça no micro-ondas por 30 segundos e depois por mais 1 minuto.",
            [("tempo", 1, None, "1 min no micro-ondas", "1 minuto", "microondas")],
        ),
        (
            "Misture e reserve por 10 minutos.",
            [("tempo", 10, None, "10 min", "10 minutos", None)],
        ),
        (
            "Deixe o feijão de molho de um dia para o outro.",
            [
                (
                    "de_um_dia_para_o_outro",
                    None,
                    None,
                    "de um dia para o outro",
                    "de um dia para o outro",
                    None,
                )
            ],
        ),
        (
            "Cubra e leve à geladeira de um dia para o outro.",
            [
                (
                    "de_um_dia_para_o_outro",
                    None,
                    None,
                    "de um dia para o outro, na geladeira",
                    "de um dia para o outro",
                    "geladeira",
                )
            ],
        ),
        (
            "Em outra panela, refogue o alho.",
            [
                (
                    "outra_panela",
                    None,
                    None,
                    "mais uma boca do fogão ao mesmo tempo",
                    "Em outra panela",
                    "fogao",
                )
            ],
        ),
        (
            "Enquanto isso, numa frigideira separada, doure o bacon.",
            [
                (
                    "outra_panela",
                    None,
                    None,
                    "mais uma boca do fogão ao mesmo tempo",
                    "numa frigideira separada",
                    "fogao",
                )
            ],
        ),
        (
            "Leve à geladeira a 4 °C.",
            [("temperatura", None, 4, "4 °C", "4 °C", None)],
        ),
    ],
)
def test_limites_do_passo(texto: str, esperado: list[tuple[Any, ...]]) -> None:
    assert _limites(texto) == esperado


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        # Aparelho antes da duração vale mais que verbo de calor.
        ("Ligue o forno e deixe aquecer por 15 minutos.", [(15, "15 min no forno", "forno")]),
        ("Deixe o forno pré-aquecer por 10 minutos.", [(10, "10 min no forno", "forno")]),
        ("Leve ao forno e cozinhe por 30 minutos.", [(30, "30 min no forno", "forno")]),
        # Aparelho em outra oração, antes, vale mais que verbo de calor de vários aparelhos.
        (
            "No micro-ondas, derreta o chocolate por 1 minuto.",
            [(1, "1 min no micro-ondas", "microondas")],
        ),
        # Mas verbo que só se faz no fogão ganha do forno da outra oração.
        ("Preaqueça o forno, refogue a cebola por 3 minutos.", [(3, "3 min no fogo", "fogao")]),
        # O que vem depois é outra ação: "e depois asse" não é o tempo do cozimento.
        (
            "Cozinhe por 10 minutos e depois asse por 30 minutos.",
            [(10, "10 min no fogo", "fogao"), (30, "30 min no forno", "forno")],
        ),
        # Liquidificador não cozinha.
        ("Bata no liquidificador e cozinhe por 10 minutos.", [(10, "10 min no fogo", "fogao")]),
        (
            "Bata no liquidificador por 3 minutos.",
            [(3, "3 min no liquidificador", "liquidificador")],
        ),
        # Frio e espera.
        (
            "Leve à geladeira para gelar e engrossar por 2 horas.",
            [(120, "2 h na geladeira", "geladeira")],
        ),
        (
            "Cubra e leve à geladeira para descansar por 1 hora.",
            [(60, "1 h na geladeira", "geladeira")],
        ),
        ("Deixe descansar 30 min na geladeira.", [(30, "30 min na geladeira", "geladeira")]),
        (
            "Deixe esfriar por 30 minutos e leve à geladeira por 4 horas.",
            [(30, "30 min esfriando", None), (240, "4 h na geladeira", "geladeira")],
        ),
        ("Deixe esfriar fora da geladeira por 20 minutos.", [(20, "20 min esfriando", None)]),
        # Fogo apagado e aparelho retirado não contam.
        ("Desligue o fogo e deixe abafado por 10 minutos.", [(10, "10 min", None)]),
        (
            "Retire do forno e espere 10 minutos antes de desenformar.",
            [(10, "10 min de espera", None)],
        ),
        # Empate: o nome mais longo é o mais preciso.
        (
            "Asse por 20 minutos no forno elétrico.",
            [(20, "20 min no forno elétrico", "forno_eletrico")],
        ),
        # Faixas, abreviação e unidades.
        ("Asse entre 40 minutos e 1 hora.", [(60, "40 min a 1 h no forno", "forno")]),
        ("Asse de 1 a 1 hora e meia.", [(90, "1 h a 1 h 30 min no forno", "forno")]),
        ("Asse por aprox. 40 minutos.", [(40, "40 min no forno", "forno")]),
        ("Asse por 1h30m.", [(90, "1 h 30 min no forno", "forno")]),
        ("Deixe curar por 2 dias.", [(2880, "2 dias", None)]),
        ("Deixe curar por 1 dia.", [(1440, "1 dia", None)]),
        ("Deixe curar de 2 a 3 dias.", [(4320, "2 a 3 dias", None)]),
    ],
)
def test_limites_de_frases_comuns(texto: str, esperado: list[tuple[int, str, str | None]]) -> None:
    assert [(lim.minutos, lim.texto, lim.equipamento) for lim in extrair_limites(texto)] == esperado


@pytest.mark.parametrize(
    ("texto", "tipo", "texto_do_limite"),
    [
        ("Prepare o creme na véspera.", "de_um_dia_para_o_outro", "de um dia para o outro"),
        (
            "Deixe a massa pronta no dia anterior.",
            "de_um_dia_para_o_outro",
            "de um dia para o outro",
        ),
        ("Congele a -18 °C.", "temperatura", "-18 °C"),
    ],
)
def test_vespera_e_temperatura_abaixo_de_zero(texto: str, tipo: str, texto_do_limite: str) -> None:
    (limite,) = extrair_limites(texto)
    assert (limite.tipo.value, limite.texto) == (tipo, texto_do_limite)


def test_o_um_dia_do_dia_para_o_outro_nao_e_duracao() -> None:
    assert [lim.tipo for lim in extrair_limites("Deixe de molho de um dia para o outro.")] == [
        TipoDeLimite.DE_UM_DIA_PARA_O_OUTRO
    ]


@pytest.mark.parametrize(
    "texto",
    [
        "No 1º passo, misture tudo.",  # ordinal, não temperatura
        "Misture 2 c. de sopa de açúcar.",  # colher, não grau
        "Junte 30 g de manteiga.",
        "Bata por 30 segundos.",  # segundos não pesam na rotina
        "Tempere a gosto e sirva.",
        "Cozinhe por 0 minutos.",  # duração nula não é limite
        "Aqueça a 500 graus.",  # fora de qualquer cozinha
        "Leve ao forno a 30 C.",  # "c" sem o grau só a partir do forno
        "Aqueça a -200 C.",  # abaixo de zero, só com o grau escrito
        "Congele a -50 °C.",  # fora de qualquer congelador
        "",
    ],
)
def test_texto_sem_limite(texto: str) -> None:
    assert extrair_limites(texto) == ()


def test_faixa_ao_contrario_fica_em_ordem() -> None:
    assert _limites("Asse por 1 hora ou 45 minutos.") == [
        ("tempo", 60, None, "45 min a 1 h no forno", "1 hora ou 45 minutos", "forno")
    ]


def test_duas_duracoes_soltas_nao_viram_faixa() -> None:
    assert _limites("Cozinhe por 10 minutos e depois asse por 30 minutos.") == [
        ("tempo", 10, None, "10 min no fogo", "10 minutos", "fogao"),
        ("tempo", 30, None, "30 min no forno", "30 minutos", "forno"),
    ]


def test_limite_depois_do_ponto_nao_herda_o_equipamento_da_frase_anterior() -> None:
    assert _limites("Retire do forno. Deixe por 10 minutos.") == [
        ("tempo", 10, None, "10 min", "10 minutos", None)
    ]


def test_ponto_e_virgula_fecha_a_frase() -> None:
    assert _limites("Leve ao forno; depois deixe por 10 minutos.") == [
        ("tempo", 10, None, "10 min", "10 minutos", None)
    ]


def test_o_ponto_de_um_decimal_nao_quebra_a_frase() -> None:
    assert _limites("Leve ao forno por 1.5 hora.") == [
        ("tempo", 90, None, "1 h 30 min no forno", "1.5 hora", "forno")
    ]


def test_limite_em_json() -> None:
    limite = Limite(
        TipoDeLimite.TEMPO, "20 min no fogo", "20 minutos", minutos=20, equipamento="fogao"
    )
    assert limite.para_json() == {
        "tipo": "tempo",
        "minutos": 20,
        "graus": None,
        "texto": "20 min no fogo",
        "trecho": "20 minutos",
        "equipamento": "fogao",
    }


# --------------------------------------------------------------------------- #
# O caminho de volta ao texto original
# --------------------------------------------------------------------------- #


def test_trecho_guarda_acento_e_caixa_do_original() -> None:
    t = _Texto("Pré-Aqueça o FÔRNO")
    assert t.normalizado == "pre-aqueca o forno"
    assert t.primeiro(("pre-aqueca",)) == "Pré-Aqueça"
    assert t.primeiro(("forno",)) == "FÔRNO"
    assert t.primeiro(("batedeira",)) == ""


def test_espacos_colapsam_como_na_taxonomia() -> None:
    t = _Texto("leve   ao\n\tforno")
    assert t.normalizado == "leve ao forno"
    assert t.primeiro(("leve ao forno",)) == "leve   ao\n\tforno"


@settings(max_examples=300, deadline=None)
@given(st.text())
def test_normalizado_e_o_mesmo_da_taxonomia(texto: str) -> None:
    """Se as duas normalizações divergirem, o trecho aponta para as palavras erradas."""
    t = _Texto(texto)
    assert t.normalizado == _normalizar(texto)
    assert len(t.origem) == len(t.normalizado)
    assert all(0 <= i < len(texto) for i in t.origem)


@settings(max_examples=200, deadline=None)
@given(
    st.text(alphabet=st.sampled_from("abcdeéãçõ 0123456789,.-°ºChmiutosrgalenzf\n"), max_size=80)
)
def test_extrair_limites_nunca_quebra(texto: str) -> None:
    for limite in extrair_limites(texto):
        assert limite.trecho
        assert limite.trecho in texto
        assert limite.minutos is None or limite.minutos > 0


# --------------------------------------------------------------------------- #
# Requisitos de cada passo
# --------------------------------------------------------------------------- #


def test_requisito_vem_com_a_evidencia_e_o_estado_do_perfil() -> None:
    r = receita(
        "Frango assado",
        [FRANGO],
        modo_preparo=["Tempere o frango.", "Pré-aqueça o forno e asse por 40 minutos."],
    )
    passos = avaliar_passos(r, PerfilCozinha.inicial())
    primeiro, segundo = passos.passos
    assert primeiro.requisitos == ()
    forno, assar = segundo.requisitos
    assert (forno.tipo, forno.id, forno.estado, forno.suposto) == (
        TipoDeRequisito.EQUIPAMENTO,
        "forno",
        Posse.DESCONHECIDO,
        False,
    )
    # O primeiro padrão do forno que casa, na ordem da taxonomia: "forno" vem antes de "pre-aqueca".
    assert forno.trecho == "forno"
    assert "pre-aqueca o forno" in forno.evidencia
    assert forno.rotulo_estado == "ainda não perguntei"
    assert (assar.id, assar.estado, assar.suposto, assar.rotulo_estado) == (
        "assar",
        Posse.TEM,
        True,
        "suposto",
    )
    assert passos.requisitos_da_receita == (), "o forno do nome já está no passo 2"


@pytest.mark.parametrize(
    ("tipo", "estado", "confirmado", "rotulo"),
    [
        (TipoDeRequisito.EQUIPAMENTO, Posse.TEM, True, "a senhora tem"),
        (TipoDeRequisito.EQUIPAMENTO, Posse.NAO_TEM, True, "a senhora não tem"),
        (TipoDeRequisito.TECNICA, Posse.TEM, True, "a senhora faz"),
        (TipoDeRequisito.TECNICA, Posse.NAO_TEM, True, "a senhora não faz"),
        (TipoDeRequisito.TECNICA, Posse.TEM, False, "suposto"),
        (TipoDeRequisito.EQUIPAMENTO, Posse.DESCONHECIDO, False, "ainda não perguntei"),
    ],
)
def test_rotulo_do_estado(
    tipo: TipoDeRequisito, estado: Posse, confirmado: bool, rotulo: str
) -> None:
    r = Requisito(
        tipo, "x", "X", estado, suposto=estado is Posse.TEM and not confirmado, evidencia=""
    )
    assert r.rotulo_estado == rotulo


def test_o_que_toda_cozinha_tem_tambem_e_conferido_pelo_portao(despensa) -> None:  # type: ignore[no-untyped-def]
    """Ela diz que não tem fogão: o passo mostra, e o portão bloqueia pelo mesmo motivo."""
    perfil = PerfilCozinha.inicial().com_equipamento("fogao", Posse.NAO_TEM)
    r = receita(
        "Arroz",
        [ingrediente("1 xícara de arroz", "arroz", 1, "xicara")],
        modo_preparo=["Cozinhe em fogo baixo e leve ao forno."],
    )
    fogao, forno = avaliar_passos(r, perfil).passos[0].requisitos
    assert (fogao.id, fogao.rotulo_estado, fogao.conferido) == ("fogao", "a senhora não tem", True)
    assert (forno.id, forno.conferido) == ("forno", True)
    assert fogao.para_json()["conferido"] is True
    impedimentos = avaliar(r, perfil, despensa).impedimentos
    assert "fogao" in {i.id for i in impedimentos}, "o não tenho dela vale até para o fogão"


def test_tecnica_pressuposta_tambem_e_conferida() -> None:
    r = receita(
        "Arroz",
        [ingrediente("1 xícara de arroz", "arroz", 1, "xicara")],
        modo_preparo=["Refogue e empane."],
    )
    fogao, refogar, empanar = avaliar_passos(r, PerfilCozinha.inicial()).passos[0].requisitos
    assert (fogao.id, fogao.trecho, fogao.conferido) == ("fogao", "Refogue", True)
    assert (refogar.id, refogar.conferido, empanar.id, empanar.conferido) == (
        "refogar",
        True,
        "empanar",
        True,
    )


def test_sem_forno_com_air_fryer_o_passo_diz_que_ela_resolve() -> None:
    perfil = (
        PerfilCozinha.inicial()
        .com_equipamento("forno", Posse.NAO_TEM)
        .com_equipamento("air_fryer", Posse.TEM)
    )
    r = receita("Frango assado", [FRANGO], modo_preparo=["Leve ao forno por 40 minutos."])
    (forno,) = avaliar_passos(r, perfil).passos[0].requisitos
    assert forno.estado is Posse.NAO_TEM
    assert forno.substituto == "air_fryer"
    assert forno.rotulo_estado == "a senhora resolve com air fryer"
    assert forno.para_json()["substituto"] == {"id": "air_fryer", "nome": "Air fryer"}


def test_sem_forno_e_sem_substituto_nao_ha_substituto() -> None:
    perfil = PerfilCozinha.inicial().com_equipamento("forno", Posse.NAO_TEM)
    r = receita("Frango assado", [FRANGO], modo_preparo=["Leve ao forno por 40 minutos."])
    (forno,) = avaliar_passos(r, perfil).passos[0].requisitos
    assert forno.substituto is None
    assert forno.para_json()["substituto"] is None
    assert forno.rotulo_estado == "a senhora não tem"


def test_contexto_da_tecnica_vale_para_a_receita_inteira() -> None:
    """ "Ao ponto" no passo e "bife" no nome: é ponto de carne, como o portão já acusa."""
    r = receita(
        "Bife acebolado",
        [ingrediente("2 bifes", "bife", 2, "unidade")],
        modo_preparo=["Tempere com sal.", "Grelhe até ficar ao ponto."],
    )
    assert "ponto_carne" in r.tecnicas
    segundo = avaliar_passos(r, PerfilCozinha.inicial()).passos[1]
    assert "ponto_carne" in {req.id for req in segundo.requisitos}


def test_ao_ponto_sem_carne_nenhuma_nao_e_ponto_de_carne() -> None:
    r = receita(
        "Arroz",
        [ingrediente("1 xícara de arroz", "arroz", 1, "xicara")],
        modo_preparo=["Cozinhe até ficar ao ponto."],
    )
    assert "ponto_carne" not in r.tecnicas
    # Só o fogão, que o "cozinhe" pede: nenhuma técnica de ponto.
    (fogao,) = avaliar_passos(r, PerfilCozinha.inicial()).passos[0].requisitos
    assert (fogao.id, fogao.trecho) == ("fogao", "Cozinhe")


def test_o_passo_so_mostra_o_que_a_receita_carrega() -> None:
    """Receita guardada antes de um padrão novo: o passo não mostra o que o portão não confere."""
    r = Receita(
        nome="Bolo",
        ingredientes=(IngredienteReceita("3 ovos", "ovos", Decimal(3), "ovo"),),
        modo_preparo=("Bata na batedeira e leve ao forno.",),
        equipamentos=frozenset({"forno"}),
    )
    (passo,) = avaliar_passos(r, PerfilCozinha.inicial()).passos
    assert [req.id for req in passo.requisitos] == ["forno"]


def test_o_que_vem_do_nome_fica_num_balde_a_parte() -> None:
    r = receita("Frango assado", [FRANGO])
    passos = avaliar_passos(r, PerfilCozinha.inicial())
    assert passos.passos == ()
    (do_nome,) = passos.requisitos_da_receita
    assert do_nome.origem is OrigemDoRequisito.NOME
    assert (do_nome.requisito.id, do_nome.requisito.trecho) == ("forno", "assado")
    assert do_nome.para_json()["origem"] == "nome"


def test_o_que_vem_dos_ingredientes_fica_num_balde_a_parte() -> None:
    r = receita(
        "Torta de frango",
        [FRANGO, ingrediente("1 pacote de massa folhada", "massa folhada", 1, "pacote")],
        modo_preparo=["Recheie e feche."],
    )
    passos = avaliar_passos(r, PerfilCozinha.inicial())
    (dos_ingredientes,) = passos.requisitos_da_receita
    assert dos_ingredientes.origem is OrigemDoRequisito.INGREDIENTES
    assert dos_ingredientes.requisito.id == "massa_folhada"
    assert dos_ingredientes.requisito.trecho == "massa folhada"
    assert dos_ingredientes.requisito.tipo is TipoDeRequisito.TECNICA


def test_o_que_foi_declarado_sem_trecho_tem_origem_na_receita() -> None:
    r = Receita(
        nome="Pão",
        ingredientes=(IngredienteReceita("500 g de farinha", "farinha", Decimal(500), "g"),),
        modo_preparo=("Misture tudo.",),
        equipamentos=frozenset({"batedeira"}),
        tecnicas=frozenset({"sovar_pao"}),
    )
    passos = avaliar_passos(r, PerfilCozinha.inicial())
    assert [
        (x.requisito.id, x.origem, x.requisito.evidencia) for x in passos.requisitos_da_receita
    ] == [
        ("batedeira", OrigemDoRequisito.RECEITA, ""),
        ("sovar_pao", OrigemDoRequisito.RECEITA, ""),
    ]


def test_passo_em_branco_fica_na_ordem_sem_nada() -> None:
    r = receita(
        "Arroz",
        [ingrediente("1 xícara de arroz", "arroz", 1, "xicara")],
        modo_preparo=["Lave o arroz.", "  ", "Cozinhe por 20 minutos."],
    )
    passos = avaliar_passos(r, PerfilCozinha.inicial()).passos
    assert [p.ordem for p in passos] == [1, 2, 3]
    assert passos[1].requisitos == passos[1].limites == ()


def _todas_as_receitas() -> st.SearchStrategy[Receita]:
    """Receitas montadas com os padrões da taxonomia, espalhados por passos, nome e ingredientes."""
    padroes = [p for e in EQUIPAMENTOS for p in e.padroes] + [
        p for t in TECNICAS for p in t.padroes
    ]
    frase = st.lists(
        st.sampled_from([*padroes, "misture", "sirva", "o frango", "a carne"]), max_size=4
    )
    return st.builds(
        lambda nome, passos, ingr: receita(
            " ".join(nome) or "Prato",
            [ingrediente(" ".join(ingr) or "sal", "sal")],
            modo_preparo=[" ".join(p) for p in passos],
        ),
        frase,
        st.lists(frase, max_size=4),
        frase,
    )


@settings(max_examples=150, deadline=None)
@given(_todas_as_receitas())
def test_todo_requisito_da_receita_aparece_num_passo_ou_no_balde(r: Receita) -> None:
    """O que o passo a passo mostra é exatamente o que o portão confere: nem mais, nem menos."""
    passos = avaliar_passos(r, PerfilCozinha.inicial())
    nos_passos = {req.id for p in passos.passos for req in p.requisitos}
    no_balde = {x.requisito.id for x in passos.requisitos_da_receita}
    assert nos_passos | no_balde == r.equipamentos | r.tecnicas
    assert not nos_passos & no_balde


@settings(max_examples=100, deadline=None)
@given(
    _todas_as_receitas(),
    st.dictionaries(
        st.sampled_from([e.id for e in EQUIPAMENTOS] + [t.id for t in TECNICAS]),
        st.sampled_from([Posse.TEM, Posse.NAO_TEM, None]),
        max_size=10,
    ),
)
def test_estado_de_cada_requisito_e_o_do_perfil(
    r: Receita, respostas: dict[str, Posse | None]
) -> None:
    perfil = PerfilCozinha.inicial()
    for id_, posse in respostas.items():
        if posse is None:
            perfil = perfil.sem_resposta(id_)
        elif id_ in perfil.equipamentos:
            perfil = perfil.com_equipamento(id_, posse)
        else:
            perfil = perfil.com_tecnica(id_, posse)
    passos = avaliar_passos(r, perfil)
    todos = [req for p in passos.passos for req in p.requisitos] + [
        x.requisito for x in passos.requisitos_da_receita
    ]
    for req in todos:
        esperado = (
            perfil.tem_equipamento(req.id)
            if req.tipo is TipoDeRequisito.EQUIPAMENTO
            else perfil.domina_tecnica(req.id)
        )
        assert req.estado is esperado
        assert req.suposto == perfil.suposto(req.id)


# --------------------------------------------------------------------------- #
# Perguntas com as opções
# --------------------------------------------------------------------------- #

NAO_SEI = {"rotulo": "Não sei", "resposta": "nao_sei"}


@pytest.mark.parametrize(
    ("tipo", "campo", "opcoes", "entrada"),
    [
        (
            TipoRestricao.EQUIPAMENTO,
            "forno",
            [
                {"rotulo": "Tenho", "resposta": "sim"},
                {"rotulo": "Não tenho", "resposta": "nao"},
                NAO_SEI,
            ],
            None,
        ),
        (
            TipoRestricao.TECNICA,
            "bechamel",
            [
                {"rotulo": "Faço", "resposta": "sim"},
                {"rotulo": "Não faço", "resposta": "nao"},
                NAO_SEI,
            ],
            None,
        ),
        (
            TipoRestricao.GOSTO,
            "gosto",
            [
                {"rotulo": "Gosto de fazer", "resposta": "gosta"},
                {"rotulo": "Não gosto", "resposta": "nao_gosta"},
                NAO_SEI,
            ],
            None,
        ),
        (
            TipoRestricao.OPERACIONAL,
            "tem_gas_sobrando",
            [{"rotulo": "Sim", "resposta": "sim"}, {"rotulo": "Não", "resposta": "nao"}, NAO_SEI],
            None,
        ),
        (
            TipoRestricao.OPERACIONAL,
            "bocas_fogao",
            [NAO_SEI],
            {"tipo": "inteiro", "unidade": "bocas", "min": 1, "max": 8},
        ),
        (
            TipoRestricao.OPERACIONAL,
            "rendimento_porcoes",
            [],
            {"tipo": "inteiro", "unidade": "porções", "min": 1, "max": 500},
        ),
        (TipoRestricao.EQUIPAMENTO, "modo_preparo", [], {"tipo": "texto"}),
        (TipoRestricao.INGREDIENTE, "milho verde", [], {"tipo": "texto"}),
    ],
)
def test_opcoes_de_cada_pergunta(
    tipo: TipoRestricao, campo: str, opcoes: list[dict[str, str]], entrada: dict[str, Any] | None
) -> None:
    assert como_responder(Pergunta(tipo, campo, "?")) == (opcoes, entrada)


def test_as_opcoes_nao_sao_compartilhadas_entre_perguntas() -> None:
    primeira, _ = como_responder(Pergunta(TipoRestricao.EQUIPAMENTO, "forno", "?"))
    primeira[0]["rotulo"] = "estragado"
    segunda, _ = como_responder(Pergunta(TipoRestricao.EQUIPAMENTO, "forno", "?"))
    assert segunda[0]["rotulo"] == "Tenho"


def test_pergunta_aponta_os_passos_que_a_pedem() -> None:
    r = receita(
        "Frango assado",
        [FRANGO],
        modo_preparo=["Tempere.", "Leve ao forno por 40 minutos.", "Sirva."],
    )
    passos = avaliar_passos(r, PerfilCozinha.inicial())
    perguntas = perguntas_com_opcoes(
        [
            Pergunta(TipoRestricao.EQUIPAMENTO, "forno", "A senhora tem forno?", "motivo"),
            Pergunta(TipoRestricao.EQUIPAMENTO, "air_fryer", "E air fryer?"),
            Pergunta(TipoRestricao.GOSTO, "gosto", "Gosta?"),
        ],
        passos,
    )
    assert [p["passos"] for p in perguntas] == [[2], [2], []], (
        "a air fryer substitui o forno do passo 2"
    )
    assert perguntas[0] == {
        "tipo": "equipamento",
        "assunto": "equipamento",
        "campo": "forno",
        "texto": "A senhora tem forno?",
        "motivo": "motivo",
        "compras": [],
        "opcoes": como_responder(Pergunta(TipoRestricao.EQUIPAMENTO, "forno", ""))[0],
        "entrada": None,
        "passos": [2],
    }
    assert [p["assunto"] for p in perguntas] == ["equipamento", "equipamento", "gosto"]
    assert (
        perguntas_com_opcoes([Pergunta(TipoRestricao.EQUIPAMENTO, "forno", "?")])[0]["passos"] == []
    )


# --------------------------------------------------------------------------- #
# O que a avaliação ganha, na forma do contrato
# --------------------------------------------------------------------------- #


def test_exige_e_o_mesmo_de_antes() -> None:
    """Os nomes em ordem alfabética, como `avaliar_receita` já devolvia."""
    r = receita(
        "Frango à parmegiana",
        [FRANGO],
        modo_preparo=["Empane o frango e frite.", "Leve ao forno e gratine."],
    )
    assert exigencias(r) == {"equipamentos": ["Forno"], "tecnicas": ["Empanar", "Fritar"]}


def _chaves(exemplo: dict[str, Any]) -> set[str]:
    return set(exemplo)


def test_por_passo_tem_a_forma_do_contrato(despensa) -> None:  # type: ignore[no-untyped-def]
    contrato = json.loads(CONTRATO.read_text(encoding="utf-8"))
    r = receita(
        "Arroz com frango",
        [FRANGO, ingrediente("2 xícaras de arroz", "arroz", 2, "xicara")],
        rendimento_porcoes=4,
        modo_preparo=[
            "Refogue a cebola e o alho no óleo.",
            "Junte o frango e leve ao forno.",
            "Acrescente o arroz e a água e cozinhe por 20 minutos.",
        ],
    )
    perfil = PerfilCozinha.inicial()
    avaliacao = avaliar(r, perfil, despensa)
    saida = detalhar(r, perfil, avaliacao)
    json.dumps(saida, ensure_ascii=False)  # serializável como sai na ferramenta e na API

    por_passo = saida["por_passo"]
    passo_do_contrato = contrato["passos"][0]
    assert _chaves(passo_do_contrato) <= _chaves(por_passo["passos"][0])
    requisito_do_contrato = passo_do_contrato["requisitos"][0]
    todos = [req for p in por_passo["passos"] for req in p["requisitos"]]
    assert todos
    assert all(_chaves(requisito_do_contrato) <= _chaves(req) for req in todos)
    limite_do_contrato = contrato["passos"][2]["limites"][0]
    limites = [lim for p in por_passo["passos"] for lim in p["limites"]]
    assert limites
    assert all(_chaves(limite_do_contrato) <= _chaves(lim) for lim in limites)
    pergunta_do_contrato = contrato["perguntas"][0]
    assert saida["perguntas"]
    assert all(_chaves(pergunta_do_contrato) <= _chaves(p) for p in saida["perguntas"])
    for pergunta in saida["perguntas"]:
        assert all(set(o) == {"rotulo", "resposta"} for o in pergunta["opcoes"])

    so_do_nome = detalhar(receita("Frango assado", [FRANGO]), perfil, avaliacao)["por_passo"]
    requisito_da_receita = contrato["requisitos_da_receita"][0]
    assert so_do_nome["requisitos_da_receita"]
    assert all(
        _chaves(requisito_da_receita) <= _chaves(x) for x in so_do_nome["requisitos_da_receita"]
    )


def test_perguntas_do_detalhe_sao_as_do_portao(despensa) -> None:  # type: ignore[no-untyped-def]
    """Mesma ordem, mesmos campos: as opções só se somam ao que o portão perguntou."""
    r = receita("Frango assado", [FRANGO], modo_preparo=["Leve ao forno por 40 minutos."])
    perfil = PerfilCozinha.inicial()
    avaliacao = avaliar(r, perfil, despensa)
    saida = detalhar(r, perfil, avaliacao)
    assert [(p["tipo"], p["campo"], p["texto"], p["motivo"]) for p in saida["perguntas"]] == [
        (p.tipo.name.lower(), p.campo, p.texto, p.motivo) for p in avaliacao.perguntas
    ]


def test_passos_em_json_sem_nada() -> None:
    assert PassosDaReceita(()).para_json() == {"passos": [], "requisitos_da_receita": []}


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Retire a carne da geladeira 30 minutos antes de assar.", ("descanso", 30, None)),
        ("Ligue o forno 15 minutos antes.", ("tempo", 15, "forno")),
        ("Asse por 30 minutos antes de desenformar.", ("tempo", 30, "forno")),
        ("Retire o frango da geladeira e asse por 40 minutos.", ("tempo", 40, "forno")),
    ],
)
def test_antecedencia_e_espera_e_o_que_sai_nao_conta(
    texto: str, esperado: tuple[str, int, str | None]
) -> None:
    (limite,) = extrair_limites(texto)
    assert (limite.tipo.value, limite.minutos, limite.equipamento) == esperado


def test_frio_que_e_so_dica_nao_e_passo_de_frio() -> None:
    from mise.passos import passos_com_frio

    r = receita(
        "Arroz",
        [ingrediente("1 xícara de arroz", "arroz", 1, "xicara")],
        modo_preparo=["Cozinhe o arroz.", "Se sobrar, pode congelar.", "Leve à geladeira."],
    )
    assert passos_com_frio(r) == (3,)
