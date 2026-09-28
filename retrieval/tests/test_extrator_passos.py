"""O modo de preparo sai como a página mostra: a ordem, o texto e as seções.

A Dona Maria cozinha lendo os passos na tela. Passo que some, passo que vira
o nome da seção, passo partido em dois ou título de seção perdido é receita
diferente da que a página ensina, e ela só descobre com a panela no fogo.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from mise.receita import Receita

from retrieval.extrator import extrair, passos_do_preparo, titulo_da_secao

URL = "https://www.receitasnestle.com.br/receitas/bolo"


def _passo(texto: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"@type": "HowToStep", **extra, **({"text": texto} if texto is not None else {})}


def _secao(nome: str, *passos: Any) -> dict[str, Any]:
    return {"@type": "HowToSection", "name": nome, "itemListElement": list(passos)}


def _pagina(instrucoes: Any) -> str:
    receita = {
        "@type": "Recipe",
        "name": "Bolo de cenoura",
        "recipeIngredient": ["3 cenouras", "2 xícaras de farinha"],
        "recipeInstructions": instrucoes,
    }
    return f'<script type="application/ld+json">{json.dumps(receita)}</script>'


def _receita(instrucoes: Any) -> Receita:
    return extrair(_pagina(instrucoes), URL).receita


# --------------------------------------------------------------------------- #
# Seções                                                                        #
# --------------------------------------------------------------------------- #


def test_a_secao_traz_os_passos_e_nao_vira_um_passo() -> None:
    """Regressão: o feijão do Receitas Nestlé ficou com um passo só, "Modo de Preparo"."""
    receita = _receita(
        [_secao("Modo de Preparo", _passo("Escorra o feijão."), _passo("Refogue a cebola."))]
    )
    assert receita.modo_preparo == ("Escorra o feijão.", "Refogue a cebola.")
    assert receita.secoes_do_preparo == (), "Modo de Preparo não é título: a lista fica corrida"
    assert receita.secao_de_cada_passo == (None, None)


def test_as_secoes_com_nome_ficam_com_o_titulo_de_cada_passo() -> None:
    receita = _receita(
        [
            _secao("Massa", _passo("Bata a cenoura."), _passo("Asse por 40 minutos.")),
            _secao("Cobertura", _passo("Derreta o chocolate.")),
        ]
    )
    assert receita.modo_preparo == (
        "Bata a cenoura.",
        "Asse por 40 minutos.",
        "Derreta o chocolate.",
    )
    assert receita.secoes_do_preparo == ("Massa", "Massa", "Cobertura")


def test_a_secao_generica_no_meio_nao_tem_titulo() -> None:
    """O bolo com brigadeiro do Receitas Nestlé intercala "Modo de Preparo" com as partes."""
    textos, secoes = passos_do_preparo(
        [
            _secao("Massa do Bolo", _passo("Bata os ovos.")),
            _secao("Modo de Preparo", _passo("Asse.")),
            _secao("Cobertura de Brigadeiro", _passo("Cozinhe o leite condensado.")),
            _secao("Modo de Preparo", _passo("Cubra o bolo.")),
        ]
    )
    assert textos == ("Bata os ovos.", "Asse.", "Cozinhe o leite condensado.", "Cubra o bolo.")
    assert secoes == ("Massa do Bolo", None, "Cobertura de Brigadeiro", None)


def test_a_ordem_e_a_da_lista_e_nao_a_de_position() -> None:
    """O Panelinha numera `position` de um jeito e mostra na ordem da lista."""
    textos, _ = passos_do_preparo(
        [
            {"@type": "HowToSection", "position": 1, "name": "Para o bolo", "itemListElement": [
                {"@type": "HowToStep", "position": 9, "itemListElement": {"@type": "HowToDirection", "text": "Primeiro."}},
                {"@type": "HowToStep", "position": 2, "itemListElement": {"@type": "HowToDirection", "text": "Segundo."}},
            ]},
            {"@type": "HowToSection", "position": 0, "name": "Para a cobertura", "itemListElement": [
                _passo("Terceiro."),
            ]},
        ]
    )  # fmt: skip
    assert textos == ("Primeiro.", "Segundo.", "Terceiro.")


def test_o_texto_dentro_do_passo_vale_quando_o_passo_nao_tem_text() -> None:
    """HowToDirection e HowToTip dentro do HowToStep são partes de um passo só."""
    textos, secoes = passos_do_preparo(
        [
            _passo(itemListElement=[
                {"@type": "HowToDirection", "text": "Misture a farinha."},
                {"@type": "HowToTip", "text": "Peneire antes."},
            ]),
            _passo("Asse."),
        ]
    )  # fmt: skip
    assert textos == ("Misture a farinha. Peneire antes.", "Asse.")
    assert secoes == ()


def test_itemlist_listitem_e_lista_dentro_de_lista() -> None:
    textos, secoes = passos_do_preparo(
        {
            "@type": "ItemList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "item": _passo("Um.")},
                {"@type": "ListItem", "position": 2, "item": "Dois."},
                [["Três."]],
                42,
            ],
        }
    )
    assert textos == ("Um.", "Dois.", "Três.")
    assert secoes == ()


def test_secao_sem_nome_so_agrupa() -> None:
    textos, secoes = passos_do_preparo(
        [
            _passo("Bata os ovos.", name="Massa"),
            {"@type": "HowToSection", "itemListElement": ["Asse."]},
        ]
    )
    assert textos == ("Bata os ovos.", "Asse.")
    assert secoes == ("Massa", "Massa"), "sem nome, a seção continua a de antes"


# --------------------------------------------------------------------------- #
# text e name                                                                   #
# --------------------------------------------------------------------------- #


def test_o_text_vale_mais_que_o_name_que_repete_o_texto() -> None:
    textos, secoes = passos_do_preparo(
        [
            _passo(
                "Deixe o feijão de molho por 12 horas.",
                name="Deixe o feijão de molho por 12 horas.",
            ),
            _passo("Descarte a água e pique o alho.", name="Descarte a água…"),
            _passo("Leve ao fogo alto.", name="Leve ao fogo..."),
            _passo(name="Sirva quente."),
        ]
    )
    assert textos == (
        "Deixe o feijão de molho por 12 horas.",
        "Descarte a água e pique o alho.",
        "Leve ao fogo alto.",
        "Sirva quente.",
    )
    assert secoes == ()


def test_o_name_do_tudogostoso_abre_a_secao_ate_o_proximo() -> None:
    """O TudoGostoso põe "Massa" no name do primeiro passo da massa, e o texto no text."""
    receita = _receita(
        [
            _passo("Bata a cenoura, os ovos e o &amp;oacute;leo.", name="Massa"),
            _passo("Asse por 40 minutos."),
            _passo("Misture o chocolate e o leite.", name="Cobertura"),
            _passo("Cubra o bolo."),
        ]
    )
    assert receita.modo_preparo == (
        "Bata a cenoura, os ovos e o óleo.",
        "Asse por 40 minutos.",
        "Misture o chocolate e o leite.",
        "Cubra o bolo.",
    )
    assert receita.secoes_do_preparo == ("Massa", "Massa", "Cobertura", "Cobertura")


def test_o_name_que_so_numera_nao_e_titulo() -> None:
    _, secoes = passos_do_preparo(
        [_passo("Lave o arroz.", name="Passo 1"), _passo("Cozinhe.", name="Passo 2")]
    )
    assert secoes == ()


def test_o_name_generico_fecha_a_secao_anterior() -> None:
    _, secoes = passos_do_preparo(
        [
            _passo("Faça a massa.", name="Massa"),
            _passo("Asse.", name="Modo de preparo"),
            _passo("Sirva."),
        ]
    )
    assert secoes == ("Massa", None, None)


# --------------------------------------------------------------------------- #
# Texto solto, quebra de linha e HTML                                           #
# --------------------------------------------------------------------------- #


def test_texto_solto_com_quebra_de_linha_vira_um_passo_por_linha() -> None:
    textos, _ = passos_do_preparo("1. Cozinhe o arroz.\n2. Refogue o alho.\r\n\n3. Misture.")
    assert textos == ("1. Cozinhe o arroz.", "2. Refogue o alho.", "3. Misture."), (
        "o número escrito no texto fica: é o texto da página"
    )


def test_texto_solto_sem_quebra_e_um_passo_so() -> None:
    assert passos_do_preparo("1. Cozinhe o arroz. 2. Refogue o alho.") == (
        ("1. Cozinhe o arroz. 2. Refogue o alho.",),
        (),
    )


def test_a_quebra_dentro_de_um_passo_entre_outros_nao_parte_o_passo() -> None:
    textos, _ = passos_do_preparo(
        [_passo("Cozinhe o arroz.<br>Deixe descansar."), _passo("<p>Sirva.</p>")]
    )
    assert textos == ("Cozinhe o arroz. Deixe descansar.", "Sirva.")


def test_o_preparo_inteiro_num_passo_so_vira_um_passo_por_linha() -> None:
    textos, secoes = passos_do_preparo(
        [_secao("Massa", _passo("Cozinhe o arroz.<br>Refogue o alho.\nMisture tudo."))]
    )
    assert textos == ("Cozinhe o arroz.", "Refogue o alho.", "Misture tudo.")
    assert secoes == ("Massa", "Massa", "Massa")


def test_etiqueta_de_bloco_separa_e_a_de_texto_some_sem_deixar_espaco() -> None:
    textos, _ = passos_do_preparo(
        [
            "<p>Aqueça o &lt;b&gt;óleo&lt;/b&gt;.</p><p>Frite o <a href='/alho'>alho</a>.</p>",
            "<ol><li>Misture tudo.</li><li>Asse por 20&nbsp;minutos.</li></ol>",
        ]
    )
    assert textos == ("Aqueça o óleo.", "Frite o alho.", "Misture tudo.", "Asse por 20 minutos.")


def test_sem_modo_de_preparo_nada_sai() -> None:
    assert passos_do_preparo(None) == ((), ())
    assert passos_do_preparo([]) == ((), ())
    assert passos_do_preparo([{"@type": "HowToStep"}, "", "  "]) == ((), ())


@pytest.mark.parametrize(
    ("nome", "titulo"),
    [
        ("Massa", "Massa"),
        ("  Cobertura  de   brigadeiro ", "Cobertura de brigadeiro"),
        ("Massa:", "Massa:"),
        ("Para o bolo", "Para o bolo"),
        ("Modo de Preparo", None),
        ("MODO DE PREPARO:", None),
        ("Modo de preparação", None),
        ("Instruções", None),
        ("Passo a passo", None),
        ("Passo 1", None),
        ("Etapa 2:", None),
        ("3.", None),
        ("", None),
    ],
)
def test_titulo_da_secao(nome: str, titulo: str | None) -> None:
    assert titulo_da_secao(nome) == titulo


# --------------------------------------------------------------------------- #
# Microdata: o número da lista da página não é texto do passo                   #
# --------------------------------------------------------------------------- #


def test_microdata_com_a_numeracao_que_recomeca_em_cada_parte(html) -> None:
    """O Receitas da Globo conta 1, 2 no prato e de novo 1, 2, 3 no molho.

    Antes o número só saía quando era a posição na receita inteira, e o passo
    do molho chegava na tela como "1 Misture todos os ingredientes".
    """
    receita = extrair(
        html("microdata_partes_numeradas.html"), "https://receitas.globo.com/x"
    ).receita
    assert receita.modo_preparo == (
        "Aqueça bem a chapa em fogo médio.",
        "Asse os salsichões por cerca de 10 minutos de cada lado.",
        "Misture todos os ingredientes em uma panela.",
        "Mantenha o molho aquecido até o momento de servir.",
        "2 colheres de mostarda vão por cima, na hora.",
    )
    assert receita.secoes_do_preparo == (), "o microdata não diz as partes: sem título inventado"


def test_microdata_o_numero_escrito_no_texto_fica() -> None:
    """Só sai o número que a página põe numa etiqueta própria e que segue a contagem."""
    pagina = (
        "<div itemscope itemtype='http://schema.org/Recipe'>"
        "<li itemprop='recipeIngredient'>2 ovos</li>"
        "<li itemprop='recipeInstructions'>1 xícara de leite morno vai primeiro.</li>"
        "<li itemprop='recipeInstructions'><b>5</b> ovos batidos entram agora.</li>"
        "<li itemprop='recipeInstructions'><span>3.</span> Asse.</li>"
        "<meta itemprop='recipeInstructions' content='4 Sirva.'>"
        "<li itemprop='recipeInstructions'><span>7</span></li>"
        "<li itemprop='recipeInstructions'> <span> </span> </li>"
        "</div>"
    )
    assert extrair(pagina, "https://exemplo.com.br/x").receita.modo_preparo == (
        "1 xícara de leite morno vai primeiro.",
        "5 ovos batidos entram agora.",
        "3. Asse.",
        "4 Sirva.",
        "7",
    )


def test_o_tipo_com_o_endereco_do_schema_vale_o_mesmo() -> None:
    """ "http://schema.org/HowToStep" e "schema:HowToSection" são os mesmos tipos."""
    textos, secoes = passos_do_preparo(
        [
            {
                "@type": "schema:HowToSection",
                "name": "Massa",
                "itemListElement": [
                    {
                        "@type": "http://schema.org/HowToStep",
                        "itemListElement": [
                            {"@type": "https://schema.org/HowToDirection", "text": "Misture."},
                            {"@type": "HowToTip", "text": "Sem bater demais."},
                        ],
                    },
                    {"@type": ["http://schema.org/HowToStep"], "text": "Asse."},
                ],
            }
        ]
    )
    assert textos == ("Misture. Sem bater demais.", "Asse.")
    assert secoes == ("Massa", "Massa")


def test_objeto_sem_tipo_com_texto_e_passo_e_sem_texto_e_secao() -> None:
    textos, secoes = passos_do_preparo(
        [
            {"text": "Misture a massa.", "itemListElement": [{"text": "Um detalhe."}]},
            {"name": "Cobertura", "itemListElement": ["Derreta o chocolate."]},
        ]
    )
    assert textos == ("Misture a massa.", "Derreta o chocolate.")
    assert secoes == (None, "Cobertura")
