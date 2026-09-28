"""A forma das respostas: erro estruturado e dinheiro com texto."""

from __future__ import annotations

import json
from decimal import Decimal

from mise.dinheiro import Dinheiro
from mise.erros import ErroMise, MassaDesconhecida, ViabilidadeNaoConfirmada
from mise.serializacao import _erro_json, _reais, protegido


def test_erro_de_dado_nao_vira_pergunta_a_ela() -> None:
    """Peso, medida e preço nunca se perguntam: o erro de dado diz para não perguntar."""
    erro = MassaDesconhecida("Cobertura de chocolate", 79.90, "1 un")
    payload = _erro_json(erro)
    assert payload["categoria"] == "dado"
    assert "pergunta" not in payload
    assert "Não pergunte" in payload["orientacao"]


def test_erro_de_regra_manda_nao_contornar() -> None:
    payload = _erro_json(ViabilidadeNaoConfirmada("Bolo", "FALTA INFO"))
    assert payload["categoria"] == "regra"
    assert payload["tipo"] == "ViabilidadeNaoConfirmada"
    assert "Não contorne" in payload["orientacao"]


def test_erro_sem_classe_conhecida_e_desconhecido() -> None:
    payload = _erro_json(ErroMise("algo", detalhe=1))
    assert payload["categoria"] == "desconhecido"
    assert payload["contexto"] == {"detalhe": "1"}
    assert "orientacao" not in payload


def test_dinheiro_vai_com_numero_e_texto() -> None:
    assert _reais(Dinheiro(Decimal("2.995"))) == {"valor": 3.0, "texto": "R$ 3,00"}


async def test_protegido_troca_o_erro_pelo_json_e_deixa_o_resto_passar() -> None:
    @protegido
    async def falha() -> str:
        raise ViabilidadeNaoConfirmada("Bolo", "BLOQUEADO")

    @protegido
    async def funciona() -> str:
        return "ok"

    assert json.loads(await falha())["tipo"] == "ViabilidadeNaoConfirmada"
    assert await funciona() == "ok"
    assert funciona.__name__ == "funciona", "o nome da ferramenta sai do wrapper"


def test_receita_sai_com_os_tres_tempos() -> None:
    from mise.receita import ingrediente, receita
    from mise.serializacao import _receita_json

    r = receita(
        "Bolo",
        [ingrediente("3 ovos", "ovos", 3, "ovo")],
        tempo_preparo_min=20,
        tempo_cozimento_min=40,
        tempo_total_min=60,
    )
    dados = _receita_json(r)
    assert (
        dados["tempo_preparo_min"],
        dados["tempo_cozimento_min"],
        dados["tempo_total_min"],
    ) == (20, 40, 60)


def test_avisos_saem_com_tipo_e_texto() -> None:
    from mise.serializacao import avisos_json
    from mise.viabilidade import Avaliacao, Aviso, Checagem, Veredito

    checagem = Checagem("operacional")
    checagem.avisar(Aviso("bocas", "Com uma boca, leva mais tempo."))
    avaliacao = Avaliacao("Arroz", Veredito.APTO, (checagem,))
    assert checagem.veredito is Veredito.APTO, "aviso não muda o veredito"
    assert avisos_json(avaliacao) == [{"tipo": "bocas", "texto": "Com uma boca, leva mais tempo."}]
