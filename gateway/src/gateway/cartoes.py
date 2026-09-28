"""Que card a conversa mostra depois de cada chamada do agente.

Na conversa, o número não vem do texto do modelo: vem de um card com a conta
completa, montado pelo backend com os dados do motor. Aqui está, para cada
ferramenta, qual card ela gera (`tipo_cartao`, um dos tipos listados em
`contratos/web/LEIA.md`) e de onde saem os dados dele (`ref`):

- `rota`: a rota da API que devolve os dados do card, na mesma forma de
  `dados`. Um `{slug}` ou `{id}` na rota o backend resolve pelos parâmetros: a
  receita pelo nome ou pelo endereço, o ingrediente pelo nome. `None` quando os
  dados são a própria resposta da ferramenta (a pergunta da vez).
- `parametros`: o que identifica o card, tirado dos argumentos da chamada. Os
  argumentos são texto do modelo, então só entra o que passa na validação, do
  tipo certo e curto: nunca o HTML de uma página, nunca um preço que não seja
  número. Faltou o que identifica o card, não há card. A receita se identifica
  pelo `receita_id` ou pelo nome, e a ordem dos parâmetros é a precedência da
  ferramenta: quem manda a receita inteira é achado pelo nome dela; quem manda
  o id, pelo id.

Toda ferramenta do motor tem uma entrada aqui, mesmo que seja "sem card"
(`None`): uma ferramenta nova sem essa decisão tomada quebra o teste. As do
Hermes (busca na web, memória) não geram card.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Final, TypedDict
from urllib.parse import urlsplit

from gateway.frases import argumentos_da_chamada, nome_da_ferramenta, valor_no_caminho

#: Os tipos de card que a tela sabe desenhar (`contratos/web/LEIA.md`).
TIPOS_DE_CARTAO: Final = frozenset(
    {
        "despensa_resumo",
        "ingrediente",
        "receita",
        "viabilidade",
        "comparacao",
        "pergunta",
        "cozinha_atualizada",
        "orcamento",
        "custo_porcao",
        "cenarios",
        "ponto_de_preco",
        "preco_preliminar",
        "decisao",
        "avaliacao_da_receita",
        "fontes",
    }
)

#: O mais longo que um nome de prato ou de ingrediente pode vir num parâmetro.
TAMANHO_DO_NOME: Final = 200

#: O mais longo que um endereço pode vir num parâmetro.
TAMANHO_DA_URL: Final = 2000

#: Acima disso não é preço de prato de delivery: é argumento quebrado.
PRECO_MAXIMO: Final = 100_000

#: Os tipos de resposta que mudam a cozinha dela (o gosto é do prato, não da cozinha).
_DA_COZINHA: Final = frozenset({"equipamento", "tecnica", "operacional"})

#: Um id do vocabulário da cozinha: `forno`, `air_fryer`, `bocas_fogao`.
_ID_DA_COZINHA: Final = re.compile(r"[a-z0-9_]{1,64}")

#: Um id de receita: 16 hex do endereço (`3f2a9c0d1b7e4a55`) ou o slug do nome
#: da receita que ela ditou (`arroz-com-frango`).
_ID_DA_RECEITA: Final = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

#: O mais longo que um id de receita pode vir.
TAMANHO_DO_ID: Final = 120

Valor = str | float


class Ref(TypedDict):
    """De onde a tela busca os dados do card."""

    rota: str | None
    parametros: dict[str, Valor]


class Cartao(TypedDict):
    """O card de uma chamada: o tipo e a referência dos dados."""

    tipo_cartao: str
    ref: Ref


def _nome(valor: object) -> str | None:
    """Nome de prato ou de ingrediente: texto de uma linha, nem vazio nem enorme."""
    if not isinstance(valor, str):
        return None
    limpo = " ".join(valor.split())
    return limpo if 0 < len(limpo) <= TAMANHO_DO_NOME else None


def _url(valor: object) -> str | None:
    """Endereço http(s) com site; qualquer outra coisa não identifica receita."""
    if not isinstance(valor, str) or len(valor) > TAMANHO_DA_URL:
        return None
    limpo = valor.strip()
    try:
        partes = urlsplit(limpo)
    except ValueError:
        return None
    return limpo if partes.scheme in ("http", "https") and partes.hostname else None


def _preco(valor: object) -> float | None:
    """Preço positivo e finito, como número (ou texto de número com ponto)."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, str):
        try:
            valor = float(Decimal(valor.strip()))
        except InvalidOperation:
            return None
    if not isinstance(valor, int | float) or not math.isfinite(valor):
        return None
    return float(valor) if 0 < valor <= PRECO_MAXIMO else None


