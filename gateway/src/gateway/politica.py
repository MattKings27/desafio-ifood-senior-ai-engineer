"""Política de acesso às ferramentas do motor: o MCP Gateway.

O agente é um programa que decide o que chamar a partir de texto, e parte desse
texto vem da internet. Expor o motor direto a ele é confiar a política de acesso
ao julgamento de um modelo. Aqui a política é determinística e fica fora do
alcance dele.

Seis camadas, de fora para dentro, na ordem de `pilha_padrao`:

    autenticação -> auditoria -> autorização -> rate limit -> quota -> breaker

Cada uma é um `ServerMiddleware` independente, testável isolado, e a ordem
importa: não faz sentido gastar quota conferindo escopo de quem nem se
autenticou, e a auditoria vem logo depois da autenticação para registrar também
o que as camadas de dentro negaram.

**Por que escopos.** As ferramentas se dividem em leitura (custo, despensa,
viabilidade) e escrita (dossiê, orçamento, decisões). O agente de conversa não
precisa de escrita em orçamento para responder "quanto custa esse prato", e
comprometer dinheiro da Dona Maria por engano é caro de desfazer. Algumas de
leitura gravam um registro do próprio servidor, como a receita candidata e a
planilha em texto, sem mexer em nada que é dela: estão listadas em
`REGISTRAM_ARTEFATO`, para o escopo não esconder que gravam.

**Trade-off assumido.** A pilha acrescenta alguns milissegundos por chamada.
Para uma decisão que envolve o dinheiro de uma pessoa real, é barato.
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Protocol

from telemetria.metricas import REGISTRO
from telemetria.rastro import identificador_do_trace, span_de_ferramenta

if TYPE_CHECKING:
    from collections.abc import Iterable


class Escopo(StrEnum):
    """O que uma credencial pode fazer."""

    LEITURA = "leitura"
    """Consultar despensa, custo, viabilidade, preço. Não muda nada."""

    ESCRITA = "escrita"
    """Gravar perfil, decisões e compras. Muda o estado da consultoria."""


#: Escopo exigido por ferramenta. Ausente = negado (allowlist, não denylist:
#: uma ferramenta nova nasce inacessível até ser classificada de propósito).
ESCOPOS: Final[dict[str, Escopo]] = {
    "diagnostico_despensa": Escopo.LEITURA,
    "custo_unitario": Escopo.LEITURA,
    "converter_medida_culinaria": Escopo.LEITURA,
    "consultar_perfil": Escopo.LEITURA,
    "proxima_pergunta": Escopo.LEITURA,
    "avaliar_receita": Escopo.LEITURA,
    "comparar_candidatas": Escopo.LEITURA,
    "calcular_cmv": Escopo.LEITURA,
    "cenarios_preco": Escopo.LEITURA,
    "testar_sensibilidade": Escopo.LEITURA,
    "consultar_orcamento": Escopo.LEITURA,
    "consultar_cardapio": Escopo.LEITURA,
    "consultar_precos_de_mercado": Escopo.LEITURA,
    "consultar_gostos": Escopo.LEITURA,
    "buscar_receita_na_web": Escopo.LEITURA,
    "buscar_preco_na_web": Escopo.LEITURA,
    "consultar_conhecimento": Escopo.LEITURA,
    "consultar_planilha": Escopo.LEITURA,
    "estimar_preco_preliminar": Escopo.LEITURA,
    "pauta_de_descoberta": Escopo.LEITURA,
    "registrar_resposta": Escopo.ESCRITA,
    "registrar_preco_mercado": Escopo.ESCRITA,
    "registrar_gosto": Escopo.ESCRITA,
    "registrar_decisao": Escopo.ESCRITA,
    "registrar_compra": Escopo.ESCRITA,
    "atualizar_despensa": Escopo.ESCRITA,
    "registrar_avaliacao_da_receita": Escopo.ESCRITA,
}

#: As ferramentas de leitura que gravam um registro produzido pelo próprio
#: servidor, sem mexer em nada que é dela.
#:
#: Leitura quer dizer que a ferramenta não muda o que é dela: a despensa, a
#: cozinha, o gosto, as decisões, as compras e os R$ 80,00. Estas gravam outra
#: coisa, e dizer que só leem seria meia verdade:
#:
#: - `buscar_receita_na_web` guarda no catálogo a receita da página que o
#:   servidor buscou (`Sessao.receita_da_web`), sem pôr em avaliação;
#: - `avaliar_receita` e `calcular_cmv` guardam como candidata a receita que
#:   avaliam (`Sessao.guardar`), inclusive quando a conferência recusa; a
#:   receita que ela dita vai também para o catálogo, como "dita";
#: - `consultar_planilha` regrava `.estado/despensa.txt`, a planilha em texto
#:   derivada do dossiê (`Sessao.atualizar_planilha_txt`);
#: - `buscar_preco_na_web` guarda o preço médio em São Paulo que o servidor
#:   procurou nos supermercados (ou que não achou), com as fontes e a prova
#:   (`mise.precos_na_web`): não é preço dela, e o dela continua valendo mais.
#:
#: O que gravam é do servidor e se refaz a cada chamada, e nada disso muda uma
#: conta dela. Por isso continuam liberadas para a credencial de leitura.
#: Ferramenta de leitura que passar a gravar entra aqui, e o teste da política
#: mostra a diferença.
REGISTRAM_ARTEFATO: Final[frozenset[str]] = frozenset(
    {
        "buscar_receita_na_web",
        "buscar_preco_na_web",
        "avaliar_receita",
        "calcular_cmv",
        "consultar_planilha",
    }
)

METODO_CHAMADA: Final = "tools/call"


class ErroDePolitica(Exception):
    """Acesso recusado pela política. Nunca vaza detalhe interno ao chamador."""

    def __init__(self, motivo: str, codigo: str, **contexto: object) -> None:
        super().__init__(motivo)
        self.motivo = motivo
        self.codigo = codigo
        self.contexto = contexto


@dataclass(frozen=True, slots=True)
class Credencial:
    """Quem está chamando e o que pode fazer."""

    identidade: str
    escopos: frozenset[Escopo]

    def pode(self, escopo: Escopo) -> bool:
        return escopo in self.escopos


class _Contexto(Protocol):
    """A parte do `ServerRequestContext` do MCP que a política usa."""

    method: str
    params: Any
    request_id: Any


CallNext = "Callable[[Any], Awaitable[Any]]"


def _nome_da_ferramenta(ctx: _Contexto) -> str | None:
    """Extrai o nome da tool de uma chamada, ou `None` se não for chamada."""
    if ctx.method != METODO_CHAMADA:
        return None
    params = ctx.params
    if isinstance(params, dict):
        nome = params.get("name")
        return nome if isinstance(nome, str) else None
    return getattr(params, "name", None)


# --------------------------------------------------------------------------- #
# 1. Autenticação
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class Autenticacao:
    """Exige um token de serviço válido.

    O token vem do ambiente, nunca do repositório. Sem token configurado o
    gateway roda em modo aberto: aceitável em desenvolvimento, e registrado
    no log de auditoria para não passar despercebido em produção.
    """

    tokens: dict[str, Credencial] = field(default_factory=dict)

    @classmethod
    def do_ambiente(cls) -> Autenticacao:
        """Lê `MISE_TOKEN_LEITURA` e `MISE_TOKEN_ESCRITA`."""
        tokens: dict[str, Credencial] = {}
        if leitura := os.environ.get("MISE_TOKEN_LEITURA"):
            tokens[leitura] = Credencial("agente-leitura", frozenset({Escopo.LEITURA}))
        if escrita := os.environ.get("MISE_TOKEN_ESCRITA"):
            tokens[escrita] = Credencial(
                "agente-escrita", frozenset({Escopo.LEITURA, Escopo.ESCRITA})
            )
        return cls(tokens)

    @property
    def aberto(self) -> bool:
        return not self.tokens

    def credencial_de(self, ctx: _Contexto) -> Credencial:
        if self.aberto:
            return Credencial("anonimo", frozenset({Escopo.LEITURA, Escopo.ESCRITA}))
        token = _token_de(ctx)
        if token is None or token not in self.tokens:
            raise ErroDePolitica(
                "credencial ausente ou inválida", "nao_autenticado", metodo=ctx.method
            )
        return self.tokens[token]

    async def __call__(self, ctx: Any, call_next: Any) -> Any:
        if _nome_da_ferramenta(ctx) is None:
            return await call_next(ctx)
        credencial = self.credencial_de(ctx)
        _CREDENCIAL_ATUAL[id(ctx)] = credencial
        try:
            return await call_next(ctx)
        finally:
            _CREDENCIAL_ATUAL.pop(id(ctx), None)


#: Credencial resolvida para o contexto em voo. Evita reautenticar em cada camada.
_CREDENCIAL_ATUAL: dict[int, Credencial] = {}


def _token_de(ctx: _Contexto) -> str | None:
    params = ctx.params
    meta = params.get("_meta") if isinstance(params, dict) else getattr(params, "meta", None)
    if isinstance(meta, dict):
        token = meta.get("mise_token")
        if isinstance(token, str):
            return token
    return os.environ.get("MISE_TOKEN")


# --------------------------------------------------------------------------- #
# 2. Autorização
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class Autorizacao:
    """Confere o escopo exigido pela ferramenta. Allowlist: desconhecido é negado."""

    escopos: dict[str, Escopo] = field(default_factory=lambda: dict(ESCOPOS))

    async def __call__(self, ctx: Any, call_next: Any) -> Any:
        nome = _nome_da_ferramenta(ctx)
        if nome is None:
            return await call_next(ctx)

        exigido = self.escopos.get(nome)
        if exigido is None:
            raise ErroDePolitica(
                f"ferramenta {nome!r} não está na allowlist da política",
                "ferramenta_desconhecida",
                ferramenta=nome,
            )
        credencial = _CREDENCIAL_ATUAL.get(id(ctx))
        if credencial is not None and not credencial.pode(exigido):
            raise ErroDePolitica(
                f"{credencial.identidade} não tem escopo {exigido.value!r} para {nome!r}",
                "escopo_insuficiente",
                ferramenta=nome,
                exigido=exigido.value,
            )
        return await call_next(ctx)


# --------------------------------------------------------------------------- #
# 3. Rate limit (token bucket)
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class RateLimit:
    """Token bucket por ferramenta.

    Protege o motor de um laço do agente, que acontece, e sem isto consome
    CPU e enche o log até alguém perceber.

    `relogio` é injetável porque política que depende de tempo precisa ser
    testável sem `sleep`: um teste que dorme é lento e, pior, intermitente.
    """

    capacidade: int = 30
    recarga_por_segundo: float = 3.0
    relogio: Callable[[], float] = time.monotonic
    _tokens: dict[str, float] = field(default_factory=dict)
    _ultimo: dict[str, float] = field(default_factory=dict)

    def _consumir(self, chave: str, agora: float) -> bool:
        anterior = self._ultimo.get(chave, agora)
        disponivel = min(
            self.capacidade,
            self._tokens.get(chave, float(self.capacidade))
            + (agora - anterior) * self.recarga_por_segundo,
        )
        self._ultimo[chave] = agora
        if disponivel < 1:
            self._tokens[chave] = disponivel
            return False
        self._tokens[chave] = disponivel - 1
        return True

    async def __call__(self, ctx: Any, call_next: Any) -> Any:
        nome = _nome_da_ferramenta(ctx)
        if nome is None:
            return await call_next(ctx)
        if not self._consumir(nome, self.relogio()):
            raise ErroDePolitica(
                f"ritmo excedido em {nome!r}; aguarde antes de repetir",
                "rate_limit",
                ferramenta=nome,
            )
        return await call_next(ctx)


# --------------------------------------------------------------------------- #
# 4. Quota
# --------------------------------------------------------------------------- #


#: Chamadas permitidas por janela, e o tamanho da janela, quando o ambiente não diz.
QUOTA_PADRAO: Final = 500
JANELA_PADRAO_MIN: Final = 60


@dataclass(slots=True)
class Quota:
    """Teto de chamadas numa janela móvel de tempo.

    Diferente do rate limit, que corta rajada por ferramenta: este olha o total
    da última hora. Existe para que um laço infinito termine com erro explícito
    em vez de rodar a noite inteira.

    Era um teto por processo, e sob o gateway do Hermes o processo do motor
    nunca reinicia: depois de 500 chamadas no total, somadas ao longo de dias,
    toda ferramenta passava a ser recusada, e a conversa e a descoberta paravam.
    Na janela móvel, o que conta é o ritmo recente, e o uso normal nunca chega
    perto do teto.

    Chamada recusada também conta: um laço que continua batendo continua
    barrado, e a janela só esvazia quando ele para. Guardar só as `maximo + 1`
    chamadas mais recentes basta, porque a decisão é sempre se a
    `(maximo + 1)`-ésima mais recente ainda está dentro da janela.

    `relogio` é injetável pelo mesmo motivo do rate limit: testar sem `sleep`.
    """

    maximo: int = QUOTA_PADRAO
    janela_segundos: float = JANELA_PADRAO_MIN * 60.0
    relogio: Callable[[], float] = time.monotonic
    _chamadas: deque[float] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.maximo < 1 or self.janela_segundos <= 0:
            raise ValueError("a quota precisa de ao menos uma chamada numa janela positiva")
        self._chamadas = deque(maxlen=self.maximo + 1)

    @classmethod
    def do_ambiente(cls, relogio: Callable[[], float] = time.monotonic) -> Quota:
        """Lê `MISE_QUOTA_CHAMADAS` e `MISE_QUOTA_JANELA_MIN`; valor inválido fica no padrão."""
        maximo = _inteiro_positivo(os.environ.get("MISE_QUOTA_CHAMADAS"), QUOTA_PADRAO)
        minutos = _inteiro_positivo(os.environ.get("MISE_QUOTA_JANELA_MIN"), JANELA_PADRAO_MIN)
        return cls(maximo=maximo, janela_segundos=minutos * 60.0, relogio=relogio)

    def _esquecer_antigas(self, agora: float) -> None:
        limite = agora - self.janela_segundos
        while self._chamadas and self._chamadas[0] <= limite:
            self._chamadas.popleft()

    @property
    def usadas(self) -> int:
        """Chamadas dentro da janela, contando as recusadas."""
        self._esquecer_antigas(self.relogio())
        return len(self._chamadas)

    async def __call__(self, ctx: Any, call_next: Any) -> Any:
        if _nome_da_ferramenta(ctx) is None:
            return await call_next(ctx)
        agora = self.relogio()
        self._esquecer_antigas(agora)
        self._chamadas.append(agora)
        if len(self._chamadas) > self.maximo:
            minutos = round(self.janela_segundos / 60)
            janela = "1 minuto" if minutos == 1 else f"{minutos} minutos"
            raise ErroDePolitica(
                f"quota de {self.maximo} chamadas em {janela} esgotada; aguarde antes de repetir",
                "quota_esgotada",
                usadas=len(self._chamadas),
            )
        return await call_next(ctx)


def _inteiro_positivo(bruto: str | None, padrao: int) -> int:
    """O número do ambiente, ou o padrão se faltar ou não for um inteiro positivo."""
    try:
        valor = int((bruto or "").strip())
    except ValueError:
        return padrao
    return valor if valor > 0 else padrao


# --------------------------------------------------------------------------- #
# 5. Circuit breaker
# --------------------------------------------------------------------------- #


class EstadoBreaker(StrEnum):
    FECHADO = "fechado"
    ABERTO = "aberto"
    MEIO_ABERTO = "meio_aberto"


@dataclass(slots=True)
class CircuitBreaker:
    """Para de chamar uma ferramenta que está falhando em sequência.

    Sem isto, uma falha persistente vira uma cascata de retentativas do agente
    contra um recurso que já se sabe quebrado.
    """

    limite_falhas: int = 5
    espera_segundos: float = 30.0
    relogio: Callable[[], float] = time.monotonic
    _falhas: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _aberto_em: dict[str, float] = field(default_factory=dict)

    def estado(self, ferramenta: str, agora: float | None = None) -> EstadoBreaker:
        agora = agora if agora is not None else self.relogio()
        abertura = self._aberto_em.get(ferramenta)
        if abertura is None:
            return EstadoBreaker.FECHADO
        if agora - abertura >= self.espera_segundos:
            return EstadoBreaker.MEIO_ABERTO
        return EstadoBreaker.ABERTO

    async def __call__(self, ctx: Any, call_next: Any) -> Any:
        nome = _nome_da_ferramenta(ctx)
        if nome is None:
            return await call_next(ctx)

        estado = self.estado(nome)
        if estado is EstadoBreaker.ABERTO:
            raise ErroDePolitica(
                f"{nome!r} falhou {self._falhas[nome]} vezes seguidas; "
                "circuito aberto temporariamente",
                "circuito_aberto",
                ferramenta=nome,
            )

        try:
            resultado = await call_next(ctx)
        except ErroDePolitica:
            raise
        except Exception:
            self._falhas[nome] += 1
            if self._falhas[nome] >= self.limite_falhas:
                self._aberto_em[nome] = self.relogio()
            raise
        else:
            self._falhas.pop(nome, None)
            self._aberto_em.pop(nome, None)
            return resultado


# --------------------------------------------------------------------------- #
# 6. Auditoria
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class Auditoria:
    """Registro append-only de toda chamada: quem, o quê, quanto tempo, resultado.

    É o que permite responder, depois, "de onde veio este número que a Dona
    Maria colocou no cardápio". Sem trilha, a explicabilidade do sistema
    depende de o modelo lembrar, que é o mesmo que não ter.
    """

    destino: Path | None = None
    memoria: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=1000))

    @classmethod
    def do_ambiente(cls) -> Auditoria:
        destino = os.environ.get("MISE_AUDITORIA")
        return cls(destino=Path(destino).expanduser() if destino else None)

    def registrar(self, evento: dict[str, Any]) -> None:
        self.memoria.append(evento)
        if self.destino is None:
            return
        self.destino.parent.mkdir(parents=True, exist_ok=True)
        with self.destino.open("a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps(evento, ensure_ascii=False, default=str) + "\n")

    async def __call__(self, ctx: Any, call_next: Any) -> Any:
        nome = _nome_da_ferramenta(ctx)
        if nome is None:
            return await call_next(ctx)

        credencial = _CREDENCIAL_ATUAL.get(id(ctx))
        identidade = credencial.identidade if credencial else "desconhecida"
        inicio = time.monotonic()
        evento: dict[str, Any] = {
            "momento": time.time(),
            "ferramenta": nome,
            "identidade": identidade,
            "request_id": str(getattr(ctx, "request_id", "")),
        }
        deu_errado = False

        # O span abre aqui, e não no motor, porque é aqui que a fronteira está:
        # tudo que o agente pede passa por este middleware. Instrumentar dentro
        # de cada ferramenta seria um lugar por ferramenta (26 hoje) para
        # esquecer um.
        with span_de_ferramenta(nome, identidade) as span:
            if identificador := identificador_do_trace():
                evento["trace_id"] = identificador
            try:
                resultado = await call_next(ctx)
            except ErroDePolitica as erro:
                deu_errado = True
                evento |= {"resultado": "negado", "codigo": erro.codigo, "motivo": erro.motivo}
                span.set_attribute("politica.codigo", erro.codigo)
                raise
            except Exception as erro:
                deu_errado = True
                evento |= {"resultado": "erro", "tipo": type(erro).__name__}
                raise
            else:
                evento["resultado"] = "ok"
                return resultado
            finally:
                duracao = round((time.monotonic() - inicio) * 1000, 2)
                evento["duracao_ms"] = duracao
                # Trilha e métrica respondem perguntas diferentes: a trilha diz o
                # que aconteceu numa chamada, a métrica diz se o sistema está bem.
                REGISTRO.registrar(nome, duracao, erro=deu_errado)
                self.registrar(evento)


# --------------------------------------------------------------------------- #
# Composição
# --------------------------------------------------------------------------- #


def pilha_padrao(
    autenticacao: Autenticacao | None = None,
    auditoria: Auditoria | None = None,
) -> list[Any]:
    """A pilha completa, na ordem correta (a primeira é a mais externa).

    Auditoria vem logo após autenticação para registrar também o que foi negado
    por escopo, rate limit ou breaker: negação é o evento mais interessante do
    log, e deixá-la de fora esconde justamente o que se quer investigar.
    """
    return [
        autenticacao or Autenticacao.do_ambiente(),
        auditoria or Auditoria.do_ambiente(),
        Autorizacao(),
        RateLimit(),
        Quota.do_ambiente(),
        CircuitBreaker(),
    ]


def escopos_de(ferramentas: Iterable[str]) -> dict[str, Escopo | None]:
    """Mapa ferramenta -> escopo exigido; `None` quando não classificada."""
    return {f: ESCOPOS.get(f) for f in ferramentas}


__all__ = [
    "ESCOPOS",
    "JANELA_PADRAO_MIN",
    "METODO_CHAMADA",
    "QUOTA_PADRAO",
    "REGISTRAM_ARTEFATO",
    "Auditoria",
    "Autenticacao",
    "Autorizacao",
    "CircuitBreaker",
    "Credencial",
    "ErroDePolitica",
    "Escopo",
    "EstadoBreaker",
    "Quota",
    "RateLimit",
    "escopos_de",
    "pilha_padrao",
]
