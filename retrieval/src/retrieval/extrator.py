"""Extração de receita a partir de uma página real.

O §2.1 manda pesquisar receitas reais na internet. Este módulo é a parte
verificável disso: dado o HTML de uma página de receita, devolve uma `Receita`
do domínio ou diz por que não conseguiu.

A ordem das tentativas é da mais confiável para a menos:

1. **JSON-LD `schema.org/Recipe`**: dado estruturado que o próprio site
   publicou. É o caminho certo e é o que os sites grandes de receita usam,
   porque é o que o Google lê.
2. **Microdata** (`itemprop`): a geração anterior do mesmo padrão.
3. Nada. **Não há heurística de HTML aqui**, e isso é deliberado: adivinhar
   ingrediente por posição de `<li>` acerta na página que você testou e erra
   calado em todas as outras. Receita errada vira preço errado, e preço errado
   a Dona Maria só descobre no fim do mês.

Nenhuma dependência de parser externo: JSON-LD mora em `<script>`, e o
`html.parser` da biblioteca padrão dá conta de achá-lo.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Any, ClassVar
from urllib.parse import urljoin, urlsplit

from mise.catalogo import foto_generica
from mise.receita import Origem, Receita

from retrieval.quantidades import interpretar_linha

#: Tipos do schema.org que contam como receita.
TIPOS_DE_RECEITA: frozenset[str] = frozenset({"recipe"})

#: "PT1H30M" -> 90. ISO 8601 de duração, que é o que o schema.org usa.
_DURACAO = re.compile(
    r"^P(?:(?P<dias>\d+)D)?T?(?:(?P<horas>\d+)H)?(?:(?P<minutos>\d+)M)?", re.IGNORECASE
)

#: "4 porções", "Rende 6", "serve 2 pessoas": o número é o que importa.
_PRIMEIRO_INTEIRO = re.compile(r"\d+")

MINUTOS_POR_HORA = 60
MINUTOS_POR_DIA = 1440


class ExtracaoFalhou(Exception):  # noqa: N818
    """A página não trouxe dado estruturado de receita.

    Sem sufixo `Error` de propósito: o resto deste repositório nomeia exceção
    pelo que aconteceu, em português, e `ExtracaoFalhouError` seria metade numa
    língua e metade na outra.

    Não é erro do domínio: é a pesquisa não ter dado certo naquela página, e o
    caminho certo é tentar outra, não inventar a receita.
    """


@dataclass(frozen=True, slots=True)
class ReceitaExtraida:
    """O que saiu da página, com a procedência junto.

    Além da receita, o que a página declara sobre ela e a tela mostra: o site
    (o nome que a página dá a si, ou o domínio), a foto, os três tempos, o
    rendimento como está escrito e o hash do conteúdo lido, para o catálogo
    saber se a página mudou.
    """

    receita: Receita
    url: str
    fonte: str
    autor: str = ""
    site: str = ""
    imagem_url: str | None = None
    preparo_min: int | None = None
    cozimento_min: int | None = None
    total_min: int | None = None
    rendimento_texto: str = ""
    hash_do_conteudo: str = ""

    def __str__(self) -> str:
        return f"{self.receita.nome} ({self.fonte})"


class _CacadorDeJsonLd(HTMLParser):
    """Recolhe o conteúdo de cada `<script type="application/ld+json">`."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocos: list[str] = []
        #: A foto que a página declara para quem a compartilha (`og:image`).
        self.og_image: str | None = None
        #: As imagens do corpo da página, com o texto alternativo de cada uma.
        self.imagens: list[tuple[str, str]] = []
        self._dentro = False
        self._atual: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "meta":
            mapa = {k.lower(): (v or "") for k, v in attrs}
            propriedade = (mapa.get("property") or mapa.get("name") or "").lower()
            if propriedade in {"og:image", "og:image:url", "og:image:secure_url"}:
                self.og_image = self.og_image or mapa.get("content") or None
            return
        if tag == "img":
            mapa = {k.lower(): (v or "") for k, v in attrs}
            fonte = mapa.get("data-src") or mapa.get("src") or ""
            if fonte.startswith(("http://", "https://", "//")):
                self.imagens.append((fonte, mapa.get("alt") or mapa.get("title") or ""))
            return
        if tag != "script":
            return
        tipo = next((v or "" for k, v in attrs if k.lower() == "type"), "")
        if "ld+json" in tipo.lower():
            self._dentro = True
            self._atual = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._dentro:
            self.blocos.append("".join(self._atual))
            self._dentro = False
            self._atual = []

    def handle_data(self, data: str) -> None:
        if self._dentro:
            self._atual.append(data)


