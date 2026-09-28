"""O analisador de português do Brasil: como a busca lê a pergunta e os trechos.

Quatro passos, na mesma ordem para o trecho e para a pergunta:

1. **caixa e acento**: "Açafrão", "acafrao" e "AÇAFRÃO" são a mesma palavra;
2. **palavras vazias**: artigo, preposição, pronome e os verbos de todo dia
   ("tem", "posso", "faço") não distinguem um trecho do outro;
3. **radical leve**: tira o plural ("feijões" e "feijão"), o infinitivo, o
   particípio ("refogar" e "refogado") e o gerúndio. É leve de propósito: um
   radical agressivo junta palavras que não têm nada a ver ("salada" e "sal",
   "farinha" e "faro"), e a parte vetorial da busca já aproxima as variações que
   o radical deixa separadas;
4. **sinônimos**, só na pergunta: quem pergunta por "muçarela" acha a
   "mussarela" da despensa. Expandir só a pergunta mantém o peso das palavras
   do corpus honesto; expandir os dois lados faria todo sinônimo parecer comum.

Os sinônimos de ingrediente vêm do casamento do motor (`mise.casamento`), que
quem monta o corpus passa pronto; este pacote não importa o motor. Os de
cozinha e de operação (geladeira e refrigerador, marmita e embalagem) estão
aqui.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

#: Palavras que não distinguem um trecho do outro. Já sem acento, como a busca lê.
VAZIAS: Final[frozenset[str]] = frozenset(
    (
        "a",
        "ao",
        "aos",
        "as",
        "o",
        "os",
        "um",
        "uma",
        "uns",
        "umas",
        "de",
        "do",
        "da",
        "dos",
        "das",
        "dum",
        "duma",
        "num",
        "numa",
        "em",
        "no",
        "na",
        "nos",
        "nas",
        "por",
        "pelo",
        "pela",
        "pelos",
        "pelas",
        "para",
        "pra",
        "pro",
        "pras",
        "pros",
        "com",
        "sem",
        "sob",
        "sobre",
        "entre",
        "ate",
        "apos",
        "e",
        "ou",
        "mas",
        "nem",
        "que",
        "se",
        "porque",
        "pois",
        "como",
        "quando",
        "onde",
        "qual",
        "quais",
        "quanto",
        "quanta",
        "quantos",
        "quantas",
        "quem",
        "cujo",
        "cuja",
        "este",
        "esta",
        "estes",
        "estas",
        "esse",
        "essa",
        "esses",
        "essas",
        "isso",
        "isto",
        "aquilo",
        "aquele",
        "aquela",
        "aqueles",
        "aquelas",
        "eu",
        "tu",
        "ele",
        "ela",
        "eles",
        "elas",
        "vos",
        "voce",
        "voces",
        "me",
        "te",
        "lhe",
        "lhes",
        "meu",
        "minha",
        "meus",
        "minhas",
        "teu",
        "tua",
        "teus",
        "tuas",
        "seu",
        "sua",
        "seus",
        "suas",
        "nosso",
        "nossa",
        "nossos",
        "nossas",
        "dele",
        "dela",
        "deles",
        "delas",
        "ja",
        "ainda",
        "tambem",
        "muito",
        "muita",
        "muitos",
        "muitas",
        "mais",
        "menos",
        "so",
        "tao",
        "entao",
        "aqui",
        "ali",
        "la",
        "ai",
        "ser",
        "sao",
        "era",
        "eram",
        "foi",
        "foram",
        "sera",
        "estar",
        "estou",
        "estava",
        "estao",
        "tem",
        "tenho",
        "ter",
        "tinha",
        "temos",
        "tenha",
        "ha",
        "havia",
        "posso",
        "pode",
        "podem",
        "poderia",
        "podia",
        "consigo",
        "consegue",
        "fazer",
        "faco",
        "faz",
        "fiz",
        "feito",
        "vou",
        "vai",
        "vamos",
        "vao",
        "dar",
        "da",
        "deu",
        "seria",
        "senhora",
        "senhor",
        "dona",
        "maria",
        "sabor",
        "hein",
        "ne",
        "oi",
        "ola",
        "sim",
        "nao",
        "algum",
        "alguma",
        "alguns",
        "algumas",
        "cada",
        "outro",
        "outra",
        "outros",
        "outras",
        "todo",
        "toda",
        "todos",
        "todas",
        "coisa",
        "coisas",
        "agora",
        "hoje",
        "depois",
        "antes",
        "mesmo",
        "mesma",
        "assim",
        "tipo",
        "favor",
        "obrigado",
        "obrigada",
        "gostaria",
        "queria",
        "quero",
        "quer",
        "sei",
        "sabe",
        "saber",
        "diga",
        "diz",
        "dizer",
        "fala",
        "falar",
        "fica",
        "ficar",
        "ficou",
        "ficam",
        "fico",
        "deve",
        "devo",
        "devem",
        "deveria",
        "precisa",
        "preciso",
        "precisam",
        "precisar",
        "acha",
        "acho",
        "achar",
        "conseguir",
        "ver",
        "vejo",
        "olhar",
        "mostra",
        "mostrar",
        "explica",
        "explicar",
        "ajuda",
        "ajudar",
        "certo",
        "certa",
        "jeito",
        "forma",
        "usar",
        "uso",
        "usa",
        "usam",
        "usei",
        "usou",
        "usando",
        "veio",
        "vem",
        "vieram",
        "sai",
        "saiu",
        "disse",
        "falei",
        "falou",
        "informei",
        "informou",
    )
)

#: Formas de verbo que o radical leve não junta sozinho ("paguei" e "pagou" não têm
#: terminação comum), ditas para o radical que o resto do verbo já tem. São os
#: verbos com que ela pergunta de dinheiro, de estoque e de preparo.
LEMAS: Final[dict[str, str]] = {
    forma: lema
    for lema, formas in {
        "pag": "pagar paguei pagou pago paga pagam pagamos pagaram pagando pagas",
        "cust": "custar custou custa custam custei custaram custando custo custos",
        "compr": "comprar comprei comprou compra compras compro compramos compraram comprado",
        "gast": "gastar gastei gastou gasta gasto gastos gastam gastamos",
        "sobr": "sobrar sobrou sobra sobras sobram sobrando",
        "rend": "render rende rendeu rendem rendimento rendimentos rendendo",
        "vend": "vender vendi vendeu vende vendo venda vendas vendem vendemos",
        "cobr": "cobrar cobro cobra cobrei cobrou cobram cobrado cobrando",
        "dur": "durar dura durou duram duracao duram",
        "guard": "guardar guardo guarda guardei guardou guardado guardada",
        "esquent": "esquentar esquento esquenta esquentei esquentou esquentado",
        "reaquec": "reaquecer reaqueco reaquece reaqueci reaquecido reaquecimento",
        "congel": "congelar congelo congela congelei congelou congelado congelada congelamento",
        "descongel": "descongelar descongelo descongela descongelei descongelado descongelamento",
        "ass": "assar asso assa assei assou assado assada assados",
        "frit": "fritar frito frita fritei fritou frita fritos fritas fritura frituras",
        "ferv": "ferver fervo ferve fervi ferveu fervendo fervura fervido",
        "cozinh": "cozinhar cozinho cozinhei cozinhou cozinhando cozinhado cozimento",
        "embal": "embalar embalo embala embalei embalagem embalagens embalado",
        "entreg": "entregar entrego entrega entregas entreguei entregou entregador",
        "conserv": "conservar conservo conserva conservacao conservado conservada",
        "refog": "refogar refogo refoga refoguei refogou refogado refogue",
        "armazen": "armazenar armazeno armazena armazenamento armazenado armazenada",
        "tempera": "temperatura temperaturas",
        "aceit": "aceitar aceitei aceitou aceito aceita aceitaram aceitando",
        "esfri": "esfriar esfrio esfria esfriei esfriou esfriado esfriada esfriando",
        "resfri": "resfriar resfrio resfria resfriei resfriou resfriado resfriamento",
    }.items()
    for forma in formas.split()
}

#: As unidades abreviadas viram palavra: "R$ 41,00/kg" é o quilo, "1 L" é o litro.
_UNIDADES: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"(?<![a-z])kg\b", re.IGNORECASE), " quilo "),
    (re.compile(r"(?<=[\d/ ])l\b"), " litro "),
    (re.compile(r"(?<=[\d/ ])L\b"), " litro "),
    (re.compile(r"(?<=\d)\s*ml\b", re.IGNORECASE), " mililitro "),
    (re.compile(r"(?<=\d)\s*g\b"), " grama "),
)

#: Palavras compostas de cozinha que o hífen separaria: "banho-maria" é uma coisa só
#: (e "maria", sozinha, é o nome dela, que a busca ignora).
_COMPOSTAS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"banho[\s-]+maria", re.IGNORECASE), "banhomaria"),
)

#: O grau de temperatura escrito com o símbolo ("180 °C", "5ºC") vira palavra.
_GRAUS: Final = re.compile(r"(?<=\d)\s*[°º]\s*c?\b|[°º]\s*c\b", re.IGNORECASE)

#: Terminações de plural, da mais longa para a mais curta, e o que fica no lugar.
_PLURAIS: Final[tuple[tuple[str, str], ...]] = (
    ("oes", "ao"),
    ("aes", "ao"),
    ("ais", "al"),
    ("eis", "el"),
    ("ois", "ol"),
    ("uis", "ul"),
    ("ns", "m"),
    ("res", "r"),
    ("zes", "z"),
    ("ses", "s"),
)

#: Terminações de verbo e de grau, tiradas depois do plural.
_TERMINACOES: Final[tuple[str, ...]] = (
    "amento",
    "imento",
    "mente",
    "ados",
    "adas",
    "idos",
    "idas",
    "ando",
    "endo",
    "indo",
    "ado",
    "ada",
    "ido",
    "ida",
    "ar",
    "er",
    "ir",
)

#: A menor palavra que o plural deixa: "sais" vira "sal", "gás" fica "gas".
_RADICAL_MINIMO: Final = 3

#: O menor radical que uma terminação de verbo deixa. Com menos, "salada" virava
#: "sal" e "comida", "com": a palavra fica inteira.
_RADICAL_DO_VERBO: Final = 4

_PALAVRA: Final = re.compile(r"[a-z0-9]+")

#: Sinônimos de cozinha e de operação, em grupos de palavras que querem dizer o mesmo.
SINONIMOS_DA_COZINHA: Final[tuple[tuple[str, ...], ...]] = (
    ("geladeira", "refrigerador", "refrigeracao"),
    ("freezer", "congelador", "congelar"),
    ("airfryer", "air fryer", "fritadeira eletrica"),
    ("microondas", "micro ondas"),
    ("marmita", "marmitex", "quentinha", "embalagem"),
    ("entrega", "delivery", "entregador"),
    ("ifood", "aplicativo", "plataforma"),
    ("taxa", "comissao"),
    ("lucro", "ganho"),
    ("validade", "vencimento"),
    ("bechamel", "molho branco"),
    ("estoque", "despensa"),
    ("orcamento", "complementos"),
    ("cardapio", "menu"),
    ("pagar", "comprar"),
    ("custar", "preço"),
)


def sem_acento(texto: str) -> str:
    """Minúscula e sem acento: "Açafrão" vira "acafrao"."""
    decomposto = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def radical(palavra: str) -> str:
    """O radical leve de uma palavra já sem acento: o plural e as terminações de verbo.

    Os verbos de `LEMAS` vão direto para o radical deles.

    >>> [radical(p) for p in ("feijoes", "refogado", "refogar", "ovos", "sais", "gas")]
    ['feijao', 'refog', 'refog', 'ovo', 'sal', 'gas']
    """
    if palavra in LEMAS:
        return LEMAS[palavra]
    if len(palavra) <= _RADICAL_MINIMO or palavra.isdigit():
        return palavra
    singular = next(
        (
            palavra[: -len(fim)] + troca
            for fim, troca in _PLURAIS
            if palavra.endswith(fim) and len(palavra) - len(fim) + len(troca) >= _RADICAL_MINIMO
        ),
        None,
    )
    if singular is not None:
        palavra = singular
    elif palavra.endswith("s") and not palavra.endswith("ss"):
        palavra = palavra[:-1]
    for fim in _TERMINACOES:
        if palavra.endswith(fim) and len(palavra) - len(fim) >= _RADICAL_DO_VERBO:
            return palavra[: -len(fim)]
    return palavra


def palavras(texto: str) -> list[str]:
    """As palavras do texto, sem acento, na ordem, com as vazias.

    "5 °C" vira "5 graus", "/kg" vira "quilo", "2 L" vira "2 litro": ela pergunta
    pelo nome da unidade, e o texto da despensa escreve a sigla.
    """
    texto = _GRAUS.sub(" graus ", texto)
    for sigla, nome in (*_UNIDADES, *_COMPOSTAS):
        texto = sigla.sub(nome, texto)
    return _PALAVRA.findall(sem_acento(texto))


@dataclass(frozen=True, slots=True)
class GrupoDaConsulta:
    """Uma palavra da pergunta e o que também vale por ela (os radicais dos sinônimos)."""

    original: str
    radicais: frozenset[str]


class Analisador:
    """Lê o texto como a busca lê: radicais sem acento, sem vazias, com sinônimos na pergunta."""

    def __init__(self, sinonimos: Iterable[Sequence[str]] = SINONIMOS_DA_COZINHA) -> None:
        self._sinonimos: dict[tuple[str, ...], set[tuple[str, ...]]] = {}
        for grupo in sinonimos:
            formas = {self._forma(frase) for frase in grupo}
            formas.discard(())
            for forma in formas:
                self._sinonimos.setdefault(forma, set()).update(formas - {forma})
        self._maior = max((len(f) for f in self._sinonimos), default=1)

    def _forma(self, frase: str) -> tuple[str, ...]:
        return tuple(radical(p) for p in palavras(frase) if p not in VAZIAS)

    def termos(self, texto: str) -> list[str]:
        """Os radicais que o texto põe no índice, na ordem, com repetição."""
        return [
            radical(p) for p in palavras(texto) if p not in VAZIAS and len(p) > 1 and p.strip("0")
        ]

    def grupos(self, pergunta: str) -> list[GrupoDaConsulta]:
        """Cada palavra da pergunta com os radicais que valem por ela.

        Um sinônimo de duas palavras ("air fryer", "molho branco") vale pela
        sequência inteira: a expansão entra no grupo da primeira palavra dela.
        """
        radicais = self.termos(pergunta)
        grupos = [GrupoDaConsulta(r, frozenset({r})) for r in radicais]
        for inicio in range(len(radicais)):
            for tamanho in range(min(self._maior, len(radicais) - inicio), 0, -1):
                forma = tuple(radicais[inicio : inicio + tamanho])
                equivalentes = self._sinonimos.get(forma)
                if not equivalentes:
                    continue
                extra = {r for e in equivalentes for r in e}
                atual = grupos[inicio]
                grupos[inicio] = GrupoDaConsulta(atual.original, atual.radicais | extra)
                break
        return _sem_repeticao(grupos)

    def consulta(self, pergunta: str) -> list[str]:
        """Os radicais que a pergunta procura, com os sinônimos, sem repetir."""
        vistos: dict[str, None] = {}
        for grupo in self.grupos(pergunta):
            for r in sorted(grupo.radicais):
                vistos.setdefault(r)
        return list(vistos)


def _sem_repeticao(grupos: Sequence[GrupoDaConsulta]) -> list[GrupoDaConsulta]:
    """A mesma palavra duas vezes na pergunta conta uma vez só na cobertura."""
    unicos: dict[str, GrupoDaConsulta] = {}
    for grupo in grupos:
        anterior = unicos.get(grupo.original)
        radicais = grupo.radicais | (anterior.radicais if anterior else frozenset())
        unicos[grupo.original] = GrupoDaConsulta(grupo.original, radicais)
    return list(unicos.values())


def sinonimos_do_casamento(apelidos: Mapping[str, str]) -> list[tuple[str, str]]:
    """Os pares de sinônimo que o casamento de ingrediente sabe, sem o que já casa sozinho.

    O casamento liga apelido e item ("filé de frango" ao "Peito de frango"). Para
    a busca, só interessa a parte que não aparece dos dois lados: "filé" e
    "peito". "Frango" já está no nome do item, e expandir "farinha" para "trigo"
    faria a pergunta sobre farinha de mandioca achar a de trigo.
    """
    pares: list[tuple[str, str]] = []
    for apelido, nome in apelidos.items():
        de_um = [p for p in palavras(apelido) if p not in VAZIAS]
        do_outro = [p for p in palavras(nome) if p not in VAZIAS]
        so_no_apelido = [p for p in de_um if radical(p) not in {radical(q) for q in do_outro}]
        so_no_nome = [p for p in do_outro if radical(p) not in {radical(q) for q in de_um}]
        if so_no_apelido and so_no_nome:
            pares.append((" ".join(so_no_apelido), " ".join(so_no_nome)))
    return sorted(set(pares))


__all__ = [
    "LEMAS",
    "SINONIMOS_DA_COZINHA",
    "VAZIAS",
    "Analisador",
    "GrupoDaConsulta",
    "palavras",
    "radical",
    "sem_acento",
    "sinonimos_do_casamento",
]
