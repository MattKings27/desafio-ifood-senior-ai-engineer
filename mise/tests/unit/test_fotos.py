"""As fotos: só com licença livre e crédito, pelo proxy, e a da receita pela página lida."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import receitas_de_teste as rt

from mise import categorias
from mise.catalogo import chave_da_imagem
from mise.despensa import OrigemDoItem
from mise.dossie import Canal
from mise.fotos import (
    ARQUIVO_DAS_FOTOS,
    ARQUIVO_DAS_FOTOS_DA_COZINHA,
    CREDITO_DA_PAGINA,
    LICENCA_LIVRE,
    VAR_FOTOS,
    VAR_FOTOS_DA_COZINHA,
    caminho_das_fotos,
    foto_do_registro,
    foto_pela_chave,
    fotos_da_cozinha,
    fotos_dos_itens,
    imagem_do_item,
    ler_fotos,
)
from mise.mcp_server import abrir_sessao

RAIZ = Path(__file__).resolve().parents[3]
DADOS = RAIZ / "dados" / ARQUIVO_DAS_FOTOS

IMAGEM = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Capers.jpg/960px-Capers.jpg"
PAGINA = "https://commons.wikimedia.org/wiki/File:Capers.jpg"


def _linha(**extra: Any) -> dict[str, Any]:
    linha = {
        "item_id": "alcaparras",
        "arquivo": "File:Capers.jpg",
        "pagina": PAGINA,
        "imagem": IMAGEM,
        "licenca": "CC BY-SA 4.0",
        "autor": "Fulana de Tal",
        "credito": "Foto: Fulana de Tal, CC BY-SA 4.0, Wikimedia Commons",
    }
    linha.update(extra)
    return linha


@pytest.mark.parametrize(
    "licenca",
    ["CC0", "CC0 1.0", "Public domain", "PD-self", "CC BY 2.0", "CC BY-SA 4.0", "CC BY-SA 3.0 de"],
)
def test_licenca_livre(licenca: str) -> None:
    assert LICENCA_LIVRE.match(licenca)


@pytest.mark.parametrize(
    "licenca",
    [
        "CC BY-NC 2.0",
        "CC BY-NC-SA 4.0",
        "CC BY-ND 4.0",
        "GFDL",
        "All rights reserved",
        "CC BY 4.0 nc",
    ],
)
def test_licenca_que_nao_e_livre(licenca: str) -> None:
    assert not LICENCA_LIVRE.match(licenca)


def test_a_linha_certa_vira_foto() -> None:
    foto = foto_do_registro(_linha())
    assert (foto.url, foto.licenca, foto.fonte_url) == (IMAGEM, "CC BY-SA 4.0", PAGINA)
    assert foto.para_tela() == {
        "url": f"/motor/imagens/{chave_da_imagem(IMAGEM)}",
        "credito": "Foto: Fulana de Tal, CC BY-SA 4.0, Wikimedia Commons",
    }
    assert foto.credito_json() == {
        "credito": "Foto: Fulana de Tal, CC BY-SA 4.0, Wikimedia Commons",
        "licenca": "CC BY-SA 4.0",
        "fonte_url": PAGINA,
    }


@pytest.mark.parametrize(
    ("extra", "motivo"),
    [
        (
            {
                "licenca": "CC BY-NC-SA 2.0",
                "credito": "Foto: Fulana de Tal, CC BY-NC-SA 2.0, Wikimedia Commons",
            },
            "não é livre",
        ),
        ({"imagem": "http://upload.wikimedia.org/x.jpg"}, "a imagem precisa ser"),
        ({"imagem": "https://exemplo.com/x.jpg"}, "a imagem precisa ser"),
        ({"imagem": "https://[::1"}, "a imagem precisa ser"),
        ({"imagem": 123}, "falta"),
        ({"pagina": "https://pt.wikipedia.org/wiki/Alcaparra"}, "a página precisa ser"),
        ({"autor": ""}, "falta"),
        ({"credito": "Foto: Wikimedia Commons"}, "o crédito precisa ser"),
        ({"item_id": None}, "falta"),
    ],
)
def test_a_linha_fora_da_regra_e_recusada(extra: dict[str, Any], motivo: str) -> None:
    with pytest.raises(ValueError, match=motivo):
        foto_do_registro(_linha(**extra))


def test_o_arquivo_de_fotos_pula_a_linha_ruim(tmp_path: Path) -> None:
    arquivo = tmp_path / "fotos.json"
    arquivo.write_text(
        json.dumps({"fotos": [_linha(), _linha(item_id="bacon", licenca="GFDL")]}),
        encoding="utf-8",
    )
    fotos = ler_fotos(arquivo)
    assert list(fotos) == ["alcaparras"]
    assert ler_fotos(tmp_path / "nao-existe.json") == {}
    quebrado = tmp_path / "quebrado.json"
    quebrado.write_text("{", encoding="utf-8")
    assert ler_fotos(quebrado) == {}


def test_o_arquivo_fica_ao_lado_da_planilha_ou_onde_a_variavel_diz(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    assert caminho_das_fotos(sessao.planilha, {}) == RAIZ / "dados" / ARQUIVO_DAS_FOTOS
    assert caminho_das_fotos(sessao.planilha, {VAR_FOTOS: "/tmp/outro.json"}) == Path(
        "/tmp/outro.json"
    )


def test_a_foto_do_item_e_a_da_receita_pela_chave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    arquivo = tmp_path / "fotos.json"
    arquivo.write_text(json.dumps({"fotos": [_linha()]}), encoding="utf-8")
    monkeypatch.setenv(VAR_FOTOS, str(arquivo))
    sessao = rt.sessao_nova(tmp_path)
    alcaparras = sessao.despensa["Alcaparras"]
    assert imagem_do_item(sessao.despensa, alcaparras) == foto_do_registro(_linha()).para_tela()
    assert imagem_do_item(sessao.despensa, sessao.despensa["Bacon"]) is None
    sessao.editavel.adicionar(
        nome="Alcaparra graúda",
        estoque=Decimal(1),
        unidade="kg",
        origem=OrigemDoItem.JA_TINHA,
        canal=Canal.TELA,
    )
    nova = sessao.despensa["Alcaparra graúda"]
    assert imagem_do_item(sessao.despensa, nova) is None, "o item que ela acrescenta não tem foto"

    do_item = foto_pela_chave(sessao, chave_da_imagem(IMAGEM))
    assert do_item is not None and do_item.licenca == "CC BY-SA 4.0"
    carne = rt.da_web(sessao, rt.CARNE_URL, rt.CARNE)
    da_receita = foto_pela_chave(sessao, chave_da_imagem(rt.FOTO))
    assert da_receita is not None
    assert (da_receita.url, da_receita.credito, da_receita.fonte_url) == (
        rt.FOTO,
        "Foto: TudoGostoso",
        carne.url,
    )
    assert foto_pela_chave(sessao, "0" * 32) is None


def test_foto_da_receita_sem_site_leva_o_credito_da_pagina(tmp_path: Path) -> None:
    sessao = rt.sessao_nova(tmp_path)
    sem_site = rt.pagina(
        "Pão", ["500 g de farinha de trigo"], ["Asse no forno."], site=None, imagem=rt.FOTO
    )
    rt.da_web(sessao, "https://exemplo.com.br/pao", sem_site)
    foto = foto_pela_chave(sessao, chave_da_imagem(rt.FOTO))
    assert foto is not None
    assert foto.credito in {"Foto: exemplo.com.br", CREDITO_DA_PAGINA}


def test_o_arquivo_versionado_cobre_os_37_itens_da_planilha(tmp_path: Path) -> None:
    """Cada item da planilha tem a foto conferida no Commons, ou o motivo de não ter."""
    dados = json.loads(DADOS.read_text(encoding="utf-8"))
    com_foto = [linha["item_id"] for linha in dados["fotos"]]
    sem_foto = [linha["item_id"] for linha in dados["sem_foto"]]
    assert sorted(com_foto + sem_foto) == sorted(categorias.DA_PLANILHA), "um de cada, sem repetir"
    assert len(com_foto) == 36
    for linha in dados["fotos"]:
        foto = foto_do_registro(linha)
        assert foto.credito.startswith("Foto: ") and foto.credito.endswith(", Wikimedia Commons")
    for linha in dados["sem_foto"]:
        assert linha["motivo"].strip()
    assert len({linha["imagem"] for linha in dados["fotos"]}) == len(com_foto), "uma foto por item"
    sessao = abrir_sessao(planilha=rt.PLANILHA, banco=tmp_path / "dossie.db")
    assert set(fotos_dos_itens(sessao.planilha)) == set(com_foto)
    adocante = sessao.despensa["Adoçante líquido"]
    assert imagem_do_item(sessao.despensa, adocante) is None


def test_a_cozinha_tem_o_proprio_arquivo_ao_lado_da_planilha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uma miniatura por equipamento e técnica, pelo mesmo registro do proxy."""
    from mise.taxonomia import EQUIPAMENTOS, TECNICAS

    monkeypatch.delenv(VAR_FOTOS_DA_COZINHA, raising=False)
    sessao = rt.sessao_nova(tmp_path)
    caminho = caminho_das_fotos(
        sessao.planilha, {}, variavel=VAR_FOTOS_DA_COZINHA, arquivo=ARQUIVO_DAS_FOTOS_DA_COZINHA
    )
    assert caminho == RAIZ / "dados" / ARQUIVO_DAS_FOTOS_DA_COZINHA
    fotos = fotos_da_cozinha(sessao.planilha)
    vocabulario = {e.id for e in EQUIPAMENTOS} | {t.id for t in TECNICAS}
    assert set(fotos) == vocabulario - {"reducao"}, "sem foto livre que mostre, fica o ícone"
    forno = fotos["forno"]
    assert forno.url.startswith("https://thumb.wikimedia.org/") and "/250px-" in forno.url
    assert foto_pela_chave(sessao, forno.chave) == forno

    arquivo = tmp_path / "cozinha.json"
    arquivo.write_text(
        json.dumps({"fotos": [_linha(item_id="forno"), _linha(item_id="fogao", licenca="GFDL")]}),
        encoding="utf-8",
    )
    monkeypatch.setenv(VAR_FOTOS_DA_COZINHA, str(arquivo))
    assert list(fotos_da_cozinha(sessao.planilha)) == ["forno"], "sem licença livre, não entra"
    assert foto_pela_chave(sessao, chave_da_imagem(IMAGEM)) is not None
