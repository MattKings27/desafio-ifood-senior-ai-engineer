"""Cliente do servidor de API do Hermes: é por ele que o chat da web fala com o agente.

O Hermes 0.21 tem, dentro do gateway, um servidor HTTP em 127.0.0.1:8642. Ele
fica desligado até existir `API_SERVER_KEY` no `.env` do perfil padrão. Com o
gateway em modo multiplex, cada perfil responde sob `/p/<perfil>/` e só aceita
a chave do próprio perfil: a do padrão dá 401 ali.
Este módulo é o único lugar do projeto que conversa com esse servidor.

A chave nunca aparece em log, exceção ou `repr`. Ela mora numa `ChaveSecreta`,
entra no cabeçalho só no momento do envio (um `httpx.Auth`), e as mensagens de
erro citam o nome da variável e o arquivo, nunca o valor. As exceções do httpx
não são encadeadas nas nossas (`from None`): o pedido que elas carregam leva o
cabeçalho `Authorization`.

Rotas usadas (todas sob o prefixo do perfil, menos `/health`):

    GET  /health                           vivo? sem autenticação
    GET  /api/sessions                     sessões (limit, source)
    POST /api/sessions                     sessão nova
    GET  /api/sessions/{id}/messages       histórico (order=oldest)
    POST /api/sessions/{id}/chat/stream    um turno, em SSE
    POST /v1/runs                          um turno que sobrevive ao cliente cair
    GET  /v1/runs/{id}                     estado do run
    GET  /v1/runs/{id}/events              eventos do run, em SSE
    POST /v1/runs/{id}/stop                parar (vale também para o chat/stream)

Dois comportamentos do Hermes que quem usa este cliente precisa saber:

- `chat/stream` **interrompe o turno** quando a conexão cai. Quem não pode perder
  o turno (a web, quando ela fecha a aba) consome o stream numa tarefa própria.
- `/v1/runs/{id}/events` aceita **um** assinante: quando ele desconecta, o
  Hermes descarta o buffer, e uma nova assinatura dá 404. O run continua, e o
  resultado sai por `estado_run`.
"""

from __future__ import annotations

import codecs
import hmac
import json
import logging
import os
import re
from collections.abc import AsyncIterator, Generator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, ClassVar, Final
from urllib.parse import quote, urlsplit

import httpx

logger = logging.getLogger(__name__)

URL_PADRAO: Final = "http://127.0.0.1:8642"
PERFIL_PADRAO: Final = "sabor-da-maria"
#: O nome que o Hermes lê no `.env` de cada perfil.
NOME_DA_CHAVE: Final = "API_SERVER_KEY"
VAR_CHAVE: Final = "MISE_HERMES_CHAVE"
VAR_URL: Final = "MISE_HERMES_URL"
VAR_PERFIL: Final = "MISE_HERMES_PERFIL"
#: Abaixo disso o Hermes se recusa a abrir a porta (`has_usable_secret(min_length=16)`).
TAMANHO_MINIMO_DA_CHAVE: Final = 16
#: O Hermes manda `: keepalive` a cada 10 s. Um minuto sem nenhum byte é conexão morta.
SILENCIO_MAXIMO_S: Final = 60.0

_PERFIL_VALIDO: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_FIM_DE_LINHA: Final = re.compile(r"\r\n|\r|\n")
_TRECHO_DE_ERRO: Final = 300
_STATUS_OK_MAXIMO: Final = 299
_STATUS_SERVIDOR: Final = 500
_SEM_PERMISSAO: Final = frozenset({401, 403})
_NAO_ENCONTRADO: Final = 404
_CONFLITO: Final = 409
_MUITOS_PEDIDOS: Final = 429


# --------------------------------------------------------------------------- #
# Erros                                                                        #
# --------------------------------------------------------------------------- #


class ErroDoHermes(Exception):
    """Base dos erros do cliente. A mensagem é em pt-BR e nunca traz a chave.

    `categoria` segue o `turno.falhou` de contratos/web (`rede`, `tempo`,
    `consultora`), para quem traduz o erro para a tela não precisar adivinhar.
    """

    categoria: ClassVar[str] = "consultora"

    def __init__(
        self, mensagem: str, *, status: int | None = None, codigo: str | None = None
    ) -> None:
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo


