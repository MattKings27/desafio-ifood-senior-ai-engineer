"""O conjunto dourado da busca: acha o trecho certo, e diz "não sei" quando deve?

`python -m evals.recuperacao` (ou `make evals-recuperacao`) monta a plataforma
num estado de referência, sempre o mesmo (a planilha dela, uma cozinha com
respostas pela tela e pela conversa, quatro receitas em avaliação, uma decisão,
uma compra, um preço e o leite que acabou), faz as perguntas de
`evals/casos/recuperacao.yaml` e mede:

- **revocação em 5**: dos trechos esperados, quantos vêm entre os 5 primeiros;
- **MRR em 10**: o inverso da posição do primeiro trecho certo;
- **nDCG em 10**: a ordem inteira, com ganho binário;
- **acerto de abstenção**: pergunta de fora abstém, pergunta com resposta não;
- **latência** por pergunta (mediana e percentil 95), com o índice já montado.

A ablação mede o mesmo conjunto com os dois braços vetoriais: os n-gramas com
hash (determinísticos, os do CI) e o modelo multilíngue, quando ele está
instalado e baixado (`retrieval[semantico]`). Sem o modelo, a coluna dele diz
que ele não está disponível, e nada é inventado no lugar.

Um trecho esperado conta como achado quando é o próprio achado, veio junto com
ele (os passos da mesma receita) ou é o pai dele: a resposta traz o cabeçalho
da receita junto com o passo.

`--calibrar` procura os limiares do portão do "não sei" que acertam mais
abstenções sem perder revocação, e mostra o resultado; os valores escolhidos
ficam em `retrieval.corpus.busca.Limiares`, com a medição ao lado.
"""

from __future__ import annotations

import argparse
import importlib.util
import itertools
import json
import math
import statistics
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import yaml
from mise import perfil_historico
from mise.catalogo import Catalogo, OrigemNoCatalogo, PaginaLida
from mise.corpus import analisador_da_plataforma, carimbo, montar_trechos
from mise.despensa import carregar_despensa
from mise.dinheiro import Dinheiro
from mise.dossie import Canal, Decisao, Dossie, OrigemPreco
from mise.mcp_server import ReceitaEntrada, Sessao
from mise.perfil import Gosto, Posse
from mise.perfil_historico import TipoDeItem
from mise.receita import Origem
from retrieval.corpus import IndiceDoCorpus, Limiares
from retrieval.corpus.vetores import CacheDeVetores, ComCache, NGramas, vetorizador_padrao

if TYPE_CHECKING:
    from retrieval.corpus import Candidatos, ResultadoDaBusca
    from retrieval.corpus.vetores import Vetorizador

RAIZ: Final = Path(__file__).resolve().parents[3]
CASOS: Final = RAIZ / "evals" / "casos" / "recuperacao.yaml"
PLANILHA: Final = RAIZ / "dados" / "despensa_dona_maria.xlsx"
ESTADO: Final = RAIZ / ".estado"

#: O relógio do estado de referência: toda data dos trechos sai dele.
AGORA: Final = datetime(2026, 9, 25, 13, 0, tzinfo=UTC)

#: O que a busca devolve para as métricas de ordem.
PROFUNDIDADE: Final = 10

#: Quanto custa, na calibração, responder o que é de fora, contra um "não sei" a mais.
CUSTO_DA_RESPOSTA_ERRADA: Final = 3

#: O piso do CI, com os n-gramas: abaixo disso a busca piorou. Fica um pouco abaixo
#: do medido (`evals/resultados/recuperacao.json`), para reprovar regressão e não
#: o arredondamento.
PISO: Final[dict[str, float]] = {
    "revocacao_5": 0.88,
    "mrr_10": 0.82,
    "ndcg_10": 0.82,
    "acerto_abstencao": 0.94,
}


# --------------------------------------------------------------------------- #
# Os casos
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Caso:
    """Uma pergunta e os trechos que respondem a ela; nenhum, se ela é de fora."""

    id: str
    pergunta: str
    esperados: tuple[str, ...]
    tipos: tuple[str, ...] | None = None
    nota: str = ""
    #: Um erro que o conjunto já conhece e a nota explica: o teste não reprova por ele.
    conhecido: bool = False

    @property
    def abster(self) -> bool:
        return not self.esperados


