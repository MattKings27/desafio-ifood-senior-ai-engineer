"""Caminhos de erro da leitura da planilha.

Uma planilha malformada precisa falhar alto e com a causa nomeada. O pior
resultado possível aqui é carregar pela metade e seguir calculando preço em
cima de dado incompleto.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

from mise.despensa import (
    ABA_DESPENSA,
    ABA_PRECOS,
    COLUNAS_DESPENSA,
    COLUNAS_PRECOS,
    Despensa,
    carregar_despensa,
)
from mise.dinheiro import Dinheiro
from mise.erros import (
    MassaDesconhecida,
    PlanilhaInvalida,
    QuantidadeInvalida,
    UnidadeNaoNormalizavel,
)
from mise.unidades import Dimensao, Quantidade

LINHAS_DESPENSA = [("Arroz branco tipo 1", 5, "kg"), ("Ovos", 30, "un")]
LINHAS_PRECOS = [("Arroz branco tipo 1", 5, "kg", 24.9), ("Ovos", 30, "un", 24.0)]


def escrever(
    caminho: Path,
    *,
    despensa: list[tuple[object, ...]] | None = None,
    precos: list[tuple[object, ...]] | None = None,
    cabecalho_despensa: tuple[str, ...] = COLUNAS_DESPENSA,
    cabecalho_precos: tuple[str, ...] = COLUNAS_PRECOS,
    aba_despensa: str = ABA_DESPENSA,
    aba_precos: str | None = ABA_PRECOS,
) -> Path:
    """Monta uma planilha de teste com a estrutura que se quiser quebrar."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = aba_despensa
    ws.append(list(cabecalho_despensa))
    for linha in despensa if despensa is not None else LINHAS_DESPENSA:
        ws.append(list(linha))
    if aba_precos is not None:
        wp = wb.create_sheet(aba_precos)
        wp.append(list(cabecalho_precos))
        for linha in precos if precos is not None else LINHAS_PRECOS:
            wp.append(list(linha))
    wb.save(caminho)
    return caminho


@pytest.fixture
def planilha(tmp_path: Path) -> Path:
    return tmp_path / "teste.xlsx"


# --------------------------------------------------------------------------- #
# Caminho feliz sobre planilha sintética
# --------------------------------------------------------------------------- #


def test_carrega_planilha_minima(planilha: Path) -> None:
    d = carregar_despensa(escrever(planilha))
    assert len(d) == 2
    assert d.total_investido == Dinheiro.de("48.90")
    assert d.origem == planilha


def test_aceita_caminho_em_string(planilha: Path) -> None:
    assert len(carregar_despensa(str(escrever(planilha)))) == 2


def test_protocolo_de_colecao(planilha: Path) -> None:
    d = carregar_despensa(escrever(planilha))
    assert "Ovos" in d
    assert "Caviar" not in d
    assert d["Ovos"].nome == "Ovos"
    assert d.get("Caviar") is None
    assert d.get("Ovos") is not None
    assert [i.nome for i in d] == list(d.nomes)


def test_ignora_linhas_vazias(planilha: Path) -> None:
    d = carregar_despensa(
        escrever(
            planilha,
            despensa=[*LINHAS_DESPENSA, (None, None, None), ("", 1, "kg")],
            precos=LINHAS_PRECOS,
        )
    )
    assert len(d) == 2


def test_aceita_decimal_com_virgula(planilha: Path) -> None:
    d = carregar_despensa(
        escrever(
            planilha,
            despensa=[("Sal", "1,5", "kg")],
            precos=[("Sal", "1,5", "kg", "3,00")],
        )
    )
    assert d["Sal"].custo.valor == Dinheiro.de("2.00")


# --------------------------------------------------------------------------- #
# Estrutura inválida
# --------------------------------------------------------------------------- #


def test_arquivo_inexistente(tmp_path: Path) -> None:
    with pytest.raises(PlanilhaInvalida, match="não encontrado"):
        carregar_despensa(tmp_path / "nao_existe.xlsx")


def test_arquivo_nao_e_xlsx(tmp_path: Path) -> None:
    ruim = tmp_path / "ruim.xlsx"
    ruim.write_text("isto não é uma planilha")
    with pytest.raises(PlanilhaInvalida, match="não foi possível abrir"):
        carregar_despensa(ruim)


def test_aba_precos_ausente(planilha: Path) -> None:
    with pytest.raises(PlanilhaInvalida, match="Precos"):
        carregar_despensa(escrever(planilha, aba_precos=None))


def test_aba_despensa_com_nome_errado(planilha: Path) -> None:
    with pytest.raises(PlanilhaInvalida, match="Despensa"):
        carregar_despensa(escrever(planilha, aba_despensa="Estoque"))


def test_cabecalho_diferente(planilha: Path) -> None:
    with pytest.raises(PlanilhaInvalida, match="cabeçalho"):
        carregar_despensa(escrever(planilha, cabecalho_despensa=("Item", "Qtd", "Un")))


def test_aba_sem_linhas_de_dados(planilha: Path) -> None:
    with pytest.raises(PlanilhaInvalida, match="não tem linhas de dados"):
        carregar_despensa(escrever(planilha, despensa=[]))