#: O número do passo sozinho numa etiqueta: "1", "2.", "3)".
_NUMERO_NA_ETIQUETA = re.compile(r"(\d{1,2})[.)º°-]?")


class _CacadorDeMicrodata(HTMLParser):
    """Recolhe `itemprop` de ingrediente, instrução, rendimento e nome."""

    INTERESSANTES: ClassVar[frozenset[str]] = frozenset(
        {
            "recipeingredient",
            "ingredients",
            "recipeinstructions",
            "recipeyield",
            "name",
            "preptime",
            "cooktime",
            "totaltime",
        }
    )

    #: Etiquetas sem fechamento: não abrem nível dentro do campo.
    VAZIAS: ClassVar[frozenset[str]] = frozenset(
        {"br", "img", "hr", "meta", "input", "link", "source", "wbr"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.campos: dict[str, list[str]] = {}
        #: O número com que a página abre cada valor, numa etiqueta só dele
        #: (`<span>1</span>`), ou "" quando não abre com número assim. Anda junto
        #: com `campos`, um por valor.
        self.numeros: dict[str, list[str]] = {}
        self._prop: str | None = None
        self._buffer: list[str] = []
        #: Quantas etiquetas estão abertas dentro do campo: o campo só fecha no
        #: fim da etiqueta que o abriu. Antes fechava no primeiro `</span>`, e o
        #: passo "<li><span>1</span><span>Tempere o peixe</span></li>" virava "1".
        self._nivel = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._prop is not None:
            if tag not in self.VAZIAS:
                self._nivel += 1
            return
        mapa = {k.lower(): (v or "") for k, v in attrs}
        prop = mapa.get("itemprop", "").lower()
        if prop not in self.INTERESSANTES:
            return
        # `content` e `datetime` carregam o valor limpo quando existem.
        for atributo in ("content", "datetime"):
            if valor := mapa.get(atributo, "").strip():
                self.campos.setdefault(prop, []).append(valor)
                self.numeros.setdefault(prop, []).append("")
                return
        if tag in self.VAZIAS:
            return
        self._prop = prop
        self._buffer = []
        self._nivel = 0

    def handle_endtag(self, tag: str) -> None:
        if self._prop is None:
            return
        if self._nivel > 0:
            self._nivel -= 1
            return
        pedacos = [p for p in (" ".join(bruto.split()) for bruto in self._buffer) if p]
        if pedacos:
            self.campos.setdefault(self._prop, []).append(" ".join(pedacos))
            numerado = len(pedacos) > 1 and _NUMERO_NA_ETIQUETA.fullmatch(pedacos[0])
            self.numeros.setdefault(self._prop, []).append(pedacos[0] if numerado else "")
        self._prop = None
        self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._prop:
            self._buffer.append(data)


def _achatar(no: Any) -> list[dict[str, Any]]:
    """JSON-LD vem em árvore, lista, `@graph`: tudo isso vira lista de objetos."""
    if isinstance(no, list):
        return [d for item in no for d in _achatar(item)]
    if not isinstance(no, dict):
        return []
    encontrados = [no]
    for chave in ("@graph", "mainEntity", "mainEntityOfPage", "itemListElement"):
        if chave in no:
            encontrados.extend(_achatar(no[chave]))
    return encontrados


def _e_receita(objeto: dict[str, Any]) -> bool:
    bruto = objeto.get("@type") or objeto.get("type") or ""
    tipos = bruto if isinstance(bruto, list) else [bruto]
    return any(str(t).strip().lower() in TIPOS_DE_RECEITA for t in tipos)


#: Etiqueta HTML dentro de um texto que devia ser só texto: "<b>alcatra</b>".
_ETIQUETA = re.compile(r"<[^<>]{0,200}>")
#: As etiquetas de bloco, que na página começam outra linha: um `<br>` entre
#: ingredientes separa dois deles. As outras ("<b>", "<a>") somem sem deixar
#: espaço, como na página: "Aqueça o <b>óleo</b>." é "Aqueça o óleo.", e não
#: "Aqueça o óleo ." com o ponto solto.
_QUEBRA = re.compile(
    r"<\s*/?\s*(?:br|p|li|div|ul|ol|h[1-6]|tr|table|section|article|blockquote)\b[^<>]{0,200}>",
    re.IGNORECASE,
)
#: Quantas vezes uma entidade pode vir escapada ("&amp;atilde;" é "ã" escapado duas vezes).
_ESCAPES_ACEITOS = 3


def _sem_html(texto: str) -> str:
    """O texto sem entidade e sem etiqueta HTML, como a página queria mostrar.

    Há site que publica "lim&amp;atilde;o" (a entidade escapada duas vezes) e
    "&lt;b&gt;Alcatra&lt;/b&gt;" (a etiqueta escapada). Sem isto, o passo saía
    na tela como "lim&atilde;o", e o nome do ingrediente com "<b>" dentro.
    """
    for _ in range(_ESCAPES_ACEITOS):
        desfeito = unescape(texto)
        if desfeito == texto:
            break
        texto = desfeito
    texto = _ETIQUETA.sub("", _QUEBRA.sub("\n", texto))
    return "\n".join(" ".join(linha.split()) for linha in texto.splitlines()).strip()


def _texto(valor: Any) -> str:
    """schema.org aceita string, objeto com `name`/`text`, ou lista de qualquer um."""
    if isinstance(valor, str):
        return _sem_html(valor)
    if isinstance(valor, dict):
        for chave in ("text", "name", "@value"):
            if chave in valor:
                return _texto(valor[chave])
        return ""
    if isinstance(valor, list):
        return " ".join(filter(None, (_texto(v) for v in valor)))
    return ""


def _lista_de_textos(valor: Any) -> list[str]:
    """Uma entrada por linha, mesmo quando o site junta tudo numa string só.

    Há site que publica a lista inteira de ingredientes como um único item,
    separado por quebra de linha. Sem quebrar, a receita saía com um
    ingrediente só, com todos os outros grudados no nome dele.
    """
    brutos = valor if isinstance(valor, list) else [valor]
    linhas = []
    for bruto in brutos:
        for linha in _texto(bruto).splitlines():
            if linha.strip():
                linhas.append(linha.strip())
    return linhas


# --------------------------------------------------------------------------- #
# O modo de preparo, como a página mostra                                      #
# --------------------------------------------------------------------------- #

#: Nomes de seção que só dizem "aqui está o preparo": a página não mostra
#: título para eles (o Receitas Nestlé põe tudo numa seção "Modo de Preparo"),
#: e a tela também não. Comparados sem acento e sem maiúscula.
_SECOES_SEM_TITULO: frozenset[str] = frozenset(
    {
        "modo de preparo",
        "modo de preparacao",
        "preparo",
        "preparacao",
        "modo de fazer",
        "como fazer",
        "instrucoes",
        "passo a passo",
        "passos",
        "etapas",
    }
)

#: "Passo 1", "Etapa 2", "3.": o nome que só numera o passo não é título de seção.
_SO_NUMERA = re.compile(r"(?:passo|etapa)?\s*\d+\s*[.:)ºª°-]?")


@dataclass(frozen=True, slots=True)
class _PassoLido:
    """Um passo do `recipeInstructions`, com as linhas do texto e a seção dele."""

    linhas: tuple[str, ...]
    secao: str | None
    #: Veio de um objeto (`HowToStep`), que declara um passo só, e não de um
    #: texto solto, em que o site junta vários passos um por linha.
    declarado: bool


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()


def titulo_da_secao(nome: str) -> str | None:
    """O nome da seção como a tela mostra, ou `None` quando ele não é título.

    "Massa" e "Cobertura" são títulos; "Modo de Preparo" e "Passo 1" não: a
    página não os mostra como título, e repetir "Modo de preparo" embaixo do
    título da tela seria ruído.
    """
    limpo = " ".join(nome.split())
    chave = _sem_acento(limpo).strip(" :.-")
    if not chave or chave in _SECOES_SEM_TITULO or _SO_NUMERA.fullmatch(chave):
        return None
    return limpo


def _tipos(objeto: dict[str, Any]) -> set[str]:
    """Os tipos do objeto, sem o prefixo: "http://schema.org/HowToStep" é "howtostep"."""
    bruto = objeto.get("@type") or ""
    return {
        re.split(r"[/:#]", str(t).strip())[-1].lower()
        for t in (bruto if isinstance(bruto, list) else [bruto])
    }


def _como_lista(valor: Any) -> list[Any]:
    if valor is None:
        return []
    return valor if isinstance(valor, list) else [valor]


def _linhas(texto: str) -> tuple[str, ...]:
    return tuple(linha for linha in _sem_html(texto).splitlines() if linha)


def _texto_do_passo(objeto: dict[str, Any]) -> str:
    """O texto de um passo: `text`; senão o que ele traz dentro; senão o `name`.

    O Panelinha põe o texto num `HowToDirection` dentro do `HowToStep`, sem
    `text` no passo: antes o passo saía vazio e sumia.
    """
    if texto := _texto(objeto.get("text")):
        return texto
    de_dentro = [
        _texto(item) if isinstance(item, str) else _texto_do_passo(item)
        for item in _como_lista(objeto.get("itemListElement"))
        if isinstance(item, str | dict)
    ]
    if texto := "\n".join(filter(None, de_dentro)):
        return texto
    return _texto(objeto.get("name"))


def _repete_o_texto(nome: str, texto: str) -> bool:
    """O `name` do passo é o próprio texto, inteiro ou cortado ("Deixe o feijão de molho…")."""
    inicio = " ".join(nome.casefold().split()).rstrip(".…").rstrip()
    return " ".join(texto.casefold().split()).startswith(inicio)


def _secao_aberta_pelo_passo(objeto: dict[str, Any], texto: str) -> tuple[bool, str | None]:
    """Se o `name` do passo abre uma seção, e com que título.

    O TudoGostoso marca a seção assim: o primeiro passo da massa traz
    `"name": "Massa"` e o texto do passo, e a página mostra "Massa" como título
    em cima dele e dos seguintes, até o próximo passo com nome. O `name` que
    repete o texto (muitos sites copiam o texto nele, às vezes cortado) não é
    título de nada, e o texto sempre vale mais que ele.
    """
    nome = " ".join(_texto(objeto.get("name")).split())
    tem_texto_proprio = bool(_texto(objeto.get("text"))) or "itemListElement" in objeto
    if not nome or not tem_texto_proprio or _repete_o_texto(nome, texto):
        return False, None
    return True, titulo_da_secao(nome)


def _e_secao(objeto: dict[str, Any]) -> bool:
    """`HowToSection`, `ItemList` ou qualquer objeto sem texto que só agrupa outros passos."""
    tipos = _tipos(objeto)
    if "howtostep" in tipos:
        return False
    if tipos & {"howtosection", "itemlist"}:
        return True
    return "itemListElement" in objeto and not _texto(objeto.get("text"))


def _ler_passos(itens: list[Any], secao: str | None, saida: list[_PassoLido]) -> None:
    """Os passos de uma lista, na ordem em que a página os publica.

    A ordem é a da lista, nunca a de `position`: há site que numera as posições
    de um jeito e mostra de outro, e o que ela lê na página é a ordem da lista.
    """
    atual = secao
    for bruto in itens:
        item = bruto
        # `ListItem` embrulha o passo em `item`.
        while isinstance(item, dict) and "item" in item and "listitem" in _tipos(item):
            item = item["item"]
        if isinstance(item, list):
            _ler_passos(item, atual, saida)
        elif isinstance(item, str):
            saida.extend(_PassoLido((linha,), atual, declarado=False) for linha in _linhas(item))
        elif isinstance(item, dict) and _e_secao(item):
            nome = _texto(item.get("name"))
            dentro = titulo_da_secao(nome) if nome.strip() else atual
            _ler_passos(_como_lista(item.get("itemListElement")), dentro, saida)
        elif isinstance(item, dict):
            texto = _texto_do_passo(item)
            abre, titulo = _secao_aberta_pelo_passo(item, texto)
            if abre:
                atual = titulo
            if linhas := tuple(linha for linha in texto.splitlines() if linha):
                saida.append(_PassoLido(linhas, atual, declarado=True))


def passos_do_preparo(bruto: Any) -> tuple[tuple[str, ...], tuple[str | None, ...]]:
    """Os passos do `recipeInstructions`, na ordem e com o texto da página, e a seção de cada um.

    O schema.org aceita texto, lista de textos, `HowToStep`, `HowToSection` com
    os passos em `itemListElement` e listas dentro de listas, e os sites usam
    todas. O que muda do texto da página é só o que a tela não mostra:
    etiqueta HTML, entidade e espaço repetido.

    Um `HowToStep` é um passo só: a quebra de linha dentro dele é da
    formatação, não um passo novo. O texto solto pode juntar vários passos,
    um por linha, e aí cada linha é um passo; o mesmo vale para o site que
    põe o preparo inteiro num `HowToStep` só.

    Antes a seção inteira virava um passo com o nome dela: o feijão do
    Receitas Nestlé saía com um passo só, "Modo de Preparo", e os cinco passos
    de verdade sumiam.

    As seções vêm vazias quando nenhum passo está numa seção com título.
    """
    lidos: list[_PassoLido] = []
    _ler_passos(_como_lista(bruto), None, lidos)
    if len(lidos) == 1 and lidos[0].declarado and len(lidos[0].linhas) > 1:
        unico = lidos[0]
        lidos = [_PassoLido((linha,), unico.secao, declarado=False) for linha in unico.linhas]
    textos = tuple(" ".join(passo.linhas) for passo in lidos)
    secoes = tuple(passo.secao for passo in lidos)
    return textos, (secoes if any(secoes) else ())


def duracao_em_minutos(bruto: Any) -> int | None:
    """ "PT1H30M" -> 90. Devolve `None` quando não dá para ler, nunca zero.

    Zero seria lido como "instantâneo" pelo portão e o tempo por fornada deixaria
    de ser checado: um valor ausente virando permissão.
    """
    texto = _texto(bruto)
    if not texto:
        return None
    if casou := _DURACAO.match(texto):
        dias = int(casou.group("dias") or 0)
        horas = int(casou.group("horas") or 0)
        minutos = int(casou.group("minutos") or 0)
        total = dias * MINUTOS_POR_DIA + horas * MINUTOS_POR_HORA + minutos
        if total > 0:
            return total
    if simples := _PRIMEIRO_INTEIRO.search(texto):
        valor = int(simples.group())
        return valor or None
    return None


#: O número do rendimento só é de porções se não vier seguido de massa,
#: volume ou tempo: "500 g", "1,5 litro" e "30 minutos" não dizem quantas
#: porções saem da receita.
_NAO_E_PORCAO = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:k?g|gramas?|quilos?|m?l|litros?|min|minutos?|h|horas?)\b",
    re.IGNORECASE,
)


