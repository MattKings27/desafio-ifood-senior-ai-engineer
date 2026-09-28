"""Busca de receita na web, com a resiliência que rede exige.

O §2.1 manda pesquisar receitas reais na internet. O `extrator` lê HTML; este
módulo é quem vai buscá-lo, e é onde mora todo o problema de sistema
distribuído que o resto do repositório não tem, porque o resto é determinístico e
local.

A rede não é confiável, e projetar como se fosse é a origem de quase todo
incidente. Aqui, cada chamada tem:

**Timeout explícito.** Sem ele, uma conexão pendurada trava a conversa inteira e
a Dona Maria fica olhando para um cursor.

**Retry com backoff exponencial e jitter.** Backoff porque repetir imediatamente
contra um servidor sobrecarregado piora a sobrecarga. Jitter porque sem ele todos
os clientes que falharam juntos voltam juntos: o efeito manada que transforma
uma indisponibilidade curta numa longa.

**Circuit breaker.** Depois de falhas seguidas, parar de tentar. Martelar uma
dependência que já se sabe quebrada gasta tempo dela e nosso, e atrasa a
recuperação.

**Degradação graciosa.** Sem busca, o agente não trava: ele diz que não
conseguiu procurar e pede para ela ditar a receita. Uma consultoria que só
funciona com internet é pior que uma que sabe trabalhar sem.

O `buscar` não traz resultado de motor de busca por conta própria: quem tem
`web_search` é o Hermes, e reimplementar indexação da web aqui seria absurdo. O
que este módulo faz é **buscar a página** que o agente escolheu e devolver a
receita estruturada.
"""

from __future__ import annotations

import random
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final
from urllib.parse import urlparse

from retrieval.extrator import ExtracaoFalhou, ReceitaExtraida, extrair
from retrieval.rede import DestinoProibido, abridor

#: Tempo máximo esperando uma página. Site de receita lento existe, mas acima
#: disto a conversa fica travada e é melhor tentar outro.
TIMEOUT: Final = 8.0

#: Tentativas por página, contando a primeira.
TENTATIVAS: Final = 3

#: Base do backoff exponencial, em segundos: 0,5 · 2^n.
BASE_BACKOFF: Final = 0.5

#: Teto do backoff. Sem teto, a terceira tentativa esperaria mais do que o
#: usuário aguenta.
TETO_BACKOFF: Final = 4.0

#: Falhas seguidas antes de o circuito abrir, por domínio.
FALHAS_PARA_ABRIR: Final = 3

#: Quanto o circuito fica aberto antes de deixar uma tentativa passar.
DESCANSO: Final = 30.0

#: Só HTTP e HTTPS. `file://` deixaria uma URL vinda do modelo ler disco local.
ESQUEMAS: Final[frozenset[str]] = frozenset({"http", "https"})

#: Tamanho máximo de página. Sem teto, uma resposta enorme consome memória até o
#: processo morrer, e quem controla o tamanho é o servidor remoto, não nós.
TAMANHO_MAXIMO: Final = 4 * 1024 * 1024

AGENTE: Final = "SaborDaMaria/1.0 (consultoria de cardapio; contato via repositorio)"

#: Status que vale repetir. 404 e 403 não vão melhorar tentando de novo.
STATUS_TEMPORARIOS: Final[frozenset[int]] = frozenset({408, 425, 429, 500, 502, 503, 504})


class BuscaFalhou(Exception):  # noqa: N818
    """Não foi possível trazer a página.

    Sem sufixo `Error` pelo mesmo motivo do resto do repositório: a exceção é
    nomeada pelo que aconteceu, em português.
    """


class CircuitoAberto(BuscaFalhou):
    """O domínio falhou demais e está em descanso."""


class UrlRecusada(BuscaFalhou):
    """URL que não se deve buscar. É recusa de regra, não falha de rede."""


@dataclass
class Disjuntor:
    """Circuit breaker por domínio.

    Por domínio e não global: um site de receita fora do ar não pode impedir a
    busca em todos os outros.

    `relogio` é injetável porque política que depende de tempo precisa ser
    testável sem dormir, pelo mesmo motivo do `RateLimit` no gateway.
    """

    falhas: dict[str, int] = field(default_factory=dict)
    aberto_desde: dict[str, float] = field(default_factory=dict)
    relogio: Callable[[], float] = time.monotonic

    def _agora(self) -> float:
        return self.relogio()

    def permitido(self, dominio: str) -> bool:
        desde = self.aberto_desde.get(dominio)
        if desde is None:
            return True
        if self._agora() - desde >= DESCANSO:
            # Meio-aberto: deixa uma tentativa passar para descobrir se voltou.
            del self.aberto_desde[dominio]
            self.falhas[dominio] = FALHAS_PARA_ABRIR - 1
            return True
        return False

    def registrar_falha(self, dominio: str) -> None:
        self.falhas[dominio] = self.falhas.get(dominio, 0) + 1
        if self.falhas[dominio] >= FALHAS_PARA_ABRIR:
            self.aberto_desde[dominio] = self._agora()

    def registrar_sucesso(self, dominio: str) -> None:
        self.falhas.pop(dominio, None)
        self.aberto_desde.pop(dominio, None)


def espera_com_jitter(tentativa: int, aleatorio: Callable[[], float] = random.random) -> float:
    """Backoff exponencial com jitter completo.

    `random() · min(teto, base · 2^n)`, que é o "full jitter" da AWS. Jitter
    parcial ainda deixa os clientes agrupados; o completo espalha de verdade.
    """
    limite: float = min(TETO_BACKOFF, BASE_BACKOFF * (2**tentativa))
    sorteado: float = aleatorio()
    return sorteado * limite