def carregar_casos(caminho: Path = CASOS) -> list[Caso]:
    bruto = yaml.safe_load(caminho.read_text("utf-8"))
    casos = [
        Caso(
            id=str(c["id"]),
            pergunta=str(c["pergunta"]),
            esperados=tuple(c.get("esperados") or ()),
            tipos=tuple(c["tipos"]) if c.get("tipos") else None,
            nota=" ".join(str(c.get("nota", "")).split()),
            conhecido=bool(c.get("conhecido", False)),
        )
        for c in bruto
    ]
    ids = [c.id for c in casos]
    if len(ids) != len(set(ids)):
        raise ValueError("casos com o mesmo id")
    return casos


# --------------------------------------------------------------------------- #
# O estado de referência
# --------------------------------------------------------------------------- #

ARROZ: Final[dict[str, Any]] = {
    "nome": "Arroz com frango",
    "rendimento_porcoes": 4,
    "tempo_cozimento_min": 40,
    "modo_preparo": ["Refogue a cebola.", "Junte o frango e o arroz e cozinhe na panela."],
    "ingredientes": [
        {"texto": "500 g de frango", "nome": "peito de frango", "quantidade": 500, "medida": "g"},
        {"texto": "1 kg de arroz", "nome": "arroz", "quantidade": 1, "medida": "kg"},
        {"texto": "sal a gosto", "nome": "sal"},
    ],
}

BOLO: Final[dict[str, Any]] = {
    "nome": "Bolo de fubá",
    "rendimento_porcoes": 8,
    "modo_preparo": ["Bata tudo no liquidificador por 3 minutos.", "Leve ao forno por 40 minutos."],
    "url": "https://www.tudogostoso.com.br/receita/123-bolo-de-fuba",
    "fonte": "TudoGostoso",
    "ingredientes": [
        {"texto": "2 xícaras de fubá", "nome": "fubá", "quantidade": 2, "medida": "xicara"},
        {
            "texto": "1 xícara de coco ralado",
            "nome": "coco ralado",
            "quantidade": 1,
            "medida": "xicara",
        },
    ],
}

XADREZ: Final[dict[str, Any]] = {
    "nome": "Frango xadrez",
    "rendimento_porcoes": 4,
    "modo_preparo": [
        "Corte o frango em cubos e tempere com sal e alho.",
        "Aqueça o óleo na frigideira e doure o frango por 10 minutos.",
        "Junte a cebola e o pimentão e refogue por 5 minutos.",
        "Acrescente o shoyu e a água e cozinhe por 5 minutos.",
        "Engrosse o molho com amido de milho.",
        "Junte o amendoim e misture.",
        "Sirva com arroz branco.",
    ],
    "ingredientes": [
        {"texto": "500 g de frango", "nome": "peito de frango", "quantidade": 500, "medida": "g"},
        {"texto": "1 cebola", "nome": "cebola", "quantidade": 1, "medida": "unidade"},
        {
            "texto": "3 colheres de shoyu",
            "nome": "shoyu",
            "quantidade": 3,
            "medida": "colher de sopa",
        },
        {"texto": "50 g de amendoim", "nome": "amendoim", "quantidade": 50, "medida": "g"},
        {"texto": "sal a gosto", "nome": "sal"},
    ],
}

PUDIM: Final[dict[str, Any]] = {
    "nome": "Pudim de leite",
    "rendimento_porcoes": 10,
    "modo_preparo": [
        "Bata os ovos, o leite e o açúcar no liquidificador por 3 minutos.",
        "Derreta o açúcar na panela até virar calda.",
        "Despeje na forma e asse em banho-maria no forno por 50 minutos.",
        "Leve à geladeira por 4 horas antes de desenformar.",
    ],
    "ingredientes": [
        {"texto": "4 ovos", "nome": "ovos", "quantidade": 4, "medida": "unidade"},
        {"texto": "500 ml de leite", "nome": "leite integral", "quantidade": 500, "medida": "ml"},
        {"texto": "200 g de açúcar", "nome": "açúcar", "quantidade": 200, "medida": "g"},
    ],
}