#: Acima disso, um número solto é mais provável dado errado do site do que
#: verdade: um site real publica "46" onde queria dizer "4 a 6". Com a unidade
#: dita ("30 unidades", "40 brigadeiros"), o número grande é crível.
RENDIMENTO_MAXIMO_SEM_UNIDADE = 24

#: Um número sozinho, sem dizer do quê.
_SO_NUMERO = re.compile(r"^\s*\d+\s*$")


def rendimento_informado(bruto: Any) -> bool:
    """O site disse quantas porções, de um jeito em que dá para confiar?

    Número de massa, volume ou tempo não conta; número grande solto também não.
    """
    texto = str(bruto) if isinstance(bruto, int) else _texto(bruto)
    casou = _PRIMEIRO_INTEIRO.search(texto)
    if casou is None or _NAO_E_PORCAO.search(texto) or int(casou.group()) <= 0:
        return False
    return not (_SO_NUMERO.match(texto) and int(casou.group()) > RENDIMENTO_MAXIMO_SEM_UNIDADE)


def rendimento_em_porcoes(bruto: Any) -> int:
    """ "4 porções", "Rende 6", 8 -> o inteiro. Sem número reconhecível, 1.

    Um chute para cima dividiria o custo por porções que não existem e faria o
    prato parecer mais barato do que é, erro que só aparece no fim do mês.
    """
    if isinstance(bruto, int) and bruto > 0:
        return bruto
    if not rendimento_informado(bruto):
        return 1
    texto = _texto(bruto)
    if casou := _PRIMEIRO_INTEIRO.search(texto):
        return max(1, int(casou.group()))
    return 1


