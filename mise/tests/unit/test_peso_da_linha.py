"""O peso que ela diz de uma linha cuja medida não se converte destrava o custo do prato.

Verificação real: "Frango com alcaparras" pedia "1 peito cortado em 4 filés" e
"2 colheres de sopa de alcaparras". A conferência perguntava quanto pesa um
peito e quanto pesa uma colher de alcaparras, ela respondia, e não havia onde
gravar: o prato nunca tinha custo. Agora a resposta vale pela tela
(`responder_sobre_a_receita`, com `por_unidade`) e pela conversa
(`avaliar_receita` com o `receita_id` e a linha com `peso`), fica anotada como
dita por ela e entra na conta. Nunca no lugar de uma medida que se converte, e
nunca sem um número dela.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
import receitas_de_teste as rt

from mise.catalogo import ReceitaDoCatalogo
from mise.cmv import calcular
from mise.complemento import PESO_DITO, ler_peso, responder_peso
from mise.erros import ErroDeUso
from mise.mcp_server import ReceitaEntrada, Sessao
from mise.passos import perguntas_com_opcoes
from mise.perfil import Gosto
from mise.receita import IngredienteReceita, Receita, ingrediente, receita
from mise.receitas_json import detalhe, guardada_por_slug, respostas_json

URL = "https://www.tudogostoso.com.br/receita/33527-frango-com-alcaparras.html"
PEITO = "1 peito cortado em 4 filés"
ALCAPARRAS = "2 colheres de sopa de alcaparras"
PAGINA = rt.pagina(
    "Frango com alcaparras",
    [PEITO, ALCAPARRAS, "sal a gosto"],
    ["Tempere os filés com sal.", "Grelhe na frigideira por 10 minutos e junte as alcaparras."],
    rende="2 porções",
)


@pytest.fixture
def sessao(tmp_path: Path) -> Sessao:
    sessao = rt.sessao_nova(tmp_path)
    rt.cozinha_confirmada(sessao)
    sessao.dossie.registrar_gosto("Frango com alcaparras", Gosto.GOSTA)
    return sessao


def _perguntas(sessao: Sessao, guardada: ReceitaDoCatalogo) -> dict[str, dict[str, object]]:
    receita_agora = sessao.catalogo.obter(guardada.slug)
    assert receita_agora is not None
    perguntas = perguntas_com_opcoes(sessao.avaliar(receita_agora.receita).perguntas)
    return {str(p["campo"]): p for p in perguntas if p["assunto"] == "medida"}


# --------------------------------------------------------------------------- #
# Ler o peso                                                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("resposta", "gramas", "de_cada"),
    [
        ("300 g", "300", None),
        ("300g", "300", None),
        ("300 gramas", "300", None),
        ("0,3 kg", "300", None),
        ("0.3 kg", "300", None),
        ("1,5 quilo", "1500", None),
        ("1/2 kg", "500", None),
        ("1.500 g", "1500", None),
        ("300", "300", None),
        ("Um peito pesa uns 300 gramas", "300", None),
        ("uns 300 gramas cada", "300", True),
        ("10 gramas cada colher", "10", True),
        ("20 g as duas colheres", "20", False),
        ("duas colheres dão uns 20 gramas", "20", False),
        ("2 colheres dão 20", "20", False),
        ("1 colher dá 10 g", "10", None),
    ],
)
def test_le_o_peso_como_ela_diz(resposta: str, gramas: str, de_cada: bool | None) -> None:
    assert ler_peso(resposta) == (Decimal(gramas), de_cada)


@pytest.mark.parametrize(
    ("resposta", "recado"),
    [
        ("não sei", "preciso de um número"),
        ("uns trezentos gramas", "preciso de um número"),
        ("300 ou 350", "preciso de um número"),
        ("1/0 kg", "preciso de um número"),
        ("200 ml", "gramas ou em quilos"),
    ],
)
def test_sem_um_peso_dela_nao_ha_peso(resposta: str, recado: str) -> None:
    """Peso não se adivinha: sem número, ou com o número em outra medida, é recusa."""
    with pytest.raises(ErroDeUso, match=recado):
        ler_peso(resposta)


# --------------------------------------------------------------------------- #
# Guardar o peso na linha                                                      #
# --------------------------------------------------------------------------- #


def _alcaparras() -> Receita:
    return receita(
        "Frango com alcaparras",
        [ingrediente(ALCAPARRAS, "alcaparras", 2, "colher de sopa")],
        rendimento_porcoes=2,
    )


@pytest.mark.parametrize(
    ("resposta", "por_unidade", "peso_g", "dito"),
    [
        ("10 g", None, "20", "uma colher de sopa de alcaparras pesa 10 g"),
        ("10 gramas cada", None, "20", "uma colher de sopa de alcaparras pesa 10 g"),
        ("20 g", False, "20", f"“{ALCAPARRAS}” pesam 20 g"),
        ("20 g as duas colheres", None, "20", f"“{ALCAPARRAS}” pesam 20 g"),
        ("20 g as duas", True, "40", "uma colher de sopa de alcaparras pesa 20 g"),
        ("0,01 kg", None, "20", "uma colher de sopa de alcaparras pesa 10 g"),
    ],
)
def test_a_linha_guarda_o_peso_inteiro_e_a_resposta_como_ela_disse(
    resposta: str, por_unidade: bool | None, peso_g: str, dito: str
) -> None:
    feito = responder_peso(
        _alcaparras(),
        ALCAPARRAS,
        resposta,
        uma="uma colher de sopa de alcaparras",
        por_unidade=por_unidade,
    )
    (linha,) = feito.receita.ingredientes
    assert linha.peso_g == Decimal(peso_g)
    assert (linha.quantidade, linha.medida) == (Decimal(2), "colher de sopa"), "a linha não muda"
    assert feito.respostas == ((ALCAPARRAS, f"{PESO_DITO}{dito}"),)


def test_peso_fora_da_faixa_e_linha_que_nao_existe_sao_recusados() -> None:
    with pytest.raises(ErroDeUso, match="50 kg"):
        responder_peso(_alcaparras(), ALCAPARRAS, "30 kg cada", uma="uma colher")
    with pytest.raises(ErroDeUso, match="não está na receita"):
        responder_peso(_alcaparras(), "1 kg de arroz", "300 g", uma="um arroz")


def test_o_peso_vai_e_volta_do_catalogo_e_se_divide_por_porcao() -> None:
    feita = _alcaparras()
    com_peso = Receita.de_dict(
        {
            **feita.para_dict(),
            "ingredientes": [{**feita.para_dict()["ingredientes"][0], "peso_g": "20"}],
        }
    )
    (linha,) = com_peso.ingredientes
    assert linha.peso_g == Decimal(20)
    assert com_peso.para_dict()["ingredientes"][0]["peso_g"] == "20"
    assert "peso_g" not in feita.para_dict()["ingredientes"][0], "sem resposta, nada muda"
    (uma,) = com_peso.por_porcao().ingredientes
    assert (uma.quantidade, uma.peso_g) == (Decimal(1), Decimal(10))
    with pytest.raises(ErroDeUso):
        IngredienteReceita(
            ALCAPARRAS, "alcaparras", Decimal(2), "colher de sopa", peso_g=Decimal(0)
        )


# --------------------------------------------------------------------------- #
# A pergunta, a tela e a conversa                                              #
# --------------------------------------------------------------------------- #


def test_a_pergunta_de_medida_diz_a_linha_e_pede_o_peso(sessao: Sessao) -> None:
    """Nada pergunta: o peito pela tabela do IBGE, a colher de alcaparras pela do USDA.

    Os dois pesos vêm com a fonte, e ela corrige se quiser.
    """
    frango = rt.da_web(sessao, URL, PAGINA)
    perguntas = _perguntas(sessao, frango)
    assert PEITO not in perguntas
    peito = next(i for i in detalhe(sessao, frango.slug)["ingredientes"] if i["situacao"] == "tem")
    referencia = peito["medida_de_referencia"]
    assert referencia["texto"] == (
        "Um peito de frango pesa cerca de 180 g, pela referência de medidas do IBGE; "
        "a senhora pode corrigir"
    )
    assert referencia["url"].startswith("https://ftp.ibge.gov.br/")
    assert referencia["pergunta"]["campo"] == PEITO
    assert referencia["pergunta"]["entrada"] == {"tipo": "peso", "unidade": "g", "peso_de": None}
    assert ALCAPARRAS not in perguntas
    alcaparras = next(
        i for i in detalhe(sessao, frango.slug)["ingredientes"] if i["nome"] == "Alcaparras"
    )
    assert alcaparras["medida_de_referencia"]["texto"] == (
        "Uma colher de sopa de alcaparras pesa cerca de 8,6 g, pela referência de medidas "
        "do USDA; a senhora pode corrigir"
    )
    assert alcaparras["medida_de_referencia"]["pergunta"]["entrada"] == {
        "tipo": "peso",
        "unidade": "g",
        "peso_de": {"cada": "1 colher de sopa", "tudo": "2 colheres de sopa"},
    }


def test_o_peso_pela_tela_destrava_o_custo(sessao: Sessao) -> None:
    frango = rt.da_web(sessao, URL, PAGINA)
    sessao.responder_sobre_a_receita(frango.slug, PEITO, "300")
    assert _perguntas(sessao, frango) == {}, "peso não é pergunta: o dela corrige a referência"
    feita = sessao.responder_sobre_a_receita(frango.slug, ALCAPARRAS, "20", por_unidade=False)
    assert _perguntas(sessao, frango) == {}

    avaliacao = sessao.avaliar(feita.receita)
    assert avaliacao.permite_precificar, avaliacao.perguntas
    cmv = calcular(feita.receita, avaliacao)
    # 300 g × R$ 14,00/kg + 20 g × R$ 41,00/kg = R$ 5,02, e a receita rende 2 porções.
    assert str(cmv.para_precificar) == "R$ 2,51"
    (peito,) = [linha for linha in cmv.linhas if linha.ingrediente == "Peito de frango"]
    assert peito.derivacao.startswith("1 peito = 300 g (a senhora disse) × R$ 14,00/kg")

    guardada = guardada_por_slug(sessao, frango.slug)
    ditos = [
        r["texto"] for r in respostas_json(guardada, guardada.atualizada_em or guardada.criada_em)
    ]
    assert ditos == [
        "A senhora disse que um peito de frango pesa 300 g.",
        f"A senhora disse que “{ALCAPARRAS}” pesam 20 g.",
    ]
    precisa = {
        i["nome"]: i["precisa"]["texto"] for i in detalhe(sessao, frango.slug)["ingredientes"]
    }
    assert precisa["Peito de frango"] == "1 unidade (300 g)"
    assert precisa["Alcaparras"] == "2 colheres de sopa (20 g)"


def test_o_peso_pela_conversa_vai_com_o_receita_id(sessao: Sessao) -> None:
    frango = rt.da_web(sessao, URL, PAGINA)
    resposta = ReceitaEntrada.model_validate(
        {
            "nome": "Frango com alcaparras",
            "ingredientes": [
                {"texto": PEITO, "nome": "peito", "peso": "uns 300 gramas"},
                {"texto": ALCAPARRAS, "nome": "alcaparras", "peso": "10 g", "por_unidade": True},
            ],
        }
    )
    feita, recado = sessao.receita_para_avaliar(frango.slug, resposta)
    assert recado == (
        "anotei na receita o que ela respondeu (peso: um peito de frango pesa 300 g; "
        "peso: uma colher de sopa de alcaparras pesa 10 g)"
    )
    assert [i.peso_g for i in feita.ingredientes] == [Decimal(300), Decimal(20), None]
    assert sessao.avaliar(feita).permite_precificar

    sem_id = ReceitaEntrada.model_validate(
        {
            "nome": "Outro frango",
            "ingredientes": [{"texto": PEITO, "nome": "peito", "peso": "300 g"}],
        }
    )
    with pytest.raises(ErroDeUso, match="vai com o receita_id"):
        sessao.receita_para_avaliar(None, sem_id)


def test_o_peso_e_o_rendimento_na_mesma_resposta(sessao: Sessao) -> None:
    sem_rendimento = rt.pagina(
        "Frango com alcaparras", [PEITO, "sal a gosto"], ["Grelhe na frigideira."], rende=""
    )
    frango = rt.da_web(sessao, URL, sem_rendimento)
    resposta = ReceitaEntrada.model_validate(
        {
            "nome": "Frango com alcaparras",
            "rendimento_porcoes": 2,
            "ingredientes": [{"texto": PEITO, "nome": "peito", "peso": "300 g"}],
        }
    )
    feita, recado = sessao.receita_para_avaliar(frango.slug, resposta)
    assert (feita.rendimento_porcoes, feita.ingredientes[0].peso_g) == (2, Decimal(300))
    assert recado == (
        "anotei na receita o que ela respondeu (peso: um peito de frango pesa 300 g; "
        "rendimento_porcoes: 2 porções)"
    )


def test_o_peso_nunca_troca_uma_medida_que_se_converte(sessao: Sessao) -> None:
    frango = rt.da_web(
        sessao,
        "https://www.tudogostoso.com.br/receita/9-frango-grelhado.html",
        rt.pagina("Frango grelhado", ["500 g de peito de frango", "sal a gosto"], ["Grelhe."]),
    )
    with pytest.raises(ErroDeUso, match="não pede peso"):
        sessao.responder_sobre_a_receita(
            frango.slug, "500 g de peito de frango", "300 g", por_unidade=True
        )
    with pytest.raises(ErroDeUso, match="já diz quanto vai"):
        sessao.responder_sobre_a_receita(frango.slug, "500 g de peito de frango", "300 g")
    pela_conversa = ReceitaEntrada.model_validate(
        {
            "nome": "Frango grelhado",
            "ingredientes": [{"texto": "500 g de peito de frango", "nome": "x", "peso": "300 g"}],
        }
    )
    with pytest.raises(ErroDeUso, match="não pede peso"):
        sessao.receita_para_avaliar(frango.slug, pela_conversa)

    # Nem um peso escrito à mão na linha muda a conta: 500 g continuam 500 g.
    (linha, sal) = frango.receita.ingredientes
    com_peso = Receita(
        nome="Frango grelhado",
        ingredientes=(replace(linha, peso_g=Decimal(300)), sal),
        modo_preparo=("Grelhe.",),
    )
    (uso,) = sessao.avaliar(com_peso).usos
    assert uso.quantidade.valor == Decimal("0.5")


def test_ela_pode_corrigir_o_peso_que_disse(sessao: Sessao) -> None:
    frango = rt.da_web(sessao, URL, PAGINA)
    sessao.responder_sobre_a_receita(frango.slug, PEITO, "3000 g")
    corrigida = sessao.responder_sobre_a_receita(frango.slug, PEITO, "300 g")
    (peito, *_) = corrigida.receita.ingredientes
    assert peito.peso_g == Decimal(300)
    with pytest.raises(ErroDeUso, match="preciso de um número"):
        sessao.responder_sobre_a_receita(frango.slug, PEITO, "não sei")


def test_ditada_de_novo_a_linha_que_nao_mudou_guarda_o_peso(sessao: Sessao) -> None:
    ditada = rt.ditada(
        sessao,
        nome="Frango da Maria",
        rendimento_porcoes=2,
        modo_preparo=["Grelhe na frigideira por 10 minutos."],
        ingredientes=[{"texto": "1 peito de frango", "nome": "peito de frango"}],
    )
    # A tabela do IBGE diz o peso do peito; o que ela disser vale mais.
    assert list(_perguntas(sessao, ditada)) == []
    sessao.responder_sobre_a_receita(ditada.slug, "1 peito de frango", "300 g")
    de_novo = ReceitaEntrada.model_validate(
        {
            "nome": "Frango da Maria",
            "rendimento_porcoes": 3,
            "modo_preparo": ["Grelhe na frigideira por 10 minutos."],
            "ingredientes": [{"texto": "1 peito de frango", "nome": "peito de frango"}],
        }
    )
    feita, _ = sessao.receita_para_avaliar(ditada.slug, de_novo)
    (peito,) = feita.ingredientes
    assert (feita.rendimento_porcoes, peito.peso_g) == (3, Decimal(300))