def montar_estado(pasta: Path) -> Sessao:
    """A plataforma no estado de referência, com o relógio parado em `AGORA`."""
    dossie = Dossie(pasta / "dossie.db", relogio=lambda: AGORA)
    sessao = Sessao(planilha=carregar_despensa(PLANILHA), dossie=dossie)
    for tipo, campo, posse, canal in (
        (TipoDeItem.EQUIPAMENTO, "forno", Posse.TEM, Canal.TELA),
        (TipoDeItem.EQUIPAMENTO, "air_fryer", Posse.NAO_TEM, Canal.CONVERSA),
        (TipoDeItem.EQUIPAMENTO, "batedeira", None, Canal.CONVERSA),
        (TipoDeItem.TECNICA, "massa_fresca", Posse.TEM, Canal.CONVERSA),
    ):
        perfil_historico.mudar_item(dossie, tipo, campo, posse, canal)
    for campo, valor, canal in (
        ("bocas_fogao", 4, Canal.TELA),
        ("tempo_max_por_fornada_min", 120, Canal.CONVERSA),
        ("tem_gas_sobrando", True, Canal.TELA),
    ):
        perfil_historico.mudar_restricao(dossie, campo, valor, canal)
    for receita in (ARROZ, XADREZ, PUDIM):
        sessao.guardar(ReceitaEntrada(**receita).para_dominio())
    bolo = replace(
        ReceitaEntrada(
            **{k: v for k, v in BOLO.items() if k not in ("url", "fonte")}
        ).para_dominio(),
        url=BOLO["url"],
        fonte=BOLO["fonte"],
        origem=Origem.WEB,
    )
    Catalogo(dossie).guardar_da_web(
        PaginaLida(bolo, site=BOLO["fonte"]), OrigemNoCatalogo.DESCOBERTA
    )
    sessao.guardar(bolo)
    dossie.registrar_gosto("Arroz com frango", Gosto.GOSTA)
    dossie.registrar_gosto("Pudim de leite", Gosto.GOSTA, "preciso de uma forma de pudim")
    dossie.registrar_decisao("Arroz com frango", Decisao.ADIADO, canal=Canal.TELA)
    dossie.registrar_decisao(
        "Arroz com frango", Decisao.ACEITO, detalhes={"preco": "R$ 18,00"}, canal=Canal.TELA
    )
    dossie.registrar_compra(
        "coco ralado", Decimal(100), "g", Dinheiro.de("6.00"), "Coco ralado, 100 g"
    )
    dossie.registrar_preco(
        "amendoim", Dinheiro.de("8.00"), OrigemPreco.INFORMADO_POR_ELA, Decimal(200), "g"
    )
    sessao.mudar_despensa(lambda editavel: editavel.acabou("leite-integral"))
    return sessao


def montar_indice(sessao: Sessao, vetorizador: Vetorizador) -> IndiceDoCorpus:
    return IndiceDoCorpus(
        montar_trechos(sessao), analisador_da_plataforma(), vetorizador, versao=carimbo(sessao)
    )


# --------------------------------------------------------------------------- #
# As métricas
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Resposta:
    """O que a busca devolveu para um caso."""

    caso: Caso
    ids: tuple[frozenset[str], ...]
    motivo: str
    ms: float
    evidencia: float
    margem: float
    similaridade: float

    @property
    def absteve(self) -> bool:
        return not self.ids

    def posicao(self, esperado: str) -> int | None:
        return next((p for p, ids in enumerate(self.ids, start=1) if esperado in ids), None)


def _ids_do_achado(resultado: ResultadoDaBusca) -> tuple[frozenset[str], ...]:
    ids: list[frozenset[str]] = []
    for achado in resultado.achados:
        pai = achado.trecho.pai
        ids.append(frozenset({achado.trecho.id, *achado.juntos, *([pai] if pai else [])}))
    return tuple(ids)


def revocacao(respostas: Sequence[Resposta], k: int = 5) -> float:
    medidas = [
        sum(1 for e in r.caso.esperados if (p := r.posicao(e)) is not None and p <= k)
        / len(r.caso.esperados)
        for r in respostas
        if not r.caso.abster
    ]
    return statistics.fmean(medidas) if medidas else 0.0


