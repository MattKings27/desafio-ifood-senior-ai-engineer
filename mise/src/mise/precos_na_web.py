"""O preço em São Paulo do que falta e não tem referência, procurado pelo servidor na hora.

O arquivo de preços de referência (`dados/precos_de_referencia.json`) cobre o
que as receitas costumam pedir. A receita nova pede o que ninguém cotou: a
"coxa e sobrecoxa de frango", o "tomate cereja". Ela não é perguntada: o
servidor procura o ingrediente pelo nome nos supermercados de São Paulo
(`retrieval.precos`, a mesma escolha determinística e a mesma rede segura), e o
que achar vira um preço de referência como os do arquivo, com as fontes e a
prova de cada uma.

- **fica guardado no dossiê** (`precos_na_web`), com a data: o que achou entra
  nas referências que o motor lê (`Sessao.referencias`), depois das do arquivo;
- **o que não achou também fica**, para não procurar de novo a cada receita:
  depois de `ESPERA_PARA_TENTAR_DE_NOVO`, a procura volta a valer;
- **tem prazo.** Quando a receita é guardada ou avaliada, a procura de tudo o
  que falta sem preço leva no máximo `PRAZO_AO_GUARDAR` segundos; o mercado
  que não respondeu fica de fora, e o que não achou fica sem preço;
- **nunca vira pergunta a ela.** Sem preço, o item fica sem preço.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, cast

from mise.referencias import PrecoDeReferencia, PrecosDeReferencia, precos_do_arquivo

if TYPE_CHECKING:
    from mise.dossie import Dossie
    from mise.viabilidade import ItemFaltante

#: Procura um ingrediente pelo nome, nas dimensões dadas, até o prazo, e
#: devolve a dimensão que achou e as fontes (`retrieval.precos.Fonte.registro`).
Pesquisador = Callable[[str, Sequence[str], float], tuple[str, list[dict[str, Any]]]]

#: A variável que desliga a procura automática ao guardar ou avaliar a receita.
VAR_PRECOS_NA_WEB: Final = "SABOR_PRECOS_NA_WEB"
#: Quanto a procura automática espera, no total, quando a receita é guardada ou avaliada.
PRAZO_AO_GUARDAR: Final = 8.0
#: Quanto a procura que o agente pede espera.
PRAZO_DA_FERRAMENTA: Final = 20.0
#: Depois de quanto tempo o que não se achou volta a ser procurado.
ESPERA_PARA_TENTAR_DE_NOVO: Final = dt.timedelta(days=1)
#: As dimensões que a procura tenta, na ordem, quando não se sabe como a receita mede.
DIMENSOES: Final = ("massa", "volume", "contagem")

ESQUEMA: Final = """
CREATE TABLE IF NOT EXISTS precos_na_web (
    chave       TEXT PRIMARY KEY,
    ingrediente TEXT NOT NULL,
    registro    TEXT NOT NULL DEFAULT '',
    buscado_em  TEXT NOT NULL
)
"""


def ligada(ambiente: dict[str, str] | None = None) -> bool:
    """A procura automática vale, a não ser que `SABOR_PRECOS_NA_WEB=desligada`."""
    import os  # noqa: PLC0415

    amb = os.environ if ambiente is None else ambiente
    return amb.get(VAR_PRECOS_NA_WEB, "").strip().casefold() != "desligada"


def _chave(nome: str) -> str:
    from mise.catalogo import chave_do_nome  # noqa: PLC0415

    return chave_do_nome(nome)


_PESQUISA_DO_PROCESSO: dict[str, Any] = {}


def _ler_do_mercado(url: str, cabecalhos: Any) -> str:  # pragma: sem cobertura (rede de verdade)
    """A leitura segura de `retrieval.precos`, procurada na hora (os testes a trocam)."""
    from retrieval import precos  # noqa: PLC0415

    return precos.ler_da_rede(url, cabecalhos)


_TRAVA = threading.Lock()


def pesquisador_da_rede() -> Pesquisador:  # pragma: sem cobertura (rede de verdade)
    """A procura nos mercados de São Paulo, com a região de cada um guardada no processo."""
    from retrieval import precos  # noqa: PLC0415

    with _TRAVA:
        pesquisa = _PESQUISA_DO_PROCESSO.get("pesquisa")
        if pesquisa is None:
            pesquisa = precos.Pesquisa(ler=_ler_do_mercado)
            _PESQUISA_DO_PROCESSO["pesquisa"] = pesquisa

    def pesquisar(
        nome: str, dimensoes: Sequence[str], prazo: float
    ) -> tuple[str, list[dict[str, Any]]]:
        dimensao, fontes = pesquisa.pelo_nome(nome, dimensoes, prazo)
        return dimensao, [f.registro() for f in fontes]

    return pesquisar


def registro_do_preco(nome: str, dimensao: str, fontes: list[dict[str, Any]]) -> dict[str, Any]:
    """O preço achado na forma do arquivo de referências, com a busca que o refaz."""
    a_peso = bool(fontes) and all(f.get("a_granel") for f in fontes)
    uma_so = all(f.get("unidade") == "un" and str(f.get("quantidade")) == "1" for f in fontes)
    embalagem = (
        "quilo" if a_peso else ("unidade" if dimensao == "contagem" and uma_so else "pacote")
    )
    return {
        "ingrediente": nome,
        "nomes": [nome],
        "embalagem": embalagem,
        "busca": {"termo": nome, "dimensao": dimensao},
        "fontes": fontes,
    }


@dataclass(frozen=True, slots=True)
class Achado:
    """O que a procura de um ingrediente deu: a referência, ou nada."""

    ingrediente: str
    referencia: PrecoDeReferencia | None
    #: A procura foi feita agora (e não lida do que foi guardado).
    agora: bool = False

    def json(self) -> dict[str, Any]:
        if self.referencia is None:
            return {
                "ingrediente": self.ingrediente,
                "achou": False,
                "texto": (
                    f"Não achei {self.ingrediente} nos supermercados de São Paulo. O item fica "
                    "sem preço; não pergunte o preço a ela."
                ),
            }
        from mise.receitas_json import referencia_json  # noqa: PLC0415

        faltante = cast("ItemFaltante", _Faltante(self.ingrediente, self.referencia))
        return {
            "ingrediente": self.ingrediente,
            "achou": True,
            **_so_o_preco(referencia_json(faltante)),
        }


@dataclass(frozen=True, slots=True)
class _Faltante:
    nome: str
    referencia: PrecoDeReferencia


def _so_o_preco(dados: dict[str, Any] | None) -> dict[str, Any]:
    return {k: v for k, v in (dados or {}).items() if k != "ingrediente"}


class PrecosNaWeb:
    """Os preços procurados pelo servidor, guardados no dossiê."""

    __slots__ = ("_dossie", "_pesquisador", "_pronto")

    def __init__(self, dossie: Dossie, pesquisador: Pesquisador | None = None) -> None:
        self._dossie = dossie
        self._pesquisador = pesquisador
        self._pronto = False

    def _garantir(self) -> None:
        if not self._pronto:
            self._dossie.garantir_esquema(ESQUEMA)
            self._pronto = True

    def _linhas(self) -> list[Any]:
        self._garantir()
        with self._dossie.cursor() as cur:
            return list(cur.execute("SELECT * FROM precos_na_web ORDER BY ingrediente"))

    def referencias(self) -> PrecosDeReferencia:
        """O que a procura achou, na forma que o motor lê."""
        registros = [json.loads(linha["registro"]) for linha in self._linhas() if linha["registro"]]
        return precos_do_arquivo(registros)

    def _guardado(self, nome: str) -> Achado | None:
        """O que já se procurou deste nome, se ainda vale; `None` para procurar de novo."""
        self._garantir()
        with self._dossie.cursor() as cur:
            linha = cur.execute(
                "SELECT * FROM precos_na_web WHERE chave = ?", (_chave(nome),)
            ).fetchone()
        if linha is None:
            return None
        if linha["registro"]:
            lido = precos_do_arquivo([json.loads(linha["registro"])])
            return Achado(nome, lido.precos[0] if lido.precos else None)
        quando = dt.datetime.fromisoformat(linha["buscado_em"])
        if self._dossie.agora() - quando >= ESPERA_PARA_TENTAR_DE_NOVO:
            return None
        return Achado(nome, None)

    def _guardar(self, nome: str, registro: dict[str, Any] | None) -> None:
        texto = json.dumps(registro, ensure_ascii=False) if registro else ""
        self._garantir()
        with self._dossie.transacao() as cur:
            cur.execute(
                "INSERT INTO precos_na_web (chave, ingrediente, registro, buscado_em) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(chave) DO UPDATE SET "
                "ingrediente = excluded.ingrediente, registro = excluded.registro, "
                "buscado_em = excluded.buscado_em",
                (_chave(nome), nome, texto, self._dossie.agora().isoformat()),
            )

    def procurar(
        self, nome: str, dimensoes: Sequence[str] = DIMENSOES, prazo: float = PRAZO_DA_FERRAMENTA
    ) -> Achado:
        """O preço médio em São Paulo deste ingrediente: o guardado, ou procurado agora."""
        nome = " ".join(nome.split())
        guardado = self._guardado(nome)
        if guardado is not None:
            return guardado
        pesquisar = self._pesquisador or pesquisador_da_rede()
        try:
            dimensao, fontes = pesquisar(nome, dimensoes, prazo)
        except Exception:  # falha de rede ou de mercado: o item fica sem preço
            dimensao, fontes = dimensoes[0], []
        registro = registro_do_preco(nome, dimensao, fontes) if fontes else None
        lido = precos_do_arquivo([registro]) if registro else PrecosDeReferencia()
        self._guardar(nome, registro if lido else None)
        return Achado(nome, lido.precos[0] if lido.precos else None, agora=True)

    def procurar_varios(
        self, pedidos: Sequence[tuple[str, Sequence[str]]], prazo: float = PRAZO_AO_GUARDAR
    ) -> list[Achado]:
        """Vários ingredientes ao mesmo tempo, com um prazo só para todos."""
        from concurrent.futures import ThreadPoolExecutor, wait  # noqa: PLC0415

        if not pedidos:
            return []
        executor = ThreadPoolExecutor(max_workers=min(4, len(pedidos)))
        futuros = [executor.submit(self.procurar, nome, dims, prazo) for nome, dims in pedidos]
        feitos, _ = wait(futuros, timeout=prazo + 1)
        executor.shutdown(wait=False, cancel_futures=True)
        return [f.result() for f in futuros if f in feitos]


__all__ = [
    "DIMENSOES",
    "ESPERA_PARA_TENTAR_DE_NOVO",
    "PRAZO_AO_GUARDAR",
    "PRAZO_DA_FERRAMENTA",
    "VAR_PRECOS_NA_WEB",
    "Achado",
    "Pesquisador",
    "PrecosNaWeb",
    "ligada",
    "pesquisador_da_rede",
    "registro_do_preco",
]