def validar(url: str) -> str:
    """Recusa o que não se deve buscar, antes de abrir conexão.

    A URL costuma vir do modelo, que a leu de uma página. Tratar isso como dado
    confiável é o caminho para `file:///etc/passwd` virar uma requisição.
    """
    partes = urlparse(url.strip())
    if partes.scheme not in ESQUEMAS:
        raise UrlRecusada(f"só busco http e https, não {partes.scheme or 'esquema vazio'!r}")
    if not partes.netloc or not partes.hostname:
        raise UrlRecusada("URL sem domínio")
    if "@" in partes.netloc:
        # "http://site-conhecido@10.0.0.1/" parece o site e vai para o IP.
        raise UrlRecusada("URL com usuário ou senha embutidos")
    return partes.netloc.lower()


def _baixar(url: str, abrir: urllib.request.OpenerDirector | None = None) -> str:
    """Uma tentativa. Sem retry aqui: quem repete é quem chama.

    A conexão passa por `retrieval.rede`: só endereço público, conferido na hora
    de conectar, inclusive em cada redirecionamento.
    """
    requisicao = urllib.request.Request(
        url, headers={"User-Agent": AGENTE, "Accept": "text/html,application/xhtml+xml"}
    )
    try:
        with (abrir or _ABRIDOR).open(requisicao, timeout=TIMEOUT) as resposta:
            bruto: bytes = resposta.read(TAMANHO_MAXIMO + 1)
    except urllib.error.HTTPError as erro:
        # Antes de URLError, de quem é subclasse.
        if erro.code in STATUS_TEMPORARIOS:
            raise BuscaFalhou(f"HTTP {erro.code}, temporário") from erro
        raise UrlRecusada(f"HTTP {erro.code}, não adianta repetir") from erro
    except DestinoProibido as erro:
        raise UrlRecusada(str(erro)) from erro
    except urllib.error.URLError as erro:
        # O urllib embrulha o que a conexão levanta; a recusa de endereço é
        # definitiva e não conta como falha do domínio no disjuntor.
        if isinstance(erro.reason, DestinoProibido):
            raise UrlRecusada(str(erro.reason)) from erro
        raise BuscaFalhou(f"não consegui falar com o servidor: {erro}") from erro
    except (TimeoutError, OSError) as erro:
        raise BuscaFalhou(f"não consegui falar com o servidor: {erro}") from erro

    if len(bruto) > TAMANHO_MAXIMO:
        raise UrlRecusada("página grande demais; quem controla o tamanho é o servidor remoto")
    return bruto.decode("utf-8", errors="replace")


def baixar(
    url: str,
    disjuntor: Disjuntor | None = None,
    dormir: Callable[[float], None] = time.sleep,
) -> str:
    """Traz a página, com retry, backoff, jitter e circuit breaker.

    `dormir` é injetável para o teste não esperar de verdade: um teste de backoff
    que dorme oito segundos é um teste que alguém pula.
    """
    dominio = validar(url)
    breaker = disjuntor or _DISJUNTOR

    if not breaker.permitido(dominio):
        raise CircuitoAberto(
            f"{dominio} falhou {FALHAS_PARA_ABRIR} vezes seguidas e está em descanso. "
            "Martelar agora só atrasa a recuperação dele, e a nossa."
        )

    ultima: Exception | None = None
    for tentativa in range(TENTATIVAS):
        try:
            html = _baixar(url)
        except UrlRecusada:
            # Recusa definitiva não conta como falha do domínio: 404 não é o site
            # estar fora do ar, e abrir o circuito por isso puniria o inocente.
            raise
        except BuscaFalhou as erro:
            ultima = erro
            if tentativa < TENTATIVAS - 1:
                dormir(espera_com_jitter(tentativa))
        else:
            breaker.registrar_sucesso(dominio)
            return html

    breaker.registrar_falha(dominio)
    raise BuscaFalhou(f"{TENTATIVAS} tentativas em {dominio} e nenhuma deu certo: {ultima}")


def buscar_receita(
    url: str,
    fonte: str = "",
    disjuntor: Disjuntor | None = None,
    dormir: Callable[[float], None] = time.sleep,
) -> ReceitaExtraida:
    """Traz a página e extrai a receita.

    Junta as duas metades: buscar é problema de rede, extrair é problema de dado.
    Separados em módulos porque falham por razões diferentes e o agente precisa
    dizer coisas diferentes: "não consegui acessar o site" e "esse site não
    publica a receita em formato estruturado" pedem ações diferentes dela.
    """
    return extrair(baixar(url, disjuntor, dormir), url, fonte)


#: Disjuntor do processo. Global porque o estado de um domínio quebrado é do
#: processo, não de uma requisição.
_DISJUNTOR: Final = Disjuntor()

#: O `urllib` que só conversa com endereço público.
_ABRIDOR: Final = abridor()


__all__ = [
    "BASE_BACKOFF",
    "DESCANSO",
    "FALHAS_PARA_ABRIR",
    "TENTATIVAS",
    "TIMEOUT",
    "BuscaFalhou",
    "CircuitoAberto",
    "Disjuntor",
    "ExtracaoFalhou",
    "UrlRecusada",
    "baixar",
    "buscar_receita",
    "espera_com_jitter",
    "validar",
]
