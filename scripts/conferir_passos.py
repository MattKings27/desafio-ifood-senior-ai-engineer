"""Confere se os passos de cada receita do catálogo são os da página de onde vieram.

Para cada receita do catálogo (lida da API no ar, só com GET) ou para cada
endereço passado, busca a página pelo mesmo caminho que a plataforma usa
(`retrieval.busca.baixar`: só endereço público, o mesmo agente) e tira os
passos direto do JSON-LD (`recipeInstructions`) com um leitor de referência
simples, escrito aqui e independente do extrator. Depois compara com:

a) o que a plataforma guardou e mostra (`passos[].texto` e, quando a API já
   diz, `passos[].secao`);
b) o que o extrator de agora tira do mesmo HTML.

    python scripts/conferir_passos.py                # o catálogo da API em 127.0.0.1:8777
    python scripts/conferir_passos.py --api http://127.0.0.1:8777
    python scripts/conferir_passos.py https://www.tudogostoso.com.br/receita/...
    python scripts/conferir_passos.py --gravar       # e grava o JSON-LD e o guardado
    python scripts/conferir_passos.py --gravadas     # confere com o que foi gravado

Uma linha por receita. Sai com erro quando o extrator diverge da página (b),
ou quando a página não veio. A página sem JSON-LD de receita não tem com o
que comparar: aparece na lista, sem erro. O guardado que diverge (a) é
receita lida antes da correção: só muda buscando a página de novo, e isso
não é deste script, que nunca escreve na API.

O leitor de referência segue a página: a ordem da lista, o texto sem
etiqueta, sem entidade e sem espaço repetido, o `text` do passo antes do
`name`, cada seção com o nome dela, e o título que a página mostra (a seção
"Modo de Preparo" não tem título; "Massa" tem).
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

RAIZ: Final = Path(__file__).resolve().parents[1]
GRAVADAS: Final = RAIZ / "scripts" / "tests" / "fixtures" / "passos"
API: Final = "http://127.0.0.1:8777"

#: As abas da grade: juntas, cobrem o catálogo que a tela mostra.
ABAS: Final = ("pode_fazer", "falta_resposta", "ranking", "nao_quer")

#: As chaves do objeto Recipe que a gravação guarda: o mínimo para o extrator
#: aceitar a receita e para conferir os passos.
CHAVES_GRAVADAS: Final = (
    "@context",
    "@type",
    "name",
    "recipeIngredient",
    "recipeInstructions",
)

#: Quanto de cada texto a linha do relatório mostra.
TRECHO: Final = 60


# --------------------------------------------------------------------------- #
# O leitor de referência                                                       #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Passo:
    """Um passo como a página mostra: o texto e o título da seção em que está."""

    texto: str
    secao: str | None = None


@dataclass(frozen=True, slots=True)
class PassoDaPagina:
    """Um passo lido do JSON-LD, com o nome da seção como a página escreveu."""

    texto: str
    nome_da_secao: str | None
    secao: str | None

    def como_mostrado(self) -> Passo:
        return Passo(self.texto, self.secao)


#: A etiqueta de bloco (e a quebra de linha) começa outra linha na página; as
#: outras etiquetas somem sem deixar espaço.
_QUEBRA: Final = re.compile(
    r"<\s*/?\s*(?:br|p|li|div|ul|ol|h[1-6]|tr|table|section|article|blockquote)\b[^<>]*>"
    r"|\r\n|\r|\n",
    re.IGNORECASE,
)
_ETIQUETA: Final = re.compile(r"<[^<>]*>")
_SEM_TITULO: Final = frozenset(
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
_SO_NUMERO: Final = re.compile(r"(?:passo|etapa)?\s*\d+\s*[.:)ºª°-]?")


def _desescapado(texto: str) -> str:
    """Sem entidade, nem a escapada duas ou três vezes ("&amp;atilde;")."""
    for _ in range(3):
        novo = html.unescape(texto)
        if novo == texto:
            break
        texto = novo
    return texto


def linhas(texto: str) -> list[str]:
    """As linhas do texto, cada uma sem etiqueta e com os espaços juntados."""
    pedacos = _QUEBRA.split(_desescapado(texto))
    limpos = (" ".join(_ETIQUETA.sub("", pedaco).split()) for pedaco in pedacos)
    return [linha for linha in limpos if linha]


def titulo(nome: str) -> str | None:
    """O título que a página mostra para a seção, ou `None` ("Modo de Preparo")."""
    limpo = " ".join(nome.split())
    decomposto = unicodedata.normalize("NFKD", limpo)
    chave = "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()
    chave = chave.strip(" :.-")
    if not chave or chave in _SEM_TITULO or _SO_NUMERO.fullmatch(chave):
        return None
    return limpo


def _tipos(objeto: dict[str, Any]) -> set[str]:
    """Os tipos, sem prefixo ("schema:HowToStep" e "http://schema.org/HowToStep")."""
    bruto = objeto.get("@type") or ""
    lista = bruto if isinstance(bruto, list) else [bruto]
    return {
        str(t).replace("#", "/").replace(":", "/").split("/")[-1].lower() for t in lista
    }


def _lista(valor: Any) -> list[Any]:
    if valor is None:
        return []
    return valor if isinstance(valor, list) else [valor]


def _texto_simples(valor: Any) -> str:
    """O texto de um campo: texto, lista de textos, ou objeto com `@value`."""
    if isinstance(valor, str):
        return valor
    if isinstance(valor, list):
        return " ".join(_texto_simples(v) for v in valor)
    if isinstance(valor, dict):
        return _texto_simples(
            valor.get("text") or valor.get("name") or valor.get("@value")
        )
    return ""


def _agrupa(objeto: dict[str, Any]) -> bool:
    """Seção, lista, ou qualquer objeto que só agrupa passos (nunca um HowToStep)."""
    tipos = _tipos(objeto)
    if "howtostep" in tipos:
        return False
    if "howtosection" in tipos or "itemlist" in tipos:
        return True
    return "itemListElement" in objeto and not linhas(
        _texto_simples(objeto.get("text"))
    )


def _linhas_do_passo(objeto: dict[str, Any]) -> tuple[list[str], bool]:
    """As linhas do texto do passo, e se ele tem texto além do `name`."""
    if proprio := linhas(_texto_simples(objeto.get("text"))):
        return proprio, True
    dentro: list[str] = []
    for filho in _lista(objeto.get("itemListElement")):
        if isinstance(filho, str):
            dentro += linhas(filho)
        elif isinstance(filho, dict):
            dentro += _linhas_do_passo(filho)[0]
    if dentro:
        return dentro, True
    return linhas(_texto_simples(objeto.get("name"))), False


def _copia(nome: str, texto: str) -> bool:
    """O `name` repete o texto do passo, inteiro ou cortado com reticências."""
    comeco = " ".join(nome.casefold().split()).rstrip(".…").rstrip()
    return " ".join(texto.casefold().split()).startswith(comeco)


@dataclass
class _Leitura:
    passos: list[tuple[list[str], str | None, bool]] = field(default_factory=list)


def _ler(itens: list[Any], secao: str | None, leitura: _Leitura) -> None:
    """Cada item, na ordem da lista; `secao` é o nome da seção em que estão."""
    atual = secao
    for bruto in itens:
        item = bruto
        while isinstance(item, dict) and "listitem" in _tipos(item) and "item" in item:
            item = item["item"]
        if isinstance(item, list):
            _ler(item, atual, leitura)
        elif isinstance(item, str):
            leitura.passos += [([linha], atual, False) for linha in linhas(item)]
        elif isinstance(item, dict) and _agrupa(item):
            nome = " ".join(_texto_simples(item.get("name")).split())
            _ler(_lista(item.get("itemListElement")), nome or atual, leitura)
        elif isinstance(item, dict):
            texto, proprio = _linhas_do_passo(item)
            nome = " ".join(_texto_simples(item.get("name")).split())
            if proprio and nome and not _copia(nome, " ".join(texto)):
                atual = nome
            if texto:
                leitura.passos.append((texto, atual, True))


def passos_da_pagina(instrucoes: Any) -> list[PassoDaPagina]:
    """Os passos do `recipeInstructions`, como a página mostra.

    Texto solto pode juntar vários passos, um por linha; um `HowToStep` é um
    passo só, a não ser que seja o único da receita (o site pôs o preparo
    inteiro nele, um passo por linha).
    """
    leitura = _Leitura()
    _ler(_lista(instrucoes), None, leitura)
    passos = leitura.passos
    if len(passos) == 1 and passos[0][2] and len(passos[0][0]) > 1:
        unico, nome, _ = passos[0]
        passos = [([linha], nome, False) for linha in unico]
    return [
        PassoDaPagina(" ".join(texto), nome, titulo(nome) if nome else None)
        for texto, nome, _ in passos
    ]


def forma(no: Any) -> str:
    """A forma do `recipeInstructions`, para o relatório: tipos, campos e seções."""
    if isinstance(no, str):
        return "texto" + (" com quebra de linha" if _QUEBRA.search(no) else "")
    if isinstance(no, dict):
        tipo = "/".join(sorted(str(t) for t in _lista(no.get("@type")))) or "objeto"
        if _agrupa(no):
            nome = " ".join(_texto_simples(no.get("name")).split())
            rotulo = f" «{nome}»" if nome else ""
            return f"{tipo}{rotulo} [{forma(no.get('itemListElement'))}]"
        campos = "+".join(c for c in ("name", "text", "itemListElement") if c in no)
        dentro = f" > {forma(no['itemListElement'])}" if "itemListElement" in no else ""
        return f"{tipo}({campos}){dentro}"
    if isinstance(no, list):
        grupos: list[list[Any]] = []
        for parte in (forma(item) for item in no):
            if grupos and grupos[-1][0] == parte:
                grupos[-1][1] += 1
            else:
                grupos.append([parte, 1])
        return ", ".join(f"{n} × {parte}" if n > 1 else parte for parte, n in grupos)
    return "nada" if no is None else type(no).__name__


# --------------------------------------------------------------------------- #
# A página                                                                     #
# --------------------------------------------------------------------------- #

_BLOCO_JSON_LD: Final = re.compile(
    r"<script[^>]*type\s*=\s*[\"']?application/ld\+json[^>]*>(.*?)</script\s*>",
    re.IGNORECASE | re.DOTALL,
)


def _objetos(no: Any) -> Iterable[dict[str, Any]]:
    """Todo objeto do JSON-LD, na ordem do documento, entrando em `@graph` e listas."""
    if isinstance(no, list):
        for item in no:
            yield from _objetos(item)
    elif isinstance(no, dict):
        yield no
        for chave in ("@graph", "mainEntity", "mainEntityOfPage", "itemListElement"):
            if chave in no:
                yield from _objetos(no[chave])


def receita_da_pagina(pagina: str) -> dict[str, Any] | None:
    """O primeiro objeto `Recipe` do JSON-LD da página, ou `None`."""
    for bloco in _BLOCO_JSON_LD.findall(pagina):
        try:
            dados = json.loads(bloco)
        except json.JSONDecodeError:
            continue
        for objeto in _objetos(dados):
            if "recipe" in _tipos(objeto):
                return objeto
    return None


def pagina_de(receita: dict[str, Any]) -> str:
    """Uma página mínima com a receita no JSON-LD, para o extrator ler sem rede."""
    bloco = json.dumps(receita, ensure_ascii=False).replace("</", "<\\/")
    return (
        f'<html><head><script type="application/ld+json">{bloco}</script></head></html>'
    )


def do_extrator(pagina: str, url: str) -> list[Passo]:
    """O que o extrator de agora tira da página: o texto e a seção de cada passo.

    A recusa do extrator (página sem receita que ele leia) vira `ValueError`.
    """
    from mise.erros import ErroMise
    from retrieval.extrator import ExtracaoFalhou, extrair

    try:
        receita = extrair(pagina, url).receita
    except (ExtracaoFalhou, ErroMise) as erro:
        raise ValueError(f"o extrator recusou a página: {erro}") from erro
    return [
        Passo(texto, secao)
        for texto, secao in zip(
            receita.modo_preparo, receita.secao_de_cada_passo, strict=True
        )
    ]


def ler_da_rede(url: str) -> str:
    """A página, pelo mesmo caminho que a plataforma usa para buscar receita.

    A busca que não dá certo (fora do ar, endereço recusado) vira `OSError`.
    """
    from retrieval.busca import BuscaFalhou, baixar

    try:
        return baixar(url)
    except BuscaFalhou as erro:
        raise OSError(str(erro)) from erro


# --------------------------------------------------------------------------- #
# O catálogo, lido da API no ar (só GET)                                       #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ReceitaDoCatalogo:
    """Uma receita que a plataforma guardou: de onde veio e os passos que mostra."""

    url: str
    slug: str = ""
    #: `None` quando a receita não veio da API (o endereço foi passado à mão).
    guardados: tuple[Passo, ...] | None = None
    #: A API diz a seção de cada passo? A de antes das seções não diz.
    com_secao: bool = False


LerJson = Callable[[str], Any]


def _get_json(url: str) -> Any:
    """GET e nada mais: a conferência nunca escreve na API."""
    requisicao = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(requisicao, timeout=30) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def _dados(resposta: Any) -> Any:
    return (
        resposta["dados"]
        if isinstance(resposta, dict) and "dados" in resposta
        else resposta
    )


def catalogo_da_api(api: str, ler_json: LerJson = _get_json) -> list[ReceitaDoCatalogo]:
    """Cada receita das abas da grade, uma vez só, com os passos que a tela mostra."""
    base = api.rstrip("/")
    slugs: dict[str, None] = {}
    for aba in ABAS:
        lista = _dados(ler_json(f"{base}/api/receitas?aba={aba}"))
        slugs.update((item["slug"], None) for item in lista.get("itens", []))
    saida = []
    for slug in slugs:
        detalhe = _dados(ler_json(f"{base}/api/receitas/{urllib.parse.quote(slug)}"))
        passos = detalhe.get("passos", [])
        saida.append(
            ReceitaDoCatalogo(
                url=detalhe["fonte"]["url"],
                slug=slug,
                guardados=tuple(Passo(p["texto"], p.get("secao")) for p in passos),
                com_secao=any("secao" in p for p in passos),
            )
        )
    return saida


# --------------------------------------------------------------------------- #
# A conferência                                                                #
# --------------------------------------------------------------------------- #


def _curto(texto: str) -> str:
    return texto if len(texto) <= TRECHO else texto[: TRECHO - 1] + "…"


def diferenca(
    esperados: Sequence[Passo], obtidos: Sequence[Passo], *, com_secao: bool = True
) -> str:
    """ "" quando os passos batem; senão a primeira diferença, dita em português."""
    for ordem, (esperado, obtido) in enumerate(
        zip(esperados, obtidos, strict=False), 1
    ):
        if esperado.texto != obtido.texto:
            return (
                f"passo {ordem}: a página diz «{_curto(esperado.texto)}», "
                f"veio «{_curto(obtido.texto)}»"
            )
        if com_secao and esperado.secao != obtido.secao:
            return (
                f"passo {ordem}: a página põe na seção {esperado.secao or 'sem título'}, "
                f"veio {obtido.secao or 'sem título'}"
            )
    if len(esperados) != len(obtidos):
        return f"a página tem {len(esperados)} passos, veio {len(obtidos)}"
    return ""


@dataclass(frozen=True, slots=True)
class Resultado:
    """A conferência de uma receita."""

    receita: ReceitaDoCatalogo
    forma: str = ""
    esperados: tuple[PassoDaPagina, ...] = ()
    #: "" quando bate; `None` quando não há guardado para comparar.
    guardado: str | None = None
    extrator: str = ""
    #: Por que não deu para conferir ("" quando deu): a página que não vem.
    falha: str = ""
    #: A página não traz JSON-LD de receita: não há com o que comparar. O
    #: extrator lê o microdata dela, e isso fica para os testes do extrator.
    sem_json_ld: bool = False

    @property
    def extrator_ok(self) -> bool:
        return not self.falha and not self.extrator

    def linha(self) -> str:
        """Uma linha do relatório, em português."""
        quem = self.receita.slug or "-"
        if self.falha:
            return f"FALHA    {quem}  {self.receita.url}  ({self.falha})"
        if self.sem_json_ld:
            return f"sem-json {quem}  {self.receita.url}  (a página não traz JSON-LD de receita)"
        marca = "ok" if self.extrator_ok and not self.guardado else "diverge"
        secoes = dict.fromkeys(
            p.nome_da_secao for p in self.esperados if p.nome_da_secao
        )
        rotulos = [
            f"«{nome}»" + ("" if titulo(nome) else " sem título") for nome in secoes
        ]
        nomes = f", seções {', '.join(rotulos)}" if rotulos else ""
        if self.guardado is None:
            guardado = "sem guardado"
        elif self.guardado:
            guardado = f"diverge ({self.guardado})"
        else:
            guardado = "ok" + (
                "" if self.receita.com_secao else " (o texto; a API não diz a seção)"
            )
        extrator = f"diverge ({self.extrator})" if self.extrator else "ok"
        return (
            f"{marca:<8} {quem}  {self.receita.url}  {len(self.esperados)} passos{nomes}  "
            f"[{self.forma}]  guardado: {guardado}  extrator: {extrator}"
        )


Leitor = Callable[[str], str]


def conferir(receita: ReceitaDoCatalogo, pagina: str) -> Resultado:
    """Os passos da página contra o guardado e contra o extrator de agora."""
    objeto = receita_da_pagina(pagina)
    if objeto is None:
        return Resultado(receita, sem_json_ld=True)
    instrucoes = objeto.get("recipeInstructions")
    esperados = tuple(passos_da_pagina(instrucoes))
    mostrados = [p.como_mostrado() for p in esperados]
    guardado = None
    if receita.guardados is not None:
        guardado = diferenca(mostrados, receita.guardados, com_secao=receita.com_secao)
    try:
        extrator = diferenca(mostrados, do_extrator(pagina, receita.url))
    except ValueError as erro:
        extrator = str(erro)
    return Resultado(receita, forma(instrucoes), esperados, guardado, extrator)


def conferir_todas(
    receitas: Sequence[ReceitaDoCatalogo], ler: Leitor
) -> list[Resultado]:
    resultados = []
    for receita in receitas:
        try:
            pagina = ler(receita.url)
        except (OSError, ValueError) as erro:
            resultados.append(Resultado(receita, falha=f"a página não veio: {erro}"))
            continue
        resultados.append(conferir(receita, pagina))
    return resultados


# --------------------------------------------------------------------------- #
# A gravação, para os testes sem rede                                          #
# --------------------------------------------------------------------------- #


def _nome_do_arquivo(receita: ReceitaDoCatalogo) -> str:
    if receita.slug:
        return f"{receita.slug}.json"
    caminho = urllib.parse.urlsplit(receita.url)
    return (
        re.sub(r"[^a-z0-9]+", "-", f"{caminho.hostname}{caminho.path}".lower()).strip(
            "-"
        )
        + ".json"
    )


def gravar(
    receita: ReceitaDoCatalogo, pagina: str, destino: Path, hoje: dt.date
) -> Path:
    """Guarda o mínimo da página (o Recipe do JSON-LD) e os passos guardados."""
    objeto = receita_da_pagina(pagina)
    if objeto is None:
        raise ValueError(f"{receita.url} não traz receita em JSON-LD")
    gravado: dict[str, Any] = {
        "gravado_em": hoje.isoformat(),
        "slug": receita.slug,
        "url": receita.url,
        "receita": {
            chave: objeto[chave] for chave in CHAVES_GRAVADAS if chave in objeto
        },
        "guardados": None
        if receita.guardados is None
        else [
            {"texto": p.texto, **({"secao": p.secao} if receita.com_secao else {})}
            for p in receita.guardados
        ],
    }
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / _nome_do_arquivo(receita)
    arquivo.write_text(
        json.dumps(gravado, ensure_ascii=False, indent=1) + "\n", "utf-8"
    )
    return arquivo


def ler_gravadas(origem: Path = GRAVADAS) -> tuple[list[ReceitaDoCatalogo], Leitor]:
    """As receitas gravadas e um leitor que devolve a página mínima de cada uma."""
    receitas: list[ReceitaDoCatalogo] = []
    paginas: dict[str, str] = {}
    for arquivo in sorted(origem.glob("*.json")):
        gravado = json.loads(arquivo.read_text("utf-8"))
        guardados = gravado.get("guardados")
        receitas.append(
            ReceitaDoCatalogo(
                url=gravado["url"],
                slug=gravado.get("slug", ""),
                guardados=None
                if guardados is None
                else tuple(Passo(p["texto"], p.get("secao")) for p in guardados),
                com_secao=bool(guardados) and all("secao" in p for p in guardados),
            )
        )
        paginas[gravado["url"]] = pagina_de(gravado["receita"])

    def ler(url: str) -> str:
        if url not in paginas:
            raise ValueError("a página não foi gravada")
        return paginas[url]

    return receitas, ler


def main(argumentos: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "urls", nargs="*", help="endereços de receita (sem eles, o catálogo)"
    )
    parser.add_argument(
        "--api", default=API, help="a API de onde ler o catálogo (só GET)"
    )
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument(
        "--gravar", action="store_true", help="grava o JSON-LD e o guardado"
    )
    modo.add_argument(
        "--gravadas", action="store_true", help="confere com o que foi gravado"
    )
    parser.add_argument(
        "--pasta", type=Path, default=GRAVADAS, help="onde gravar ou ler"
    )
    opcoes = parser.parse_args(argumentos)

    if opcoes.gravadas:
        receitas, ler = ler_gravadas(opcoes.pasta)
    else:
        ler = ler_da_rede
        if opcoes.urls:
            receitas = [ReceitaDoCatalogo(url=url) for url in opcoes.urls]
        else:
            try:
                receitas = catalogo_da_api(opcoes.api)
            except (urllib.error.URLError, OSError, ValueError, KeyError) as erro:
                print(f"não consegui ler o catálogo em {opcoes.api}: {erro}")
                return 1

    paginas: dict[str, str] = {}

    def lendo(url: str) -> str:
        paginas[url] = ler(url)
        return paginas[url]

    resultados = conferir_todas(receitas, lendo)
    for resultado in resultados:
        print(resultado.linha())
    conferidas = [r for r in resultados if not r.falha and not r.sem_json_ld]
    divergem = [r for r in resultados if not r.extrator_ok]
    guardados = [r for r in resultados if r.guardado]
    sem_json_ld = [r for r in resultados if r.sem_json_ld]
    origem = "páginas gravadas" if opcoes.gravadas else "páginas buscadas agora"
    print(
        f"\n{len(conferidas) - len(divergem)} de {len(conferidas)} receitas com o extrator "
        f"igual à página ({origem}); {len(guardados)} com o guardado diferente da "
        f"página; {len(sem_json_ld)} sem JSON-LD; "
        f"{len(resultados) - len(conferidas) - len(sem_json_ld)} que não vieram"
    )
    if opcoes.gravar:
        if divergem:
            print(
                "nada foi gravado: há receita que não deu para conferir ou que diverge"
            )
            return 1
        hoje = dt.datetime.now(tz=dt.UTC).date()
        for resultado in conferidas:
            gravar(
                resultado.receita, paginas[resultado.receita.url], opcoes.pasta, hoje
            )
        print(f"gravado em {opcoes.pasta}")
    return 1 if divergem else 0


if __name__ == "__main__":
    sys.exit(main())
