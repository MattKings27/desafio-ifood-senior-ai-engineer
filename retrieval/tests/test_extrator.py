"""Extração de receita a partir de página real.

Os testes usam HTML salvo, não rede. Um teste que depende da internet falha por
motivo que não é o seu, e um portão que falha por motivo alheio é um portão que
alguém desliga.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from mise.receita import Origem

from retrieval.extrator import (
    ExtracaoFalhou,
    de_json_ld,
    de_microdata,
    duracao_em_minutos,
    extrair,
    imagem_da_pagina,
    para_receita,
    rendimento_em_porcoes,
)

URL = "https://www.tudogostoso.com.br/receita/123-bolo-de-cenoura"


# --------------------------------------------------------------------------- #
# JSON-LD                                                                      #
# --------------------------------------------------------------------------- #


def test_extrai_do_grafo(html) -> None:
    """`@graph` com WebSite e Recipe juntos é o formato mais comum."""
    r = extrair(html("tudogostoso_bolo.html"), URL)

    assert r.receita.nome == "Bolo de cenoura com cobertura"
    assert r.receita.rendimento_porcoes == 12
    assert r.autor == "Dona Cida"


def test_os_tres_tempos_ficam_separados(html) -> None:
    """Preparo, cozimento e total como o site publica: o total não vira tempo de fogo."""
    r = extrair(html("tudogostoso_bolo.html"), URL)

    assert r.receita.tempo_preparo_min == 20
    assert r.receita.tempo_cozimento_min == 40
    assert r.receita.tempo_total_min == 60
    assert r.receita.tempo_declarado_min == 60


def test_so_o_tempo_de_cozimento() -> None:
    objeto = {
        "@type": "Recipe",
        "name": "Arroz",
        "recipeIngredient": ["1 xícara de arroz"],
        "cookTime": "PT25M",
    }
    r = para_receita(objeto, URL)

    assert (r.receita.tempo_preparo_min, r.receita.tempo_total_min) == (None, None)
    assert r.receita.tempo_cozimento_min == 25


def test_ingredientes_saem_interpretados(html) -> None:
    r = extrair(html("tudogostoso_bolo.html"), URL)
    por_nome = {i.nome: i for i in r.receita.ingredientes}

    assert por_nome["açúcar"].quantidade == Decimal(2)
    assert por_nome["açúcar"].medida == "xicara de cha"
    assert por_nome["óleo"].quantidade == Decimal("0.5")
    assert por_nome["farinha de trigo"].quantidade == Decimal("2.5")
    assert por_nome["Sal"].a_gosto


def test_equipamento_e_detectado_do_modo_de_preparo(html) -> None:
    """O portão precisa saber que a receita usa forno e liquidificador."""
    r = extrair(html("tudogostoso_bolo.html"), URL)
    assert {"forno", "liquidificador"} <= r.receita.equipamentos


def test_procedencia_vem_junto(html) -> None:
    r = extrair(html("tudogostoso_bolo.html"), URL)

    assert r.receita.origem is Origem.WEB
    assert r.receita.url == URL
    assert r.receita.fonte == "tudogostoso.com.br"
    assert r.receita.tem_procedencia
    assert "tudogostoso.com.br" in r.receita.citacao


def test_deteccao_preserva_a_origem(html) -> None:
    """Regressão: `com_exigencias_detectadas` reconstruía a receita e perdia `origem`.

    A receita saía da web e voltava marcada como informada por ela, sem nenhum
    erro: procedência perdida em silêncio.
    """
    r = extrair(html("tudogostoso_bolo.html"), URL)
    assert r.receita.com_exigencias_detectadas().origem is Origem.WEB


def test_bloco_quebrado_nao_derruba_a_extracao(html) -> None:
    """Sites põem vários blocos; basta um estar bom."""
    r = extrair(html("json_quebrado.html"), "https://exemplo.com.br/arroz")
    assert r.receita.nome == "Arroz simples"


def test_pagina_sem_receita_falha_dizendo_por_que(html) -> None:
    with pytest.raises(ExtracaoFalhou, match="ingrediente"):
        extrair(html("sem_receita.html"), "https://exemplo.com.br/lista")


def test_json_ld_sem_recipe_e_recusado(html) -> None:
    with pytest.raises(ExtracaoFalhou, match="Recipe"):
        de_json_ld(html("sem_receita.html"))


# --------------------------------------------------------------------------- #
# Microdata                                                                    #
# --------------------------------------------------------------------------- #


def test_microdata_quando_nao_ha_json_ld(html) -> None:
    r = extrair(html("microdata_brigadeiro.html"), "https://exemplo.com.br/brigadeiro")

    assert r.receita.nome == "Brigadeiro de panela"
    assert r.receita.rendimento_porcoes == 30
    assert r.receita.tempo_total_min == 25
    assert (r.receita.tempo_preparo_min, r.receita.tempo_cozimento_min) == (None, None)
    assert len(r.receita.ingredientes) == 4


def test_microdata_com_os_tempos_separados() -> None:
    html = (
        '<div itemscope itemtype="http://schema.org/Recipe">'
        '<h1 itemprop="name">Feijão</h1>'
        '<meta itemprop="prepTime" content="PT10M">'
        '<meta itemprop="cookTime" content="PT1H">'
        '<li itemprop="recipeIngredient">1 kg de feijão</li></div>'
    )
    r = extrair(html, "https://exemplo.com.br/feijao")

    assert (r.receita.tempo_preparo_min, r.receita.tempo_cozimento_min) == (10, 60)
    assert r.receita.tempo_total_min is None


def test_microdata_interpreta_embalagem(html) -> None:
    r = extrair(html("microdata_brigadeiro.html"), "https://exemplo.com.br/brigadeiro")
    nomes = {i.nome for i in r.receita.ingredientes}
    assert "leite condensado" in nomes


def test_microdata_sem_ingrediente_falha(html) -> None:
    with pytest.raises(ExtracaoFalhou, match="itemprop"):
        de_microdata(html("sem_receita.html"))


# --------------------------------------------------------------------------- #
# Duração e rendimento                                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("PT1H30M", 90),
        ("PT45M", 45),
        ("PT2H", 120),
        ("P1DT2H", 1560),
        ("40 minutos", 40),
        ("", None),
        ("PT0M", None),
        ("sem tempo", None),
    ],
)
def test_duracao(bruto: str, esperado: int | None) -> None:
    """Zero vira `None`: zero seria lido como instantâneo e dispensaria a checagem."""
    assert duracao_em_minutos(bruto) == esperado


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("12 porções", 12),
        ("Rende 6", 6),
        ("serve 2 pessoas", 2),
        (8, 8),
        ("", 1),
        ("a vontade", 1),
        ("0 porções", 1),
    ],
)
def test_rendimento(bruto: object, esperado: int) -> None:
    """Sem número reconhecível, 1 porção.

    Chutar para cima dividiria o custo por porções que não existem e faria o
    prato parecer mais barato do que é.
    """
    assert rendimento_em_porcoes(bruto) == esperado


# --------------------------------------------------------------------------- #
# Procedência como invariante                                                  #
# --------------------------------------------------------------------------- #


def test_receita_da_web_sem_url_e_impossivel() -> None:
    """O tipo recusa antes de qualquer uso: não é disciplina de quem constrói."""
    from mise.erros import SemProcedencia
    from mise.receita import Receita, ingrediente

    with pytest.raises(SemProcedencia, match="endereço"):
        Receita(
            nome="Bolo sem fonte",
            ingredientes=(ingrediente("2 ovos", "ovos", 2, "ovo"),),
            origem=Origem.WEB,
        )


def test_receita_informada_por_ela_nao_precisa_de_url() -> None:
    from mise.receita import Receita, ingrediente

    r = Receita(
        nome="Bolo da vó",
        ingredientes=(ingrediente("2 ovos", "ovos", 2, "ovo"),),
        origem=Origem.INFORMADA_POR_ELA,
    )
    assert not r.tem_procedencia
    assert "a senhora me passou" in r.citacao


# --------------------------------------------------------------------------- #
# Formas que o schema.org aceita e os sites usam                               #
# --------------------------------------------------------------------------- #


def test_receita_extraida_se_apresenta(html) -> None:
    r = extrair(html("tudogostoso_bolo.html"), URL)
    assert str(r) == "Bolo de cenoura com cobertura (tudogostoso.com.br)"


@pytest.mark.parametrize(
    ("objeto", "esperado"),
    [
        ({"name": "Bolo"}, "Bolo"),
        ({"text": "passo"}, "passo"),
        ({"@value": "valor"}, "valor"),
        ({"sem_nada": 1}, ""),
        (["a", "b"], "a b"),
        (42, ""),
        (None, ""),
    ],
)
def test_texto_aceita_as_formas_do_schema(objeto: object, esperado: str) -> None:
    """schema.org aceita string, objeto ou lista no mesmo campo, e os sites usam todas."""
    from retrieval.extrator import _texto

    assert _texto(objeto) == esperado


def test_instrucao_como_string_unica_vira_lista() -> None:
    """Muito site põe o modo de preparo inteiro num parágrafo só."""
    from retrieval.extrator import para_receita

    r = para_receita(
        {
            "name": "Arroz",
            "recipeIngredient": ["1 xícara de arroz"],
            "recipeInstructions": "Refogue e cozinhe na panela.",
        },
        "https://exemplo.com.br/arroz",
    )
    assert r.receita.modo_preparo == ("Refogue e cozinhe na panela.",)


def test_receita_sem_ingrediente_nenhum_e_recusada() -> None:
    from retrieval.extrator import para_receita

    with pytest.raises(ExtracaoFalhou, match="lista de ingredientes"):
        para_receita({"name": "Vazia"}, "https://exemplo.com.br/x")


def test_achatar_ignora_no_que_nao_e_objeto() -> None:
    from retrieval.extrator import _achatar

    assert _achatar("texto solto") == []
    assert _achatar(7) == []


def test_tipo_em_lista_e_reconhecido() -> None:
    """`"@type": ["Recipe", "NewsArticle"]` aparece em site de portal."""
    from retrieval.extrator import _e_receita

    assert _e_receita({"@type": ["NewsArticle", "Recipe"]})
    assert not _e_receita({"@type": ["NewsArticle"]})
    assert not _e_receita({})


def test_fonte_explicita_vence_o_dominio() -> None:
    r = extrair(html_simples(), "https://exemplo.com.br/x", fonte="Caderno da Vó")
    assert r.fonte == "Caderno da Vó"
    assert r.receita.fonte == "Caderno da Vó"


def html_simples() -> str:
    return (
        '<script type="application/ld+json">'
        '{"@type":"Recipe","name":"Arroz","recipeIngredient":["1 xícara de arroz"]}'
        "</script>"
    )


# --------------------------------------------------------------------------- #
# Dados reais que os sites publicam errado
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("bruto", "informado"),
    [
        ("4 porções", True),
        ("serve 8 pessoas", True),
        (6, True),
        ("46", False),  # "4 a 6" publicado como "46" num site de receita real
        (46, False),
        ("30 unidades", True),  # brigadeiro: número grande, mas dito do quê
        ("500 g", False),
        ("30 minutos", False),
        (None, False),
    ],
)
def test_rendimento_informado_so_quando_da_para_confiar(bruto: object, informado: bool) -> None:
    from retrieval.extrator import rendimento_informado

    assert rendimento_informado(bruto) is informado


def test_lista_numa_string_so_vira_uma_linha_por_ingrediente() -> None:
    """Um site real publica os ingredientes todos num item, separados por quebra de linha."""
    pagina = (
        '<script type="application/ld+json">'
        '{"@type":"Recipe","name":"Espaguete","recipeYield":"46",'
        '"recipeIngredient":["1/2 kg de espaguete\\nSal\\n4 dentes de alho em lâminas"],'
        '"recipeInstructions":"Cozinhe a massa.\\nRefogue o alho."}</script>'
    )
    receita = extrair(pagina, "https://exemplo.com.br/espaguete").receita
    assert [i.texto_original for i in receita.ingredientes] == [
        "1/2 kg de espaguete",
        "Sal",
        "4 dentes de alho em lâminas",
    ]
    assert receita.modo_preparo == ("Cozinhe a massa.", "Refogue o alho.")
    assert not receita.rendimento_informado, "46 porções de meio quilo de massa: pergunta"


# --------------------------------------------------------------------------- #
# A foto: a maior que a página declara, e nunca a genérica                      #
# --------------------------------------------------------------------------- #

PAGINA = "https://www.receiteria.com.br/receita/bola-de-carne-moida"
PLACEHOLDER = "https://static.itdg.com.br/images/1200-675/default/placeholder-img-default-tdg.png"


def test_da_lista_vale_a_original_de_que_sairam_os_recortes() -> None:
    """WordPress declara a original e os recortes: a original, sem sufixo, é a maior."""
    base = "https://www.receiteria.com.br/wp-content/uploads/bola"
    lista = [f"{base}-400x400.jpg", f"{base}.jpg", f"{base}-730x480.jpg", f"{base}-400x220.jpg"]
    assert imagem_da_pagina(lista, PAGINA) == f"{base}.jpg"


def test_da_lista_vale_a_maior_pelo_tamanho_declarado() -> None:
    lista = [
        {"@type": "ImageObject", "url": "/p.jpg", "width": 300, "height": "200"},
        {"@type": "ImageObject", "url": "/g.jpg", "width": "1200px", "height": {"@value": 800}},
        {"@type": "ImageObject", "contentUrl": "/m.jpg", "width": 800, "height": 600},
    ]
    assert imagem_da_pagina(lista, PAGINA) == "https://www.receiteria.com.br/g.jpg"


def test_sem_tamanho_vale_a_primeira() -> None:
    lista = ["https://site.com.br/a.webp", "https://site.com.br/b.webp"]
    assert imagem_da_pagina(lista, PAGINA) == "https://site.com.br/a.webp"


def test_o_tamanho_no_caminho_conta() -> None:
    lista = ["https://img.com/images/300-200/a.jpg", "https://img.com/images/1200-675/b.jpg"]
    assert imagem_da_pagina(lista, PAGINA) == "https://img.com/images/1200-675/b.jpg"


@pytest.mark.parametrize(
    "bruto",
    [
        {"@type": "ImageObject", "url": PLACEHOLDER},
        [PLACEHOLDER],
        "https://site.com.br/img/sem-foto.png",
        "None",
        "null",
        "data:image/png;base64,AAAA",
        "",
        None,
        [{"@id": "#foto"}],
    ],
)
def test_foto_generica_ou_quebrada_fica_de_fora(bruto: object) -> None:
    """O chapéu cinza do TudoGostoso não é a foto do prato: sem foto, a tela mostra o gradiente."""
    assert imagem_da_pagina(bruto, PAGINA) is None


def test_a_generica_na_lista_nao_tira_a_verdadeira() -> None:
    real = "https://static.itdg.com.br/images/1200-675/abc/241034-original.jpg"
    assert imagem_da_pagina([PLACEHOLDER, real], PAGINA) == real


def _pagina(receita: dict[str, object], cabeca: str = "") -> str:
    return (
        f"<html><head>{cabeca}<script type='application/ld+json'>{json.dumps(receita)}"
        "</script></head><body></body></html>"
    )


RECEITA = {
    "@type": "Recipe",
    "name": "Peixe com limão",
    "recipeIngredient": ["2 postas de peixe", "1 limão"],
    "recipeInstructions": ["Tempere o peixe."],
}


def test_sem_foto_na_receita_vale_a_do_compartilhamento() -> None:
    """A receita estruturada sem foto: vale a que a página declara para compartilhar."""
    og = "<meta property='og:image' content='https://img.globo.com/peixe-1920x0.jpg'>"
    r = extrair(_pagina(RECEITA, og), PAGINA)
    assert r.imagem_url == "https://img.globo.com/peixe-1920x0.jpg"


def test_a_foto_da_receita_vale_mais_que_a_do_compartilhamento() -> None:
    og = "<meta property='og:image' content='https://img.globo.com/logo.jpg'>"
    r = extrair(_pagina({**RECEITA, "image": "https://img.globo.com/prato.jpg"}, og), PAGINA)
    assert r.imagem_url == "https://img.globo.com/prato.jpg"


def test_compartilhamento_sem_foto_de_verdade_fica_sem_foto() -> None:
    """A página que escreve "None" no lugar da foto não ganha foto chamada None."""
    og = "<meta name='description' content='x'><meta property='og:image' content='None'>"
    assert extrair(_pagina(RECEITA, og), PAGINA).imagem_url is None


def test_texto_sem_entidade_e_sem_etiqueta() -> None:
    """Entidade escapada duas vezes e etiqueta escapada saíam na tela como estavam."""
    receita = {
        **RECEITA,
        "recipeIngredient": ["500g de &lt;b&gt;Alcatra&lt;/b&gt; em cubos", "Sal a gosto"],
        "recipeInstructions": ["Tempere com o lim&amp;atilde;o.<br>Sirva."],
    }
    r = extrair(_pagina(receita), PAGINA)
    assert r.receita.ingredientes[0].nome == "Alcatra"
    assert r.receita.modo_preparo == ("Tempere com o limão.", "Sirva.")


def test_microdata_com_o_passo_em_etiquetas_dentro() -> None:
    """O passo com o número e o texto em etiquetas separadas: antes só o número chegava."""
    html = (
        "<div itemscope itemtype='http://schema.org/Recipe'>"
        "<h1 itemprop='name'>Peixe</h1>"
        "<li itemprop='recipeIngredient'><span>2</span> <b>postas</b> de peixe<br></li>"
        "<ol><li itemprop='recipeInstructions'><span>1</span> <span>Tempere o peixe.</span></li>"
        "<li itemprop='recipeInstructions'><span>2</span><span>Leve ao forno<br>por 20 min.</span>"
        "</li></ol><img itemprop='recipeInstructions' src='x.png'></div>"
    )
    r = extrair(html, PAGINA)
    assert r.receita.modo_preparo == ("Tempere o peixe.", "Leve ao forno por 20 min.")
    assert r.receita.ingredientes[0].texto_original == "2 postas de peixe"


def _pagina_com_lingua(receita: dict[str, object], lang: str = "") -> str:
    atributo = f' lang="{lang}"' if lang else ""
    bloco = json.dumps({"@context": "https://schema.org", "@type": "Recipe", **receita})
    return (
        f'<html{atributo}><head><script type="application/ld+json">{bloco}</script></head></html>'
    )


_EM_INGLES: dict[str, object] = {
    "name": "Feijao tropeiro",
    "recipeIngredient": [
        "1 kilogram Beans",
        "200 gram Diced bacon",
        "1 cup Toasted manioc flour",
        "2 tablespoon Butter",
        "1 pinch Salt",
    ],
    "recipeInstructions": ["Cook the beans."],
}


def test_receita_declarada_em_outra_lingua_e_recusada() -> None:
    with pytest.raises(ExtracaoFalhou, match="outra língua"):
        extrair(_pagina_com_lingua({**_EM_INGLES, "inLanguage": "en-US"}), "https://exemplo.com/r")


def test_pagina_em_outra_lingua_e_recusada() -> None:
    with pytest.raises(ExtracaoFalhou, match="outra língua"):
        extrair(_pagina_com_lingua(_EM_INGLES, lang="en"), "https://exemplo.com/r")


def test_medidas_em_ingles_sem_lingua_declarada_sao_recusadas() -> None:
    with pytest.raises(ExtracaoFalhou, match="outra língua"):
        extrair(_pagina_com_lingua(_EM_INGLES), "https://exemplo.com/r")


def test_receita_em_portugues_continua_entrando() -> None:
    receita = {
        "name": "Feijão tropeiro",
        "inLanguage": "pt-BR",
        "recipeIngredient": [
            "500 g de feijão",
            "200 g de bacon",
            "1 xícara de farinha de mandioca",
        ],
        "recipeInstructions": ["Cozinhe o feijão."],
    }
    assert (
        extrair(_pagina_com_lingua(receita, lang="pt-BR"), "https://exemplo.com/r").receita.nome
        == "Feijão tropeiro"
    )


def test_quadro_de_video_nao_vira_foto_do_prato() -> None:
    """A imagem de compartilhamento tirada do vídeo do programa mostra a apresentadora, não o prato."""
    og = (
        "<meta property='og:image' content='https://s2-receitas.glbimg.com/x=/1280x0/"
        "filters:format(jpeg)/https://s02.video.glbimg.com/x720/13885321.jpg'>"
    )
    assert extrair(_pagina(RECEITA, og), PAGINA).imagem_url is None


def test_sem_foto_declarada_vale_a_imagem_do_corpo_que_cita_o_prato() -> None:
    og = "<meta property='og:image' content='https://s02.video.glbimg.com/x720/1.jpg'>"
    corpo = (
        "<img src='https://img.globo.com/apresentadora.jpg' alt='A apresentadora no estúdio'>"
        f"<img src='https://img.globo.com/prato.jpg' alt='{RECEITA['name']} servido na travessa'>"
    )
    r = extrair(_pagina(RECEITA, og + corpo), PAGINA)
    assert r.imagem_url == "https://img.globo.com/prato.jpg"