def mrr(respostas: Sequence[Resposta], k: int = PROFUNDIDADE) -> float:
    medidas: list[float] = []
    for r in respostas:
        if r.caso.abster:
            continue
        posicoes = [p for e in r.caso.esperados if (p := r.posicao(e)) is not None and p <= k]
        medidas.append(1 / min(posicoes) if posicoes else 0.0)
    return statistics.fmean(medidas) if medidas else 0.0


def ndcg(respostas: Sequence[Resposta], k: int = PROFUNDIDADE) -> float:
    medidas: list[float] = []
    for r in respostas:
        if r.caso.abster:
            continue
        ganhos = [1.0 if any(e in ids for e in r.caso.esperados) else 0.0 for ids in r.ids[:k]]
        dcg = sum(g / math.log2(p + 1) for p, g in enumerate(ganhos, start=1))
        ideal = sum(1 / math.log2(p + 1) for p in range(1, min(k, len(r.caso.esperados)) + 1))
        medidas.append(dcg / ideal if ideal else 0.0)
    return statistics.fmean(medidas) if medidas else 0.0


def acerto_de_abstencao(respostas: Sequence[Resposta]) -> float:
    if not respostas:
        return 0.0
    return sum(1 for r in respostas if r.absteve == r.caso.abster) / len(respostas)


def _percentil(valores: Sequence[float], p: float) -> float:
    ordenados = sorted(valores)
    if not ordenados:
        return 0.0
    posicao = min(len(ordenados) - 1, max(0, math.ceil(p * len(ordenados)) - 1))
    return ordenados[posicao]


@dataclass(frozen=True, slots=True)
class Relatorio:
    """As métricas de uma rodada, com o vetorizador que ela usou."""

    vetorizador: str
    casos: int
    revocacao_5: float
    mrr_10: float
    ndcg_10: float
    acerto_abstencao: float
    latencia_p50_ms: float
    latencia_p95_ms: float
    erros: tuple[str, ...] = field(default=())

    def dentro_do_piso(self) -> list[str]:
        """As métricas abaixo do piso do CI; vazio quando está tudo certo."""
        return [
            f"{nome} {getattr(self, nome):.3f} < {piso:.2f}"
            for nome, piso in PISO.items()
            if getattr(self, nome) < piso
        ]


def relatorio(nome: str, respostas: Sequence[Resposta]) -> Relatorio:
    erros: list[str] = []
    for r in respostas:
        if r.absteve != r.caso.abster:
            erros.append(
                f"{r.caso.id}: {'absteve' if r.absteve else 'respondeu'} "
                f"(evidência {r.evidencia:.2f}, margem {r.margem:.2f})"
            )
        elif not r.caso.abster and all(r.posicao(e) is None for e in r.caso.esperados):
            erros.append(f"{r.caso.id}: nenhum trecho esperado nos primeiros {PROFUNDIDADE}")
    latencias = [r.ms for r in respostas]
    return Relatorio(
        vetorizador=nome,
        casos=len(respostas),
        revocacao_5=round(revocacao(respostas), 4),
        mrr_10=round(mrr(respostas), 4),
        ndcg_10=round(ndcg(respostas), 4),
        acerto_abstencao=round(acerto_de_abstencao(respostas), 4),
        latencia_p50_ms=round(statistics.median(latencias), 2) if latencias else 0.0,
        latencia_p95_ms=round(_percentil(latencias, 0.95), 2),
        erros=tuple(erros),
    )


# --------------------------------------------------------------------------- #
# As rodadas
# --------------------------------------------------------------------------- #


def perguntar(
    indice: IndiceDoCorpus, casos: Sequence[Caso], limiares: Limiares | None = None
) -> list[Resposta]:
    """Cada caso pela busca inteira, com o tempo de cada pergunta."""
    respostas: list[Resposta] = []
    for caso in casos:
        inicio = time.perf_counter()
        resultado = indice.buscar(
            caso.pergunta, tipos=caso.tipos, k=PROFUNDIDADE, limiares=limiares
        )
        ms = (time.perf_counter() - inicio) * 1000
        respostas.append(
            Resposta(
                caso,
                _ids_do_achado(resultado),
                resultado.motivo,
                ms,
                resultado.evidencia,
                resultado.margem,
                resultado.similaridade,
            )
        )
    return respostas


