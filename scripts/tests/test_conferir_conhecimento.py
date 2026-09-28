"""A conferência dos trechos citados: sem rede, com as páginas gravadas.

`make conferir-conhecimento` busca as páginas de verdade. Aqui a mesma prova
roda com o pedaço gravado de cada página: se alguém mudar um trecho no YAML ou
num padrão do preço preliminar, ele deixa de estar na página, e o teste
reprova. É o que garante que a base de cozinha não ganha fato sem fonte.
"""

from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path
from typing import Any, Self

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import conferir_conhecimento as conferencia


def test_toda_citacao_esta_na_pagina_gravada() -> None:
    lista = conferencia.citacoes()
    resultado, paginas = conferencia.conferir(lista, conferencia.ler_gravadas())
    sem_prova = [(c.id, problema) for c, problema in resultado if problema]
    assert not sem_prova
    assert len({c.url for c in lista}) == len(paginas)
    ids = [c.id for c in lista]
    assert len(ids) == len(set(ids))
    fatos = [i for i in ids if i.startswith("conhecimento:")]
    assert 40 <= len(fatos) <= 60, "a base curada tem de 40 a 60 fatos"
    assert {i for i in ids if i.startswith("parametro:")} >= {
        "parametro:valor_hora",
        "parametro:botijao_preco",
        "parametro:botijao_horas",
        "parametro:kwh_preco",
    }


def test_trecho_mudado_perde_a_prova(monkeypatch: pytest.MonkeyPatch) -> None:
    original = conferencia.citacoes()
    alterada = [
        conferencia.Citacao(
            original[0].id, original[0].url, original[0].trecho + " e mais nada"
        ),
        *original[1:],
    ]
    monkeypatch.setattr(conferencia, "citacoes", lambda: alterada)
    assert conferencia.main(["--gravadas"]) == 1


def test_pagina_que_nao_vem_e_falha_e_nao_prova() -> None:
    lista = [
        conferencia.Citacao("x:1", "https://exemplo.com.br/a", "um trecho qualquer")
    ]

    def cair(_url: str) -> str:
        raise urllib.error.URLError("fora do ar")

    resultado, paginas = conferencia.conferir(lista, cair)
    assert paginas == {}
    assert resultado[0][1].startswith("a página não veio")


def test_pagina_que_nao_foi_gravada_nao_prova(tmp_path: Path) -> None:
    arquivo = tmp_path / "gravadas.json"
    arquivo.write_text(json.dumps({"gravado_em": "2026-09-26", "paginas": {}}), "utf-8")
    ler = conferencia.ler_gravadas(arquivo)
    lista = [
        conferencia.Citacao("x:1", "https://exemplo.com.br/a", "um trecho qualquer")
    ]
    resultado, _ = conferencia.conferir(lista, ler)
    assert "não foi gravada" in resultado[0][1]


def test_gravar_guarda_o_pedaco_em_volta_do_trecho(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pagina = "começo " * 200 + "O trecho que importa está aqui." + " fim" * 200
    lista = [
        conferencia.Citacao("x:1", "https://exemplo.com.br/a", "trecho que importa")
    ]
    monkeypatch.setattr(conferencia, "citacoes", lambda: lista)
    monkeypatch.setattr(conferencia, "ler_da_rede", lambda _url: pagina)
    destino = tmp_path / "gravadas.json"
    assert conferencia.main(["--gravar", "--arquivo", str(destino)]) == 0
    gravado = json.loads(destino.read_text("utf-8"))
    janela = gravado["paginas"]["https://exemplo.com.br/a"]["janelas"][0]
    assert "trecho que importa" in janela
    assert len(janela) < len(pagina)
    assert conferencia.main(["--gravadas", "--arquivo", str(destino)]) == 0
    assert "1 de 1 trechos conferidos" in capsys.readouterr().out


def test_gravar_nao_grava_quando_falta_prova(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lista = [conferencia.Citacao("x:1", "https://exemplo.com.br/a", "trecho ausente")]
    monkeypatch.setattr(conferencia, "citacoes", lambda: lista)
    monkeypatch.setattr(conferencia, "ler_da_rede", lambda _url: "outra coisa")
    destino = tmp_path / "gravadas.json"
    assert conferencia.main(["--gravar", "--arquivo", str(destino)]) == 1
    assert not destino.exists()


def test_janela_ignora_trecho_que_nao_esta_na_pagina() -> None:
    assert conferencia.janelas("texto da página", ["não está"]) == []


class _Resposta:
    """O que o `urllib` devolve, com os bytes e os cabeçalhos de uma página gravada."""

    def __init__(self, bruto: bytes, tipo: str) -> None:
        self._bruto = io.BytesIO(bruto)
        from email.message import Message

        self.headers = Message()
        self.headers["Content-Type"] = tipo

    def read(self, limite: int) -> bytes:
        return self._bruto.read(limite)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class _Abridor:
    def __init__(self, resposta: _Resposta) -> None:
        self.resposta = resposta

    def open(self, _requisicao: Any, timeout: float) -> _Resposta:
        assert timeout > 0
        return self.resposta


def test_ler_da_rede_le_html_e_planilha(monkeypatch: pytest.MonkeyPatch) -> None:
    import openpyxl
    from retrieval.corpus import conferencia as modulo

    html = (
        "<html><head><title>x</title></head><body><p>Olá,&nbsp;mundo</p></body></html>"
    )
    resposta = _Resposta(html.encode("iso-8859-1"), "text/html; charset=iso-8859-1")
    original = modulo.baixar
    monkeypatch.setattr(modulo, "baixar", lambda url: original(url, _Abridor(resposta)))
    assert conferencia.ler_da_rede("https://exemplo.com.br/a") == "Olá, mundo"

    livro = openpyxl.Workbook()
    aba = livro.active
    assert aba is not None
    aba.append(["BRASIL", "GLP", 3301, "R$/13kg", 114.8])
    saida = io.BytesIO()
    livro.save(saida)
    planilha = saida.getvalue()
    monkeypatch.setattr(
        modulo,
        "baixar",
        lambda url: modulo.Documento(url, planilha, "application/octet-stream"),
    )
    assert conferencia.ler_da_rede("https://exemplo.com.br/p.xlsx") == (
        "BRASIL | GLP | 3301 | R$/13kg | 114.8"
    )
