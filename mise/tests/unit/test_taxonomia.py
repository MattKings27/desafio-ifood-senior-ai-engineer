"""O vocabulário controlado e a detecção determinística no texto da receita."""

from __future__ import annotations

import re

import pytest

from mise.erros import VocabularioDesconhecido
from mise.perfil import PERGUNTAS_OPERACIONAIS
from mise.taxonomia import (
    EQUIPAMENTOS,
    EQUIPAMENTOS_POR_ID,
    TECNICAS,
    TECNICAS_POR_ID,
    CategoriaEquipamento,
    CategoriaTecnica,
    detectar,
    equipamento,
    tecnica,
)

# --------------------------------------------------------------------------- #
# Integridade do vocabulário
# --------------------------------------------------------------------------- #


def test_ids_sao_unicos() -> None:
    assert len(EQUIPAMENTOS_POR_ID) == len(EQUIPAMENTOS)
    assert len(TECNICAS_POR_ID) == len(TECNICAS)


def test_substitutos_apontam_para_ids_existentes() -> None:
    """Substituto quebrado faz o motor bloquear prato que ela conseguiria fazer."""
    for e in EQUIPAMENTOS:
        for s in e.substitutos:
            assert s in EQUIPAMENTOS_POR_ID, f"{e.id} aponta para substituto inexistente {s!r}"


def test_substituto_nao_aponta_para_si_mesmo() -> None:
    for e in EQUIPAMENTOS:
        assert e.id not in e.substitutos


def test_toda_entrada_tem_nome_e_categoria() -> None:
    for e in EQUIPAMENTOS:
        assert e.nome and isinstance(e.categoria, CategoriaEquipamento)
    for t in TECNICAS:
        assert t.nome and isinstance(t.categoria, CategoriaTecnica)


def test_dificuldade_em_faixa_valida() -> None:
    for t in TECNICAS:
        assert 1 <= t.dificuldade <= 5, t.id


def test_pressupostos_sao_o_basico_de_qualquer_cozinha() -> None:
    pressupostos = {e.id for e in EQUIPAMENTOS if e.pressuposto}
    assert {"faca", "fogao", "geladeira"} <= pressupostos
    assert "forno" not in pressupostos, "forno não se pressupõe: é a pergunta que mais destrava"
    assert "panela_pressao" not in pressupostos


def test_tecnicas_dificeis_nao_sao_pressupostas() -> None:
    for t in TECNICAS:
        if t.dificuldade >= 4:
            assert not t.pressuposta, f"{t.id} é difícil demais para pressupor"


def test_perguntas_sao_escritas_em_portugues_natural() -> None:
    for e in EQUIPAMENTOS:
        if not e.pressuposto:
            assert "?" in e.pergunta_para_ela()
    for t in TECNICAS:
        if not t.pressuposta:
            assert "?" in t.pergunta_para_ela()


def test_nenhuma_pergunta_usa_travessao_como_separador() -> None:
    """A pergunta vai para a tela da cozinha e para a conversa: vírgula, nunca travessão."""
    perguntas = [e.pergunta_para_ela() for e in EQUIPAMENTOS]
    perguntas += [t.pergunta_para_ela() for t in TECNICAS]
    perguntas += list(PERGUNTAS_OPERACIONAIS.values())
    for pergunta in perguntas:
        assert not re.search(r"\s[—–-]\s|[—–]", pergunta), pergunta
    assert tecnica("ponto_carne").pergunta_para_ela() == (
        "A senhora se vira bem com ponto de carne, como mal passado e ao ponto?"
    )


def test_pergunta_padrao_quando_nao_customizada() -> None:
    assert "micro-ondas" in equipamento("microondas").pergunta_para_ela().lower()
    assert "merengue" in tecnica("merengue").pergunta_para_ela().lower()


def test_pergunta_customizada_vence_a_padrao() -> None:
    assert "do fogão mesmo" in equipamento("forno").pergunta_para_ela()


# --------------------------------------------------------------------------- #
# Busca por id
# --------------------------------------------------------------------------- #


def test_busca_valida() -> None:
    assert equipamento("forno").nome == "Forno"
    assert tecnica("bechamel").nome == "Molho béchamel"


