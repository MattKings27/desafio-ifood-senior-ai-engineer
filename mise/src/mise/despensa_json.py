"""A despensa como a tela e o agente leem: os textos em pt-BR e as formas do contrato.

A ferramenta do agente (`atualizar_despensa`) e as rotas da tela
(`/api/despensa/...`) dizem a mesma coisa sobre o mesmo item, com as mesmas
palavras: por isso as duas montam a resposta aqui, e nenhuma formata sozinha.
As formas seguem `contratos/web/despensa.json`, `despensa-item.json` e
`despensa-escrita.json`.

Regras de todo texto daqui: dinheiro sempre como "R$ x,yy" (é o que o guard-rail
da conversa reconhece), quantidade e data já escritas (`*_texto`), vírgula
decimal, e nenhuma palavra interna do sistema.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, Final

from mise import categorias, fotos
from mise.despensa import (
    Confianca,
    Despensa,
    Ingrediente,
    OrigemDoItem,
    Pendencia,
    TipoDePendencia,
    montar_ingrediente,
)
from mise.dinheiro import Dinheiro
from mise.dossie import EstadoOrcamento, LinhaDoExtrato
from mise.erros import ErroDeUso, ErroMise
from mise.genero import falar
from mise.unidades import Dimensao, Quantidade

if TYPE_CHECKING:
    from mise.despensa_editavel import EstadoDaDespensa, Evento, Mudanca
    from mise.mcp_server import Sessao
    from mise.receita import Receita
    from mise.viabilidade import Veredito

#: O horário dela. O Brasil não tem horário de verão desde 2019: Brasília é UTC-3
#: o ano todo, e um fuso fixo não depende da base de fusos do sistema.
FUSO: Final = timezone(timedelta(hours=-3), "Brasília")

MESES: Final = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)

#: As ordens que a lista da despensa aceita.
ORDENS: Final = ("valor", "nome", "custo", "categoria")

#: As unidades que a tela oferece para responder "quanto vem na embalagem?".
UNIDADES_DA_EMBALAGEM: Final = ("g", "kg", "ml", "L")

#: Como cada embalagem se escreve, no singular e no plural.
_EMBALAGENS: Final[dict[str, tuple[str, str]]] = {
    "un": ("embalagem", "embalagens"),
    "und": ("embalagem", "embalagens"),
    "unid": ("embalagem", "embalagens"),
    "unidade": ("embalagem", "embalagens"),
    "unidades": ("embalagem", "embalagens"),
    "embalagem": ("embalagem", "embalagens"),
    "pc": ("peça", "peças"),
    "peca": ("peça", "peças"),
    "pct": ("pacote", "pacotes"),
    "pacote": ("pacote", "pacotes"),
    "sache": ("sachê", "sachês"),
    "vidro": ("vidro", "vidros"),
    "frasco": ("frasco", "frascos"),
    "pote": ("pote", "potes"),
    "lata": ("lata", "latas"),
    "caixa": ("caixa", "caixas"),
    "caixinha": ("caixinha", "caixinhas"),
    "garrafa": ("garrafa", "garrafas"),
    "saco": ("saco", "sacos"),
    "balde": ("balde", "baldes"),
    "bandeja": ("bandeja", "bandejas"),
    "duzia": ("dúzia", "dúzias"),
}

#: Rótulos que contam unidades soltas (ovos), e não embalagens.
_CONTAGEM: Final = frozenset({"un", "und", "unid", "unidade", "unidades"})


# --------------------------------------------------------------------------- #
# Números, quantidades e datas
# --------------------------------------------------------------------------- #


def numero_texto(valor: Decimal) -> str:
    """Como se escreve no Brasil: "0,5", "1.234", nunca "0.5"."""
    n = valor.normalize()
    if n == n.to_integral_value():
        inteiro = int(n)
        return f"{inteiro:,}".replace(",", ".")
    return f"{n:f}".replace(".", ",")


def quantidade_texto(quantidade: Quantidade) -> str:
    """ "500 g", "1,5 kg", "300 ml", "2 L", "30 unidades"."""
    valor = quantidade.valor
    if quantidade.dimensao is Dimensao.CONTAGEM:
        return f"{numero_texto(valor)} {'unidade' if valor == 1 else 'unidades'}"
    grande, pequena = ("kg", "g") if quantidade.dimensao is Dimensao.MASSA else ("L", "ml")
    if 0 < valor < 1:
        return f"{numero_texto(valor * 1000)} {pequena}"
    return f"{numero_texto(valor)} {grande}"


def quando_texto(momento: datetime, agora: datetime) -> str:
    """ "hoje, 14:32", "ontem, 09:10", "24 de setembro", "24 de setembro de 2025"."""
    local = momento.astimezone(FUSO)
    hoje = agora.astimezone(FUSO).date()
    if local.date() == hoje:
        return f"hoje, {local:%H:%M}"
    if local.date() == hoje - timedelta(days=1):
        return f"ontem, {local:%H:%M}"
    data = f"{local.day} de {MESES[local.month - 1]}"
    return data if local.year == hoje.year else f"{data} de {local.year}"


def data_hora_texto(momento: datetime) -> str:
    """ "2026-09-25 10:00", no horário dela: para a planilha em texto."""
    return f"{momento.astimezone(FUSO):%Y-%m-%d %H:%M}"


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _maiuscula(texto: str) -> str:
    return texto[:1].upper() + texto[1:]


# --------------------------------------------------------------------------- #
# Um item
# --------------------------------------------------------------------------- #


def _palavra_da_embalagem(rotulo: str) -> str:
    primeira = _sem_acento(rotulo.strip().split(" ", 1)[0]).lower() if rotulo.strip() else ""
    return "".join(c for c in primeira if c.isalpha())


def _embalagem(rotulo: str, quantas: Decimal) -> str:
    palavra = _palavra_da_embalagem(rotulo)
    singular, plural = _EMBALAGENS.get(
        palavra, (palavra or "embalagem", f"{palavra or 'embalagem'}s")
    )
    return singular if quantas == 1 else plural


def _e_pura(item: Ingrediente) -> bool:
    return item.unidade_compra.rotulo_original.strip().lower() in {"kg", "g", "mg", "l", "ml"}


def estoque_texto(item: Ingrediente) -> str:
    """O que ela tem: "2 kg", "2 kg (1 balde de 2 kg)", "1 embalagem (peso não informado)"."""
    if item.estoque.valor == 0:
        return "acabou"
    em_embalagens = item.linha.estoque
    unidade = item.unidade_compra
    if unidade.conteudo_por_embalagem is None:
        palavra = _palavra_da_embalagem(unidade.rotulo_original)
        if item.embalagem_opaca or palavra not in _CONTAGEM:
            embalagem = _embalagem(unidade.rotulo_original, em_embalagens)
            texto = f"{numero_texto(em_embalagens)} {embalagem}"
            return f"{texto} (peso não informado)" if item.embalagem_opaca else texto
        return quantidade_texto(item.estoque)
    if _e_pura(item):
        return quantidade_texto(item.estoque)
    return (
        f"{quantidade_texto(item.estoque)} ({numero_texto(em_embalagens)} "
        f"{_embalagem(unidade.rotulo_original, em_embalagens)} de "
        f"{quantidade_texto(unidade.conteudo_por_embalagem)})"
    )


def comprado_texto(item: Ingrediente) -> str:
    """O que ela comprou e quanto pagou: "2 kg por R$ 28,00", "1 balde de 2 kg por R$ 82,00"."""
    if not item.preco_informado:
        return "a senhora não disse quanto pagou"
    quantas = item.quantidade_bruta
    unidade = item.unidade_compra
    if unidade.conteudo_por_embalagem is None:
        palavra = _palavra_da_embalagem(unidade.rotulo_original)
        if item.embalagem_opaca or palavra not in _CONTAGEM:
            comprado = f"{numero_texto(quantas)} {_embalagem(unidade.rotulo_original, quantas)}"
        else:
            comprado = quantidade_texto(Quantidade(quantas, Dimensao.CONTAGEM))
    elif _e_pura(item):
        comprado = quantidade_texto(item.comprado)
    else:
        comprado = (
            f"{numero_texto(quantas)} {_embalagem(unidade.rotulo_original, quantas)} de "
            f"{quantidade_texto(unidade.conteudo_por_embalagem)}"
        )
    return f"{comprado} por {item.preco_pago}"


def custo_conhecido(item: Ingrediente) -> bool:
    """O custo por quilo, litro ou unidade existe? Sem preço ou sem peso, não."""
    return item.preco_informado and item.custo.confianca is not Confianca.DESCONHECIDA


def custo_texto(item: Ingrediente) -> str:
    """ "R$ 41,00/kg", ou o que falta para saber."""
    if not item.preco_informado:
        return "sem o preço, não dá para saber"
    if item.custo.confianca is Confianca.DESCONHECIDA:
        return "sem o peso da embalagem, não dá para saber"
    return f"{item.custo.valor}/{item.dimensao.value}"


def custo_unitario_json(item: Ingrediente) -> dict[str, Any] | None:
    if not custo_conhecido(item):
        return None
    return {"valor": float(item.custo.valor.arredondado().valor), "texto": custo_texto(item)}


def derivacao_texto(item: Ingrediente) -> str:
    """A conta, escrita como ela lê. Embalagem sem peso diz por que não há custo por quilo."""
    if item.preco_informado and item.custo.confianca is Confianca.DESCONHECIDA:
        quantas = item.quantidade_bruta
        return (
            f"{item.preco_pago} ÷ {numero_texto(quantas)} "
            f"{_embalagem(item.unidade_compra.rotulo_original, quantas)}; sem o peso da "
            "embalagem, não dá para saber o custo por quilo"
        )
    return item.custo.derivacao


def confianca_rotulo(item: Ingrediente) -> str:
    if not item.preco_informado:
        return "falta o preço que a senhora pagou"
    if item.custo.confianca is Confianca.DESCONHECIDA:
        return "falta o peso da embalagem"
    if item.custo.confianca is Confianca.MEDIA:
        if item.linha.conteudo_informado:
            return "conta com o peso que a senhora informou"
        return "conta com conversão de embalagem"
    if item.origem is OrigemDoItem.PLANILHA:
        return "conta direta da planilha"
    return "conta direta"


ORIGEM_ROTULO: Final[dict[OrigemDoItem, str]] = {
    OrigemDoItem.PLANILHA: "da planilha",
    OrigemDoItem.JA_TINHA: "a senhora já tinha",
    OrigemDoItem.ORCAMENTO: "comprado com os complementos",
}


def fracao_texto(fracao: Decimal, item: Ingrediente | None = None) -> str:
    if item is not None and not item.preco_informado:
        return "sem o preço, fica fora do total"
    pct = (fracao * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    if fracao > 0 and pct == 0:
        return "menos de 1% do que a senhora pagou"
    return f"{pct}% do que a senhora pagou"


def receitas_texto(quantas: int) -> str:
    if quantas == 0:
        return "ainda sem receita"
    return f"entra em {quantas} {'receita' if quantas == 1 else 'receitas'}"


def dinheiro_json(valor: Dinheiro) -> dict[str, Any]:
    """Dinheiro com número e texto: a tela mostra o texto e usa o número só para ordenar."""
    return {"valor": float(valor.arredondado().valor), "texto": str(valor)}


def item_json(item: Ingrediente, despensa: Despensa, receitas_que_usam: int = 0) -> dict[str, Any]:
    """O item da lista (`despensa.json#itens`), com os campos antigos que a tela ainda lê."""
    categoria = categorias.categoria(item.categoria)
    fracao = despensa.fracao_de(item)
    return {
        "id": item.id,
        "nome": item.nome,
        "categoria": categoria.id,
        "categoria_rotulo": categoria.rotulo,
        "estoque": float(item.estoque.valor),
        "unidade": item.dimensao.value,
        "estoque_texto": estoque_texto(item),
        "pago": dinheiro_json(item.preco_pago) if item.preco_informado else None,
        "custo_unitario": custo_unitario_json(item),
        "derivacao": derivacao_texto(item),
        "confianca": item.custo.confianca.value,
        "confianca_rotulo": confianca_rotulo(item),
        "fracao_do_total": round(float(fracao), 4),
        "fracao_texto": fracao_texto(fracao, item),
        "origem": item.origem.value,
        "origem_rotulo": ORIGEM_ROTULO[item.origem],
        # A foto do Commons dos itens da planilha; o item que ela acrescentou não tem.
        "imagem": fotos.imagem_do_item(despensa, item),
        "receitas_que_usam": receitas_que_usam,
        "receitas_que_usam_texto": receitas_texto(receitas_que_usam),
        "pendente": despensa.pendencia_de(item.nome) is not None,
        "rota": f"/despensa/{item.id}",
        # Campos da tela antiga: ficam até ela parar de ler.
        "custo_texto": custo_texto(item),
        "normalizacao_importou": item.normalizacao_importou,
        "custo_ingenuo": dinheiro_json(item.custo_ingenuo),
        "rotulo_original": item.unidade_compra.rotulo_original,
    }


def pendencia_json(pendencia: Pendencia, despensa: Despensa) -> dict[str, Any]:
    """Uma pergunta da despensa, com a resposta que a tela oferece ali mesmo."""
    item = despensa.get(pendencia.ingrediente)
    id_ = item.id if item is not None else ""
    nome = falar(pendencia.ingrediente)
    if pendencia.tipo is TipoDePendencia.PRECO:
        # "com" sem artigo é como se fala da receita que leva o item: "receitas com frango".
        impacto_texto = f"sem o preço, as receitas com {nome.minusculo} ficam sem custo"
        resposta: dict[str, Any] = {
            "tipo": TipoDePendencia.PRECO.value,
            "rotulo": "Quanto a senhora pagou?",
            # Sem unidade a escolher: a resposta é o valor e a quantidade comprada.
            "unidades": [],
            "campos": ["preco_pago", "quantidade_comprada"],
        }
        # O começo da frase dela, em primeira pessoa: "Paguei por farinha de rosca ".
        rascunho = f"Paguei por {nome.minusculo} "
    else:
        impacto_texto = f"{pendencia.impacto} parados até isso ser respondido"
        resposta = {
            "tipo": TipoDePendencia.EMBALAGEM.value,
            "rotulo": "Quanto vem na embalagem?",
            "unidades": list(UNIDADES_DA_EMBALAGEM),
        }
        rascunho = f"A embalagem {nome.de()} tem "
    return {
        "id": id_,
        "ingrediente": pendencia.ingrediente,
        "tipo": pendencia.tipo.value,
        "motivo": pendencia.motivo,
        "pergunta": pendencia.pergunta,
        "impacto": dinheiro_json(pendencia.impacto),
        "impacto_texto": impacto_texto,
        "resposta_inline": resposta,
        "rascunho_chat": rascunho,
        "rota": f"/despensa/{id_}",
    }


# --------------------------------------------------------------------------- #
# Os R$ 80,00
# --------------------------------------------------------------------------- #


def resumo_do_orcamento(estado: EstadoOrcamento) -> str:
    """O saldo dos complementos dito para ela."""
    if not estado.gasto:
        return f"Nada gasto ainda: restam {estado.restante} para complementos."
    return f"Saíram {estado.gasto} dos complementos; restam {estado.restante}."


def compra_json(linha: LinhaDoExtrato, agora: datetime) -> dict[str, Any]:
    return {
        "id": linha.id,
        "descricao": linha.descricao,
        "ingrediente": linha.ingrediente,
        "item_id": linha.item_id,
        "valor": dinheiro_json(linha.valor),
        "quando_texto": quando_texto(linha.registrado, agora),
        "canal": linha.canal,
        "estornada": linha.estornada,
        "estorno": linha.e_estorno,
        "pode_estornar": linha.ativa and linha.valor.valor > 0,
        "rota_estorno": f"/api/compras/{linha.id}/estorno",
    }


def orcamento_json(
    estado: EstadoOrcamento, extrato: tuple[LinhaDoExtrato, ...], agora: datetime
) -> dict[str, Any]:
    """O painel dos R$ 80,00: quanto saiu, quanto resta e as compras que contam."""
    inicial = estado.inicial.valor
    return {
        "inicial": dinheiro_json(estado.inicial),
        "restante": dinheiro_json(estado.restante),
        "gasto": dinheiro_json(estado.gasto),
        "fracao_gasta": round(float(estado.gasto.valor / inicial), 4) if inicial else 0.0,
        "texto": resumo_do_orcamento(estado),
        "compras": [compra_json(linha, agora) for linha in extrato if linha.ativa],
    }


def orcamento_da_sessao(sessao: Sessao) -> dict[str, Any]:
    return orcamento_json(sessao.dossie.orcamento(), sessao.dossie.extrato(), sessao.dossie.agora())


# --------------------------------------------------------------------------- #
# Receitas que usam cada item
# --------------------------------------------------------------------------- #


def receitas_por_item(
    despensa: Despensa, receitas: Mapping[str, Receita]
) -> dict[str, list[Receita]]:
    """Para cada item (pelo nome), as receitas em avaliação que o usam.

    O casamento é o mesmo do portão (`casar`, só o confiável): "frango" na
    receita é o "Peito de frango" dela. Ingrediente "a gosto" também conta: a
    receita usa o item, só não diz quanto.
    """
    from mise.casamento import casar  # noqa: PLC0415

    usos: dict[str, list[Receita]] = {}
    for receita in receitas.values():
        vistos: set[str] = set()
        for ingrediente in receita.ingredientes:
            casamento = casar(ingrediente.nome, despensa)
            if casamento.confiavel and casamento.item is not None:
                vistos.add(casamento.item.nome)
        for nome in vistos:
            usos.setdefault(nome, []).append(receita)
    return usos


def slug_da_receita(receita: Receita) -> str:
    """O id da receita na tela: 16 hex do endereço canônico, ou o slug do nome.

    A regra mora em `mise.catalogo.id_da_receita`, a mesma do catálogo, das
    ferramentas (`receita_id`) e do contrato.
    """
    from mise.catalogo import id_da_receita  # noqa: PLC0415

    return id_da_receita(receita)


def vereditos(sessao: Sessao) -> dict[str, Veredito]:
    """O veredito de agora de cada receita em avaliação."""
    return {nome: sessao.avaliar(receita).veredito for nome, receita in sessao.candidatas.items()}


def receitas_afetadas(
    antes: Mapping[str, Veredito], depois: Mapping[str, Veredito]
) -> dict[str, Any]:
    """O que a mudança na despensa fez com as receitas: as que liberou e as que segurou."""
    liberadas = sorted(
        n
        for n, v in depois.items()
        if v.permite_precificar and n in antes and not antes[n].permite_precificar
    )
    bloqueadas = sorted(
        n
        for n, v in depois.items()
        if not v.permite_precificar and n in antes and antes[n].permite_precificar
    )
    mudaram = [
        {"receita": n, "antes": antes[n].rotulo_para_ela, "depois": v.rotulo_para_ela}
        for n, v in sorted(depois.items())
        if n in antes and antes[n] is not v
    ]
    partes = []
    if liberadas:
        partes.append(
            f"Isso libera {len(liberadas)} {'receita' if len(liberadas) == 1 else 'receitas'}."
        )
    if bloqueadas:
        partes.append(
            f"Isso segura {len(bloqueadas)} {'receita' if len(bloqueadas) == 1 else 'receitas'}."
        )
    # A receita que mudou sem ser liberada nem segurada ("Dá pra fazer" para "Dá,
    # comprando") também é dita: "nenhuma mudou" seria falso.
    contadas = set(liberadas) | set(bloqueadas)
    partes.extend(
        f"{m['receita']} passou para “{m['depois']}”."
        for m in mudaram
        if m["receita"] not in contadas
    )
    if not partes:
        partes.append(
            "Nenhuma receita em avaliação mudou." if antes else "Ainda não há receita em avaliação."
        )
    return {
        "liberadas": liberadas,
        "bloqueadas": bloqueadas,
        "mudaram": mudaram,
        "texto": " ".join(partes),
    }


# --------------------------------------------------------------------------- #
# A lista e o detalhe
# --------------------------------------------------------------------------- #


def _chave_de_busca(texto: str) -> str:
    return " ".join(_sem_acento(texto).casefold().split())


def _ordenar(itens: list[Ingrediente], ordem: str) -> list[Ingrediente]:
    if ordem == "nome":
        return sorted(itens, key=lambda i: _chave_de_busca(i.nome))
    if ordem == "custo":
        # Sem custo conhecido, por último: não há número para comparar.
        return sorted(
            itens,
            key=lambda i: (
                not custo_conhecido(i),
                -i.custo.valor.valor if custo_conhecido(i) else 0,
            ),
        )
    if ordem == "categoria":
        posicao = {c.id: n for n, c in enumerate(categorias.CATEGORIAS)}
        return sorted(
            itens, key=lambda i: (posicao.get(i.categoria, len(posicao)), _chave_de_busca(i.nome))
        )
    return sorted(itens, key=lambda i: i.preco_pago.valor, reverse=True)


def listar(
    sessao: Sessao, *, q: str | None = None, categoria: str | None = None, ordem: str = "valor"
) -> dict[str, Any]:
    """`GET /api/despensa`: os itens (com busca, categoria e ordem), as perguntas e o orçamento."""
    if ordem not in ORDENS:
        raise ErroDeUso("ordem desconhecida", ordem=ordem, validas=", ".join(ORDENS))
    if categoria is not None and categoria and not categorias.valida(categoria):
        raise ErroDeUso(
            "categoria desconhecida",
            categoria=categoria,
            validas=", ".join(c.id for c in categorias.CATEGORIAS),
        )
    despensa = sessao.despensa
    usos = receitas_por_item(despensa, sessao.candidatas)
    todos = list(despensa)
    filtrados = todos
    if q and q.strip():
        alvo = _chave_de_busca(q)
        filtrados = [i for i in filtrados if alvo in _chave_de_busca(i.nome)]
    if categoria:
        filtrados = [i for i in filtrados if i.categoria == categoria]
    contagem: dict[str, int] = {}
    for item in todos:
        contagem[item.categoria] = contagem.get(item.categoria, 0) + 1
    return {
        "itens": [
            item_json(i, despensa, len(usos.get(i.nome, []))) for i in _ordenar(filtrados, ordem)
        ],
        "total_investido": dinheiro_json(despensa.total_investido),
        "total_itens": len(todos),
        "encontrados": len(filtrados),
        "categorias": [
            {"id": c.id, "rotulo": c.rotulo, "quantidade": contagem[c.id]}
            for c in categorias.CATEGORIAS
            if contagem.get(c.id)
        ],
        # Todas, com ou sem item: é a lista do "em que categoria fica?" de um item novo.
        "categorias_para_escolher": [
            {"id": c.id, "rotulo": c.rotulo} for c in categorias.CATEGORIAS
        ],
        "pendencias": [pendencia_json(p, despensa) for p in despensa.pendencias],
        "orcamento": orcamento_da_sessao(sessao),
    }


def _uso_texto(sessao: Sessao, receita: Receita, item: Ingrediente) -> tuple[str, Veredito]:
    avaliacao = sessao.avaliar(receita)
    quantidades = [
        u.quantidade
        for u in avaliacao.usos
        if u.casamento.item is not None and u.casamento.item.nome == item.nome and not u.rotulo
    ]
    if not quantidades:
        return "usa a gosto", avaliacao.veredito
    total = quantidades[0]
    for q in quantidades[1:]:
        total = total + q if q.dimensao is total.dimensao else total
    return f"usa {quantidade_texto(total)}", avaliacao.veredito


def evento_json(
    evento: Evento, estado: EstadoDaDespensa, extrato: Mapping[int, LinhaDoExtrato], agora: datetime
) -> dict[str, Any]:
    """Uma mudança dela, como o histórico mostra."""
    item = estado.item(evento.item_id)
    nome = (
        item.linha.nome if item is not None else str(evento.dados.get("linha", {}).get("nome", ""))
    )
    return {
        "id": evento.rotulo,
        "tipo": evento.tipo.value,
        "acao": evento.acao.value,
        "texto": texto_do_evento(
            evento, nome, extrato, item.linha.unidade if item is not None else ""
        ),
        "quando_texto": quando_texto(evento.registrado, agora),
        "canal": evento.canal,
        "pode_desfazer": estado.pode_desfazer(evento),
        "desfaz": f"ev-{evento.desfaz:04d}" if evento.desfaz is not None else None,
        "item_id": evento.item_id,
        "item_nome": nome,
        "motivo": evento.motivo or None,
        "rota": f"/despensa/{evento.item_id}",
    }


def evento_da_planilha(item: Ingrediente) -> dict[str, Any]:
    """O começo da história de um item da planilha: não se desfaz."""
    return {
        "id": "planilha",
        "tipo": "planilha",
        "acao": "planilha",
        "texto": f"Veio da planilha: {comprado_texto(item)}.",
        "quando_texto": "na planilha que a senhora entregou",
        "canal": "planilha",
        "pode_desfazer": False,
        "desfaz": None,
        "item_id": item.id,
        "item_nome": item.nome,
        "motivo": None,
        "rota": f"/despensa/{item.id}",
    }


def detalhe(sessao: Sessao, item_id: str) -> dict[str, Any]:
    """`GET /api/despensa/itens/{id}`: o item, a conta, as receitas que o usam e a história."""
    estado = sessao.editavel.estado()
    despensa = estado.despensa
    item = sessao.editavel.item(item_id)
    usos = receitas_por_item(despensa, sessao.candidatas).get(item.nome, [])
    receitas = []
    for receita in usos:
        uso, veredito = _uso_texto(sessao, receita, item)
        slug = slug_da_receita(receita)
        receitas.append(
            {
                "slug": slug,
                "nome": receita.nome,
                "veredito": veredito.rotulo,
                "veredito_rotulo": veredito.rotulo_para_ela,
                "imagem": None,
                "usa_texto": uso,
                "rota": f"/receitas/{slug}",
            }
        )
    extrato = sessao.dossie.extrato()
    por_id = {linha.id: linha for linha in extrato}
    agora = sessao.dossie.agora()
    na_despensa = estado.item(item_id)
    historico = [evento_da_planilha(item)] if item.origem is OrigemDoItem.PLANILHA else []
    historico += [
        evento_json(e, estado, por_id, agora) for e in (na_despensa.eventos if na_despensa else ())
    ]
    return {
        **item_json(item, despensa, len(usos)),
        "comprado_texto": comprado_texto(item),
        "unidade_compra_rotulo": item.unidade_compra.rotulo_original,
        "pendencia": (
            pendencia_json(p, despensa) if (p := despensa.pendencia_de(item.nome)) else None
        ),
        "receitas": receitas,
        "historico": historico,
        "compras": [compra_json(linha, agora) for linha in extrato if linha.item_id == item.id],
        "rascunho_chat": f"O que eu posso fazer com {falar(item.nome).minusculo}?",
    }


def eventos_json(sessao: Sessao, limite: int = 50, cursor: str | None = None) -> dict[str, Any]:
    """`GET /api/despensa/eventos`: as mudanças dela, da mais nova para a mais antiga.

    Paginada por cursor: `proximo_cursor` é o id do último evento da página
    (`ev-0012`), e a página seguinte traz os anteriores a ele. `None` quando
    não há mais nada.
    """
    from mise.despensa_editavel import id_do_rotulo  # noqa: PLC0415

    estado = sessao.editavel.estado()
    por_id = {linha.id: linha for linha in sessao.dossie.extrato()}
    agora = sessao.dossie.agora()
    eventos = list(reversed(estado.eventos))
    if cursor:
        try:
            anterior_a = id_do_rotulo(cursor)
        except ErroMise:
            raise ErroDeUso("cursor inválido", cursor=cursor) from None
        eventos = [e for e in eventos if e.id < anterior_a]
    pagina = eventos[:limite]
    return {
        "eventos": [evento_json(e, estado, por_id, agora) for e in pagina],
        "proximo_cursor": pagina[-1].rotulo if len(eventos) > limite else None,
        "total": len(estado.eventos),
        "versao": estado.versao,
    }


# --------------------------------------------------------------------------- #
# O que cada mudança diz
# --------------------------------------------------------------------------- #


def _na_unidade(valor: object, unidade: str) -> str:
    """ "1,5 kg", "4 embalagens", "24 unidades": a quantidade na unidade da linha."""
    numero = _numero_bruto(valor)
    rotulo = unidade.strip()
    if not rotulo or valor is None:
        return numero
    if rotulo.lower() in {"kg", "g", "mg", "l", "ml"}:
        return f"{numero} {rotulo}"
    try:
        quantas = Decimal(str(valor))
    except ArithmeticError:
        return numero
    if rotulo.lower() in _CONTAGEM:
        return f"{numero} {'unidade' if quantas == 1 else 'unidades'}"
    return f"{numero} {_embalagem(rotulo, quantas)}"


def _campo_texto(campo: str, antes: object, depois: object, unidade: str) -> str:
    de_para = f"de {_na_unidade(antes, unidade)} para {_na_unidade(depois, unidade)}"
    if campo == "estoque":
        return f"estoque {de_para}"
    if campo == "quantidade_comprada":
        return f"quantidade comprada {de_para}"
    if campo == "preco_pago":
        return f"preço de {_dinheiro_bruto(antes)} para {_dinheiro_bruto(depois)}"
    if campo == "unidade":
        return f"unidade de {antes} para {depois}"
    if campo == "categoria":
        return (
            f"categoria de {categorias.categoria(str(antes)).rotulo} para "
            f"{categorias.categoria(str(depois)).rotulo}"
        )
    return ""


def _numero_bruto(valor: object) -> str:
    if valor is None:
        return "nada"
    try:
        return numero_texto(Decimal(str(valor)))
    except ArithmeticError:
        return str(valor)


def _dinheiro_bruto(valor: object) -> str:
    if valor is None:
        return "não informado"
    try:
        return str(Dinheiro(Decimal(str(valor))))
    except ArithmeticError:
        return str(valor)


def _conteudo_da_unidade(unidade: object) -> str:
    """ "un 1kg" → "1 kg": o peso que ela informou, como ela lê."""
    from mise.unidades import interpretar_unidade_compra  # noqa: PLC0415

    try:
        lida = interpretar_unidade_compra(str(unidade))
    except ErroMise:
        return str(unidade)
    return (
        quantidade_texto(lida.conteudo_por_embalagem)
        if lida.conteudo_por_embalagem
        else str(unidade)
    )


def _valor_devolvido(evento: Evento, extrato: Mapping[int, LinhaDoExtrato]) -> Dinheiro:
    total = Dinheiro.zero()
    for id_ in evento.dados.get("estornos", []):
        linha = extrato.get(int(id_))
        if linha is not None:
            total = total - linha.valor
    return total


def _valor_da_compra(evento: Evento, extrato: Mapping[int, LinhaDoExtrato]) -> Dinheiro | None:
    compra_id = evento.dados.get("compra_id")
    linha = extrato.get(int(compra_id)) if isinstance(compra_id, int) else None
    return linha.valor if linha is not None else None


def texto_do_evento(  # noqa: PLR0911
    evento: Evento,
    nome: str,
    extrato: Mapping[int, LinhaDoExtrato],
    unidade: str = "",
) -> str:
    """A mudança em uma frase, para o histórico.

    `unidade` é a da linha do item, para a quantidade que a correção não mudou de
    unidade sair escrita nela ("de 2 kg para 1,5 kg").
    """
    from mise.despensa_editavel import Acao, TipoDeEvento  # noqa: PLC0415

    devolvido = _valor_devolvido(evento, extrato)
    compra = _valor_da_compra(evento, extrato)
    if evento.tipo is TipoDeEvento.ADICIONAR:
        dados = evento.dados.get("linha", {})
        origem = str(dados.get("origem", ""))
        if origem == OrigemDoItem.ORCAMENTO.value:
            return f"A senhora comprou com os complementos: {_resumo_da_linha(evento)}."
        return f"A senhora acrescentou o que já tinha: {_resumo_da_linha(evento)}."
    if evento.tipo is TipoDeEvento.REMOVER:
        if evento.acao is Acao.ESTORNO:
            return f"A compra voltou para os complementos ({devolvido}) e o item saiu da despensa."
        prefixo = (
            "Desfeito: saiu da despensa." if evento.acao is Acao.DESFAZER else "Tirado da despensa."
        )
        return f"{prefixo} {devolvido} voltaram para os complementos." if devolvido else prefixo
    if evento.tipo is TipoDeEvento.RESTAURAR:
        base = "Voltou para a despensa."
        return f"{base} {compra} saíram de novo dos complementos." if compra else base
    campos = evento.dados.get("campos", {})
    antes = evento.dados.get("antes", {})
    if evento.acao is Acao.ACABOU:
        return "A senhora avisou que acabou."
    if evento.acao is Acao.INFORMAR_EMBALAGEM:
        return f"Embalagem de {_conteudo_da_unidade(campos.get('unidade'))} informada."
    unidade = str(campos.get("unidade") or unidade)
    detalhes = [
        texto
        for campo in ("estoque", "quantidade_comprada", "preco_pago", "unidade", "categoria")
        if campo in campos
        and (texto := _campo_texto(campo, antes.get(campo), campos[campo], unidade))
    ]
    corpo = "; ".join(detalhes) or "dados corrigidos"
    prefixo = "Desfeita a correção" if evento.acao is Acao.DESFAZER else "Corrigido"
    texto = f"{prefixo}: {corpo}."
    if devolvido and compra is not None:
        texto += f" Voltaram {devolvido} e saíram {compra} dos complementos."
    return texto


def _resumo_da_linha(evento: Evento) -> str:
    """ "2 embalagens de 200 g por R$ 9,00", a partir da linha gravada no evento."""
    from mise.despensa_editavel import linha_do_evento  # noqa: PLC0415

    try:
        linha = linha_do_evento(evento)
        item, _ = montar_ingrediente(linha)
    except (ErroMise, KeyError, ValueError, ArithmeticError):
        return str(evento.dados.get("linha", {}).get("nome", "item"))
    if item.origem is OrigemDoItem.ORCAMENTO:
        return comprado_texto(item)
    if not item.preco_informado:
        return f"{estoque_texto(item)}, sem o preço"
    return f"{estoque_texto(item)}, pagou {item.preco_pago}"


# --------------------------------------------------------------------------- #
# A resposta de uma mudança
# --------------------------------------------------------------------------- #


def texto_da_mudanca(mudanca: Mudanca, orcamento: EstadoOrcamento) -> str:  # noqa: PLR0911, PLR0912
    """O que o agente (ou a tela) diz depois de uma mudança.

    Com o gênero do nome conhecido, a frase leva o artigo e concorda com ele
    ("Anotei o creme de leite.", "Anotei que as alcaparras acabaram."). Sem o
    gênero, a frase é outra, uma que não precisa de artigo ("Anotei na despensa:
    tahine."), em vez de sair capenga.
    """
    from mise.despensa_editavel import Acao, TipoDeEvento  # noqa: PLC0415

    if mudanca.repetida:
        return "Isso já estava anotado."
    nome = falar(mudanca.nome)
    o_nome = nome.com_artigo()
    if mudanca.evento is None:
        estava = nome.verbo("estava", "estavam")
        if o_nome is None:
            return f"Nada mudou: {nome.minusculo} já {estava} assim."
        return f"Nada mudou {nome.contraido('em')}: já {estava} assim."
    evento = mudanca.evento
    restam = f"restam {orcamento.restante}"
    if evento.tipo is TipoDeEvento.ADICIONAR:
        anotei = f"Anotei {o_nome}." if o_nome else f"Anotei na despensa: {nome.minusculo}."
        if mudanca.compra is not None:
            return f"{anotei} Saíram {mudanca.compra.valor} dos complementos; {restam}."
        return f"{anotei} Como a senhora já tinha, não mexi nos complementos."
    if evento.tipo is TipoDeEvento.REMOVER:
        if mudanca.estornos:
            devolvi = f"devolvi {mudanca.estornado} aos complementos; {restam}."
            if o_nome:
                return f"Tirei {o_nome} e {devolvi}"
            return f"Tirei da despensa: {nome.minusculo}. {_maiuscula(devolvi)}"
        if o_nome:
            return f"Tirei {o_nome} da despensa. Não mexi nos complementos."
        return f"Tirei da despensa: {nome.minusculo}. Não mexi nos complementos."
    if evento.tipo is TipoDeEvento.RESTAURAR:
        # Volta com o mesmo artigo com que saiu: "Tirei as alcaparras", "Voltei as alcaparras".
        voltou = (
            f"Voltei {o_nome} para a despensa."
            if o_nome
            else f"Voltou para a despensa: {nome.minusculo}."
        )
        if mudanca.compra is not None:
            return f"{voltou} Saíram de novo {mudanca.compra.valor} dos complementos; {restam}."
        return voltou
    depois = mudanca.depois
    sai = nome.verbo("sai", "saem")
    if evento.acao is Acao.ACABOU:
        if o_nome:
            return f"Anotei que {o_nome} {nome.verbo('acabou', 'acabaram')}."
        return f"Anotei: {nome.minusculo} acabou."
    if evento.acao is Acao.INFORMAR_EMBALAGEM and depois is not None:
        conteudo = _conteudo_da_unidade(depois.linha.unidade)
        if not custo_conhecido(depois):
            # Sem o preço, a embalagem sozinha não dá o custo: dizer "sai a" deixaria a frase
            # sem valor.
            return (
                f"Anotei {conteudo} na embalagem {nome.de()}. Falta o preço que a senhora pagou "
                "para saber o custo."
            )
        if o_nome:
            return f"Com {conteudo} na embalagem, {o_nome} {sai} a {custo_texto(depois)}."
        return (
            f"Com {conteudo} na embalagem, o custo de {nome.minusculo} fica em "
            f"{custo_texto(depois)}."
        )
    custo = f" Agora {sai} a {custo_texto(depois)}." if depois and custo_conhecido(depois) else ""
    dinheiro = ""
    if mudanca.compra is not None:
        dinheiro = f" Os complementos acompanharam o valor novo; {restam}."
    if evento.acao is Acao.DESFAZER:
        if nome.conhecido:
            feito = f"Desfiz a última correção {nome.contraido('de')}."
        else:
            feito = f"Desfiz a última correção: {nome.minusculo} voltou como estava."
    elif o_nome:
        feito = f"Corrigi {o_nome}."
    else:
        feito = f"Corrigi na despensa: {nome.minusculo}."
    return f"{feito}{custo}{dinheiro}"


def _ingrediente_resumo(item: Ingrediente | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "estoque": estoque_texto(item),
        "pago": str(item.preco_pago) if item.preco_informado else None,
        "custo_unitario": custo_texto(item),
        "derivacao": derivacao_texto(item),
        "confianca": item.custo.confianca.value,
    }


def mudanca_json(sessao: Sessao, mudanca: Mudanca, afetadas: dict[str, Any]) -> dict[str, Any]:
    """A resposta de uma escrita na despensa, a mesma para a tela e para o agente."""
    despensa = sessao.despensa
    usos = receitas_por_item(despensa, sessao.candidatas)
    estado_do_orcamento = sessao.dossie.orcamento()
    resolvida = mudanca.pendencia_resolvida
    dinheiro_mexeu = mudanca.compra is not None or bool(mudanca.estornos)
    return {
        "item": (
            item_json(mudanca.depois, despensa, len(usos.get(mudanca.depois.nome, [])))
            if mudanca.depois is not None
            else None
        ),
        "id": mudanca.item_id,
        "ingrediente": mudanca.nome,
        "mudou": mudanca.mudou,
        "repetida": mudanca.repetida,
        "evento": mudanca.evento.rotulo if mudanca.evento is not None else None,
        "antes": _ingrediente_resumo(mudanca.antes),
        "depois": _ingrediente_resumo(mudanca.depois),
        "removido": mudanca.item_id if mudanca.depois is None and mudanca.evento else None,
        "estorno": dinheiro_json(mudanca.estornado) if mudanca.estornos else None,
        "compra": dinheiro_json(mudanca.compra.valor) if mudanca.compra is not None else None,
        "pendencias_resolvidas": [resolvida.ingrediente] if resolvida is not None else [],
        "pendencia": (
            pendencia_json(mudanca.pendencia_depois, despensa)
            if mudanca.pendencia_depois is not None and mudanca.depois is not None
            else None
        ),
        "receitas_afetadas": afetadas,
        "orcamento": orcamento_da_sessao(sessao),
        "orcamento_mudou": dinheiro_mexeu,
        "texto": texto_da_mudanca(mudanca, estado_do_orcamento),
    }


def estorno_json(
    sessao: Sessao, estorno: LinhaDoExtrato, mudanca: Mudanca | None, afetadas: dict[str, Any]
) -> dict[str, Any]:
    """A resposta de `POST /api/compras/{id}/estorno`."""
    estado = sessao.dossie.orcamento()
    devolvido = -estorno.valor
    texto = f"Devolvi {devolvido} aos complementos; restam {estado.restante}."
    if mudanca is not None and mudanca.evento is not None:
        nome = falar(mudanca.nome)
        if nome.conhecido:
            saiu = nome.verbo("saiu", "saíram")
            texto += f" {nome.com_artigo(maiuscula=True)} {saiu} da despensa."
        else:
            texto += f" Saiu da despensa: {nome.maiusculo}."
    return {
        "compra_id": estorno.estorna,
        "estorno_id": estorno.id,
        "estorno": dinheiro_json(devolvido),
        "removido": mudanca.item_id if mudanca is not None else None,
        "receitas_afetadas": afetadas,
        "orcamento": orcamento_da_sessao(sessao),
        "texto": texto,
    }


__all__ = [
    "FUSO",
    "ORDENS",
    "ORIGEM_ROTULO",
    "UNIDADES_DA_EMBALAGEM",
    "comprado_texto",
    "confianca_rotulo",
    "custo_conhecido",
    "custo_texto",
    "custo_unitario_json",
    "data_hora_texto",
    "derivacao_texto",
    "detalhe",
    "dinheiro_json",
    "estoque_texto",
    "estorno_json",
    "evento_json",
    "eventos_json",
    "fracao_texto",
    "item_json",
    "listar",
    "mudanca_json",
    "numero_texto",
    "o_item",
    "orcamento_da_sessao",
    "orcamento_json",
    "pendencia_json",
    "quando_texto",
    "quantidade_texto",
    "receitas_afetadas",
    "receitas_por_item",
    "receitas_texto",
    "resumo_do_orcamento",
    "slug_da_receita",
    "texto_da_mudanca",
    "texto_do_evento",
    "vereditos",
]


def o_item(nome: str) -> str:
    """O item com o artigo que ele pede: "a cobertura de chocolate", "os ovos", "o sal".

    Sem o gênero conhecido, o nome sozinho ("tahine"), porque artigo errado é pior
    que nenhum.
    """
    falado = falar(nome)
    com_artigo = falado.com_artigo()
    return com_artigo if com_artigo is not None else falado.minusculo
