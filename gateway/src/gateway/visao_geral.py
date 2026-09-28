"""A tela inicial numa leitura só: o próximo passo, as perguntas, os números e o que está parado.

`GET /api/visao-geral` (a forma de `contratos/web/visao-geral.json`) e o card
`despensa_resumo` da conversa leem daqui. Tudo sai das mesmas funções das telas
de cada área, para a tela inicial nunca dizer outra coisa que a tela de lá:

- **os indicadores** (despensa, orçamento, receitas, cardápio e cozinha), cada
  um com a rota que o cartão abre e o texto pronto, com o plural certo;
- **o próximo passo**, dito para ela, com um link ou um rascunho para a conversa;
- **as perguntas**: as da despensa (`pendencias`, a mesma forma da despensa) e
  as da cozinha que seguram receitas (`perguntas_da_cozinha`, a forma das
  perguntas da receita, uma por pergunta, com as receitas que ela libera);
- **onde o dinheiro está parado**: todos os itens com preço, do que mais custou
  para o que menos custou (a tela mostra cinco e abre o resto);
- **as receitas recomendadas** (a aba "dá pra fazer" da grade) e a prévia do
  cardápio (a forma dos pratos de `cardapio.json`).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, Final

from mise import receitas_json
from mise.despensa import TipoDePendencia
from mise.despensa_json import dinheiro_json, item_json, pendencia_json
from mise.dinheiro import Dinheiro
from mise.genero import falar
from mise.perfil import contagem

from gateway.cardapio import cardapio

if TYPE_CHECKING:
    from mise.despensa import Despensa, Pendencia
    from mise.mcp_server import Sessao
    from mise.receitas_json import LeituraDaReceita

#: Quantas receitas recomendadas a tela inicial recebe (ela mostra algumas e abre o resto).
RECOMENDADAS: Final = 8

#: As perguntas da cozinha que a tela inicial faz: as de equipamento, técnica e rotina.
TIPOS_DA_COZINHA: Final = frozenset({"equipamento", "tecnica", "operacional"})

#: As perguntas que são da própria receita (o tempo no fogo, o rendimento, o preparo):
#: essas ficam na tela da receita, que é onde a resposta volta.
CAMPOS_DA_RECEITA: Final = frozenset({"tempo_cozimento_min", "rendimento_porcoes", "modo_preparo"})

#: Onde as perguntas ficam na tela inicial, e a aba das receitas que esperam resposta.
ROTA_DAS_PERGUNTAS: Final = "/#perguntas"
#: O que falta saber da cozinha se responde conversando: o agente pergunta o gosto,
#: depois só o que a cozinha precisa dizer, uma pergunta por vez.
ROTA_DA_CONVERSA_DA_COZINHA: Final = "/conversa?comecar=cozinha"
ROTA_DA_ABA_FALTA_RESPOSTA: Final = "/receitas?aba=falta_resposta"

#: O que ela manda para o agente quando ainda não há receita nenhuma.
RASCUNHO_DE_RECEITAS: Final = "Que receitas eu consigo fazer com o que tenho na despensa?"

#: Quantos nomes de receita a frase cita antes de dizer "e mais N".
_NOMES_NA_FRASE: Final = 2


def _pct(fracao: Decimal) -> str:
    """ "12%"; o que existe e arredonda para zero é "menos de 1%"."""
    pct = (fracao * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    if fracao > 0 and pct == 0:
        return "menos de 1%"
    return f"{pct}%"


def _minuscula(nome: str) -> str:
    return falar(nome).minusculo


def _lista(nomes: Sequence[str]) -> str:
    """ "arroz com frango", "arroz com frango e bolo de fubá", "a, b e mais 2"."""
    if len(nomes) <= _NOMES_NA_FRASE:
        return " e ".join(nomes)
    return f"{', '.join(nomes[:_NOMES_NA_FRASE])} e mais {len(nomes) - _NOMES_NA_FRASE}"


# --------------------------------------------------------------------------- #
# Os indicadores
# --------------------------------------------------------------------------- #


def _kpi_despensa(despensa: Despensa) -> dict[str, Any]:
    quantos = len(despensa)
    return {
        "total": dinheiro_json(despensa.total_investido),
        "itens": quantos,
        "texto": contagem(quantos, "ingrediente", "ingredientes")
        if quantos
        else "nenhum ingrediente",
        "rota": "/despensa",
    }


def _kpi_orcamento(sessao: Sessao) -> dict[str, Any]:
    estado = sessao.dossie.orcamento()
    return {
        "restante": dinheiro_json(estado.restante),
        "inicial": dinheiro_json(estado.inicial),
        "gasto": dinheiro_json(estado.gasto),
        "texto": f"{estado.gasto} já gastos" if estado.gasto else "nada gasto ainda",
        "rota": "/despensa#orcamento",
    }


def _kpi_receitas(no_catalogo: int, da_pra_fazer: int) -> dict[str, Any]:
    if no_catalogo == 0:
        texto = "nenhuma receita ainda"
    elif da_pra_fazer == 0:
        texto = f"nenhuma das {no_catalogo} dá pra fazer ainda"
    else:
        verbo = "dá" if da_pra_fazer == 1 else "dão"
        texto = f"{da_pra_fazer} de {no_catalogo} {verbo} pra fazer"
    return {
        "no_catalogo": no_catalogo,
        "da_pra_fazer": da_pra_fazer,
        "texto": texto,
        "rota": "/receitas",
    }


def _kpi_cardapio(pratos: int) -> dict[str, Any]:
    return {
        "pratos": pratos,
        "texto": contagem(pratos, "prato", "pratos") + " no cardápio"
        if pratos
        else "nenhum prato ainda",
        "rota": "/cardapio",
    }


def _kpi_cozinha(sessao: Sessao) -> dict[str, Any]:
    """O progresso da cozinha, com o mesmo texto da tela da cozinha."""
    perfil = sessao.perfil
    return {
        "respondidos": perfil.respondidos,
        "supostos": perfil.supostos,
        "em_aberto": perfil.em_aberto,
        "fracao_respondida": perfil.fracao_respondida,
        "texto": perfil.progresso_para_a_tela(),
        "rota": "/cozinha",
    }


# --------------------------------------------------------------------------- #
# As perguntas
# --------------------------------------------------------------------------- #


def _pergunta_da_cozinha(grupo: list[LeituraDaReceita], pergunta: dict[str, Any]) -> dict[str, Any]:
    nomes = [_minuscula(leitura.nome) for leitura in grupo]
    quantas = contagem(len(nomes), "receita", "receitas")
    segura = f"Isso segura {quantas}: {_lista(nomes)}."
    primeira = grupo[0]
    return {
        "id": f"{pergunta['tipo']}:{pergunta['campo']}",
        "pergunta": {**pergunta, "motivo": segura},
        "receita": {"slug": primeira.slug, "nome": primeira.nome},
        "receitas": [{"slug": leitura.slug, "nome": leitura.nome} for leitura in grupo],
        "rascunho_chat": f"Sobre a pergunta “{pergunta['texto']}”: ",
        "rota": ROTA_DA_ABA_FALTA_RESPOSTA,
    }


def perguntas_da_cozinha(
    sessao: Sessao, leituras: Sequence[LeituraDaReceita]
) -> list[dict[str, Any]]:
    """As perguntas da cozinha que seguram receitas, uma por pergunta, da que libera mais."""
    grupos: dict[tuple[str, str], tuple[dict[str, Any], list[LeituraDaReceita]]] = {}
    for leitura in sorted(leituras, key=lambda le: le.nome.casefold()):
        if leitura.aba != "falta_resposta":
            continue
        pergunta = receitas_json.pergunta_json(sessao, leitura)
        if (
            pergunta is None
            or pergunta["tipo"] not in TIPOS_DA_COZINHA
            or pergunta["campo"] in CAMPOS_DA_RECEITA
        ):
            continue
        chave = (pergunta["tipo"], pergunta["campo"])
        grupos.setdefault(chave, (pergunta, []))[1].append(leitura)
    ordenados = sorted(grupos.values(), key=lambda par: -len(par[1]))
    return [_pergunta_da_cozinha(grupo, pergunta) for pergunta, grupo in ordenados]


def _pendencias(despensa: Despensa) -> list[dict[str, Any]]:
    return [pendencia_json(p, despensa) for p in despensa.pendencias]


# --------------------------------------------------------------------------- #
# O próximo passo
# --------------------------------------------------------------------------- #


def _sobre(pendencia: Pendencia) -> str:
    nome = falar(pendencia.ingrediente)
    return nome.com_artigo() or nome.minusculo


def _link(texto: str, rota: str) -> dict[str, Any]:
    return {"texto": texto, "acao": {"tipo": "link", "rota": rota}}


def proximo_passo(
    despensa: Despensa,
    perguntas: Sequence[dict[str, Any]],
    *,
    no_catalogo: int,
    da_pra_fazer: int,
    pratos: int,
) -> dict[str, Any]:
    """O que ela faz agora, dito para ela: a pergunta que segura dinheiro vem primeiro."""
    if despensa.pendencias:
        pendencia = despensa.pendencias[0]
        if pendencia.tipo is TipoDePendencia.PRECO:
            porque = "sem o preço, as receitas com ele ficam sem custo"
        else:
            porque = f"sem isso, {pendencia.impacto} ficam parados"
        return _link(
            f"Responda a pergunta sobre {_sobre(pendencia)}: {porque}.", ROTA_DAS_PERGUNTAS
        )
    if perguntas:
        libera = contagem(sum(len(p["receitas"]) for p in perguntas), "receita", "receitas")
        return _link(
            f"Responda o que falta saber da sua cozinha: isso libera {libera}.",
            ROTA_DA_CONVERSA_DA_COZINHA,
        )
    if no_catalogo == 0:
        return {
            "texto": (
                "Peça receitas para o agente: ele procura na internet as que aproveitam "
                "a sua despensa."
            ),
            "acao": {"tipo": "perguntar", "rascunho": RASCUNHO_DE_RECEITAS},
        }
    if pratos == 0 and da_pra_fazer > 0:
        dao = (
            "a receita que já dá" if da_pra_fazer == 1 else f"as {da_pra_fazer} receitas que já dão"
        )
        return _link(f"Veja {dao} pra fazer e escolha o que entra no cardápio.", "/receitas")
    if pratos == 0:
        return {
            "texto": "Nenhuma receita dá pra fazer ainda. Peça outras para o agente.",
            "acao": {"tipo": "perguntar", "rascunho": RASCUNHO_DE_RECEITAS},
        }
    no_cardapio = contagem(pratos, "prato", "pratos")
    return _link(
        f"O seu cardápio tem {no_cardapio}. Confira o preço e o lucro de cada um.", "/cardapio"
    )


# --------------------------------------------------------------------------- #
# O dinheiro parado
# --------------------------------------------------------------------------- #


def _usados(leituras: Sequence[LeituraDaReceita]) -> set[str]:
    """Os itens que alguma receita que ela consegue (ou pode vir a conseguir) fazer usa."""
    return {
        ajuste.item.id
        for leitura in leituras
        if leitura.aba in ("pode_fazer", "falta_resposta")
        for ajuste in leitura.avaliacao.ajustes
        if ajuste.item is not None
    }


def _dois_maiores(despensa: Despensa, com_preco: Sequence[Any]) -> dict[str, Any]:
    dois = com_preco[:2]
    soma = sum((i.preco_pago for i in dois), Dinheiro.zero())
    total = despensa.total_investido.valor
    fracao = soma.valor / total if total else Decimal(0)
    nomes = [i.nome for i in dois]
    if len(nomes) == 2:  # noqa: PLR2004 (os dois maiores)
        texto = f"{nomes[0]} e {nomes[1]} somam {_pct(fracao)} de tudo o que a senhora pagou"
    elif nomes:
        texto = f"{nomes[0]} é tudo o que a senhora pagou"
    else:
        texto = "Nada pago na despensa ainda"
    return {
        "nomes": nomes,
        "soma": dinheiro_json(soma),
        "fracao": round(float(fracao), 4),
        "texto": texto,
    }


def dinheiro_parado(despensa: Despensa, leituras: Sequence[LeituraDaReceita]) -> dict[str, Any]:
    """Todos os itens com preço, do que mais custou ao que menos custou."""
    com_preco = [i for i in despensa.por_valor() if i.preco_informado]
    usados = _usados(leituras)
    itens = []
    for item in com_preco:
        fracao = despensa.fracao_de(item)
        itens.append(
            {
                "id": item.id,
                "nome": item.nome,
                "pago": dinheiro_json(item.preco_pago),
                "fracao": round(float(fracao), 4),
                "fracao_texto": _pct(fracao),
                "imagem": item_json(item, despensa)["imagem"],
                "sem_receita": item.id not in usados,
                "rota": f"/despensa/{item.id}",
            }
        )
    return {
        "total_itens": len(itens),
        "dois_maiores": _dois_maiores(despensa, com_preco),
        "itens": itens,
    }


# --------------------------------------------------------------------------- #
# A tela inteira
# --------------------------------------------------------------------------- #


def visao_geral(sessao: Sessao) -> dict[str, Any]:
    """`GET /api/visao-geral`: a tela inicial numa leitura só."""
    despensa = sessao.despensa
    leituras = receitas_json.ler(sessao, receitas_json.guardadas(sessao))
    grade = receitas_json.lista(sessao, receitas_json.Filtros(aba="pode_fazer"))
    da_pra_fazer = grade["contagens"]["pode_fazer"]
    no_cardapio = cardapio(sessao)
    pratos = no_cardapio["pratos"]
    perguntas = perguntas_da_cozinha(sessao, leituras)
    return {
        "kpis": {
            "despensa": _kpi_despensa(despensa),
            "orcamento": _kpi_orcamento(sessao),
            "receitas": _kpi_receitas(len(leituras), da_pra_fazer),
            "cardapio": _kpi_cardapio(len(pratos)),
            "cozinha": _kpi_cozinha(sessao),
        },
        "proximo_passo": proximo_passo(
            despensa,
            perguntas,
            no_catalogo=len(leituras),
            da_pra_fazer=da_pra_fazer,
            pratos=len(pratos),
        ),
        "pendencias": _pendencias(despensa),
        "perguntas_da_cozinha": perguntas,
        "dinheiro_parado": dinheiro_parado(despensa, leituras),
        "receitas_recomendadas": grade["itens"][:RECOMENDADAS],
        "cardapio_previa": pratos,
    }


__all__ = [
    "CAMPOS_DA_RECEITA",
    "RASCUNHO_DE_RECEITAS",
    "RECOMENDADAS",
    "TIPOS_DA_COZINHA",
    "dinheiro_parado",
    "perguntas_da_cozinha",
    "proximo_passo",
    "visao_geral",
]
