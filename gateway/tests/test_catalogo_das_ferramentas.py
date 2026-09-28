"""Os quatro lugares que conhecem cada ferramenta do motor dizem a mesma lista.

O servidor registra, a política libera (`ESCOPOS`), a conversa diz o que ela
está fazendo (`frases`) e decide o card (`cartoes`). Uma ferramenta nova que
entre em só um deles fica negada pela política, sem frase na linha do tempo ou
sem a decisão do card; este teste é o que obriga a passar pelos quatro.

E o escopo de leitura diz a verdade: chamada de verdade, cada ferramenta de
leitura ou não grava nada, ou está em `REGISTRAM_ARTEFATO`.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
import sessao_de_teste
from mise.mcp_server import abrir_sessao, construir_servidor

from gateway.cartoes import CARTOES
from gateway.frases import FRASES_DO_MOTOR
from gateway.politica import ESCOPOS, REGISTRAM_ARTEFATO, Escopo

PLANILHA = Path(__file__).resolve().parents[2] / "dados" / "despensa_dona_maria.xlsx"


async def test_registradas_liberadas_com_frase_e_com_card_sao_as_mesmas(tmp_path: Path) -> None:
    sessao = abrir_sessao(planilha=PLANILHA, banco=tmp_path / "dossie.db")
    try:
        registradas = {t.name for t in await construir_servidor(sessao).list_tools()}
    finally:
        sessao.dossie.fechar()
    assert registradas == set(ESCOPOS)
    assert registradas == set(FRASES_DO_MOTOR)
    assert registradas == set(CARTOES)


# --------------------------------------------------------------------------- #
# O escopo de leitura não esconde o que grava                                  #
# --------------------------------------------------------------------------- #

PAGINA_COM_RECEITA = (
    '<script type="application/ld+json">'
    '{"@type":"Recipe","name":"Arroz da web","recipeYield":"4",'
    '"recipeIngredient":["1 xícara de arroz","sal a gosto"],'
    '"recipeInstructions":["Refogue e cozinhe na panela."]}'
    "</script>"
)

#: Uma chamada que dá certo para cada ferramenta de leitura, com o arroz com
#: frango já liberado pelo portão.
CHAMADAS_DE_LEITURA: dict[str, dict[str, Any]] = {
    "diagnostico_despensa": {},
    "custo_unitario": {"ingrediente": "frango"},
    "converter_medida_culinaria": {
        "quantidade": 1,
        "medida": "xicara",
        "ingrediente": "farinha de trigo",
    },
    "consultar_perfil": {},
    "proxima_pergunta": {},
    "avaliar_receita": {"receita_id": "arroz-com-frango"},
    "comparar_candidatas": {},
    "calcular_cmv": {"receita_id": "arroz-com-frango"},
    "cenarios_preco": {"receita_id": "arroz-com-frango"},
    "testar_sensibilidade": {"receita_id": "arroz-com-frango", "preco": 12.0},
    "consultar_orcamento": {},
    "consultar_cardapio": {},
    "consultar_precos_de_mercado": {},
    "consultar_gostos": {},
    "buscar_receita_na_web": {"url": "https://www.tudogostoso.com.br/receita/9-arroz"},
    "buscar_preco_na_web": {"ingrediente": "tomate cereja"},
    "consultar_conhecimento": {"pergunta": "posso trocar manteiga por óleo?"},
    "consultar_planilha": {},
    "estimar_preco_preliminar": {"receita_id": "arroz-com-frango"},
    "pauta_de_descoberta": {},
}


def test_toda_ferramenta_de_leitura_tem_uma_chamada_de_verdade() -> None:
    leitura = {nome for nome, escopo in ESCOPOS.items() if escopo is Escopo.LEITURA}
    assert set(CHAMADAS_DE_LEITURA) == leitura


def _versao_do_banco(monitor: sqlite3.Connection) -> int:
    """Muda quando outra conexão grava no arquivo, mesmo que grave o mesmo valor."""
    versao: int = monitor.execute("PRAGMA data_version").fetchone()[0]
    return versao


async def test_so_as_leituras_declaradas_gravam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chamada por chamada: mudou o arquivo do dossiê, ou regravou a planilha em texto?

    Algumas criam na primeira chamada a tabela que ainda não existe (esquema, e
    não dado dela); por isso cada uma roda uma vez antes de medir.
    """
    monkeypatch.setattr("retrieval.busca.baixar", lambda *_a, **_c: PAGINA_COM_RECEITA)
    sessao = sessao_de_teste.sessao_com_receitas(tmp_path)
    # A procura de preço sem rede: nenhum mercado tem, e o "não achei" fica guardado.
    sessao.pesquisador_de_precos = lambda _nome, dimensoes, _prazo: (dimensoes[0], [])
    assert sessao.arquivo_txt is not None
    servidor = construir_servidor(sessao)

    async def chamar(nome: str, **outros: Any) -> None:
        resultado = await servidor.call_tool(nome, {**CHAMADAS_DE_LEITURA[nome], **outros})
        resposta = json.loads(resultado.content[0].text)
        assert "erro" not in resposta, (nome, resposta)

    for nome in CHAMADAS_DE_LEITURA:
        await chamar(nome)
    # Endereço que já está no catálogo volta dele, sem gravar: o que grava é a página nova.
    pagina_nova = {"url": "https://www.tudogostoso.com.br/receita/10-outro-arroz"}
    gravaram: set[str] = set()
    with closing(sqlite3.connect(tmp_path / "dossie.db")) as monitor:
        for nome in CHAMADAS_DE_LEITURA:
            sessao.arquivo_txt.unlink(missing_ok=True)
            antes = _versao_do_banco(monitor)
            novo = {
                "buscar_receita_na_web": pagina_nova,
                "buscar_preco_na_web": {"ingrediente": "tomate grape"},
            }
            await chamar(nome, **novo.get(nome, {}))
            if _versao_do_banco(monitor) != antes or sessao.arquivo_txt.exists():
                gravaram.add(nome)
    sessao.dossie.fechar()
    assert gravaram == REGISTRAM_ARTEFATO
