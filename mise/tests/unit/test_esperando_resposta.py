"""Com a cozinha nova, "nada dá para fazer" é mentira: a verdade é "ainda não confirmei".

Depois da primeira descoberta, toda receita espera uma resposta dela, e a aba
"Dá para fazer" fica vazia. A tela e o agente diziam isso como se nada
fosse possível. Estes testes guardam a conta que separa, pela despensa, as
receitas que usam só o que ela tem (e esperam só o que ela responder) das que
pedem compra, com a frase pronta, a mesma na grade e na conversa.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import receitas_de_teste as rt

from mise.mcp_server import Sessao
from mise.receitas_json import (
    LINHA_SEM_LEITURA,
    PRECISA_COMPRAR,
    SO_COM_O_QUE_TEM,
    Filtros,
    catalogo_para_a_consultora,
    espera_da_receita,
    guardadas,
    ler,
    lista,
)

FRANGO_ACEBOLADO = rt.pagina(
    "Frango acebolado",
    ["500 g de peito de frango", "2 cebolas", "3 dentes de alho", "Sal", "Azeite"],
    ["Tempere o frango.", "Frite o frango na frigideira por 20 minutos."],
)
FEIJAO_NA_PRESSAO = rt.pagina(
    "Feijão na pressão",
    ["500 g de feijão carioca", "1 cebola", "Sal e pimenta-do-reino"],
    ["Cozinhe o feijão na panela de pressão por 30 minutos."],
)
FEIJAO_COM_LOURO = rt.pagina(
    "Feijão com louro e cominho",
    ["500 g de feijão carioca", "2 colheres de chá de cominho", "1 cebola"],
    ["Cozinhe o feijão na panela por 40 minutos."],
)
ARROZ_COM_MILHO = rt.pagina(
    "Arroz com milho",
    ["1 xícara de arroz", "Milho"],
    ["Cozinhe o arroz na panela por 20 minutos."],
)


@pytest.fixture
def sessao(tmp_path: Path) -> Sessao:
    """A cozinha nova: nada confirmado, quatro receitas trazidas da internet."""
    sessao = rt.sessao_nova(tmp_path)
    rt.da_web(sessao, "https://www.tudogostoso.com.br/receita/1-frango.html", FRANGO_ACEBOLADO)
    rt.da_web(sessao, "https://www.tudogostoso.com.br/receita/2-feijao.html", FEIJAO_NA_PRESSAO)
    rt.da_web(sessao, "https://www.tudogostoso.com.br/receita/3-feijao.html", FEIJAO_COM_LOURO)
    rt.da_web(sessao, "https://www.tudogostoso.com.br/receita/4-arroz.html", ARROZ_COM_MILHO)
    return sessao


def test_cada_receita_que_espera_fica_num_grupo_so(sessao: Sessao) -> None:
    esperas = {le.nome: espera_da_receita(le) for le in ler(sessao, guardadas(sessao))}
    assert esperas == {
        "Frango acebolado": SO_COM_O_QUE_TEM,
        "Feijão na pressão": SO_COM_O_QUE_TEM,
        "Feijão com louro e cominho": PRECISA_COMPRAR,
        # "Milho" sem quantidade: a lata de 170 g da página do produto, e a compra.
        "Arroz com milho": PRECISA_COMPRAR,
    }
    assert LINHA_SEM_LEITURA == "linha_sem_leitura"


def test_a_grade_diz_quantas_usam_so_o_que_ela_tem_e_o_que_falta_ela_dizer(
    sessao: Sessao,
) -> None:
    resposta = lista(sessao, Filtros(aba="pode_fazer"))
    assert resposta["contagens"]["pode_fazer"] == 0
    assert resposta["contagens"]["falta_resposta"] == 4
    espera = resposta["esperando_resposta"]
    assert espera["receitas"] == 4
    assert (espera["so_com_o_que_tem"], espera["precisa_comprar"]) == (2, 2)
    assert espera["linha_sem_leitura"] == 0
    assert sorted(espera["nomes"]) == ["Feijão na pressão", "Frango acebolado"]
    assert len(espera["slugs"]) == len(espera["nomes"])
    assert espera["falta_dizer"] == [
        "quanto tempo consegue ficar cozinhando de uma vez",
        "se tem panela de pressão",
    ]
    assert espera["texto"] == (
        "2 receitas usam só o que a senhora tem; falta só a senhora me dizer quanto tempo "
        "consegue ficar cozinhando de uma vez e se tem panela de pressão. 2 receitas pedem "
        "alguma compra."
    )


def test_cada_pergunta_diz_quantas_das_suas_receitas_nao_pedem_compra(sessao: Sessao) -> None:
    painel = lista(sessao, Filtros(aba="falta_resposta"))["perguntas_que_liberam"]
    tempo = next(p for p in painel if p["pergunta"]["campo"] == "tempo_max_por_fornada_min")
    assert (tempo["receitas"], tempo["sem_compra"]) == (4, 2)
    assert tempo["sem_compra_texto"] == "2 delas usam só o que a senhora tem"
    pressao = next(p for p in painel if p["pergunta"]["campo"] == "panela_pressao")
    assert (pressao["receitas"], pressao["sem_compra"]) == (1, 1)
    assert pressao["sem_compra_texto"] == "usa só o que a senhora tem"
    # O preço do cominho vem da referência, e nunca vira pergunta no painel.
    assert {p["pergunta"]["assunto"] for p in painel} <= {"equipamento", "tecnica", "rotina"}


def test_sem_nenhuma_so_com_o_que_tem_a_frase_diz_a_verdade(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    rt.da_web(sessao, "https://www.tudogostoso.com.br/receita/3-feijao.html", FEIJAO_COM_LOURO)
    espera = lista(sessao, Filtros())["esperando_resposta"]
    assert espera["so_com_o_que_tem"] == 0
    assert espera["texto"] == "A receita que espera resposta pede alguma compra."
    rt.da_web(
        sessao,
        "https://www.tudogostoso.com.br/receita/5-feijao.html",
        rt.pagina(
            "Feijão com páprica",
            ["500 g de feijão carioca", "1 colher de chá de páprica defumada"],
            ["Cozinhe o feijão na panela por 40 minutos."],
        ),
    )
    espera = lista(sessao, Filtros())["esperando_resposta"]
    assert espera["texto"] == (
        "Nenhuma das 2 receitas que esperam resposta usa só o que a senhora tem: todas "
        "pedem alguma compra."
    )


def test_sem_receita_esperando_o_bloco_vem_nulo(tmp_path: Path) -> None:
    assert lista(rt.sessao_nova(tmp_path), Filtros())["esperando_resposta"] is None


def test_a_consultora_recebe_o_catalogo_separado_como_na_tela(sessao: Sessao) -> None:
    """ "O que eu consigo fazer?" sai daqui, e não de palpite: as mesmas contas da grade."""
    catalogo = catalogo_para_a_consultora(sessao)
    assert catalogo["da_para_fazer"] == []
    assert {r["prato"] for r in catalogo["usa_so_o_que_tem"]} == {
        "Frango acebolado",
        "Feijão na pressão",
    }
    feijao = next(r for r in catalogo["usa_so_o_que_tem"] if r["prato"] == "Feijão na pressão")
    assert "falta_comprar" not in feijao
    assert any("panela de pressão" in p for p in feijao["falta_responder"])
    compras = {r["prato"]: r["falta_comprar"] for r in catalogo["precisa_comprar"]}
    assert compras == {"Feijão com louro e cominho": ["cominho"], "Arroz com milho": ["Milho"]}
    assert catalogo["linha_sem_leitura"] == []
    assert catalogo["texto"] == lista(sessao, Filtros())["esperando_resposta"]["texto"]
    assert catalogo == sessao.comparar()["catalogo"]


def test_o_que_ela_confirmou_na_cozinha_libera_a_receita(sessao: Sessao) -> None:
    rt.cozinha_confirmada(sessao)
    catalogo = catalogo_para_a_consultora(sessao)
    assert "Frango acebolado" in [r["prato"] for r in catalogo["da_para_fazer"]]
    frango = next(r for r in catalogo["da_para_fazer"] if r["prato"] == "Frango acebolado")
    assert frango["como"] == "Com o que a senhora tem"
