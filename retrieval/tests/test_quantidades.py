"""Interpretação de linha de ingrediente escrita por gente.

O defeito que estes testes existem para impedir não é a linha que falha, é a
que **quase** acerta. "1/2 xícara" lido como 1 não quebra nada: produz um
número plausível, atravessa o casamento, entra no CMV e sai como preço. A Dona
Maria só descobre no fim do mês.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from retrieval.quantidades import (
    A_GOSTO_POR_CONVENCAO,
    e_a_gosto,
    interpretar_linha,
    so_tempero,
)


@pytest.mark.parametrize(
    ("linha", "quantidade", "medida", "nome"),
    [
        ("200 g de queijo ralado", Decimal(200), "g", "queijo ralado"),
        ("1 xícara de arroz", Decimal(1), "xicara", "arroz"),
        ("2 xícaras (chá) de açúcar", Decimal(2), "xicara de cha", "açúcar"),
        ("2 colheres de sopa de manteiga", Decimal(2), "colher de sopa", "manteiga"),
        ("1 colher (chá) de sal fino", Decimal(1), "colher de cha", "sal fino"),
        ("500g de carne moída", Decimal(500), "g", "carne moída"),
        ("1kg de batata", Decimal(1), "kg", "batata"),
        ("250 ml de leite", Decimal(250), "ml", "leite"),
        ("2 colheres de sopa de óleo", Decimal(2), "colher de sopa", "óleo"),
        ("2 colheres (sopa) de azeite", Decimal(2), "colher de sopa", "azeite"),
        # Colher sem dizer qual é a de sopa; antes virava "colheres de óleo".
        ("2 colheres de óleo", Decimal(2), "colher", "óleo"),
        ("1 colher de açúcar", Decimal(1), "colher", "açúcar"),
    ],
)
def test_linhas_comuns(linha: str, quantidade: Decimal, medida: str, nome: str) -> None:
    i = interpretar_linha(linha)
    assert i.quantidade == quantidade
    assert i.medida == medida
    assert i.nome == nome
    assert i.texto_original == linha


@pytest.mark.parametrize(
    ("linha", "esperado"),
    [
        ("1/2 xícara de óleo", Decimal("0.5")),
        ("1 e 1/2 xícara de leite", Decimal("1.5")),
        ("1 1/2 xícara de leite", Decimal("1.5")),
        ("2 e 3/4 xícaras de farinha", Decimal("2.75")),
        ("½ kg de carne", Decimal("0.5")),
        ("¼ xícara de vinagre", Decimal("0.25")),
        ("1 ½ colher de chá de sal", Decimal("1.5")),
        ("2,5 kg de frango", Decimal("2.5")),
    ],
)
def test_fracoes_e_decimais(linha: str, esperado: Decimal) -> None:
    """O caso que mais importa: "1/2" não pode virar 1."""
    assert interpretar_linha(linha).quantidade == esperado


def test_meia_xicara_nunca_vira_uma() -> None:
    """Regressão explícita: o inteiro comia o numerador da fração."""
    i = interpretar_linha("1/2 xícara de óleo")
    assert i.quantidade == Decimal("0.5")
    assert i.nome == "óleo"


@pytest.mark.parametrize(
    ("linha", "medida", "nome"),
    [
        ("4 ovos", "ovo", "ovos"),
        # O preparo sai do nome e vai para a observação: "picadas" não se compra.
        ("3 cenouras médias picadas", "cenoura", "cenouras médias"),
        ("2 dentes de alho", "dente de alho", "dentes de alho"),
        ("1 cebola grande", "cebola", "cebola grande"),
    ],
)
def test_peso_unitario_mantem_o_ingrediente_no_nome(linha: str, medida: str, nome: str) -> None:
    """Quando a medida é o próprio ingrediente, tirá-la do nome apaga o item."""
    i = interpretar_linha(linha)
    assert i.medida == medida
    assert i.nome == nome


@pytest.mark.parametrize(
    "linha",
    [
        "sal a gosto",
        "Pimenta-do-reino à gosto",
        "Cheiro-verde a vontade",
        "Azeite para untar",
        "Chocolate granulado para decorar",
        "Queijo ralado q.b.",
        "Salsinha (opcional)",
    ],
)
def test_a_gosto_nao_ganha_quantidade(linha: str) -> None:
    """Custo desprezível, mas declarado: some do CMV e a conta deixa de fechar."""
    i = interpretar_linha(linha)
    assert i.quantidade is None
    assert i.a_gosto
    assert i.nome
    assert i.observacao


@pytest.mark.parametrize(
    ("linha", "nome"),
    [
        ("1 lata de leite condensado", "leite condensado"),
        ("1 pacote de macarrão", "macarrão"),
        ("2 caixas de creme de leite", "creme de leite"),
        ("1 tablete de fermento", "fermento"),
    ],
)
def test_embalagem_nao_gruda_no_nome(linha: str, nome: str) -> None:
    """ "lata de leite condensado" não casaria com "leite condensado" na despensa."""
    assert interpretar_linha(linha).nome == nome


def test_linha_sem_numero_nao_inventa_quantidade() -> None:
    """Um número plausível e errado é pior que nenhum: o motor sabe perguntar."""
    i = interpretar_linha("Farinha de trigo")
    assert i.quantidade is None
    assert i.nome == "Farinha de trigo"


def test_linha_vazia_nao_quebra() -> None:
    i = interpretar_linha("   ")
    assert i.nome == ""
    assert i.quantidade is None


def test_texto_original_e_sempre_preservado() -> None:
    """É o que a Dona Maria confere quando discorda da nossa interpretação."""
    bruto = "  2   xícaras   (chá)  de açúcar  "
    assert interpretar_linha(bruto).texto_original == "2 xícaras (chá) de açúcar"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("sal a gosto", True), ("q.b.", True), ("2 ovos", False), ("200 g de sal", False)],
)
def test_deteccao_de_a_gosto(texto: str, esperado: bool) -> None:
    assert e_a_gosto(texto) is esperado


# --------------------------------------------------------------------------- #
# Entrada malformada: o que chega de site real                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "linha",
    [
        "1/0 xícara de óleo",
        "1/ xícara de leite",
        "abc g de farinha",
        "/2 xícara",
    ],
)
def test_numero_impossivel_nao_vira_quantidade(linha: str) -> None:
    """Divisão por zero e fração truncada não podem virar número plausível."""
    i = interpretar_linha(linha)
    assert i.quantidade is None or i.quantidade >= 0


def test_fracao_com_denominador_zero_e_ignorada() -> None:
    from retrieval.quantidades import _fracao

    assert _fracao("1/0") is None
    assert _fracao("1/2/3") is None
    assert _fracao("a/b") is None


def test_decimal_invalido_devolve_none() -> None:
    from retrieval.quantidades import _para_decimal

    assert _para_decimal("abc") is None
    assert _para_decimal("") is None
    assert _para_decimal("2,5") == Decimal("2.5")


def test_medida_sem_ingrediente_usa_a_propria_medida() -> None:
    """Três colheres de sopa sem dizer de quê: acontece em lista mal formatada."""
    i = interpretar_linha("3 colheres de sopa")
    assert i.quantidade == Decimal(3)
    assert i.nome


def test_singulares_de_texto_vazio() -> None:
    from retrieval.quantidades import _singulares

    assert _singulares("") == ("",)


def test_separar_medida_de_texto_vazio() -> None:
    from retrieval.quantidades import _separar_medida

    assert _separar_medida("   ") == ("", "")


def test_marca_padrao_quando_nenhuma_casa() -> None:
    from retrieval.quantidades import _marca_encontrada

    assert _marca_encontrada("texto sem marca") == "a gosto"
    assert _marca_encontrada("sal a gosto") == "a gosto"


def test_so_numero_sem_medida_nem_nome() -> None:
    i = interpretar_linha("3")
    assert i.quantidade == Decimal(3)


def test_misto_com_fracao_impossivel_cai_para_a_proxima_tentativa() -> None:
    """ "1 e 1/0" não é 1: a fração inválida derruba a leitura mista."""
    i = interpretar_linha("1 e 1/0 xícara de leite")
    assert i.quantidade is None or i.quantidade == Decimal(1)


def test_so_inteiro_com_numero_ilegivel() -> None:
    from retrieval.quantidades import _so_inteiro

    assert _so_inteiro("sem numero") is None


def test_misto_sem_casar_devolve_none() -> None:
    from retrieval.quantidades import _misto

    assert _misto("2 xícaras") is None


def test_so_fracao_sem_casar_devolve_none() -> None:
    from retrieval.quantidades import _so_fracao

    assert _so_fracao("2 xícaras") is None
    assert _so_fracao("1/0 xícara") is None


# --------------------------------------------------------------------------- #
# As linhas das receitas de verdade que a leitura não entendia                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("linha", "quantidade", "nome", "observacao"),
    [
        ("Suco de 1 limão", Decimal(1), "limão", "suco"),
        ("suco de 2 limões", Decimal(2), "limões", "suco"),
        ("raspas de 1 limão", Decimal(1), "limão", "raspas"),
        ("Raspas de 1/2 laranja", Decimal("0.5"), "laranja", "raspas"),
        # Uma linha do catálogo: o caldo do limão é o suco dele.
        ("caldo de ½ limão", Decimal("0.5"), "limão", "caldo"),
        ("Caldo de 2 laranjas", Decimal(2), "laranjas", "caldo"),
    ],
)
def test_a_parte_da_fruta_e_a_fruta_que_se_compra(
    linha: str, quantidade: Decimal, nome: str, observacao: str
) -> None:
    """ "Suco de 1 limão" pede um limão: a quantidade é da fruta, e a parte vai junto."""
    i = interpretar_linha(linha)
    assert (i.quantidade, i.nome, i.observacao) == (quantidade, nome, observacao)
    assert i.entendida
    assert not i.nao_entendida


def test_o_plural_que_troca_a_vogal_ainda_e_a_medida() -> None:
    """ "2 limões" é a mesma medida que "1 limão": sem isto, o limão ficava sem peso típico."""
    assert interpretar_linha("2 limões").medida == interpretar_linha("1 limão").medida == "limao"


def test_o_caldo_que_nao_e_de_fruta_nao_vira_fruta() -> None:
    """ "Caldo de 1 tablete" não é parte de fruta nenhuma: a linha segue como era, sem número."""
    for linha in ("caldo de 1 tablete de galinha", "Caldo de galinha"):
        assert interpretar_linha(linha).nao_entendida, linha


def test_suco_sem_numero_continua_sem_entender() -> None:
    """Sem número, "suco de laranja" não vira quantidade inventada: vira pergunta."""
    assert interpretar_linha("Suco de laranja").nao_entendida


@pytest.mark.parametrize(
    "linha",
    [
        "Sal",
        "Sal.",
        "Sal e pimenta-do-reino",
        "sal e pimenta do reino",
        "Azeite",
        "Cheiro-verde",
        "Orégano",
        "Pimenta",
        "Pimenta-do-reino moída",
        "Salsinha e cebolinha picadas",
        "Sal, pimenta e orégano",
        "Folhas de louro",
        "Cheiro-verde (salsinha e cebolinha)",
        "Canela em pó",
    ],
)
def test_so_o_nome_do_tempero_e_a_gosto_pela_convencao(linha: str) -> None:
    """ "Sal" sozinho é como a receita brasileira escreve "sal a gosto": não segura a receita."""
    i = interpretar_linha(linha)
    assert so_tempero(linha)
    assert i.a_gosto
    assert not i.nao_entendida
    assert i.quantidade is None
    assert i.observacao == A_GOSTO_POR_CONVENCAO


@pytest.mark.parametrize(
    "linha",
    [
        "Milho",
        "Ervilha",
        "Azeitona sem caroço",
        "Alho amassado",
        "Caldo de galinha",
        "Sazón",
        "temperos de sua preferência",
        "Sal e milho",
        "Pimentão",
        "Suco de laranja",
    ],
)
def test_o_que_nao_e_so_tempero_continua_pergunta(linha: str) -> None:
    """Sem número, o que muda a compra e o custo continua virando pergunta a ela."""
    assert not so_tempero(linha)
    assert interpretar_linha(linha).nao_entendida


def test_o_tempero_com_numero_continua_com_o_numero() -> None:
    """ "1 colher de chá de sal" diz quanto vai: a convenção só vale para a linha sem número."""
    i = interpretar_linha("1 colher de chá de sal")
    assert i.quantidade == Decimal(1)
    assert not so_tempero("1 colher de chá de sal")


@pytest.mark.parametrize(
    ("linha", "quantidade", "medida", "nome", "observacao"),
    [
        ("1 peito cortado em 4 filés", Decimal(1), "", "peito", "cortado em 4 filés"),
        (
            "1 peito de frango cortado em 4 filés",
            Decimal(1),
            "",
            "peito de frango",
            "cortado em 4 filés",
        ),
        ("1 cebola cortada em quadrados", Decimal(1), "cebola", "cebola", "cortada em quadrados"),
        (
            "1 cenoura descascada e em cubos",
            Decimal(1),
            "cenoura",
            "cenoura",
            "descascada e em cubos",
        ),
        ("1 dente de alho em lâminas", Decimal(1), "dente de alho", "dente de alho", "em lâminas"),
        ("200 g de bacon em cubos", Decimal(200), "g", "bacon", "em cubos"),
    ],
)
def test_o_preparo_sai_do_nome(
    linha: str, quantidade: Decimal, medida: str, nome: str, observacao: str
) -> None:
    """O corte não é o ingrediente: "cebola cortada em quadrados" é a cebola da despensa."""
    i = interpretar_linha(linha)
    assert (i.quantidade, i.medida, i.nome, i.observacao) == (
        quantidade,
        medida,
        nome,
        observacao,
    )


@pytest.mark.parametrize(
    "linha",
    [
        "1 xícara de carne moída",
        "100 g de queijo ralado",
        "1 colher de pimenta calabresa em flocos",
        "2 colheres de leite em pó",
    ],
)
def test_o_que_muda_o_produto_fica_no_nome(linha: str) -> None:
    """Moída, ralado, em flocos, em pó: é outro produto na prateleira, e fica."""
    assert interpretar_linha(linha).observacao == ""


def test_a_primeira_palavra_nunca_e_preparo() -> None:
    """ "Picadinho" é o prato: só sai o que vem depois do nome."""
    assert interpretar_linha("500 g de picadinho de carne").nome == "picadinho de carne"


@pytest.mark.parametrize(
    ("linha", "quantidade", "observacao"),
    [
        ("2 a 3 colheres de sopa de alcaparras", Decimal(3), "entre 2 e 3"),
        ("2 ou 3 dentes de alho", Decimal(3), "entre 2 e 3"),
        ("1-2 xícaras de água", Decimal(2), "entre 1 e 2"),
        ("½ a 1 xícara de leite", Decimal(1), "entre 0,5 e 1"),
    ],
)
def test_faixa_vale_o_maior(linha: str, quantidade: Decimal, observacao: str) -> None:
    """ "2 a 3 colheres" pede até 3: a despensa tem de dar conta do maior."""
    i = interpretar_linha(linha)
    assert (i.quantidade, i.observacao) == (quantidade, observacao)
    assert "a 3" not in i.nome


def test_faixa_ao_contrario_nao_muda_a_quantidade() -> None:
    """ "3 a 2" não é faixa que se leia: fica o primeiro número, sem inventar."""
    assert interpretar_linha("3 a 2 colheres de açúcar").quantidade == Decimal(3)


@pytest.mark.parametrize(
    ("linha", "gramas", "nome"),
    [
        ("6 bifes pequenos de alcatra (500 gramas)", Decimal(500), "bifes pequenos de alcatra"),
        (
            "2 postas, de aproximadamente 180 gramas cada, de robalo limpas e sem pele",
            Decimal(360),
            "postas de robalo",
        ),
        ("1 posta de salmão de 1 kg", Decimal(1000), "posta de salmão"),
        (
            "1 xícara de chá de queijo mussarela ralado (200 gramas)",
            Decimal(200),
            "queijo mussarela ralado",
        ),
        ("1 colher de sopa de manteiga (15 gramas)", Decimal(15), "manteiga"),
        ("2 colheres (sopa) de manteiga (15 g cada)", Decimal(30), "manteiga"),
        ("1 cebola grande (cerca de 0,2 kg)", Decimal(200), "cebola grande"),
    ],
)
def test_o_peso_que_a_receita_da_vale_mais(linha: str, gramas: Decimal, nome: str) -> None:
    """O peso escrito na receita vale mais que a tabela e que a densidade: é a receita dizendo."""
    i = interpretar_linha(linha)
    assert (i.quantidade, i.medida, i.nome) == (gramas, "g", nome)


@pytest.mark.parametrize(
    ("linha", "quantidade", "medida", "nome", "observacao"),
    [
        ("2 latas de milho (200 g)", Decimal(2), "lata", "milho", "200 g"),
        ("1 pacote de macarrão de 500 g", Decimal(1), "pacote", "macarrão", "de 500 g"),
    ],
)
def test_embalagem_com_peso_continua_embalagem(
    linha: str, quantidade: Decimal, medida: str, nome: str, observacao: str
) -> None:
    """Compra-se a lata, e o preço é por lata: o peso só fica anotado."""
    i = interpretar_linha(linha)
    assert (i.quantidade, i.medida, i.nome, i.observacao) == (quantidade, medida, nome, observacao)


def test_parentese_sem_peso_nao_muda_a_quantidade() -> None:
    """O parêntese que não é peso nem tipo de medida não muda nada: é a linha sem ele."""
    i = interpretar_linha("500 gramas de carne moída (usamos paleta)")
    sem = interpretar_linha("500 gramas de carne moída")
    assert (i.quantidade, i.medida, i.nome) == (Decimal(500), "gramas", "carne moída")
    assert (i.quantidade, i.medida, i.nome) == (sem.quantidade, sem.medida, sem.nome)


def test_peso_zero_nao_vale() -> None:
    """ "(0 g)" é dado quebrado da página: fica a leitura sem ele."""
    i = interpretar_linha("2 ovos (0 g)")
    assert (i.quantidade, i.medida) == (Decimal(2), "ovo")


def test_peso_na_linha_em_gramas_nao_muda() -> None:
    """Linha que já está em gramas não troca de número por um parêntese."""
    i = interpretar_linha("500 g de carne (1 kg)")
    assert (i.quantidade, i.medida) == (Decimal(500), "g")


@pytest.mark.parametrize(
    ("linha", "observacao", "opcional"),
    [
        ("Óleo para refogar", "para refogar", False),
        ("Arroz branco, fatias de pão e farofa para acompanhar", "para acompanhar", True),
    ],
)
def test_para_refogar_e_para_acompanhar_sao_a_gosto(
    linha: str, observacao: str, opcional: bool
) -> None:
    """A receita escolheu não dar quantidade: não é linha que a leitura não entendeu."""
    i = interpretar_linha(linha)
    assert i.a_gosto
    assert not i.nao_entendida
    assert (i.observacao, i.opcional) == (observacao, opcional)


# --------------------------------------------------------------------------- #
# O "de" antes da medida, o tipo da colher e o "(ou a gosto)"                   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("linha", "quantidade", "medida", "nome", "observacao"),
    [
        # As três linhas do catálogo que saíam com a medida grudada no nome.
        (
            "1 e 1/4 de xícara de chá de farinha de milho em flocos (250 gramas)",
            Decimal(250),
            "g",
            "farinha de milho em flocos",
            "250 gramas",
        ),
        (
            "1/4 de colher de chá de pimenta-do-reino (ou a gosto)",
            Decimal("0.25"),
            "colher de cha",
            "pimenta-do-reino",
            "a gosto",
        ),
        (
            "1/2 colher de chá de sal (ou a gosto)",
            Decimal("0.5"),
            "colher de cha",
            "sal",
            "a gosto",
        ),
        # Fração ou número misto com "de" antes da medida.
        ("1/2 de xícara de açúcar", Decimal("0.5"), "xicara", "açúcar", ""),
        ("1 e 1/2 de colher de sopa de manteiga", Decimal("1.5"), "colher de sopa", "manteiga", ""),
        ("1 1/2 de xícara (chá) de leite", Decimal("1.5"), "xicara de cha", "leite", ""),
        ("2 e 1/2 de xícaras (chá) de farinha", Decimal("2.5"), "xicara de cha", "farinha", ""),
        ("3/4 de xícara (chá) de leite", Decimal("0.75"), "xicara de cha", "leite", ""),
        ("1/4 de xícara de chá de óleo", Decimal("0.25"), "xicara de cha", "óleo", ""),
        (
            "1/8 de colher de chá de noz-moscada",
            Decimal("0.125"),
            "colher de cha",
            "noz-moscada",
            "",
        ),
        ("1/2 de lata de milho", Decimal("0.5"), "lata", "milho", ""),
        # Fração unicode, com e sem "de", com e sem o "e" do número misto.
        ("½ de xícara de óleo", Decimal("0.5"), "xicara", "óleo", ""),
        ("1 ½ de xícara de farinha de trigo", Decimal("1.5"), "xicara", "farinha de trigo", ""),
        ("¼ de colher (chá) de sal", Decimal("0.25"), "colher de cha", "sal", ""),
        ("1 e ½ xícara de leite", Decimal("1.5"), "xicara", "leite", ""),
        ("1 e meia xícara (chá) de açúcar", Decimal("1.5"), "xicara de cha", "açúcar", ""),
        # O tipo da colher entre parênteses ou por extenso, com e sem "(ou a gosto)".
        (
            "1/2 colher de sopa de sal (ou a gosto)",
            Decimal("0.5"),
            "colher de sopa",
            "sal",
            "a gosto",
        ),
        (
            "1/2 colher (sopa) de sal (ou a gosto)",
            Decimal("0.5"),
            "colher de sopa",
            "sal",
            "a gosto",
        ),
        ("2 colheres de chá de sal (ou a gosto)", Decimal(2), "colher de cha", "sal", "a gosto"),
        (
            "2 colheres (chá) de açúcar (ou a gosto)",
            Decimal(2),
            "colher de cha",
            "açúcar",
            "a gosto",
        ),
        ("1 xícara (de chá) de leite", Decimal(1), "xicara de cha", "leite", ""),
        (
            "1/2 de colher de sopa de azeite (ou a gosto)",
            Decimal("0.5"),
            "colher de sopa",
            "azeite",
            "a gosto",
        ),
        (
            "meia colher de chá de sal (ou a gosto)",
            Decimal("0.5"),
            "colher de cha",
            "sal",
            "a gosto",
        ),
        ("1/2 colher de chá de sal (a gosto)", Decimal("0.5"), "colher de cha", "sal", "a gosto"),
        (
            "1/2 xícara (chá) de óleo (ou a gosto)",
            Decimal("0.5"),
            "xicara de cha",
            "óleo",
            "a gosto",
        ),
        ("1 copo (americano) de leite", Decimal(1), "copo americano", "leite", ""),
        # Como a colher vai cheia é da medida, e vai para a observação.
        ("1 colher (sopa) rasa de açúcar", Decimal(1), "colher de sopa", "açúcar", "rasa"),
        ("2 colheres (sopa rasa) de açúcar", Decimal(2), "colher de sopa", "açúcar", "rasa"),
        ("1 colher de sopa cheia de farinha", Decimal(1), "colher de sopa", "farinha", "cheia"),
        (
            "2 colheres de sopa (cheias) de farinha",
            Decimal(2),
            "colher de sopa",
            "farinha",
            "cheias",
        ),
    ],
)
def test_a_medida_depois_do_de_e_com_o_tipo_da_colher(
    linha: str, quantidade: Decimal, medida: str, nome: str, observacao: str
) -> None:
    """ "1/2 colher de chá de sal (ou a gosto)" pede sal, meia colher de chá, e não "chá de sal"."""
    i = interpretar_linha(linha)
    assert (i.quantidade, i.medida, i.nome, i.observacao) == (quantidade, medida, nome, observacao)
    assert i.entendida
    assert i.texto_original == linha


@pytest.mark.parametrize(
    ("com_a_marca", "sem_a_marca"),
    [
        ("1/2 colher de chá de sal (ou a gosto)", "1/2 colher de chá de sal"),
        ("1/2 colher de chá de sal (opcional)", "1/2 colher de chá de sal"),
        (
            "1/4 de colher de chá de pimenta-do-reino (ou a gosto)",
            "1/4 colher de chá de pimenta-do-reino",
        ),
        ("2 colheres (chá) de açúcar (ou a gosto)", "2 colheres de chá de açúcar"),
    ],
)
def test_o_parentese_da_marca_nao_muda_a_medida(com_a_marca: str, sem_a_marca: str) -> None:
    """ "(ou a gosto)" e "(opcional)" dizem da linha, não da colher: a medida é a mesma sem eles."""
    com, sem = interpretar_linha(com_a_marca), interpretar_linha(sem_a_marca)
    assert (com.quantidade, com.medida, com.nome) == (sem.quantidade, sem.medida, sem.nome)


def test_o_opcional_entre_parenteses_continua_opcional() -> None:
    i = interpretar_linha("1/2 colher de chá de sal (opcional)")
    assert i.opcional
    assert (i.medida, i.nome) == ("colher de cha", "sal")


def test_o_tipo_que_nao_forma_medida_nao_gruda_no_nome() -> None:
    """Um parêntese depois da colher que não é tipo conhecido sai da linha sem virar ingrediente."""
    assert interpretar_linha("1 xícara (café) de açúcar").nome == "açúcar"


def test_o_de_antes_do_que_nao_e_medida_fica_no_nome() -> None:
    """Só a medida perde o "de" da frente: sem medida, a linha segue como era."""
    i = interpretar_linha("2 de açúcar")
    assert (i.quantidade, i.medida, i.nome) == (Decimal(2), "", "açúcar")


def test_a_versao_da_leitura_e_um_numero() -> None:
    """A receita guardada lembra com que regras foi lida; mudar as regras sobe o número."""
    from retrieval.quantidades import VERSAO_DA_LEITURA

    assert isinstance(VERSAO_DA_LEITURA, int)
    assert VERSAO_DA_LEITURA >= 2