def de_json_ld(html: str) -> dict[str, Any]:
    """O primeiro objeto `schema.org/Recipe` da página."""
    cacador = _CacadorDeJsonLd()
    cacador.feed(html)
    return _receita_dos_blocos(cacador.blocos)


def _receita_dos_blocos(blocos: list[str]) -> dict[str, Any]:
    for bloco in blocos:
        try:
            dados = json.loads(bloco)
        except json.JSONDecodeError:
            # Bloco quebrado não derruba a extração: sites põem vários, e basta
            # um estar bom.
            continue
        for objeto in _achatar(dados):
            if _e_receita(objeto):
                return objeto
    raise ExtracaoFalhou("nenhum bloco JSON-LD do tipo Recipe na página")


def de_microdata(html: str) -> dict[str, Any]:
    """Receita em microdata, a geração anterior do mesmo padrão."""
    cacador = _CacadorDeMicrodata()
    cacador.feed(html)
    campos = cacador.campos

    ingredientes = campos.get("recipeingredient") or campos.get("ingredients") or []
    if not ingredientes:
        raise ExtracaoFalhou("nenhum itemprop de ingrediente na página")

    return {
        "name": (campos.get("name") or [""])[0],
        "recipeIngredient": ingredientes,
        "recipeInstructions": _sem_o_numero_do_passo(
            campos.get("recipeinstructions", []), cacador.numeros.get("recipeinstructions", [])
        ),
        "recipeYield": (campos.get("recipeyield") or [""])[0],
        "prepTime": (campos.get("preptime") or [""])[0],
        "cookTime": (campos.get("cooktime") or [""])[0],
        "totalTime": (campos.get("totaltime") or [""])[0],
    }