class HermesForaDoAr(ErroDoHermes):
    """Nada escutando na porta: gateway parado ou sem a chave do perfil padrão."""

    categoria = "rede"


class ConexaoInterrompida(ErroDoHermes):
    """A conexão caiu no meio da resposta."""

    categoria = "rede"


class TempoEsgotado(ErroDoHermes):
    """O Hermes não mandou nenhum byte dentro do prazo."""

    categoria = "tempo"


class ChaveAusente(ErroDoHermes):
    """Não há chave para o perfil: nem em `MISE_HERMES_CHAVE`, nem no `.env`."""


class ChaveRecusada(ErroDoHermes):
    """401/403: a chave não é a do perfil (a do perfil padrão não vale em /p/<perfil>/)."""


class NaoEncontrado(ErroDoHermes):
    """404: sessão, run ou perfil que o gateway não conhece."""


class Conflito(ErroDoHermes):
    """409: sessão que já existe, ou run que não está mais ativo neste processo."""


class AgenteOcupada(ErroDoHermes):
    """429: o limite de turnos simultâneos do servidor de API foi atingido."""

    def __init__(self, mensagem: str, *, espera_s: float | None = None, **resto: Any) -> None:
        super().__init__(mensagem, **resto)
        self.espera_s = espera_s


class FalhaNoHermes(ErroDoHermes):
    """5xx: o Hermes quebrou do lado de lá."""


class PedidoRecusado(ErroDoHermes):
    """Outro 4xx: o pedido saiu malformado daqui."""


class RespostaInvalida(ErroDoHermes):
    """A resposta não tem a forma que o Hermes 0.21 documenta."""


# --------------------------------------------------------------------------- #
# A chave                                                                      #
# --------------------------------------------------------------------------- #


class ChaveSecreta:
    """Um segredo que não se deixa imprimir. `revelar()` é o único jeito de ler."""

    __slots__ = ("_valor",)

    def __init__(self, valor: str) -> None:
        self._valor = valor

    def revelar(self) -> str:
        return self._valor

    def igual_a(self, outra: ChaveSecreta) -> bool:
        """Compara sem vazar tempo, para conferir se duas chaves são a mesma."""
        return hmac.compare_digest(self._valor.encode(), outra._valor.encode())

    def __repr__(self) -> str:
        return "ChaveSecreta('****')"

    __str__ = __repr__


@dataclass(frozen=True)
class ChaveEncontrada:
    """A chave e de onde ela veio: o nome da variável ou o caminho do `.env`."""

    chave: ChaveSecreta
    origem: str


def hermes_home(ambiente: Mapping[str, str] | None = None) -> Path:
    """A pasta do Hermes: `HERMES_HOME`, como o próprio Hermes lê, ou `~/.hermes`."""
    amb = os.environ if ambiente is None else ambiente
    valor = amb.get("HERMES_HOME", "").strip()
    return Path(valor).expanduser() if valor else Path.home() / ".hermes"


def validar_perfil(perfil: str) -> str:
    """O nome entra em caminho de arquivo e em URL: só o alfabeto dos perfis do Hermes."""
    if not _PERFIL_VALIDO.match(perfil) or ".." in perfil:
        raise ValueError(f"nome de perfil inválido: {perfil!r}")
    return perfil


def caminho_do_env(perfil: str, home: Path | None = None) -> Path:
    """O `.env` do perfil. O perfil `default` usa o `.env` da própria pasta do Hermes."""
    base = hermes_home() if home is None else home
    if validar_perfil(perfil) == "default":
        return base / ".env"
    return base / "profiles" / perfil / ".env"


def _sem_comentario_no_fim(valor: str) -> str:
    """Tira `# comentário` do fim, como o python-dotenv (e o Hermes) fazem.

    Entre aspas, o comentário só começa depois da aspa que fecha. Sem aspas, só
    `#` precedido de espaço conta: `abc#def` é um valor, `abc # def` não.
    """
    valor = valor.strip()
    if valor[:1] in ("'", '"'):
        aspa = valor[0]
        i = 1
        while i < len(valor):
            if aspa == '"' and valor[i] == "\\":
                i += 2
                continue
            if valor[i] == aspa:
                return valor[: i + 1] if valor[i + 1 :].lstrip().startswith("#") else valor
            i += 1
        return valor
    return re.split(r"\s+#", valor, maxsplit=1)[0].strip()


