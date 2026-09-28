"""LLM-as-judge e a calibração que o torna interpretável.

O teste mais importante deste arquivo é `test_o_juiz_nao_generaliza_sozinho`, e
ele **afirma um resultado ruim de propósito**.

O juiz determinístico concorda 100% com o humano no conjunto contra o qual as
regras dele foram escritas. Isso não é evidência de nada: é sobreajuste por
construção. No conjunto reservado (escrito depois e nunca consultado ao ajustar
as regras), ele cai para 67%, abaixo do limiar de utilizável que o próprio módulo
define.

Registrar isso é o ponto. Um juiz apresentado com a concordância do conjunto de
ajuste é a mesma categoria de erro que o juiz existe para pegar: um número que
parece mais confiável do que é.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.juiz import (
    CONCORDANCIA_MINIMA,
    LIMIAR,
    Calibracao,
    JuizDeModelo,
    JuizDeterministico,
    Nota,
    Resposta,
    calibrar,
    carregar_respostas,
)

CASOS = Path(__file__).resolve().parents[1] / "casos"
RESERVADO = CASOS / "respostas_reservadas.yaml"


@pytest.fixture
def juiz() -> JuizDeterministico:
    return JuizDeterministico()


# --------------------------------------------------------------------------- #
# O dataset rotulado                                                           #
# --------------------------------------------------------------------------- #


def test_dataset_e_equilibrado() -> None:
    """Conjunto só com resposta boa mede complacência, não qualidade."""
    respostas = carregar_respostas()
    boas = sum(r.humano_aprovou for r in respostas)
    assert boas == len(respostas) - boas


def test_todo_rotulo_tem_criterio() -> None:
    """Quem discordar precisa poder discordar do critério, não do rótulo."""
    sem = [r.id for r in carregar_respostas() if not r.porque]
    assert not sem


def test_reservado_existe_e_e_equilibrado() -> None:
    respostas = carregar_respostas(RESERVADO)
    boas = sum(r.humano_aprovou for r in respostas)
    assert boas == len(respostas) - boas
    assert len(respostas) >= 6


def test_os_dois_conjuntos_nao_se_cruzam() -> None:
    """Se um caso aparecer nos dois, o reservado deixou de ser reservado."""
    ajuste = {r.id for r in carregar_respostas()}
    reservado = {r.id for r in carregar_respostas(RESERVADO)}
    assert not (ajuste & reservado)


# --------------------------------------------------------------------------- #
# A medição honesta                                                            #
# --------------------------------------------------------------------------- #


def test_concordancia_perfeita_no_conjunto_de_ajuste(juiz: JuizDeterministico) -> None:
    """E isso **não** é evidência de qualidade.

    As regras foram escritas olhando este conjunto. Um teste que parasse aqui
    estaria apresentando sobreajuste como resultado.
    """
    assert calibrar(juiz).concordancia == 1.0


def test_o_juiz_nao_generaliza_sozinho(juiz: JuizDeterministico) -> None:
    """67% no conjunto reservado, abaixo do limiar de 80% que o módulo define.

    Este teste afirma um resultado ruim porque o resultado ruim é a informação.
    O juiz determinístico é o **piso**: serve para o portão rodar sem
    credencial e para um juiz LLM ter contra o que provar que acrescenta algo.
    Não serve como medida de qualidade sozinho.

    Se um dia ele passar de 80% no reservado, este teste quebra, e aí o certo é
    conferir se o conjunto reservado não vazou para o ajuste, antes de comemorar.
    """
    calibracao = calibrar(juiz, carregar_respostas(RESERVADO))

    assert calibracao.concordancia == pytest.approx(4 / 6, abs=0.01)
    assert not calibracao.utilizavel, (
        "o juiz determinístico passou do limiar no conjunto reservado. "
        "Confira se o reservado não vazou para o ajuste antes de comemorar."
    )


def test_falso_positivo_e_separado_de_falso_negativo(juiz: JuizDeterministico) -> None:
    """Custam coisas diferentes e não podem virar um número só.

    Aprovar resposta ruim deixa um número errado chegar à Dona Maria. Reprovar
    resposta boa só gasta revisão humana.
    """
    c = calibrar(juiz, carregar_respostas(RESERVADO))
    assert "reservado-precisao-falsa" in c.falsos_positivos
    assert "reservado-orcamento-respeitado" in c.falsos_negativos


def test_o_falso_positivo_e_o_que_mais_custa(juiz: JuizDeterministico) -> None:
    """ "Exatamente R$ 4,3271" sobre medida de xícara é precisão inventada.

    O juiz aprovou. É a falha mais cara que ele tem, e está registrada aqui em
    vez de diluída numa média.
    """
    caso = next(r for r in carregar_respostas(RESERVADO) if r.id == "reservado-precisao-falsa")
    assert juiz.julgar(caso).aprovou
    assert not caso.humano_aprovou


# --------------------------------------------------------------------------- #
# As regras do juiz determinístico                                             #
# --------------------------------------------------------------------------- #


def test_numero_sem_conta_e_reprovado(juiz: JuizDeterministico) -> None:
    nota = juiz.julgar(Resposta("x", "quanto custa?", "O custo é R$ 4,31.", "ruim", "sem conta"))
    assert not nota.aprovou
    assert "sem a conta" in nota.justificativa


def test_preco_que_ignora_a_taxa_e_reprovado(juiz: JuizDeterministico) -> None:
    """O erro mais caro do enunciado, e o que mais parece certo."""
    nota = juiz.julgar(
        Resposta(
            "x",
            "por quanto vendo?",
            "Vendendo a R$ 5,00 a senhora tem R$ 0,69 de lucro por porção, "
            "que dá uma margem boa para começar.",
            "ruim",
            "ignora a taxa",
        )
    )
    assert "ignora os 10%" in nota.justificativa


def test_recusa_honesta_e_premiada(juiz: JuizDeterministico) -> None:
    nota = juiz.julgar(
        Resposta(
            "x",
            "quanto custa?",
            "Não dá para calcular ainda: preciso saber quanto vem na embalagem "
            "antes de dividir o preço pela quantidade.",
            "boa",
            "recusa",
        )
    )
    assert nota.aprovou


def test_nota_fica_entre_zero_e_um(juiz: JuizDeterministico) -> None:
    for texto in ["R$ 1,00", "Não dá para calcular, preciso saber o peso da embalagem primeiro"]:
        nota = juiz.julgar(Resposta("x", "p", texto, "boa", ""))
        assert 0.0 <= nota.valor <= 1.0


def test_limiar_define_aprovacao() -> None:
    assert Nota(LIMIAR, "").aprovou
    assert not Nota(LIMIAR - 0.01, "").aprovou


# --------------------------------------------------------------------------- #
# Calibração como estrutura                                                    #
# --------------------------------------------------------------------------- #


def test_calibracao_vazia_nao_divide_por_zero() -> None:
    assert Calibracao(0, 0, (), ()).concordancia == 0.0


def test_calibracao_se_apresenta() -> None:
    c = Calibracao(10, 8, ("a",), ("b",))
    texto = str(c)
    assert "8/10" in texto
    assert "aprovou o que o humano reprovou: a" in texto
    assert "reprovou o que o humano aprovou: b" in texto


def test_limiar_de_utilizavel_e_explicito() -> None:
    assert Calibracao(10, 8, (), ()).utilizavel
    assert not Calibracao(10, 7, (), ()).utilizavel
    assert CONCORDANCIA_MINIMA == 0.8


# --------------------------------------------------------------------------- #
# O juiz por modelo                                                            #
# --------------------------------------------------------------------------- #


def test_juiz_de_modelo_sabe_quando_nao_pode_rodar(monkeypatch) -> None:
    """O portão do CI não pode depender de chave de API.

    Portão que falha por motivo alheio ao código é portão que alguém desliga.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert JuizDeModelo.disponivel() is False

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-teste")
    assert JuizDeModelo.disponivel() is True


def test_juiz_de_modelo_tem_a_mesma_interface() -> None:
    """É o que permite trocar juiz sem mexer na calibração."""
    assert hasattr(JuizDeModelo(), "julgar")


def test_juiz_de_modelo_pede_temperatura_zero() -> None:
    from evals.juiz import TEMPERATURA_DO_JUIZ

    resposta = Resposta("r1", "Quanto cobro?", "Cobre R$ 8,68.", "boa", "tem a conta")
    pedido = JuizDeModelo().pedido(resposta)
    assert pedido["temperature"] == TEMPERATURA_DO_JUIZ == 0
    assert pedido["model"] == "claude-haiku-4-5"
    assert "Cobre R$ 8,68." in str(pedido["messages"])
