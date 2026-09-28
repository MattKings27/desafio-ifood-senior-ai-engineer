"""A cascata de casamento. O teste que mais importa é o que RECUSA."""

from __future__ import annotations

from decimal import Decimal

import pytest

from mise.casamento import (
    LIMIAR_APROXIMADO,
    PEITO_DE_FRANGO,
    SINONIMOS,
    Estrategia,
    casar,
    casar_confirmado,
    casar_todos,
    nucleo_do_nome,
)
from mise.despensa import Despensa


@pytest.mark.parametrize(
    ("texto", "esperado", "estrategia"),
    [
        ("Carne moída (patinho)", "Carne moída (patinho)", Estrategia.EXATO),
        ("carne moida (patinho)", "Carne moída (patinho)", Estrategia.NORMALIZADO),
        ("peito de frango", "Peito de frango", Estrategia.NORMALIZADO),
        ("parmesão", "Queijo parmesão ralado", Estrategia.SINONIMO),
        ("mussarela", "Queijo mussarela", Estrategia.SINONIMO),
        ("frango", "Peito de frango", Estrategia.SINONIMO),
        ("acém", "Carne de panela (acém)", Estrategia.SINONIMO),
        ("fubá", "Polenta (fubá)", Estrategia.SINONIMO),
        ("cheiro verde", "Salsinha (cheiro-verde)", Estrategia.SINONIMO),
        ("ovo", "Ovos", Estrategia.SINONIMO),
    ],
)
def test_casamentos_corretos(
    despensa: Despensa, texto: str, esperado: str, estrategia: Estrategia
) -> None:
    c = casar(texto, despensa)
    assert c.item is not None
    assert c.item.nome == esperado
    assert c.estrategia is estrategia
    assert c.confiavel


@pytest.mark.parametrize(
    "texto",
    [
        "farinha de rosca",
        "creme de leite",
        "linguiça calabresa",
        "pimentão",
        "cenoura",
        "requeijão",
        "fermento em pó",
        "molho shoyu",
        "bacalhau",
        "gengibre",
    ],
)
def test_recusa_o_que_nao_tem(despensa: Despensa, texto: str) -> None:
    """Falso-positivo aqui produz CMV plausível e errado: o pior defeito possível."""
    c = casar(texto, despensa)
    assert not c.encontrado, f"{texto!r} casou indevidamente com {c.item.nome if c.item else ''}"
    assert c.estrategia is Estrategia.NENHUM


def test_farinha_de_rosca_nao_vira_farinha_de_trigo(despensa: Despensa) -> None:
    """O falso-positivo mais tentador: dois nomes quase iguais, preços diferentes."""
    c = casar("farinha de rosca", despensa)
    assert c.item is None
    assert c.score < LIMIAR_APROXIMADO


def test_casamento_por_nucleo(despensa: Despensa) -> None:
    """Palavras de ruído não impedem o reconhecimento."""
    c = casar("tomate maduro picado", despensa)
    assert c.item is not None
    assert c.item.nome == "Tomate"


def test_texto_vazio(despensa: Despensa) -> None:
    for vazio in ("", "   "):
        c = casar(vazio, despensa)
        assert not c.encontrado
        assert c.score == 0.0


def test_explicacao_de_cada_estrategia(despensa: Despensa) -> None:
    assert "nome idêntico" in casar("Tomate", despensa).explicacao()
    assert "ignorando acento" in casar("tomate", despensa).explicacao()
    assert "sinônimo" in casar("parmesão", despensa).explicacao()
    assert "não foi encontrado" in casar("caviar", despensa).explicacao()


def test_explicacao_de_aproximado_cita_o_score(despensa: Despensa) -> None:
    c = casar("arroz branco tipo 1 parboilizado", despensa)
    if c.estrategia is Estrategia.APROXIMADO:
        assert "semelhança" in c.explicacao()


def test_casar_todos(despensa: Despensa) -> None:
    resultados = casar_todos(["tomate", "caviar", "cebola"], despensa)
    assert [r.encontrado for r in resultados] == [True, False, True]


def test_ordem_das_estrategias_e_decrescente() -> None:
    assert (
        Estrategia.EXATO
        > Estrategia.NORMALIZADO
        > Estrategia.SINONIMO
        > Estrategia.NUCLEO
        > Estrategia.APROXIMADO
        > Estrategia.NENHUM
    )


def test_confiavel_exige_pelo_menos_nucleo() -> None:
    from mise.casamento import Casamento

    assert not Casamento("x", None, Estrategia.NENHUM, 0).confiavel