def _sem_o_numero_do_passo(passos: list[str], numeros: list[str]) -> list[str]:
    """ "1 Tempere o peixe" vira "Tempere o peixe": o número é da lista da página, não do texto.

    Sai só o número que a página põe numa etiqueta própria no começo do passo
    (`<span>1</span>`) e que segue a contagem dela: o seguinte ao anterior, ou
    1 quando a página recomeça a contar numa parte nova da receita. O Receitas
    da Globo conta 1, 2, 3 no prato e de novo 1, 2 no molho; antes o número só
    saía quando era a posição na receita inteira, e o passo do molho chegava na
    tela como "1 Misture todos os ingredientes". O número escrito no próprio
    texto ("2 colheres de açúcar") nunca sai: é o texto dela.
    """
    saida = []
    anterior = 0
    for passo, numero in zip(passos, numeros, strict=True):
        casou = _NUMERO_NA_ETIQUETA.fullmatch(numero)
        valor = int(casou.group(1)) if casou else None
        if valor is not None and valor in {anterior + 1, 1}:
            saida.append(passo[len(numero) :].strip())
            anterior = valor
        else:
            saida.append(passo)
    return saida


def para_receita(
    objeto: dict[str, Any], url: str, fonte: str = "", *, foto_de_reserva: str | None = None
) -> ReceitaExtraida:
    """Um objeto schema.org virando `Receita` do domínio.

    A `Receita` nasce com `origem=WEB`, e o próprio tipo recusa isso sem URL:
    é o que garante que nenhuma receita pesquisada chegue à Dona Maria sem ela
    poder conferir de onde veio.

    Os três tempos ficam separados, como o site publica. Antes o total (com as
    esperas) ocupava o lugar do tempo no fogo, e o portão comparava a marinada
    de uma noite com o tempo que ela tem por cozinhada.

    `foto_de_reserva` é a foto que a página declara para quem a compartilha
    (`og:image`): vale só quando a receita estruturada não declara foto nenhuma.
    """
    nome = _texto(objeto.get("name")) or "Receita sem nome"
    linhas = _lista_de_textos(objeto.get("recipeIngredient") or objeto.get("ingredients"))
    if not linhas:
        raise ExtracaoFalhou(f"a página de {nome!r} não trouxe lista de ingredientes")

    ingredientes = tuple(interpretar_linha(linha) for linha in linhas)
    passos, secoes = passos_do_preparo(objeto.get("recipeInstructions"))
    receita = Receita(
        nome=nome,
        ingredientes=ingredientes,
        rendimento_porcoes=rendimento_em_porcoes(objeto.get("recipeYield")),
        rendimento_informado=rendimento_informado(objeto.get("recipeYield")),
        modo_preparo=passos,
        secoes_do_preparo=secoes,
        tempo_preparo_min=duracao_em_minutos(objeto.get("prepTime")),
        tempo_cozimento_min=duracao_em_minutos(objeto.get("cookTime")),
        tempo_total_min=duracao_em_minutos(objeto.get("totalTime")),
        url=url,
        fonte=fonte or _dominio(url),
        origem=Origem.WEB,
    ).com_exigencias_detectadas()

    return ReceitaExtraida(
        receita=receita,
        url=url,
        fonte=fonte or _dominio(url),
        autor=_texto(objeto.get("author")),
        # O site é o nome que a própria página se dá, ou o domínio: nunca o que
        # quem pediu a busca disse que era.
        site=_texto(objeto.get("publisher")) or _dominio(url),
        imagem_url=(
            imagem_da_pagina(objeto.get("image"), url) or imagem_da_pagina(foto_de_reserva, url)
        ),
        preparo_min=duracao_em_minutos(objeto.get("prepTime")),
        cozimento_min=duracao_em_minutos(objeto.get("cookTime")),
        total_min=duracao_em_minutos(objeto.get("totalTime")),
        rendimento_texto=_rendimento_escrito(objeto.get("recipeYield")),
        hash_do_conteudo=hash_do_conteudo(objeto),
    )


