"""As seções do modo de preparo ("Massa", "Cobertura") chegam à tela como a página mostra.

A seção é opcional: a receita guardada antes dela, e a da página que não
divide o preparo, continuam com a lista corrida, gravadas igual.
"""

from __future__ import annotations

from mise.passos import avaliar_passos
from mise.perfil import PerfilCozinha
from mise.receita import Origem, Receita, ingrediente, receita

FARINHA = ingrediente("2 xícaras de farinha", "farinha", 2, "xicara")

PASSOS = ("Bata a massa no liquidificador.", "Asse por 40 minutos.", "Derreta o chocolate.")


def _bolo(secoes: tuple[str | None, ...] = ()) -> Receita:
    return receita(
        "Bolo com cobertura",
        [FARINHA],
        rendimento_porcoes=8,
        modo_preparo=PASSOS,
        url="https://www.receitasnestle.com.br/receitas/bolo",
        secoes_do_preparo=secoes,
    )


def test_a_secao_de_cada_passo_vai_e_volta_do_dossie() -> None:
    bolo = _bolo(("Massa", "Massa", "Cobertura"))
    dados = bolo.para_dict()
    assert dados["secoes_do_preparo"] == ["Massa", "Massa", "Cobertura"]
    assert Receita.de_dict(dados) == bolo
    assert Receita.de_dict(dados).secao_de_cada_passo == ("Massa", "Massa", "Cobertura")


def test_a_receita_sem_secoes_fica_gravada_igual() -> None:
    """Nem a chave aparece: a receita sem seções é o mesmo JSON de antes."""
    assert "secoes_do_preparo" not in _bolo().para_dict()


def test_a_receita_guardada_antes_das_secoes_abre_com_a_lista_corrida() -> None:
    antiga = _bolo().para_dict()
    antiga.pop("secoes_do_preparo", None)
    lida = Receita.de_dict(antiga)
    assert lida.secoes_do_preparo == ()
    assert lida.secao_de_cada_passo == (None, None, None)


def test_secoes_que_nao_batem_com_os_passos_nao_valem() -> None:
    """Título em cima do passo errado é pior do que título nenhum."""
    torta = _bolo(("Massa", "Cobertura"))
    assert torta.secao_de_cada_passo == (None, None, None)


def test_as_secoes_seguem_a_receita_por_porcao_e_a_deteccao() -> None:
    bolo = _bolo(("Massa", None, "Cobertura"))
    assert bolo.por_porcao().secoes_do_preparo == ("Massa", None, "Cobertura")
    assert bolo.com_exigencias_detectadas().secoes_do_preparo == ("Massa", None, "Cobertura")


def test_cada_passo_diz_a_secao_na_tela() -> None:
    bolo = Receita(
        nome="Bolo com cobertura",
        ingredientes=(FARINHA,),
        modo_preparo=PASSOS,
        url="https://exemplo.com.br/bolo",
        origem=Origem.WEB,
        secoes_do_preparo=("Massa", "Massa", "Cobertura"),
    )
    passos = avaliar_passos(bolo, PerfilCozinha.inicial()).para_json()["passos"]
    assert [(p["ordem"], p["texto"], p["secao"]) for p in passos] == [
        (1, PASSOS[0], "Massa"),
        (2, PASSOS[1], "Massa"),
        (3, PASSOS[2], "Cobertura"),
    ]


def test_o_passo_sem_secao_diz_null() -> None:
    passos = avaliar_passos(_bolo(), PerfilCozinha.inicial()).para_json()["passos"]
    assert [p["secao"] for p in passos] == [None, None, None]
