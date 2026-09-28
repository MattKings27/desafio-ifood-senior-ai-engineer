"""A avaliação que ela faz de cada receita: se gosta, as estrelas, as notas e a pontuação.

São três coisas dela sobre um prato, e cada uma mora num lugar só:

- **se gosta de fazer** é a checagem de gosto da conferência, e mora na tabela
  `gostos` do dossiê, pelo nome do prato. Avaliar a receita escreve lá; a
  avaliação lê de lá. Não há uma segunda cópia do gosto que possa discordar da
  primeira.
- **as estrelas**, de 1 a 5, em sabor, facilidade, tempo, "aguenta a entrega" e
  "apelo de venda", e **as notas** moram aqui, na tabela `avaliacoes`, pelo
  `receita_id`.
- **a pontuação** não mora em lugar nenhum: é calculada na leitura, em Decimal,
  com a conta escrita.

A pontuação vai de 0 a 100. Cada estrela vira uma nota de 0 a 1 ((n − 1) ÷ 4),
e as notas se juntam pela média ponderada das categorias que ela avaliou (pesos
sabor 0,30, apelo de venda 0,25, aguenta a entrega 0,20, facilidade 0,15,
tempo 0,10). O gosto entra à parte: vale 1 quando ela gosta de fazer, 0,5
quando ainda não disse e 0 quando não gosta. Pontuação = 100 × (0,75 × nota +
0,25 × gosto), com uma casa. Sem estrela nenhuma, não há pontuação.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from mise.erros import ErroDeUso

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mise.dossie import Dossie

#: As cinco categorias, na ordem em que a tela mostra.
CATEGORIAS: Final = ("sabor", "facilidade", "tempo", "entrega", "apelo")

#: O peso de cada categoria na nota. Somam 1.
PESOS: Final[Mapping[str, Decimal]] = MappingProxyType(
    {
        "sabor": Decimal("0.30"),
        "apelo": Decimal("0.25"),
        "entrega": Decimal("0.20"),
        "facilidade": Decimal("0.15"),
        "tempo": Decimal("0.10"),
    }
)

#: A ordem em que a conta é escrita: do peso maior para o menor.
ORDEM_DA_CONTA: Final = ("sabor", "apelo", "entrega", "facilidade", "tempo")

#: Como cada categoria se diz na conta escrita para ela.
NA_CONTA: Final[Mapping[str, str]] = MappingProxyType(
    {
        "sabor": "sabor",
        "apelo": "apelo de venda",
        "entrega": "aguenta a entrega",
        "facilidade": "facilidade",
        "tempo": "tempo",
    }
)

#: Como cada categoria aparece na tela.
NA_TELA: Final[Mapping[str, str]] = MappingProxyType(
    {
        "sabor": "Sabor",
        "facilidade": "Facilidade de preparo",
        "tempo": "Tempo de preparo",
        "entrega": "Aguenta a entrega",
        "apelo": "Apelo de venda",
    }
)

MENOR_ESTRELA: Final = 1
MAIOR_ESTRELA: Final = 5

#: O peso da nota das estrelas e o do gosto na pontuação.
PESO_DA_NOTA: Final = Decimal("0.75")
PESO_DO_GOSTO: Final = Decimal("0.25")

#: Quanto o gosto vale: gosta, não disse, não gosta.
VALOR_DO_GOSTO: Final[Mapping[bool | None, Decimal]] = MappingProxyType(
    {True: Decimal(1), None: Decimal("0.5"), False: Decimal(0)}
)

#: As notas cabem numa folha de caderno, não num livro.
TAMANHO_DAS_NOTAS: Final = 2000

ESQUEMA_DAS_AVALIACOES: Final = """
CREATE TABLE IF NOT EXISTS avaliacoes (
    receita_id    TEXT PRIMARY KEY,
    sabor         INTEGER CHECK (sabor BETWEEN 1 AND 5),
    facilidade    INTEGER CHECK (facilidade BETWEEN 1 AND 5),
    tempo         INTEGER CHECK (tempo BETWEEN 1 AND 5),
    entrega       INTEGER CHECK (entrega BETWEEN 1 AND 5),
    apelo         INTEGER CHECK (apelo BETWEEN 1 AND 5),
    notas         TEXT NOT NULL DEFAULT '',
    atualizada_em TEXT NOT NULL
);
"""

#: Casas da nota escrita na conta: a nota exata é usada na pontuação.
_CASAS_DA_NOTA: Final = Decimal("0.0001")
_UMA_CASA: Final = Decimal("0.1")


# --------------------------------------------------------------------------- #
# A pontuação
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Pontuacao:
    """A pontuação de 0 a 100, com a conta escrita para ela."""

    valor: Decimal
    derivacao: str

    @property
    def texto(self) -> str:
        """ "87,8", "90,0": sempre com uma casa, como a pontuação é arredondada."""
        return _uma_casa(self.valor)


def _uma_casa(valor: Decimal) -> str:
    return f"{valor.quantize(_UMA_CASA, rounding=ROUND_HALF_UP):f}".replace(".", ",")


def _decimal_br(valor: Decimal) -> str:
    """ "87,8", "0,8375": como se escreve no Brasil, sem zeros sobrando."""
    n = valor.normalize()
    if n == n.to_integral_value():
        return str(n.quantize(Decimal(1)))
    return f"{n:f}".replace(".", ",")


def _gosto_na_conta(gosta: bool | None) -> str:
    if gosta is True:
        return "a senhora gosta de fazer, que vale 1"
    if gosta is False:
        return "a senhora não gosta de fazer, que vale 0"
    return "a senhora ainda não disse se gosta de fazer, que vale 0,5"


def pontuar(estrelas: Mapping[str, int | None], gosta: bool | None) -> Pontuacao | None:
    """A pontuação das estrelas e do gosto, com a conta; `None` sem estrela nenhuma."""
    dadas = {c: estrelas[c] for c in ORDEM_DA_CONTA if estrelas.get(c) is not None}
    if not dadas:
        return None
    soma_dos_pesos = sum((PESOS[c] for c in dadas), Decimal(0))
    ponderada = sum(
        (PESOS[c] * (Decimal(n) - 1) / 4 for c, n in dadas.items() if n is not None), Decimal(0)
    )
    nota = ponderada / soma_dos_pesos
    g = VALOR_DO_GOSTO[gosta]
    valor = (100 * (PESO_DA_NOTA * nota + PESO_DO_GOSTO * g)).quantize(
        _UMA_CASA, rounding=ROUND_HALF_UP
    )
    escrita = nota.quantize(_CASAS_DA_NOTA, rounding=ROUND_HALF_UP)
    nota_texto = _decimal_br(escrita)
    if escrita != nota:
        nota_texto = f"cerca de {nota_texto}"
    partes = [
        f"{NA_CONTA[c]} {n} ({'peso ' if i == 0 else ''}{f'{PESOS[c]:.2f}'.replace('.', ',')})"
        for i, (c, n) in enumerate(dadas.items())
    ]
    so_as_dadas = "" if len(dadas) == len(CATEGORIAS) else " (contam só as que a senhora deu)"
    derivacao = (
        f"Estrelas: {', '.join(partes)}, dão {nota_texto} de 1{so_as_dadas}; "
        f"{_gosto_na_conta(gosta)}; pontuação = 100 × (0,75 × {_decimal_br(escrita)} + "
        f"0,25 × {_decimal_br(g)}) = {_uma_casa(valor)}"
    )
    return Pontuacao(valor=valor, derivacao=derivacao)


# --------------------------------------------------------------------------- #
# O que ela deu: estrelas e notas
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class EstrelasENotas:
    """As estrelas e as notas dela sobre uma receita, como estão gravadas."""

    receita_id: str
    estrelas: Mapping[str, int | None]
    notas: str = ""
    atualizada_em: datetime | None = None

    @property
    def avaliada(self) -> bool:
        """Ela deu pelo menos uma estrela."""
        return any(v is not None for v in self.estrelas.values())


def sem_estrelas(receita_id: str) -> EstrelasENotas:
    return EstrelasENotas(receita_id, dict.fromkeys(CATEGORIAS))


def conferir_estrelas(estrelas: Mapping[str, object]) -> dict[str, int | None]:
    """As estrelas que vieram, conferidas: categoria conhecida, inteiro de 1 a 5 ou `None`."""
    conferidas: dict[str, int | None] = {}
    for categoria, valor in estrelas.items():
        if categoria not in PESOS:
            raise ErroDeUso(
                f"não conheço a categoria {categoria!r}",
                validas=", ".join(CATEGORIAS),
            )
        if valor is None:
            conferidas[categoria] = None
            continue
        if isinstance(valor, bool) or not isinstance(valor, int):
            raise ErroDeUso(f"a estrela de {categoria} tem que ser um número inteiro de 1 a 5")
        if not MENOR_ESTRELA <= valor <= MAIOR_ESTRELA:
            raise ErroDeUso(f"a estrela de {categoria} vai de 1 a 5, e veio {valor}")
        conferidas[categoria] = valor
    return conferidas


class Avaliacoes:
    """As estrelas e as notas dela, por `receita_id`, sobre o dossiê."""

    __slots__ = ("_dossie", "_pronto")

    def __init__(self, dossie: Dossie) -> None:
        self._dossie = dossie
        self._pronto = False

    def _garantir(self) -> None:
        if not self._pronto:
            self._dossie.garantir_esquema(ESQUEMA_DAS_AVALIACOES)
            self._pronto = True

    def obter(self, receita_id: str) -> EstrelasENotas:
        """As estrelas e as notas da receita; sem nada gravado, tudo vazio."""
        self._garantir()
        with self._dossie.cursor() as cur:
            linha = cur.execute(
                "SELECT * FROM avaliacoes WHERE receita_id = ?", (receita_id,)
            ).fetchone()
        if linha is None:
            return sem_estrelas(receita_id)
        return EstrelasENotas(
            receita_id=receita_id,
            estrelas={c: linha[c] for c in CATEGORIAS},
            notas=linha["notas"],
            atualizada_em=datetime.fromisoformat(linha["atualizada_em"]),
        )

    def todas(self) -> dict[str, EstrelasENotas]:
        """Todas as avaliações gravadas, pelo `receita_id`."""
        self._garantir()
        with self._dossie.cursor() as cur:
            linhas = cur.execute("SELECT * FROM avaliacoes").fetchall()
        return {
            linha["receita_id"]: EstrelasENotas(
                receita_id=linha["receita_id"],
                estrelas={c: linha[c] for c in CATEGORIAS},
                notas=linha["notas"],
                atualizada_em=datetime.fromisoformat(linha["atualizada_em"]),
            )
            for linha in linhas
        }

    def gravar(
        self,
        receita_id: str,
        *,
        estrelas: Mapping[str, int | None] | None = None,
        notas: str | None = None,
    ) -> EstrelasENotas:
        """Grava só o que mudou: as estrelas que vieram (`None` apaga) e as notas, se vieram."""
        self._garantir()
        mudancas = conferir_estrelas(estrelas or {})
        if notas is not None and len(notas) > TAMANHO_DAS_NOTAS:
            raise ErroDeUso(f"as notas cabem em até {TAMANHO_DAS_NOTAS} letras")
        atual = self.obter(receita_id)
        novas = {**atual.estrelas, **mudancas}
        texto = atual.notas if notas is None else notas.strip()
        agora = self._dossie.agora().isoformat()
        with self._dossie.transacao() as cur:
            cur.execute(
                "INSERT INTO avaliacoes (receita_id, sabor, facilidade, tempo, entrega, apelo, "
                "notas, atualizada_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(receita_id) DO UPDATE SET sabor = excluded.sabor, "
                "facilidade = excluded.facilidade, tempo = excluded.tempo, "
                "entrega = excluded.entrega, apelo = excluded.apelo, notas = excluded.notas, "
                "atualizada_em = excluded.atualizada_em",
                (receita_id, *(novas[c] for c in CATEGORIAS), texto, agora),
            )
        return self.obter(receita_id)


__all__ = [
    "CATEGORIAS",
    "ESQUEMA_DAS_AVALIACOES",
    "MAIOR_ESTRELA",
    "MENOR_ESTRELA",
    "NA_CONTA",
    "NA_TELA",
    "ORDEM_DA_CONTA",
    "PESOS",
    "PESO_DA_NOTA",
    "PESO_DO_GOSTO",
    "TAMANHO_DAS_NOTAS",
    "VALOR_DO_GOSTO",
    "Avaliacoes",
    "EstrelasENotas",
    "Pontuacao",
    "conferir_estrelas",
    "pontuar",
    "sem_estrelas",
]