def rodar(
    sessao: Sessao, vetorizador: Vetorizador, casos: Sequence[Caso]
) -> tuple[Relatorio, list[Resposta]]:
    """Uma rodada: monta o índice (fora do tempo medido) e faz as perguntas."""
    indice = montar_indice(sessao, vetorizador)
    _ = indice.vetores  # os vetores dos trechos saem antes da primeira pergunta medida
    respostas = perguntar(indice, casos)
    return relatorio(indice.vetorizador.nome, respostas), respostas


def calibrar(
    sessao: Sessao, vetorizador: Vetorizador, casos: Sequence[Caso]
) -> tuple[Limiares, Relatorio]:
    """Os limiares de menor custo de erro, e depois de mais revocação e MRR.

    Responder uma pergunta de fora da plataforma custa três vezes mais que um
    "não sei" para uma pergunta que tinha resposta (`CUSTO_DA_RESPOSTA_ERRADA`):
    um trecho com fonte para a pergunta errada engana, e o "não sei" só deixa de
    ajudar. Entre combinações empatadas, fica a mais permissiva (limiares
    menores): o portão só fecha o que precisa fechar.
    """
    indice = montar_indice(sessao, vetorizador)
    medidos: list[tuple[Caso, Candidatos]] = [
        (c, indice.candidatos(c.pergunta, tipos=c.tipos)) for c in casos
    ]
    grade = itertools.product(
        (0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65),
        (0.6, 0.7, 0.8, 0.9, 1.01),
        (0.0, 0.1, 0.2, 0.3),
        (0.2, 0.3, 0.4),
        (0.5, 0.6, 0.7) if indice.vetorizador.semantico else (0.6,),
    )
    melhor: tuple[tuple[float, ...], Limiares, Relatorio] | None = None
    for minima, segura, margem, por_trecho, semantica in grade:
        if segura < minima:
            continue
        limiares = Limiares(minima, segura, margem, por_trecho, semantica)
        respostas = [
            Resposta(
                caso,
                _ids_do_achado(r := indice.decidir(c, k=PROFUNDIDADE, limiares=limiares)),
                r.motivo,
                0.0,
                r.evidencia,
                r.margem,
                r.similaridade,
            )
            for caso, c in medidos
        ]
        atual = relatorio(indice.vetorizador.nome, respostas)
        erradas = sum(1 for r in respostas if r.caso.abster and not r.absteve)
        caladas = sum(1 for r in respostas if not r.caso.abster and r.absteve)
        chave = (
            -(CUSTO_DA_RESPOSTA_ERRADA * erradas + caladas),
            atual.revocacao_5,
            atual.mrr_10,
            -minima,
            -segura,
            -margem,
            -por_trecho,
            -semantica,
        )
        if melhor is None or chave > melhor[0]:
            melhor = (chave, limiares, atual)
    assert melhor is not None
    return melhor[1], melhor[2]


def vetorizador_neural(estado: Path = ESTADO) -> Vetorizador | None:
    """O modelo multilíngue, se o pacote estiver instalado; `None` se não estiver."""
    if importlib.util.find_spec("fastembed") is None:
        return None
    return vetorizador_padrao(estado, modo="neural")


def vetorizador_ngramas() -> Vetorizador:
    return ComCache(NGramas(), CacheDeVetores(None))


# --------------------------------------------------------------------------- #
# A saída
# --------------------------------------------------------------------------- #

_LINHAS: Final = (
    ("revocacao_5", "revocação em 5"),
    ("mrr_10", "MRR em 10"),
    ("ndcg_10", "nDCG em 10"),
    ("acerto_abstencao", "acerto de abstenção"),
    ("latencia_p50_ms", "latência p50 (ms)"),
    ("latencia_p95_ms", "latência p95 (ms)"),
)


def tabela(colunas: Sequence[tuple[str, Relatorio | None]]) -> str:
    """A ablação lado a lado, em Markdown."""
    cabeca = "| métrica | " + " | ".join(nome for nome, _ in colunas) + " |"
    linhas = [cabeca, "|---|" + "---:|" * len(colunas)]
    for chave, rotulo in _LINHAS:
        valores = [
            "indisponível" if r is None else f"{getattr(r, chave):.3f}".replace(".", ",")
            for _, r in colunas
        ]
        linhas.append(f"| {rotulo} | " + " | ".join(valores) + " |")
    return "\n".join(linhas)


