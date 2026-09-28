"""A linha da despensa e a conta única do custo: a planilha e as mudanças dela passam pelo mesmo lugar."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

from mise import categorias
from mise.despensa import (
    Confianca,
    Despensa,
    LinhaDaDespensa,
    OrigemDoItem,
    TipoDePendencia,
    carregar_despensa,
    carregar_linhas,
    id_do_item,
    montar_despensa,
    montar_ingrediente,
)
from mise.dinheiro import Dinheiro
from mise.erros import (
    ErroDeUso,
    MassaDesconhecida,
    PlanilhaInvalida,
    PrecoDesconhecido,
    QuantidadeInvalida,
)
from mise.receita import ingrediente, receita
from mise.unidades import Dimensao, Quantidade
from mise.viabilidade import checar_ingredientes


def _linha(**campos: object) -> LinhaDaDespensa:
    base: dict[str, object] = {
        "nome": "Creme de leite",
        "estoque": Decimal(2),
        "unidade": "un 200g",
        "quantidade_comprada": Decimal(2),
        "preco_pago": Decimal("9.00"),
    }
    return LinhaDaDespensa(**{**base, **campos})  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Ids e categorias
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("Carne moída (patinho)", "carne-moida-patinho"),
        ("Óleo de soja", "oleo-de-soja"),
        ("Salsinha (cheiro-verde)", "salsinha-cheiro-verde"),
        ("Arroz branco tipo 1", "arroz-branco-tipo-1"),
        ("  Açafrão em pó (cúrcuma)  ", "acafrao-em-po-curcuma"),
    ],
)
def test_id_e_o_slug_do_nome(nome: str, esperado: str) -> None:
    assert id_do_item(nome) == esperado


def test_os_37_itens_tem_id_estavel_e_categoria_escrita_a_mao(despensa: Despensa) -> None:
    ids = [i.id for i in despensa]
    assert len(set(ids)) == 37
    assert set(ids) == set(categorias.DA_PLANILHA)
    for item in despensa:
        assert item.categoria == categorias.DA_PLANILHA[item.id]
        assert item.categoria != "outros", item.nome
        assert item.origem is OrigemDoItem.PLANILHA
        assert item.preco_informado


def test_contagem_das_categorias_da_planilha(despensa: Despensa) -> None:
    contagem: dict[str, int] = {}
    for item in despensa:
        contagem[item.categoria] = contagem.get(item.categoria, 0) + 1
    assert contagem == {
        "proteinas": 6,
        "graos": 7,
        "hortifruti": 6,
        "laticinios": 5,
        "temperos": 5,
        "oleos": 2,
        "conservas": 1,
        "confeitaria": 5,
    }


def test_por_id_e_pendencia_de(despensa: Despensa) -> None:
    assert despensa.por_id("alcaparras") is despensa["Alcaparras"]
    assert despensa.por_id("caviar") is None
    assert despensa.pendencia_de("Cobertura de chocolate") is None
    assert despensa.pendencia_de("Alcaparras") is None


def test_fracao_de_despensa_sem_valor_e_zero() -> None:
    item, _ = montar_ingrediente(_linha(preco_pago=None, nome="Farinha de rosca"))
    vazia = Despensa(itens={item.nome: item})
    assert vazia.fracao_de(item) == 0


# --------------------------------------------------------------------------- #
# carregar_linhas e carregar_despensa
# --------------------------------------------------------------------------- #


def test_carregar_linhas_cruza_as_abas_na_ordem_dela(caminho_planilha: Path) -> None:
    linhas = carregar_linhas(caminho_planilha)
    assert len(linhas) == 37
    assert linhas[0].nome == "Arroz branco tipo 1"
    assert linhas[0].estoque == Decimal(5)
    assert linhas[0].preco_pago == Decimal("24.9")
    alcaparras = next(linha for linha in linhas if linha.id == "alcaparras")
    assert (alcaparras.unidade, alcaparras.quantidade_comprada) == ("balde 2kg", Decimal(1))


def test_carregar_despensa_e_montar_as_linhas(despensa: Despensa, caminho_planilha: Path) -> None:
    montada = montar_despensa(carregar_linhas(caminho_planilha))
    assert [i.nome for i in montada] == [i.nome for i in despensa]
    assert montada.total_investido == despensa.total_investido == Dinheiro.de("663.39")
    assert montada.pendencias == []


def test_dois_nomes_com_o_mesmo_id_sao_recusados(tmp_path: Path) -> None:
    caminho = tmp_path / "duplicado.xlsx"
    livro = openpyxl.Workbook()
    aba = livro.active
    aba.title = "Despensa"
    aba.append(["Ingrediente", "Quantidade em estoque", "Unidade"])
    aba.append(["Açúcar", 1, "kg"])
    aba.append(["Acucar", 1, "kg"])
    precos = livro.create_sheet("Precos")
    precos.append(["Ingrediente", "Quantidade comprada", "Unidade", "Preço total pago (R$)"])
    precos.append(["Açúcar", 1, "kg", 4.0])
    precos.append(["Acucar", 1, "kg", 4.0])
    livro.save(caminho)
    with pytest.raises(PlanilhaInvalida, match="mesmo id"):
        carregar_despensa(caminho)


# --------------------------------------------------------------------------- #
# montar_ingrediente
# --------------------------------------------------------------------------- #


def test_embalagem_declarada_e_conta_media() -> None:
    item, pendencia = montar_ingrediente(_linha())
    assert pendencia is None
    assert item.custo.valor.arredondado() == Dinheiro.de("22.50")
    assert item.custo.confianca is Confianca.MEDIA
    assert item.custo.derivacao == "2 × 0,2 kg = 0,4 kg; R$ 9,00 ÷ 0,4 kg = R$ 22,50/kg"
    assert item.estoque == Quantidade(Decimal("0.4"), Dimensao.MASSA)
    assert item.id == "creme-de-leite"
    assert item.categoria == "laticinios"


@pytest.mark.parametrize(
    ("unidade", "estoque", "derivacao"),
    [
        ("g", "500", "500 g = 0,5 kg; R$ 9,00 ÷ 0,5 kg = R$ 18,00/kg"),
        ("ml", "500", "500 ml = 0,5 L; R$ 9,00 ÷ 0,5 L = R$ 18,00/L"),
        ("kg", "0.5", "R$ 9,00 ÷ 0,5 kg = R$ 18,00/kg"),
    ],
)
def test_unidade_pura_e_conversao_e_nao_embalagem(
    unidade: str, estoque: str, derivacao: str
) -> None:
    item, _ = montar_ingrediente(
        _linha(unidade=unidade, estoque=Decimal(estoque), quantidade_comprada=Decimal(estoque))
    )
    assert item.custo.confianca is Confianca.ALTA
    assert item.custo.derivacao == derivacao


def test_embalagem_informada_por_ela_e_conta_media_escrita_inteira() -> None:
    item, pendencia = montar_ingrediente(
        _linha(
            nome="Cobertura de chocolate",
            estoque=Decimal(1),
            unidade="un 1kg",
            quantidade_comprada=Decimal(1),
            preco_pago=Decimal("79.90"),
            conteudo_informado=True,
        )
    )
    assert pendencia is None
    assert item.custo.confianca is Confianca.MEDIA
    assert item.custo.derivacao.startswith("1 × 1 kg = 1 kg; R$ 79,90 ÷ 1 kg = R$ 79,90/kg")
    assert "a senhora que informou" in item.custo.derivacao


def test_sem_preco_o_custo_e_desconhecido_e_vira_pergunta() -> None:
    item, pendencia = montar_ingrediente(
        _linha(nome="Farinha de rosca", unidade="kg", estoque=Decimal("0.5"), preco_pago=None)
    )
    assert not item.preco_informado
    assert item.preco_pago == Dinheiro.zero()
    assert item.custo.confianca is Confianca.DESCONHECIDA
    # Sem o preço não há custo, e ninguém pergunta: a receita custa pela referência.
    assert pendencia is None
    assert TipoDePendencia.PRECO.value == "preco_pago"
    with pytest.raises(PrecoDesconhecido) as erro:
        item.custo_de(Quantidade(Decimal("0.1"), Dimensao.MASSA))
    assert erro.value.ingrediente == "Farinha de rosca"


def test_embalagem_opaca_de_item_novo_pergunta_o_peso() -> None:
    item, pendencia = montar_ingrediente(
        _linha(
            nome="Leite condensado",
            unidade="un",
            estoque=Decimal(1),
            quantidade_comprada=Decimal(1),
        )
    )
    assert item.embalagem_opaca
    assert pendencia is None
    with pytest.raises(MassaDesconhecida):
        item.custo_de(Quantidade(Decimal("0.2"), Dimensao.MASSA))


def test_quantidade_comprada_zero_e_recusada_mesmo_sem_preco() -> None:
    with pytest.raises(QuantidadeInvalida):
        montar_ingrediente(_linha(quantidade_comprada=Decimal(0), preco_pago=None))


def test_a_linha_nao_troca_de_nome_nem_de_id() -> None:
    linha = _linha()
    assert linha.com(estoque=Decimal(1)).estoque == Decimal(1)
    with pytest.raises(ErroDeUso, match="nome"):
        linha.com(nome="Nata")
    with pytest.raises(ErroDeUso):
        linha.com(id="outro")


def test_categoria_explicita_vale_mais_que_a_do_nome() -> None:
    assert _linha(categoria="confeitaria").categoria == "confeitaria"
    assert _linha(nome="Trufa branca").categoria == "outros"


# --------------------------------------------------------------------------- #
# O portão com um item sem preço
# --------------------------------------------------------------------------- #


def test_receita_com_item_sem_preco_pergunta_o_preco_em_vez_de_custar_zero(
    despensa: Despensa,
) -> None:
    rosca, pendencia = montar_ingrediente(
        _linha(nome="Farinha de rosca", unidade="kg", estoque=Decimal(1), preco_pago=None)
    )
    assert pendencia is None
    com_rosca = Despensa(itens={**despensa.itens, rosca.nome: rosca})
    bife = receita(
        "Bife à milanesa",
        [ingrediente("200 g de farinha de rosca", "farinha de rosca", 200, "g")],
        rendimento_porcoes=2,
    )
    checagem, usos, faltantes, _ = checar_ingredientes(bife, com_rosca)
    assert not usos
    assert not faltantes
    # Sem o preço dela e sem referência: não custa zero, e não pergunta; fica de fora.
    assert not checagem.perguntas
    assert [i.id for i in checagem.impedimentos] == ["sem_preco"]
