"""O cliente do servidor de API do Hermes, contra um Hermes falso.

O que estes testes protegem, na ordem em que doeria:

1. A chave nunca aparece em log, exceção, traceback ou `repr`.
2. Um frame SSE partido em qualquer byte vira os mesmos eventos: um `R$` cortado
   entre dois pedaços não pode sumir nem duplicar.
3. Cada status do Hermes vira um erro com nome e mensagem em pt-BR.
4. A chave de `MISE_HERMES_CHAVE` vence a do `.env`, e o `.env` é lido como o
   Hermes lê.
"""

from __future__ import annotations

import json
import logging
import random
import secrets
import traceback
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from gateway import hermes_cliente as hc
from gateway.hermes_cliente import (
    AgenteOcupada,
    ChaveAusente,
    ChaveRecusada,
    ChaveSecreta,
    ClienteHermes,
    ConexaoInterrompida,
    Conflito,
    EventoSSE,
    FalhaNoHermes,
    HermesForaDoAr,
    LeitorSSE,
    NaoEncontrado,
    PedidoRecusado,
    RespostaInvalida,
    TempoEsgotado,
)

CHAVE = "segredo-de-teste-" + secrets.token_hex(12)
PERFIL = "sabor-da-maria"


# --------------------------------------------------------------------------- #
# Um Hermes falso                                                              #
# --------------------------------------------------------------------------- #


class Pedacos(httpx.AsyncByteStream):
    """Um corpo que chega em pedaços, e opcionalmente quebra no fim."""

    def __init__(self, pedacos: list[bytes], erro: Exception | None = None) -> None:
        self._pedacos = pedacos
        self._erro = erro

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for pedaco in self._pedacos:
            yield pedaco
        if self._erro is not None:
            raise self._erro

    async def aclose(self) -> None:
        return None


Rota = Callable[[httpx.Request], httpx.Response]


class HermesFalso:
    """Responde por (método, caminho) e guarda cada pedido que recebeu."""

    def __init__(self, rotas: dict[tuple[str, str], Rota] | None = None) -> None:
        self.rotas = rotas or {}
        self.pedidos: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.pedidos.append(request)
        caminho = request.url.raw_path.decode().split("?", 1)[0]  # cru: o escape conta
        rota = self.rotas.get((request.method, caminho))
        if rota is None:
            return httpx.Response(404, json={"error": {"message": f"sem rota {caminho}"}})
        return rota(request)

    def transporte(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def _json(status: int, corpo: Any, **cabecalhos: str) -> Rota:
    return lambda _request: httpx.Response(status, json=corpo, headers=cabecalhos)


def _autenticado(corpo: Any) -> Rota:
    """Como o Hermes: 401 sem a chave do perfil."""

    def rota(request: httpx.Request) -> httpx.Response:
        if request.headers.get("Authorization") != f"Bearer {CHAVE}":
            return httpx.Response(
                401,
                json={
                    "error": {
                        "message": "Invalid gateway API key (API_SERVER_KEY)",
                        "type": "gateway_auth_error",
                        "code": "gateway_auth_failed",
                    }
                },
            )
        return httpx.Response(200, json=corpo)

    return rota


def _sse(
    pedacos: list[bytes], erro: Exception | None = None, tipo: str = "text/event-stream"
) -> Rota:
    return lambda _request: httpx.Response(
        200, headers={"content-type": tipo}, stream=Pedacos(pedacos, erro)
    )


def _cliente(falso: HermesFalso, **opcoes: Any) -> ClienteHermes:
    opcoes.setdefault("chave", ChaveSecreta(CHAVE))
    opcoes.setdefault("origem_da_chave", "/tmp/.env")
    return ClienteHermes(perfil=PERFIL, transporte=falso.transporte(), **opcoes)


SAUDAVEL = {"status": "ok", "platform": "hermes-agent", "version": "0.21.4"}
SESSOES = {"object": "list", "data": [{"id": "s1", "title": "Conversa"}], "has_more": False}


def _frame(evento: str | None, dados: Any) -> bytes:
    prefixo = f"event: {evento}\n" if evento else ""
    return f"{prefixo}data: {json.dumps(dados, ensure_ascii=False)}\n\n".encode()


TURNO = b"".join(
    [
        _frame("run.started", {"run_id": "run_1", "seq": 1, "user_message": {"content": "Oi"}}),
        b": keepalive\n\n",
        _frame(
            "assistant.delta", {"run_id": "run_1", "delta": "A porção sai R$ 2,47 de ingrediente"}
        ),
        _frame(
            "tool.started", {"tool_name": "mcp__mise__avaliar_receita", "args": {"prato": "pão"}}
        ),
        b": keepalive\n\n",
        _frame("tool.completed", {"tool_name": "mcp__mise__avaliar_receita"}),
        _frame(
            "assistant.completed", {"content": "Dá pra fazer, e não é caro.", "session_id": "s1"}
        ),
        _frame("run.completed", {"session_id": "s2", "usage": {"input_tokens": 10}}),
        _frame("done", {}),
    ]
)
NOMES_DO_TURNO = [
    "run.started",
    "assistant.delta",
    "tool.started",
    "tool.completed",
    "assistant.completed",
    "run.completed",
    "done",
]


def _ler(leitor: LeitorSSE, pedacos: list[bytes]) -> list[EventoSSE]:
    eventos: list[EventoSSE] = []
    for pedaco in pedacos:
        eventos.extend(leitor.alimentar(pedaco))
    eventos.extend(leitor.terminar())
    return eventos


# --------------------------------------------------------------------------- #
# A chave                                                                      #
# --------------------------------------------------------------------------- #


def test_chave_secreta_nao_se_deixa_imprimir() -> None:
    chave = ChaveSecreta(CHAVE)
    assert CHAVE not in repr(chave)
    assert CHAVE not in str(chave)
    assert CHAVE not in f"{chave}"
    assert chave.revelar() == CHAVE
    assert chave.igual_a(ChaveSecreta(CHAVE))
    assert not chave.igual_a(ChaveSecreta(CHAVE + "x"))


def test_chave_encontrada_nao_vaza_no_repr() -> None:
    assert CHAVE not in repr(hc.ChaveEncontrada(ChaveSecreta(CHAVE), "MISE_HERMES_CHAVE"))


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("API_SERVER_KEY=abc", "abc"),
        ("export API_SERVER_KEY=abc", "abc"),
        ("  API_SERVER_KEY = abc  ", "abc"),
        ('API_SERVER_KEY="a b"', "a b"),
        ('API_SERVER_KEY="a\\"b"', 'a"b'),
        ('API_SERVER_KEY="abc" # comentário', "abc"),
        ('API_SERVER_KEY="abc', '"abc'),
        ("API_SERVER_KEY='abc' # comentário", "abc"),
        ("API_SERVER_KEY=abc # comentário", "abc"),
        ("API_SERVER_KEY=abc#def", "abc#def"),
        ("# API_SERVER_KEY=comentada\n\nOUTRA=1\nsem_igual\nAPI_SERVER_KEY=vale", "vale"),
        ("API_SERVER_KEY=primeira\nAPI_SERVER_KEY=ultima", "ultima"),
        ("API_SERVER_KEYS=outra", None),
        ("", None),
    ],
)
def test_le_o_env_como_o_hermes(texto: str, esperado: str | None) -> None:
    assert hc.ler_valor_do_env(texto, "API_SERVER_KEY") == esperado