def _rendimento_escrito(bruto: Any) -> str:
    """O rendimento como a página escreveu ("4 porções", "500 g"), para mostrar a ela."""
    return str(bruto) if isinstance(bruto, int) else _texto(bruto)


#: O tamanho no endereço: "-730x480.jpg" (WordPress), "/1200-675/" (TudoGostoso).
_TAMANHO_NO_ENDERECO = re.compile(r"(?<![0-9])(\d{2,5})[x-](\d{2,5})(?=[./_-])")
#: O sufixo de tamanho do WordPress, antes da extensão: "foto-400x400.jpg".
_SUFIXO_DE_TAMANHO = re.compile(r"-\d{2,5}x\d{2,5}(?=\.\w{2,5}$)")
#: O que não é endereço de foto, mas aparece no lugar de um: "None", "null".
_NAO_E_ENDERECO: frozenset[str] = frozenset({"none", "null", "undefined", "false", "#"})


def _dimensao(valor: Any) -> int:
    """ "1200", 1200, "1200px" ou {"@value": 1200}: o número, ou 0."""
    if isinstance(valor, dict):
        valor = valor.get("@value") or valor.get("value")
    casou = re.match(r"\s*(\d{1,5})", str(valor)) if valor is not None else None
    return int(casou.group(1)) if casou else 0


