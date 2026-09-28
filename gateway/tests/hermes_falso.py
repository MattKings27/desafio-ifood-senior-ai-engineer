"""Um servidor de API do Hermes falso, para os testes do chat.

Fala o mesmo protocolo do Hermes 0.21.4 que `contratos/hermes/chat-stream-amostra.jsonl`
gravou: cada evento do `chat/stream` sai como `event: <nome>` e `data: {JSON}` com
`session_id`, `run_id` e `seq`, e o corpo chega partido em pedaços de tamanho
aleatório, no meio de uma linha ou de um caractere acentuado.

Um roteiro por turno (`HermesFalso.roteiros`), na ordem em que os turnos chegam.
O roteiro pode esperar um `asyncio.Event` (`Esperar`), para o teste segurar o
turno no meio, e quebrar a conexão (`Quebrar`). Um `POST /v1/runs/{id}/stop`
faz o stream parado responder `run.cancelled`, como o Hermes faz.

Os runs de segundo plano (`POST /v1/runs`, a descoberta de receitas) têm os
roteiros deles (`HermesFalso.runs`): os eventos saem de `GET /v1/runs/{id}/events`
só com `data:`, o nome dentro do JSON (`event`), como o Hermes 0.21 publica; o
estado sai de `GET /v1/runs/{id}` e a transcrição da sessão, de
`GET /api/sessions/{id}/messages`. `Fazer` roda uma ação no meio do run: é por
ali que o teste faz o servidor MCP gravar no catálogo, na hora em que a
ferramenta roda. `ocupada_por` faz os próximos `POST /v1/runs` darem 429.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from collections import deque
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from gateway.hermes_cliente import ChaveSecreta, ClienteHermes

PERFIL = "sabor-da-maria-avaliacao"
CHAVE = ChaveSecreta("chave-de-teste-" + "x" * 20)


@dataclass(frozen=True)
class Evento:
    nome: str
    dados: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Esperar:
    """Segura o stream até o teste liberar (ou até alguém pedir para parar)."""

    sinal: asyncio.Event


@dataclass(frozen=True)
class Quebrar:
    """A conexão cai aqui."""


@dataclass(frozen=True)
class Fazer:
    """Roda uma ação no meio do run (o servidor MCP gravando no catálogo, por exemplo)."""

    acao: Callable[[], None]


Passo = Evento | Esperar | Quebrar
PassoDoRun = Evento | Esperar | Quebrar | Fazer


@dataclass
class RoteiroDeRun:
    """Um run de segundo plano: os eventos, a transcrição da sessão e o fim."""

    passos: list[PassoDoRun]
    run_id: str = "run_descoberta_1"
    #: O que `GET /api/sessions/{id}/messages` devolve para a sessão do run.
    mensagens: list[dict[str, Any]] = field(default_factory=list)
    #: O status que `GET /v1/runs/{id}` passa a dar se a conexão cair no meio.
    status_se_cair: str = "completed"


@dataclass
class Roteiro:
    passos: list[Passo]
    run_id: str = "run_falso_1"
    #: Se o Hermes deve ignorar o pedido de parar (para testar a desistência do backend).
    ignora_parada: bool = False


def _frame(nome: str, dados: dict[str, Any]) -> bytes:
    return f"event: {nome}\ndata: {json.dumps(dados, ensure_ascii=False)}\n\n".encode()


class _Corpo(httpx.AsyncByteStream):
    def __init__(self, hermes: HermesFalso, roteiro: Roteiro, sessao_id: str) -> None:
        self._hermes = hermes
        self._roteiro = roteiro
        self._sessao_id = sessao_id
        self._seq = 0
        self._aleatorio = random.Random(hermes.semente)

    def _com_cabecalho(self, evento: Evento) -> bytes:
        self._seq += 1
        dados = {
            "session_id": self._sessao_id,
            "run_id": self._roteiro.run_id,
            "seq": self._seq,
            "ts": 1790332228.0 + self._seq,
            **evento.dados,
        }
        return _frame(evento.nome, dados)

    def _em_pedacos(self, bruto: bytes) -> list[bytes]:
        pedacos, inicio = [], 0
        while inicio < len(bruto):
            fim = inicio + self._aleatorio.randint(1, 23)
            pedacos.append(bruto[inicio:fim])
            inicio = fim
        return pedacos

    def _cancelado(self) -> list[bytes]:
        return [
            self._com_cabecalho(
                Evento("assistant.completed", {"content": "", "interrupted": True})
            ),
            self._com_cabecalho(
                Evento("run.cancelled", {"messages": [], "usage": {}, "interrupted": True})
            ),
            self._com_cabecalho(Evento("done")),
        ]

    async def __aiter__(self) -> AsyncIterator[bytes]:
        parada = self._hermes.parada_de(self._roteiro.run_id)
        for passo in self._roteiro.passos:
            if parada.is_set() and not self._roteiro.ignora_parada:
                for bruto in self._cancelado():
                    yield bruto
                return
            if isinstance(passo, Esperar):
                esperas = {asyncio.ensure_future(passo.sinal.wait())}
                if not self._roteiro.ignora_parada:
                    esperas.add(asyncio.ensure_future(parada.wait()))
                _, pendentes = await asyncio.wait(esperas, return_when=asyncio.FIRST_COMPLETED)
                for pendente in pendentes:
                    pendente.cancel()
                continue
            if isinstance(passo, Quebrar):
                raise httpx.ReadError("a conexão caiu")
            for pedaco in self._em_pedacos(self._com_cabecalho(passo)):
                yield pedaco
                await asyncio.sleep(0)

    async def aclose(self) -> None:
        self._hermes.fechados += 1


class _CorpoDoRun(httpx.AsyncByteStream):
    """Os eventos de um run: `data: {JSON}` com `event`, `run_id` e `timestamp`, sem `event:`."""

    def __init__(self, hermes: HermesFalso, roteiro: RoteiroDeRun) -> None:
        self._hermes = hermes
        self._roteiro = roteiro
        self._aleatorio = random.Random(hermes.semente)

    def _quadro(self, evento: Evento) -> bytes:
        # Um valor que é função só se resolve na hora de sair: o resumo do fim de uma
        # ferramenta depende do que ela fez (`Fazer`) logo antes.
        resolvidos = {k: v() if callable(v) else v for k, v in evento.dados.items()}
        dados = {
            "event": evento.nome,
            "run_id": self._roteiro.run_id,
            "timestamp": 1790332228.0,
            **resolvidos,
        }
        return f"data: {json.dumps(dados, ensure_ascii=False)}\n\n".encode()

    def _em_pedacos(self, bruto: bytes) -> list[bytes]:
        pedacos, inicio = [], 0
        while inicio < len(bruto):
            fim = inicio + self._aleatorio.randint(1, 23)
            pedacos.append(bruto[inicio:fim])
            inicio = fim
        return pedacos

    async def __aiter__(self) -> AsyncIterator[bytes]:
        run_id = self._roteiro.run_id
        parada = self._hermes.parada_de(run_id)
        for passo in self._roteiro.passos:
            if parada.is_set():
                self._hermes.status_dos_runs[run_id] = "cancelled"
                yield self._quadro(Evento("run.cancelled", {"interrupted": True}))
                yield b": stream closed\n\n"
                return
            if isinstance(passo, Esperar):
                esperas = {
                    asyncio.ensure_future(passo.sinal.wait()),
                    asyncio.ensure_future(parada.wait()),
                }
                _, pendentes = await asyncio.wait(esperas, return_when=asyncio.FIRST_COMPLETED)
                for pendente in pendentes:
                    pendente.cancel()
                continue
            if isinstance(passo, Fazer):
                passo.acao()
                continue
            if isinstance(passo, Quebrar):
                self._hermes.status_dos_runs[run_id] = self._roteiro.status_se_cair
                raise httpx.ReadError("a conexão caiu")
            if passo.nome.startswith("run."):
                self._hermes.status_dos_runs[run_id] = passo.nome.removeprefix("run.")
            for pedaco in self._em_pedacos(self._quadro(passo)):
                yield pedaco
                await asyncio.sleep(0)
        yield b": stream closed\n\n"


class HermesFalso:
    """Responde como o servidor de API do Hermes e guarda o que recebeu."""

    def __init__(self, semente: int = 7) -> None:
        self.semente = semente
        self.roteiros: deque[Roteiro] = deque()
        self.pedidos: list[httpx.Request] = []
        self.turnos: list[dict[str, Any]] = []
        self.sessoes_criadas: list[str] = []
        self.sessoes_sumidas: set[str] = set()
        self.paradas: list[str] = []
        self.fora_do_ar = False
        self.fechados = 0
        self._paradas: dict[str, asyncio.Event] = {}
        self.runs: deque[RoteiroDeRun] = deque()
        self.runs_pedidos: list[dict[str, Any]] = []
        self.status_dos_runs: dict[str, str] = {}
        self.mensagens_das_sessoes: dict[str, list[dict[str, Any]]] = {}
        #: Quantos `POST /v1/runs` ainda respondem 429 antes de aceitar.
        self.ocupada_por = 0
        #: Sessão nova com título é recusada (título repetido, como o Hermes faz).
        self.recusa_titulo = False
        #: O pedido de parar um run é recusado (409, run que não está mais ativo).
        self.recusa_parar = False
        self._runs_ativos: dict[str, RoteiroDeRun] = {}

    def parada_de(self, run_id: str) -> asyncio.Event:
        return self._paradas.setdefault(run_id, asyncio.Event())

    def cliente(self) -> ClienteHermes:
        return ClienteHermes(
            perfil=PERFIL,
            chave=CHAVE,
            origem_da_chave="teste",
            transporte=httpx.MockTransport(self),
            silencio_maximo_s=5.0,
        )

    async def __call__(self, request: httpx.Request) -> httpx.Response:  # noqa: PLR0911
        self.pedidos.append(request)
        if self.fora_do_ar:
            raise httpx.ConnectError("nada escutando", request=request)
        caminho = request.url.path
        prefixo = f"/p/{PERFIL}"
        if caminho == "/health":
            return httpx.Response(200, json={"status": "ok", "version": "0.21.4"})
        if not caminho.startswith(prefixo):
            return httpx.Response(404, json={"error": {"message": "Unknown profile"}})
        caminho = caminho.removeprefix(prefixo)
        if request.method == "GET" and caminho == "/api/sessions":
            return httpx.Response(200, json={"object": "list", "data": [], "has_more": False})
        if request.method == "POST" and caminho == "/api/sessions":
            corpo = json.loads(request.content or b"{}")
            if self.recusa_titulo and "title" in corpo:
                return httpx.Response(400, json={"error": {"message": "Title already in use"}})
            sessao_id = f"api_falsa_{len(self.sessoes_criadas) + 1}"
            self.sessoes_criadas.append(sessao_id)
            return httpx.Response(200, json={"session": {"id": sessao_id, **corpo}})
        if achado := re.fullmatch(r"/api/sessions/([^/]+)/chat/stream", caminho):
            return self._chat(request, achado.group(1))
        if achado := re.fullmatch(r"/v1/runs/([^/]+)/stop", caminho):
            run_id = achado.group(1)
            if self.recusa_parar:
                return httpx.Response(409, json={"error": {"message": "Run is not active"}})
            self.paradas.append(run_id)
            self.parada_de(run_id).set()
            return httpx.Response(200, json={"run_id": run_id, "status": "stopping"})
        return self._run(request, caminho)

    def _run(self, request: httpx.Request, caminho: str) -> httpx.Response:  # noqa: PLR0911
        if request.method == "POST" and caminho == "/v1/runs":
            if self.ocupada_por > 0:
                self.ocupada_por -= 1
                return httpx.Response(
                    429,
                    headers={"Retry-After": "0"},
                    json={"error": {"message": "Too many concurrent runs (max 1)"}},
                )
            corpo = json.loads(request.content or b"{}")
            chave = request.headers.get("Idempotency-Key")
            self.runs_pedidos.append({**corpo, "idempotency_key": chave})
            roteiro = self.runs.popleft()
            self._runs_ativos[roteiro.run_id] = roteiro
            self.status_dos_runs[roteiro.run_id] = "running"
            sessao = corpo.get("session_id")
            if isinstance(sessao, str):
                self.mensagens_das_sessoes[sessao] = roteiro.mensagens
            return httpx.Response(
                202, json={"run_id": roteiro.run_id, "status": "started", "replayed": False}
            )
        if achado := re.fullmatch(r"/v1/runs/([^/]+)/events", caminho):
            roteiro = self._runs_ativos.get(achado.group(1))
            if roteiro is None:
                return httpx.Response(404, json={"error": {"message": "Run not found"}})
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=_CorpoDoRun(self, roteiro),
            )
        if achado := re.fullmatch(r"/v1/runs/([^/]+)", caminho):
            run_id = achado.group(1)
            if run_id not in self.status_dos_runs:
                return httpx.Response(404, json={"error": {"message": "Run not found"}})
            return httpx.Response(
                200, json={"run_id": run_id, "status": self.status_dos_runs[run_id]}
            )
        if achado := re.fullmatch(r"/api/sessions/([^/]+)/messages", caminho):
            sessao_id = achado.group(1)
            if sessao_id not in self.mensagens_das_sessoes:
                return httpx.Response(404, json={"error": {"message": "Session not found"}})
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": self.mensagens_das_sessoes[sessao_id],
                    "session_id": sessao_id,
                },
            )
        return httpx.Response(404, json={"error": {"message": f"sem rota {caminho}"}})

    def _chat(self, request: httpx.Request, sessao_id: str) -> httpx.Response:
        if sessao_id in self.sessoes_sumidas:
            return httpx.Response(404, json={"error": {"message": "Session not found"}})
        self.turnos.append({"sessao_id": sessao_id, **json.loads(request.content)})
        roteiro = self.roteiros.popleft()
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_Corpo(self, roteiro, sessao_id),
        )


# --------------------------------------------------------------------------- #
# Roteiros prontos                                                             #
# --------------------------------------------------------------------------- #

#: A saída do motor que sustenta os valores do turno de exemplo.
SAIDA_DO_DIAGNOSTICO = json.dumps(
    {
        "itens": 37,
        "total_investido": {"valor": 663.39, "texto": "R$ 663,39"},
        "maiores_investimentos": [
            {"ingrediente": "Alcaparras", "pago": {"texto": "R$ 82,00"}},
            {"ingrediente": "Cobertura de chocolate", "pago": {"texto": "R$ 79,90"}},
        ],
        "dois_maiores": {"texto": "R$ 161,90"},
    },
    ensure_ascii=False,
)

#: Como o Hermes embrulha a saída de ferramenta MCP.
EMBRULHO = "<untrusted_tool_output>\n{}\n</untrusted_tool_output>"


def mensagens_do_turno(
    *saidas: tuple[str, str], final: str = "", chamadas: int = 2
) -> list[dict[str, Any]]:
    """O `run.completed.messages`: as mensagens do agente e as saídas das ferramentas."""
    mensagens: list[dict[str, Any]] = []
    for i, (ferramenta, saida) in enumerate(saidas):
        mensagens.append(
            {"role": "assistant", "content": "", "tool_calls": [{"id": f"c{i}", "function": {}}]}
        )
        mensagens.append(
            {
                "role": "tool",
                "tool_name": ferramenta,
                "name": ferramenta,
                "tool_call_id": f"c{i}",
                "content": EMBRULHO.format(saida),
            }
        )
    for _ in range(max(0, chamadas - len(saidas))):
        mensagens.append({"role": "assistant", "content": final})
    return mensagens


def turno(
    rascunho: list[str],
    *,
    final: str | None = None,
    antes: list[Passo] | None = None,
    depois: list[Passo] | None = None,
    mensagens: list[dict[str, Any]] | None = None,
    fim: str = "run.completed",
    sessao_final: str | None = None,
    uso: dict[str, int] | None = None,
    run_id: str = "run_falso_1",
) -> Roteiro:
    """Um turno inteiro: início, o que vem antes do texto, o rascunho, o fim."""
    texto = "".join(rascunho) if final is None else final
    completo: dict[str, Any] = {"content": texto, "completed": fim == "run.completed"}
    terminal: dict[str, Any] = {
        "messages": mensagens if mensagens is not None else [],
        "usage": uso or {"input_tokens": 20_000, "output_tokens": 300, "total_tokens": 20_300},
        "completed": fim == "run.completed",
    }
    if sessao_final is not None:
        completo["session_id"] = sessao_final
        terminal["session_id"] = sessao_final
    passos: list[Passo] = [
        Evento("run.started", {"user_message": {"role": "user", "content": "?"}}),
        Evento("message.started", {"message": {"id": "msg_1", "role": "assistant"}}),
        *(antes or []),
        *(Evento("assistant.delta", {"message_id": "msg_1", "delta": p}) for p in rascunho),
        *(depois or []),
        Evento("tool.progress", {"tool_name": "_thinking", "delta": "custa R$ 7,50 de cabeça"}),
        Evento("assistant.completed", completo),
        Evento(fim, terminal),
        Evento("done"),
    ]
    return Roteiro(passos, run_id=run_id)


def chamada(ferramenta: str, args: dict[str, Any] | None = None, *, ok: bool = True) -> list[Passo]:
    """Uma chamada de ferramenta: `tool.started` com os argumentos, e o fim sem eles."""
    return [
        Evento("tool.started", {"tool_name": ferramenta, "preview": None, "args": args or {}}),
        Evento(
            "tool.completed" if ok else "tool.failed",
            {"tool_name": ferramenta, "preview": None, "args": None},
        ),
    ]