def test_hermes_home_segue_a_variavel_do_hermes(tmp_path: Path, monkeypatch) -> None:
    assert hc.hermes_home({"HERMES_HOME": str(tmp_path)}) == tmp_path
    assert hc.hermes_home({}) == Path.home() / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "x"))
    assert hc.hermes_home() == tmp_path / "x"


def test_caminho_do_env_do_perfil_e_do_padrao(tmp_path: Path, monkeypatch) -> None:
    assert hc.caminho_do_env("default", tmp_path) == tmp_path / ".env"
    assert hc.caminho_do_env(PERFIL, tmp_path) == tmp_path / "profiles" / PERFIL / ".env"
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert hc.caminho_do_env(PERFIL) == tmp_path / "profiles" / PERFIL / ".env"


@pytest.mark.parametrize("perfil", ["", "../fora", "a..b", "com espaço", "/abs", "-x"])
def test_perfil_invalido_nao_vira_caminho(perfil: str) -> None:
    with pytest.raises(ValueError, match="perfil inválido"):
        hc.validar_perfil(perfil)


def _perfil_com_chave(home: Path, valor: str | None, perfil: str = PERFIL) -> Path:
    pasta = home / "profiles" / perfil
    pasta.mkdir(parents=True, exist_ok=True)
    env = pasta / ".env"
    env.write_text(
        "OUTRA=1\n" + (f"API_SERVER_KEY={valor}\n" if valor is not None else ""), encoding="utf-8"
    )
    return env


def test_variavel_de_ambiente_vence_o_arquivo(tmp_path: Path) -> None:
    _perfil_com_chave(tmp_path, "do-arquivo-" + "x" * 20)
    achada = hc.descobrir_chave(PERFIL, ambiente={"MISE_HERMES_CHAVE": CHAVE}, home=tmp_path)
    assert achada.chave.revelar() == CHAVE
    assert achada.origem == "MISE_HERMES_CHAVE"