def _entre(valor: str, aspa: str) -> bool:
    return len(valor) > 1 and valor[0] == valor[-1] == aspa


def _sem_aspas(valor: str) -> str:
    if _entre(valor, '"'):
        return re.sub(r'\\(["\\])', r"\1", valor[1:-1])
    if _entre(valor, "'"):
        return valor[1:-1]
    return valor


def ler_valor_do_env(texto: str, nome: str) -> str | None:
    """O valor de `nome` num `.env`, lido do mesmo jeito que o Hermes lê.

    `export` na frente, comentários, aspas simples e duplas. Se a variável
    aparece mais de uma vez, vale a última, como no Hermes.
    """
    achado: str | None = None
    for bruta in texto.splitlines():
        linha = bruta.strip()
        if not linha or linha.startswith("#"):
            continue
        if linha.startswith("export "):
            linha = linha[len("export ") :].lstrip()
        chave, sep, valor = linha.partition("=")
        if sep and chave.strip() == nome:
            achado = _sem_aspas(_sem_comentario_no_fim(valor))
    return achado


def ler_chave_do_env(caminho: Path) -> ChaveSecreta | None:
    """A `API_SERVER_KEY` do arquivo, ou `None` se o arquivo ou a linha não existem.

    Arquivo que existe mas não se deixa ler vira `ChaveAusente`: tratá-lo como
    "sem chave" faria o bootstrap gerar outra por cima de uma que existe.
    """
    try:
        texto = caminho.read_text(encoding="utf-8-sig", errors="replace")
    except FileNotFoundError:
        return None
    except OSError as causa:
        raise ChaveAusente(
            f"Não deu para ler {caminho} ({type(causa).__name__}); confira as permissões."
        ) from None
    valor = ler_valor_do_env(texto, NOME_DA_CHAVE)
    return ChaveSecreta(valor) if valor is not None else None


def chave_utilizavel(chave: ChaveSecreta | None) -> bool:
    """O Hermes só abre a porta com 16 ou mais caracteres."""
    return chave is not None and len(chave.revelar().strip()) >= TAMANHO_MINIMO_DA_CHAVE


def descobrir_chave(
    perfil: str, *, ambiente: Mapping[str, str] | None = None, home: Path | None = None
) -> ChaveEncontrada:
    """`MISE_HERMES_CHAVE` primeiro; senão, a `API_SERVER_KEY` do `.env` do perfil."""
    amb = os.environ if ambiente is None else ambiente
    da_variavel = amb.get(VAR_CHAVE, "").strip()
    if da_variavel:
        chave = ChaveSecreta(da_variavel)
        if not chave_utilizavel(chave):
            raise ChaveAusente(
                f"{VAR_CHAVE} tem menos de {TAMANHO_MINIMO_DA_CHAVE} caracteres; "
                "o Hermes recusaria essa chave."
            )
        return ChaveEncontrada(chave, VAR_CHAVE)

    caminho = caminho_do_env(perfil, hermes_home(amb) if home is None else home)
    chave_do_arquivo = ler_chave_do_env(caminho)
    if chave_do_arquivo is None:
        raise ChaveAusente(
            f"Sem chave para o perfil {perfil}: defina {VAR_CHAVE} ou rode a etapa "
            f"'API do agente' do bootstrap, que grava {NOME_DA_CHAVE} em {caminho}."
        )
    if not chave_utilizavel(chave_do_arquivo):
        raise ChaveAusente(
            f"A {NOME_DA_CHAVE} de {caminho} tem menos de {TAMANHO_MINIMO_DA_CHAVE} "
            "caracteres; o Hermes recusaria essa chave."
        )
    return ChaveEncontrada(chave_do_arquivo, str(caminho))


class _Portador(httpx.Auth):
    """Põe o `Authorization` só no pedido que sai, sem guardar o cabeçalho no cliente."""

    def __init__(self, chave: ChaveSecreta) -> None:
        self._chave = chave

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self._chave.revelar()}"
        yield request

    def __repr__(self) -> str:
        return "_Portador('****')"


