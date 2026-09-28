"""A conferência das fotos dos ingredientes: sem rede, com as respostas gravadas do Commons.

`make conferir-fotos` pergunta à API do Commons de verdade. Aqui a mesma prova
roda com o que foi gravado: se alguém trocar uma licença, um autor ou um
endereço no arquivo das fotos, a linha deixa de bater com o que o Commons disse,
e o teste reprova. É o que garante que nenhuma foto sem licença livre ou sem o
crédito certo chega à tela.
"""

from __future__ import annotations

import copy
import io
import json
import sys
from pathlib import Path
from typing import Any, Self

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import conferir_fotos as conferencia


def test_toda_foto_bate_com_o_que_o_commons_disse() -> None:
    lista = conferencia.fotos()
    resultado, respostas = conferencia.conferir(lista, conferencia.ler_gravadas())
    ruins = [(item, achados) for item, achados in resultado if achados]
    assert not ruins
    assert len(resultado) == len(respostas) == 36


def test_o_item_sem_foto_diz_por_que() -> None:
    """Sem foto livre que mostre o item de verdade, ele fica sem foto, com o motivo."""
    dados = json.loads(conferencia.ARQUIVO.read_text(encoding="utf-8"))
    (sem,) = dados["sem_foto"]
    assert sem["item_id"] == "adocante-liquido"
    assert "sem marca" in sem["motivo"]
    com_foto = {f["item_id"] for f in dados["fotos"]}
    assert sem["item_id"] not in com_foto
    assert len(com_foto) + len(dados["sem_foto"]) == 37


def test_toda_foto_da_cozinha_bate_com_o_que_o_commons_disse() -> None:
    lista = conferencia.fotos(conferencia.ARQUIVO_DA_COZINHA)
    gravadas = conferencia.ler_gravadas(conferencia.GRAVADAS_DA_COZINHA)
    resultado, respostas = conferencia.conferir(lista, gravadas)
    assert not [(item, achados) for item, achados in resultado if achados]
    assert len(resultado) == len(respostas) == 62
    assert all("/250px-" in foto["imagem"] for foto in lista), "a miniatura pequena"


def test_cada_item_da_cozinha_tem_foto_ou_o_motivo_de_nao_ter() -> None:
    from mise.taxonomia import EQUIPAMENTOS, TECNICAS

    dados = json.loads(conferencia.ARQUIVO_DA_COZINHA.read_text(encoding="utf-8"))
    vocabulario = {e.id: "equipamento" for e in EQUIPAMENTOS} | {
        t.id: "tecnica" for t in TECNICAS
    }
    linhas = [*dados["fotos"], *dados["sem_foto"]]
    assert sorted(linha["item_id"] for linha in linhas) == sorted(vocabulario)
    assert all(linha["tipo"] == vocabulario[linha["item_id"]] for linha in linhas)
    assert all(linha["motivo"].strip() for linha in dados["sem_foto"])
    imagens = [foto["imagem"] for foto in dados["fotos"]]
    assert len(set(imagens)) == len(imagens), "uma foto por item"


def _uma() -> tuple[dict[str, Any], dict[str, Any]]:
    foto = copy.deepcopy(conferencia.fotos()[0])
    resposta = conferencia.ler_gravadas()(foto["arquivo"])
    return foto, resposta


@pytest.mark.parametrize(
    ("campo", "valor", "trecho"),
    [
        ("licenca", "CC BY-SA 2.0", "licenca: a linha diz"),
        ("autor", "Outra Pessoa", "autor: a linha diz"),
        ("imagem", "https://upload.wikimedia.org/outra.jpg", "imagem: a linha diz"),
        (
            "pagina",
            "https://commons.wikimedia.org/wiki/File:Outra.jpg",
            "pagina: a linha diz",
        ),
    ],
)
def test_linha_que_nao_bate_reprova(campo: str, valor: str, trecho: str) -> None:
    foto, resposta = _uma()
    foto[campo] = valor
    assert any(trecho in achado for achado in conferencia.problemas(foto, resposta))


