"""Receitas para os testes do catálogo e da grade, lidas como o servidor lê.

A receita da internet entra no catálogo pela página, com o JSON-LD passando
pelo extrator de verdade, sem rede: é o mesmo caminho de `buscar_receita_na_web`
depois que a página chega.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from retrieval.extrator import extrair

from mise.catalogo import OrigemNoCatalogo, ReceitaDoCatalogo
from mise.mcp_server import ReceitaEntrada, Sessao, abrir_sessao
from mise.perfil import PerfilCozinha, Posse

PLANILHA = Path(__file__).resolve().parents[3] / "dados" / "despensa_dona_maria.xlsx"

FOTO = "https://static.tudogostoso.com.br/fotos/22090.jpg"


def pagina(
    nome: str,
    ingredientes: list[str],
    passos: list[str],
    *,
    rende: str = "4 porções",
    site: str | None = "TudoGostoso",
    imagem: Any = None,
    tempos: tuple[str, str, str] | None = ("PT15M", "PT30M", "PT45M"),
    autor: str | None = "Leuda",
) -> str:
    """O HTML de uma página com a receita em JSON-LD."""
    objeto: dict[str, Any] = {
        "@type": "Recipe",
        "name": nome,
        "recipeYield": rende,
        "recipeIngredient": ingredientes,
        "recipeInstructions": passos,
    }
    if site:
        objeto["publisher"] = {"@type": "Organization", "name": site}
    if autor:
        objeto["author"] = {"@type": "Person", "name": autor}
    if imagem is not None:
        objeto["image"] = imagem
    if tempos is not None:
        objeto["prepTime"], objeto["cookTime"], objeto["totalTime"] = tempos
    return f'<script type="application/ld+json">{json.dumps(objeto)}</script>'


def da_web(
    sessao: Sessao,
    url: str,
    html: str,
    origem: OrigemNoCatalogo = OrigemNoCatalogo.DESCOBERTA,
) -> ReceitaDoCatalogo:
    """A página lida e guardada no catálogo, como a busca faz."""
    return sessao.catalogar(extrair(html, url), origem)


def ditada(sessao: Sessao, **receita: Any) -> ReceitaDoCatalogo:
    """A receita que ela dita, pelo caminho da conversa."""
    feita, _ = sessao.receita_para_avaliar(None, ReceitaEntrada(**receita))
    guardada = sessao.catalogo.por_nome(feita.nome)
    assert guardada is not None
    return guardada


def cozinha_confirmada(sessao: Sessao, *, bocas: int = 4, minutos: int = 240) -> None:
    """Tudo o que a cozinha tem e sabe, e a rotina dita: a conferência só olha a despensa."""
    perfil = PerfilCozinha.inicial()
    perfil = perfil.com_equipamentos((e, Posse.TEM) for e in perfil.equipamentos)
    perfil = perfil.com_tecnicas((t, Posse.TEM) for t in perfil.tecnicas)
    sessao.dossie.salvar_perfil(
        perfil.com_restricao("bocas_fogao", bocas)
        .com_restricao("tempo_max_por_fornada_min", minutos)
        .com_restricao("tem_gas_sobrando", True)
        .com_restricao("espaco_geladeira_litros", 30)
        .com_restricao("energia_aparelhos_simultaneos", 3)
        .com_restricao("porcoes_por_fornada", 20)
    )


def sessao_nova(pasta: Path) -> Sessao:
    return abrir_sessao(planilha=PLANILHA, banco=pasta / "dossie.db")


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

CARNE_URL = "https://www.tudogostoso.com.br/receita/22090-carne-moida-com-arroz.html"
CARNE = pagina(
    "Carne moída com arroz na panela",
    [
        "500 g de carne moída",
        "2 xícaras de arroz",
        "1 cebola picada",
        "2 dentes de alho",
        "2 colheres de sopa de óleo",
        "1 lata de milho verde",
        "sal a gosto",
        "cheiro-verde a gosto (opcional)",
        "temperos de sua preferência",
    ],
    [
        "Refogue a cebola e o alho no óleo.",
        "Junte a carne moída e deixe dourar bem.",
        "Acrescente o arroz e a água e cozinhe por 20 minutos.",
    ],
    imagem=FOTO,
)

MILHO_URL = "https://www.tudogostoso.com.br/receita/1-frango-com-milho.html"
MILHO = pagina(
    "Frango com milho verde",
    [
        "500 g de peito de frango",
        "1 lata de milho verde",
        "1 cebola",
        "2 colheres de sopa de óleo",
        "sal a gosto",
    ],
    ["Refogue a cebola no óleo.", "Junte o frango e cozinhe por 25 minutos.", "Junte o milho."],
    imagem={"@type": "ImageObject", "url": "/fotos/frango.jpg"},
    tempos=("PT10M", "PT25M", ""),
)

BOLO_URL = "https://www.panelinha.com.br/receita/bolo-no-forno"
BOLO = pagina(
    "Bolo de fubá",
    ["2 xícaras de fubá", "3 ovos", "1 xícara de leite"],
    ["Bata tudo.", "Asse no forno por 40 minutos."],
    site="Panelinha",
    tempos=None,
    autor=None,
)
