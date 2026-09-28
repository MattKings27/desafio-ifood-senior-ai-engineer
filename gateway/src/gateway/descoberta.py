"""A descoberta de receitas: a plataforma pede, o agente procura, o servidor guarda.

A Dona Maria quer ver receitas de verdade na grade sem pedir uma por uma. Quem
procura é o agente, rodando no Hermes como serviço, em segundo plano:

1. **O pedido é fixo.** Um run novo do Hermes (`POST /v1/runs`, numa sessão
   nova só dele) com as instruções de `hermes/prompts/descoberta.md`: chamar
   `pauta_de_descoberta`, fazer até 8 pesquisas com `web_search`, trazer até 20
   páginas com `buscar_receita_na_web`, até 3 de cada pesquisa e primeiro dos
   sites de receita mais populares, não conversar com ninguém e parar. O
   esforço de raciocínio é baixo (`model_options`): é tarefa de rotina.
2. **Quem escreve no catálogo é o servidor.** Cada página entra por
   `buscar_receita_na_web`, que busca, lê a receita estruturada (JSON-LD ou
   microdata) e guarda com a fonte. O que o modelo escreve no texto não entra
   em lugar nenhum. A receita que a página trouxe entra com a origem da
   conversa; este serviço, que sabe que o pedido foi da descoberta, a marca
   como descoberta (`Catalogo.marcar_como_descoberta`), e só se ela entrou
   depois do começo desta rodada.
3. **O progresso vem do catálogo e dos eventos do run.** `tool.started` diz o
   que o agente está fazendo (pesquisando, lendo a página de um site);
   `tool.completed` da leitura traz o `receita_id` que o servidor devolveu, e é
   pelo catálogo que se confere se a receita entrou mesmo. No fim, a transcrição
   da sessão confere o que os eventos resumiram.
4. **Uma rodada por vez.** Pedir outra durante uma rodada devolve a que está
   rodando (HTTP 409, `ocupado`). Se ela está no meio de uma conversa, a rodada
   espera o turno terminar e tenta de novo; se o Hermes está no limite de
   turnos, tenta de novo daqui a pouco.
5. **Limites de verdade.** Passou de 8 pesquisas ou de 20 páginas, ou de cerca
   de 16 minutos (35 segundos por pesquisa ou página lida), o serviço pede ao
   Hermes para parar. Os limites são os da pauta (`mise.descoberta`), um número
   só para o pedido e para quem confere.
6. **Chave de desligar.** Cada rodada custa dinheiro. `SABOR_DESCOBERTA=ligada`
   liga (o `make dev` liga); sem a variável, ou com `desligada`, o pedido é
   recusado com o motivo (HTTP 501, e a tela abre a conversa com o pedido
   escrito). Os testes e o CI rodam desligados.

Os disparos são da tela: o botão "Procurar mais receitas" e a primeira visita
com o catálogo vazio chamam `POST /api/receitas/descoberta`. Ler a grade nunca
dispara nada.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlsplit

from mise.descoberta import MAXIMO_DE_BUSCAS, MAXIMO_DE_PAGINAS

from gateway.conversa import quadro_sse
from gateway.frases import nome_da_ferramenta
from gateway.hermes_cliente import (
    AgenteOcupada,
    ChaveAusente,
    ChaveRecusada,
    ClienteHermes,
    ErroDoHermes,
    PedidoRecusado,
)

if TYPE_CHECKING:
    from mise.mcp_server import Sessao

    from gateway.conversa import ServicoDeConversa
    from gateway.hermes_cliente import EventoSSE

logger = logging.getLogger(__name__)

#: A chave de desligar: `ligada` liga; sem ela, ou com `desligada`, fica desligada.
VAR_DESCOBERTA: Final = "SABOR_DESCOBERTA"
LIGADA: Final = "ligada"
DESLIGADA: Final = "desligada"
#: Outro arquivo de instruções, no lugar de `hermes/prompts/descoberta.md`.
VAR_PROMPT: Final = "SABOR_PROMPT_DESCOBERTA"
PROMPT_PADRAO: Final = Path(__file__).resolve().parents[3] / "hermes" / "prompts" / "descoberta.md"

#: A mensagem do run; as instruções vão à parte, fixas.
ENTRADA: Final = (
    "Procure agora receitas para a despensa da Dona Maria, seguindo as instruções desta tarefa."
)
#: Tarefa de rotina: raciocínio baixo, que custa menos e basta para escolher páginas.
ESFORCO: Final = "low"

#: Quanto uma pesquisa ou uma página lida leva, com folga, contando o modelo e a leitura.
SEGUNDOS_POR_PASSO: Final = 35.0
#: A rodada mais longa: um passo para cada pesquisa e cada página que a pauta permite.
#: Com 8 pesquisas e 20 páginas, 980 segundos, cerca de 16 minutos.
DURACAO_MAXIMA_S: Final = SEGUNDOS_POR_PASSO * (MAXIMO_DE_BUSCAS + MAXIMO_DE_PAGINAS)

#: O caminho do fluxo de eventos de uma rodada, na API.
ROTA_DOS_EVENTOS: Final = "/api/receitas/descoberta/eventos"

_TERMINAIS: Final = frozenset({"completed", "failed", "cancelled", "interrupted"})
_RECEITA_ID: Final = re.compile(r'receita_id\\*"\s*:\s*\\*"([0-9a-f]{16})')
_JA_CONHECIDA: Final = re.compile(r'ja_conhecida\\*"\s*:\s*(true|false)')

# --------------------------------------------------------------------------- #
# O que ela lê                                                                 #
# --------------------------------------------------------------------------- #

PROCURANDO: Final = "Procurando receitas com o que a senhora tem…"
SEPARANDO: Final = "Separando o que procurar com o que a senhora tem…"
LENDO_UMA: Final = "Lendo uma página de receita…"
ESPERANDO_A_CONVERSA: Final = (
    "Estou terminando de responder a senhora na conversa. Logo depois eu procuro as receitas."
)
ESPERANDO_A_CONSULTORA: Final = "O agente está ocupado agora. Eu tento de novo daqui a pouco."
JA_PROCURANDO: Final = "Já estou procurando receitas para a senhora. É só acompanhar por aqui."
DESLIGADA_AQUI: Final = (
    "A busca automática de receitas está desligada aqui. A senhora pode trazer uma receita "
    "pelo endereço dela, ou me pedir na conversa."
)
SEM_INSTRUCOES: Final = (
    "A busca automática de receitas não está pronta aqui. A senhora pode trazer uma receita "
    "pelo endereço dela, ou me pedir na conversa."
)
FORA_DO_AR: Final = (
    "Não consegui procurar receitas agora: o agente está fora do ar. "
    "As telas continuam funcionando normalmente."
)
CONTINUOU_OCUPADA: Final = (
    "O agente continuou ocupado e eu não consegui procurar receitas agora. "
    "A senhora pode tentar de novo daqui a pouco."
)
CONVERSA_NAO_TERMINOU: Final = (
    "A conversa continuou e eu não cheguei a procurar receitas. "
    "A senhora pode pedir de novo quando quiser."
)
DEMOROU: Final = "A busca demorou demais e eu parei."
PROBLEMA: Final = "Tive um problema para procurar receitas agora."
INTERROMPIDA: Final = "O agente foi reiniciado no meio da busca."
TENTE_DE_NOVO: Final = "A senhora pode tentar de novo daqui a pouco."


def _receitas(n: int) -> str:
    return f"{n} {'receita nova' if n == 1 else 'receitas novas'}"


def _paginas(n: int) -> str:
    return f"{n} {'página' if n == 1 else 'páginas'}"


def texto_do_fim(lidas: int, encontradas: int) -> str:
    """A frase do fim de uma rodada que terminou bem, com os números dela."""
    if encontradas:
        return f"Encontrei {_receitas(encontradas)}."
    if lidas:
        return f"Li {_paginas(lidas)}, mas nenhuma receita nova entrou desta vez."
    return "Desta vez não achei página de receita nova para ler."


def texto_do_erro(motivo: str, encontradas: int) -> str:
    """O erro na língua dela, dizendo o que já ficou na lista."""
    if encontradas:
        ficou = f"As {_receitas(encontradas)} que eu trouxe já estão na lista."
        if encontradas == 1:
            ficou = "A receita nova que eu trouxe já está na lista."
        return f"{motivo} {ficou}"
    return f"{motivo} {TENTE_DE_NOVO}"


def _erro_do_hermes(erro: ErroDoHermes) -> str:
    if erro.categoria == "rede" or isinstance(erro, ChaveAusente | ChaveRecusada):
        return FORA_DO_AR
    if isinstance(erro, AgenteOcupada):
        return CONTINUOU_OCUPADA
    if erro.categoria == "tempo":
        return DEMOROU
    return PROBLEMA


def _site(preview: object) -> str | None:
    """O site do endereço que o agente pediu para ler, sem o `www.`."""
    if not isinstance(preview, str):
        return None
    achado = re.search(r"https?://[^\s\"'<>]+", preview)
    if achado is None:
        return None
    try:
        host = urlsplit(achado.group(0)).hostname
    except ValueError:
        return None
    return host.removeprefix("www.") if host else None


def resultado_da_leitura(texto: object) -> tuple[str | None, bool | None]:
    """O `receita_id` e o `ja_conhecida` que `buscar_receita_na_web` devolveu, se aparecem.

    Lê o texto que o Hermes publica (o resumo do `tool.completed` ou a mensagem
    da ferramenta na transcrição), escapado ou não. É só uma pista: quem diz se
    a receita entrou é o catálogo.
    """
    if not isinstance(texto, str):
        return None, None
    receita = _RECEITA_ID.search(texto)
    conhecida = _JA_CONHECIDA.search(texto)
    return (
        receita.group(1) if receita else None,
        (conhecida.group(1) == "true") if conhecida else None,
    )


# --------------------------------------------------------------------------- #
# Configuração                                                                 #
# --------------------------------------------------------------------------- #


def ligada_no_ambiente(ambiente: Mapping[str, str] | None = None) -> bool:
    """`SABOR_DESCOBERTA=ligada` liga. Sem a variável, fica desligada: cada rodada custa."""
    amb = os.environ if ambiente is None else ambiente
    return amb.get(VAR_DESCOBERTA, "").strip().lower() == LIGADA


@dataclass(frozen=True, slots=True)
class Configuracao:
    ligada: bool = False
    maximo_de_buscas: int = MAXIMO_DE_BUSCAS
    maximo_de_paginas: int = MAXIMO_DE_PAGINAS
    #: A rodada mais longa: passou disso, pede para parar.
    duracao_maxima_s: float = DURACAO_MAXIMA_S
    #: Quanto esperar um turno da conversa terminar antes de desistir.
    espera_da_conversa_s: float = 300.0
    intervalo_da_espera_s: float = 2.0
    #: Quantas vezes tentar quando o Hermes está no limite de turnos, e o intervalo.
    tentativas_se_ocupada: int = 3
    espera_se_ocupada_s: float = 20.0
    #: O intervalo da consulta ao estado do run quando o fluxo de eventos cai.
    intervalo_do_estado_s: float = 3.0
    keepalive_s: float = 10.0
    prompt: Path = PROMPT_PADRAO

    @classmethod
    def do_ambiente(cls, ambiente: Mapping[str, str] | None = None) -> Configuracao:
        amb = os.environ if ambiente is None else ambiente
        prompt = amb.get(VAR_PROMPT, "").strip()
        return cls(
            ligada=ligada_no_ambiente(amb),
            prompt=Path(prompt).expanduser() if prompt else PROMPT_PADRAO,
        )


# --------------------------------------------------------------------------- #
# Uma rodada                                                                   #
# --------------------------------------------------------------------------- #


def rota_dos_eventos(execucao_id: str) -> str:
    return f"{ROTA_DOS_EVENTOS}?execucao={execucao_id}"


@dataclass(slots=True)
class Execucao:
    """Uma rodada de descoberta na memória: o estado, os números e os eventos numerados."""

    id: str
    iniciada: datetime
    estado: str = "procurando"
    etapa: str = "pesquisando"
    texto: str = PROCURANDO
    lidas: int = 0
    encontradas: list[str] = field(default_factory=list)
    buscas: int = 0
    paginas: int = 0
    run_id: str | None = None
    sessao_id: str | None = None
    parar_pedido: bool = False
    tarefa: asyncio.Task[None] | None = None
    terminada_em: float | None = None
    eventos: list[dict[str, Any]] = field(default_factory=list)
    _sinal: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def terminada(self) -> bool:
        return self.estado != "procurando"

    @property
    def ultimo_seq(self) -> int:
        return len(self.eventos)

    @property
    def sinal(self) -> asyncio.Event:
        """Dispara no próximo evento. Pegue antes de ler, para não perder o aviso."""
        return self._sinal

    def emitir(self, tipo: str, campos: Mapping[str, Any]) -> dict[str, Any]:
        evento = {"seq": self.ultimo_seq + 1, "tipo": tipo, **campos}
        self.eventos.append(evento)
        sinal, self._sinal = self._sinal, asyncio.Event()
        sinal.set()
        return evento

    def progresso(self, etapa: str, texto: str) -> None:
        self.etapa, self.texto = etapa, texto
        self.emitir(
            "progresso",
            {
                "etapa": etapa,
                "texto": texto,
                "lidas": self.lidas,
                "encontradas": len(self.encontradas),
            },
        )

    def terminar(self, estado: str, texto: str) -> None:
        self.estado, self.texto = estado, texto
        self.terminada_em = time.monotonic()
        self.emitir(
            "fim",
            {
                "estado": estado,
                "lidas": self.lidas,
                "encontradas": len(self.encontradas),
                "texto": texto,
            },
        )

    def resumo(self) -> dict[str, Any]:
        """O bloco `descoberta` de `GET /api/receitas`."""
        return {
            "estado": self.estado,
            "lidas": self.lidas,
            "encontradas": len(self.encontradas),
            "texto": self.texto,
        }

    def inicio(self) -> dict[str, Any]:
        """A resposta de `POST /api/receitas/descoberta` (`descoberta-inicio.json`)."""
        return {
            "execucao_id": self.id,
            "estado": self.estado,
            "texto": self.texto,
            "eventos": rota_dos_eventos(self.id),
        }

    def depois_de(self, seq: int) -> list[dict[str, Any]]:
        return self.eventos[max(0, seq) :]


@dataclass(frozen=True, slots=True)
class Resposta:
    """O que a rota devolve: o status HTTP e o envelope."""

    status: int
    ok: bool
    dados: dict[str, Any] | None
    erro: str | None = None
    categoria: str | None = None


# --------------------------------------------------------------------------- #
# O serviço                                                                    #
# --------------------------------------------------------------------------- #


class ServicoDeDescoberta:
    """A rodada de descoberta em andamento e a última, sobre a sessão do app."""

    def __init__(
        self,
        sessao: Sessao,
        *,
        conversa: ServicoDeConversa | None = None,
        fabrica_do_cliente: Callable[[], ClienteHermes] | None = None,
        configuracao: Configuracao | None = None,
    ) -> None:
        self.sessao = sessao
        self.conversa = conversa
        self.fabrica_do_cliente = fabrica_do_cliente
        self.configuracao = configuracao or Configuracao()
        self._cliente: ClienteHermes | None = None
        self._atual: Execucao | None = None

    @classmethod
    def do_ambiente(
        cls, sessao: Sessao, conversa: ServicoDeConversa | None = None
    ) -> ServicoDeDescoberta:
        return cls(sessao, conversa=conversa, configuracao=Configuracao.do_ambiente())

    def cliente(self) -> ClienteHermes:
        """O cliente do Hermes: o da conversa, ou um próprio quando há fábrica."""
        if self.fabrica_do_cliente is None and self.conversa is not None:
            return self.conversa.cliente()
        if self._cliente is None:
            self._cliente = (self.fabrica_do_cliente or ClienteHermes.do_ambiente)()
        return self._cliente

    async def fechar(self) -> None:
        atual = self._atual
        if atual is not None and atual.tarefa is not None and not atual.tarefa.done():
            atual.tarefa.cancel()
            await asyncio.gather(atual.tarefa, return_exceptions=True)
        if self._cliente is not None:
            await self._cliente.fechar()
            self._cliente = None

    # -- o que a tela lê ---------------------------------------------------- #

    @property
    def em_andamento(self) -> Execucao | None:
        atual = self._atual
        return atual if atual is not None and not atual.terminada else None

    def estado(self) -> dict[str, Any] | None:
        """A rodada de agora ou a última deste processo; `None` se nenhuma rodou."""
        return self._atual.resumo() if self._atual is not None else None

    def execucao(self, execucao_id: str | None) -> Execucao | None:
        """A rodada pedida (ou a última, sem id), se ainda está na memória."""
        atual = self._atual
        if atual is None or (execucao_id is not None and execucao_id != atual.id):
            return None
        return atual

    def assinar(self, execucao: Execucao, desde: int) -> AsyncIterator[str] | None:
        """Os eventos depois de `desde`, em SSE; `None` quando não há mais nada a mandar."""
        if execucao.terminada and desde >= execucao.ultimo_seq:
            return None
        return self._transmitir(execucao, desde)

    async def _transmitir(self, execucao: Execucao, desde: int) -> AsyncIterator[str]:
        visto = max(0, desde)
        yield ": conectado\n\n"
        while True:
            sinal = execucao.sinal
            for evento in execucao.depois_de(visto):
                yield quadro_sse(evento)
                visto = int(evento["seq"])
            if execucao.terminada and visto >= execucao.ultimo_seq:
                return
            try:
                await asyncio.wait_for(sinal.wait(), self.configuracao.keepalive_s)
            except TimeoutError:
                yield ": keepalive\n\n"

    # -- começar ------------------------------------------------------------ #

    async def iniciar(self) -> Resposta:
        """Começa uma rodada, ou diz por que não. Nunca espera a rodada terminar."""
        rodando = self.em_andamento
        if rodando is not None:
            return Resposta(409, False, rodando.inicio(), JA_PROCURANDO, "ocupado")
        if not self.configuracao.ligada:
            # 501: a tela trata como rota que não existe e abre a conversa com o pedido.
            dados = {
                "execucao_id": None,
                "estado": "parada",
                "texto": DESLIGADA_AQUI,
                "eventos": None,
            }
            return Resposta(501, False, dados, DESLIGADA_AQUI, "regra")
        # Daqui até a tarefa existir não há `await`: dois cliques juntos não abrem duas rodadas.
        execucao = Execucao(id=f"dx-{uuid.uuid4().hex[:8]}", iniciada=self.sessao.dossie.agora())
        ocupada = self.conversa is not None and self.conversa.ocupada
        if ocupada:
            execucao.progresso("esperando", ESPERANDO_A_CONVERSA)
        else:
            execucao.progresso("pesquisando", PROCURANDO)
        self._atual = execucao
        execucao.tarefa = asyncio.create_task(
            self._rodar(execucao), name=f"descoberta {execucao.id}"
        )
        return Resposta(202, True, execucao.inicio())

    async def esperar(self) -> None:
        """Espera a rodada de agora terminar (para os testes)."""
        atual = self._atual
        if atual is not None and atual.tarefa is not None:
            await asyncio.gather(atual.tarefa, return_exceptions=True)

    # -- a rodada ----------------------------------------------------------- #

    async def _rodar(self, execucao: Execucao) -> None:
        try:
            if not await self._esperar_a_conversa(execucao):
                execucao.terminar("parada", CONVERSA_NAO_TERMINOU)
                return
            instrucoes = self._instrucoes()
            if instrucoes is None:
                execucao.terminar("erro", SEM_INSTRUCOES)
                return
            cliente = self.cliente()
            execucao.sessao_id = await self._abrir_sessao(cliente, execucao)
            run_id = execucao.run_id = await self._iniciar_run(cliente, execucao, instrucoes)
            try:
                async with asyncio.timeout(self.configuracao.duracao_maxima_s):
                    status = await self._acompanhar(cliente, execucao, run_id)
            except TimeoutError:
                await self._parar(cliente, execucao)
                await self._conferir_a_transcricao(cliente, execucao)
                execucao.terminar("erro", texto_do_erro(DEMOROU, len(execucao.encontradas)))
                return
            await self._conferir_a_transcricao(cliente, execucao)
            self._terminar_pelo_status(execucao, status)
        except asyncio.CancelledError:
            if not execucao.terminada:
                execucao.terminar("erro", texto_do_erro(INTERROMPIDA, len(execucao.encontradas)))
            raise
        except ErroDoHermes as erro:
            logger.warning(
                "descoberta %s: o Hermes falhou (%s): %s", execucao.id, type(erro).__name__, erro
            )
            execucao.terminar(
                "erro", texto_do_erro(_erro_do_hermes(erro), len(execucao.encontradas))
            )
        except Exception:
            logger.exception("descoberta %s quebrou", execucao.id)
            execucao.terminar("erro", texto_do_erro(PROBLEMA, len(execucao.encontradas)))

    def _terminar_pelo_status(self, execucao: Execucao, status: str) -> None:
        encontradas = len(execucao.encontradas)
        if status in {"completed", "cancelled"}:
            execucao.terminar("parada", texto_do_fim(execucao.lidas, encontradas))
        elif status == "interrupted":
            execucao.terminar("erro", texto_do_erro(INTERROMPIDA, encontradas))
        else:
            execucao.terminar("erro", texto_do_erro(PROBLEMA, encontradas))

    async def _esperar_a_conversa(self, execucao: Execucao) -> bool:
        """Espera o turno da conversa terminar. `False` se passou do prazo."""
        if self.conversa is None or not self.conversa.ocupada:
            return True
        prazo = time.monotonic() + self.configuracao.espera_da_conversa_s
        while self.conversa.ocupada:
            if time.monotonic() >= prazo:
                return False
            await asyncio.sleep(self.configuracao.intervalo_da_espera_s)
        execucao.progresso("pesquisando", PROCURANDO)
        return True

    def _instrucoes(self) -> str | None:
        try:
            texto = self.configuracao.prompt.read_text(encoding="utf-8").strip()
        except OSError:
            logger.warning("sem as instruções da descoberta em %s", self.configuracao.prompt)
            return None
        return texto or None

    async def _abrir_sessao(self, cliente: ClienteHermes, execucao: Execucao) -> str:
        """Uma sessão nova do Hermes só para esta rodada, com um título que diz o que é."""
        titulo = f"Sabor da Maria: busca de receitas {execucao.id}"
        try:
            sessao = await cliente.criar_sessao(titulo)
        except PedidoRecusado:
            sessao = await cliente.criar_sessao()  # título repetido: o Hermes escolhe
        return str(sessao["id"])

    async def _iniciar_run(
        self, cliente: ClienteHermes, execucao: Execucao, instrucoes: str
    ) -> str:
        """`POST /v1/runs`; com o Hermes no limite de turnos, espera e tenta de novo."""
        restantes = max(1, self.configuracao.tentativas_se_ocupada)
        while True:
            restantes -= 1
            try:
                aceito = await cliente.iniciar_run(
                    ENTRADA,
                    sessao_id=execucao.sessao_id,
                    instrucoes=instrucoes,
                    opcoes_do_modelo={"reasoning": {"effort": ESFORCO}},
                    chave_de_idempotencia=execucao.id,
                )
            except AgenteOcupada as erro:
                if restantes <= 0:
                    raise
                execucao.progresso("esperando", ESPERANDO_A_CONSULTORA)
                await asyncio.sleep(
                    max(erro.espera_s or 0.0, self.configuracao.espera_se_ocupada_s)
                )
                continue
            execucao.progresso("pesquisando", PROCURANDO)
            return aceito.run_id

    async def _acompanhar(self, cliente: ClienteHermes, execucao: Execucao, run_id: str) -> str:
        """Segue os eventos do run até o fim; se o fluxo cai, consulta o estado."""
        try:
            async for evento in cliente.eventos_run(run_id):
                status = await self._processar(cliente, execucao, evento)
                if status is not None:
                    return status
        except ErroDoHermes as erro:
            if erro.categoria not in {"rede", "tempo"}:
                raise
            logger.info(
                "descoberta %s: o fluxo do run caiu (%s); sigo pelo estado", execucao.id, erro
            )
        return await self._esperar_o_fim(cliente, run_id)

    async def _esperar_o_fim(self, cliente: ClienteHermes, run_id: str) -> str:
        while True:
            estado = await cliente.estado_run(run_id)
            status = str(estado.get("status") or "")
            if status in _TERMINAIS:
                return status
            await asyncio.sleep(self.configuracao.intervalo_do_estado_s)

    async def _processar(
        self, cliente: ClienteHermes, execucao: Execucao, evento: EventoSSE
    ) -> str | None:
        """Um evento do run. Devolve o status quando o run terminou."""
        nome = evento.nome
        dados = evento.dados if isinstance(evento.dados, dict) else {}
        if nome.startswith("run."):
            status = nome.removeprefix("run.")
            return status if status in _TERMINAIS else None
        ferramenta = nome_da_ferramenta(str(dados.get("tool") or dados.get("tool_name") or ""))
        if nome == "tool.started":
            await self._comecou(cliente, execucao, ferramenta, dados.get("preview"))
        elif nome == "tool.completed" and ferramenta == "buscar_receita_na_web":
            receita_id, conhecida = resultado_da_leitura(dados.get("preview"))
            if conhecida is not True:
                execucao.lidas += 1
                if receita_id is not None:
                    await self._encontrada(execucao, receita_id)
                execucao.progresso("lendo", execucao.texto)
        return None

    async def _comecou(
        self, cliente: ClienteHermes, execucao: Execucao, ferramenta: str, preview: object
    ) -> None:
        if ferramenta == "pauta_de_descoberta":
            execucao.progresso("pesquisando", SEPARANDO)
        elif ferramenta == "web_search":
            execucao.buscas += 1
            if execucao.buscas > self.configuracao.maximo_de_buscas:
                await self._parar(cliente, execucao)
                return
            consulta = preview.strip() if isinstance(preview, str) and preview.strip() else None
            texto = f"Procurando na internet: {consulta}…" if consulta else PROCURANDO
            execucao.progresso("pesquisando", texto)
        elif ferramenta == "buscar_receita_na_web":
            execucao.paginas += 1
            if execucao.paginas > self.configuracao.maximo_de_paginas:
                await self._parar(cliente, execucao)
                return
            site = _site(preview)
            execucao.progresso("lendo", f"Lendo uma receita de {site}…" if site else LENDO_UMA)

    async def _parar(self, cliente: ClienteHermes, execucao: Execucao) -> None:
        if execucao.parar_pedido or execucao.run_id is None:
            return
        execucao.parar_pedido = True
        try:
            await cliente.parar(execucao.run_id)
        except ErroDoHermes as erro:
            logger.warning("descoberta %s: o Hermes não aceitou parar: %s", execucao.id, erro)

    async def _encontrada(self, execucao: Execucao, receita_id: str) -> None:
        """A receita que o servidor guardou nesta rodada: marca a origem e avisa a grade.

        A pista vem do Hermes, mas quem confirma é o catálogo: receita que não
        existe, que já estava lá antes da rodada, ou que ela mesma trouxe, não
        conta como encontrada.
        """
        if receita_id in execucao.encontradas:
            return
        item = await asyncio.to_thread(self._marcar_e_ler, receita_id, execucao.iniciada)
        if item is None:
            return
        execucao.encontradas.append(receita_id)
        aba, receita = item
        if aba is not None:
            execucao.emitir("receita.encontrada", {"aba": aba, "receita": receita})

    def _marcar_e_ler(
        self, receita_id: str, desde: datetime
    ) -> tuple[str | None, dict[str, Any]] | None:
        from mise import receitas_json  # noqa: PLC0415

        guardada = self.sessao.catalogo.marcar_como_descoberta(receita_id, desde)
        if guardada is None:
            return None
        leitura = receitas_json.ler(self.sessao, [guardada])[0]
        restante = self.sessao.dossie.orcamento().restante
        aba = leitura.aba
        item = receitas_json.item_da_grade(
            self.sessao, leitura, restante, com_pergunta=aba == "falta_resposta"
        )
        return aba, item

    async def _conferir_a_transcricao(self, cliente: ClienteHermes, execucao: Execucao) -> None:
        """Confere pela transcrição da sessão o que os eventos resumiram (ou perderam)."""
        if execucao.sessao_id is None:
            return
        try:
            historico = await cliente.mensagens(execucao.sessao_id)
        except ErroDoHermes as erro:
            logger.info("descoberta %s: sem a transcrição (%s)", execucao.id, erro)
            return
        lidas = 0
        for mensagem in historico.mensagens:
            if mensagem.get("role") != "tool":
                continue
            conteudo = mensagem.get("content")
            texto = (
                conteudo if isinstance(conteudo, str) else json.dumps(conteudo, ensure_ascii=False)
            )
            receita_id, conhecida = resultado_da_leitura(texto)
            nome = str(mensagem.get("tool_name") or mensagem.get("name") or "")
            # Sem o nome da ferramenta, só a resposta da leitura traz `ja_conhecida`.
            da_leitura = (
                nome_da_ferramenta(nome) == "buscar_receita_na_web"
                if nome
                else (conhecida is not None)
            )
            if not da_leitura or conhecida is True:
                continue
            lidas += 1
            if receita_id is not None:
                await self._encontrada(execucao, receita_id)
        execucao.lidas = max(execucao.lidas, lidas)


__all__ = [
    "DESLIGADA",
    "DURACAO_MAXIMA_S",
    "ENTRADA",
    "ESFORCO",
    "LIGADA",
    "PROMPT_PADRAO",
    "SEGUNDOS_POR_PASSO",
    "VAR_DESCOBERTA",
    "VAR_PROMPT",
    "Configuracao",
    "Execucao",
    "Resposta",
    "ServicoDeDescoberta",
    "ligada_no_ambiente",
    "resultado_da_leitura",
    "rota_dos_eventos",
    "texto_do_erro",
    "texto_do_fim",
]
