"""Custo de modelo, conferido à mão.

Os números de referência são os da primeira rodada real do agente: 16 tokens de
entrada, 4.527 de saída, 230.513 lidos do cache e 55.396 gravados, no Opus 5.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from telemetria.custo import (
    FONTE_DOS_PRECOS,
    PRECOS,
    ModeloDesconhecido,
    Orcamento,
    UsoDeModelo,
    preco_de,
)

RODADA_REAL = UsoDeModelo(
    "claude-opus-5", entrada=16, saida=4527, leitura_de_cache=230_513, gravacao_de_cache=55_396
)


def test_precos_da_referencia() -> None:
    """Opus 5 a US$ 5 / 25; a versão anterior tinha 15 / 75, três vezes o real."""
    assert (PRECOS["claude-opus-5"].entrada, PRECOS["claude-opus-5"].saida) == (5, 25)
    assert (PRECOS["claude-sonnet-5"].entrada, PRECOS["claude-sonnet-5"].saida) == (2, 10)
    assert (PRECOS["claude-haiku-4-5"].entrada, PRECOS["claude-haiku-4-5"].saida) == (1, 5)
    assert "24/06/2026" in FONTE_DOS_PRECOS


def test_cache_tem_preco_proprio() -> None:
    opus = PRECOS["claude-opus-5"]
    assert opus.leitura_de_cache == Decimal("0.5")
    assert opus.gravacao_de_cache("5m") == Decimal("6.25")
    assert opus.gravacao_de_cache("1h") == Decimal("10")
    assert PRECOS["claude-opus-5-5"].leitura_de_cache == Decimal("0.20")
    with pytest.raises(ValueError, match="vida de cache"):
        opus.gravacao_de_cache("1d")


def test_a_rodada_real_conferida_a_mao() -> None:
    """16×5 + 4.527×25 + 230.513×0,5 + 55.396×6,25, por milhão."""
    partes = RODADA_REAL.partes_usd()
    assert partes["entrada"] == Decimal("0.00008")
    assert partes["saida"] == Decimal("0.113175")
    assert partes["leitura_de_cache"] == Decimal("0.1152565")
    assert partes["gravacao_de_cache"] == Decimal("0.346225")
    assert RODADA_REAL.custo_usd == Decimal("0.5747365")


def test_so_entrada_e_saida_erraria_por_ordem_de_grandeza() -> None:
    sem_cache = UsoDeModelo("claude-opus-5", entrada=16, saida=4527)
    assert RODADA_REAL.custo_usd > 5 * sem_cache.custo_usd


def test_gravacao_de_uma_hora_custa_mais() -> None:
    uma_hora = UsoDeModelo("claude-opus-5", gravacao_de_cache=1_000_000, vida_do_cache="1h")
    assert uma_hora.custo_usd == Decimal("10")


@pytest.mark.parametrize(
    ("nome", "entrada"),
    [
        ("claude-opus-5", 5),
        ("claude-opus-5-5", 4),  # não pode cair no Opus 5
        ("anthropic/claude-opus-5", 5),
        ("claude-sonnet-5-20261001", 2),
    ],
)
def test_nome_do_modelo(nome: str, entrada: int) -> None:
    assert preco_de(nome).entrada == entrada


@pytest.mark.parametrize("nome", ["gpt-5", "claude-opus-50", "claude-opus"])
def test_modelo_sem_preco_e_recusado(nome: str) -> None:
    with pytest.raises(ModeloDesconhecido, match="sem preço"):
        preco_de(nome)


def test_token_negativo_e_recusado() -> None:
    with pytest.raises(ValueError, match="negativa"):
        UsoDeModelo("claude-opus-5", saida=-1)


def test_tokens_somam_tudo() -> None:
    assert RODADA_REAL.tokens == 16 + 4527 + 230_513 + 55_396


@pytest.fixture
def orcamento() -> Orcamento:
    o = Orcamento()
    o.registrar(RODADA_REAL)
    o.registrar(UsoDeModelo("claude-sonnet-5", entrada=1000, saida=100))
    o.registrar(UsoDeModelo("claude-opus-5", saida=1000))
    return o


def test_orcamento_vazio_nao_quebra() -> None:
    vazio = Orcamento()
    assert vazio.total_usd == 0
    assert vazio.concentracao() == []
    assert vazio.resumo() == "nenhuma chamada de modelo registrada"


def test_partes_mostram_onde_esta_o_dinheiro(orcamento: Orcamento) -> None:
    partes = orcamento.partes_usd()
    assert max(partes, key=lambda k: partes[k]) == "gravacao_de_cache"
    assert sum(partes.values()) == orcamento.total_usd


def test_por_modelo_ordena_do_mais_caro(orcamento: Orcamento) -> None:
    assert list(orcamento.por_modelo()) == ["claude-opus-5", "claude-sonnet-5"]


def test_concentracao_responde_o_80_20(orcamento: Orcamento) -> None:
    assert orcamento.concentracao() == [RODADA_REAL]
    assert len(orcamento.concentracao(0.999)) == 3


def test_resumo_diz_qual_parte_pesa(orcamento: Orcamento) -> None:
    texto = orcamento.resumo()
    assert "3 chamada(s)" in texto
    assert "gravacao de cache" in texto