def test_sem_variavel_le_o_env_do_perfil(tmp_path: Path) -> None:
    env = _perfil_com_chave(tmp_path, CHAVE)
    achada = hc.descobrir_chave(PERFIL, ambiente={"MISE_HERMES_CHAVE": "  "}, home=tmp_path)
    assert achada.chave.revelar() == CHAVE
    assert achada.origem == str(env)


def test_le_o_home_do_ambiente_quando_nao_passado(tmp_path: Path, monkeypatch) -> None:
    _perfil_com_chave(tmp_path, CHAVE)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("MISE_HERMES_CHAVE", raising=False)
    assert hc.descobrir_chave(PERFIL).chave.revelar() == CHAVE


def test_variavel_curta_demais_e_recusada(tmp_path: Path) -> None:
    with pytest.raises(ChaveAusente, match="menos de 16"):
        hc.descobrir_chave(PERFIL, ambiente={"MISE_HERMES_CHAVE": "curta"}, home=tmp_path)


def test_chave_ausente_diz_onde_procurou(tmp_path: Path) -> None:
    _perfil_com_chave(tmp_path, None)
    with pytest.raises(ChaveAusente) as erro:
        hc.descobrir_chave(PERFIL, ambiente={}, home=tmp_path)
    assert "MISE_HERMES_CHAVE" in str(erro.value)
    assert str(tmp_path / "profiles" / PERFIL / ".env") in str(erro.value)


def test_arquivo_inexistente_e_chave_ausente(tmp_path: Path) -> None:
    with pytest.raises(ChaveAusente):
        hc.descobrir_chave(PERFIL, ambiente={}, home=tmp_path)


def test_chave_do_arquivo_curta_demais(tmp_path: Path) -> None:
    _perfil_com_chave(tmp_path, "curta")
    with pytest.raises(ChaveAusente, match="menos de 16"):
        hc.descobrir_chave(PERFIL, ambiente={}, home=tmp_path)


def test_env_ilegivel_nao_passa_por_ausente(tmp_path: Path) -> None:
    """Se o arquivo existe e não se lê, gerar outra chave por cima seria o erro."""
    (tmp_path / "profiles" / PERFIL / ".env").mkdir(parents=True)
    with pytest.raises(ChaveAusente, match="Não deu para ler"):
        hc.ler_chave_do_env(tmp_path / "profiles" / PERFIL / ".env")


def test_chave_utilizavel_tem_16_ou_mais() -> None:
    assert not hc.chave_utilizavel(None)
    assert not hc.chave_utilizavel(ChaveSecreta("x" * 15))
    assert hc.chave_utilizavel(ChaveSecreta("x" * 16))


# --------------------------------------------------------------------------- #
# Montagem do cliente                                                          #
# --------------------------------------------------------------------------- #


async def test_do_ambiente_com_chave(tmp_path: Path) -> None:
    _perfil_com_chave(tmp_path, CHAVE, perfil="outro-perfil")
    ambiente = {"MISE_HERMES_URL": "http://127.0.0.1:9999/", "MISE_HERMES_PERFIL": "outro-perfil"}
    async with ClienteHermes.do_ambiente(ambiente, home=tmp_path) as cliente:
        assert cliente.url == "http://127.0.0.1:9999"
        assert cliente.perfil == "outro-perfil"
        assert cliente.prefixo == "/p/outro-perfil"
        assert cliente.tem_chave
        assert "presente" in repr(cliente)
        assert CHAVE not in repr(cliente)


async def test_do_ambiente_sem_chave_guarda_o_motivo(tmp_path: Path) -> None:
    falso = HermesFalso({("GET", "/health"): _json(200, SAUDAVEL)})
    cliente = ClienteHermes.do_ambiente({}, home=tmp_path, transporte=falso.transporte())
    assert not cliente.tem_chave
    assert "ausente" in repr(cliente)
    with pytest.raises(ChaveAusente, match="etapa 'API do agente'"):
        await cliente.saude()
    await cliente.fechar()


async def test_sem_chave_e_sem_motivo_ainda_explica() -> None:
    async with ClienteHermes(perfil=PERFIL) as cliente:
        with pytest.raises(ChaveAusente, match=PERFIL):
            await cliente.listar_sessoes()


def test_url_invalida() -> None:
    with pytest.raises(ValueError, match="http"):
        ClienteHermes(url="ftp://x")
    with pytest.raises(ValueError, match="http"):
        ClienteHermes(url="127.0.0.1:8642")


def test_perfil_padrao_nao_tem_prefixo() -> None:
    assert ClienteHermes(perfil="default").prefixo == ""


# --------------------------------------------------------------------------- #
# Rotas                                                                        #
# --------------------------------------------------------------------------- #