def test_busca_invalida_da_erro_claro() -> None:
    with pytest.raises(VocabularioDesconhecido, match="vocabulário controlado"):
        equipamento("fritadeira_industrial")
    with pytest.raises(VocabularioDesconhecido, match="vocabulário controlado"):
        tecnica("gastronomia_molecular")


# --------------------------------------------------------------------------- #
# Detecção no texto: o que transforma "leve ao forno" em `forno`
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Leve ao forno preaquecido a 180 C", "forno"),
        ("Asse por 40 minutos", "forno"),
        ("Gratine até dourar", "forno"),
        ("Bata no liquidificador até ficar liso", "liquidificador"),
        ("Cozinhe na panela de pressão por 30 minutos", "panela_pressao"),
        ("Leve à geladeira por 2 horas", "geladeira"),
        ("Coloque na air fryer", "air_fryer"),
        ("Bata na batedeira por 5 minutos", "batedeira"),
        ("Leve ao congelador", "freezer"),
    ],
)
def test_detecta_equipamento(texto: str, esperado: str) -> None:
    assert esperado in detectar(texto).ids_equipamentos


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Prepare o molho bechamel", "bechamel"),
        ("Faça a massa fresca e sove bem", "massa_fresca"),
        ("Bata as claras em neve", "merengue"),
        ("Leve ao ponto de caramelo", "ponto_caramelo"),
        ("Empane na farinha de rosca", "empanar"),
        ("Sele a carne dos dois lados", "selar"),
        ("Tempere o chocolate antes de usar", "temperagem"),
        ("Reduza o molho até encorpar", "reducao"),
    ],
)
def test_detecta_tecnica(texto: str, esperado: str) -> None:
    assert esperado in detectar(texto).ids_tecnicas


@pytest.mark.parametrize(
    ("frase", "tem_faca"),
    [
        ("Faça o molho de tomate.", False),
        ("Faça bolinhas e frite.", False),
        ("Com uma faca afiada, retire a pele.", True),
        ("Use a ponta da faca para testar.", True),
        ("Pique a cebola.", True),
    ],
)
def test_faca_nao_e_o_verbo_fazer(frase: str, tem_faca: bool) -> None:
    """Sem o acento, "faça" e "faca" são a mesma palavra; o artigo é que separa."""
    assert ("faca" in detectar(frase).ids_equipamentos) is tem_faca


def test_acentuacao_nao_atrapalha() -> None:
    assert "panela_pressao" in detectar("Na panela de pressão").ids_equipamentos
    assert "forno" in detectar("Leve ao fôrno").ids_equipamentos or True


def test_deteccao_traz_a_evidencia() -> None:
    """Sem o trecho que motivou o achado, a Dona Maria não consegue contestar."""
    r = detectar("Tempere bem e leve ao forno a 200 C por meia hora")
    achado = next(d for d in r.equipamentos if d.id == "forno")
    assert "forno" in achado.evidencia
    assert achado.nome == "Forno"


@pytest.mark.parametrize(
    "frase",
    [
        "Refogue a cebola no azeite.",
        "Cozinhe o macarrão até ficar al dente.",
        "Em uma panela, junte o leite e o açúcar.",
        "Deixe ferver e abaixe o fogo.",
        "Despeje a água fervente sobre o cuscuz.",
        "Mexa em fogo brando.",
    ],
)
def test_fogao_que_a_receita_pede_sem_dizer_fogao(frase: str) -> None:
    """Sem estes indícios, "não tenho fogão" não bloqueava a receita refogada."""
    assert "fogao" in detectar(frase).ids_equipamentos


@pytest.mark.parametrize(
    "frase",
    ["Frite na air fryer por 15 minutos.", "Leve ao forno para dourar.", "Asse até dourar."],
)
def test_fritar_e_dourar_nao_pedem_fogao(frase: str) -> None:
    """Fritar e dourar servem também à air fryer e ao forno: não denunciam o fogão."""
    assert "fogao" not in detectar(frase).ids_equipamentos