def _id_da_receita(valor: object) -> str | None:
    """O `receita_id` que as ferramentas devolvem; qualquer outra coisa não é id."""
    if not isinstance(valor, str):
        return None
    limpo = valor.strip().lower()
    return limpo if len(limpo) <= TAMANHO_DO_ID and _ID_DA_RECEITA.fullmatch(limpo) else None


def _tipo_da_cozinha(valor: object) -> str | None:
    if not isinstance(valor, str):
        return None
    tipo = valor.strip().lower()
    return tipo if tipo in _DA_COZINHA else None


def _id_da_cozinha(valor: object) -> str | None:
    if not isinstance(valor, str):
        return None
    campo = valor.strip().lower()
    return campo if _ID_DA_COZINHA.fullmatch(campo) else None


@dataclass(frozen=True, slots=True)
class Parametro:
    """Um parâmetro do card: o nome na rota, onde está no argumento e como validar."""

    nome: str
    caminho: str
    validar: Callable[[object], Valor | None] = _nome
    obrigatorio: bool = True


@dataclass(frozen=True, slots=True)
class ModeloDeCartao:
    """O card que uma ferramenta gera."""

    tipo_cartao: str
    rota: str | None
    parametros: tuple[Parametro, ...] = ()
    #: Parâmetros que não vêm do argumento: a aba da lista de receitas, por exemplo.
    fixos: tuple[tuple[str, str], ...] = ()
    #: Nomes de parâmetros opcionais dos quais pelo menos um tem de vir: a receita
    #: se identifica pelo `receita_id` ou pelo nome, e basta um dos dois.
    algum_de: tuple[str, ...] = ()

    def montar(self, argumentos: Mapping[str, Any]) -> Cartao | None:
        """O card destes argumentos; `None` se falta o que o identifica."""
        valores: dict[str, Valor] = dict(self.fixos)
        for parametro in self.parametros:
            valor = parametro.validar(valor_no_caminho(argumentos, parametro.caminho))
            if valor is not None:
                valores[parametro.nome] = valor
            elif parametro.obrigatorio:
                return None
        if self.algum_de and not any(nome in valores for nome in self.algum_de):
            return None
        return {"tipo_cartao": self.tipo_cartao, "ref": {"rota": self.rota, "parametros": valores}}


_PRATO: Final = Parametro("prato", "prato")
_TALVEZ_O_PRATO: Final = Parametro("prato", "prato", obrigatorio=False)
_PRATO_DA_RECEITA: Final = Parametro("prato", "receita.nome", obrigatorio=False)
_ENDERECO_DA_RECEITA: Final = Parametro("url", "receita.url", _url, obrigatorio=False)
_RECEITA_ID: Final = Parametro("receita_id", "receita_id", _id_da_receita, obrigatorio=False)
#: A receita se identifica pelo id ou pelo nome: basta um dos dois.
_ID_OU_PRATO: Final = ("receita_id", "prato")
_ENDERECO: Final = Parametro("url", "url", _url)
_RECEITA_DA_WEB: Final = ModeloDeCartao("receita", "/api/receitas/{slug}", (_ENDERECO,))
_ORCAMENTO: Final = ModeloDeCartao("orcamento", "/api/orcamento")

#: O card de cada ferramenta do motor (`None` = sem card). As chaves são as de
#: `politica.ESCOPOS`.
_INGREDIENTE: Final = ModeloDeCartao(
    "ingrediente", "/api/despensa/itens/{id}", (Parametro("ingrediente", "ingrediente"),)
)

