"""As premissas do preço preliminar: padrão com fonte, o valor dela e a faixa que vale."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from mise import parametros
from mise.dossie import Dossie
from mise.erros import Ausente, ErroDeUso

AGORA = datetime(2026, 9, 26, 13, 30, tzinfo=UTC)


@pytest.fixture
def dossie(tmp_path: Path) -> Dossie:
    return Dossie(tmp_path / "dossie.db", relogio=lambda: AGORA)


def test_todo_padrao_tem_fonte_com_trecho_e_data() -> None:
    for p in parametros.PARAMETROS:
        if p.padrao is None:
            assert p.fonte is None
            continue
        if p.nome in parametros.SEM_FONTE_PUBLICA:
            # A premissa da plataforma diz que é estimativa, e ela muda.
            assert p.fonte is None
            assert "estimativa da plataforma" in p.sobre_o_padrao, p.nome
            assert "a senhora pode mudar" in p.sobre_o_padrao, p.nome
            continue
        assert p.fonte is not None, p.nome
        assert p.fonte.url.startswith("https://"), p.nome
        assert p.fonte.trecho.strip(), p.nome
        assert p.fonte.verificado_em.year == 2026, p.nome
        assert p.sobre_o_padrao, p.nome
        assert p.minimo <= p.padrao <= p.maximo, p.nome


def test_toda_potencia_de_aparelho_e_um_parametro() -> None:
    assert set(parametros.POTENCIA_DO_APARELHO.values()) <= set(parametros.PARAMETROS_POR_NOME)


def test_sem_nada_informado_vale_o_padrao_ou_falta(dossie: Dossie) -> None:
    premissas = parametros.ler(dossie)
    assert list(premissas) == [p.nome for p in parametros.PARAMETROS]
    assert (premissas["valor_hora"].origem, premissas["valor_hora"].valor) == (
        "padrao",
        Decimal("7.37"),
    )
    assert premissas["embalagem_por_porcao"].origem == "falta"
    assert premissas["embalagem_por_porcao"].valor is None
    assert premissas["embalagem_por_porcao"].texto == ""
    assert premissas["embalagem_por_porcao"].fonte is None


def test_o_valor_dela_vale_mais_que_o_padrao_e_volta_com_null(dossie: Dossie) -> None:
    gravada = parametros.definir(dossie, "valor_hora", 15)
    assert (gravada.origem, gravada.valor, gravada.fonte) == (
        "dela",
        Decimal(15),
        "informado pela senhora",
    )
    assert parametros.ler(dossie)["valor_hora"].valor == Decimal(15)
    de_novo = parametros.definir(dossie, "valor_hora", 18.5)
    assert de_novo.valor == Decimal("18.5")
    voltou = parametros.definir(dossie, "valor_hora", None)
    assert (voltou.origem, voltou.valor) == ("padrao", Decimal("7.37"))
    sem_padrao = parametros.definir(dossie, "embalagem_por_porcao", None)
    assert sem_padrao.origem == "falta"


@pytest.mark.parametrize("valor", ["1,20", True, float("nan"), float("inf"), [1]])
def test_so_numero_vira_premissa(dossie: Dossie, valor: object) -> None:
    with pytest.raises(ErroDeUso):
        parametros.definir(dossie, "embalagem_por_porcao", valor)


@pytest.mark.parametrize(
    ("nome", "valor"), [("valor_hora", 0), ("botijao_horas", 5000), ("embalagem_por_porcao", -1)]
)
def test_fora_da_faixa_nao_grava(dossie: Dossie, nome: str, valor: float) -> None:
    with pytest.raises(ErroDeUso) as erro:
        parametros.definir(dossie, nome, valor)
    assert "fora da faixa" in erro.value.mensagem
    assert parametros.ler(dossie)[nome].origem != "dela"


def test_premissa_desconhecida_e_ausente(dossie: Dossie) -> None:
    with pytest.raises(Ausente):
        parametros.definir(dossie, "salario_do_papa", 1)
    with pytest.raises(Ausente):
        parametros.parametro("salario_do_papa")


def test_json_da_premissa_como_o_contrato(dossie: Dossie) -> None:
    padrao = parametros.ler(dossie)["botijao_preco"].para_json(AGORA)
    assert padrao == {
        "nome": "botijao_preco",
        "rotulo": "Preço do botijão de gás",
        "valor": {"valor": 114.8, "texto": "R$ 114,80 o botijão de 13 kg"},
        "origem": "padrao",
        "fonte": padrao["fonte"],
        "fonte_url": padrao["fonte_url"],
        "atualizado_texto": "conferido em 26/09/2026",
        "editavel": True,
    }
    assert "ANP" in (padrao["fonte"] or "")
    assert padrao["fonte_url"].endswith(".xlsx")

    dela = parametros.definir(dossie, "embalagem_por_porcao", 1.2).para_json(AGORA)
    assert dela == {
        "nome": "embalagem_por_porcao",
        "rotulo": "Embalagem por porção",
        "valor": {"valor": 1.2, "texto": "R$ 1,20 por porção"},
        "origem": "dela",
        "fonte": "informado pela senhora",
        "fonte_url": None,
        "atualizado_texto": "hoje, 10:30",
        "editavel": True,
    }
    amanha = parametros.ler(dossie)["embalagem_por_porcao"].para_json(AGORA + timedelta(days=1))
    assert amanha["atualizado_texto"] == "ontem, 10:30"

    falta = parametros.ler(dossie)["potencia_mixer"].para_json(AGORA)
    assert (falta["valor"], falta["origem"], falta["fonte"], falta["atualizado_texto"]) == (
        None,
        "falta",
        None,
        None,
    )


def test_o_texto_de_cada_tipo_de_valor() -> None:
    assert parametros.parametro("kwh_preco").texto(Decimal("0.998")) == "99,8 centavos por kWh"
    assert parametros.parametro("potencia_air_fryer").texto(Decimal(1500)) == "1.500 W"
    assert parametros.parametro("botijao_horas").texto(Decimal(40)) == "40 horas de fogo"
    assert parametros.parametro("valor_hora").texto(Decimal("7.37")) == "R$ 7,37 por hora"


def test_arredondar_para_cima_na_casa_pedida() -> None:
    assert parametros.para_cima(Decimal("0.047833"), 4) == Decimal("0.0479")
    assert parametros.para_cima(Decimal("0.15"), 3) == Decimal("0.150")


def test_a_tabela_e_criada_uma_vez_por_dossie(
    dossie: Dossie, monkeypatch: pytest.MonkeyPatch
) -> None:
    parametros.ler(dossie)
    chamadas: list[str] = []
    monkeypatch.setattr(dossie, "garantir_esquema", chamadas.append)
    parametros.ler(dossie)
    parametros.definir(dossie, "valor_hora", 10)
    assert chamadas == []