# --------------------------------------------------------------------------- #
# SSE                                                                          #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EventoSSE:
    """Um evento do stream.

    `nome` é o campo `event:`. O `/v1/runs/{id}/events` do Hermes não manda esse
    campo e põe o nome em `dados["event"]`; nesse caso é ele que vale. Sem os
    dois, o nome é `message`, como manda a especificação.
    """

    nome: str
    dados: Any
    ultimo_id: str | None = None


class LeitorSSE:
    """Parser incremental de `text/event-stream`, na especificação do WHATWG.

    Os pedaços chegam partidos em qualquer byte: no meio de uma linha, no meio de
    um caractere acentuado, entre o `\\r` e o `\\n`. Nada disso pode virar evento
    trocado ou `R$` cortado ao meio. Comentários (`: keepalive`) não viram
    evento; ficam contados em `comentarios`, para quem quiser medir silêncio.
    """

    def __init__(self) -> None:
        self._decodificador = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._resto = ""
        self._dados: list[str] = []
        self._evento = ""
        self._ultimo_id: str | None = None
        self._inicio = True
        self.comentarios = 0
        self.retry_ms: int | None = None

    def alimentar(self, pedaco: bytes) -> list[EventoSSE]:
        return self._processar(self._decodificador.decode(pedaco), final=False)

    def terminar(self) -> list[EventoSSE]:
        """Fim do stream. Evento sem a linha em branco final é descartado (especificação)."""
        eventos = self._processar(self._decodificador.decode(b"", final=True), final=True)
        if self._resto or self._dados:
            logger.debug("stream terminou no meio de um evento; descartado como manda o SSE")
        self._resto, self._dados, self._evento = "", [], ""
        return eventos

    def _processar(self, texto: str, *, final: bool) -> list[EventoSSE]:
        if self._inicio and texto:
            self._inicio = False
            texto = texto.removeprefix("﻿")
        buffer = self._resto + texto
        eventos: list[EventoSSE] = []
        inicio = 0
        for fim in _FIM_DE_LINHA.finditer(buffer):
            if fim.group() == "\r" and fim.end() == len(buffer) and not final:
                break  # pode ser a primeira metade de um \r\n; espera o próximo pedaço
            evento = self._linha(buffer[inicio : fim.start()])
            if evento is not None:
                eventos.append(evento)
            inicio = fim.end()
        self._resto = buffer[inicio:]
        return eventos

    def _linha(self, linha: str) -> EventoSSE | None:
        if not linha:
            return self._despachar()
        if linha.startswith(":"):
            self.comentarios += 1
            return None
        campo, _, valor = linha.partition(":")
        valor = valor.removeprefix(" ")
        if campo == "data":
            self._dados.append(valor)
        elif campo == "event":
            self._evento = valor
        elif campo == "id":
            if "\x00" not in valor:
                self._ultimo_id = valor
        elif campo == "retry" and valor.isdigit():
            self.retry_ms = int(valor)
        return None

    def _despachar(self) -> EventoSSE | None:
        if not self._dados:
            self._evento = ""
            return None
        bruto = "\n".join(self._dados)
        nome = self._evento
        self._dados, self._evento = [], ""
        try:
            dados: Any = json.loads(bruto)
        except ValueError:
            dados = bruto
        if not nome:
            embutido = dados.get("event") if isinstance(dados, dict) else None
            nome = embutido if isinstance(embutido, str) and embutido else "message"
        return EventoSSE(nome=nome, dados=dados, ultimo_id=self._ultimo_id)


# --------------------------------------------------------------------------- #
# O que as rotas devolvem                                                      #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SaudeDoHermes:
    """O servidor respondeu e aceitou a chave do perfil."""

    versao: str
    perfil: str


@dataclass(frozen=True)
class HistoricoDaSessao:
    """As mensagens e o id que o Hermes resolveu.

    Depois de uma compressão o Hermes continua a conversa numa sessão filha, e
    `sessao_id` já vem com o id dela; quem guardou o id antigo deve adotá-lo.
    """

    sessao_id: str
    mensagens: list[dict[str, Any]]


@dataclass(frozen=True)
class RunAceito:
    """O que o `POST /v1/runs` devolve. `repetido` quando a chave de idempotência já existia."""

    run_id: str
    status: str
    repetido: bool


# --------------------------------------------------------------------------- #
# O cliente                                                                    #
# --------------------------------------------------------------------------- #