def _candidatas(bruto: Any, url_da_pagina: str) -> list[tuple[str, int]]:
    """Cada foto declarada, absoluta e só http ou https, com a área que declara (0 se não diz)."""
    itens = bruto if isinstance(bruto, list) else [bruto]
    saida: list[tuple[str, int]] = []
    for item in itens:
        endereco: Any = item
        area = 0
        if isinstance(item, dict):
            endereco = item.get("url") or item.get("contentUrl")
            area = _dimensao(item.get("width")) * _dimensao(item.get("height"))
        if not isinstance(endereco, str) or not endereco.strip():
            continue
        limpo = unescape(endereco.strip())
        if limpo.lower() in _NAO_E_ENDERECO or not re.search(r"[./]", limpo):
            continue
        absoluto = urljoin(url_da_pagina, limpo)
        partes = urlsplit(absoluto)
        if partes.scheme not in ("http", "https") or not partes.hostname:
            continue
        if not area and (tamanho := _TAMANHO_NO_ENDERECO.search(partes.path)):
            area = int(tamanho.group(1)) * int(tamanho.group(2))
        saida.append((absoluto, area))
    return saida


def imagem_da_pagina(bruto: Any, url_da_pagina: str) -> str | None:
    """A maior foto que a página declara, absoluta e só http ou https; nunca a genérica.

    O schema.org aceita texto, lista, ou objeto `ImageObject` com `url` (e
    `width` e `height`). Da lista vale a maior: pela largura e altura que a
    página declara, ou pelo tamanho escrito no endereço ("-730x480.jpg"). A
    original do WordPress, sem sufixo, é maior que os recortes dela. Sem
    tamanho nenhum, vale a primeira. `data:` e outros esquemas não entram, e a
    imagem genérica do site ("placeholder") também não
    (`mise.catalogo.foto_generica`): sem foto, a tela mostra o gradiente.
    """
    candidatas = [(url, area) for url, area in _candidatas(bruto, url_da_pagina)]
    candidatas = [(url, area) for url, area in candidatas if not foto_generica(url)]
    if not candidatas:
        return None
    recortes: dict[str, int] = {}
    for url, area in candidatas:
        original = _SUFIXO_DE_TAMANHO.sub("", url)
        if original != url:
            recortes[original] = max(recortes.get(original, 0), area)
    # A original de que saíram os recortes é maior que qualquer um deles.
    medidas = [
        (url, area or (recortes[url] + 1 if url in recortes else 0)) for url, area in candidatas
    ]
    return max(medidas, key=lambda par: par[1])[0]


