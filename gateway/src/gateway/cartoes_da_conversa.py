"""Os cards da conversa: de qual chamada, com quais dados do motor, apontando para onde.

`gateway.cartoes.cartao_para` diz que card uma chamada do agente gera e de
qual rota vêm os dados, ainda como modelo (`/api/receitas/{slug}`) e com os
argumentos crus do modelo. Aqui o card vira coisa concreta:

1. **A rota é resolvida** para um recurso que existe: a receita pelo id, pelo
   nome ou pelo endereço, entre as que estão em avaliação e no catálogo; o
   ingrediente pelo nome, pelo mesmo casamento que o motor usa. O que não se
   resolve não vira card: um card apontando para nada é pior que nenhum.
2. **Os dados vêm da própria API**, em processo, pela rota que a tela chamaria
   (`GET` no app, sem rede). É a mesma função, com a mesma forma de `dados`.
3. **Sem a API por perto, ou sem a rota**, o card sai com dados mínimos,
   tirados do motor, com os nomes de campo do contrato. Os cards de receita
   (`receita`, `viabilidade`, `comparacao`, `custo_porcao`) montam os dados
   pelas mesmas funções das rotas (`mise.receitas_json`), e saem iguais. Rota
   que existe e recusa (o prato que o portão não liberou) não dá card.
4. **Nenhum número vem do texto do modelo**: dos argumentos só sai o que
   identifica o recurso, e os valores saem do motor.

Também moram aqui as respostas rápidas que cada card sugere (`sugestoes_para`).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import quote, urlencode

from gateway.cartoes import Cartao, Valor

if TYPE_CHECKING:
    from mise.despensa import Ingrediente
    from mise.mcp_server import Sessao
    from mise.receita import Receita

logger = logging.getLogger(__name__)

#: Busca uma rota da API em processo: `(status, corpo JSON)`.
Buscar = Callable[[str], Awaitable[tuple[int, Any]]]

#: Cards que mostram dinheiro: no histórico, são "conta de hoje, 14:32".
TIPOS_COM_DINHEIRO: Final = frozenset(
    {
        "despensa_resumo",
        "ingrediente",
        "viabilidade",
        "comparacao",
        "orcamento",
        "custo_porcao",
        "cenarios",
        "ponto_de_preco",
        "preco_preliminar",
        "decisao",
    }
)

#: Quantos itens parados o resumo da despensa mostra.
MAIORES_PARADOS: Final = 3

#: Os parâmetros de card que apontam uma receita (`gateway.cartoes`).
_IDENTIFICAM_A_RECEITA: Final = ("receita_id", "prato", "url")

#: Os campos de uma pendência no resumo da despensa (`visao-geral.json#pendencias`).
_CAMPOS_DA_PENDENCIA: Final = frozenset(
    {
        "id",
        "ingrediente",
        "pergunta",
        "impacto",
        "impacto_texto",
        "resposta_inline",
        "rascunho_chat",
        "rota",
    }
)


# --------------------------------------------------------------------------- #
# Ids do contrato                                                              #
# --------------------------------------------------------------------------- #


def slug(texto: str) -> str:
    """`Óleo de soja` → `oleo-de-soja`: o id de item da planilha (`mise.despensa.id_do_item`)."""
    from mise.despensa import id_do_item  # noqa: PLC0415

    return id_do_item(texto)


def url_canonica(url: str) -> str:
    """Host minúsculo sem `www.`, caminho sem barra final; a regra de `mise.catalogo`."""
    from mise.catalogo import url_canonica as do_catalogo  # noqa: PLC0415

    return do_catalogo(url)


def slug_da_receita(receita: Receita) -> str:
    """O id da receita no contrato, o mesmo que a despensa usa (`despensa_json.slug_da_receita`).

    16 hex do sha256 da URL canônica, ou o slug do nome. Provisório até o
    catálogo de receitas dar o id definitivo: é lá que muda, e aqui acompanha.
    """
    from mise.despensa_json import slug_da_receita as da_despensa  # noqa: PLC0415

    return da_despensa(receita)


def id_do_ingrediente(item: Ingrediente) -> str:
    """O id do item: o que a despensa editável der, senão o slug do nome."""
    proprio = getattr(item, "id", None)
    return proprio if isinstance(proprio, str) and proprio else slug(item.nome)


def _dinheiro(valor: Any) -> dict[str, Any]:
    return {"valor": float(valor.arredondado().valor), "texto": str(valor)}


def _minuscula(texto: str) -> str:
    primeira = texto.split(" ", 1)[0]
    return texto if len(primeira) > 1 and primeira.isupper() else texto[:1].lower() + texto[1:]


# --------------------------------------------------------------------------- #
# A referência resolvida                                                       #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class RefResolvida:
    """O card com a rota concreta e o recurso que ela aponta."""

    tipo_cartao: str
    rota: str | None
    parametros: dict[str, Valor]
    #: A receita em avaliação que o card aponta, quando aponta uma.
    receita: str | None = None
    #: O item da despensa que o card aponta, quando aponta um.
    ingrediente: str | None = None

    @property
    def chave(self) -> str:
        """O que faz dois cards do mesmo turno serem o mesmo card."""
        if self.rota is None:
            return self.tipo_cartao
        return f"{self.tipo_cartao} {self.rota}"


def _mesma_url(a: str, b: str) -> bool:
    return url_canonica(a) == url_canonica(b)


def _com_consulta(rota: str, parametros: dict[str, Valor]) -> str:
    if not parametros:
        return rota
    return f"{rota}?{urlencode({k: str(v) for k, v in parametros.items()}, quote_via=quote)}"


class MontadorDeCartoes:
    """Resolve a referência e monta os dados de cada card, a partir da sessão do app."""

    def __init__(
        self, sessao: Sessao, buscar: Buscar | None, relogio: Callable[[], datetime]
    ) -> None:
        self._sessao = sessao
        self._buscar = buscar
        self._relogio = relogio

    @property
    def sessao(self) -> Sessao:
        """A sessão do app, de onde saem os dados dos cards."""
        return self._sessao

    # -- resolução --------------------------------------------------------- #

    def _receita(self, parametros: dict[str, Valor]) -> Receita | None:
        """A receita que o card aponta, na precedência da ferramenta.

        O primeiro identificador dos parâmetros decide (a ordem é a da
        ferramenta, em `gateway.cartoes`): pelo id, só pelo id; pelo nome, o
        nome e depois o endereço, que vêm da mesma receita. Vale a receita em
        avaliação e a do catálogo: a receita que o agente acabou de trazer
        da internet está no catálogo, e ainda não em avaliação.
        """
        primeiro = next((k for k in parametros if k in _IDENTIFICAM_A_RECEITA), None)
        if primeiro == "receita_id":
            return self._pelo_id(parametros["receita_id"])
        prato, url = parametros.get("prato"), parametros.get("url")
        if isinstance(prato, str):
            achada = self._sessao.dossie.candidata(prato)
            if achada is None and (do_catalogo := self._sessao.catalogo.por_nome(prato)):
                achada = do_catalogo.receita
            if achada is not None:
                return achada
        if isinstance(url, str):
            lida = self._sessao.catalogo.por_url(url)
            if lida is not None:
                return lida.receita
            for receita in self._sessao.candidatas.values():
                if receita.url and _mesma_url(receita.url, url):
                    return receita
        return None

    def _pelo_id(self, receita_id: object) -> Receita | None:
        """A receita com este id, em avaliação ou no catálogo, pela mesma busca das ferramentas."""
        from mise.erros import Ausente  # noqa: PLC0415

        if not isinstance(receita_id, str):
            return None
        try:
            return self._sessao.receita_por_id(receita_id)
        except Ausente:
            return None

    def _ingrediente(self, nome: object) -> Ingrediente | None:
        """O item de que o agente falou, pelo id ou pelo nome, como a ferramenta dele acha.

        Nome que não casa com nenhum item não vira card: nunca um 404 na tela.
        """
        from mise.erros import Ausente  # noqa: PLC0415
        from mise.ferramentas.despensa import item_da_conversa  # noqa: PLC0415

        if not isinstance(nome, str) or not nome.strip():
            return None
        try:
            return item_da_conversa(self._sessao.despensa, nome)
        except Ausente:
            return None

    def resolver(self, cartao: Cartao) -> RefResolvida | None:
        """A rota concreta do card, ou `None` quando o recurso não existe."""
        tipo = cartao["tipo_cartao"]
        modelo = cartao["ref"]["rota"]
        parametros = dict(cartao["ref"]["parametros"])
        if modelo is None:
            return RefResolvida(tipo, None, parametros)
        if "{slug}" in modelo:
            receita = self._receita(parametros)
            if receita is None:
                return None
            chave = slug_da_receita(receita)
            parametros = {"slug": chave, "prato": receita.nome}
            rota = modelo.replace("{slug}", quote(chave, safe=""))
            return RefResolvida(tipo, rota, parametros, receita=receita.nome)
        if "{id}" in modelo:
            item = self._ingrediente(parametros.get("ingrediente"))
            if item is None:
                return None
            chave = id_do_ingrediente(item)
            parametros = {"id": chave, "ingrediente": item.nome}
            rota = modelo.replace("{id}", quote(chave, safe=""))
            return RefResolvida(tipo, rota, parametros, ingrediente=item.nome)
        return self._na_consulta(tipo, modelo, parametros)

    def _na_consulta(
        self, tipo: str, modelo: str, parametros: dict[str, Valor]
    ) -> RefResolvida | None:
        """A rota sem marcador, com os parâmetros na consulta (`/api/precos?prato=`).

        As rotas de preço de hoje recebem o prato: o `receita_id` vira o nome da
        receita, e o que não se acha pelo id não vira card.
        """
        if "receita_id" in parametros:
            pelo_id = self._receita(parametros)
            if pelo_id is None:
                return None
            resto = {k: v for k, v in parametros.items() if k not in _IDENTIFICAM_A_RECEITA}
            parametros = {"prato": pelo_id.nome, **resto}
        prato = parametros.get("prato")
        receita = self._sessao.dossie.candidata(prato) if isinstance(prato, str) else None
        if receita is not None:
            parametros["prato"] = receita.nome
        return RefResolvida(
            tipo,
            _com_consulta(modelo, parametros),
            parametros,
            receita=receita.nome if receita is not None else None,
        )

    # -- os dados ---------------------------------------------------------- #

    async def montar(self, cartao: Cartao, *, cartao_id: str) -> dict[str, Any] | None:
        """O card pronto para a tela, ou `None` quando não há o que mostrar."""
        ref = await asyncio.to_thread(self.resolver, cartao)
        if ref is None:
            return None
        return await self.montar_resolvido(ref, cartao_id=cartao_id)

    async def montar_resolvido(self, ref: RefResolvida, *, cartao_id: str) -> dict[str, Any] | None:
        dados: Any = None
        if ref.rota is not None and self._buscar is not None:
            status, corpo = await self._buscar(ref.rota)
            if status == 200 and isinstance(corpo, dict):  # noqa: PLR2004
                if not corpo.get("ok"):
                    return None  # a rota existe e recusou: o portão, por exemplo
                dados = corpo.get("dados")
            elif not _rota_inexistente(status, corpo):
                return None
        if dados is None:
            dados = await asyncio.to_thread(self.dados_minimos, ref)
            if dados is None:
                return None
        return {
            "cartao_id": cartao_id,
            "tipo_cartao": ref.tipo_cartao,
            "ref": {"rota": ref.rota, "parametros": ref.parametros},
            "dados": dados,
            "gerado": self._relogio().isoformat(),
        }

    def dados_minimos(self, ref: RefResolvida) -> dict[str, Any] | None:
        """Os dados do card sem a API por perto, ou sem a rota, com os nomes do contrato."""
        montar = _MINIMOS.get(ref.tipo_cartao)
        if montar is None:
            return None
        try:
            return montar(self, ref)
        except Exception:
            # Card é acessório: um erro aqui nunca derruba o turno.
            logger.exception("não consegui montar os dados do card %s", ref.tipo_cartao)
            return None

    # -- dados mínimos, um por tipo ----------------------------------------- #

    def _despensa_resumo(self, _ref: RefResolvida) -> dict[str, Any]:
        from mise.despensa_json import pendencia_json  # noqa: PLC0415

        despensa = self._sessao.despensa
        total = despensa.total_investido
        maiores = [i for i in despensa.por_valor() if i.preco_informado][:MAIORES_PARADOS]
        return {
            "kpis": {
                "despensa": {
                    "total": _dinheiro(total),
                    "itens": len(despensa),
                    "texto": f"{len(despensa)} ingredientes",
                    "rota": "/despensa",
                }
            },
            "dinheiro_parado": {
                "total_itens": len(despensa),
                "itens": [
                    {
                        "id": id_do_ingrediente(i),
                        "nome": i.nome,
                        "pago": _dinheiro(i.preco_pago),
                        "fracao": round(float(despensa.fracao_de(i)), 4),
                        "fracao_texto": f"{despensa.fracao_de(i):.0%}",
                        "imagem": None,
                        "rota": f"/despensa/{id_do_ingrediente(i)}",
                    }
                    for i in maiores
                ],
            },
            "pendencias": [
                {k: v for k, v in pendencia_json(p, despensa).items() if k in _CAMPOS_DA_PENDENCIA}
                for p in despensa.pendencias
            ],
        }

    def _slug_da_ref(self, ref: RefResolvida) -> str | None:
        """O id da receita do card: o da rota resolvida, ou o da receita pelo nome."""
        slug_do_card = ref.parametros.get("slug")
        if isinstance(slug_do_card, str):
            return slug_do_card
        receita = self._receita({"prato": ref.receita}) if ref.receita else None
        return slug_da_receita(receita) if receita is not None else None

    def _receita_da_ref(self, ref: RefResolvida) -> dict[str, Any] | None:
        """O detalhe da receita (`receita.json`), pela mesma função da rota."""
        from mise import receitas_json  # noqa: PLC0415

        slug_do_card = self._slug_da_ref(ref)
        if slug_do_card is None:
            return None
        return receitas_json.detalhe(self._sessao, slug_do_card)

    def _comparacao(self, _ref: RefResolvida) -> dict[str, Any]:
        """A aba `pode_fazer` da grade, pela mesma função da rota: só o que ela consegue fazer."""
        from mise import receitas_json  # noqa: PLC0415

        return receitas_json.lista(self._sessao, receitas_json.Filtros(aba="pode_fazer"))

    def _custo(self, ref: RefResolvida) -> dict[str, Any] | None:
        """O custo por porção (`custo.json`); receita que a conferência não liberou não tem."""
        from mise import receitas_json  # noqa: PLC0415

        slug_do_card = self._slug_da_ref(ref)
        if slug_do_card is None:
            return None
        try:
            return receitas_json.custo(self._sessao, slug_do_card)
        except receitas_json.CustoRecusado:
            return None

    def _pergunta(self, _ref: RefResolvida) -> dict[str, Any] | None:
        """A pergunta da vez, como `proxima_pergunta` monta, com as opções de resposta."""
        from mise.elicitacao import montar_plano  # noqa: PLC0415

        sessao = self._sessao
        plano = montar_plano(
            list(sessao.candidatas.values()),
            sessao.perfil,
            sessao.despensa,
            avaliador=sessao.avaliar,
        )
        melhor = plano.proxima
        if melhor is None:
            return None
        tipo = melhor.pergunta.tipo.name.lower()
        # A pergunta do gosto é sobre um prato: o campo é o prato, como o motor
        # grava. Com o campo "gosto", o botão dizia "Gosto de fazer gosto." e
        # gravava o gosto de um prato chamado "gosto".
        campo = campo_da_pergunta(tipo, melhor.campo, melhor.receitas_afetadas)
        return {
            "ha_pergunta": True,
            "pergunta": melhor.texto,
            "tipo": tipo,
            "campo": campo,
            "por_que_esta": melhor.justificativa(),
            "pratos_afetados": list(melhor.receitas_afetadas),
            "opcoes": opcoes_da_pergunta(tipo, campo),
        }


def fontes_do_conhecimento(montador: MontadorDeCartoes, ref: RefResolvida) -> dict[str, Any] | None:
    """ "De onde eu tirei isso": as fontes da consulta que o agente acabou de fazer.

    O Hermes não manda a resposta da ferramenta junto com o fim da chamada, só
    os argumentos; então a mesma busca roda de novo aqui, sobre o mesmo corpus
    (`mise.corpus`), que é determinística para o mesmo estado da plataforma.
    Cada trecho vira um chip com a tela dele; o fato da base de cozinha vira um
    chip com o nome da fonte, sem tela. Sem trecho ("não sei"), não há card.
    """
    from mise.corpus import corpus_da_sessao, fontes_do_resultado  # noqa: PLC0415

    pergunta = ref.parametros.get("pergunta")
    if not isinstance(pergunta, str) or not pergunta.strip():
        return None
    return fontes_do_resultado(corpus_da_sessao(montador.sessao).buscar(pergunta))


_MINIMOS: Final[dict[str, Callable[[MontadorDeCartoes, RefResolvida], dict[str, Any] | None]]] = {
    "despensa_resumo": MontadorDeCartoes._despensa_resumo,
    "receita": MontadorDeCartoes._receita_da_ref,
    "viabilidade": MontadorDeCartoes._receita_da_ref,
    "comparacao": MontadorDeCartoes._comparacao,
    "custo_porcao": MontadorDeCartoes._custo,
    "pergunta": MontadorDeCartoes._pergunta,
    "fontes": fontes_do_conhecimento,
}


def campo_da_pergunta(tipo: str, campo: str, pratos: tuple[str, ...] | list[str]) -> str:
    """O campo que a resposta grava: o da cozinha como veio, e o prato na pergunta do gosto."""
    if tipo == "gosto" and pratos:
        return pratos[0]
    return campo


def _rota_inexistente(status: int, corpo: Any) -> bool:
    """404 do próprio FastAPI (a rota não existe), e não o `ausente` do envelope."""
    return status == 404 and isinstance(corpo, dict) and "categoria" not in corpo  # noqa: PLR2004


def gerado_texto(tipo_cartao: str, quando: str) -> str:
    """ "conta de hoje, 14:32" nos cards com dinheiro; nos outros, só o quando."""
    return f"conta de {quando}" if tipo_cartao in TIPOS_COM_DINHEIRO else quando


# --------------------------------------------------------------------------- #
# Opções e sugestões                                                           #
# --------------------------------------------------------------------------- #


def _responder(tipo: str, campo: str, resposta: str) -> dict[str, str]:
    return {"tipo": "responder", "tipo_pergunta": tipo, "campo": campo, "resposta": resposta}


def _sim_nao_sei(
    tipo: str, campo: str, rotulos: tuple[str, str, str], textos: tuple[str, str, str]
) -> list[dict[str, Any]]:
    """Três botões: o sim e o não gravam pelo motor; o "não sei" é só texto para o agente."""
    return [
        {"rotulo": rotulos[0], "texto": textos[0], "acao": _responder(tipo, campo, "sim")},
        {"rotulo": rotulos[1], "texto": textos[1], "acao": _responder(tipo, campo, "nao")},
        {"rotulo": rotulos[2], "texto": textos[2]},
    ]


def opcoes_da_pergunta(tipo: str, campo: str) -> list[dict[str, Any]]:
    """Os botões de resposta: tenho / não tenho / não sei, sei fazer…, gosto… ou nada (número).

    "Não sei" vai como texto, sem ação: quem decide o que fazer com a dúvida é o
    agente, e o motor não grava "não sei" como "não tem".
    """
    from mise.taxonomia import EQUIPAMENTOS_POR_ID, TECNICAS_POR_ID  # noqa: PLC0415

    opcoes: list[dict[str, Any]] = []
    if tipo == "equipamento" and campo in EQUIPAMENTOS_POR_ID:
        nome = _minuscula(EQUIPAMENTOS_POR_ID[campo].nome)
        opcoes = _sim_nao_sei(
            tipo,
            campo,
            ("Tenho", "Não tenho", "Não sei"),
            (f"Tenho {nome}.", f"Não tenho {nome}.", f"Não sei se tenho {nome}."),
        )
    elif tipo == "tecnica" and campo in TECNICAS_POR_ID:
        nome = _minuscula(TECNICAS_POR_ID[campo].nome)
        opcoes = _sim_nao_sei(
            tipo,
            campo,
            ("Sei fazer", "Não sei fazer", "Não tenho certeza"),
            (
                f"Sei fazer {nome}.",
                f"Não sei fazer {nome}.",
                f"Não tenho certeza se sei fazer {nome}.",
            ),
        )
    elif tipo == "operacional" and campo == "tem_gas_sobrando":
        opcoes = _sim_nao_sei(
            tipo,
            campo,
            ("Sim", "Não", "Não sei"),
            ("Tenho gás sobrando.", "Não tenho gás sobrando.", "Não sei se tenho gás sobrando."),
        )
    elif tipo == "gosto" and campo:
        prato = _minuscula(campo)
        opcoes = [
            {
                "rotulo": "Gosto de fazer",
                "texto": f"Gosto de fazer {prato}.",
                "acao": _responder(tipo, campo, "gosta"),
            },
            {
                "rotulo": "Não gosto",
                "texto": f"Não gosto de fazer {prato}.",
                "acao": _responder(tipo, campo, "nao_gosta"),
            },
        ]
    return opcoes


_QUANTO_COBRAR: Final = {"rotulo": "Quanto cobrar?", "texto": "Quanto eu cobro por porção?"}
_OUTRO_PRECO: Final = {"rotulo": "Quero outro preço", "texto": "Quero ver a conta com outro preço."}

_SUGESTOES_FIXAS: Final[dict[str, list[dict[str, Any]]]] = {
    "cenarios": [
        _OUTRO_PRECO,
        {"rotulo": "Vou pensar", "texto": "Vou pensar um pouco antes de decidir o preço."},
    ],
    "custo_porcao": [_QUANTO_COBRAR],
    "receita": [
        {"rotulo": "Dá pra eu fazer?", "texto": "Dá pra eu fazer essa receita?"},
        {"rotulo": "Outra receita", "texto": "Me mostra outra receita com o que eu tenho."},
    ],
    "comparacao": [
        {"rotulo": "Qual aproveita mais?", "texto": "Qual delas aproveita mais o que eu tenho?"}
    ],
    "despensa_resumo": [
        {
            "rotulo": "Receitas com isso",
            "texto": "Que receitas aproveitam o que está parado na despensa?",
        }
    ],
    "decisao": [{"rotulo": "Ver o cardápio", "texto": "Como ficou o meu cardápio?"}],
    "orcamento": [
        {"rotulo": "O que dá pra comprar?", "texto": "O que dá pra comprar com o que sobrou?"}
    ],
}


def _dicionario(valor: object) -> dict[str, Any]:
    return valor if isinstance(valor, dict) else {}


def sugestoes_para(cartao: dict[str, Any] | None) -> list[dict[str, Any]]:
    """As respostas rápidas depois do último card do turno; nenhuma se não houve card."""
    if cartao is None:
        return []
    tipo = str(cartao.get("tipo_cartao"))
    dados = _dicionario(cartao.get("dados"))
    parametros = _dicionario(_dicionario(cartao.get("ref")).get("parametros"))
    sugestoes: list[dict[str, Any]]
    if tipo == "pergunta":
        sugestoes = [dict(o) for o in dados.get("opcoes") or [] if isinstance(o, dict)]
    elif tipo == "ponto_de_preco":
        prato, preco = parametros.get("prato"), parametros.get("preco")
        sugestoes = [_OUTRO_PRECO]
        if isinstance(prato, str) and isinstance(preco, int | float):
            acao = {"tipo": "decidir", "prato": prato, "decisao": "aceito", "preco": preco}
            cobrar = {"rotulo": "Vou cobrar este preço", "texto": "Vou cobrar este preço."}
            sugestoes = [{**cobrar, "acao": acao}, _OUTRO_PRECO]
    elif tipo == "viabilidade":
        sugestoes = [_QUANTO_COBRAR] if dados.get("pode_precificar") else []
    elif tipo == "ingrediente" and isinstance(dados.get("nome"), str):
        nome = _minuscula(dados["nome"])
        sugestoes = [{"rotulo": "Receitas com ele", "texto": f"Que receitas usam {nome}?"}]
    else:
        sugestoes = _SUGESTOES_FIXAS.get(tipo, [])
    return [dict(s) for s in sugestoes]


def dados_iguais(a: object, b: object) -> bool:
    """Dois `dados` de card iguais (o card não precisa ser mandado de novo)."""
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


__all__ = [
    "TIPOS_COM_DINHEIRO",
    "Buscar",
    "MontadorDeCartoes",
    "RefResolvida",
    "campo_da_pergunta",
    "dados_iguais",
    "fontes_do_conhecimento",
    "gerado_texto",
    "id_do_ingrediente",
    "opcoes_da_pergunta",
    "slug",
    "slug_da_receita",
    "sugestoes_para",
    "url_canonica",
]
