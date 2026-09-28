"""O preço médio em São Paulo: as fontes, a média, a fonte fora da curva e a embalagem que ela compra.

A referência só cota o que é o produto das fontes, na medida que se compara com
a embalagem. O nome parecido ("linguiça toscana", "maionese light", "caldo de
galinha em pó") fica sem preço.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from mise.compras import Medida, medida, precificar_falta
from mise.referencias import PrecosDeReferencia, ler_precos, precos_do_arquivo
from mise.unidades import Dimensao, Quantidade

ARQUIVO = Path(__file__).resolve().parents[3] / "dados" / "precos_de_referencia.json"


def _fonte(
    site: str, preco: str, quantidade: str = "200", unidade: str = "g", **mais: Any
) -> dict[str, Any]:
    return {
        "site": site,
        "produto": f"Creme de Leite {site} {quantidade}{unidade}",
        "id": "1",
        "preco": preco,
        "quantidade": quantidade,
        "unidade": unidade,
        "url": f"https://www.{site.lower()}.com.br/creme/p",
        "api": f"https://www.{site.lower()}.com.br/api/io/_v/api/intelligent-search/product_search/?query=1",
        "cep": "01310-100",
        "data": "2026-09-27",
        "campo": "commertialOffer.Price",
        "trecho": f'"Price":{preco}',
        **mais,
    }


def _creme(*fontes: dict[str, Any], **mais: Any) -> dict[str, Any]:
    return {
        "ingrediente": "creme de leite",
        "nomes": ["creme de leite", "creme de leite de caixinha"],
        "embalagem": "caixinha",
        "evitar": ["fresco"],
        "fontes": list(fontes),
        **mais,
    }


CREME = _creme(_fonte("Mambo", "3.60"), _fonte("Coop", "4.00"), _fonte("Covabra", "4.40"))


def _unidades(valor: str, embalagem: str = "") -> Medida:
    return Medida(Quantidade(Decimal(valor), Dimensao.CONTAGEM), embalagem)


@pytest.fixture(scope="module")
def do_arquivo() -> PrecosDeReferencia:
    return ler_precos(ARQUIVO.resolve())


def test_o_preco_medio_e_a_media_do_quilo_das_fontes() -> None:
    (creme,) = precos_do_arquivo([CREME]).precos
    assert creme.preco_medio == Decimal(20)
    assert creme.preco_medio_texto == "R$ 20,00 o quilo"
    assert creme.media_texto == (
        "média de 3 mercados de São Paulo: R$ 18,00, R$ 20,00 e R$ 22,00 o quilo, em 27/09/2026"
    )
    assert (
        creme.preco_texto == "R$ 4,00 pela caixinha de 200 g, preço médio em São Paulo, 27/09/2026"
    )
    assert creme.texto == (
        "preço médio em São Paulo: R$ 4,00 pela caixinha de 200 g (média de 3 mercados de São "
        "Paulo: R$ 18,00, R$ 20,00 e R$ 22,00 o quilo, em 27/09/2026); a senhora pode corrigir"
    )
    assert creme.site == "mercado de São Paulo"


def test_a_fonte_mais_de_50_por_cento_longe_da_mediana_sai_da_media() -> None:
    cara = _fonte("Luzia", "9.00")
    (creme,) = precos_do_arquivo([_creme(*CREME["fontes"], cara)]).precos
    assert [f.site for f in creme.fora_da_media] == ["Luzia"]
    assert creme.preco_medio == Decimal(20)
    assert creme.media_texto.endswith(
        "; fora da média, por ficar mais de 50% longe da mediana: Luzia (R$ 45,00 o quilo)"
    )
    # Com duas, as duas entram: não se sabe qual das duas está fora.
    (duas,) = precos_do_arquivo([_creme(_fonte("Mambo", "3.60"), cara)]).precos
    assert duas.fora_da_media == ()
    assert duas.preco_medio == Decimal("31.5")


def test_uma_fonte_so_diz_o_mercado() -> None:
    (uma,) = precos_do_arquivo([_creme(_fonte("Mambo", "3.60"))]).precos
    assert uma.site == "Mambo"
    assert uma.media_texto == (
        "preço de 1 mercado de São Paulo (Mambo): R$ 18,00 o quilo, em 27/09/2026"
    )
    assert uma.preco_texto == "R$ 3,60 pela caixinha de 200 g, no Mambo, 27/09/2026"
    assert uma.texto.startswith("preço em São Paulo: R$ 3,60")


def test_datas_diferentes_viram_um_intervalo() -> None:
    antiga = _fonte("Coop", "4.00", data="2026-09-25")
    (creme,) = precos_do_arquivo([_creme(_fonte("Mambo", "3.60"), antiga)]).precos
    assert creme.media_texto.endswith("entre 25/09/2026 e 27/09/2026")
    assert creme.data_texto == "27/09/2026"


def test_ela_compra_a_menor_embalagem_que_cobre_pelo_preco_medio() -> None:
    fontes = [_fonte("Mambo", "3.60"), _fonte("Coop", "6.00", "300"), _fonte("Covabra", "4.40")]
    precos = precos_do_arquivo([_creme(*fontes)])
    # R$ 20,00 o quilo: a caixinha de 200 g sai por R$ 4,00; 250 g pede a de 300 g.
    cotada = precos.cotar("creme de leite", medida(150, "g"))
    assert cotada is not None
    referencia, na_embalagem = cotada
    assert (referencia.tamanho, str(referencia.preco)) == (Decimal("0.2"), "R$ 4,00")
    maior = precos.cotar("creme de leite", medida(250, "g"))
    assert maior is not None
    assert (maior[0].tamanho, str(maior[0].preco)) == (Decimal("0.3"), "R$ 6,00")
    assert maior[0].embalagem_texto == "caixinha de 300 g"
    assert maior[0].produto == "Creme de Leite Coop 300g"
    # Mais do que a maior embalagem: a maior, quantas vezes precisar.
    muito = precos.cotar("creme de leite", medida(1, "kg"))
    assert muito is not None
    preco = precificar_falta(muito[1], muito[0].cotacao)
    assert preco is not None
    assert (str(preco.consumo), str(preco.desembolso)) == ("R$ 20,00", "R$ 24,00")
    assert na_embalagem == medida(150, "g")


def test_o_vendido_a_peso_sai_na_medida_certa() -> None:
    cenoura = {
        "ingrediente": "cenoura",
        "nomes": ["cenoura"],
        "embalagem": "quilo",
        "fontes": [
            _fonte("Mambo", "8.00", "1", "kg", a_granel=True),
            _fonte("Coop", "6.00", "1", "kg", a_granel=True),
        ],
    }
    precos = precos_do_arquivo([cenoura])
    cotada = precos.cotar("cenouras médias", medida(2, "", "cenoura"))
    assert cotada is not None
    referencia, na_embalagem = cotada
    assert referencia.embalagem_texto == "quilo"
    preco = precificar_falta(na_embalagem, referencia.cotacao)
    assert preco is not None
    # 2 cenouras de 120 g (IBGE) a R$ 7,00 o quilo.
    assert (str(preco.consumo), str(preco.desembolso)) == ("R$ 1,68", "R$ 1,68")


CALDO: dict[str, Any] = {
    "ingrediente": "caldo de galinha em tablete",
    "nomes": ["caldo de galinha", "MAGGI Caldo Galinha"],
    "embalagem": "caixa",
    "cada": "tablete",
    "evitar": ["pó", "po"],
    "fontes": [
        _fonte("Mambo", "3.60", "6", "un"),
        _fonte("Savegnago", "4.20", "6", "un"),
    ],
}


def test_a_caixa_de_tabletes_cota_os_tabletes() -> None:
    precos = precos_do_arquivo([CALDO])
    (caldo,) = precos.precos
    assert caldo.embalagem_texto == "caixa com 6 tabletes"
    assert caldo.preco_medio_texto == "R$ 0,65 o tablete"
    cotada = precos.cotar("MAGGI® Caldo Galinha", _unidades("2", "tablete"))
    assert cotada is not None
    referencia, na_embalagem = cotada
    assert na_embalagem == _unidades("2")
    preco = precificar_falta(na_embalagem, referencia.cotacao)
    assert preco is not None
    assert (str(preco.consumo.arredondado()), str(preco.desembolso)) == ("R$ 1,30", "R$ 3,90")
    # "1 lata" de caldo não são tabletes.
    assert precos.cotar("caldo de galinha", _unidades("1", "lata")) is None


def test_a_lata_da_receita_e_a_lata_da_referencia() -> None:
    milho = {
        "ingrediente": "milho verde em lata",
        "nomes": ["milho verde"],
        "embalagem": "lata",
        "fontes": [_fonte("Mambo", "3.40", "170"), _fonte("Coop", "3.40", "170")],
    }
    cotada = precos_do_arquivo([milho]).cotar("milho verde", _unidades("1", "lata"))
    assert cotada is not None
    assert cotada[1] == Medida(Quantidade(Decimal("0.17"), Dimensao.MASSA))
    assert cotada[0].embalagem_texto == "lata de 170 g"
    assert str(cotada[0].preco) == "R$ 3,40"


def test_a_colher_vira_gramas_pelo_peso_da_colher_na_tabela_do_ibge() -> None:
    extrato = {
        "ingrediente": "extrato de tomate",
        "nomes": ["extrato de tomate"],
        "embalagem": "lata",
        "fontes": [_fonte("Mambo", "4.00", "130"), _fonte("Coop", "4.00", "130")],
    }
    precos = precos_do_arquivo([extrato])
    # A medida do próprio ingrediente vem antes da conta pela colher: a xícara de
    # extrato de tomate pesa 262 g na tabela do USDA, então meia xícara são 131 g.
    cotada = precos.cotar(
        "extrato de tomate", medida(Decimal("0.5"), "xicara de cha", "extrato de tomate")
    )
    assert cotada is not None
    assert cotada[1] == Medida(Quantidade(Decimal("0.131"), Dimensao.MASSA))
    assert cotada[0].suposicao == ""


def test_o_tempero_seco_na_colher_cabe_no_pacote_menor() -> None:
    # O colorau não tem medida própria na tabela: a colher de chá conta até o
    # volume dela em gramas, e cabe no pacote menor.
    colorau = {
        "ingrediente": "colorau",
        "nomes": ["colorau"],
        "embalagem": "pacote",
        "tempero_seco": True,
        "fontes": [_fonte("Mambo", "4.00", "20"), _fonte("Coop", "5.00", "50")],
    }
    precos = precos_do_arquivo([colorau])
    cotada = precos.cotar("colorau", medida(1, "colher de cha", "colorau"))
    assert cotada is not None
    referencia, na_embalagem = cotada
    assert na_embalagem == Medida(Quantidade(Decimal("0.005"), Dimensao.MASSA))
    assert "pesa até 5 g" in referencia.texto
    preco = precificar_falta(na_embalagem, referencia.cotacao)
    assert preco is not None
    assert str(preco.desembolso) == "R$ 3,00"
    # Sem medida nenhuma ("1 folha de louro"), a conta leva o pacote inteiro, e diz.
    sem_medida = precos.cotar("colorau", None)
    assert sem_medida is not None
    assert sem_medida[1] is None
    assert "leva o pacote inteiro" in sem_medida[0].texto
    # Contado sem peso ("3 pimentas", "1 stick"): o pacote inteiro, e o texto diz.
    contado = precos.cotar("colorau", _unidades("3"))
    assert contado is not None
    assert contado[1] is None
    assert "a receita pede 3 e não diz quanto pesa" in contado[0].texto
    # Muito mais que o pacote: não se sabe o peso, e fica sem preço.
    assert precos.cotar("colorau", medida(1, "xicara de cha", "colorau")) is None
    # O que não é tempero seco não supõe nada.
    assert precos_do_arquivo([CREME]).cotar("creme de leite", None) is None


def test_a_nota_do_produto_vai_no_texto() -> None:
    dedo = _creme(*CREME["fontes"], nota="a pimenta ardida mais comum é a dedo-de-moça")
    (referencia,) = precos_do_arquivo([dedo]).precos
    assert "; a pimenta ardida mais comum é a dedo-de-moça; a senhora pode corrigir" in (
        referencia.texto
    )


@pytest.mark.parametrize(
    ("mudanca", "motivo"),
    [
        ({"api": "http://x"}, "https"),
        ({"preco": "0"}, "positivos"),
        ({"trecho": '"Price":1.00'}, "trecho"),
        ({"trecho": "Price"}, "trecho"),
        ({"unidade": "xicara"}, "unidade"),
        ({"produto": ""}, "falta produto"),
        ({"quantidade": "muito"}, "número"),
    ],
)
def test_a_fonte_sem_prova_e_recusada(
    mudanca: dict[str, str], motivo: str, caplog: pytest.LogCaptureFixture
) -> None:
    ruim = {**_fonte("Mambo", "3.60"), **mudanca}
    assert not precos_do_arquivo([_creme(ruim)])
    assert motivo in caplog.text


def test_registro_sem_fonte_ou_com_medidas_misturadas_e_recusado(
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert not precos_do_arquivo([{**CREME, "embalagem": ""}])
    misturado = _creme(_fonte("Mambo", "3.60"), _fonte("Coop", "4.00", "1", "L"))
    assert not precos_do_arquivo([misturado])
    assert "medem coisas diferentes" in caplog.text
    em_gramas = {**CALDO, "fontes": [_fonte("Mambo", "3.60")]}
    assert not precos_do_arquivo([em_gramas])
    assert "cada uma" in caplog.text


def test_o_registro_antigo_de_uma_fonte_so_ainda_vale() -> None:
    antigo = {
        "ingrediente": "milho verde",
        "nomes": ["milho verde"],
        "embalagem": "lata",
        **_fonte("Mambo", "3.40", "170"),
    }
    (milho,) = precos_do_arquivo([antigo]).precos
    assert milho.site == "Mambo"


def test_a_soma_junta_as_referencias() -> None:
    juntas = precos_do_arquivo([CREME]) + precos_do_arquivo([CALDO])
    assert [p.ingrediente for p in juntas.precos] == [
        "creme de leite",
        "caldo de galinha em tablete",
    ]


# --------------------------------------------------------------------------- #
# O arquivo de verdade                                                         #
# --------------------------------------------------------------------------- #


def test_o_arquivo_inteiro_passa_pela_conferencia_do_motor() -> None:
    dados = json.loads(ARQUIVO.read_text("utf-8"))
    lidos = precos_do_arquivo(dados["precos"])
    assert len(lidos.precos) == len(dados["precos"])
    for preco in lidos.precos:
        assert preco.fontes
        assert all(f.api.startswith("https://") for f in preco.fontes)


def test_cada_preco_do_arquivo_tem_duas_fontes_de_sao_paulo_ou_mais(
    do_arquivo: PrecosDeReferencia,
) -> None:
    sites = {
        "Mambo",
        "Coop",
        "Oba Hortifruti",
        "Atacadão",
        "Swift",
        "Savegnago",
        "Covabra",
        "Casa Santa Luzia",
    }
    # Só um mercado de São Paulo vende a pescada branca com esse nome.
    de_um_mercado = {"filé de pescada branca"}
    for preco in do_arquivo.precos:
        assert {f.site for f in preco.fontes} <= sites, preco.ingrediente
        if preco.ingrediente not in de_um_mercado:
            assert len(preco.fontes) >= 2, preco.ingrediente


@pytest.mark.parametrize(
    ("nome", "falta"),
    [
        ("farinha de milho em flocos", medida(250, "g")),
        ("cebola roxa", medida(Decimal("0.07"), "kg")),
        ("molho shoyu", medida(Decimal("0.5"), "xicara", "molho shoyu")),
        ("maionese", medida(54, "g")),
        ("tempero para aves", medida(1, "pacote")),
        ("bananas da terra", medida(3, "")),
        ("MAGGI® Caldo Galinha", medida(2, "tablete")),
        ("linguiça defumada", medida(1, "")),
        ("pimenta-do-reino", medida(1, "pitada", "pimenta-do-reino")),
        ("pimenta-do-reino", medida(1, "colher de cha", "pimenta-do-reino")),
        ("páprica doce", medida(1, "colher de cha", "páprica doce")),
        ("cominho em pó", medida(1, "colher de cha", "cominho em pó")),
        ("folhas de louro", None),
        ("extrato de tomate", medida(Decimal("0.5"), "xicara de cha", "extrato de tomate")),
        ("extrato de tomate", medida(2, "colher de sopa", "extrato de tomate")),
        ("creme de leite", medida(1, "lata")),
        ("leite condensado", medida(1, "lata")),
        ("limão", medida(1, "limao", "limão")),
        ("pimentões", medida(2, "")),
        ("margarina", medida(100, "g")),
        ("chocolate em pó", medida(3, "colher", "chocolate em pó")),
        ("milho verde", medida(1, "lata")),
        # O que escondia receitas do catálogo por falta de preço.
        ("pimentas ardidas", medida(3, "")),
        ("alecrim", medida(1, "ramo", "alecrim")),
        ("mandioca", medida(1, "kg")),
        ("stick de MAGGI® MEU SEGREDO 7 Vegetais", medida(1, "")),
        ("sazón", medida(2, "")),
        ("sazóns para feijão", medida(2, "")),
    ],
)
def test_o_que_falta_nas_receitas_do_catalogo_tem_preco_medio(
    do_arquivo: PrecosDeReferencia, nome: str, falta: Medida | None
) -> None:
    cotada = do_arquivo.cotar(nome, falta)
    assert cotada is not None, nome
    referencia, na_embalagem = cotada
    assert len(referencia.na_media) >= 2, nome
    assert precificar_falta(na_embalagem, referencia.cotacao) is not None


@pytest.mark.parametrize(
    "nome",
    [
        # Outro produto com nome parecido: o preço de uma não é o da outra.
        "linguiça toscana",
        "linguiça",
        "pescada amarela",
        "maionese light",
        "caldo de galinha em pó",
        "molho shoyu light",
        "farinha de milho",
        "flocão de milho",
        "banana",
        "geleia de damasco",
        "amêndoa",
        "creme de leite fresco",
        "pimenta-do-reino em grão",
        "couve-flor",
        "manteiga sem sal",
        "leite condensado light",
    ],
)
def test_o_nome_parecido_nao_leva_o_preco_do_outro(
    do_arquivo: PrecosDeReferencia, nome: str
) -> None:
    assert do_arquivo.de(nome) == (), [p.ingrediente for p in do_arquivo.de(nome)]


def test_a_linguica_toscana_nao_e_calabresa_e_a_fina_e_outra(
    do_arquivo: PrecosDeReferencia,
) -> None:
    assert [p.ingrediente for p in do_arquivo.de("linguiça calabresa")] == [
        "linguiça calabresa defumada"
    ]
    assert [p.ingrediente for p in do_arquivo.de("linguicinhas defumadas")] == [
        "linguiça defumada fina"
    ]
    assert do_arquivo.de("linguiça toscana") == ()


def test_a_pimenta_ardida_e_a_dedo_de_moca_e_o_texto_diz(do_arquivo: PrecosDeReferencia) -> None:
    (dedo,) = do_arquivo.de("pimentas ardidas")
    assert dedo.ingrediente == "pimenta dedo-de-moça"
    assert "dedo-de-moça" in dedo.texto


@pytest.mark.parametrize(
    ("nome", "falta"),
    [
        # O que a tabela do IBGE não diz, a do USDA diz, ou a classe com base citada:
        # a colher, a pitada e a folha viram gramas, e o preço de referência cota.
        ("páprica doce", medida(1, "colher de cha", "páprica doce")),
        ("cominho em pó", medida(1, "colher de cha", "cominho em pó")),
        ("pimenta-do-reino", medida(1, "pitada", "pimenta-do-reino")),
        ("damascos", medida(Decimal("0.5"), "xicara de cha", "damascos")),
        ("extrato de tomate", medida(Decimal("0.5"), "xicara de cha", "extrato de tomate")),
        ("folha de louro", medida(1, "folha de louro", "folha de louro")),
    ],
)
def test_a_medida_com_fonte_vira_gramas_e_o_preco_cota(
    do_arquivo: PrecosDeReferencia, nome: str, falta: Medida | None
) -> None:
    assert do_arquivo.de(nome), "o produto tem preço de referência"
    assert falta is not None
    assert falta.quantidade.dimensao.value == "kg"
    assert do_arquivo.cotar(nome, falta) is not None
