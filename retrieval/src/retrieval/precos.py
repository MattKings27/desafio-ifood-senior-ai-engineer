"""O preço em São Paulo: o que os supermercados de São Paulo cobram, lido no catálogo deles.

A Dona Maria não é perguntada quanto custa o que ela precisa comprar. O preço
sai dos supermercados de São Paulo, e só do que o servidor leu no catálogo de
cada um:

- **só mercado de São Paulo.** Cada mercado da lista tem loja no estado, e o
  preço é o da loja que atende um CEP de São Paulo. O catálogo é VTEX, que
  regionaliza: a região do CEP (`/api/checkout/pub/regions`) escolhe a loja, e a
  busca com a região (`regionId`) devolve o preço dela. Mercado de loja única
  (sem região) devolve o preço da loja;
- **a escolha é determinística.** O nome do produto tem de ter as palavras do
  ingrediente e nenhuma das palavras a evitar ("light", "roxa", "em pó"); o
  conteúdo tem de estar no nome ("200g", "1kg", "900ml", "12 unidades") ou o
  produto é vendido a peso (o preço é do quilo); e tem de estar em estoque.
  Entre os que passam, vale a menor embalagem que cobre o que se pede (sem
  pedido, a menor de todas), e no empate, o menor preço;
- **a prova fica guardada.** Cada preço guarda o endereço da consulta do
  produto na API do mercado, com a região, e o trecho literal do preço na
  resposta (`"Price":3.79`). `make conferir-referencias` busca de novo e confere.

A rede passa pelo abridor seguro (`retrieval.rede`): só endereço público, com
tempo e tamanho limitados.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from retrieval.rede import DestinoProibido, abridor, resolver_pelo_sistema

#: Lê um endereço e devolve o texto da resposta. Injetável para teste sem rede.
Leitor = Callable[[str, Mapping[str, str]], str]

#: Como a consulta se apresenta: genérico, sem contato pessoal.
AGENTE: Final = "Mozilla/5.0 (compatible; SaborDaMaria-precos/1.0)"
#: O tempo máximo de uma consulta e o maior tamanho de resposta aceito.
TEMPO_LIMITE: Final = 10.0
TAMANHO_MAXIMO: Final = 3 * 1024 * 1024
#: Quantos produtos cada busca traz para a escolha.
PRODUTOS_POR_BUSCA: Final = 30
#: O campo do preço na resposta da API.
CAMPO: Final = "commertialOffer.Price"


@dataclass(frozen=True, slots=True)
class Mercado:
    """Um supermercado de São Paulo, com o CEP que escolhe a loja."""

    site: str
    host: str
    #: O CEP de São Paulo que a região usa, com hífen ("01310-100").
    cep: str
    #: Onde fica a loja que atende o CEP.
    onde: str
    #: O catálogo regionaliza por CEP: sem região para o CEP, o mercado fica de fora.
    regionalizado: bool = True

    @property
    def cep_numeros(self) -> str:
        return self.cep.replace("-", "")


#: Os supermercados de São Paulo com catálogo público (VTEX). A região do CEP de
#: cada um aponta para uma loja no estado de São Paulo.
MERCADOS: Final[tuple[Mercado, ...]] = (
    Mercado("Mambo", "www.mambo.com.br", "01310-100", "São Paulo, capital"),
    Mercado("Coop", "www.coopsupermercado.com.br", "01310-100", "Grande São Paulo"),
    Mercado(
        "Oba Hortifruti",
        "www.obahortifruti.com.br",
        "01310-100",
        "São Paulo, capital (loja Jardim Paulista)",
    ),
    Mercado("Atacadão", "www.atacadao.com.br", "01310-100", "São Paulo, capital"),
    Mercado("Swift", "www.swift.com.br", "01310-100", "São Paulo, capital"),
    Mercado("Savegnago", "www.savegnago.com.br", "14010-000", "Ribeirão Preto, SP"),
    Mercado("Covabra", "www.covabra.com.br", "13010-000", "Campinas, SP"),
    Mercado(
        "Casa Santa Luzia",
        "www.santaluzia.com.br",
        "01424-000",
        "São Paulo, capital (Jardins)",
        regionalizado=False,
    ),
)


class PrecoNaoVeio(Exception):  # noqa: N818
    """A consulta ao mercado não trouxe resposta que se leia."""


# --------------------------------------------------------------------------- #
# Ler                                                                          #
# --------------------------------------------------------------------------- #


def ipv4_primeiro(host: str, porta: int) -> list[str]:
    """Os endereços do nome, o IPv4 primeiro: sem rota IPv6, o primeiro endereço não conecta."""
    return sorted(resolver_pelo_sistema(host, porta), key=lambda endereco: ":" in endereco)


#: Quantas vezes se tenta a consulta que falhou no servidor do mercado (5xx, rede).
TENTATIVAS: Final = 2


def ler_da_rede(url: str, cabecalhos: Mapping[str, str]) -> str:
    """A resposta da API do mercado, pelo abridor seguro, com tempo e tamanho limitados."""
    requisicao = urllib.request.Request(
        url, headers={"User-Agent": AGENTE, "Accept": "application/json", **cabecalhos}
    )
    erro: Exception | None = None
    for _ in range(TENTATIVAS):
        try:
            with abridor(ipv4_primeiro).open(requisicao, timeout=TEMPO_LIMITE) as resposta:
                bruto: bytes = resposta.read(TAMANHO_MAXIMO + 1)
        except urllib.error.HTTPError as falhou:
            erro = falhou
            if falhou.code < 500:  # noqa: PLR2004 (4xx não melhora tentando de novo)
                break
            continue
        except (urllib.error.URLError, OSError, DestinoProibido) as falhou:
            erro = falhou
            continue
        if len(bruto) > TAMANHO_MAXIMO:
            raise PrecoNaoVeio(f"resposta grande demais: {url}")
        return bruto.decode("utf-8", errors="replace")
    raise PrecoNaoVeio(f"{url}: {erro}") from erro


def _json(texto: str, url: str) -> Any:
    try:
        return json.loads(texto)
    except ValueError as erro:
        raise PrecoNaoVeio(f"a resposta não é JSON: {url}") from erro


def regiao_do_cep(mercado: Mercado, ler: Leitor = ler_da_rede) -> str | None:
    """A região VTEX do CEP de São Paulo; `""` para o mercado sem região, `None` sem loja."""
    if not mercado.regionalizado:
        return ""
    url = (
        f"https://{mercado.host}/api/checkout/pub/regions"
        f"?country=BRA&postalCode={mercado.cep_numeros}"
    )
    regioes = _json(ler(url, {}), url)
    if not isinstance(regioes, list):
        return None
    for regiao in regioes:
        if isinstance(regiao, dict) and regiao.get("sellers") and regiao.get("id"):
            return str(regiao["id"])
    return None


def _com_regiao(url: str, regiao: str) -> str:
    return f"{url}&regionId={urllib.parse.quote(regiao)}" if regiao else url


def url_da_busca(mercado: Mercado, termo: str, regiao: str) -> str:
    """A busca do catálogo (Intelligent Search da VTEX), com a região."""
    base = (
        f"https://{mercado.host}/api/io/_v/api/intelligent-search/product_search/"
        f"?query={urllib.parse.quote(termo)}&count={PRODUTOS_POR_BUSCA}&page=1"
        "&locale=pt-BR&hideUnavailableItems=true"
    )
    return _com_regiao(base, regiao)


def url_do_produto(mercado: Mercado, produto_id: str, regiao: str) -> str:
    """A consulta de um produto só, pelo id, com a região: é a prova guardada do preço."""
    base = (
        f"https://{mercado.host}/api/io/_v/api/intelligent-search/product_search/"
        f"?query={urllib.parse.quote(produto_id)}&count=5&page=1&locale=pt-BR"
    )
    return _com_regiao(base, regiao)


def _segmento(regiao: str) -> dict[str, str]:
    """O cookie da VTEX que leva a região para a busca antiga do catálogo."""
    if not regiao:
        return {}
    dados = {
        "channel": "1",
        "regionId": regiao,
        "currencyCode": "BRL",
        "currencySymbol": "R$",
        "countryCode": "BRA",
        "cultureInfo": "pt-BR",
        "channelPrivacy": "public",
    }
    valor = base64.b64encode(json.dumps(dados).encode()).decode()
    return {"Cookie": f"vtex_segment={valor}"}


def buscar_produtos(
    mercado: Mercado, termo: str, regiao: str, ler: Leitor = ler_da_rede
) -> list[dict[str, Any]]:
    """Os produtos da busca, com o preço da região.

    A busca inteligente às vezes responde com um redirecionamento para uma
    categoria, sem produto; aí vale a busca antiga do catálogo, com a região no
    cookie de segmento.
    """
    url = url_da_busca(mercado, termo, regiao)
    resposta = _json(ler(url, {}), url)
    produtos = resposta.get("products") if isinstance(resposta, dict) else None
    if produtos:
        return [p for p in produtos if isinstance(p, dict)]
    antiga = (
        f"https://{mercado.host}/api/catalog_system/pub/products/search"
        f"?ft={urllib.parse.quote(termo)}&_from=0&_to={PRODUTOS_POR_BUSCA - 1}"
    )
    lista = _json(ler(antiga, _segmento(regiao)), antiga)
    return [p for p in lista if isinstance(p, dict)] if isinstance(lista, list) else []


# --------------------------------------------------------------------------- #
# O conteúdo da embalagem, pelo nome                                           #
# --------------------------------------------------------------------------- #


def sem_acento(texto: str) -> str:
    """Sem acento, em minúscula, com hífen e barra virando espaço."""
    decomposto = unicodedata.normalize("NFKD", texto)
    simples = "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()
    return " ".join(re.sub(r"[-/]", " ", simples).split())


@dataclass(frozen=True, slots=True)
class Conteudo:
    """O que a embalagem tem: 200 g, 900 ml, 12 unidades, ou o quilo vendido a peso."""

    quantidade: Decimal
    #: `g`, `kg`, `ml`, `L` ou `un`.
    unidade: str
    a_granel: bool = False

    @property
    def base(self) -> Decimal:
        """Na unidade-base: quilos, litros ou unidades."""
        fator = {"g": Decimal("0.001"), "ml": Decimal("0.001")}.get(self.unidade, Decimal(1))
        return self.quantidade * fator

    @property
    def dimensao(self) -> str:
        return {"g": "massa", "kg": "massa", "ml": "volume", "L": "volume"}.get(
            self.unidade, "contagem"
        )


_NUMERO: Final = r"(\d+(?:[.,]\d+)?)"
_MEDIDA: Final = re.compile(
    rf"(?<![\d.,]){_NUMERO}\s*(kg|kgs|quilos?|g|gr|grs|gramas|ml|l|lt|lts|litros?)\b(?!\s*cada)"
)
_VARIAS: Final = re.compile(r"\b\d+\s*x\s*\d")
_CONTADAS: Final = re.compile(
    r"(?<![\d.,])(\d+)\s*(?:unidades|unidade|unid|und|un|tabletes|cubos|saches|sticks|ovos)\b"
)
_UNIDADE: Final[dict[str, str]] = {
    "kg": "kg",
    "kgs": "kg",
    "quilo": "kg",
    "quilos": "kg",
    "g": "g",
    "gr": "g",
    "grs": "g",
    "gramas": "g",
    "ml": "ml",
    "l": "L",
    "lt": "L",
    "lts": "L",
    "litro": "L",
    "litros": "L",
}


def _decimal(texto: str) -> Decimal | None:
    try:
        valor = Decimal(texto.replace(",", "."))
    except InvalidOperation:
        return None
    return valor if valor.is_finite() and valor > 0 else None


def conteudo_do_nome(nome: str, *, contado: bool = False) -> Conteudo | None:  # noqa: PLR0911
    """O conteúdo que o nome do produto diz; `None` quando não diz, ou diz dois.

    `contado` lê as unidades ("com 6 unidades", "12 cubos", "dúzia") em vez do
    peso: é o caso do caldo em tablete e dos ovos. Embalagem com várias
    ("2x200g") fica de fora: o preço não é de uma.
    """
    texto = sem_acento(nome)
    if _VARIAS.search(texto):
        return None
    if contado:
        if re.search(r"\bduzia\b", texto):
            return Conteudo(Decimal(12), "un")
        contagens = {Decimal(n) for n in _CONTADAS.findall(texto)}
        if len(contagens) == 1:
            return Conteudo(contagens.pop(), "un")
        if not contagens and re.search(r"\b(?:unidade|maco|molho)\b", texto):
            return Conteudo(Decimal(1), "un")
        return None
    medidas = {(v, _UNIDADE[u]) for n, u in _MEDIDA.findall(texto) if (v := _decimal(n))}
    if len(medidas) != 1:
        return None
    valor, unidade = medidas.pop()
    return Conteudo(valor, unidade)


# --------------------------------------------------------------------------- #
# O que procurar e a escolha                                                   #
# --------------------------------------------------------------------------- #

#: Palavras que fazem de um produto outro produto. Só valem quando o nome do
#: ingrediente não as tem: "cebola roxa" aceita "roxa"; "cebola" não.
EVITAR_SEMPRE: Final[frozenset[str]] = frozenset(
    {
        "light",
        "diet",
        "zero",
        "lactose",
        "vegano",
        "vegana",
        "vegetal",
        "proteico",
        "fit",
        "organico",
        "organica",
        "sabor",
        "aroma",
        "recheado",
        "recheio",
        "kit",
        "combo",
        "leve",
        "pague",
        "desidratado",
        "desidratada",
        "frito",
        "frita",
        "crispy",
        "crocante",
        "palha",
        "chips",
        "salgadinho",
        "biscoito",
        "conserva",
        "picado",
        "picada",
        "triturado",
        "triturada",
        "empanado",
        "empanada",
        "temperado",
        "temperada",
        "temp",
        "espetinho",
        "desossado",
        "desossada",
        "passarinho",
        "file",
        "pate",
        "molho",
        "creme",
        "sopa",
        "caldo",
        "tempero",
        "mistura",
        "preparo",
        "instantaneo",
        "infantil",
        "baby",
        "mini",
        "gourmet",
        "premium",
        "especial",
        "importada",
        "importado",
        "cereja",
        "grape",
        "roxa",
        "roxo",
        "branca",
        "branco",
        "amarela",
        "amarelo",
        "preta",
        "preto",
        "vermelha",
        "vermelho",
        "doce",
        "defumado",
        "defumada",
        "po",
        "moido",
        "moida",
        "ralado",
        "ralada",
        "flocos",
        "fatiado",
        "fatiada",
        "integral",
        "desnatado",
        "semidesnatado",
        "fresco",
        "fresca",
        "seco",
        "seca",
        "suco",
        "geleia",
        "vinagrete",
        "display",
        "refil",
    }
)

_SEM_SENTIDO: Final = frozenset(
    {"de", "da", "do", "das", "dos", "e", "em", "com", "a", "o", "para"}
)

#: O que tira do produto uma parte que o ingrediente tem: sem osso, sem pele.
_FRASES_A_EVITAR: Final = ("sem osso", "sem pele")

#: O maior conteúdo que a procura pelo nome aceita, na unidade-base: acima disso
#: é embalagem de atacado (a caixa de 16 kg de frango), e não o que ela compra.
_MAIOR_EMBALAGEM: Final[dict[str, Decimal]] = {
    "massa": Decimal(5),
    "volume": Decimal(5),
    "contagem": Decimal(30),
}


def _singular(palavra: str) -> str:
    """ "limoes" vira "limao"; "cenouras", "cenoura"; "ss" e palavra curta ficam."""
    if palavra.endswith("oes") and len(palavra) > _CURTA + 1:
        return palavra[:-3] + "ao"
    if palavra.endswith("s") and len(palavra) > _CURTA and not palavra.endswith("ss"):
        return palavra[:-1]
    return palavra


#: A palavra até este tamanho fica como está ("gas", "mas").
_CURTA: Final = 3


def palavras(texto: str) -> list[str]:
    """As palavras do texto, sem acento e no singular simples ("cenouras" vira "cenoura")."""
    return [_singular(p) for p in re.findall(r"[a-z0-9]+", sem_acento(texto))]


@dataclass(frozen=True, slots=True)
class Procura:
    """O que procurar num mercado, e como reconhecer o produto certo."""

    termo: str
    #: As palavras que o nome do produto tem de ter (sem acento, no singular).
    exigir: tuple[str, ...]
    #: As palavras que dizem que é outro produto, além de `EVITAR_SEMPRE`.
    evitar: tuple[str, ...] = ()
    #: As palavras de `EVITAR_SEMPRE` que este produto pode ter ("moída", "em pó").
    permitir: tuple[str, ...] = ()
    #: `massa`, `volume` ou `contagem`: a dimensão do conteúdo.
    dimensao: str = "massa"
    #: `True`: só o vendido a peso; `False`: só o embalado; `None`: qualquer um.
    a_granel: bool | None = None
    #: O menor e o maior conteúdo aceitos, na unidade-base (quilo, litro, unidade).
    minimo: Decimal | None = None
    maximo: Decimal | None = None
    #: Pedaço do caminho da categoria que o produto tem de ter ("hortifruti").
    categoria: str = ""

    @classmethod
    def do_registro(cls, bruto: Mapping[str, Any]) -> Procura:
        """A procura como o arquivo de preços guarda (`busca`)."""

        def numero(chave: str) -> Decimal | None:
            valor = bruto.get(chave)
            return Decimal(str(valor)) if valor not in (None, "") else None

        granel = bruto.get("a_granel")
        return cls(
            termo=str(bruto["termo"]),
            exigir=tuple(palavras(" ".join(bruto.get("exigir") or [str(bruto["termo"])]))),
            evitar=tuple(palavras(" ".join(bruto.get("evitar") or []))),
            permitir=tuple(palavras(" ".join(bruto.get("permitir") or []))),
            dimensao=str(bruto.get("dimensao") or "massa"),
            a_granel=None if granel is None else bool(granel),
            minimo=numero("minimo"),
            maximo=numero("maximo"),
            categoria=str(bruto.get("categoria") or ""),
        )

    @classmethod
    def do_nome(cls, nome: str, dimensao: str = "massa") -> Procura:
        """A procura de um ingrediente pelo nome dele, sem ajuste: é a da receita nova."""
        limpo = re.sub(r"[^\w\s-]", " ", nome)
        exigir = tuple(p for p in palavras(limpo) if p not in _SEM_SENTIDO and not p.isdigit())
        return cls(
            termo=" ".join(limpo.split()),
            exigir=exigir,
            dimensao=dimensao,
            maximo=_MAIOR_EMBALAGEM.get(dimensao),
        )

    def recusa(self, nome_do_produto: str) -> str:
        """Por que o nome não é deste produto; `""` quando é."""
        do_produto = set(palavras(nome_do_produto))
        faltam = [p for p in self.exigir if p not in do_produto]
        if faltam:
            return f"o nome não tem {', '.join(faltam)}"
        proprias = set(self.exigir) | set(palavras(self.termo)) | set(self.permitir)
        evitadas = sorted(
            p for p in do_produto & (EVITAR_SEMPRE | set(self.evitar)) if p not in proprias
        )
        if evitadas:
            return f"o nome diz {', '.join(evitadas)}"
        nome = sem_acento(nome_do_produto)
        termo = sem_acento(self.termo)
        for frase in _FRASES_A_EVITAR:
            if frase in nome and frase not in termo:
                return f"o nome diz {frase}"
        return ""


@dataclass(frozen=True, slots=True)
class Candidato:
    """Um produto do mercado que pode ser o ingrediente."""

    mercado: Mercado
    produto_id: str
    nome: str
    link: str
    preco: Decimal
    #: O literal do preço como a resposta escreve ("3.79").
    literal: str
    conteudo: Conteudo
    categorias: tuple[str, ...] = ()


def _oferta(item: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """A oferta do primeiro vendedor com estoque e preço."""
    for vendedor in item.get("sellers") or ():
        oferta = vendedor.get("commertialOffer") if isinstance(vendedor, dict) else None
        if (
            isinstance(oferta, dict)
            and (oferta.get("AvailableQuantity") or 0) > 0
            and (oferta.get("Price") or 0) > 0
        ):
            return oferta
    return None


def candidato(mercado: Mercado, produto: Mapping[str, Any], procura: Procura) -> Candidato | None:
    """O produto da resposta como candidato; `None` quando não serve (e não se sabe por quê)."""
    itens = produto.get("items") or []
    if len(itens) != 1 or not isinstance(itens[0], dict):
        return None
    item = itens[0]
    oferta = _oferta(item)
    if oferta is None:
        return None
    nome = str(produto.get("productName") or "").strip()
    if _TRAVESSAO.search(nome):
        # O nome vai para a tela como o mercado escreve, e travessão não separa ideia ali.
        return None
    unidade = str(item.get("measurementUnit") or "").casefold()
    if unidade == "kg":
        # Vendido a peso: o preço é o do quilo, e a embalagem é o que ela pesar.
        conteudo: Conteudo | None = Conteudo(Decimal(1), "kg", a_granel=True)
    elif unidade in ("un", "und") and Decimal(str(item.get("unitMultiplier") or 1)) == 1:
        conteudo = conteudo_do_nome(nome, contado=procura.dimensao == "contagem")
    else:
        conteudo = None
    if conteudo is None:
        return None
    preco = Decimal(str(oferta["Price"]))
    return Candidato(
        mercado=mercado,
        produto_id=str(produto.get("productId") or ""),
        nome=nome,
        link=str(produto.get("linkText") or ""),
        preco=preco,
        literal=_literal(oferta["Price"]),
        conteudo=conteudo,
        categorias=tuple(str(c) for c in produto.get("categories") or ()),
    )


#: O travessão e o meio-travessão que alguns mercados põem no nome do produto.
_TRAVESSAO: Final = re.compile("[\u2013\u2014]")


def _literal(valor: object) -> str:
    """Como o JSON escreve o número: 3.79, 4, 12.9."""
    return json.dumps(valor)


def serve(c: Candidato, procura: Procura) -> str:  # noqa: PLR0911
    """Por que o candidato não serve para esta procura; `""` quando serve."""
    if motivo := procura.recusa(c.nome):
        return motivo
    if procura.a_granel is not None and c.conteudo.a_granel != procura.a_granel:
        return "vendido a peso" if c.conteudo.a_granel else "vendido embalado"
    if c.conteudo.dimensao != procura.dimensao:
        return f"o conteúdo é de {c.conteudo.dimensao}"
    if procura.categoria and not any(
        sem_acento(procura.categoria) in sem_acento(cat) for cat in c.categorias
    ):
        return "é de outra seção do mercado"
    base = c.conteudo.base
    if procura.minimo is not None and base < procura.minimo:
        return "embalagem pequena demais"
    if procura.maximo is not None and base > procura.maximo:
        return "embalagem grande demais"
    return ""


def escolher(
    candidatos: Iterable[Candidato], necessidade: Decimal | None = None
) -> Candidato | None:
    """A menor embalagem que cobre a necessidade (sem ela, a menor); no empate, a mais barata.

    Vendido a peso, ela leva o que precisa, e é o que vale quando o mercado
    vende assim: o menor preço do quilo. Sem embalagem que cubra, a maior, que
    ela compra mais de uma vez.
    """
    lista = list(candidatos)
    if not lista:
        return None

    def por_base(c: Candidato) -> Decimal:
        return c.preco / c.conteudo.base

    a_granel = [c for c in lista if c.conteudo.a_granel]
    if a_granel:
        return min(a_granel, key=lambda c: (por_base(c), c.produto_id))
    embalados = [c for c in lista if not c.conteudo.a_granel]
    cobrem = [c for c in embalados if necessidade is None or c.conteudo.base >= necessidade]
    if cobrem:
        return min(cobrem, key=lambda c: (c.conteudo.base, c.preco, c.produto_id))
    return max(embalados, key=lambda c: (c.conteudo.base, -c.preco, c.produto_id))


# --------------------------------------------------------------------------- #
# A fonte, com a prova                                                         #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Fonte:
    """O preço de um produto num mercado de São Paulo, com o que prova."""

    site: str
    produto: str
    produto_id: str
    preco: Decimal
    quantidade: Decimal
    unidade: str
    a_granel: bool
    url: str
    api: str
    cep: str
    data: dt.date
    campo: str
    trecho: str

    def registro(self) -> dict[str, Any]:
        """Como o arquivo de preços e o dossiê guardam."""
        return {
            "site": self.site,
            "produto": self.produto,
            "id": self.produto_id,
            "preco": str(self.preco),
            "quantidade": str(self.quantidade),
            "unidade": self.unidade,
            "a_granel": self.a_granel,
            "url": self.url,
            "api": self.api,
            "cep": self.cep,
            "data": self.data.isoformat(),
            "campo": self.campo,
            "trecho": self.trecho,
        }


def fonte_do_candidato(c: Candidato, regiao: str, hoje: dt.date) -> Fonte:
    return Fonte(
        site=c.mercado.site,
        produto=c.nome,
        produto_id=c.produto_id,
        preco=c.preco,
        quantidade=c.conteudo.quantidade,
        unidade=c.conteudo.unidade,
        a_granel=c.conteudo.a_granel,
        url=f"https://{c.mercado.host}/{c.link}/p",
        api=url_do_produto(c.mercado, c.produto_id, regiao),
        cep=c.mercado.cep,
        data=hoje,
        campo=CAMPO,
        trecho=f'"Price":{c.literal}',
    )


@dataclass(slots=True)
class Pesquisa:
    """Uma rodada de consultas: guarda a região de cada mercado para não perguntar de novo."""

    mercados: Sequence[Mercado] = MERCADOS
    ler: Leitor = ler_da_rede
    hoje: dt.date = field(default_factory=lambda: dt.datetime.now(tz=dt.UTC).date())
    _regioes: dict[str, str | None] = field(default_factory=dict)
    #: O que deu errado em cada mercado, para quem quiser saber.
    falhas: list[str] = field(default_factory=list)

    def regiao(self, mercado: Mercado) -> str | None:
        if mercado.host not in self._regioes:
            try:
                self._regioes[mercado.host] = regiao_do_cep(mercado, self.ler)
            except PrecoNaoVeio as erro:
                self.falhas.append(f"{mercado.site}: {erro}")
                self._regioes[mercado.host] = None
        return self._regioes[mercado.host]

    def no_mercado(
        self, mercado: Mercado, procura: Procura, necessidade: Decimal | None = None
    ) -> Fonte | None:
        """O produto escolhido neste mercado, com a prova; `None` quando não há."""
        regiao = self.regiao(mercado)
        if regiao is None:
            return None
        try:
            produtos = buscar_produtos(mercado, procura.termo, regiao, self.ler)
        except PrecoNaoVeio as erro:
            self.falhas.append(f"{mercado.site}: {erro}")
            return None
        candidatos = [c for p in produtos if (c := candidato(mercado, p, procura))]
        escolhido = escolher((c for c in candidatos if not serve(c, procura)), necessidade)
        return fonte_do_candidato(escolhido, regiao, self.hoje) if escolhido else None

    def em_todos(self, procura: Procura, necessidade: Decimal | None = None) -> list[Fonte]:
        """O produto escolhido em cada mercado que tem, na ordem da lista."""
        achadas = (self.no_mercado(m, procura, necessidade) for m in self.mercados)
        return [f for f in achadas if f is not None]

    def _produtos(self, mercado: Mercado, termo: str) -> tuple[str, list[dict[str, Any]]] | None:
        regiao = self.regiao(mercado)
        if regiao is None:
            return None
        try:
            return regiao, buscar_produtos(mercado, termo, regiao, self.ler)
        except PrecoNaoVeio as erro:
            self.falhas.append(f"{mercado.site}: {erro}")
            return None

    def pelo_nome(
        self, nome: str, dimensoes: Sequence[str], prazo: float
    ) -> tuple[str, list[Fonte]]:
        """O ingrediente pelo nome, em todos os mercados ao mesmo tempo, até o prazo.

        Uma busca por mercado; o que chega depois do prazo fica de fora. As
        dimensões são tentadas na ordem ("massa", "volume", "contagem"), e vale
        a primeira que algum mercado tem.
        """
        procuras = [Procura.do_nome(nome, d) for d in dimensoes]
        if not procuras:
            return "massa", []
        executor = ThreadPoolExecutor(max_workers=max(1, len(self.mercados)))
        futuros = {executor.submit(self._produtos, m, procuras[0].termo): m for m in self.mercados}
        feitos, atrasados = wait(futuros, timeout=prazo)
        executor.shutdown(wait=False, cancel_futures=True)
        for futuro in atrasados:
            self.falhas.append(f"{futuros[futuro].site}: passou do prazo de {prazo:g} s")
        respostas = [(futuros[f], r) for f in feitos if (r := f.result()) is not None]
        respostas.sort(key=lambda par: self.mercados.index(par[0]))
        for procura in procuras:
            fontes: list[Fonte] = []
            for mercado, (regiao, produtos) in respostas:
                candidatos = [c for p in produtos if (c := candidato(mercado, p, procura))]
                escolhido = escolher(c for c in candidatos if not serve(c, procura))
                if escolhido is not None:
                    fontes.append(fonte_do_candidato(escolhido, regiao, self.hoje))
            if fontes:
                return procura.dimensao, fontes
        return procuras[0].dimensao, []


# --------------------------------------------------------------------------- #
# Conferir a prova                                                             #
# --------------------------------------------------------------------------- #


def conferir_fonte(registro: Mapping[str, Any], ler: Leitor = ler_da_rede) -> str:
    """Busca a consulta guardada e diz o que não confere; `""` quando a resposta prova o preço."""
    url = str(registro.get("api") or "")
    if not url.startswith("https://"):
        return "a fonte não guarda a consulta da API"
    try:
        texto = ler(url, {})
    except PrecoNaoVeio as erro:
        return f"a consulta não veio ({erro})"
    return problema_na_resposta(registro, texto)


def problema_na_resposta(registro: Mapping[str, Any], texto: str) -> str:  # noqa: PLR0911
    """O que a resposta da API não prova do registro; `""` quando prova tudo."""
    try:
        resposta = json.loads(texto)
    except ValueError:
        return "a resposta não é JSON"
    produtos = resposta.get("products") if isinstance(resposta, dict) else None
    achado = next(
        (
            p
            for p in produtos or ()
            if isinstance(p, dict) and str(p.get("productId")) == str(registro.get("id"))
        ),
        None,
    )
    if achado is None:
        return "o produto não está mais na resposta"
    if str(achado.get("productName") or "").strip() != registro.get("produto"):
        return f"o produto da resposta é outro ({achado.get('productName')!r})"
    itens = achado.get("items") or [{}]
    oferta = _oferta(itens[0]) if isinstance(itens[0], dict) else None
    if oferta is None:
        return "o produto está sem estoque ou sem preço"
    if Decimal(str(oferta["Price"])) != Decimal(str(registro.get("preco"))):
        return f"o preço mudou (a resposta diz {oferta['Price']})"
    if str(registro.get("trecho")) not in texto:
        return "o trecho do preço não está na resposta"
    a_granel = str(itens[0].get("measurementUnit") or "").casefold() == "kg"
    if a_granel != bool(registro.get("a_granel")):
        return "o produto mudou o jeito de vender (a peso ou embalado)"
    return ""


__all__ = [
    "CAMPO",
    "EVITAR_SEMPRE",
    "MERCADOS",
    "Candidato",
    "Conteudo",
    "Fonte",
    "Leitor",
    "Mercado",
    "Pesquisa",
    "PrecoNaoVeio",
    "Procura",
    "buscar_produtos",
    "candidato",
    "conferir_fonte",
    "conteudo_do_nome",
    "escolher",
    "fonte_do_candidato",
    "ler_da_rede",
    "palavras",
    "problema_na_resposta",
    "regiao_do_cep",
    "sem_acento",
    "serve",
    "url_da_busca",
    "url_do_produto",
]
