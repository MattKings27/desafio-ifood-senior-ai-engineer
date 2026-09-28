"""As fotos pela API: só as registradas, baixadas com as travas e guardadas em disco.

Sem rede: o download é trocado por um falso que devolve os bytes (ou a recusa)
de cada endereço, e o teste confere quem foi pedido.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import sessao_de_teste
from fastapi.testclient import TestClient
from mise.catalogo import OrigemNoCatalogo, chave_da_imagem
from mise.fotos import fotos_da_cozinha
from retrieval.extrator import extrair
from retrieval.imagens import ImagemBaixada, ImagemIndisponivel, ImagemRecusada

from gateway.http import criar_app
from gateway.rotas.imagens import CACHE_LONGO, AcervoDeImagens

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x01" * 32
#: A foto de um prato: dezenas de KB. Menos de 15 KB é a imagem genérica do site.
PNG = b"\x89PNG\r\n\x1a\n" + b"\x02" * 20 * 1024
#: O chapéu de cozinheiro cinza que o site põe quando a receita não tem foto: uns 3 KB.
PNG_GENERICO = b"\x89PNG\r\n\x1a\n" + b"\x03" * 3 * 1024

COMMONS = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Capers.jpg/960px-Capers.jpg"
PAGINA_COMMONS = "https://commons.wikimedia.org/wiki/File:Capers.jpg"
CREDITO = "Foto: Fulana de Tal, CC BY-SA 4.0, Wikimedia Commons"

FOTO_DA_RECEITA = "https://static.tudogostoso.com.br/fotos/frango-com-alcaparras.jpg"
RECEITA_URL = "https://www.tudogostoso.com.br/receita/77-frango-com-alcaparras.html"
RECEITA_HTML = (
    '<script type="application/ld+json">'
    + json.dumps(
        {
            "@type": "Recipe",
            "name": "Frango com alcaparras",
            "recipeYield": "4 porções",
            "recipeIngredient": ["500 g de peito de frango", "2 colheres de sopa de alcaparras"],
            "recipeInstructions": ["Cozinhe o frango na panela por 25 minutos."],
            "publisher": {"@type": "Organization", "name": "TudoGostoso"},
            "image": FOTO_DA_RECEITA,
        }
    )
    + "</script>"
)


def _arquivo_de_fotos(pasta: Path) -> Path:
    caminho = pasta / "fotos_ingredientes.json"
    caminho.write_text(
        json.dumps(
            {
                "fotos": [
                    {
                        "item_id": "alcaparras",
                        "arquivo": "File:Capers.jpg",
                        "pagina": PAGINA_COMMONS,
                        "imagem": COMMONS,
                        "licenca": "CC BY-SA 4.0",
                        "autor": "Fulana de Tal",
                        "credito": CREDITO,
                    },
                    {
                        "item_id": "bacon",
                        "arquivo": "File:Bacon.jpg",
                        "pagina": "https://commons.wikimedia.org/wiki/File:Bacon.jpg",
                        "imagem": "https://upload.wikimedia.org/wikipedia/commons/b/bb/Bacon.jpg",
                        "licenca": "CC BY-NC-SA 2.0",
                        "autor": "Alguém",
                        "credito": "Foto: Alguém, CC BY-NC-SA 2.0, Wikimedia Commons",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return caminho


class Download:
    """O download falso: os bytes de cada endereço, e quem foi pedido."""

    def __init__(self) -> None:
        self.pedidos: list[str] = []
        self.respostas: dict[str, ImagemBaixada | Exception] = {
            COMMONS: ImagemBaixada(JPEG, "image/jpeg"),
            FOTO_DA_RECEITA: ImagemBaixada(PNG, "image/png"),
        }

    def __call__(self, url: str) -> ImagemBaixada:
        self.pedidos.append(url)
        resposta = self.respostas[url]
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


class Relogio:
    def __init__(self) -> None:
        self.agora = 1000.0

    def __call__(self) -> float:
        return self.agora


@pytest.fixture
def download() -> Download:
    return Download()


@pytest.fixture
def relogio() -> Relogio:
    return Relogio()


@pytest.fixture
def cliente(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, download: Download, relogio: Relogio
) -> TestClient:
    monkeypatch.setenv("MISE_PLANILHA", str(sessao_de_teste.PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(tmp_path / "estado" / "dossie.db"))
    monkeypatch.setenv("MISE_FOTOS", str(_arquivo_de_fotos(tmp_path)))
    monkeypatch.delenv("MISE_AUDITORIA", raising=False)
    app = criar_app()
    app.state.imagens = AcervoDeImagens(tmp_path / "imagens", download, relogio=relogio)
    return TestClient(app)


def _pasta(cliente: TestClient) -> Path:
    acervo: AcervoDeImagens = cliente.app.state.imagens  # type: ignore[attr-defined]
    return acervo.pasta


def _dados(resposta: Any) -> Any:
    corpo = resposta.json()
    assert corpo["ok"], corpo
    return corpo["dados"]


# --------------------------------------------------------------------------- #
# A despensa traz a foto do Commons                                            #
# --------------------------------------------------------------------------- #


def test_a_despensa_traz_a_foto_do_item_pela_api(cliente: TestClient) -> None:
    esperada = {"url": f"/motor/imagens/{chave_da_imagem(COMMONS)}", "credito": CREDITO}
    item = _dados(cliente.get("/api/despensa/itens/alcaparras"))
    assert item["imagem"] == esperada
    lista = {i["id"]: i for i in _dados(cliente.get("/api/despensa"))["itens"]}
    assert lista["alcaparras"]["imagem"] == esperada
    assert lista["bacon"]["imagem"] is None, "foto sem licença livre não aparece"
    assert lista["tomate"]["imagem"] is None, "item sem foto no arquivo"


def test_o_item_que_ela_acrescenta_nao_tem_foto(cliente: TestClient) -> None:
    resposta = cliente.post(
        "/api/despensa/itens",
        json={"nome": "Linguiça calabresa", "estoque": 1, "unidade": "kg"},
    )
    assert resposta.status_code in {200, 201}, resposta.text
    item = resposta.json()["dados"]["item"]
    assert item["id"].startswith("item-")
    assert item["imagem"] is None


def test_a_cozinha_traz_a_miniatura_de_cada_item_pelo_mesmo_proxy(
    cliente: TestClient, download: Download
) -> None:
    perfil = _dados(cliente.get("/api/perfil"))
    itens = {i["id"]: i for i in [*perfil["equipamentos"], *perfil["tecnicas"]]}
    assert itens["reducao"]["imagem"] is None, "sem foto livre que mostre, a tela mostra o ícone"
    assert sum(1 for i in itens.values() if i["imagem"]) == 62
    sessao = cliente.app.state.sessao  # type: ignore[attr-defined]
    forno = fotos_da_cozinha(sessao.planilha)["forno"]
    assert itens["forno"]["imagem"] == {
        "url": f"/motor/imagens/{forno.chave}",
        "credito": forno.credito,
    }
    download.respostas[forno.url] = ImagemBaixada(JPEG, "image/jpeg")
    resposta = cliente.get(f"/api/imagens/{forno.chave}")
    assert (resposta.status_code, resposta.content) == (200, JPEG)
    credito = _dados(cliente.get(f"/api/imagens/{forno.chave}/credito"))
    assert credito == forno.credito_json()
    assert download.pedidos == [forno.url]


# --------------------------------------------------------------------------- #
# O proxy                                                                      #
# --------------------------------------------------------------------------- #


def test_a_foto_registrada_e_servida_e_guardada(cliente: TestClient, download: Download) -> None:
    chave = chave_da_imagem(COMMONS)
    resposta = cliente.get(f"/api/imagens/{chave}")
    assert resposta.status_code == 200
    assert resposta.content == JPEG
    assert resposta.headers["content-type"] == "image/jpeg"
    assert resposta.headers["cache-control"] == CACHE_LONGO
    assert resposta.headers["x-content-type-options"] == "nosniff"
    assert (_pasta(cliente) / f"{chave}.jpg").read_bytes() == JPEG
    de_novo = cliente.get(f"/api/imagens/{chave}")
    assert de_novo.content == JPEG
    assert download.pedidos == [COMMONS], "a segunda vez sai do disco"


@pytest.mark.parametrize("chave", ["0" * 32, "a" * 31, "A" * 32, "g" * 32, "0" * 64])
def test_chave_que_nao_foi_registrada_e_404_sem_download(
    cliente: TestClient, download: Download, chave: str
) -> None:
    resposta = cliente.get(f"/api/imagens/{chave}")
    assert resposta.status_code == 404
    assert resposta.json()["categoria"] == "ausente"
    assert download.pedidos == []


def test_caminho_no_lugar_da_chave_nao_chega_a_lugar_nenhum(
    cliente: TestClient, download: Download
) -> None:
    for caminho in ("..%2F..%2Fetc%2Fpasswd", "%2e%2e%2fdossie.db", "https%3A%2F%2Fexemplo.com"):
        assert cliente.get(f"/api/imagens/{caminho}").status_code == 404
    assert download.pedidos == []


def test_a_foto_da_receita_lida_vem_pelo_mesmo_registro(
    cliente: TestClient, download: Download
) -> None:
    sessao = cliente.app.state.sessao  # type: ignore[attr-defined]
    sessao.catalogar(extrair(RECEITA_HTML, RECEITA_URL), OrigemNoCatalogo.DESCOBERTA)
    itens = [
        i
        for aba in ("pode_fazer", "falta_resposta")
        for i in _dados(cliente.get("/api/receitas", params={"aba": aba}))["itens"]
    ]
    (item,) = [i for i in itens if i["nome"] == "Frango com alcaparras"]
    assert item["imagem"] == {
        "url": f"/motor/imagens/{chave_da_imagem(FOTO_DA_RECEITA)}",
        "credito": "Foto: TudoGostoso",
    }
    detalhe = _dados(cliente.get(f"/api/receitas/{item['slug']}"))
    assert detalhe["imagem"] == item["imagem"]
    caminho = item["imagem"]["url"].removeprefix("/motor")
    resposta = cliente.get(f"/api{caminho.removeprefix('/api')}")
    assert resposta.status_code == 200
    assert (resposta.content, resposta.headers["content-type"]) == (PNG, "image/png")
    credito = _dados(cliente.get(f"/api/imagens/{chave_da_imagem(FOTO_DA_RECEITA)}/credito"))
    assert credito == {"credito": "Foto: TudoGostoso", "licenca": None, "fonte_url": RECEITA_URL}
    assert download.pedidos == [FOTO_DA_RECEITA]


def test_a_foto_generica_do_site_tira_a_foto_da_receita(
    cliente: TestClient, download: Download
) -> None:
    """Chegou o chapéu cinza de 3 KB: 404, e a receita passa a vir sem foto (o gradiente)."""
    download.respostas[FOTO_DA_RECEITA] = ImagemBaixada(PNG_GENERICO, "image/png")
    sessao = cliente.app.state.sessao  # type: ignore[attr-defined]
    slug = sessao.catalogar(extrair(RECEITA_HTML, RECEITA_URL), OrigemNoCatalogo.DESCOBERTA).slug
    chave = chave_da_imagem(FOTO_DA_RECEITA)
    resposta = cliente.get(f"/api/imagens/{chave}")
    assert resposta.status_code == 404
    assert (
        resposta.json()["erro"] == "Essa receita não tem foto: o site mostra uma imagem genérica."
    )
    assert _dados(cliente.get(f"/api/receitas/{slug}"))["imagem"] is None
    assert cliente.get(f"/api/imagens/{chave}").status_code == 404
    assert download.pedidos == [FOTO_DA_RECEITA], "a genérica não é baixada de novo"
    assert not (_pasta(cliente) / f"{chave}.png").exists()


def test_a_miniatura_do_item_nao_e_generica_por_ser_pequena(
    cliente: TestClient, download: Download
) -> None:
    """A foto do Commons é pequena de propósito: só a foto de receita passa pela régua."""
    resposta = cliente.get(f"/api/imagens/{chave_da_imagem(COMMONS)}")
    assert (resposta.status_code, resposta.content) == (200, JPEG)


def test_o_credito_da_foto_do_item(cliente: TestClient, download: Download) -> None:
    credito = _dados(cliente.get(f"/api/imagens/{chave_da_imagem(COMMONS)}/credito"))
    assert credito == {"credito": CREDITO, "licenca": "CC BY-SA 4.0", "fonte_url": PAGINA_COMMONS}
    assert cliente.get(f"/api/imagens/{'1' * 32}/credito").status_code == 404
    assert download.pedidos == [], "o crédito não baixa a foto"


def test_arquivo_que_nao_e_foto_e_recusado_e_lembrado(
    cliente: TestClient, download: Download
) -> None:
    download.respostas[COMMONS] = ImagemRecusada("o arquivo não é uma foto")
    chave = chave_da_imagem(COMMONS)
    for _ in range(2):
        resposta = cliente.get(f"/api/imagens/{chave}")
        assert resposta.status_code == 404
        assert resposta.json()["erro"] == "Essa foto não pode ser mostrada."
    assert download.pedidos == [COMMONS], "a recusa fica guardada por um tempo"
    assert not list(_pasta(cliente).glob("*")) if _pasta(cliente).exists() else True


def test_site_fora_do_ar_e_502_e_tenta_de_novo_depois(
    cliente: TestClient, download: Download, relogio: Relogio
) -> None:
    download.respostas[COMMONS] = ImagemIndisponivel("não consegui falar com o site")
    chave = chave_da_imagem(COMMONS)
    resposta = cliente.get(f"/api/imagens/{chave}")
    assert resposta.status_code == 502
    assert resposta.json()["categoria"] == "rede"
    assert cliente.get(f"/api/imagens/{chave}").status_code == 502
    assert download.pedidos == [COMMONS]
    relogio.agora += 601
    download.respostas[COMMONS] = ImagemBaixada(JPEG, "image/jpeg")
    assert cliente.get(f"/api/imagens/{chave}").status_code == 200
    assert download.pedidos == [COMMONS, COMMONS]


def test_o_acervo_fica_ao_lado_do_dossie(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MISE_PLANILHA", str(sessao_de_teste.PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(tmp_path / "estado" / "dossie.db"))
    app = criar_app()
    with TestClient(app) as cliente:
        assert cliente.get(f"/api/imagens/{'0' * 32}").status_code == 404
    assert app.state.imagens.pasta == tmp_path / "estado" / "imagens"
