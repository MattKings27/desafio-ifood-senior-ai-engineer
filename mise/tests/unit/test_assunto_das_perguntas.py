"""Cada pergunta diz do que trata, para a tela não precisar ler o texto."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from mise.despensa import OrigemDoItem
from mise.dossie import Canal
from mise.mcp_server import Sessao, abrir_sessao
from mise.passos import perguntas_com_opcoes
from mise.receita import Receita, ingrediente, receita
from mise.viabilidade import AssuntoDaPergunta, Pergunta, TipoRestricao, assunto_da

PLANILHA = Path(__file__).resolve().parents[3] / "dados" / "despensa_dona_maria.xlsx"
PANELA = ["Refogue tudo na panela por 20 minutos."]

#: À Dona Maria só se pergunta gosto, equipamento, técnica e limite da rotina.
PROIBIDOS = frozenset(
    {
        "linha_nao_lida",
        "preco_de_compra",
        "preco_da_despensa",
        "peso_da_embalagem",
        "medida",
        "mesmo_ingrediente",
        "ingrediente",
        "tempo_cozimento",
    }
)


@pytest.fixture
def sessao(tmp_path: Path) -> Sessao:
    return abrir_sessao(planilha=PLANILHA, banco=tmp_path / "dossie.db")


def _assuntos(sessao: Sessao, feita: Receita) -> dict[str, dict[str, object]]:
    perguntas = perguntas_com_opcoes(sessao.avaliar(feita).perguntas)
    return {p["assunto"]: p for p in perguntas}


def test_a_linha_que_a_leitura_nao_entendeu(sessao: Sessao) -> None:
    feita = receita(
        "Arroz temperado",
        [
            ingrediente("1 kg de arroz", "arroz", 1, "kg"),
            ingrediente(
                "temperos de sua preferência", "temperos de sua preferência", entendida=False
            ),
        ],
        rendimento_porcoes=4,
        modo_preparo=PANELA,
    )
    # O tempero que a receita não diz qual é vai a gosto: nunca vira pergunta.
    assert not set(_assuntos(sessao, feita)) & PROIBIDOS


def test_o_preco_do_que_falta_comprar_traz_quanto_falta(sessao: Sessao) -> None:
    feita = receita(
        "Bolo de coco",
        [
            ingrediente("2 xícaras de farinha de trigo", "farinha de trigo", 2, "xícara"),
            ingrediente("1 xícara de coco ralado", "coco ralado", 1, "xícara"),
        ],
        rendimento_porcoes=8,
        modo_preparo=["Misture tudo e asse no forno por 40 minutos."],
    )
    # A xícara de coco ralado vira gramas pela tabela do USDA, e o preço de referência cota.
    assert not set(_assuntos(sessao, feita)) & PROIBIDOS


@pytest.mark.parametrize(
    ("linha", "texto"),
    [
        (
            ingrediente("2 colheres de sopa de alcaparras", "alcaparras", 2, "colher de sopa"),
            "Não sei quanto pesa uma colher de sopa de alcaparras. Se a senhora souber, "
            "em gramas, eu calculo.",
        ),
        (
            ingrediente("1 bife de alcatra", "alcatra", 1, ""),
            "Não sei quanto pesa um miolo de alcatra. Se a senhora souber, em gramas, eu calculo.",
        ),
    ],
)
def test_a_medida_que_nao_se_converte_pergunta_como_gente(
    sessao: Sessao, linha: object, texto: str
) -> None:
    """Nada de "densidade", "unidade ''" nem aspas: o texto e o motivo aparecem na tela."""
    feita = receita("Frango com alcaparras", [linha], rendimento_porcoes=4, modo_preparo=PANELA)
    # O peso vem de uma fonte, ou a receita fica de fora: nunca vira pergunta.
    del texto
    assert not set(_assuntos(sessao, feita)) & PROIBIDOS


def test_o_peso_da_embalagem_que_ela_nao_disse(sessao: Sessao) -> None:
    feita = receita(
        "Brigadeiro de colher",
        [ingrediente("200 g de cobertura de chocolate", "cobertura de chocolate", 200, "g")],
        rendimento_porcoes=4,
        modo_preparo=PANELA,
    )
    # O peso da embalagem vem estimado pela página do supermercado, com a fonte.
    assert not set(_assuntos(sessao, feita)) & PROIBIDOS


def test_o_preco_que_ela_nao_disse_de_um_item_da_despensa(sessao: Sessao) -> None:
    sessao.editavel.adicionar(
        nome="Linguiça calabresa",
        estoque=Decimal(1),
        unidade="kg",
        origem=OrigemDoItem.JA_TINHA,
        canal=Canal.TELA,
    )
    feita = receita(
        "Linguiça acebolada",
        [ingrediente("500 g de linguiça calabresa", "linguiça calabresa", 500, "g")],
        rendimento_porcoes=4,
        modo_preparo=PANELA,
    )
    # O preço que ela não disse vem do preço de referência, dito como referência.
    assert not set(_assuntos(sessao, feita)) & PROIBIDOS


def test_o_que_a_propria_receita_nao_diz(sessao: Sessao) -> None:
    sem_rendimento = Receita(
        nome="Farofa simples",
        ingredientes=(
            ingrediente("200 g de farinha de mandioca", "farinha de mandioca", 200, "g"),
        ),
        modo_preparo=("Toste a farinha na panela.",),
        rendimento_informado=False,
    ).com_exigencias_detectadas()
    # O rendimento nunca é pergunta: sem ele na receita, a plataforma estima pelo
    # peso dos ingredientes e pelo peso de uma porção, e ela pode mudar.
    avaliacao = sessao.avaliar(sem_rendimento)
    assert "rendimento" not in _assuntos(sessao, sem_rendimento)
    assert avaliacao.rendimento is not None
    assert avaliacao.rendimento.estimado
    assert avaliacao.rendimento.porcoes == 1
    assert avaliacao.rendimento.texto == (
        "cerca de 1 porção (estimativa: porções de 350 g; a senhora pode mudar)"
    )
    sem_preparo = receita(
        "Salada", [ingrediente("2 tomates", "tomate", 2, "unidade")], rendimento_porcoes=2
    )
    assert "modo_preparo" in _assuntos(sessao, sem_preparo)


@pytest.mark.parametrize(
    ("tipo", "campo", "assunto"),
    [
        (TipoRestricao.EQUIPAMENTO, "forno", AssuntoDaPergunta.EQUIPAMENTO),
        (TipoRestricao.EQUIPAMENTO, "modo_preparo", AssuntoDaPergunta.MODO_PREPARO),
        (TipoRestricao.TECNICA, "fritar", AssuntoDaPergunta.TECNICA),
        (TipoRestricao.GOSTO, "gosto", AssuntoDaPergunta.GOSTO),
        (TipoRestricao.OPERACIONAL, "rendimento_porcoes", AssuntoDaPergunta.RENDIMENTO),
        (TipoRestricao.OPERACIONAL, "tempo_cozimento_min", AssuntoDaPergunta.TEMPO_COZIMENTO),
        (TipoRestricao.OPERACIONAL, "bocas_fogao", AssuntoDaPergunta.ROTINA),
        (TipoRestricao.INGREDIENTE, "sal", AssuntoDaPergunta.INGREDIENTE),
    ],
)
def test_sem_assunto_dito_ele_sai_do_tipo_e_do_campo(
    tipo: TipoRestricao, campo: str, assunto: AssuntoDaPergunta
) -> None:
    assert assunto_da(Pergunta(tipo, campo, "?")) is assunto
    dita = Pergunta(tipo, campo, "?", assunto=AssuntoDaPergunta.MEDIDA)
    assert assunto_da(dita) is AssuntoDaPergunta.MEDIDA