def test_o_que_o_commons_diz_tambem_reprova() -> None:
    foto, resposta = _uma()
    assert conferencia.problemas(foto, {}) == ["o arquivo não existe mais no Commons"]
    assert any(
        "não é livre" in a
        for a in conferencia.problemas(foto, {**resposta, "licenca": "CC BY-NC 2.0"})
    )
    assert any(
        "restrição" in a
        for a in conferencia.problemas(foto, {**resposta, "restricoes": "trademarked"})
    )
    assert any(
        "tipo" in a
        for a in conferencia.problemas(foto, {**resposta, "mime": "image/svg+xml"})
    )


def test_resposta_da_api_vira_o_resumo() -> None:
    resposta = {
        "query": {
            "pages": [
                {
                    "title": "File:Capers.jpg",
                    "imageinfo": [
                        {
                            "thumburl": "https://upload.wikimedia.org/thumb/960px-Capers.jpg",
                            "url": "https://upload.wikimedia.org/Capers.jpg",
                            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Capers.jpg",
                            "mime": "image/jpeg",
                            "extmetadata": {
                                "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                "LicenseUrl": {
                                    "value": "https://creativecommons.org/licenses/by-sa/4.0"
                                },
                                "Artist": {
                                    "value": '<a href="//commons.wikimedia.org/wiki/User:F">Fulana &amp; Cia</a>'
                                },
                            },
                        }
                    ],
                }
            ]
        }
    }
    assert conferencia.resumo_da_resposta(resposta) == {
        "arquivo": "File:Capers.jpg",
        "pagina": "https://commons.wikimedia.org/wiki/File:Capers.jpg",
        "imagem": "https://upload.wikimedia.org/thumb/960px-Capers.jpg",
        "mime": "image/jpeg",
        "licenca": "CC BY-SA 4.0",
        "licenca_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "autor": "Fulana & Cia",
        "restricoes": "",
    }
    assert (
        conferencia.resumo_da_resposta({"query": {"pages": [{"missing": True}]}}) == {}
    )


class _Resposta:
    def __init__(self, corpo: dict[str, Any]) -> None:
        self._corpo = json.dumps(corpo).encode()

    def read(self) -> bytes:
        return self._corpo

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_consulta_na_rede_pede_o_arquivo_certo(monkeypatch: pytest.MonkeyPatch) -> None:
    pedidos: list[Any] = []

    class _Abridor:
        def open(self, pedido: Any, timeout: float) -> _Resposta:
            pedidos.append((pedido, timeout))
            return _Resposta({"query": {"pages": [{"missing": True}]}})

    import retrieval.rede

    monkeypatch.setattr(retrieval.rede, "abridor", _Abridor)
    assert conferencia.consultar_na_rede("File:Capers.jpg") == {}
    ((pedido, prazo),) = pedidos
    assert "titles=File%3ACapers.jpg" in pedido.full_url
    assert "iiurlwidth=960" in pedido.full_url
    conferencia.consultar_na_rede("File:Capers.jpg", largura=250)
    assert "iiurlwidth=250" in pedidos[-1][0].full_url
    assert pedido.get_header("User-agent") == conferencia.AGENTE
    assert "@" not in conferencia.AGENTE, "sem e-mail no cabeçalho"
    assert prazo == 20


def test_main_diz_quantas_bateram(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    saida = io.StringIO()
    monkeypatch.setattr(sys, "stdout", saida)
    assert conferencia.main(["--gravadas"]) == 0
    assert "36 de 36 fotos conferidas no Commons." in saida.getvalue()
    assert conferencia.main(["--cozinha", "--gravadas"]) == 0
    assert "62 de 62 fotos conferidas no Commons." in saida.getvalue()
    gravado = tmp_path / "gravadas.json"
    monkeypatch.setattr(conferencia, "GRAVADAS", gravado)
    monkeypatch.setattr(conferencia, "consultar_na_rede", lambda _a: {})
    assert conferencia.main(["--gravar"]) == 1, "sem resposta do Commons, reprova"
    assert json.loads(gravado.read_text(encoding="utf-8"))["respostas"]
