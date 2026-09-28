"""Golden test sobre a planilha real da Dona Maria.

Estes números vêm do arquivo que ela entregou. Se qualquer um mudar sem que a
planilha tenha mudado, é regressão, e regressão aqui significa recomendar um
preço errado para uma pessoa que vai apostar o dinheiro dela nisso.

Os seis itens marcados com `# armadilha` são aqueles em que `preço ÷ quantidade`
aplicado cru à planilha dá um número diferente do correto.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from mise.despensa import Confianca, Despensa
from mise.dinheiro import Dinheiro
from mise.unidades import Dimensao

PLANILHA = Path(__file__).resolve().parents[3] / "dados" / "despensa_dona_maria.xlsx"

# nome -> (custo por unidade-base, dimensão, confiança)
CUSTOS_ESPERADOS: dict[str, tuple[str, Dimensao, Confianca]] = {
    "Arroz branco tipo 1": ("4.98", Dimensao.MASSA, Confianca.ALTA),
    "Feijão carioquinha": ("9.00", Dimensao.MASSA, Confianca.ALTA),
    "Feijão preto": ("9.60", Dimensao.MASSA, Confianca.ALTA),
    "Peito de frango": ("14.00", Dimensao.MASSA, Confianca.ALTA),
    "Carne moída (patinho)": ("28.00", Dimensao.MASSA, Confianca.ALTA),
    "Carne de panela (acém)": ("23.20", Dimensao.MASSA, Confianca.ALTA),
    "Miolo de alcatra": ("42.50", Dimensao.MASSA, Confianca.ALTA),
    "Bacon": ("23.90", Dimensao.MASSA, Confianca.ALTA),
    "Ovos": ("0.80", Dimensao.CONTAGEM, Confianca.ALTA),
    "Farinha de trigo": ("5.15", Dimensao.MASSA, Confianca.ALTA),
    "Farinha de mandioca": ("8.60", Dimensao.MASSA, Confianca.ALTA),
    "Macarrão espaguete": ("13.99", Dimensao.MASSA, Confianca.ALTA),
    "Polenta (fubá)": ("10.00", Dimensao.MASSA, Confianca.ALTA),
    "Batata": ("6.00", Dimensao.MASSA, Confianca.ALTA),
    "Queijo mussarela": ("40.00", Dimensao.MASSA, Confianca.ALTA),
    "Queijo parmesão ralado": ("42.90", Dimensao.MASSA, Confianca.ALTA),
    "Tomate": ("8.00", Dimensao.MASSA, Confianca.ALTA),
    "Cebola": ("4.00", Dimensao.MASSA, Confianca.ALTA),
    "Alho": ("20.00", Dimensao.MASSA, Confianca.ALTA),
    "Óleo de soja": ("9.00", Dimensao.VOLUME, Confianca.ALTA),
    "Manteiga": ("40.00", Dimensao.MASSA, Confianca.ALTA),
    "Sal": ("1.85", Dimensao.MASSA, Confianca.ALTA),
    "Açúcar": ("4.28", Dimensao.MASSA, Confianca.ALTA),
    "Leite integral": ("5.00", Dimensao.VOLUME, Confianca.ALTA),
    "Couve": ("12.00", Dimensao.MASSA, Confianca.ALTA),
    "Salsinha (cheiro-verde)": ("21.00", Dimensao.MASSA, Confianca.ALTA),
    "Caldo de carne (tempero)": ("7.10", Dimensao.MASSA, Confianca.ALTA),
    "Açafrão em pó (cúrcuma)": ("10.80", Dimensao.MASSA, Confianca.ALTA),
    "Alcaparras": ("41.00", Dimensao.MASSA, Confianca.MEDIA),  # armadilha: balde 2kg
    "Amêndoa fatiada": ("60.00", Dimensao.MASSA, Confianca.ALTA),
    "Chantilly": ("47.34", Dimensao.MASSA, Confianca.MEDIA),  # armadilha: un 500g
    "Leite ninho em pó": ("37.95", Dimensao.MASSA, Confianca.MEDIA),  # armadilha: un 400g
    # Indedutível pela planilha: o peso vem estimado pela página do supermercado.
    "Cobertura de chocolate": ("79.90", Dimensao.MASSA, Confianca.MEDIA),
    "Azeite de oliva extra virgem": ("61.98", Dimensao.VOLUME, Confianca.MEDIA),  # un 500ml
    "Aceto balsâmico": ("25.98", Dimensao.VOLUME, Confianca.MEDIA),  # armadilha: un 500ml
    "Canela em pó": ("18.30", Dimensao.MASSA, Confianca.ALTA),
    "Adoçante líquido": ("19.00", Dimensao.VOLUME, Confianca.MEDIA),  # armadilha: un 100ml
}

#: Onde o cálculo ingênuo diverge do correto. nome -> (ingênuo, correto, fator).
ARMADILHAS: dict[str, tuple[str, str]] = {
    "Alcaparras": ("82.00", "41.00"),
    "Chantilly": ("23.67", "47.34"),
    "Leite ninho em pó": ("15.18", "37.95"),
    "Azeite de oliva extra virgem": ("30.99", "61.98"),
    "Aceto balsâmico": ("12.99", "25.98"),
    "Adoçante líquido": ("1.90", "19.00"),
}


def test_carrega_os_37_ingredientes(despensa: Despensa) -> None:
    assert len(despensa) == 37
    assert set(despensa.nomes) == set(CUSTOS_ESPERADOS)


def test_total_investido(despensa: Despensa) -> None:
    assert despensa.total_investido == Dinheiro.de("663.39")


@pytest.mark.parametrize(("nome", "esperado"), CUSTOS_ESPERADOS.items(), ids=CUSTOS_ESPERADOS)
def test_custo_unitario(
    despensa: Despensa, nome: str, esperado: tuple[str, Dimensao, Confianca]
) -> None:
    valor, dimensao, confianca = esperado
    item = despensa[nome]
    assert item.custo.valor.arredondado() == Dinheiro.de(valor), item.custo.derivacao
    assert item.custo.dimensao is dimensao
    assert item.custo.confianca is confianca


@pytest.mark.parametrize(("nome", "valores"), ARMADILHAS.items(), ids=ARMADILHAS)
def test_armadilha_de_normalizacao(despensa: Despensa, nome: str, valores: tuple[str, str]) -> None:
    """O cálculo ingênuo e o correto realmente divergem, e ficamos com o correto."""
    ingenuo, correto = Dinheiro.de(valores[0]), Dinheiro.de(valores[1])
    item = despensa[nome]

    assert item.custo_ingenuo.arredondado() == ingenuo, "a conta ingênua mudou"
    assert item.custo.valor.arredondado() == correto, item.custo.derivacao
    assert item.normalizacao_importou, "este item deveria divergir"
    assert item.custo.confianca is Confianca.MEDIA


def test_apenas_seis_itens_exigem_normalizacao(despensa: Despensa) -> None:
    """Nos outros 31, ingênuo e correto coincidem, e é isso que torna o bug sutil."""
    divergentes = {i.nome for i in despensa if i.normalizacao_importou}
    assert divergentes == set(ARMADILHAS)


def test_toda_derivacao_e_auditavel(despensa: Despensa) -> None:
    """Nenhum custo aparece sem a conta que o produziu."""
    for item in despensa:
        assert item.custo.derivacao, f"{item.nome} sem derivação"
        assert "÷" in item.custo.derivacao


def test_o_item_indedutivel_vira_estimativa_com_fonte(despensa: Despensa) -> None:
    """A planilha tem exatamente um item indedutível, e ele não vira pergunta.

    O peso da cobertura de chocolate vem da página do supermercado (a embalagem
    de preço mais perto dos R$ 79,90), dito como estimativa e com a fonte.
    """
    assert despensa.pendencias == []
    estimados = [i.nome for i in despensa if i.embalagem_estimada is not None]
    assert estimados == ["Cobertura de chocolate"]
    derivacao = despensa["Cobertura de chocolate"].custo.derivacao
    assert "estimativa" in derivacao
    assert "R$ 79,90" in derivacao
    assert "a senhora pode corrigir" in derivacao


def test_ovos_continuam_contados_e_nao_viram_massa(despensa: Despensa) -> None:
    """30 ovos a R$ 24,00 é contagem legítima, não embalagem opaca."""
    ovos = despensa["Ovos"]
    assert ovos.dimensao is Dimensao.CONTAGEM
    assert not ovos.embalagem_opaca
    assert ovos.custo.confianca is Confianca.ALTA


def test_cobertura_e_embalagem_com_o_peso_estimado(despensa: Despensa) -> None:
    """Uma peça só de unidade opaca: é embalagem, e o peso vem estimado, com a fonte."""
    cobertura = despensa["Cobertura de chocolate"]
    assert not cobertura.embalagem_opaca
    assert cobertura.embalagem_estimada is not None
    assert cobertura.custo.confianca is Confianca.MEDIA


def test_estoque_igual_ao_comprado(despensa: Despensa) -> None:
    """Ela ainda não cozinhou nada: as duas abas batem item a item."""
    for item in despensa:
        assert item.estoque.valor == item.comprado.valor, item.nome


def test_capital_concentrado_nos_dois_itens_gourmet(despensa: Despensa) -> None:
    """Alcaparras e cobertura sozinhas são ~24% do capital: insight de negócio."""
    top2 = despensa.por_valor()[:2]
    assert [i.nome for i in top2] == ["Alcaparras", "Cobertura de chocolate"]
    soma = top2[0].preco_pago + top2[1].preco_pago
    fracao = soma.valor / despensa.total_investido.valor
    assert Decimal("0.24") < fracao < Decimal("0.25")


def test_sem_mudanca_dela_a_despensa_da_sessao_e_a_da_planilha(
    despensa: Despensa, tmp_path: Path
) -> None:
    """A despensa editável sem evento nenhum: os mesmos 37 itens, as mesmas contas."""
    from mise.mcp_server import abrir_sessao

    sessao = abrir_sessao(planilha=PLANILHA, banco=tmp_path / "dossie.db")
    try:
        agora = sessao.despensa
        assert agora is sessao.planilha
        assert agora.total_investido == Dinheiro.de("663.39")
        assert [
            (i.nome, i.custo.valor, i.custo.derivacao, i.custo.confianca, i.estoque) for i in agora
        ] == [
            (i.nome, i.custo.valor, i.custo.derivacao, i.custo.confianca, i.estoque)
            for i in despensa
        ]
        assert [p.pergunta for p in agora.pendencias] == [p.pergunta for p in despensa.pendencias]
    finally:
        sessao.dossie.fechar()