async def test_saude_confere_a_porta_e_a_chave_do_perfil() -> None:
    falso = HermesFalso(
        {
            ("GET", "/health"): _json(200, SAUDAVEL),
            ("GET", f"/p/{PERFIL}/api/sessions"): _autenticado(SESSOES),
        }
    )
    async with _cliente(falso) as cliente:
        saude = await cliente.saude()
    assert (saude.versao, saude.perfil) == ("0.21.4", PERFIL)
    saude_pedido, sessoes_pedido = falso.pedidos
    assert "Authorization" not in saude_pedido.headers, "/health não precisa de chave"
    assert sessoes_pedido.headers["Authorization"] == f"Bearer {CHAVE}"
    assert sessoes_pedido.url.params["limit"] == "1"


async def test_versao_desconhecida_vira_interrogacao() -> None:
    falso = HermesFalso({("GET", "/health"): _json(200, {"status": "ok"})})
    async with _cliente(falso) as cliente:
        assert await cliente.versao() == "?"


async def test_criar_sessao() -> None:
    falso = HermesFalso(
        {
            ("POST", f"/p/{PERFIL}/api/sessions"): _json(
                201, {"session": {"id": "api_1", "title": "Oi"}}
            )
        }
    )
    async with _cliente(falso) as cliente:
        sessao = await cliente.criar_sessao("Oi", sessao_id="api_1")
        await cliente.criar_sessao()
    assert sessao["id"] == "api_1"
    assert json.loads(falso.pedidos[0].content) == {"title": "Oi", "id": "api_1"}
    assert json.loads(falso.pedidos[1].content) == {}


@pytest.mark.parametrize("corpo", [{"session": None}, {"session": {"title": "sem id"}}, []])
async def test_criar_sessao_resposta_torta(corpo: Any) -> None:
    falso = HermesFalso({("POST", f"/p/{PERFIL}/api/sessions"): _json(201, corpo)})
    async with _cliente(falso) as cliente:
        with pytest.raises(RespostaInvalida):
            await cliente.criar_sessao("x")


async def test_listar_sessoes_filtra_a_fonte() -> None:
    falso = HermesFalso({("GET", f"/p/{PERFIL}/api/sessions"): _autenticado(SESSOES)})
    async with _cliente(falso) as cliente:
        assert [s["id"] for s in await cliente.listar_sessoes(limite=5)] == ["s1"]
        await cliente.listar_sessoes(fonte=None)
    assert dict(falso.pedidos[0].url.params) == {"limit": "5", "source": "api_server"}
    assert dict(falso.pedidos[1].url.params) == {"limit": "50"}


async def test_listar_sessoes_sem_lista() -> None:
    falso = HermesFalso({("GET", f"/p/{PERFIL}/api/sessions"): _json(200, {"data": "x"})})
    async with _cliente(falso) as cliente:
        with pytest.raises(RespostaInvalida, match="data"):
            await cliente.listar_sessoes()


async def test_mensagens_adota_o_id_resolvido() -> None:
    """Depois de uma compressão o Hermes responde com o id da sessão filha."""
    rota = f"/p/{PERFIL}/api/sessions/s%201/messages"
    falso = HermesFalso(
        {
            ("GET", rota): _json(
                200, {"session_id": "s2", "data": [{"role": "user", "content": "Oi"}]}
            )
        }
    )
    async with _cliente(falso) as cliente:
        historico = await cliente.mensagens("s 1")
    assert historico.sessao_id == "s2"
    assert historico.mensagens == [{"role": "user", "content": "Oi"}]
    assert dict(falso.pedidos[0].url.params) == {"order": "oldest", "limit": "500"}


async def test_mensagens_sem_id_resolvido_mantem_o_pedido() -> None:
    falso = HermesFalso(
        {("GET", f"/p/{PERFIL}/api/sessions/s1/messages"): _json(200, {"data": []})}
    )
    async with _cliente(falso) as cliente:
        assert (await cliente.mensagens("s1")).sessao_id == "s1"


async def test_mensagens_sem_lista() -> None:
    falso = HermesFalso({("GET", f"/p/{PERFIL}/api/sessions/s1/messages"): _json(200, {})})
    async with _cliente(falso) as cliente:
        with pytest.raises(RespostaInvalida):
            await cliente.mensagens("s1")


async def test_id_vazio_nao_vira_rota() -> None:
    async with _cliente(HermesFalso()) as cliente:
        with pytest.raises(ValueError, match="sessao_id"):
            await cliente.mensagens("  ")
        with pytest.raises(ValueError, match="run_id"):
            await cliente.parar("")