def _objeto(valor: Any, contexto: str) -> dict[str, Any]:
    if not isinstance(valor, dict):
        raise RespostaInvalida(f"O Hermes respondeu {contexto} sem um objeto JSON.")
    return valor


def _texto_obrigatorio(valor: Any, campo: str, contexto: str) -> str:
    if not isinstance(valor, str) or not valor:
        raise RespostaInvalida(f"O Hermes respondeu {contexto} sem o campo {campo!r}.")
    return valor


def _segmento(valor: str, nome: str) -> str:
    """Um id que vai dentro do caminho da URL, escapado e nunca vazio."""
    if not valor.strip():
        raise ValueError(f"{nome} vazio")
    return quote(valor, safe="")


def _validar_url(url: str) -> str:
    partes = urlsplit(url)
    if partes.scheme not in ("http", "https") or not partes.netloc:
        raise ValueError(f"{VAR_URL} precisa ser http(s)://host:porta, veio {url!r}")
    return url.rstrip("/")


def _detalhe_do_erro(resposta: httpx.Response) -> tuple[str, str | None]:
    """A mensagem e o código que o Hermes mandou, cortados. O Hermes já redige segredo."""
    try:
        corpo = resposta.json()
    except ValueError:
        return resposta.text.strip()[:_TRECHO_DE_ERRO], None
    erro = corpo.get("error") if isinstance(corpo, dict) else None
    if isinstance(erro, dict):
        mensagem, codigo = erro.get("message"), erro.get("code")
        return (
            str(mensagem or "")[:_TRECHO_DE_ERRO],
            str(codigo) if codigo else None,
        )
    if isinstance(erro, str):
        return erro[:_TRECHO_DE_ERRO], None
    return json.dumps(corpo, ensure_ascii=False)[:_TRECHO_DE_ERRO], None


def _espera_s(resposta: httpx.Response) -> float | None:
    bruto = resposta.headers.get("Retry-After", "").strip()
    try:
        return float(bruto) if bruto else None
    except ValueError:
        return None


