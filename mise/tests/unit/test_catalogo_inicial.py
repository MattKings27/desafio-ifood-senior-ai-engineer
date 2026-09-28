"""A semente do catálogo: um clone novo abre a tela de Receitas cheia."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mise.catalogo import Catalogo, semear_o_catalogo
from mise.dossie import Dossie
from mise.mcp_server import abrir_sessao

RAIZ = Path(__file__).resolve().parents[3]
SEMENTE = RAIZ / "dados" / "catalogo_inicial.json"
PLANILHA = RAIZ / "dados" / "despensa_dona_maria.xlsx"


def test_a_semente_do_repositorio_so_tem_receita_da_web_sem_resposta_dela() -> None:
    receitas = json.loads(SEMENTE.read_text(encoding="utf-8"))
    assert receitas
    for receita in receitas:
        assert receita["url_canonica"], receita["nome"]
        assert receita["origem"] != "dita"
        assert receita["respostas"] == "[]"


def test_o_catalogo_vazio_recebe_a_semente_inteira(tmp_path: Path) -> None:
    dossie = Dossie(tmp_path / "dossie.db")
    total = len(json.loads(SEMENTE.read_text(encoding="utf-8")))
    assert semear_o_catalogo(dossie, SEMENTE) == total
    assert len(Catalogo(dossie).listar()) == total
    dossie.fechar()


def test_com_receita_no_catalogo_a_semente_nao_entra_de_novo(tmp_path: Path) -> None:
    dossie = Dossie(tmp_path / "dossie.db")
    semear_o_catalogo(dossie, SEMENTE)
    assert semear_o_catalogo(dossie, SEMENTE) == 0
    dossie.fechar()


def test_sem_arquivo_nada_acontece(tmp_path: Path) -> None:
    dossie = Dossie(tmp_path / "dossie.db")
    assert semear_o_catalogo(dossie, tmp_path / "nao-existe.json") == 0
    dossie.fechar()


def test_a_sessao_so_semeia_quando_a_variavel_aponta_a_semente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MISE_CATALOGO_INICIAL", raising=False)
    sem = abrir_sessao(PLANILHA, tmp_path / "sem.db")
    assert Catalogo(sem.dossie).listar() == ()
    sem.dossie.fechar()
    monkeypatch.setenv("MISE_CATALOGO_INICIAL", str(SEMENTE))
    com = abrir_sessao(PLANILHA, tmp_path / "com.db")
    assert Catalogo(com.dossie).listar()
    com.dossie.fechar()
