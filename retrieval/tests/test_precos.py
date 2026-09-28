"""O preço em São Paulo, sem rede: a região do CEP, a escolha do produto e a prova.

As respostas aqui têm a forma das da API da VTEX (a busca inteligente e a de
regiões), com o mínimo que o código lê. A escolha é determinística: o nome com
as palavras do ingrediente e sem as a evitar, o conteúdo no nome, em estoque, a
menor embalagem que cobre, e no empate o menor preço.
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.error
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import pytest

from retrieval import precos
from retrieval.precos import (
    Candidato,
    Conteudo,
    Mercado,
    Pesquisa,
    PrecoNaoVeio,
    Procura,
    candidato,
    conferir_fonte,
    conteudo_do_nome,
    escolher,
    palavras,
    problema_na_resposta,
    regiao_do_cep,
    serve,
)

MERCADO = Mercado("Mambo", "www.mambo.com.br", "01310-100", "São Paulo, capital")
SEM_REGIAO = Mercado("Casa", "www.casa.com.br", "01424-000", "São Paulo", regionalizado=False)
HOJE = dt.date(2026, 9, 27)


def _produto(  # noqa: PLR0913
    nome: str,
    preco: float,
    *,
    produto_id: str = "1",
    unidade: str = "un",
    multiplicador: float = 1.0,
    estoque: int = 10,
    categorias: tuple[str, ...] = ("/Mercearia/",),
) -> dict[str, Any]:
    return {
        "productId": produto_id,
        "productName": nome,
        "linkText": nome.lower().replace(" ", "-"),
        "categories": list(categorias),
        "items": [
            {
                "measurementUnit": unidade,
                "unitMultiplier": multiplicador,
                "sellers": [{"commertialOffer": {"Price": preco, "AvailableQuantity": estoque}}],
            }
        ],
    }


class _Leitor:
    """Responde por pedaço do endereço, e guarda o que foi pedido."""

    def __init__(self, respostas: Mapping[str, object]) -> None:
        self.respostas = respostas
        self.pedidos: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, cabecalhos: Mapping[str, str]) -> str:
        self.pedidos.append((url, dict(cabecalhos)))
        for pedaco, resposta in self.respostas.items():
            if pedaco in url:
                if isinstance(resposta, Exception):
                    raise resposta
                return resposta if isinstance(resposta, str) else json.dumps(resposta)
        raise PrecoNaoVeio(f"sem resposta para {url}")


REGIAO = [{"id": "v2.ABC", "sellers": [{"id": "loja"}]}]


def _compacto(dados: object) -> str:
    """Como a VTEX escreve: sem espaço depois dos dois-pontos."""
    return json.dumps(dados, separators=(",", ":"))


# --------------------------------------------------------------------------- #
# O conteúdo pelo nome                                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("nome", "contado", "esperado"),
    [
        ("Creme de Leite Nestlé 200g", False, Conteudo(Decimal(200), "g")),
        ("Óleo de Soja Liza 900ml", False, Conteudo(Decimal(900), "ml")),
        ("Leite Integral Tirol 1L", False, Conteudo(Decimal(1), "L")),
        ("Arroz Tipo 1 Coop 1kg", False, Conteudo(Decimal(1), "kg")),
        ("Pimenta Reino Kitano 15g Moida", False, Conteudo(Decimal(15), "g")),
        ("Farinha de Trigo 1,5 kg", False, Conteudo(Decimal("1.5"), "kg")),
        ("Leite em Pó 2x200g", False, None),
        ("Creme de Leite", False, None),
        ("Tempero 60g 12 Unidades 5g Cada", False, Conteudo(Decimal(60), "g")),
        ("Caldo de Galinha Knorr 57g com 6 Cubos", True, Conteudo(Decimal(6), "un")),
        ("Ovos Brancos Extra Com 12 Unidades", True, Conteudo(Decimal(12), "un")),
        ("Ovos Brancos Dúzia", True, Conteudo(Decimal(12), "un")),
        ("Couve Manteiga em Maço Oba", True, Conteudo(Decimal(1), "un")),
        ("Alho Poró Unidade", True, Conteudo(Decimal(1), "un")),
        ("Caldo Maggi Galinha 57g", True, None),
    ],
)
def test_o_conteudo_sai_do_nome(nome: str, contado: bool, esperado: Conteudo | None) -> None:
    assert conteudo_do_nome(nome, contado=contado) == esperado


def test_o_conteudo_na_unidade_base() -> None:
    assert Conteudo(Decimal(200), "g").base == Decimal("0.2")
    assert Conteudo(Decimal(900), "ml").dimensao == "volume"
    assert Conteudo(Decimal(6), "un").dimensao == "contagem"
    assert Conteudo(Decimal(1), "kg").base == 1


def test_as_palavras_ficam_no_singular_sem_acento() -> None:
    assert palavras("Cenouras Médias") == ["cenoura", "media"]
    assert palavras("Limões") == ["limao"]
    assert palavras("Pimenta-do-Reino") == ["pimenta", "do", "reino"]


# --------------------------------------------------------------------------- #
# O nome certo                                                                 #
# --------------------------------------------------------------------------- #


def test_a_procura_recusa_o_nome_de_outro_produto() -> None:
    maionese = Procura("maionese", ("maionese",))
    assert maionese.recusa("Maionese Hellmann's Tradicional 500g") == ""
    assert maionese.recusa("Maionese Light Hellmann's 500g") == "o nome diz light"
    assert maionese.recusa("Ketchup 400g") == "o nome não tem maionese"
    calabresa = Procura("linguiça calabresa", ("linguica", "calabresa"), evitar=("toscana",))
    assert calabresa.recusa("Linguiça Toscana Sadia 700g").startswith("o nome não tem")
    caldo = Procura("caldo de galinha", ("caldo", "galinha"), evitar=("po",))
    assert caldo.recusa("Caldo em Pó de Galinha Maggi 35g") == "o nome diz po"
    reino = Procura("pimenta do reino", ("pimenta", "reino"), permitir=("moida",))
    assert reino.recusa("Pimenta do Reino Moída 50g") == ""


def test_a_procura_do_registro_e_a_do_nome() -> None:
    procura = Procura.do_registro(
        {
            "termo": "creme de leite",
            "exigir": ["creme", "leite"],
            "evitar": ["fresco"],
            "permitir": ["uht"],
            "dimensao": "massa",
            "a_granel": False,
            "minimo": "0.15",
            "maximo": "0.25",
            "categoria": "laticinios",
        }
    )
    assert procura.exigir == ("creme", "leite")
    assert procura.evitar == ("fresco",)
    assert (procura.minimo, procura.maximo, procura.a_granel) == (
        Decimal("0.15"),
        Decimal("0.25"),
        False,
    )
    sem_nada = Procura.do_registro({"termo": "cebola"})
    assert (sem_nada.exigir, sem_nada.a_granel, sem_nada.minimo) == (("cebola",), None, None)
    do_nome = Procura.do_nome("MAGGI® Caldo de Galinha 2", "contagem")
    assert do_nome.exigir == ("maggi", "caldo", "galinha")
    assert do_nome.dimensao == "contagem"


def test_o_nome_com_travessao_fica_de_fora() -> None:
    procura = Procura("banha", ("banha",))
    assert candidato(MERCADO, _produto("Banha Sadia \u2013 500g", 20.4), procura) is None
    assert candidato(MERCADO, _produto("Banha Sadia 500g", 20.4), procura) is not None


def test_o_candidato_le_o_preco_do_quilo_do_vendido_a_peso() -> None:
    procura = Procura("cebola", ("cebola",))
    a_peso = candidato(
        MERCADO, _produto("Cebola Nacional Kg", 8.99, unidade="kg", multiplicador=0.24), procura
    )
    assert a_peso is not None
    assert a_peso.conteudo == Conteudo(Decimal(1), "kg", a_granel=True)
    assert a_peso.preco == Decimal("8.99")
    assert a_peso.literal == "8.99"


@pytest.mark.parametrize(
    "produto",
    [
        _produto("Creme de Leite 200g", 3.99, estoque=0),
        _produto("Creme de Leite 200g", 0),
        _produto("Creme de Leite 200g", 3.99, unidade="un", multiplicador=2),
        _produto("Creme de Leite", 3.99),
        {"productName": "Creme de Leite 200g", "items": []},
    ],
)
def test_o_produto_sem_estoque_sem_preco_ou_sem_conteudo_nao_e_candidato(
    produto: dict[str, Any],
) -> None:
    assert candidato(MERCADO, produto, Procura("creme de leite", ("creme", "leite"))) is None


def _cand(nome: str, preco: str, conteudo: Conteudo, produto_id: str = "1") -> Candidato:
    return Candidato(
        MERCADO,
        produto_id,
        nome,
        nome.lower(),
        Decimal(preco),
        preco,
        conteudo,
        ("/Hortifruti/Legumes/",),
    )


def test_serve_confere_granel_dimensao_secao_e_tamanho() -> None:
    procura = Procura(
        "cebola",
        ("cebola",),
        a_granel=True,
        categoria="hortifruti",
        minimo=Decimal("0.5"),
        maximo=Decimal(2),
    )
    kg = Conteudo(Decimal(1), "kg", a_granel=True)
    assert serve(_cand("Cebola Kg", "8", kg), procura) == ""
    assert serve(_cand("Cebola 1kg", "8", Conteudo(Decimal(1), "kg")), procura) == (
        "vendido embalado"
    )
    assert serve(_cand("Cebola Roxa Kg", "8", kg), procura) == "o nome diz roxa"
    embalada = Procura("cebola", ("cebola",), a_granel=False)
    assert serve(_cand("Cebola Kg", "8", kg), embalada) == "vendido a peso"
    assert (
        serve(_cand("Cebola 6 unidades", "8", Conteudo(Decimal(6), "un")), embalada)
        == "o conteúdo é de contagem"
    )
    outra_secao = Procura("cebola", ("cebola",), categoria="mercearia")
    assert serve(_cand("Cebola Kg", "8", kg), outra_secao) == "é de outra seção do mercado"
    pequena = Procura("cebola", ("cebola",), minimo=Decimal(2))
    assert serve(_cand("Cebola Kg", "8", kg), pequena) == "embalagem pequena demais"
    grande = Procura("cebola", ("cebola",), maximo=Decimal("0.5"))
    assert serve(_cand("Cebola Kg", "8", kg), grande) == "embalagem grande demais"


def test_escolhe_a_menor_embalagem_que_cobre_e_no_empate_a_mais_barata() -> None:
    g200 = _cand("A 200g", "4.00", Conteudo(Decimal(200), "g"), "1")
    g200_barata = _cand("B 200g", "3.50", Conteudo(Decimal(200), "g"), "2")
    g500 = _cand("C 500g", "8.00", Conteudo(Decimal(500), "g"), "3")
    assert escolher([g500, g200, g200_barata]) == g200_barata
    assert escolher([g500, g200], Decimal("0.3")) == g500
    # Nenhuma cobre: a maior, que ela compra mais de uma vez.
    assert escolher([g500, g200], Decimal(2)) == g500
    assert escolher([]) is None
    kg_caro = _cand("Kg", "9", Conteudo(Decimal(1), "kg", a_granel=True), "4")
    kg_barato = _cand("Kg", "7", Conteudo(Decimal(1), "kg", a_granel=True), "5")
    assert escolher([kg_caro, kg_barato]) == kg_barato
    # Misturado, vale o vendido a peso: ela leva o que precisa.
    assert escolher([kg_barato, g200]) == kg_barato


# --------------------------------------------------------------------------- #
# A região, a busca e a prova                                                  #
# --------------------------------------------------------------------------- #


def test_a_regiao_do_cep_escolhe_a_loja() -> None:
    ler = _Leitor({"regions": REGIAO})
    assert regiao_do_cep(MERCADO, ler) == "v2.ABC"
    assert "postalCode=01310100" in ler.pedidos[0][0]
    assert regiao_do_cep(SEM_REGIAO, ler) == ""
    assert regiao_do_cep(MERCADO, _Leitor({"regions": [{"id": "v2.X", "sellers": []}]})) is None
    assert regiao_do_cep(MERCADO, _Leitor({"regions": {"erro": 1}})) is None
    with pytest.raises(PrecoNaoVeio, match="não é JSON"):
        regiao_do_cep(MERCADO, _Leitor({"regions": "<html>"}))


def test_a_pesquisa_escolhe_e_guarda_a_prova() -> None:
    busca = {
        "products": [
            _produto("Creme de Leite Light 200g", 2.99, produto_id="9"),
            _produto("Creme de Leite Italac 200g", 3.49, produto_id="7"),
            _produto("Creme de Leite Nestlé 200g", 4.47, produto_id="8"),
            _produto("Creme de Leite Nestlé Lata 300g", 8.49, produto_id="6"),
        ]
    }
    ler = _Leitor({"regions": REGIAO, "intelligent-search": busca})
    pesquisa = Pesquisa([MERCADO, SEM_REGIAO], ler, HOJE)
    procura = Procura("creme de leite", ("creme", "leite"), maximo=Decimal("0.25"))
    fontes = pesquisa.em_todos(procura)
    assert [f.produto for f in fontes] == ["Creme de Leite Italac 200g"] * 2
    fonte = fontes[0]
    assert fonte.registro() == {
        "site": "Mambo",
        "produto": "Creme de Leite Italac 200g",
        "id": "7",
        "preco": "3.49",
        "quantidade": "200",
        "unidade": "g",
        "a_granel": False,
        "url": "https://www.mambo.com.br/creme-de-leite-italac-200g/p",
        "api": (
            "https://www.mambo.com.br/api/io/_v/api/intelligent-search/product_search/"
            "?query=7&count=5&page=1&locale=pt-BR&regionId=v2.ABC"
        ),
        "cep": "01310-100",
        "data": "2026-09-27",
        "campo": "commertialOffer.Price",
        "trecho": '"Price":3.49',
    }
    # A busca foi com a região, e a região foi perguntada uma vez só.
    assert sum("regions" in url for url, _ in ler.pedidos) == 1
    assert any("regionId=v2.ABC" in url for url, _ in ler.pedidos)
    assert "regionId" not in fontes[1].api


def test_sem_produto_na_busca_inteligente_vale_a_busca_antiga_com_a_regiao() -> None:
    antiga = [_produto("Margarina Qualy com Sal 500g", 8.99, produto_id="3")]
    ler = _Leitor(
        {
            "regions": REGIAO,
            "intelligent-search": {"products": [], "redirect": "/categoria"},
            "catalog_system": antiga,
        }
    )
    fonte = Pesquisa([MERCADO], ler, HOJE).no_mercado(MERCADO, Procura("margarina", ("margarina",)))
    assert fonte is not None
    assert fonte.preco == Decimal("8.99")
    cookie = next(c for url, c in ler.pedidos if "catalog_system" in url)
    assert cookie["Cookie"].startswith("vtex_segment=")
    sem_nada = _Leitor({"regions": REGIAO, "intelligent-search": {}, "catalog_system": {}})
    assert Pesquisa([MERCADO], sem_nada, HOJE).em_todos(Procura("x", ("x",))) == []


def test_mercado_que_nao_responde_fica_de_fora_com_o_motivo() -> None:
    sem_regiao = Pesquisa([MERCADO], _Leitor({"regions": PrecoNaoVeio("fora do ar")}), HOJE)
    assert sem_regiao.em_todos(Procura("x", ("x",))) == []
    assert "fora do ar" in sem_regiao.falhas[0]
    sem_busca = Pesquisa(
        [MERCADO],
        _Leitor({"regions": REGIAO, "intelligent-search": PrecoNaoVeio("500")}),
        HOJE,
    )
    assert sem_busca.em_todos(Procura("x", ("x",))) == []
    assert sem_busca.falhas == ["Mambo: 500"]


def _registro() -> dict[str, Any]:
    return {
        "id": "7",
        "produto": "Creme de Leite Italac 200g",
        "preco": "3.49",
        "trecho": '"Price":3.49',
        "a_granel": False,
        "api": "https://www.mambo.com.br/api/io/_v/api/intelligent-search/product_search/?query=7",
    }


def test_a_prova_confere_produto_preco_trecho_e_jeito_de_vender() -> None:
    resposta = _compacto(
        {"products": [_produto("Creme de Leite Italac 200g", 3.49, produto_id="7")]}
    )
    assert problema_na_resposta(_registro(), resposta) == ""
    assert conferir_fonte(_registro(), lambda _u, _c: resposta) == ""
    mudou = _compacto({"products": [_produto("Creme de Leite Italac 200g", 3.99, produto_id="7")]})
    assert problema_na_resposta(_registro(), mudou) == "o preço mudou (a resposta diz 3.99)"
    outro = _compacto({"products": [_produto("Outro 200g", 3.49, produto_id="7")]})
    assert problema_na_resposta(_registro(), outro).startswith("o produto da resposta é outro")
    sem = _compacto(
        {"products": [_produto("Creme de Leite Italac 200g", 3.49, estoque=0, produto_id="7")]}
    )
    assert problema_na_resposta(_registro(), sem) == "o produto está sem estoque ou sem preço"
    assert problema_na_resposta(_registro(), _compacto({"products": []})) == (
        "o produto não está mais na resposta"
    )
    assert problema_na_resposta(_registro(), "<html>") == "a resposta não é JSON"
    sem_trecho = {**_registro(), "trecho": '"Price":3.490'}
    assert problema_na_resposta(sem_trecho, resposta) == "o trecho do preço não está na resposta"
    a_peso = _compacto(
        {"products": [_produto("Creme de Leite Italac 200g", 3.49, produto_id="7", unidade="kg")]}
    )
    assert problema_na_resposta(_registro(), a_peso).startswith("o produto mudou o jeito")
    assert conferir_fonte({**_registro(), "api": ""}) == "a fonte não guarda a consulta da API"

    def fora(_url: str, _cab: Mapping[str, str]) -> str:
        raise PrecoNaoVeio("sem rede")

    assert conferir_fonte(_registro(), fora).startswith("a consulta não veio")


# --------------------------------------------------------------------------- #
# A rede                                                                       #
# --------------------------------------------------------------------------- #


class _Resposta:
    def __init__(self, corpo: bytes) -> None:
        self.corpo = corpo

    def __enter__(self) -> _Resposta:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, limite: int) -> bytes:
        return self.corpo[:limite]


class _Abridor:
    def __init__(self, respostas: list[object]) -> None:
        self.respostas = respostas

    def open(self, _req: object, timeout: float) -> _Resposta:
        assert timeout == precos.TEMPO_LIMITE
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        assert isinstance(resposta, bytes)
        return _Resposta(resposta)


def _com_abridor(monkeypatch: pytest.MonkeyPatch, respostas: list[object]) -> None:
    abridor = _Abridor(respostas)
    monkeypatch.setattr(precos, "abridor", lambda _resolver: abridor)


def test_ler_da_rede_tenta_de_novo_o_erro_do_servidor(monkeypatch: pytest.MonkeyPatch) -> None:
    erro_500 = urllib.error.HTTPError("https://x", 500, "erro", {}, None)  # type: ignore[arg-type]
    _com_abridor(monkeypatch, [erro_500, b'{"ok": 1}'])
    assert precos.ler_da_rede("https://x", {}) == '{"ok": 1}'


def test_ler_da_rede_nao_repete_o_404_e_recusa_o_grande(monkeypatch: pytest.MonkeyPatch) -> None:
    erro_404 = urllib.error.HTTPError("https://x", 404, "sumiu", {}, None)  # type: ignore[arg-type]
    _com_abridor(monkeypatch, [erro_404])
    with pytest.raises(PrecoNaoVeio, match="404"):
        precos.ler_da_rede("https://x", {})
    _com_abridor(monkeypatch, [OSError("rede"), OSError("rede")])
    with pytest.raises(PrecoNaoVeio, match="rede"):
        precos.ler_da_rede("https://x", {})
    _com_abridor(monkeypatch, [b"x" * (precos.TAMANHO_MAXIMO + 1)])
    with pytest.raises(PrecoNaoVeio, match="grande demais"):
        precos.ler_da_rede("https://x", {})


def test_o_ipv4_vem_primeiro(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(precos, "resolver_pelo_sistema", lambda _h, _p: ["2800::1", "200.1.1.1"])
    assert precos.ipv4_primeiro("x", 443) == ["200.1.1.1", "2800::1"]


def test_os_mercados_sao_de_sao_paulo() -> None:
    assert len(precos.MERCADOS) >= 3
    for mercado in precos.MERCADOS:
        assert mercado.cep[:2] in {"01", "02", "03", "04", "05", "08", "09", "13", "14"}
        assert mercado.cep_numeros.isdigit()


# --------------------------------------------------------------------------- #
# A procura pelo nome, com prazo                                               #
# --------------------------------------------------------------------------- #


def test_pelo_nome_busca_uma_vez_por_mercado_e_tenta_as_dimensoes() -> None:
    busca = {
        "products": [
            _produto("Ovos Brancos 12 Unidades", 9.99, produto_id="1"),
            _produto("Coxa e Sobrecoxa de Frango Kg", 12.9, produto_id="2", unidade="kg"),
            _produto("Coxa e Sobrecoxa de Frango sem Osso Kg", 19.9, produto_id="3", unidade="kg"),
        ]
    }
    ler = _Leitor({"regions": REGIAO, "intelligent-search": busca})
    pesquisa = Pesquisa([MERCADO, SEM_REGIAO], ler, HOJE)
    dimensao, fontes = pesquisa.pelo_nome("coxa e sobrecoxa de frango", ("massa",), 5)
    assert dimensao == "massa"
    assert [f.produto for f in fontes] == ["Coxa e Sobrecoxa de Frango Kg"] * 2
    buscas = [url for url, _ in ler.pedidos if "intelligent-search" in url]
    assert len(buscas) == 2
    # Ovos não têm peso no nome: a massa não acha, a contagem acha.
    dimensao, fontes = pesquisa.pelo_nome("ovos brancos", ("massa", "contagem"), 5)
    assert (dimensao, [f.quantidade for f in fontes]) == ("contagem", [Decimal(12)] * 2)
    assert pesquisa.pelo_nome("trufa", ("massa", "volume"), 5) == ("massa", [])


def test_pelo_nome_deixa_de_fora_o_mercado_que_passou_do_prazo() -> None:
    import threading

    solta = threading.Event()

    def ler(url: str, _c: Mapping[str, str]) -> str:
        if "regions" in url:
            return json.dumps(REGIAO)
        if "casa.com.br" in url:
            solta.wait(2)
        return json.dumps({"products": [_produto("Cebola Kg", 8.0, unidade="kg")]})

    pesquisa = Pesquisa([MERCADO, SEM_REGIAO], ler, HOJE)
    _dimensao, fontes = pesquisa.pelo_nome("cebola", ("massa",), 0.5)
    solta.set()
    assert [f.site for f in fontes] == ["Mambo"]
    assert any("passou do prazo" in falha for falha in pesquisa.falhas)
    falhou = Pesquisa(
        [MERCADO], _Leitor({"regions": REGIAO, "intelligent-search": PrecoNaoVeio("x")}), HOJE
    )
    assert falhou.pelo_nome("cebola", ("massa",), 1) == ("massa", [])
    sem_regiao = Pesquisa([MERCADO], _Leitor({"regions": []}), HOJE)
    assert sem_regiao.pelo_nome("cebola", ("massa",), 1) == ("massa", [])
    assert Pesquisa([MERCADO], ler, HOJE).pelo_nome("cebola", (), 1) == ("massa", [])


def test_a_procura_pelo_nome_recusa_sem_osso_e_atacado() -> None:
    procura = Procura.do_nome("coxa e sobrecoxa de frango")
    assert procura.recusa("Coxa e Sobrecoxa de Frango sem Osso Kg") == "o nome diz sem osso"
    assert procura.recusa("Coxa e Sobrecoxa Frango Cong Temp 1kg") == "o nome diz temp"
    assert procura.maximo == Decimal(5)
    com_osso = Procura.do_nome("coxa sem osso")
    assert com_osso.recusa("Coxa sem Osso Kg") == ""