def test_todo_sinonimo_aponta_para_item_existente(despensa: Despensa) -> None:
    """Um sinônimo quebrado é um casamento que silenciosamente deixa de funcionar."""
    for chave, destino in SINONIMOS.items():
        assert destino in despensa, f"sinônimo {chave!r} aponta para {destino!r}, que não existe"


# --------------------------------------------------------------------------- #
# Como as receitas de verdade escrevem
# --------------------------------------------------------------------------- #

COMO_A_RECEITA_ESCREVE = [
    ("cebolas picadas", "Cebola"),
    ("2 cebolas médias picadas", "Cebola"),
    ("dentes de alho amassados", "Alho"),
    ("filé de frango em tiras", "Peito de frango"),
    ("peito de frango sem pele", "Peito de frango"),
    ("queijo mussarela ralado", "Queijo mussarela"),
    ("tomates maduros", "Tomate"),
    ("tomate em rodelas", "Tomate"),
    ("batatas cozidas", "Batata"),
    ("folhas de couve", "Couve"),
    ("ovo batido", "Ovos"),
    ("manteiga derretida", "Manteiga"),
    ("feijão preto", "Feijão preto"),
    ("azeite de oliva", "Azeite de oliva extra virgem"),
]

NAO_E_O_MESMO_INGREDIENTE = [
    "coxa e sobrecoxa",  # outro corte, outro preço
    "leite condensado",
    "creme de leite",
    "creme de leite fresco",  # chantilly é creme batido e adoçado
    "farinha de rosca",
    "carne em cubos",  # acém, alcatra ou patinho: pergunta, não chuta
    "milho verde",
]


@pytest.mark.parametrize(("texto", "esperado"), COMO_A_RECEITA_ESCREVE)
def test_o_que_ela_tem_e_achado_do_jeito_que_a_receita_escreve(
    despensa: Despensa, texto: str, esperado: str
) -> None:
    """Sem isso o agente mandava comprar a cebola que já está na despensa."""
    casamento = casar(texto, despensa)
    assert casamento.confiavel, casamento.explicacao()
    assert casamento.item is not None
    assert casamento.item.nome == esperado


@pytest.mark.parametrize("texto", NAO_E_O_MESMO_INGREDIENTE)
def test_parecido_nao_e_o_mesmo(despensa: Despensa, texto: str) -> None:
    """Casar errado não dá erro em lugar nenhum: dá um custo plausível e falso."""
    assert not casar(texto, despensa).confiavel


# --------------------------------------------------------------------------- #
# As equivalências dos 37 itens, o frango da receita de frango e o parecido      #
# --------------------------------------------------------------------------- #


def test_cada_item_da_planilha_tem_a_sua_equivalencia(despensa: Despensa) -> None:
    """Os 37 itens estão na tabela escrita à mão: nenhum depende da semelhança."""
    assert set(despensa.nomes) <= set(SINONIMOS.values())


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("alcatra", "Miolo de alcatra"),
        ("bifes pequenos de alcatra", "Miolo de alcatra"),
        ("coração da alcatra", "Miolo de alcatra"),
        ("filés de frango", "Peito de frango"),
        ("file de peito de frango", "Peito de frango"),
        ("sassami", "Peito de frango"),
        ("peito de frango cortado em 4 filés", "Peito de frango"),
        ("cebola cortada em quadrados", "Cebola"),
        ("queijo mozarela", "Queijo mussarela"),
        ("farinha de mesa", "Farinha de mandioca"),
        ("açúcar refinado", "Açúcar"),
        ("canela em pó", "Canela em pó"),
        ("azeite ou manteiga", "Manteiga"),
        ("óleo ou manteiga", "Manteiga"),
        ("feijão da sua preferência", "Feijão carioquinha"),
        ("feijão de sua preferência", "Feijão carioquinha"),
    ],
)
def test_equivalencias_escritas_casam_com_confianca(
    despensa: Despensa, texto: str, esperado: str
) -> None:
    c = casar(texto, despensa)
    assert c.item is not None
    assert c.item.nome == esperado
    assert c.confiavel


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("óleo para fritura", "Óleo de soja"),
        ("óleo para fritar", "Óleo de soja"),
        ("óleo para untar", "Óleo de soja"),
        ("Óleo para refogar", "Óleo de soja"),
        ("óleo de soja para fritar", "Óleo de soja"),
        ("óleo, para fritar", "Óleo de soja"),
        ("manteiga para untar a forma", "Manteiga"),
        ("farinha de trigo para polvilhar", "Farinha de trigo"),
        ("açúcar para polvilhar", "Açúcar"),
        ("queijo parmesão para polvilhar", "Queijo parmesão ralado"),
        ("azeite para pincelar", "Azeite de oliva extra virgem"),
        ("cheiro-verde para servir", "Salsinha (cheiro-verde)"),
        ("salsinha para decorar", "Salsinha (cheiro-verde)"),
        ("azeite ou manteiga para untar", "Manteiga"),
    ],
)
def test_a_finalidade_nao_muda_o_ingrediente(despensa: Despensa, texto: str, esperado: str) -> None:
    """ "Óleo para fritura" é o óleo de soja dela: para que serve não é o que se compra."""
    c = casar(texto, despensa)
    assert c.item is not None
    assert c.item.nome == esperado
    assert c.confiavel
    assert c.texto_receita == texto, "a linha da receita continua como ela escreveu"