async def test_iniciar_run_com_idempotencia() -> None:
    falso = HermesFalso(
        {("POST", f"/p/{PERFIL}/v1/runs"): _json(202, {"run_id": "run_9", "status": "started"})}
    )
    async with _cliente(falso) as cliente:
        aceito = await cliente.iniciar_run(
            "execucao=1",
            sessao_id="s1",
            instrucoes="Descubra receitas.",
            opcoes_do_modelo={"reasoning_effort": "low"},
            chave_de_idempotencia="descoberta-1",
        )
    assert aceito == hc.RunAceito(run_id="run_9", status="started", repetido=False)
    pedido = falso.pedidos[0]
    assert pedido.headers["Idempotency-Key"] == "descoberta-1"
    assert json.loads(pedido.content) == {
        "input": "execucao=1",
        "session_id": "s1",
        "instructions": "Descubra receitas.",
        "model_options": {"reasoning_effort": "low"},
    }


async def test_iniciar_run_repetido() -> None:
    corpo = {"run_id": "run_9", "status": "started", "replayed": False}
    falso = HermesFalso(
        {("POST", f"/p/{PERFIL}/v1/runs"): _json(202, corpo, **{"Idempotency-Replayed": "true"})}
    )
    async with _cliente(falso) as cliente:
        aceito = await cliente.iniciar_run("x")
    assert aceito.repetido
    assert "Idempotency-Key" not in falso.pedidos[0].headers


async def test_iniciar_run_valida_entrada_e_resposta() -> None:
    falso = HermesFalso(
        {
            ("POST", f"/p/{PERFIL}/v1/runs"): lambda _r: httpx.Response(202, text="não json"),
        }
    )
    async with _cliente(falso) as cliente:
        with pytest.raises(ValueError, match="entrada"):
            await cliente.iniciar_run(" ")
        with pytest.raises(RespostaInvalida, match="JSON"):
            await cliente.iniciar_run("x")
        falso.rotas[("POST", f"/p/{PERFIL}/v1/runs")] = _json(202, {"status": "started"})
        with pytest.raises(RespostaInvalida, match="run_id"):
            await cliente.iniciar_run("x")


async def test_estado_e_parar_run() -> None:
    falso = HermesFalso(
        {
            ("GET", f"/p/{PERFIL}/v1/runs/run_1"): _json(
                200, {"status": "completed", "output": "Oi"}
            ),
            ("POST", f"/p/{PERFIL}/v1/runs/run_1/stop"): _json(
                200, {"run_id": "run_1", "status": "stopping"}
            ),
        }
    )
    async with _cliente(falso) as cliente:
        assert (await cliente.estado_run("run_1"))["output"] == "Oi"
        assert (await cliente.parar("run_1"))["status"] == "stopping"


# --------------------------------------------------------------------------- #
# Erros                                                                        #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("status", "corpo", "tipo", "trecho"),
    [
        (
            401,
            {"error": {"message": "Invalid gateway API key", "code": "gateway_auth_failed"}},
            ChaveRecusada,
            "recusou a chave",
        ),
        (403, {"error": "proibido"}, ChaveRecusada, "HTTP 403"),
        (
            404,
            {"error": "Unknown or unconfigured profile"},
            NaoEncontrado,
            "não conhece este perfil",
        ),
        (
            404,
            {"error": {"message": "Session not found: s9", "code": "session_not_found"}},
            NaoEncontrado,
            "Session not found",
        ),
        (
            409,
            {"error": {"message": "Run is not active", "code": "run_not_active"}},
            Conflito,
            "Run is not active",
        ),
        (500, {"error": {"message": "boom"}}, FalhaNoHermes, "HTTP 500"),
        (503, "fora", FalhaNoHermes, "fora"),
        (400, ["lista"], PedidoRecusado, "lista"),
    ],
)
async def test_status_vira_erro_com_nome(
    status: int, corpo: Any, tipo: type[Exception], trecho: str
) -> None:
    rota: Rota = (
        (lambda _r: httpx.Response(status, text=corpo))
        if isinstance(corpo, str)
        else _json(status, corpo)
    )
    falso = HermesFalso({("GET", f"/p/{PERFIL}/v1/runs/r1"): rota})
    async with _cliente(falso) as cliente:
        with pytest.raises(tipo) as erro:
            await cliente.estado_run("r1")
    assert trecho in str(erro.value)
    assert erro.value.status == status  # type: ignore[attr-defined]


async def test_limite_de_turnos_traz_a_espera() -> None:
    corpo = {
        "error": {"message": "Too many concurrent runs (max 10)", "code": "rate_limit_exceeded"}
    }
    falso = HermesFalso(
        {("POST", f"/p/{PERFIL}/v1/runs"): _json(429, corpo, **{"Retry-After": "1"})}
    )
    async with _cliente(falso) as cliente:
        with pytest.raises(AgenteOcupada) as erro:
            await cliente.iniciar_run("x")
    assert erro.value.espera_s == 1.0
    assert erro.value.codigo == "rate_limit_exceeded"
    assert erro.value.categoria == "consultora"


