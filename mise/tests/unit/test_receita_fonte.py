"""Procedência como invariante do tipo.

O §2.1 manda pesquisar receitas reais na internet. Uma receita apresentada como
pesquisada, sem endereço, não é verificável: a Dona Maria não tem como conferir
de onde vieram as quantidades, e nós não temos como mostrar.

Por isso a regra mora no `__post_init__` e não numa convenção de quem constrói:
uma receita da web sem URL não chega a existir.
"""

from __future__ import annotations

import pytest

from mise.erros import SemProcedencia
from mise.receita import Origem, Receita
from mise.receita import ingrediente as ing


def _receita(**extras) -> Receita:
    return Receita(nome="Bolo", ingredientes=(ing("2 ovos", "ovos", 2, "ovo"),), **extras)


def test_web_sem_url_nao_chega_a_existir() -> None:
    with pytest.raises(SemProcedencia) as capturado:
        _receita(origem=Origem.WEB)

    erro = capturado.value
    assert erro.receita_nome == "Bolo"
    assert "endereço" in str(erro)
    assert "conferir" in str(erro)


def test_web_com_url_vazia_tambem_e_recusada() -> None:
    """String em branco não é endereço."""
    with pytest.raises(SemProcedencia):
        _receita(origem=Origem.WEB, url="   ")


def test_web_com_url_passa() -> None:
    r = _receita(origem=Origem.WEB, url="https://exemplo.com.br/bolo")
    assert r.tem_procedencia


def test_origem_padrao_e_informada_por_ela() -> None:
    """A maioria das receitas nesta conversa vem da boca dela."""
    assert _receita().origem is Origem.INFORMADA_POR_ELA


@pytest.mark.parametrize(
    ("extras", "trecho"),
    [
        ({"origem": Origem.WEB, "url": "https://www.tudogostoso.com.br/x"}, "tudogostoso.com.br"),
        (
            {"origem": Origem.WEB, "url": "https://x.com/y", "fonte": "Caderno da Vó"},
            "Caderno da Vó",
        ),
        ({"origem": Origem.INFORMADA_POR_ELA}, "a senhora me passou"),
        ({"origem": Origem.AUTORAL}, "Bolo"),
    ],
)
def test_citacao_diz_de_onde_veio(extras: dict, trecho: str) -> None:
    """A citação é como o agente credita a fonte em voz alta."""
    assert trecho in _receita(**extras).citacao


def test_citacao_autoral_e_so_o_nome() -> None:
    assert _receita(origem=Origem.AUTORAL).citacao == "Bolo"


def test_erro_de_procedencia_e_recusa_de_regra() -> None:
    """Não é pedido de dado: quem chamou disse de onde veio e não disse onde."""
    from mise.erros import ErroDeRegra

    assert issubclass(SemProcedencia, ErroDeRegra)