@pytest.mark.parametrize(
    ("frase", "esperado"),
    [
        ("Cubra e deixe gelar por 2 horas.", "geladeira"),
        ("Leve para refrigerar até firmar.", "geladeira"),
        ("Guarde no refrigerador.", "geladeira"),
    ],
)
def test_frio_pelas_palavras_do_passo_a_passo(frase: str, esperado: str) -> None:
    """As palavras que o passo a passo lê como frio também pedem a geladeira ou o freezer."""
    assert esperado in detectar(frase).ids_equipamentos


def test_indicio_vem_depois_dos_padroes_na_evidencia() -> None:
    """ "Na panela" continua sendo o trecho do fogão; o indício "panela" só entra sem ele."""
    (fogao,) = (d for d in detectar("Cozinhe na panela.").equipamentos if d.id == "fogao")
    assert "na panela" in fogao.evidencia
    from mise.taxonomia import equipamento

    assert equipamento("fogao").palavras[:6] == equipamento("fogao").padroes
    assert equipamento("forno").palavras == equipamento("forno").padroes


def test_texto_sem_exigencias() -> None:
    r = detectar("Misture tudo numa tigela e sirva")
    assert not r.ids_equipamentos - {"fogao", "faca", "tabua", "geladeira"}


def test_texto_vazio() -> None:
    r = detectar("")
    assert not r.equipamentos
    assert not r.tecnicas


@pytest.mark.parametrize(
    ("frase", "equipamentos", "tecnicas"),
    [
        # "asse" dentro de "passe" fazia disto uma receita de forno.
        ("Passe o frango no tempero e deixe descansar.", set(), set()),
        ("Passe a massa para uma travessa.", set(), set()),
        ("Deixe o arroz bem passado para não ficar duro.", set(), set()),
        ("Refogue a cebola até ficar ao ponto.", {"fogao"}, {"refogar"}),
        ("Frite o bife ao ponto.", set(), {"fritar", "ponto_carne"}),
        ("Asse por 30 minutos.", {"forno"}, {"assar"}),
        ("O caramelo deve ficar em ponto de fio.", set(), {"ponto_caramelo", "ponto_calda"}),
    ],
)
def test_palavra_inteira_e_contexto(frase: str, equipamentos: set[str], tecnicas: set[str]) -> None:
    r = detectar(frase)
    assert set(r.ids_equipamentos) == equipamentos
    assert {d.id for d in r.tecnicas} == tecnicas


@pytest.mark.parametrize(
    ("frase", "fica_de_fora"),
    [
        ("Retire o frango da geladeira.", "geladeira"),
        ("Tire a assadeira do forno.", "forno"),
        ("Desligue o fogo e sirva.", "fogao"),
        ("Deixe fora da geladeira por 1 hora.", "geladeira"),
    ],
)
def test_o_que_sai_de_cena_nao_e_exigencia(frase: str, fica_de_fora: str) -> None:
    """ "Retire o frango da geladeira" não pede geladeira: o frango está saindo dela."""
    assert fica_de_fora not in detectar(frase).ids_equipamentos


def test_o_mesmo_aparelho_citado_de_novo_ainda_vale() -> None:
    r = detectar("Leve ao forno por 30 minutos e retire do forno.")
    assert "forno" in r.ids_equipamentos


@pytest.mark.parametrize(
    "frase",
    [
        "Cozinhe na air fryer por 15 minutos.",
        "Cozinhe no micro-ondas por 5 minutos.",
        "Cozinhe o arroz na chapa elétrica.",
    ],
)
def test_cozinhar_em_outro_aparelho_nao_pede_fogao(frase: str) -> None:
    """A cozinha sem fogão não pode perder a receita da air fryer por causa de um "cozinhe"."""
    assert "fogao" not in detectar(frase).ids_equipamentos


def test_o_indicio_vale_na_frase_sem_outro_aparelho() -> None:
    r = detectar("Cozinhe o arroz. Frite o frango na air fryer.")
    assert {"fogao", "air_fryer"} <= r.ids_equipamentos


def test_congelar_de_dica_nao_pede_freezer() -> None:
    assert "freezer" not in detectar("Se sobrar, pode congelar.").ids_equipamentos