def _colunas(
    sessao: Sessao, casos: Sequence[Caso], modo: str
) -> tuple[list[tuple[str, Relatorio | None]], dict[str, Any]]:
    """A coluna dos n-gramas e a do modelo, conforme o modo pedido."""
    colunas: list[tuple[str, Relatorio | None]] = []
    detalhes: dict[str, Any] = {}
    if modo in ("ngramas", "ambos"):
        rel, _ = rodar(sessao, vetorizador_ngramas(), casos)
        colunas.append(("n-gramas com hash", rel))
        detalhes["ngramas"] = asdict(rel)
    if modo in ("neural", "ambos"):
        neural = vetorizador_neural()
        rel_neural: Relatorio | None = None
        if neural is not None:
            rel_neural, _ = rodar(sessao, neural, casos)
            if rel_neural.vetorizador == vetorizador_ngramas().nome:
                rel_neural = None  # o modelo não carregou: não finge a coluna
        colunas.append(("modelo multilíngue", rel_neural))
        detalhes["neural"] = asdict(rel_neural) if rel_neural else None
    return colunas, detalhes


def _calibracoes(sessao: Sessao, casos: Sequence[Caso]) -> dict[str, Any]:
    """Os limiares calibrados com cada braço vetorial disponível."""
    detalhes: dict[str, Any] = {}
    for nome, vetorizador in (("ngramas", vetorizador_ngramas()), ("neural", vetorizador_neural())):
        if vetorizador is None:
            continue
        limiares, rel = calibrar(sessao, vetorizador, casos)
        print(f"calibração ({nome}): {limiares}")
        print(f"  com eles: {rel}")
        detalhes[f"calibracao_{nome}"] = {"limiares": asdict(limiares), "relatorio": asdict(rel)}
    return detalhes


def main(argumentos: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="O conjunto dourado da busca da plataforma.")
    parser.add_argument("--vetorizador", choices=("ngramas", "neural", "ambos"), default="ambos")
    parser.add_argument("--saida", type=Path, help="grava o relatório em JSON")
    parser.add_argument("--calibrar", action="store_true", help="procura os limiares do portão")
    opcoes = parser.parse_args(argumentos)

    casos = carregar_casos()
    with tempfile.TemporaryDirectory(prefix="recuperacao-") as pasta:
        sessao = montar_estado(Path(pasta))
        try:
            colunas, detalhes = _colunas(sessao, casos, opcoes.vetorizador)
            if opcoes.calibrar:
                detalhes.update(_calibracoes(sessao, casos))
        finally:
            sessao.dossie.fechar()

    print(f"Conjunto dourado da busca: {len(casos)} perguntas, ", end="")
    print(f'{sum(1 for c in casos if c.abster)} que têm de dar "não sei"\n')
    print(tabela(colunas))
    falhas: list[str] = []
    for nome, rel in colunas:
        for erro in rel.erros if rel else ():
            print(f"  {nome}: {erro}")
        if rel is not None and nome.startswith("n-gramas"):
            falhas = rel.dentro_do_piso()
    if opcoes.saida:
        opcoes.saida.parent.mkdir(parents=True, exist_ok=True)
        conteudo = json.dumps({"casos": len(casos), **detalhes}, ensure_ascii=False, indent=2)
        opcoes.saida.write_text(conteudo + "\n", "utf-8")
    if falhas:
        print("\n  abaixo do piso: " + "; ".join(falhas))
        return 1
    print("\n  dentro do piso")
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "AGORA",
    "CASOS",
    "PISO",
    "Caso",
    "Relatorio",
    "Resposta",
    "acerto_de_abstencao",
    "calibrar",
    "carregar_casos",
    "main",
    "montar_estado",
    "montar_indice",
    "mrr",
    "ndcg",
    "perguntar",
    "relatorio",
    "revocacao",
    "rodar",
    "tabela",
    "vetorizador_neural",
    "vetorizador_ngramas",
]
