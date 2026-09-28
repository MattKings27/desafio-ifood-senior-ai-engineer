"""Os detalhes do dono do turno: contexto da tela, erros do Hermes, prévias e caminhos raros."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import sessao_de_teste
from fastapi import FastAPI
from hermes_falso import HermesFalso, chamada, mensagens_do_turno, turno
from mise.mcp_server import Sessao

from gateway.conversa import (
    LIMITE_DE_TOKENS,
    Configuracao,
    Pedido,
    ServicoDeConversa,
    _falha_do_hermes,
    _previa,
    linha_do_contexto,
    quadro_sse,
    resolver_contexto,
)
from gateway.conversas_db import EstadoDoTurno
from gateway.eventos_do_turno import (
    DEMOROU,
    FORA_DO_AR,
    INTERROMPIDO,
    PROBLEMA,
    Falha,
    Normalizador,
)
from gateway.frases import SENTINELA
from gateway.hermes_cliente import (
    AgenteOcupada,
    ChaveAusente,
    ChaveRecusada,
    ConexaoInterrompida,
    FalhaNoHermes,
    TempoEsgotado,
)
from gateway.http import criar_app

ORIGEM = "http://localhost:3000"


@pytest.fixture
def sessao(tmp_path: Path) -> Sessao:
    return sessao_de_teste.sessao_com_receitas(tmp_path)


@pytest.fixture
def hermes() -> HermesFalso:
    return HermesFalso()


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, hermes: HermesFalso) -> FastAPI:
    banco = tmp_path / "dossie.db"
    sessao_de_teste.preparar_dossie(banco)
    monkeypatch.setenv("MISE_PLANILHA", str(sessao_de_teste.PLANILHA))
    monkeypatch.setenv("MISE_DOSSIE", str(banco))
    for variavel in ("MISE_AUDITORIA", "MISE_CONVERSAS", "MISE_AUDITOR_URL"):
        monkeypatch.delenv(variavel, raising=False)
    app = criar_app()
    sessao_de_teste.guardar_receitas(app.state.sessao)
    servico: ServicoDeConversa = app.state.conversa
    servico.fabrica_do_cliente = hermes.cliente
    servico.configuracao = Configuracao(keepalive_s=0.05, espera_da_parada_s=0.3)
    servico.home = tmp_path / "hermes"
    return app


@pytest.fixture
def servico(app: FastAPI) -> ServicoDeConversa:
    servico: ServicoDeConversa = app.state.conversa
    return servico


@pytest.fixture
async def api(app: FastAPI, servico: ServicoDeConversa) -> AsyncIterator[httpx.AsyncClient]:
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://127.0.0.1") as cliente:
        yield cliente
    await servico.fechar()


async def _turno(servico: ServicoDeConversa, conversa_id: str, texto: str, **extra: Any) -> str:
    turno_id = await servico.iniciar_turno(
        conversa_id, Pedido(texto, extra.pop("id_cliente", f"u-{texto[:8]}"), **extra)
    )
    await servico.esperar(turno_id)
    return turno_id


# --------------------------------------------------------------------------- #
# Configuração e funções soltas                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("", LIMITE_DE_TOKENS),
        ("90000", 90_000),
        ("muito", LIMITE_DE_TOKENS),
        ("0", LIMITE_DE_TOKENS),
    ],
)
def test_limite_de_tokens_do_ambiente(valor: str, esperado: int) -> None:
    assert (
        Configuracao.do_ambiente({"MISE_CONVERSA_LIMITE_TOKENS": valor}).limite_de_tokens
        == esperado
    )


@pytest.mark.parametrize(
    ("erro", "esperado"),
    [
        (AgenteOcupada("ocupada"), "consultora"),
        (ConexaoInterrompida("caiu"), "rede"),
        (ChaveAusente("sem chave"), "rede"),
        (ChaveRecusada("recusada"), "rede"),
        (TempoEsgotado("demorou"), "tempo"),
        (FalhaNoHermes("500"), "consultora"),
    ],
)
def test_erro_do_hermes_vira_categoria_do_contrato(erro: Exception, esperado: str) -> None:
    falha = _falha_do_hermes(erro)  # type: ignore[arg-type]
    assert falha.categoria == esperado
    assert falha.mensagem in {FORA_DO_AR, DEMOROU, PROBLEMA} or "outra conversa" in falha.mensagem


def test_previa_sem_markdown_e_cortada() -> None:
    assert _previa("**Gravado.** Arroz,\n\n sai R$ 18,00.") == "Gravado. Arroz, sai R$ 18,00."
    assert _previa(f"Sai {SENTINELA} a porção") == "Sai R$ ··· a porção"
    longa = _previa("palavra " * 30)
    assert longa.endswith("…") and len(longa) <= 90


def test_quadro_sse() -> None:
    assert quadro_sse({"seq": 3, "tipo": "texto.parcial", "delta": "Olá"}) == (
        'id: 3\ndata: {"seq":3,"tipo":"texto.parcial","delta":"Olá"}\n\n'
    )


# --------------------------------------------------------------------------- #
# O contexto da tela                                                           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("bruto", "rotulo"),
    [
        ({"tipo": "ingrediente", "id": "alcaparras"}, "Alcaparras"),
        ({"tipo": "pendencia", "id": "cobertura-de-chocolate"}, "Cobertura de chocolate"),
        ({"tipo": "receita", "id": "arroz-com-frango"}, "Arroz com frango"),
        ({"tipo": "receita", "id": "Bolo de Fubá"}, "Bolo de fubá"),
        ({"tipo": "equipamento", "id": "forno"}, "Forno"),
        ({"tipo": "tecnica", "id": "bechamel"}, "Molho béchamel"),
        ({"tipo": "restricao", "id": "bocas_fogao"}, "bocas fogao"),
        ({"tipo": "tela", "id": "despensa", "tela": "despensa"}, "Despensa"),
    ],
)
def test_contexto_conhecido(sessao: Sessao, bruto: dict[str, str], rotulo: str) -> None:
    contexto = resolver_contexto(sessao, bruto)
    assert contexto is not None and contexto["rotulo"] == rotulo


def test_prato_do_cardapio_e_contexto_conhecido(sessao: Sessao) -> None:
    sessao.decidir("Arroz com frango", "aceito", "", 18.0)
    # Some da lista de candidatas, mas continua no cardápio.
    with sessao.dossie.cursor() as cur:
        cur.execute("DELETE FROM candidatas")
    contexto = resolver_contexto(sessao, {"tipo": "prato", "id": "arroz-com-frango"})
    assert contexto is not None and contexto["rotulo"] == "Arroz com frango"


@pytest.mark.parametrize(
    "bruto",
    [
        {"tipo": "ingrediente", "id": "caviar"},
        {"tipo": "receita", "id": "lasanha"},
        {"tipo": "equipamento", "id": "teletransporte"},
        {"tipo": "tela", "id": "admin"},
        {"tipo": "coisa", "id": "x"},
        {},
    ],
)
def test_contexto_desconhecido(sessao: Sessao, bruto: dict[str, str]) -> None:
    assert resolver_contexto(sessao, bruto) is None


def test_tela_desconhecida_no_contexto_vira_nada(sessao: Sessao) -> None:
    contexto = resolver_contexto(sessao, {"tipo": "ingrediente", "id": "sal", "tela": "hack"})
    assert contexto is not None and contexto["tela"] is None


def test_linha_do_contexto() -> None:
    assert linha_do_contexto(None) is None
    assert linha_do_contexto({"tipo": "receita", "rotulo": "Bolo de R$ 10"}) == (
        "[a senhora está vendo a receita Bolo de …]"
    )


# --------------------------------------------------------------------------- #
# Caminhos raros do turno                                                      #
# --------------------------------------------------------------------------- #


async def test_card_de_rota_que_existe_no_turno(
    servico: ServicoDeConversa, hermes: HermesFalso
) -> None:
    """cenarios_preco do prato aprovado: a rota /api/precos existe e devolve os três."""
    hermes.roteiros.append(
        turno(
            ["São três caminhos."],
            antes=chamada("mcp__mise__cenarios_preco", {"prato": "Arroz com frango"}),
        )
    )
    conversa = servico.banco.criar_conversa()
    turno_id = await _turno(servico, conversa.id, "Quanto cobro?")
    eventos = servico._vivos[turno_id].eventos
    (cartao,) = [e for e in eventos if e["tipo"] == "cartao"]
    assert cartao["ref"]["rota"] == "/api/precos?prato=Arroz%20com%20frango"
    assert len(cartao["dados"]["cenarios"]) == 3
    assert cartao["dados"]["cmv"]["texto"] == "R$ 3,00"
    sugestoes = next(e for e in eventos if e["tipo"] == "sugestoes")["opcoes"]
    assert [s["rotulo"] for s in sugestoes] == ["Quero outro preço", "Vou pensar"]


async def test_card_de_prato_que_o_portao_recusa_nao_aparece(
    servico: ServicoDeConversa, hermes: HermesFalso
) -> None:
    hermes.roteiros.append(
        turno(
            ["Esse ainda não dá."],
            antes=chamada("mcp__mise__cenarios_preco", {"prato": "Bolo de fubá"}),
        )
    )
    conversa = servico.banco.criar_conversa()
    turno_id = await _turno(servico, conversa.id, "E o bolo?")
    assert not [e for e in servico._vivos[turno_id].eventos if e["tipo"] == "cartao"]


async def test_buscar_na_api(servico: ServicoDeConversa, monkeypatch: pytest.MonkeyPatch) -> None:
    assert (await servico._buscar_na_api("/metricas"))[1] is None, "texto, não JSON"
    assert (await servico._buscar_na_api("/api/orcamento"))[0] == 200
    interno = servico._interno
    assert interno is not None

    async def quebra(*_: Any, **__: Any) -> Any:
        raise httpx.ConnectError("fora")

    monkeypatch.setattr(interno, "get", quebra)
    assert await servico._buscar_na_api("/api/orcamento") == (500, None)
    servico.app = None
    assert await servico._buscar_na_api("/api/orcamento") == (404, {"detail": "Not Found"})


async def test_hermes_que_recusa_parar_nao_quebra(
    servico: ServicoDeConversa, hermes: HermesFalso
) -> None:
    import asyncio

    original = hermes.__call__

    async def recusa_parar(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/stop"):
            return httpx.Response(409, json={"error": {"message": "run_not_active"}})
        return await original(request)

    servico.fabrica_do_cliente = lambda: _cliente(recusa_parar)
    nunca = asyncio.Event()
    from hermes_falso import Esperar

    hermes.roteiros.append(turno(["..."], depois=[Esperar(nunca)]))
    conversa = servico.banco.criar_conversa()
    turno_id = await servico.iniciar_turno(conversa.id, Pedido("Oi", "u-recusa"))
    while servico._vivos[turno_id].run_id is None:
        await asyncio.sleep(0.01)
    assert (await servico.parar(conversa.id, turno_id))[0] == 202
    await servico.esperar(turno_id)
    assert servico._vivos[turno_id].estado is EstadoDoTurno.CANCELADO


def _cliente(rota: Any) -> Any:
    from hermes_falso import CHAVE, PERFIL

    from gateway.hermes_cliente import ClienteHermes

    return ClienteHermes(
        perfil=PERFIL, chave=CHAVE, origem_da_chave="teste", transporte=httpx.MockTransport(rota)
    )


async def test_erro_inesperado_no_turno_vira_falha_da_consultora(
    servico: ServicoDeConversa, hermes: HermesFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def quebra(self: Normalizador, evento: Any) -> None:
        raise RuntimeError("bug")

    monkeypatch.setattr(Normalizador, "processar", quebra)
    hermes.roteiros.append(turno(["Oi"]))
    conversa = servico.banco.criar_conversa()
    turno_id = await _turno(servico, conversa.id, "Oi")
    fim = servico._vivos[turno_id].eventos[-1]
    assert (fim["tipo"], fim["mensagem"]) == ("turno.falhou", PROBLEMA)


async def test_banco_ilegivel_na_conferencia_nao_para_o_turno(
    servico: ServicoDeConversa, hermes: HermesFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    def ilegivel(_conversa_id: str) -> Any:
        raise sqlite3.OperationalError("disco cheio")

    hermes.roteiros.append(
        turno(
            ["Gastou R$ 663,39."],
            mensagens=mensagens_do_turno(("mcp__mise__diagnostico_despensa", "R$ 663,39")),
        )
    )
    conversa = servico.banco.criar_conversa()
    monkeypatch.setattr(servico.banco, "valores_conferidos", ilegivel)
    turno_id = await _turno(servico, conversa.id, "Quanto gastei?")
    final = next(e for e in servico._vivos[turno_id].eventos if e["tipo"] == "texto.final")
    assert (final["texto"], final["retirados"]) == ("Gastou R$ 663,39.", 0)


async def test_reenvio_depois_de_apagarem_a_bolha(
    servico: ServicoDeConversa, hermes: HermesFalso
) -> None:
    hermes.fora_do_ar = True
    conversa = servico.banco.criar_conversa()
    primeiro = await _turno(servico, conversa.id, "Oi", id_cliente="u-bolha")
    registro = servico.banco.turno(primeiro)
    assert registro is not None and registro.mensagem_id is not None
    with servico.banco._transacao() as cur:
        cur.execute("DELETE FROM mensagens WHERE id = ?", (registro.mensagem_id,))
    hermes.fora_do_ar = False
    hermes.roteiros.append(turno(["Voltei."]))
    await _turno(servico, conversa.id, "Oi", id_cliente="u-bolha")
    papeis = [m.papel.value for m in servico.banco.mensagens(conversa.id)]
    assert papeis == ["consultora", "senhora", "consultora"]


async def test_retomada_pula_mensagem_sem_texto(
    servico: ServicoDeConversa, hermes: HermesFalso
) -> None:
    conversa = servico.banco.criar_conversa()
    hermes.roteiros.append(turno(["Primeira resposta."], uso={"input_tokens": 10}))
    await _turno(servico, conversa.id, "Primeira")
    hermes.fora_do_ar = True
    await _turno(servico, conversa.id, "Segunda")
    hermes.fora_do_ar = False
    servico.banco.registrar_tokens(conversa.id, 10**7)
    hermes.roteiros.append(turno(["Retomado."]))
    await _turno(servico, conversa.id, "Terceira")
    mensagem = hermes.turnos[-1]["message"]
    assert '- você: "Primeira resposta."' in mensagem
    assert mensagem.count("- a senhora:") == 3


async def test_estado_de_turno_gravado_em_andamento_sem_dono(
    api: httpx.AsyncClient, servico: ServicoDeConversa
) -> None:
    """Uma linha em andamento que nenhum processo conduz (só acontece se o banco foi mexido)."""
    conversa = servico.banco.criar_conversa()
    orfao = servico.banco.criar_turno(conversa.id, None, "u-orfao")
    estado = (await api.get(f"/api/conversas/{conversa.id}/turnos/{orfao.id}")).json()["dados"]
    assert estado["estado"] == "em_andamento" and "terminado_texto" not in estado
    resposta = await api.get(f"/api/conversas/{conversa.id}/turnos/{orfao.id}/eventos")
    assert '"mensagem":"' + INTERROMPIDO in resposta.text
    assert "interrompido" not in resposta.text.split(INTERROMPIDO)[1]
    await servico.esperar("t-nao-existe")


async def test_cartao_gravado_sem_instante(servico: ServicoDeConversa) -> None:
    parte = {
        "tipo": "cartao",
        "cartao": {"cartao_id": "k", "tipo_cartao": "orcamento", "dados": {}},
    }
    assert servico._parte(parte) == parte
    assert servico._parte({"tipo": "texto", "texto": "oi"}) == {"tipo": "texto", "texto": "oi"}


async def test_acao_grande_demais_e_recusada(
    api: httpx.AsyncClient, servico: ServicoDeConversa
) -> None:
    conversa = servico.banco.criar_conversa()
    resposta = await api.post(
        f"/api/conversas/{conversa.id}/turnos",
        json={
            "texto": "oi",
            "id_cliente": "u-grande",
            "acao": {"tipo": "avaliar", "notas": "x" * 3000},
        },
        headers={"Origin": ORIGEM},
    )
    assert resposta.status_code == 422


async def test_fechar_sem_nada_aberto(servico: ServicoDeConversa) -> None:
    await servico.fechar()
    await servico.fechar()


def test_falha_de_rede_por_padrao_na_queda() -> None:
    assert Falha("rede", INTERROMPIDO).categoria == "rede"