class ClienteHermes:
    """Cliente assíncrono do servidor de API do Hermes, para um perfil.

    Use com `async with`, ou chame `fechar()`. Sem `transporte`, fala com a rede;
    os testes passam um `httpx.MockTransport`.
    """

    def __init__(
        self,
        *,
        url: str = URL_PADRAO,
        perfil: str = PERFIL_PADRAO,
        chave: ChaveSecreta | None = None,
        origem_da_chave: str | None = None,
        motivo_sem_chave: str | None = None,
        transporte: httpx.AsyncBaseTransport | None = None,
        tempo_limite_s: float = 10.0,
        silencio_maximo_s: float = SILENCIO_MAXIMO_S,
    ) -> None:
        self.url = _validar_url(url)
        self.perfil = validar_perfil(perfil)
        self.origem_da_chave = origem_da_chave
        self._chave = chave
        self._motivo_sem_chave = motivo_sem_chave
        self._tempo_limite_s = tempo_limite_s
        self._silencio_maximo_s = silencio_maximo_s
        self._http = httpx.AsyncClient(
            base_url=self.url,
            transport=transporte,
            timeout=httpx.Timeout(tempo_limite_s, connect=min(tempo_limite_s, 3.0)),
            headers={"User-Agent": "sabor-da-maria/hermes-cliente"},
        )

    @classmethod
    def do_ambiente(
        cls,
        ambiente: Mapping[str, str] | None = None,
        *,
        home: Path | None = None,
        transporte: httpx.AsyncBaseTransport | None = None,
    ) -> ClienteHermes:
        """URL, perfil e chave das variáveis `MISE_HERMES_*` e do `.env` do perfil.

        Chave ausente não impede de montar o cliente: `saude()` e as chamadas
        autenticadas é que levantam `ChaveAusente`, com o motivo.
        """
        amb = os.environ if ambiente is None else ambiente
        perfil = amb.get(VAR_PERFIL, "").strip() or PERFIL_PADRAO
        url = amb.get(VAR_URL, "").strip() or URL_PADRAO
        try:
            encontrada = descobrir_chave(perfil, ambiente=amb, home=home)
        except ChaveAusente as causa:
            return cls(url=url, perfil=perfil, motivo_sem_chave=str(causa), transporte=transporte)
        return cls(
            url=url,
            perfil=perfil,
            chave=encontrada.chave,
            origem_da_chave=encontrada.origem,
            transporte=transporte,
        )

    @property
    def prefixo(self) -> str:
        """`/p/<perfil>` no gateway multiplex; o perfil padrão responde sem prefixo."""
        return "" if self.perfil == "default" else f"/p/{self.perfil}"

    @property
    def tem_chave(self) -> bool:
        return self._chave is not None

    def __repr__(self) -> str:
        estado = "presente" if self._chave is not None else "ausente"
        return f"ClienteHermes(url={self.url!r}, perfil={self.perfil!r}, chave={estado})"

    async def fechar(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> ClienteHermes:
        return self

    async def __aexit__(
        self,
        tipo: type[BaseException] | None,
        erro: BaseException | None,
        rastro: TracebackType | None,
    ) -> None:
        await self.fechar()

    # -- infraestrutura ----------------------------------------------------- #

    def _autenticacao(self) -> _Portador:
        if self._chave is None:
            raise ChaveAusente(self._motivo_sem_chave or f"Sem chave para o perfil {self.perfil}.")
        return _Portador(self._chave)

    def _conferir(self, resposta: httpx.Response, rota: str) -> None:
        status = resposta.status_code
        if status <= _STATUS_OK_MAXIMO:
            return
        mensagem, codigo = _detalhe_do_erro(resposta)
        onde = f"{resposta.request.method} {rota}"
        if status in _SEM_PERMISSAO:
            raise ChaveRecusada(
                f"O Hermes recusou a chave do perfil {self.perfil} (HTTP {status}, {onde}). "
                f"A chave veio de {self.origem_da_chave or 'lugar nenhum'}; a do perfil padrão "
                "não vale sob /p/<perfil>/. Rode `make agente-status`.",
                status=status,
                codigo=codigo,
            )
        if status == _NAO_ENCONTRADO:
            dica = (
                " O gateway não conhece este perfil: reinicie-o depois de criar o perfil."
                if "profile" in mensagem.lower()
                else ""
            )
            raise NaoEncontrado(
                f"O Hermes não achou {onde}: {mensagem}.{dica}", status=status, codigo=codigo
            )
        if status == _CONFLITO:
            raise Conflito(f"O Hermes recusou {onde}: {mensagem}.", status=status, codigo=codigo)
        if status == _MUITOS_PEDIDOS:
            raise AgenteOcupada(
                f"O agente está no limite de turnos simultâneos ({mensagem}).",
                espera_s=_espera_s(resposta),
                status=status,
                codigo=codigo,
            )
        if status >= _STATUS_SERVIDOR:
            raise FalhaNoHermes(
                f"O Hermes falhou em {onde} (HTTP {status}): {mensagem}.",
                status=status,
                codigo=codigo,
            )
        raise PedidoRecusado(
            f"O Hermes recusou {onde} (HTTP {status}): {mensagem}.", status=status, codigo=codigo
        )

    def _fora_do_ar(self, causa: Exception) -> HermesForaDoAr:
        return HermesForaDoAr(
            f"O servidor de API do Hermes não respondeu em {self.url} ({type(causa).__name__}). "
            "O gateway está parado, ou o perfil padrão não tem API_SERVER_KEY; "
            "rode `make agente-status`."
        )

    def _sem_resposta(self, rota: str) -> TempoEsgotado:
        return TempoEsgotado(f"O Hermes não respondeu a tempo em {rota}.")

    async def _pedir(
        self,
        metodo: str,
        rota: str,
        *,
        autenticar: bool = True,
        corpo: Mapping[str, Any] | None = None,
        parametros: Mapping[str, str | int] | None = None,
        cabecalhos: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        auth = self._autenticacao() if autenticar else None
        try:
            resposta = await self._http.request(
                metodo,
                rota,
                json=corpo,
                params=parametros,
                headers=cabecalhos,
                auth=auth if auth is not None else httpx.USE_CLIENT_DEFAULT,
            )
        except httpx.TimeoutException:
            raise self._sem_resposta(rota) from None
        except httpx.TransportError as causa:
            raise self._fora_do_ar(causa) from None
        logger.debug("Hermes %s %s -> %s", metodo, rota, resposta.status_code)
        self._conferir(resposta, rota)
        return resposta

    async def _json(self, metodo: str, rota: str, **opcoes: Any) -> Any:
        resposta = await self._pedir(metodo, rota, **opcoes)
        try:
            return resposta.json()
        except ValueError:
            raise RespostaInvalida(f"O Hermes respondeu {rota} com algo que não é JSON.") from None

    async def _stream(
        self,
        metodo: str,
        rota: str,
        *,
        corpo: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[EventoSSE]:
        auth = self._autenticacao()
        prazo = httpx.Timeout(self._tempo_limite_s, read=self._silencio_maximo_s)
        leitor = LeitorSSE()
        respondeu = False
        try:
            async with self._http.stream(
                metodo,
                rota,
                json=corpo,
                auth=auth,
                timeout=prazo,
                headers={"Accept": "text/event-stream"},
            ) as resposta:
                respondeu = True
                logger.debug("Hermes %s %s -> %s (stream)", metodo, rota, resposta.status_code)
                if resposta.status_code > _STATUS_OK_MAXIMO:
                    await resposta.aread()
                    self._conferir(resposta, rota)
                tipo = resposta.headers.get("content-type", "")
                if "text/event-stream" not in tipo:
                    raise RespostaInvalida(
                        f"O Hermes respondeu {rota} com {tipo or 'sem content-type'}, não SSE."
                    )
                async for pedaco in resposta.aiter_bytes():
                    for evento in leitor.alimentar(pedaco):
                        yield evento
                for evento in leitor.terminar():
                    yield evento
        except httpx.TimeoutException:
            raise self._sem_resposta(rota) from None
        except httpx.TransportError as causa:
            if not respondeu:
                raise self._fora_do_ar(causa) from None
            raise ConexaoInterrompida(
                f"A conexão com o Hermes caiu no meio de {rota} ({type(causa).__name__})."
            ) from None

    # -- rotas --------------------------------------------------------------- #

    async def versao(self) -> str:
        """`GET /health`, sem chave: a porta responde? Devolve a versão do Hermes."""
        dados = _objeto(await self._json("GET", "/health", autenticar=False), "/health")
        return str(dados.get("version") or "?")

    async def saude(self) -> SaudeDoHermes:
        """O caminho inteiro que o chat precisa: a porta responde e aceita a chave do perfil."""
        versao = await self.versao()
        await self._json("GET", f"{self.prefixo}/api/sessions", parametros={"limit": 1})
        return SaudeDoHermes(versao=versao, perfil=self.perfil)

    async def criar_sessao(
        self, titulo: str | None = None, *, sessao_id: str | None = None
    ) -> dict[str, Any]:
        """Sessão nova, com `source=api_server`. Título repetido o Hermes recusa (400)."""
        corpo: dict[str, Any] = {}
        if titulo is not None:
            corpo["title"] = titulo
        if sessao_id is not None:
            corpo["id"] = sessao_id
        rota = f"{self.prefixo}/api/sessions"
        dados = _objeto(await self._json("POST", rota, corpo=corpo), rota)
        sessao = _objeto(dados.get("session"), rota)
        _texto_obrigatorio(sessao.get("id"), "id", rota)
        return sessao

    async def listar_sessoes(
        self, *, limite: int = 50, fonte: str | None = "api_server"
    ) -> list[dict[str, Any]]:
        """As sessões mais recentes. `fonte=None` inclui as de outras origens, como o terminal."""
        parametros: dict[str, str | int] = {"limit": limite}
        if fonte:
            parametros["source"] = fonte
        rota = f"{self.prefixo}/api/sessions"
        dados = _objeto(await self._json("GET", rota, parametros=parametros), rota)
        itens = dados.get("data")
        if not isinstance(itens, list):
            raise RespostaInvalida(f"O Hermes respondeu {rota} sem a lista 'data'.")
        return [_objeto(item, rota) for item in itens]

    async def mensagens(self, sessao_id: str, *, limite: int = 500) -> HistoricoDaSessao:
        """O histórico, do mais antigo ao mais novo (o Hermes corta em 500 por página)."""
        rota = f"{self.prefixo}/api/sessions/{_segmento(sessao_id, 'sessao_id')}/messages"
        dados = _objeto(
            await self._json("GET", rota, parametros={"order": "oldest", "limit": limite}), rota
        )
        itens = dados.get("data")
        if not isinstance(itens, list):
            raise RespostaInvalida(f"O Hermes respondeu {rota} sem a lista 'data'.")
        resolvida = dados.get("session_id")
        return HistoricoDaSessao(
            sessao_id=resolvida if isinstance(resolvida, str) and resolvida else sessao_id,
            mensagens=[_objeto(item, rota) for item in itens],
        )

    def stream_chat(
        self,
        sessao_id: str,
        mensagem: str,
        *,
        instrucao_de_sistema: str | None = None,
        opcoes_do_modelo: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[EventoSSE]:
        """Um turno em SSE: `run.started`, `assistant.delta`, `tool.*`, `assistant.completed`,
        `run.completed|failed|cancelled` e `done`.

        `instrucao_de_sistema` vai no fim do system prompt do Hermes, em toda
        requisição do turno. Mudá-la no meio de uma sessão é editar o histórico
        (cache frio e, nos modelos com histórico preservado, raciocínio
        invalidado): mande a mesma desde o primeiro turno.

        Fechar o iterador antes do `done` fecha a conexão, e o Hermes interrompe
        o turno.
        """
        if not mensagem.strip():
            raise ValueError("mensagem vazia")
        corpo: dict[str, Any] = {"message": mensagem}
        if instrucao_de_sistema is not None:
            corpo["system_message"] = instrucao_de_sistema
        if opcoes_do_modelo is not None:
            corpo["model_options"] = dict(opcoes_do_modelo)
        rota = f"{self.prefixo}/api/sessions/{_segmento(sessao_id, 'sessao_id')}/chat/stream"
        return self._stream("POST", rota, corpo=corpo)

    async def iniciar_run(
        self,
        entrada: str,
        *,
        sessao_id: str | None = None,
        instrucoes: str | None = None,
        opcoes_do_modelo: Mapping[str, Any] | None = None,
        chave_de_idempotencia: str | None = None,
    ) -> RunAceito:
        """`POST /v1/runs`: o turno roda no Hermes mesmo que ninguém esteja ouvindo."""
        if not entrada.strip():
            raise ValueError("entrada vazia")
        corpo: dict[str, Any] = {"input": entrada}
        if sessao_id is not None:
            corpo["session_id"] = sessao_id
        if instrucoes is not None:
            corpo["instructions"] = instrucoes
        if opcoes_do_modelo is not None:
            corpo["model_options"] = dict(opcoes_do_modelo)
        cabecalhos = {"Idempotency-Key": chave_de_idempotencia} if chave_de_idempotencia else None
        rota = f"{self.prefixo}/v1/runs"
        resposta = await self._pedir("POST", rota, corpo=corpo, cabecalhos=cabecalhos)
        try:
            dados = _objeto(resposta.json(), rota)
        except ValueError:
            raise RespostaInvalida(f"O Hermes respondeu {rota} com algo que não é JSON.") from None
        repetido = bool(dados.get("replayed")) or (
            resposta.headers.get("Idempotency-Replayed", "").lower() == "true"
        )
        return RunAceito(
            run_id=_texto_obrigatorio(dados.get("run_id"), "run_id", rota),
            status=str(dados.get("status") or ""),
            repetido=repetido,
        )

    async def estado_run(self, run_id: str) -> dict[str, Any]:
        """`GET /v1/runs/{id}`: status, `output` no fim, `usage` e `runtime`."""
        rota = f"{self.prefixo}/v1/runs/{_segmento(run_id, 'run_id')}"
        return _objeto(await self._json("GET", rota), rota)

    def eventos_run(self, run_id: str) -> AsyncIterator[EventoSSE]:
        """`GET /v1/runs/{id}/events`. Um assinante só: ao cair, o buffer vai embora."""
        return self._stream("GET", f"{self.prefixo}/v1/runs/{_segmento(run_id, 'run_id')}/events")

    async def parar(self, run_id: str) -> dict[str, Any]:
        """`POST /v1/runs/{id}/stop`, que também para um turno do `chat/stream`.

        Devolve `{"status": "stopping"}`, ou o estado final se o run já acabou.
        Run que não está mais ativo neste processo do Hermes dá `Conflito`.
        """
        rota = f"{self.prefixo}/v1/runs/{_segmento(run_id, 'run_id')}/stop"
        return _objeto(await self._json("POST", rota), rota)
