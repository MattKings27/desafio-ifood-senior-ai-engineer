"""As rotas da despensa: a lista, o item, as mudanças dela, a planilha em texto e o estorno.

As formas estão em `contratos/web/despensa.json`, `despensa-item.json` e
`despensa-escrita.json`, e são montadas em `mise.despensa_json`, as mesmas que a
ferramenta do agente devolve: a tela e a conversa dizem a mesma coisa do mesmo
item.

Escritas aceitam a chave de idempotência no cabeçalho `Idempotency-Key` ou em
`id_cliente` no corpo: o mesmo clique reenviado não grava duas vezes, nem
debita duas vezes. Um item que não existe sai com a categoria `ausente` (404).

Os R$ 80,00: acrescentar com `origem: "orcamento"` ("comprei com os R$ 80")
debita na hora, e tirar esse item devolve. Acrescentar o que ela já tinha e
editar os itens da planilha não mexem no orçamento.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Final, Literal

from fastapi import APIRouter, Header, Query
from fastapi.responses import PlainTextResponse
from mise import despensa_json as dj
from mise.despensa import OrigemDoItem
from mise.despensa_editavel import Acao, chave_do_nome, id_do_rotulo
from mise.erros import ErroDeUso
from pydantic import AliasChoices, BaseModel, Field

from gateway.rotas._comum import RespostaPadrao, SessaoDaApp, responder

#: Tamanho máximo de uma chave de idempotência vinda da tela.
TAMANHO_DA_CHAVE: Final = 200

roteador = APIRouter(tags=["despensa"])

ChaveDoCabecalho = Annotated[
    str | None,
    Header(alias="Idempotency-Key", min_length=1, max_length=TAMANHO_DA_CHAVE),
]


class NovoItemBody(BaseModel):
    """Um item que ela acrescenta: o que já tinha, ou o que comprou com os complementos."""

    nome: str = Field(min_length=1, max_length=80)
    estoque: float = Field(ge=0)
    unidade: str = Field(min_length=1, max_length=40)
    quantidade_comprada: float | None = Field(default=None, gt=0)
    preco_pago: float | None = Field(default=None, ge=0)
    origem: Literal["ja_tinha", "orcamento"] = "ja_tinha"
    categoria: str | None = Field(default=None, max_length=40)
    #: O prato para o qual ela comprou, quando comprou com os complementos. A tela
    #: manda como `receita`; `prato` também vale.
    prato: str | None = Field(
        default=None, max_length=200, validation_alias=AliasChoices("prato", "receita")
    )
    motivo: str = Field(default="", max_length=300)
    id_cliente: str | None = Field(default=None, min_length=1, max_length=TAMANHO_DA_CHAVE)


class CorrecaoBody(BaseModel):
    """O que ela corrige num item. O nome não muda.

    `conteudo_da_embalagem` ("1 kg", "400 g") responde "quanto vem na
    embalagem?"; `conteudo_por_embalagem` é aceito com o mesmo sentido.
    """

    #: Só para recusar com o motivo: o nome de um item não muda.
    nome: str | None = Field(default=None, max_length=80)
    estoque: float | None = Field(default=None, ge=0)
    unidade: str | None = Field(default=None, min_length=1, max_length=40)
    quantidade_comprada: float | None = Field(default=None, gt=0)
    preco_pago: float | None = Field(default=None, ge=0)
    categoria: str | None = Field(default=None, max_length=40)
    conteudo_da_embalagem: str | None = Field(
        default=None,
        max_length=40,
        validation_alias=AliasChoices("conteudo_da_embalagem", "conteudo_por_embalagem"),
    )
    motivo: str = Field(default="", max_length=300)
    id_cliente: str | None = Field(default=None, min_length=1, max_length=TAMANHO_DA_CHAVE)


class ChaveBody(BaseModel):
    """Só a chave de idempotência, para desfazer e estornar."""

    id_cliente: str | None = Field(default=None, min_length=1, max_length=TAMANHO_DA_CHAVE)


def _decimal(valor: float | None) -> Decimal | None:
    return Decimal(str(valor)) if valor is not None else None


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #


Ordem = Literal["valor", "nome", "custo", "categoria"]


@roteador.get("/api/despensa", response_model=RespostaPadrao)
def despensa(
    sessao: SessaoDaApp,
    q: Annotated[str | None, Query(max_length=80)] = None,
    categoria: Annotated[str | None, Query(max_length=40)] = None,
    ordem: Ordem = "valor",
) -> RespostaPadrao:
    """A despensa de agora: itens com a conta, as perguntas em aberto e os R$ 80,00.

    `q` procura no nome (sem ligar para acento e caixa), `categoria` filtra pelo
    id da categoria, e `ordem` é `valor` (o que mais custou primeiro), `nome`,
    `custo` (custo unitário) ou `categoria`. O total e as categorias contam a
    despensa inteira, com ou sem filtro.
    """
    return responder(lambda: dj.listar(sessao, q=q, categoria=categoria, ordem=ordem))


@roteador.get("/api/despensa/itens", response_model=RespostaPadrao)
def listar_itens(
    sessao: SessaoDaApp,
    q: Annotated[str | None, Query(max_length=80)] = None,
    categoria: Annotated[str | None, Query(max_length=40)] = None,
    ordem: Ordem = "valor",
) -> RespostaPadrao:
    """Só os itens, com os mesmos filtros de `/api/despensa`."""

    def montar() -> dict[str, Any]:
        lista = dj.listar(sessao, q=q, categoria=categoria, ordem=ordem)
        return {k: lista[k] for k in ("itens", "total_itens", "encontrados", "categorias")}

    return responder(montar)


@roteador.get("/api/despensa/itens/{item_id}", response_model=RespostaPadrao)
def item(item_id: str, sessao: SessaoDaApp) -> RespostaPadrao:
    """O item: a conta do custo por unidade, as receitas que o usam, as compras e a história."""
    return responder(lambda: dj.detalhe(sessao, item_id))


@roteador.get("/api/despensa/eventos", response_model=RespostaPadrao)
def eventos(
    sessao: SessaoDaApp,
    limite: Annotated[int, Query(ge=1, le=500)] = 50,
    cursor: Annotated[str | None, Query(max_length=20)] = None,
) -> RespostaPadrao:
    """As mudanças dela na despensa, da mais nova para a mais antiga, com o que dá para desfazer.

    `cursor` é o `proximo_cursor` da página anterior.
    """
    return responder(lambda: dj.eventos_json(sessao, limite, cursor))


@roteador.get("/api/despensa/planilha.txt", response_class=PlainTextResponse)
def planilha_txt(sessao: SessaoDaApp) -> PlainTextResponse:
    """A planilha dela em texto (UTF-8): a mesma que o agente lê em `consultar_planilha`."""
    versao, texto = sessao.atualizar_planilha_txt()
    return PlainTextResponse(
        texto,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="despensa.txt"',
            "X-Versao-Da-Planilha": str(versao),
        },
    )


# --------------------------------------------------------------------------- #
# Escrita
# --------------------------------------------------------------------------- #


@roteador.post("/api/despensa/itens", response_model=RespostaPadrao)
def adicionar(
    corpo: NovoItemBody, sessao: SessaoDaApp, idempotency_key: ChaveDoCabecalho = None
) -> RespostaPadrao:
    """Acrescenta um item. `origem: "orcamento"` debita os R$ 80,00 na hora."""

    def montar() -> dict[str, Any]:
        mudanca, afetadas = sessao.mudar_despensa(
            lambda e: e.adicionar(
                nome=corpo.nome,
                estoque=Decimal(str(corpo.estoque)),
                unidade=corpo.unidade,
                quantidade_comprada=_decimal(corpo.quantidade_comprada),
                preco_pago=_decimal(corpo.preco_pago),
                origem=OrigemDoItem(corpo.origem),
                categoria=corpo.categoria,
                prato=corpo.prato,
                motivo=corpo.motivo,
                chave=idempotency_key or corpo.id_cliente,
                canal=sessao.canal,
            )
        )
        return dj.mudanca_json(sessao, mudanca, afetadas)

    return responder(montar)


@roteador.patch("/api/despensa/itens/{item_id}", response_model=RespostaPadrao)
def corrigir(
    item_id: str,
    corpo: CorrecaoBody,
    sessao: SessaoDaApp,
    idempotency_key: ChaveDoCabecalho = None,
) -> RespostaPadrao:
    """Corrige o item: estoque, unidade, quanto comprou ou pagou, categoria ou a embalagem."""

    def montar() -> dict[str, Any]:
        if corpo.nome is not None:
            atual = sessao.editavel.item(item_id)
            if chave_do_nome(corpo.nome) != chave_do_nome(atual.nome):
                raise ErroDeUso(
                    "o nome de um item não muda: cotações e compras usam o nome como chave; "
                    "tire o item e acrescente com o nome novo",
                    id=item_id,
                )
        mudanca, afetadas = sessao.mudar_despensa(
            lambda e: e.corrigir(
                item_id,
                estoque=_decimal(corpo.estoque),
                unidade=corpo.unidade,
                quantidade_comprada=_decimal(corpo.quantidade_comprada),
                preco_pago=_decimal(corpo.preco_pago),
                categoria=corpo.categoria,
                conteudo_da_embalagem=corpo.conteudo_da_embalagem,
                acao=_acao_da_correcao(corpo),
                motivo=corpo.motivo,
                chave=idempotency_key or corpo.id_cliente,
                canal=sessao.canal,
            )
        )
        return dj.mudanca_json(sessao, mudanca, afetadas)

    return responder(montar)


def _acao_da_correcao(corpo: CorrecaoBody) -> Acao:
    """Como o histórico conta a correção: a embalagem informada, o "acabou" ou a correção."""
    campos = set(corpo.model_dump(exclude_none=True, exclude={"motivo", "id_cliente", "nome"}))
    if corpo.conteudo_da_embalagem and campos <= {"conteudo_da_embalagem"}:
        return Acao.INFORMAR_EMBALAGEM
    if corpo.estoque == 0 and campos == {"estoque"}:
        return Acao.ACABOU
    return Acao.CORRIGIR


@roteador.delete("/api/despensa/itens/{item_id}", response_model=RespostaPadrao)
def remover(
    item_id: str,
    sessao: SessaoDaApp,
    motivo: Annotated[str, Query(max_length=300)] = "",
    id_cliente: Annotated[str | None, Query(min_length=1, max_length=TAMANHO_DA_CHAVE)] = None,
    idempotency_key: ChaveDoCabecalho = None,
) -> RespostaPadrao:
    """Tira o item. Se ela o comprou com os complementos, o valor volta para os R$ 80,00."""

    def montar() -> dict[str, Any]:
        mudanca, afetadas = sessao.mudar_despensa(
            lambda e: e.remover(
                item_id,
                motivo=motivo,
                chave=idempotency_key or id_cliente,
                canal=sessao.canal,
            )
        )
        return dj.mudanca_json(sessao, mudanca, afetadas)

    return responder(montar)


@roteador.post("/api/despensa/eventos/{evento_id}/desfazer", response_model=RespostaPadrao)
def desfazer(
    evento_id: str,
    sessao: SessaoDaApp,
    corpo: ChaveBody | None = None,
    idempotency_key: ChaveDoCabecalho = None,
) -> RespostaPadrao:
    """Desfaz a última mudança de um item (`ev-0012` ou `12`), com um evento novo."""

    def montar() -> dict[str, Any]:
        numero = id_do_rotulo(evento_id)
        mudanca, afetadas = sessao.mudar_despensa(
            lambda e: e.desfazer(
                numero,
                chave=idempotency_key or (corpo.id_cliente if corpo else None),
                canal=sessao.canal,
            )
        )
        return dj.mudanca_json(sessao, mudanca, afetadas)

    return responder(montar)


@roteador.post("/api/compras/{compra_id}/estorno", response_model=RespostaPadrao)
def estornar(
    compra_id: int,
    sessao: SessaoDaApp,
    corpo: ChaveBody | None = None,
    idempotency_key: ChaveDoCabecalho = None,
) -> RespostaPadrao:
    """Devolve uma compra aos R$ 80,00. Devolver de novo a mesma compra não devolve duas vezes.

    Se a compra acrescentou um item na despensa, o item sai junto. A chave de
    idempotência é aceita por simetria com as outras escritas: a própria compra
    já é a identidade do estorno.
    """
    del corpo, idempotency_key

    def montar() -> dict[str, Any]:
        (estorno, mudanca), afetadas = sessao.mudar_despensa(
            lambda e: e.estornar_compra(compra_id, canal=sessao.canal)
        )
        return dj.estorno_json(sessao, estorno, mudanca, afetadas)

    return responder(montar)


__all__ = ["CorrecaoBody", "NovoItemBody", "roteador"]
