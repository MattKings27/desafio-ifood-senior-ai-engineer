"""Uma sessão do motor com receitas em avaliação, para os testes da conversa.

O arroz com frango passa pelo portão (cozinha confirmada, gosto confirmado): é o
prato que tem custo, preço e decisão, e é a receita que ela ditou. O bolo de
fubá vem da internet, pela página que o servidor leu (o HTML fica aqui, sem
rede), e pede coco ralado, que a despensa não tem.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mise.dossie import Dossie
from mise.mcp_server import ReceitaEntrada, Sessao, abrir_sessao
from mise.perfil import Gosto, PerfilCozinha, Posse
from mise.receita import Receita

PLANILHA = Path(__file__).resolve().parents[2] / "dados" / "despensa_dona_maria.xlsx"

ARROZ_COM_FRANGO: dict[str, Any] = {
    "nome": "Arroz com frango",
    "rendimento_porcoes": 4,
    "tempo_cozimento_min": 40,
    "modo_preparo": ["Refogue a cebola.", "Junte o frango e o arroz e cozinhe na panela."],
    "ingredientes": [
        {"texto": "500 g de frango", "nome": "peito de frango", "quantidade": 500, "medida": "g"},
        {"texto": "1 kg de arroz", "nome": "arroz", "quantidade": 1, "medida": "kg"},
        {"texto": "sal a gosto", "nome": "sal"},
    ],
}

BOLO_DA_WEB: dict[str, Any] = {
    "nome": "Bolo de fubá",
    "rendimento_porcoes": 8,
    "modo_preparo": ["Bata tudo no liquidificador por 3 minutos.", "Leve ao forno por 40 minutos."],
    "url": "https://www.tudogostoso.com.br/receita/123-bolo-de-fuba/?utm_source=x#topo",
    "fonte": "TudoGostoso",
    "ingredientes": [
        {"texto": "2 xícaras de fubá", "nome": "fubá", "quantidade": 2, "medida": "xicara"},
        {
            "texto": "1 xícara de coco ralado",
            "nome": "coco ralado",
            "quantidade": 1,
            "medida": "xicara",
        },
    ],
}


def preparar_dossie(banco: Path, *, aprovada: bool = True) -> None:
    """A cozinha toda confirmada e o gosto pelo arroz com frango: o portão libera."""
    if not aprovada:
        return
    with Dossie(banco) as dossie:
        perfil = PerfilCozinha.inicial()
        perfil = perfil.com_equipamentos((e, Posse.TEM) for e in perfil.equipamentos)
        perfil = perfil.com_tecnicas((t, Posse.TEM) for t in perfil.tecnicas)
        dossie.salvar_perfil(
            perfil.com_restricao("bocas_fogao", 4).com_restricao("tempo_max_por_fornada_min", 120)
        )
        dossie.registrar_gosto("Arroz com frango", Gosto.GOSTA)


def pagina_do_bolo() -> str:
    """A página do bolo de fubá, com a receita em JSON-LD, como o site publica."""
    objeto = {
        "@type": "Recipe",
        "name": BOLO_DA_WEB["nome"],
        "recipeYield": str(BOLO_DA_WEB["rendimento_porcoes"]),
        "publisher": {"@type": "Organization", "name": BOLO_DA_WEB["fonte"]},
        "recipeIngredient": [i["texto"] for i in BOLO_DA_WEB["ingredientes"]],
        "recipeInstructions": BOLO_DA_WEB["modo_preparo"],
    }
    return f'<script type="application/ld+json">{json.dumps(objeto)}</script>'


def guardar_da_pagina(sessao: Sessao, html: str, url: str) -> Receita:
    """O que `buscar_receita_na_web` faz depois de trazer a página: ler e guardar no catálogo."""
    from mise.catalogo import OrigemNoCatalogo
    from retrieval.extrator import extrair

    return sessao.catalogar(extrair(html, url), OrigemNoCatalogo.CONVERSA).receita


def guardar_receitas(sessao: Sessao) -> Sessao:
    arroz, _ = sessao.receita_para_avaliar(None, ReceitaEntrada(**ARROZ_COM_FRANGO))
    sessao.guardar(arroz)
    sessao.guardar(guardar_da_pagina(sessao, pagina_do_bolo(), BOLO_DA_WEB["url"]))
    return sessao


def sessao_com_receitas(pasta: Path, *, aprovada: bool = True) -> Sessao:
    banco = pasta / "dossie.db"
    preparar_dossie(banco, aprovada=aprovada)
    return guardar_receitas(abrir_sessao(PLANILHA, banco))