def hash_do_conteudo(objeto: dict[str, Any]) -> str:
    """O sha256 do objeto de receita lido, com as chaves em ordem: muda só se a receita mudou."""
    bruto = json.dumps(objeto, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(bruto.encode()).hexdigest()


def extrair(html: str, url: str, fonte: str = "") -> ReceitaExtraida:
    """Receita a partir do HTML de uma página, tentando JSON-LD e depois microdata."""
    cacador = _CacadorDeJsonLd()
    cacador.feed(html)
    try:
        objeto = _receita_dos_blocos(cacador.blocos)
    except ExtracaoFalhou:
        objeto = de_microdata(html)
    _recusar_outra_lingua(html, objeto)
    reserva = cacador.og_image
    if reserva is None or foto_generica(urljoin(url, reserva)):
        reserva = _foto_do_prato_no_corpo(cacador.imagens, str(objeto.get("name") or ""), url)
    return para_receita(objeto, url, fonte, foto_de_reserva=reserva)


_MENOR_PALAVRA_DO_PRATO = 3
_PALAVRAS_QUE_NAO_DIZEM_O_PRATO = frozenset(
    {
        "receita",
        "receitas",
        "de",
        "da",
        "do",
        "das",
        "dos",
        "com",
        "e",
        "ao",
        "na",
        "no",
        "facil",
        "simples",
    }
)


def _foto_do_prato_no_corpo(imagens: list[tuple[str, str]], nome: str, url: str) -> str | None:
    """A primeira imagem do corpo cuja descrição cita o prato, quando a página não declara foto.

    Sem essa pista, nenhuma: a tela mostra o gradiente com o ícone, que diz a verdade.
    """
    palavras = [
        p
        for p in re.findall(r"[a-z0-9]+", _sem_acento(nome.lower()))
        if len(p) > _MENOR_PALAVRA_DO_PRATO and p not in _PALAVRAS_QUE_NAO_DIZEM_O_PRATO
    ]
    if not palavras:
        return None
    for fonte, alternativo in imagens:
        endereco = urljoin(url, fonte)
        if foto_generica(endereco):
            continue
        if palavras[0] in _sem_acento(alternativo.lower()):
            return endereco
    return None


_SO_PORTUGUES = "a receita está em outra língua; só leio receitas em português"
_LINGUA_DA_PAGINA = re.compile(r"<html[^>]*\blang\s*=\s*[\"']?([A-Za-z-]+)", re.IGNORECASE)
_MEDIDA_EM_INGLES = re.compile(
    r"\b(cups?|tablespoons?|teaspoons?|tbsp|tsp|grams?|kilograms?|pinch|ounces?|oz|lbs?|pounds?)\b",
    re.IGNORECASE,
)


def _recusar_outra_lingua(html: str, objeto: Mapping[str, Any]) -> None:
    """Só entra receita em português: ingrediente em outra língua não casa com a despensa dela.

    Uma receita em inglês ("1 cup Toasted manioc flour") viraria uma lista de compra
    falsa, com tudo o que ela já tem. Vale a língua declarada da receita, depois a da
    página, e, sem nenhuma das duas, as medidas escritas em inglês nos ingredientes.
    """
    declarada = str(objeto.get("inLanguage") or "").strip().lower()
    achada = _LINGUA_DA_PAGINA.search(html[:5000])
    pagina = achada.group(1).lower() if achada else ""
    for lingua in (declarada, pagina):
        if lingua:
            if not lingua.startswith("pt"):
                raise ExtracaoFalhou(_SO_PORTUGUES)
            return
    linhas = [str(x) for x in (objeto.get("recipeIngredient") or []) if str(x).strip()]
    em_ingles = sum(1 for linha in linhas if _MEDIDA_EM_INGLES.search(linha))
    if linhas and em_ingles >= max(3, len(linhas) // 2):
        raise ExtracaoFalhou(_SO_PORTUGUES)


def _dominio(url: str) -> str:
    """O domínio, que é como a Dona Maria reconhece a fonte."""
    sem_esquema = re.sub(r"^https?://", "", url.strip())
    return sem_esquema.split("/")[0].removeprefix("www.")


__all__ = [
    "ExtracaoFalhou",
    "ReceitaExtraida",
    "de_json_ld",
    "de_microdata",
    "duracao_em_minutos",
    "extrair",
    "hash_do_conteudo",
    "imagem_da_pagina",
    "para_receita",
    "passos_do_preparo",
    "rendimento_em_porcoes",
    "rendimento_informado",
    "titulo_da_secao",
]