def test_ingrediente_duplicado(planilha: Path) -> None:
    with pytest.raises(PlanilhaInvalida, match="duas vezes"):
        carregar_despensa(
            escrever(planilha, despensa=[("Sal", 1, "kg"), ("Sal", 2, "kg")], precos=LINHAS_PRECOS)
        )


def test_item_sem_preco_correspondente(planilha: Path) -> None:
    with pytest.raises(PlanilhaInvalida, match="sem preço correspondente"):
        carregar_despensa(
            escrever(planilha, despensa=[("Trufa branca", 1, "kg")], precos=LINHAS_PRECOS)
        )


def test_unidade_divergente_entre_abas(planilha: Path) -> None:
    with pytest.raises(PlanilhaInvalida, match="não dá para cruzar"):
        carregar_despensa(
            escrever(
                planilha,
                despensa=[("Leite", 2, "L")],
                precos=[("Leite", 2, "ml", 10.0)],
            )
        )


def test_unidade_desconhecida(planilha: Path) -> None:
    with pytest.raises(UnidadeNaoNormalizavel):
        carregar_despensa(
            escrever(planilha, despensa=[("Sal", 1, "saco")], precos=[("Sal", 1, "saco", 3.0)])
        )


# --------------------------------------------------------------------------- #
# Valores inválidos
# --------------------------------------------------------------------------- #


def test_valor_ausente(planilha: Path) -> None:
    with pytest.raises(PlanilhaInvalida, match="valor ausente"):
        carregar_despensa(
            escrever(planilha, despensa=[("Sal", None, "kg")], precos=[("Sal", 1, "kg", 3.0)])
        )


def test_valor_nao_numerico(planilha: Path) -> None:
    with pytest.raises(PlanilhaInvalida, match="não numérico"):
        carregar_despensa(
            escrever(planilha, despensa=[("Sal", "muito", "kg")], precos=[("Sal", 1, "kg", 3.0)])
        )


def test_quantidade_negativa(planilha: Path) -> None:
    with pytest.raises(QuantidadeInvalida):
        carregar_despensa(
            escrever(planilha, despensa=[("Sal", -1, "kg")], precos=[("Sal", 1, "kg", 3.0)])
        )


def test_quantidade_comprada_zero(planilha: Path) -> None:
    with pytest.raises(QuantidadeInvalida):
        carregar_despensa(
            escrever(planilha, despensa=[("Sal", 0, "kg")], precos=[("Sal", 0, "kg", 3.0)])
        )


# --------------------------------------------------------------------------- #
# custo_de
# --------------------------------------------------------------------------- #


def test_custo_de_quantidade(despensa: Despensa) -> None:
    arroz = despensa["Arroz branco tipo 1"]
    custo = arroz.custo_de(Quantidade(Decimal("0.1"), Dimensao.MASSA))
    assert custo.arredondado() == Dinheiro.de("0.50")


def test_custo_de_item_contado(despensa: Despensa) -> None:
    ovos = despensa["Ovos"]
    assert ovos.custo_de(Quantidade(Decimal("2"), Dimensao.CONTAGEM)).arredondado() == Dinheiro.de(
        "1.60"
    )


def test_embalagem_opaca_usa_o_peso_estimado_com_a_fonte(despensa: Despensa) -> None:
    """A cobertura de chocolate: o peso vem da página do supermercado, dito como estimativa."""
    cobertura = despensa["Cobertura de chocolate"]
    assert cobertura.embalagem_estimada is not None
    assert cobertura.custo_de(Quantidade(Decimal("0.2"), Dimensao.MASSA)).arredondado() == (
        Dinheiro.de("15.98")
    )
    assert "estimativa" in cobertura.custo.derivacao
    assert "Carrefour" in cobertura.custo.derivacao


def test_embalagem_opaca_sem_fonte_recusa_em_vez_de_estimar() -> None:
    """Sem página que diga o peso, recusar é melhor que estimar: e ninguém pergunta."""
    from mise.despensa import LinhaDaDespensa, montar_ingrediente

    pote, pendencia = montar_ingrediente(
        LinhaDaDespensa("Doce de leite", Decimal(1), "un", Decimal(1), Decimal("20.00"))
    )
    assert pendencia is None
    with pytest.raises(MassaDesconhecida):
        pote.custo_de(Quantidade(Decimal("0.2"), Dimensao.MASSA))


def test_dimensao_errada_em_item_normal(despensa: Despensa) -> None:
    arroz = despensa["Arroz branco tipo 1"]
    with pytest.raises(UnidadeNaoNormalizavel):
        arroz.custo_de(Quantidade(Decimal("1"), Dimensao.VOLUME))


def test_str_do_custo_unitario(despensa: Despensa) -> None:
    assert str(despensa["Arroz branco tipo 1"].custo) == "R$ 4,98/kg"


def test_str_da_pendencia(despensa: Despensa) -> None:
    from mise.despensa import Pendencia

    assert despensa.pendencias == []
    feita = Pendencia("Cobertura de chocolate", "sem peso", "", Dinheiro.de("79.90"))
    assert str(feita) == "Cobertura de chocolate: sem peso"
