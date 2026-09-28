from __future__ import annotations

import pytest

from mise.erros import (
    CustoIndeterminado,
    DensidadeDesconhecida,
    ErroDeDados,
    ErroDeRegra,
    ErroDeUso,
    ErroMise,
    IngredienteDesconhecido,
    MassaDesconhecida,
    OrcamentoExcedido,
    PlanilhaInvalida,
    QuantidadeInvalida,
    UnidadeNaoNormalizavel,
    UnidadesIncompativeis,
    ViabilidadeNaoConfirmada,
)


def test_hierarquia_separa_dado_de_regra_de_uso() -> None:
    """A categoria decide a reação: perguntar, recusar ou corrigir o código."""
    assert issubclass(ErroDeDados, ErroMise)
    assert issubclass(ErroDeRegra, ErroMise)
    assert issubclass(ErroDeUso, ErroMise)
    assert not issubclass(ErroDeDados, ErroDeRegra)


def test_contexto_aparece_na_mensagem() -> None:
    erro = ErroMise("algo quebrou", ingrediente="Sal", valor=3)
    assert "algo quebrou" in str(erro)
    assert "ingrediente='Sal'" in str(erro)
    assert "valor=3" in str(erro)


def test_erro_sem_contexto_nao_ganha_parenteses() -> None:
    assert str(ErroMise("simples")) == "simples"


def test_massa_desconhecida_gera_pergunta_em_pt_br() -> None:
    erro = MassaDesconhecida("Cobertura de chocolate", 79.90, "un")
    assert "R$ 79,90" in erro.pergunta
    assert "quanto vem na embalagem" in erro.pergunta
    assert erro.ingrediente == "Cobertura de chocolate"


def test_massa_desconhecida_formata_milhar() -> None:
    assert "R$ 1.234,50" in MassaDesconhecida("Trufa", 1234.50, "un").pergunta


def test_unidade_nao_normalizavel_com_ingrediente_nomeia_o_item() -> None:
    erro = UnidadeNaoNormalizavel("caixa", "Sal")
    assert erro.mensagem == "não sei quanto pesa 1 caixa de sal"
    assert erro.ingrediente == "Sal"


def test_unidade_nao_normalizavel_sem_ingrediente_omite_o_trecho() -> None:
    erro = UnidadeNaoNormalizavel("caixa")
    assert erro.mensagem == "não entendi a medida “caixa”"
    assert erro.pergunta == (
        "Não entendi a medida “caixa”. Pode me dizer em gramas, quilos, litros ou unidades?"
    )
    assert erro.ingrediente is None


@pytest.mark.parametrize(
    ("ingrediente", "pergunta"),
    [
        (
            "Peito de frango",
            "Não sei quanto pesa um peito de frango. Se a senhora souber, em gramas, eu calculo.",
        ),
        (
            "Caldo de carne (tempero)",
            "Não sei quanto pesa um caldo de carne. Se a senhora souber, em gramas, eu calculo.",
        ),
        (
            "Cebola",
            "Não sei quanto pesa uma cebola. Se a senhora souber, em gramas, eu calculo.",
        ),
        (
            "Tahine",
            "Não sei quanto pesa cada unidade de tahine. Se a senhora souber, em gramas, "
            "eu calculo.",
        ),
    ],
)
def test_sem_medida_pergunta_o_peso_de_uma_peca(ingrediente: str, pergunta: str) -> None:
    """ "1 peito de frango" sem peso: a pergunta fala como ela, sem "unidade ''"."""
    erro = UnidadeNaoNormalizavel("", ingrediente)
    assert erro.pergunta == pergunta
    assert "'" not in erro.mensagem


def test_densidade_desconhecida_guarda_o_par() -> None:
    erro = DensidadeDesconhecida("bacalhau", "xícara")
    assert erro.ingrediente == "bacalhau"
    assert erro.medida == "xícara"


@pytest.mark.parametrize(
    ("ingrediente", "medida", "pergunta"),
    [
        (
            "Alcaparras",
            "colher de sopa",
            "Não sei quanto pesa uma colher de sopa de alcaparras. Se a senhora souber, "
            "em gramas, eu calculo.",
        ),
        (
            "Queijo mussarela",
            "xicara de cha",
            "Não sei quanto pesa uma xícara de chá de queijo mussarela. Se a senhora souber, "
            "em gramas, eu calculo.",
        ),
        (
            "Leite ninho em pó",
            "copo americano",
            "Não sei quanto pesa um copo americano de leite ninho em pó. Se a senhora souber, "
            "em gramas, eu calculo.",
        ),
    ],
)
def test_densidade_desconhecida_pergunta_como_gente(
    ingrediente: str, medida: str, pergunta: str
) -> None:
    """Nada de "densidade" nem aspas de código no que chega a ela."""
    erro = DensidadeDesconhecida(ingrediente, medida)
    assert erro.pergunta == pergunta
    assert "densidade" not in erro.mensagem
    assert "'" not in erro.mensagem


def test_ingrediente_desconhecido_carrega_o_palpite() -> None:
    erro = IngredienteDesconhecido("farinha de rosca", "Farinha de trigo", 0.62)
    assert erro.melhor_palpite == "Farinha de trigo"
    assert erro.score == 0.62


def test_viabilidade_nao_confirmada_lista_pendencias() -> None:
    erro = ViabilidadeNaoConfirmada("Lasanha", "FALTA_INFO", ("tem forno?",))
    assert erro.veredito == "FALTA_INFO"
    assert erro.pendencias == ("tem forno?",)
    assert "APTO" in str(erro)


def test_custo_indeterminado_conta_os_ingredientes() -> None:
    erro = CustoIndeterminado("Bolo", ("Cobertura de chocolate", "Trufa"))
    assert "2 ingredientes sem custo" in str(erro)


def test_orcamento_excedido_calcula_o_quanto_falta() -> None:
    erro = OrcamentoExcedido(100.0, 80.0)
    assert erro.faltam == pytest.approx(20.0)
    assert "R$ 100.00" in str(erro) or "100" in str(erro)


def test_planilha_invalida_e_erro_de_uso() -> None:
    erro = PlanilhaInvalida("aba ausente", "/tmp/x.xlsx")
    assert isinstance(erro, ErroDeUso)
    assert erro.caminho == "/tmp/x.xlsx"


def test_quantidade_invalida_sem_contexto() -> None:
    assert "em " not in str(QuantidadeInvalida(-1))


def test_unidades_incompativeis_nomeia_os_dois_lados() -> None:
    erro = UnidadesIncompativeis("kg", "L")
    assert erro.esquerda == "kg"
    assert erro.direita == "L"


def test_ausente_e_erro_de_uso_com_contexto() -> None:
    """Na conversa, apontar para o que não existe é erro de quem chamou."""
    from mise.erros import Ausente
    from mise.serializacao import _erro_json

    erro = Ausente("não encontrei esse ingrediente na despensa", id="item-0000")
    assert isinstance(erro, ErroDeUso)
    assert erro.contexto == {"id": "item-0000"}
    payload = _erro_json(erro)
    assert (payload["categoria"], payload["tipo"]) == ("uso", "Ausente")