@pytest.mark.parametrize(("cabecalho", "esperado"), [({}, None), ({"Retry-After": "logo"}, None)])
async def test_espera_ausente_ou_ilegivel(
    cabecalho: dict[str, str], esperado: float | None
) -> None:
    falso = HermesFalso({("GET", f"/p/{PERFIL}/v1/runs/r1"): _json(429, {}, **cabecalho)})
    async with _cliente(falso) as cliente:
        with pytest.raises(AgenteOcupada) as erro:
            await cliente.estado_run("r1")
    assert erro.value.espera_s == esperado


async def test_resposta_que_nao_e_json() -> None:
    falso = HermesFalso({("GET", "/health"): lambda _r: httpx.Response(200, text="<html>")})
    async with _cliente(falso) as cliente:
        with pytest.raises(RespostaInvalida, match="JSON"):
            await cliente.versao()


async def test_resposta_que_nao_e_objeto() -> None:
    falso = HermesFalso({("GET", "/health"): _json(200, ["ok"])})
    async with _cliente(falso) as cliente:
        with pytest.raises(RespostaInvalida, match="objeto"):
            await cliente.versao()


def _quebra(erro: Exception) -> Rota:
    def rota(_request: httpx.Request) -> httpx.Response:
        raise erro

    return rota


async def test_porta_fechada_e_fora_do_ar() -> None:
    falso = HermesFalso({("GET", "/health"): _quebra(httpx.ConnectError("Connection refused"))})
    async with _cliente(falso) as cliente:
        with pytest.raises(HermesForaDoAr) as erro:
            await cliente.versao()
    assert erro.value.categoria == "rede"
    assert "make agente-status" in str(erro.value)


async def test_sem_resposta_e_tempo_esgotado() -> None:
    falso = HermesFalso({("GET", "/health"): _quebra(httpx.ReadTimeout("devagar"))})
    async with _cliente(falso) as cliente:
        with pytest.raises(TempoEsgotado) as erro:
            await cliente.versao()
    assert erro.value.categoria == "tempo"


# --------------------------------------------------------------------------- #
# SSE                                                                          #
# --------------------------------------------------------------------------- #


def test_leitor_turno_inteiro() -> None:
    leitor = LeitorSSE()
    eventos = _ler(leitor, [TURNO])
    assert [e.nome for e in eventos] == NOMES_DO_TURNO
    assert eventos[1].dados["delta"] == "A porção sai R$ 2,47 de ingrediente"
    assert leitor.comentarios == 2


def test_leitor_partido_em_qualquer_byte() -> None:
    """Todo ponto de corte possível, inclusive no meio do "ç" e do "R$ 2,47"."""
    esperado = _ler(LeitorSSE(), [TURNO])
    for corte in range(len(TURNO) + 1):
        assert _ler(LeitorSSE(), [TURNO[:corte], TURNO[corte:]]) == esperado, corte


def test_leitor_byte_a_byte_e_em_pedacos_aleatorios() -> None:
    esperado = _ler(LeitorSSE(), [TURNO])
    assert _ler(LeitorSSE(), [TURNO[i : i + 1] for i in range(len(TURNO))]) == esperado
    sorteio = random.Random(20260925)
    for _ in range(50):
        cortes = sorted(sorteio.sample(range(1, len(TURNO)), 12))
        pedacos = [TURNO[a:b] for a, b in zip([0, *cortes], [*cortes, len(TURNO)], strict=True)]
        assert _ler(LeitorSSE(), pedacos) == esperado


@pytest.mark.parametrize("quebra", [b"\r\n", b"\r"])
def test_leitor_aceita_crlf_e_cr(quebra: bytes) -> None:
    convertido = TURNO.replace(b"\n", quebra)
    esperado = [e.nome for e in _ler(LeitorSSE(), [TURNO])]
    for corte in range(len(convertido) + 1):
        eventos = _ler(LeitorSSE(), [convertido[:corte], convertido[corte:]])
        assert [e.nome for e in eventos] == esperado, corte


def test_leitor_dados_em_varias_linhas() -> None:
    eventos = _ler(
        LeitorSSE(), [b'event: x\ndata: {"a":\ndata: 1}\n\ndata: linha 1\ndata: linha 2\n\n']
    )
    assert eventos == [EventoSSE("x", {"a": 1}), EventoSSE("message", "linha 1\nlinha 2")]


def test_leitor_nome_dentro_do_json_como_no_v1_runs() -> None:
    corpo = (
        b'data: {"event": "message.delta", "run_id": "r1", "delta": "Oi"}\n\n'
        b": keepalive\n\n"
        b'data: {"event": "run.completed", "output": "Oi"}\n\n'
        b'data: {"event": 7}\n\n'
        b": stream closed\n\n"
    )
    leitor = LeitorSSE()
    assert [e.nome for e in _ler(leitor, [corpo])] == ["message.delta", "run.completed", "message"]
    assert leitor.comentarios == 2


