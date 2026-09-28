"""A busca híbrida no corpus da plataforma, com o "não sei" como resposta possível.

O caminho de uma pergunta:

1. **dois braços**: BM25 sobre os radicais (termo exato, nome de ingrediente,
   número) e o cosseno dos vetores (significado, ou forma de palavra quando só
   há os n-gramas). Cada um traz os 30 melhores;
2. **fusão por posição** (Reciprocal Rank Fusion, k = 60): a nota do BM25 não
   tem teto e a do cosseno vai de menos 1 a 1; somar as duas daria peso a quem tem
   escala maior. Posição não tem escala;
3. **o portão do "não sei"**: a pergunta precisa ter as palavras dela, pesadas
   pela raridade, cobertas por algum dos primeiros trechos da fusão ou da busca
   por palavra (`evidencia`). Na
   faixa do meio, só passa se o primeiro colocado se destacar do segundo
   (`margem`). Com o modelo semântico, um cosseno alto também vale como
   evidência. Os limiares foram calibrados no conjunto dourado de recuperação
   (`evals/casos/recuperacao.yaml`), e o número de cada um diz de onde veio;
4. **cada trecho precisa se sustentar**: além do portão da pergunta, um trecho
   só entra na resposta se cobrir uma parte da pergunta, para a resposta não
   completar os seis lugares com o que só se parece;
5. **diversidade** (Maximal Marginal Relevance, λ = 0,7): entre dois trechos
   quase iguais, o segundo perde lugar para um que acrescente alguma coisa;
6. **do pequeno para o grande**: o passo de uma receita volta com o cabeçalho
   dela (rendimento, fonte, situação), e dois passos da mesma receita viram um
   trecho só.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Final

from retrieval.corpus.analisador import Analisador, GrupoDaConsulta
from retrieval.corpus.modelo import TIPOS, Trecho
from retrieval.corpus.vetores import Vetorizador, cosseno
from retrieval.indice import BM25, K_RRF

#: Quantos candidatos cada braço traz antes da fusão.
CANDIDATOS: Final = 30

#: Quantos trechos a consulta devolve, se ninguém disser outro número.
K_PADRAO: Final = 6

#: O máximo que uma consulta devolve, peça quem pedir.
K_MAXIMO: Final = 12

#: O peso da relevância contra a diversidade na escolha final (MMR).
LAMBDA_MMR: Final = 0.7

#: Quantos dos primeiros colocados contam para a evidência da pergunta.
PRIMEIROS: Final = 3

#: A nota de fusão de quem vem em primeiro nos dois braços: vira pontuação 1,0.
_NOTA_MAXIMA: Final = 2 / (K_RRF + 1)


@dataclass(frozen=True, slots=True)
class Limiares:
    """Os cortes do portão do "não sei", calibrados no conjunto dourado.

    Os valores padrão são os que `python -m evals.recuperacao --calibrar` achou
    nas 57 perguntas de `evals/casos/recuperacao.yaml`, com responder o que é de
    fora custando três vezes um "não sei" a mais. As duas colunas da ablação
    escolheram os mesmos cortes lexicais; o do cosseno só vale com o modelo.
    Com eles, os n-gramas acertam a decisão entre responder e dizer "não sei" em
    55 das 57 perguntas (0,965), com revocação em 5 de 0,902 e MRR em 10 de
    0,845 (`evals/resultados/recuperacao.json`).

    A margem sobre o segundo colocado entrou na calibração e saiu em zero: neste
    conjunto ela não separou nenhuma pergunta de fora que a evidência já não
    separasse, e fechava perguntas com resposta. Ela continua no portão, com o
    corte ajustável, para quando o conjunto crescer.
    """

    #: Abaixo disto, a pergunta não é sobre a plataforma: "não sei".
    evidencia_minima: float = 0.45
    #: Acima disto, a pergunta passa sem olhar a margem.
    evidencia_segura: float = 0.6
    #: Entre as duas, o primeiro colocado precisa se destacar do segundo por isto.
    margem_minima: float = 0.0
    #: A parte da pergunta que um trecho precisa cobrir para entrar na resposta.
    cobertura_por_trecho: float = 0.4
    #: Com o modelo semântico: cosseno que vale como evidência sozinho.
    similaridade_semantica: float = 0.7


@dataclass(frozen=True, slots=True)
class Achado:
    """Um trecho que respondeu, com a nota e o texto que o agente lê."""

    trecho: Trecho
    #: De 0 a 1: 1 é o primeiro colocado nos dois braços.
    pontuacao: float
    #: O texto do trecho; o de um passo vem com o cabeçalho da receita antes.
    texto: str
    posicao_lexical: int | None
    posicao_vetorial: int | None
    #: A parte da pergunta, pesada pela raridade, que o trecho cobre.
    cobertura: float
    #: O cosseno entre a pergunta e o trecho.
    similaridade: float
    #: Os ids dos trechos que vieram juntos neste (os passos da mesma receita).
    juntos: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResultadoDaBusca:
    """O que a busca achou, ou por que disse "não sei"."""

    pergunta: str
    achados: tuple[Achado, ...]
    evidencia: float
    margem: float
    similaridade: float
    vetorizador: str
    #: Vazio quando respondeu; senão, por que se absteve.
    motivo: str = ""
    #: Os candidatos antes do portão e da diversidade, para a avaliação medir.
    candidatos: tuple[str, ...] = field(default=())

    @property
    def nada_relevante(self) -> bool:
        return not self.achados


def fundir_por_posicao(*listas: Sequence[int]) -> dict[int, float]:
    """Reciprocal Rank Fusion: cada lista soma 1 / (60 + posição) a quem está nela."""
    fundido: dict[int, float] = {}
    for lista in listas:
        for posicao, indice in enumerate(lista, start=1):
            fundido[indice] = fundido.get(indice, 0.0) + 1 / (K_RRF + posicao)
    return fundido


def escolher_com_diversidade(
    candidatos: Sequence[tuple[int, float]],
    vetores: Sequence[Sequence[float]],
    quantos: int,
    *,
    lambda_: float = LAMBDA_MMR,
    grupo: Callable[[int], str] | None = None,
) -> list[int]:
    """Maximal Marginal Relevance: relevância menos a semelhança com o que já entrou.

    `candidatos` são `(índice, relevância)` na ordem da fusão, que desempata:
    entre notas iguais, vence quem veio antes. Escolhe até `quantos` itens, ou
    até `quantos` grupos diferentes quando `grupo` diz de que grupo cada item é
    (os passos de uma receita contam como a receita).
    """
    relevancia = dict(candidatos)
    maior = max(relevancia.values(), default=0.0) or 1.0
    posicao = {i: p for p, (i, _) in enumerate(candidatos)}
    restantes = [i for i, _ in candidatos]
    escolhidos: list[int] = []
    grupos: set[str] = set()

    def contagem() -> int:
        return len(grupos) if grupo is not None else len(escolhidos)

    while restantes and contagem() < quantos:

        def nota(i: int) -> float:
            parecido = max((cosseno(vetores[i], vetores[j]) for j in escolhidos), default=0.0)
            return lambda_ * relevancia[i] / maior - (1 - lambda_) * parecido

        melhor = max(restantes, key=lambda i: (nota(i), -posicao[i]))
        escolhidos.append(melhor)
        restantes.remove(melhor)
        if grupo is not None:
            grupos.add(grupo(melhor))
    return escolhidos


@dataclass(frozen=True, slots=True)
class Candidatos:
    """O primeiro estágio da busca: os candidatos da fusão e o que foi medido de cada um.

    Não depende dos limiares do portão: a calibração mede uma vez e testa cada
    combinação de limiares no segundo estágio (`IndiceDoCorpus.decidir`).
    """

    pergunta: str
    ordem: tuple[int, ...]
    fundido: dict[int, float]
    cobertura: dict[int, float]
    semelhanca: dict[int, float]
    posicao_lexical: dict[int, int]
    posicao_vetorial: dict[int, int]
    evidencia: float
    margem: float
    similaridade: float
    vetorizador: str
    #: Por que não há candidato (pergunta sem palavra útil, filtro sem trecho).
    motivo: str = ""


class IndiceDoCorpus:
    """Os trechos da plataforma, prontos para a busca híbrida."""

    def __init__(
        self,
        trechos: Iterable[Trecho],
        analisador: Analisador,
        vetorizador: Vetorizador,
        *,
        versao: str = "",
        limiares: Limiares | None = None,
    ) -> None:
        self.trechos: tuple[Trecho, ...] = tuple(trechos)
        ids = [t.id for t in self.trechos]
        if len(ids) != len(set(ids)):
            repetidos = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"trechos com o mesmo id: {', '.join(repetidos)}")
        self.por_id = {t.id: t for t in self.trechos}
        self.analisador = analisador
        self.vetorizador = vetorizador
        self.versao = versao
        self.limiares = limiares or Limiares()
        documentos = [analisador.termos(t.indexavel) for t in self.trechos]
        self._termos = [frozenset(d) for d in documentos]
        self._bm25 = BM25(documentos)
        self._idf_maximo = math.log(1 + (len(self.trechos) + 0.5) / 0.5)
        self._vetores: list[list[float]] | None = None

    def __len__(self) -> int:
        return len(self.trechos)

    @property
    def vetores(self) -> list[list[float]]:
        """Os vetores dos trechos, calculados na primeira busca que precisar deles."""
        if self._vetores is None:
            self._vetores = self.vetorizador.vetorizar([self._vetorizavel(t) for t in self.trechos])
        return self._vetores

    def _vetorizavel(self, trecho: Trecho) -> str:
        """O que o braço vetorial lê de cada trecho.

        Com os n-gramas, o cabeçalho entra duas vezes: o cosseno não normaliza
        por tamanho como o BM25, e num trecho longo o nome do registro ("Azeite
        de oliva", "Forno") se dilui no resto. O modelo semântico recebe o
        trecho como está, com o cabeçalho uma vez só: a repetição corrige a
        contagem de n-gramas, e as medidas do modelo foram feitas assim.
        """
        if self.vetorizador.semantico:
            return trecho.indexavel
        return f"{trecho.cabecalho} {trecho.indexavel}"

    # -- sinais ------------------------------------------------------------- #

    def _peso(self, grupo: GrupoDaConsulta) -> float:
        return max(self._bm25.idf.get(r, self._idf_maximo) for r in grupo.radicais)

    def cobertura(self, grupos: Sequence[GrupoDaConsulta], indice: int) -> float:
        """A parte da pergunta, pesada pela raridade de cada palavra, que o trecho cobre."""
        total = sum(self._peso(g) for g in grupos)
        if not total:  # pragma: sem cobertura (o peso de uma palavra é sempre positivo)
            return 0.0
        termos = self._termos[indice]
        return sum(self._peso(g) for g in grupos if g.radicais & termos) / total

    # -- a busca ------------------------------------------------------------ #

    def buscar(
        self,
        pergunta: str,
        *,
        tipos: Iterable[str] | None = None,
        k: int = K_PADRAO,
        limiares: Limiares | None = None,
    ) -> ResultadoDaBusca:
        """Os trechos que respondem à pergunta, ou nada, com o porquê."""
        return self.decidir(self.candidatos(pergunta, tipos=tipos), k=k, limiares=limiares)

    def candidatos(self, pergunta: str, *, tipos: Iterable[str] | None = None) -> Candidatos:
        """Os dois braços, a fusão e os sinais de cada candidato."""
        filtro = set(tipos) if tipos is not None else None
        if filtro is not None and not filtro <= set(TIPOS):
            raise ValueError(f"tipos desconhecidos: {', '.join(sorted(filtro - set(TIPOS)))}")
        grupos = self.analisador.grupos(pergunta)
        permitidos = [i for i, t in enumerate(self.trechos) if filtro is None or t.tipo in filtro]
        if not grupos or not permitidos:
            motivo = "pergunta sem palavra útil" if not grupos else "nenhum trecho desse tipo"
            vazio: dict[int, float] = {}
            return Candidatos(
                pergunta, (), vazio, {}, {}, {}, {}, 0.0, 0.0, 0.0, self.vetorizador.nome, motivo
            )

        termos = sorted({r for g in grupos for r in g.radicais})
        notas = self._bm25.pontuar(termos)
        lexical = sorted(
            (i for i in permitidos if notas[i] > 0), key=lambda i: (-notas[i], self.trechos[i].id)
        )[:CANDIDATOS]
        vetores = self.vetores
        alvo = self.vetorizador.vetorizar([pergunta])[0]
        semelhanca = {i: cosseno(alvo, vetores[i]) for i in permitidos}
        vetorial = sorted(
            (i for i in permitidos if semelhanca[i] > 0),
            key=lambda i: (-semelhanca[i], self.trechos[i].id),
        )[:CANDIDATOS]
        fundido = fundir_por_posicao(lexical, vetorial)
        ordem = tuple(sorted(fundido, key=lambda i: (-fundido[i], self.trechos[i].id)))
        cobertura = {i: self.cobertura(grupos, i) for i in ordem}
        return Candidatos(
            pergunta=pergunta,
            ordem=ordem,
            fundido=fundido,
            cobertura=cobertura,
            semelhanca={i: semelhanca[i] for i in ordem},
            posicao_lexical={i: p for p, i in enumerate(lexical, start=1)},
            posicao_vetorial={i: p for p, i in enumerate(vetorial, start=1)},
            evidencia=max(
                (cobertura[i] for i in {*ordem[:PRIMEIROS], *lexical[:PRIMEIROS]}), default=0.0
            ),
            margem=_margem([notas[i] for i in lexical[:2]]),
            similaridade=max((semelhanca[i] for i in ordem[:PRIMEIROS]), default=0.0),
            vetorizador=self.vetorizador.nome,
        )

    def decidir(
        self, c: Candidatos, *, k: int = K_PADRAO, limiares: Limiares | None = None
    ) -> ResultadoDaBusca:
        """O portão do "não sei", o sustento de cada trecho, a diversidade e a expansão."""
        cortes = limiares or self.limiares
        quantos = max(1, min(k, K_MAXIMO))
        ids = tuple(self.trechos[i].id for i in c.ordem)

        def resultado(achados: Sequence[Achado], motivo: str) -> ResultadoDaBusca:
            return ResultadoDaBusca(
                c.pergunta,
                tuple(achados),
                c.evidencia,
                c.margem,
                c.similaridade,
                c.vetorizador,
                motivo,
                ids,
            )

        motivo = c.motivo or self._motivo_para_abster(c.evidencia, c.margem, c.similaridade, cortes)
        if motivo:
            return resultado((), motivo)
        semantico = self.vetorizador.semantico
        sustentados = [
            i
            for i in c.ordem
            if c.cobertura[i] >= cortes.cobertura_por_trecho
            or (semantico and c.semelhanca[i] >= cortes.similaridade_semantica)
        ]
        if not sustentados:
            return resultado((), "nenhum trecho cobre a pergunta")
        return resultado(self._expandir(self._escolher(c.fundido, sustentados, quantos), c), "")

    def _motivo_para_abster(
        self, evidencia: float, margem: float, similaridade: float, cortes: Limiares
    ) -> str:
        if self.vetorizador.semantico and similaridade >= cortes.similaridade_semantica:
            return ""
        if evidencia < cortes.evidencia_minima:
            return "a pergunta quase não aparece na plataforma nem na base de cozinha"
        if evidencia < cortes.evidencia_segura and margem < cortes.margem_minima:
            return "nenhum trecho se destaca como resposta"
        return ""

    def _escolher(self, fundido: dict[int, float], ordem: Sequence[int], quantos: int) -> list[int]:
        """Os trechos pela diversidade, até `quantos` receitas ou registros diferentes."""
        return escolher_com_diversidade(
            [(i, fundido[i]) for i in ordem],
            self.vetores,
            quantos,
            grupo=lambda i: self.trechos[i].pai or self.trechos[i].id,
        )

    def _expandir(self, escolhidos: Sequence[int], sinais: Candidatos) -> list[Achado]:
        """Do pequeno para o grande: cada filho volta com o pai, e irmãos viram um só."""
        por_grupo: dict[str, list[int]] = {}
        for i in escolhidos:
            chave = self.trechos[i].pai or self.trechos[i].id
            por_grupo.setdefault(chave, []).append(i)
        achados: list[Achado] = []
        for chave, membros in por_grupo.items():
            melhor = membros[0]
            trecho = self.trechos[melhor]
            pai = self.por_id.get(chave)
            filhos = sorted(
                (self.trechos[i] for i in membros if self.trechos[i].pai),
                key=lambda t: (t.ordem, t.id),
            )
            if pai is not None and filhos:
                texto = "\n".join([pai.texto, *(f.texto for f in filhos)])
            else:
                texto = trecho.texto
            achados.append(
                Achado(
                    trecho=trecho,
                    pontuacao=round(min(1.0, sinais.fundido[melhor] / _NOTA_MAXIMA), 2),
                    texto=texto,
                    posicao_lexical=sinais.posicao_lexical.get(melhor),
                    posicao_vetorial=sinais.posicao_vetorial.get(melhor),
                    cobertura=round(sinais.cobertura[melhor], 4),
                    similaridade=round(sinais.semelhanca[melhor], 4),
                    juntos=tuple(self.trechos[i].id for i in membros[1:]),
                )
            )
        return achados


def _margem(notas: Sequence[float]) -> float:
    """Quanto o primeiro colocado do BM25 se destaca do segundo, de 0 a 1."""
    if not notas or notas[0] <= 0:
        return 0.0
    if len(notas) == 1:
        return 1.0
    return (notas[0] - notas[1]) / notas[0]


__all__ = [
    "CANDIDATOS",
    "K_MAXIMO",
    "K_PADRAO",
    "LAMBDA_MMR",
    "Achado",
    "Candidatos",
    "IndiceDoCorpus",
    "Limiares",
    "ResultadoDaBusca",
    "escolher_com_diversidade",
    "fundir_por_posicao",
]