@pytest.mark.parametrize(
    "texto",
    [
        "farinha de rosca",
        "farinha de rosca para empanar",
        "extrato de tomate",
        "extrato de tomate para servir",
        "massa de tomate",
        "óleo de coco para untar",
        "creme de leite para servir",
        "leite condensado para decorar",
        "tempero para aves",
    ],
)
def test_tirar_a_finalidade_nao_faz_o_parecido_virar_o_mesmo(
    despensa: Despensa, texto: str
) -> None:
    """Sem a finalidade, o que é outro produto continua outro: nada disso é dela com confiança."""
    assert not casar(texto, despensa).confiavel, casar(texto, despensa).explicacao()


def test_a_farinha_de_rosca_para_empanar_nao_vira_a_de_trigo(despensa: Despensa) -> None:
    c = casar("farinha de rosca para empanar", despensa)
    assert c.item is None
    assert c.score < LIMIAR_APROXIMADO


def test_o_extrato_de_tomate_nunca_e_o_tomate_com_confianca(despensa: Despensa) -> None:
    for texto in (
        "extrato de tomate",
        "2 colheres de extrato de tomate",
        "extrato de tomate para servir",
    ):
        c = casar(texto, despensa)
        assert not c.confiavel, c.explicacao()
        assert c.estrategia < Estrategia.NUCLEO


@pytest.mark.parametrize(
    ("texto", "nucleo"),
    [
        ("óleo para fritura", "oleo"),
        ("manteiga para untar a assadeira", "manteiga"),
        ("farinha de trigo para polvilhar", "farinha trigo"),
        ("tempero para aves", "tempero ave"),
    ],
)
def test_o_nucleo_nao_leva_a_finalidade(texto: str, nucleo: str) -> None:
    """O preço de referência e a pergunta de preço usam o núcleo: sem a finalidade, é o produto."""
    assert nucleo_do_nome(texto) == nucleo


@pytest.mark.parametrize("texto", ["peito", "1 peito cortado em 4 filés", "filés"])
def test_numa_receita_de_frango_o_peito_e_o_peito_de_frango(despensa: Despensa, texto: str) -> None:
    c = casar(texto, despensa, contexto="Frango com alcaparras")
    assert c.item is not None
    assert c.item.nome == PEITO_DE_FRANGO
    assert c.confiavel


def test_fora_da_receita_de_frango_o_peito_so_pergunta(despensa: Despensa) -> None:
    """ "Peito" numa receita de peru não vira o frango dela: vira pergunta."""
    c = casar("peito", despensa, contexto="Peito de peru assado")
    assert c.estrategia is Estrategia.PARCIAL
    assert not c.confiavel
    assert "só parecido" in c.explicacao()


@pytest.mark.parametrize(
    ("texto", "parecido"),
    [
        ("canela", "Canela em pó"),
        ("caldo", "Caldo de carne (tempero)"),
        ("mandioca", "Farinha de mandioca"),
        ("farinha de trigo integral", "Farinha de trigo"),
    ],
)
def test_o_parecido_nunca_e_confiavel(despensa: Despensa, texto: str, parecido: str) -> None:
    """O nome do item dela contém o da receita (ou o contrário): parecido, nunca "tem"."""
    c = casar(texto, despensa)
    assert c.estrategia is Estrategia.PARCIAL
    assert c.item is not None
    assert c.item.nome == parecido
    assert not c.confiavel


@pytest.mark.parametrize(
    "texto", ["leite condensado", "creme de leite", "vinagre ou suco de limão"]
)
def test_uma_palavra_em_comum_nao_basta(despensa: Despensa, texto: str) -> None:
    """ "Leite condensado" não é o leite integral dela, nem para perguntar."""
    c = casar(texto, despensa)
    assert c.estrategia is Estrategia.NENHUM