def test_leitor_campos_da_especificacao() -> None:
    corpo = (
        "﻿id: 7\nretry: 1500\nretry: logo\ndata:sem espaço\n\n"
        "id: com\x00nulo\ndata:  dois espaços\n\n"
        "evento-sem-dois-pontos\nevent: vazio\n\n"
        "data\n\n"
        "desconhecido: x\ndata: ok\n\n"
    ).encode()
    leitor = LeitorSSE()
    eventos = _ler(leitor, [corpo])
    assert eventos == [
        EventoSSE("message", "sem espaço", "7"),
        EventoSSE("message", " dois espaços", "7"),
        EventoSSE("message", "", "7"),
        EventoSSE("message", "ok", "7"),
    ]
    assert leitor.retry_ms == 1500


def test_leitor_descarta_evento_sem_linha_final() -> None:
    assert _ler(LeitorSSE(), [b"event: x\ndata: {}\n\nevent: y\ndata: {"]) == [EventoSSE("x", {})]


def test_leitor_sem_nada() -> None:
    leitor = LeitorSSE()
    assert leitor.alimentar(b"") == []
    assert leitor.terminar() == []


async def _eventos(fluxo: AsyncIterator[EventoSSE]) -> list[EventoSSE]:
    return [evento async for evento in fluxo]


async def test_stream_chat_em_pedacos_tortos() -> None:
    corte = TURNO.index("ç".encode()) + 1  # no meio do "ç"
    pedacos = [TURNO[:5], TURNO[5:corte], TURNO[corte : corte + 3], TURNO[corte + 3 :]]
    rota = f"/p/{PERFIL}/api/sessions/s1/chat/stream"
    falso = HermesFalso({("POST", rota): _sse(pedacos)})
    async with _cliente(falso) as cliente:
        eventos = await _eventos(
            cliente.stream_chat(
                "s1",
                "Consigo fazer pão?",
                instrucao_de_sistema="Escreva curto.",
                opcoes_do_modelo={"reasoning_effort": "medium"},
            )
        )
    assert [e.nome for e in eventos] == NOMES_DO_TURNO
    assert eventos[-2].dados["session_id"] == "s2"
    pedido = falso.pedidos[0]
    assert json.loads(pedido.content) == {
        "message": "Consigo fazer pão?",
        "system_message": "Escreva curto.",
        "model_options": {"reasoning_effort": "medium"},
    }
    assert pedido.headers["Accept"] == "text/event-stream"
    assert pedido.headers["Authorization"] == f"Bearer {CHAVE}"


async def test_stream_que_termina_num_cr_solto_entrega_o_ultimo_evento() -> None:
    """Com fim de linha só `\\r`, o último `\\r` pode ser metade de um `\\r\\n`: o leitor
    espera o próximo pedaço, que nunca vem, e só no fim do stream despacha."""
    rota = f"/p/{PERFIL}/api/sessions/s1/chat/stream"
    falso = HermesFalso({("POST", rota): _sse([b"event: done\rdata: {}\r\r"])})
    async with _cliente(falso) as cliente:
        eventos = await _eventos(cliente.stream_chat("s1", "Oi"))
    assert eventos == [EventoSSE("done", {})]


async def test_stream_chat_evento_de_erro_chega_como_evento() -> None:
    corpo = _frame("run.started", {}) + _frame("error", {"message": "falhou"}) + _frame("done", {})
    rota = f"/p/{PERFIL}/api/sessions/s1/chat/stream"
    falso = HermesFalso({("POST", rota): _sse([corpo])})
    async with _cliente(falso) as cliente:
        eventos = await _eventos(cliente.stream_chat("s1", "Oi"))
    assert [(e.nome, e.dados) for e in eventos][1:] == [
        ("error", {"message": "falhou"}),
        ("done", {}),
    ]
    assert json.loads(falso.pedidos[0].content) == {"message": "Oi"}


async def test_stream_chat_mensagem_vazia() -> None:
    async with _cliente(HermesFalso()) as cliente:
        with pytest.raises(ValueError, match="mensagem"):
            cliente.stream_chat("s1", "   ")


async def test_stream_recusado_antes_de_comecar() -> None:
    corpo = {"error": {"message": "Too many concurrent runs (max 10)"}}
    rota = f"/p/{PERFIL}/api/sessions/s1/chat/stream"
    falso = HermesFalso({("POST", rota): _json(429, corpo)})
    async with _cliente(falso) as cliente:
        with pytest.raises(AgenteOcupada):
            await _eventos(cliente.stream_chat("s1", "Oi"))


