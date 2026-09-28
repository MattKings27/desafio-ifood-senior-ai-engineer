"""A pauta da descoberta: o que procurar sai da despensa, sem modelo no meio."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from receitas_de_teste import ditada, pagina, sessao_nova
from retrieval.extrator import extrair

from mise import categorias
from mise.catalogo import OrigemNoCatalogo, url_canonica
from mise.descoberta import (
    BASICOS,
    MAXIMO_DE_BUSCAS,
    MAXIMO_DE_PAGINAS,
    MAXIMO_DE_PRATOS,
    MINIMO_DE_BUSCAS,
    PAGINAS_POR_BUSCA,
    PRATOS_CLASSICOS,
    SITES_POPULARES,
    TERMOS_DA_PLANILHA,
    MotivoDaPauta,
    itens_da_pauta,
    montar_pauta,
    pratos_da_pauta,
    receitas_conhecidas,
    termo_de_busca,
)
from mise.despensa import OrigemDoItem
from mise.dossie import Canal
from mise.mcp_server import Sessao

ALCAPARRAS_URL = "https://www.tudogostoso.com.br/receita/88-frango-com-alcaparras.html"
ALCAPARRAS = pagina(
    "Frango com alcaparras",
    ["500 g de peito de frango", "3 colheres de sopa de alcaparras", "1 cebola"],
    ["Refogue a cebola.", "Junte o frango e as alcaparras e cozinhe por 20 minutos."],
)


def test_todo_item_da_planilha_tem_termo_de_busca() -> None:
    assert set(TERMOS_DA_PLANILHA) == set(categorias.DA_PLANILHA)
    assert BASICOS <= set(TERMOS_DA_PLANILHA)


def test_a_pauta_comeca_pelos_pratos_que_ela_cobre_e_pelo_dinheiro_parado(
    tmp_path: Path,
) -> None:
    """Só o item mais caro trazia receita que pede compra; o prato clássico dela vem antes."""
    pauta = montar_pauta(sessao_nova(tmp_path))
    assert pauta["disponivel"] is True
    assert pauta["buscas"] == [
        "receita de feijão tropeiro",
        "receita de escondidinho de carne moída",
        "receita de farofa de bacon",
        "receita de polenta com queijo",
        "receita com alcaparras",
        "receita com cobertura de chocolate",
        "receita com carne moída",
        "receita com alcatra",
    ]
    assert pauta["pratos_para_procurar"][2] == {
        "prato": "farofa de bacon",
        "busca": "receita de farofa de bacon",
        "itens_da_despensa": ["Farinha de mandioca", "Bacon", "Cebola"],
        "motivo_texto": "a despensa dela tem a base: farinha de mandioca, bacon e cebola",
    }
    assert {i["motivo"] for i in pauta["itens_para_procurar"]} == {"sem_receita"}
    assert pauta["itens_para_procurar"][0]["motivo_texto"] == (
        "R$ 82,00 pagos, e nenhuma receita usa ainda"
    )
    assert pauta["limites"] == {"buscas": 8, "paginas": 20, "paginas_por_busca": 3}
    assert pauta["texto"] == (
        "Separei 8 buscas: 4 por pratos clássicos que a despensa dela já cobre e 4 pelo "
        "dinheiro parado sem receita."
    )
    assert "no máximo 8 pesquisas" in pauta["orientacao"]
    assert "no máximo 20 páginas" in pauta["orientacao"]
    assert "até 3 de cada pesquisa" in pauta["orientacao"]
    assert "azeite" not in " ".join(pauta["buscas"]), "o que vai em todo prato não vira busca"


def test_todo_prato_classico_sai_de_itens_da_planilha() -> None:
    """O mapa é curado à mão: cada prato aponta para itens que a planilha dela tem."""
    nomes = [prato.nome for prato in PRATOS_CLASSICOS]
    assert len(set(nomes)) == len(nomes)
    for prato in PRATOS_CLASSICOS:
        assert set(prato.itens) <= set(categorias.DA_PLANILHA), prato.nome
        temperos = {"sal", "oleo-de-soja", "azeite-de-oliva-extra-virgem"}
        assert not set(prato.itens) & temperos, "o sal e o óleo não fazem a base de um prato"
        assert prato.busca == f"receita de {prato.nome}"
    assert {"feijão tropeiro", "frango acebolado", "macarrão alho e óleo"} <= set(nomes)


def test_o_prato_so_entra_com_a_base_inteira_na_despensa(tmp_path: Path) -> None:
    sessao = sessao_nova(tmp_path)
    couve = sessao.despensa["Couve"]
    sessao.editavel.acabou(couve.id, motivo="teste", canal=Canal.TELA)
    pratos = pratos_da_pauta(sessao.despensa, receitas_conhecidas(sessao))
    assert [p.prato.nome for p in pratos] == [
        "escondidinho de carne moída",
        "farofa de bacon",
        "polenta com queijo",
        "purê de batata",
    ]
    assert len(pratos) == MAXIMO_DE_PRATOS


def test_o_prato_que_ja_tem_receita_sai_da_pauta(tmp_path: Path) -> None:
    sessao = sessao_nova(tmp_path)
    url = "https://www.tudogostoso.com.br/receita/7-feijao-tropeiro-mineiro.html"
    tropeiro = pagina(
        "Feijão tropeiro mineiro",
        ["500 g de feijão carioca", "200 g de bacon", "2 xícaras de farinha de mandioca"],
        ["Cozinhe o feijão.", "Frite o bacon e junte a farinha e o feijão."],
    )
    sessao.catalogar(extrair(tropeiro, url), OrigemNoCatalogo.DESCOBERTA)
    pauta = montar_pauta(sessao)
    assert "receita de feijão tropeiro" not in pauta["buscas"]
    assert pauta["buscas"][:MAXIMO_DE_PRATOS] == [
        "receita de escondidinho de carne moída",
        "receita de farofa de bacon",
        "receita de polenta com queijo",
        "receita de purê de batata",
    ]


def test_a_receita_que_entrou_muda_a_pauta_e_vira_endereco_conhecido(tmp_path: Path) -> None:
    sessao = sessao_nova(tmp_path)
    sessao.catalogar(extrair(ALCAPARRAS, ALCAPARRAS_URL), OrigemNoCatalogo.DESCOBERTA)
    pauta = montar_pauta(sessao)
    assert "receita com alcaparras" not in pauta["buscas"]
    assert "receita com peito de frango" not in pauta["buscas"]
    assert pauta["buscas"][MAXIMO_DE_PRATOS] == "receita com cobertura de chocolate"
    assert pauta["urls_conhecidas"] == [url_canonica(ALCAPARRAS_URL)]
    assert pauta["sites_que_ja_funcionaram"] == ["tudogostoso.com.br"]


def test_a_pauta_traz_os_sites_populares_que_publicam_receita_estruturada(
    tmp_path: Path,
) -> None:
    """A busca prefere os sites que o servidor lê: a lista vai na pauta, com ou sem busca."""
    sessao = sessao_nova(tmp_path)
    pauta = montar_pauta(sessao)
    assert pauta["sites_populares"] == list(SITES_POPULARES)
    assert pauta["sites_populares"][:2] == ["tudogostoso.com.br", "receitas.globo.com"]
    assert len(set(SITES_POPULARES)) == len(SITES_POPULARES)
    assert all("/" not in site and not site.startswith("www.") for site in SITES_POPULARES)
    orientacao = pauta["orientacao"]
    assert "prefira primeiro as páginas dos sites de 'sites_populares'" in orientacao
    assert orientacao.index("sites_populares") < orientacao.index("sites_que_ja_funcionaram")


def _usa_quase_tudo(sessao: Sessao, fora: set[str]) -> None:
    """Uma receita ditada que usa todos os itens com preço, menos os de `fora`."""
    ingredientes = [
        {"texto": f"100 g de {item.nome}", "nome": item.nome, "quantidade": 100, "medida": "g"}
        for item in sessao.despensa
        if item.nome not in fora
    ]
    ditada(
        sessao,
        nome="Receita que usa tudo",
        rendimento_porcoes=4,
        modo_preparo=["Misture tudo na panela."],
        ingredientes=ingredientes,
    )


def test_com_pouco_parado_entram_os_maiores_gastos(tmp_path: Path) -> None:
    sessao = sessao_nova(tmp_path)
    _usa_quase_tudo(sessao, {"Canela em pó", "Farinha de mandioca"})
    assert len(receitas_conhecidas(sessao)) == 1
    pauta = itens_da_pauta(sessao.despensa, receitas_conhecidas(sessao))
    assert [(i.item.nome, i.motivo) for i in pauta] == [
        ("Farinha de mandioca", MotivoDaPauta.SEM_RECEITA),
        ("Canela em pó", MotivoDaPauta.SEM_RECEITA),
        ("Alcaparras", MotivoDaPauta.MAIOR_INVESTIMENTO),
        ("Cobertura de chocolate", MotivoDaPauta.MAIOR_INVESTIMENTO),
        ("Carne moída (patinho)", MotivoDaPauta.MAIOR_INVESTIMENTO),
    ]
    assert len(pauta) == MINIMO_DE_BUSCAS
    assert pauta[2].para_json()["motivo_texto"] == "R$ 82,00 pagos; já entra em 1 receita"
    texto = montar_pauta(sessao)["texto"]
    assert texto == (
        "Separei 6 buscas: 4 por pratos clássicos que a despensa dela já cobre e 2 pelo "
        "dinheiro parado sem receita."
    )


def test_sem_nada_parado_so_os_maiores_gastos(tmp_path: Path) -> None:
    sessao = sessao_nova(tmp_path)
    _usa_quase_tudo(sessao, set())
    pauta = montar_pauta(sessao)
    assert len(pauta["buscas"]) == MINIMO_DE_BUSCAS
    assert pauta["texto"] == (
        "Separei 5 buscas: 4 por pratos clássicos que a despensa dela já cobre e 1 pelos "
        "itens em que ela mais gastou."
    )
    sem_pratos = itens_da_pauta(sessao.despensa, receitas_conhecidas(sessao))
    assert {i.motivo for i in sem_pratos} == {MotivoDaPauta.MAIOR_INVESTIMENTO}
    assert len(sem_pratos) == MINIMO_DE_BUSCAS


def test_item_sem_estoque_ou_sem_preco_nao_entra(tmp_path: Path) -> None:
    sessao = sessao_nova(tmp_path)
    for item in list(sessao.despensa):
        if item.nome != "Bacon":
            sessao.editavel.acabou(item.id, motivo="teste", canal=Canal.TELA)
    sessao.editavel.adicionar(
        nome="Linguiça calabresa (defumada)",
        estoque=Decimal(1),
        unidade="kg",
        quantidade_comprada=None,
        preco_pago=None,
        origem=OrigemDoItem.JA_TINHA,
        motivo="teste",
        canal=Canal.TELA,
    )
    pauta = montar_pauta(sessao)
    assert pauta["buscas"] == ["receita com bacon"]
    assert (
        pauta["texto"]
        == "Separei 1 busca pelos itens em que mais dinheiro está parado sem receita."
    )
    novo = sessao.despensa["Linguiça calabresa (defumada)"]
    assert termo_de_busca(novo) == "linguiça calabresa"


def test_sem_por_onde_comecar_a_pauta_diz(tmp_path: Path) -> None:
    sessao = sessao_nova(tmp_path)
    for item in list(sessao.despensa):
        sessao.editavel.acabou(item.id, motivo="teste", canal=Canal.TELA)
    pauta = montar_pauta(sessao)
    assert (pauta["disponivel"], pauta["buscas"], pauta["itens_para_procurar"]) == (False, [], [])
    assert pauta["orientacao"].startswith("Não procure receitas agora")


def test_nunca_mais_que_oito_buscas(tmp_path: Path) -> None:
    pauta = itens_da_pauta(sessao_nova(tmp_path).despensa, {})
    assert len(pauta) == MAXIMO_DE_BUSCAS == 8
    assert len({i.termo for i in pauta}) == len(pauta)


def test_as_vinte_paginas_cabem_nas_oito_buscas_ate_tres_de_cada() -> None:
    """Cada busca tem teto, para a primeira não gastar as leituras das outras.

    O teto é a divisão arredondada para cima: com 2 por busca, as 8 buscas nunca
    chegariam às 20 páginas; com 3, chegam, e nenhuma pesquisa sozinha leva a rodada.
    """
    assert (MAXIMO_DE_BUSCAS, MAXIMO_DE_PAGINAS, PAGINAS_POR_BUSCA) == (8, 20, 3)
    assert PAGINAS_POR_BUSCA * MAXIMO_DE_BUSCAS >= MAXIMO_DE_PAGINAS
    assert (PAGINAS_POR_BUSCA - 1) * MAXIMO_DE_BUSCAS < MAXIMO_DE_PAGINAS
    assert PAGINAS_POR_BUSCA < MAXIMO_DE_PAGINAS
    assert MAXIMO_DE_PRATOS < MINIMO_DE_BUSCAS <= MAXIMO_DE_BUSCAS