CARTOES: Final[Mapping[str, ModeloDeCartao | None]] = {
    "diagnostico_despensa": ModeloDeCartao("despensa_resumo", "/api/visao-geral"),
    "custo_unitario": _INGREDIENTE,
    "converter_medida_culinaria": None,
    "consultar_perfil": None,
    # Só a resposta que muda a cozinha; a de gosto é sobre o prato, e não tem card.
    "registrar_resposta": ModeloDeCartao(
        "cozinha_atualizada",
        "/api/perfil",
        (Parametro("tipo", "tipo", _tipo_da_cozinha), Parametro("campo", "campo", _id_da_cozinha)),
    ),
    # A pergunta da vez é a própria resposta da ferramenta: não há rota a buscar.
    "proxima_pergunta": ModeloDeCartao("pergunta", None),
    # A receita inteira vale mais que o id nestas duas: o nome dela vem primeiro.
    "avaliar_receita": ModeloDeCartao(
        "viabilidade",
        "/api/receitas/{slug}",
        (_PRATO_DA_RECEITA, _ENDERECO_DA_RECEITA, _RECEITA_ID),
        algum_de=_ID_OU_PRATO,
    ),
    "comparar_candidatas": ModeloDeCartao(
        "comparacao", "/api/receitas", fixos=(("aba", "pode_fazer"),)
    ),
    "calcular_cmv": ModeloDeCartao(
        "custo_porcao",
        "/api/receitas/{slug}/custo",
        (_PRATO_DA_RECEITA, _RECEITA_ID),
        algum_de=_ID_OU_PRATO,
    ),
    # O id vale mais que o nome nas de preço: o id vem primeiro.
    "cenarios_preco": ModeloDeCartao(
        "cenarios", "/api/precos", (_RECEITA_ID, _TALVEZ_O_PRATO), algum_de=_ID_OU_PRATO
    ),
    "testar_sensibilidade": ModeloDeCartao(
        "ponto_de_preco",
        "/api/preco-em",
        (_RECEITA_ID, _TALVEZ_O_PRATO, Parametro("preco", "preco", _preco)),
        algum_de=_ID_OU_PRATO,
    ),
    "estimar_preco_preliminar": ModeloDeCartao(
        "preco_preliminar",
        "/api/receitas/{slug}/estimativa",
        (_RECEITA_ID, _TALVEZ_O_PRATO),
        algum_de=_ID_OU_PRATO,
    ),
    # "De onde eu tirei isso": os trechos da resposta da ferramenta, sem rota a buscar.
    "consultar_conhecimento": ModeloDeCartao("fontes", None, (Parametro("pergunta", "pergunta"),)),
    "buscar_receita_na_web": _RECEITA_DA_WEB,
    # A descoberta roda sem ela olhando: a pauta não vira card.
    "pauta_de_descoberta": None,
    "registrar_avaliacao_da_receita": ModeloDeCartao(
        "avaliacao_da_receita",
        "/api/receitas/{slug}/avaliacao",
        (Parametro("receita_id", "receita_id", _id_da_receita),),
    ),
    "consultar_orcamento": _ORCAMENTO,
    "registrar_compra": _ORCAMENTO,
    "registrar_decisao": ModeloDeCartao("decisao", "/api/cardapio", (_PRATO,)),
    "registrar_gosto": None,
    "consultar_gostos": None,
    "registrar_preco_mercado": _ORCAMENTO,
    "consultar_precos_de_mercado": None,
    # O preço achado aparece na receita, com as fontes: o card seria a mesma coisa.
    "buscar_preco_na_web": None,
    "consultar_cardapio": None,
    # A planilha em texto é para ela ler na conversa; o card seria a própria planilha.
    "consultar_planilha": None,
    # O item depois da mudança: a mesma rota do detalhe na tela.
    "atualizar_despensa": _INGREDIENTE,
}


def cartao_para(ferramenta: str, argumentos: object = None) -> Cartao | None:
    """`{tipo_cartao, ref: {rota, parametros}}` do card da chamada, ou `None` se não há card."""
    modelo = CARTOES.get(nome_da_ferramenta(ferramenta))
    if modelo is None:
        return None
    return modelo.montar(argumentos_da_chamada(argumentos))


__all__ = [
    "CARTOES",
    "PRECO_MAXIMO",
    "TAMANHO_DA_URL",
    "TAMANHO_DO_ID",
    "TAMANHO_DO_NOME",
    "TIPOS_DE_CARTAO",
    "Cartao",
    "ModeloDeCartao",
    "Parametro",
    "Ref",
    "cartao_para",
]