@pytest.mark.parametrize("tipo", ["application/json", ""])
async def test_stream_que_nao_e_sse(tipo: str) -> None:
    rota = f"/p/{PERFIL}/api/sessions/s1/chat/stream"
    falso = HermesFalso({("POST", rota): _sse([b"{}"], tipo=tipo)})
    async with _cliente(falso) as cliente:
        with pytest.raises(RespostaInvalida, match="não SSE"):
            await _eventos(cliente.stream_chat("s1", "Oi"))


async def test_conexao_que_cai_no_meio_entrega_o_que_chegou() -> None:
    rota = f"/p/{PERFIL}/api/sessions/s1/chat/stream"
    parte = _frame("run.started", {"run_id": "r1"})
    falso = HermesFalso({("POST", rota): _sse([parte], erro=httpx.ReadError("caiu"))})
    recebidos: list[str] = []
    async with _cliente(falso) as cliente:
        with pytest.raises(ConexaoInterrompida) as erro:
            async for evento in cliente.stream_chat("s1", "Oi"):
                recebidos.append(evento.nome)
    assert recebidos == ["run.started"]
    assert erro.value.categoria == "rede"


async def test_stream_mudo_por_tempo_demais() -> None:
    rota = f"/p/{PERFIL}/v1/runs/r1/events"
    falso = HermesFalso({("GET", rota): _sse([b": keepalive\n\n"], erro=httpx.ReadTimeout("mudo"))})
    async with _cliente(falso) as cliente:
        with pytest.raises(TempoEsgotado):
            await _eventos(cliente.eventos_run("r1"))


async def test_stream_com_porta_fechada() -> None:
    rota = f"/p/{PERFIL}/v1/runs/r1/events"
    falso = HermesFalso({("GET", rota): _quebra(httpx.ConnectError("recusada"))})
    async with _cliente(falso) as cliente:
        with pytest.raises(HermesForaDoAr):
            await _eventos(cliente.eventos_run("r1"))


async def test_eventos_run() -> None:
    corpo = (
        b'data: {"event": "tool.started", "run_id": "r1", "tool": "web_search"}\n\n'
        b": keepalive\n\n"
        b'data: {"event": "run.completed", "run_id": "r1", "output": "pronto"}\n\n'
        b": stream closed\n\n"
    )
    falso = HermesFalso({("GET", f"/p/{PERFIL}/v1/runs/r1/events"): _sse([corpo])})
    async with _cliente(falso) as cliente:
        eventos = await _eventos(cliente.eventos_run("r1"))
    assert [e.nome for e in eventos] == ["tool.started", "run.completed"]


# --------------------------------------------------------------------------- #
# A chave nunca vaza                                                           #
# --------------------------------------------------------------------------- #


async def test_a_chave_nunca_aparece_em_log_excecao_ou_repr(caplog) -> None:
    caplog.set_level(logging.DEBUG)
    turno = f"/p/{PERFIL}/api/sessions/s1/chat/stream"
    falso = HermesFalso(
        {
            ("GET", "/health"): _json(200, SAUDAVEL),
            ("GET", f"/p/{PERFIL}/api/sessions"): _autenticado(SESSOES),
            ("GET", f"/p/{PERFIL}/v1/runs/r401"): _json(401, {"error": {"message": "Invalid key"}}),
            ("GET", f"/p/{PERFIL}/v1/runs/r500"): _json(500, {"error": {"message": "boom"}}),
            ("GET", f"/p/{PERFIL}/v1/runs/rcai"): _quebra(httpx.ConnectError("recusada")),
            ("POST", turno): _sse([TURNO[:40]], erro=httpx.ReadError("caiu")),
        }
    )
    textos: list[str] = []
    async with _cliente(falso) as cliente:
        textos.append(repr(cliente))
        textos.append(repr(hc._Portador(ChaveSecreta(CHAVE))))
        await cliente.saude()
        for run_id in ("r401", "r500", "rcai"):
            with pytest.raises(hc.ErroDoHermes) as erro:
                await cliente.estado_run(run_id)
            textos += [
                str(erro.value),
                repr(erro.value),
                "".join(traceback.format_exception(erro.value)),
            ]
        with pytest.raises(ConexaoInterrompida) as erro_stream:
            await _eventos(cliente.stream_chat("s1", "Oi"))
        textos += [str(erro_stream.value), "".join(traceback.format_exception(erro_stream.value))]
    assert falso.pedidos[1].headers["Authorization"] == f"Bearer {CHAVE}", "a chave foi enviada"
    assert "HTTP Request" in caplog.text or "Hermes GET" in caplog.text, "houve log para conferir"
    for texto in [*textos, caplog.text]:
        assert CHAVE not in texto