def test_dois_parecidos_nao_viram_pergunta(despensa: Despensa) -> None:
    """ "Carne" está na moída e na de panela: não há um item só a perguntar."""
    assert casar("carne", despensa).estrategia is not Estrategia.PARCIAL


def test_o_que_ela_confirmou_vale_mais(despensa: Despensa) -> None:
    confirmado = casar_confirmado("alcatra", "Miolo de alcatra", despensa)
    assert confirmado.item is not None
    assert confirmado.confiavel
    assert "confirmou" in confirmado.explicacao()
    assert casar_confirmado("alcatra", "", despensa).item is None
    assert casar_confirmado("alcatra", "Caviar", despensa).item is None


def test_o_nucleo_tira_o_corte_e_o_preparo() -> None:
    assert nucleo_do_nome("cenouras médias descascadas") == "cenoura"


@pytest.mark.parametrize(
    ("texto", "item"),
    [
        ("Queijo Parmesão TIROLEZ ralado", "Queijo parmesão ralado"),
        ("Coração da Alcatra bovina Perdigão Montana", "Miolo de alcatra"),
        ("MAGGI® Caldo de carne", "Caldo de carne (tempero)"),
    ],
)
def test_a_marca_nao_muda_o_ingrediente(despensa: Despensa, texto: str, item: str) -> None:
    """A marca registrada, a palavra em maiúscula e a marca conhecida saem antes de casar."""
    c = casar(texto, despensa)
    assert c.confiavel
    assert c.item is not None
    assert c.item.nome == item
    assert c.texto_receita == texto


def test_a_marca_que_e_o_produto_fica() -> None:
    """ "Leite MOÇA" sem a marca seria o leite dela, e é leite condensado."""
    from mise.casamento import sem_marca

    assert sem_marca("Leite MOÇA®") == "Leite MOÇA®"
    assert sem_marca("NESCAU®") == "NESCAU®"
    assert sem_marca("Maionese Hellmann's") == "Maionese"
    assert sem_marca("SAL A GOSTO") == "SAL A GOSTO"


@pytest.mark.parametrize(
    ("pedido", "item", "forma"),
    [
        ("mandioca", "Farinha de mandioca", "farinha"),
        ("canela", "Canela em pó", "po"),
        ("tomate", "Extrato de tomate", "extrato"),
        ("queijo parmesão ralado", "Queijo parmesão ralado", None),
    ],
)
def test_a_forma_do_produto_decide(pedido: str, item: str, forma: str | None) -> None:
    from mise.casamento import forma_diferente, mesma_forma

    assert forma_diferente(pedido, item) == forma
    assert mesma_forma(pedido, item) is (forma is None)


def test_o_diminutivo_e_o_mesmo_produto() -> None:
    from mise.casamento import nucleo_do_nome

    assert nucleo_do_nome("4 linguicinhas defumadas") == nucleo_do_nome("linguiça defumada")
    assert nucleo_do_nome("cebolinha") != nucleo_do_nome("cebola")


def test_a_farinha_amarela_e_a_farinha_de_mandioca(despensa: Despensa) -> None:
    c = casar("Farinha amarela ou branca", despensa)
    assert c.confiavel
    assert c.item is not None
    assert c.item.nome == "Farinha de mandioca"


def test_o_couro_do_bacon_e_o_bacon_dela_com_a_decisao_dita(despensa: Despensa) -> None:
    from mise.casamento import motivo_do_sinonimo
    from mise.receita import ingrediente, receita
    from mise.viabilidade import checar_ingredientes

    c = casar("couro do bacon", despensa)
    assert c.confiavel
    assert c.item is not None
    assert c.item.nome == "Bacon"
    assert motivo_do_sinonimo("couro do bacon") == "o couro é a pele da mesma peça"
    feijao = receita("Feijão", [ingrediente("1 couro do bacon", "couro do bacon", 1, "")])
    checagem, usos, faltantes, _ = checar_ingredientes(feijao, despensa)
    (ajuste,) = checagem.ajustes  # type: ignore[attr-defined]
    assert ajuste.decisao.startswith("Considerei que couro do bacon é o seu bacon")
    assert not faltantes and not checagem.perguntas
    # O pedaço de toucinho da tabela do IBGE: 10 g, estimativa que ela corrige.
    assert usos[0].quantidade.valor == Decimal("0.01")
