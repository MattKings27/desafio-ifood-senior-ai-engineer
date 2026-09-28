"""Casamento entre o ingrediente da receita e o item da despensa.

A receita diz "carne moída". A planilha diz "Carne moída (patinho)". A receita
diz "parmesão"; a planilha, "Queijo parmesão ralado". São o mesmo ingrediente,
e nenhuma comparação de string exata resolve.

O caminho é uma **cascata com confiança decrescente**, e o ponto de projeto é
onde ela para. Abaixo do limiar, o resultado não é o melhor palpite: é
`None`, e vira pergunta. Um casamento errado aqui não dá erro em lugar nenhum;
ele simplesmente produz um CMV plausível e errado, que é o pior tipo de defeito
num sistema que recomenda preço.

**As equivalências são escritas à mão** (`SINONIMOS`), item por item dos 37 da
planilha: cada nome que uma receita brasileira usa para aquele produto, e só
para aquele produto. "Alcatra" é o miolo de alcatra dela; "filés de frango"
são o peito de frango. O que não está ali e só se parece fica de fora.

**Numa receita de frango, "peito" é o peito de frango** (`contexto`): "1 peito
cortado em 4 filés", numa receita chamada "Frango com alcaparras", não é outra
carne. Fora de uma receita de frango, "peito" não casa com nada sozinho.

**A marca não muda o ingrediente** (`sem_marca`): "Queijo Parmesão TIROLEZ
ralado" é o queijo parmesão ralado dela, e "Coração da Alcatra bovina Perdigão
Montana" é o miolo de alcatra. A marca registrada (®, ™), a palavra toda em
maiúscula no meio do nome e as marcas conhecidas saem antes de comparar; a
marca que virou nome de produto ("leite Moça", "leite Ninho", "Maizena") fica.

**A forma do produto decide** (`mesma_forma`): farinha, fubá, polvilho,
extrato, caldo, molho, creme, leite, óleo, suco e o que é em pó são outro
produto que o ingrediente cru, e vice-versa: "1 kg de mandioca cozida" não é a
farinha de mandioca dela, é compra.

**O parecido nunca vira "tem" sozinho.** Quando o nome do item dela contém o
que a receita pede ("canela" e "Canela em pó", "mandioca" e "Farinha de
mandioca"), o casamento é `PARCIAL`: não é confiável, e a conferência decide
pelo lado seguro, que é não ser o item dela (a linha vira compra). A decisão é
dita a ela ("considerei que mandioca não é a sua farinha de mandioca") e ela
corrige quando quiser: a resposta fica guardada na linha da receita
(`IngredienteReceita.item_da_despensa`) e vale daquela receita em diante.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from enum import IntEnum
from functools import lru_cache
from typing import TYPE_CHECKING, Final

from rapidfuzz import fuzz, process

if TYPE_CHECKING:
    from mise.despensa import Despensa, Ingrediente


class Estrategia(IntEnum):
    """Como o casamento foi obtido. Maior é mais confiável."""

    CONFIRMADO = 7
    """Ela disse que a linha da receita é este item dela (`item_da_despensa`)."""
    EXATO = 6
    NORMALIZADO = 5
    SINONIMO = 4
    NUCLEO = 3
    PARCIAL = 2
    """O nome do item dela contém o que a receita pede: pergunta, nunca "tem" sozinho."""
    APROXIMADO = 1
    NENHUM = 0


#: Score mínimo (0-100) para aceitar um casamento aproximado.
#: Calibrado para aceitar "carne moida" ~ "carne moida (patinho)" e recusar
#: "farinha de rosca" ~ "farinha de trigo", que é o falso-positivo caro.
LIMIAR_APROXIMADO: Final = 88

#: Sinônimos e nomes populares -> nome na despensa da Dona Maria.
#:
#: As equivalências dos 37 itens da planilha, escritas à mão: cada nome que uma
#: receita usa para aquele produto (o corte, a marca de prateleira, o apelido),
#: e nenhum que seja outro produto parecido. "Coração da alcatra" é o miolo da
#: alcatra, o mesmo corte com outro nome; "farinha de rosca", "leite
#: condensado", "sal grosso", "açúcar mascavo", "canela em pau" e "couve-flor"
#: são outros produtos e ficam de fora de propósito. As chaves são comparadas
#: sem acento e sem pontuação, e também pelo núcleo (sem o corte e o preparo:
#: "bifes de alcatra" é "alcatra").
SINONIMOS: Final[dict[str, str]] = {
    # Arroz branco tipo 1
    "arroz": "Arroz branco tipo 1",
    "arroz branco": "Arroz branco tipo 1",
    "arroz agulhinha": "Arroz branco tipo 1",
    "arroz tipo 1": "Arroz branco tipo 1",
    # Feijão carioquinha e feijão preto
    "feijao": "Feijão carioquinha",
    "feijao carioca": "Feijão carioquinha",
    "feijao carioquinha": "Feijão carioquinha",
    "feijao preto": "Feijão preto",
    # Peito de frango: o peito, o filé do peito e o sassami são a mesma peça.
    "frango": "Peito de frango",
    "file de frango": "Peito de frango",
    "peito de frango": "Peito de frango",
    "file de peito de frango": "Peito de frango",
    "peito de frango sem osso": "Peito de frango",
    "sassami": "Peito de frango",
    # Carne moída (patinho)
    "patinho": "Carne moída (patinho)",
    "carne moida": "Carne moída (patinho)",
    "patinho moido": "Carne moída (patinho)",
    "carne moida de patinho": "Carne moída (patinho)",
    # Carne de panela (acém)
    "acem": "Carne de panela (acém)",
    "carne de panela": "Carne de panela (acém)",
    # Miolo de alcatra: "coração da alcatra" é o mesmo corte, com outro nome.
    "alcatra": "Miolo de alcatra",
    "miolo de alcatra": "Miolo de alcatra",
    "coracao da alcatra": "Miolo de alcatra",
    "coracao de alcatra": "Miolo de alcatra",
    # Bacon: o couro é a pele da mesma peça.
    "bacon": "Bacon",
    "couro do bacon": "Bacon",
    "couro de bacon": "Bacon",
    # Ovos
    "ovo": "Ovos",
    "ovos": "Ovos",
    "ovo inteiro": "Ovos",
    # Farinha de trigo e farinha de mandioca. A "farinha amarela" (a farinha
    # d'água) é farinha de mandioca, como a de mesa; a de milho diz que é de milho.
    "farinha": "Farinha de trigo",
    "trigo": "Farinha de trigo",
    "farinha de trigo": "Farinha de trigo",
    "farinha de trigo tipo 1": "Farinha de trigo",
    "farinha de mandioca": "Farinha de mandioca",
    "farinha de mandioca torrada": "Farinha de mandioca",
    "farinha de mandioca crua": "Farinha de mandioca",
    "farinha de mesa": "Farinha de mandioca",
    "farinha amarela": "Farinha de mandioca",
    "farinha d agua": "Farinha de mandioca",
    # Macarrão espaguete
    "macarrao": "Macarrão espaguete",
    "espaguete": "Macarrão espaguete",
    "spaghetti": "Macarrão espaguete",
    "macarrao espaguete": "Macarrão espaguete",
    "macarrao tipo espaguete": "Macarrão espaguete",
    # Polenta (fubá)
    "fuba": "Polenta (fubá)",
    "polenta": "Polenta (fubá)",
    "fuba mimoso": "Polenta (fubá)",
    # Batata
    "batata": "Batata",
    "batata inglesa": "Batata",
    # Queijo mussarela e queijo parmesão ralado
    "mussarela": "Queijo mussarela",
    "muçarela": "Queijo mussarela",
    "mucarela": "Queijo mussarela",
    "mozarela": "Queijo mussarela",
    "mozzarella": "Queijo mussarela",
    "queijo mozarela": "Queijo mussarela",
    "queijo mucarela": "Queijo mussarela",
    "queijo mozzarella": "Queijo mussarela",
    "queijo": "Queijo mussarela",
    "parmesao": "Queijo parmesão ralado",
    "queijo parmesao": "Queijo parmesão ralado",
    # Tomate, cebola e alho
    "tomate": "Tomate",
    "tomate italiano": "Tomate",
    "cebola": "Cebola",
    "cebola branca": "Cebola",
    "alho": "Alho",
    # Óleo de soja
    "oleo": "Óleo de soja",
    "oleo de soja": "Óleo de soja",
    "oleo vegetal": "Óleo de soja",
    # Manteiga
    "manteiga": "Manteiga",
    "manteiga sem sal": "Manteiga",
    "manteiga com sal": "Manteiga",
    # Sal e açúcar: o refinado; o grosso e o mascavo são outros produtos.
    "sal": "Sal",
    "sal refinado": "Sal",
    "sal fino": "Sal",
    "acucar": "Açúcar",
    "acucar refinado": "Açúcar",
    "acucar cristal": "Açúcar",
    # Leite integral: o leite de vaca; condensado, de coco e em pó são outros.
    "leite": "Leite integral",
    "leite integral": "Leite integral",
    "leite de vaca": "Leite integral",
    # Couve: a couve-manteiga; couve-flor é outra coisa.
    "couve": "Couve",
    "couve manteiga": "Couve",
    # Salsinha (cheiro-verde): o cheiro-verde é salsinha com cebolinha.
    "cheiro verde": "Salsinha (cheiro-verde)",
    "salsinha": "Salsinha (cheiro-verde)",
    "salsa": "Salsinha (cheiro-verde)",
    "cebolinha": "Salsinha (cheiro-verde)",
    # Caldo de carne (tempero)
    "caldo de carne": "Caldo de carne (tempero)",
    "caldo de carne em tablete": "Caldo de carne (tempero)",
    "tablete de caldo de carne": "Caldo de carne (tempero)",
    # Açafrão em pó (cúrcuma)
    "curcuma": "Açafrão em pó (cúrcuma)",
    "acafrao": "Açafrão em pó (cúrcuma)",
    "acafrao da terra": "Açafrão em pó (cúrcuma)",
    "acafrao em po": "Açafrão em pó (cúrcuma)",
    # Alcaparras
    "alcaparra": "Alcaparras",
    "alcaparras": "Alcaparras",
    # Amêndoa fatiada
    "amendoa": "Amêndoa fatiada",
    "amendoas": "Amêndoa fatiada",
    "amendoa laminada": "Amêndoa fatiada",
    # Chantilly
    "chantilly": "Chantilly",
    "chantili": "Chantilly",
    # Leite ninho em pó
    "leite ninho": "Leite ninho em pó",
    "leite em po": "Leite ninho em pó",
    # Cobertura de chocolate
    "chocolate": "Cobertura de chocolate",
    "cobertura de chocolate": "Cobertura de chocolate",
    "chocolate para cobertura": "Cobertura de chocolate",
    # Azeite de oliva extra virgem
    "azeite": "Azeite de oliva extra virgem",
    "azeite de oliva": "Azeite de oliva extra virgem",
    "azeite extra virgem": "Azeite de oliva extra virgem",
    # Aceto balsâmico
    "aceto balsamico": "Aceto balsâmico",
    "vinagre balsamico": "Aceto balsâmico",
    "balsamico": "Aceto balsâmico",
    # Canela em pó: "canela" sozinha pode ser em pau, e vira pergunta.
    "canela em po": "Canela em pó",
    # Adoçante líquido
    "adocante": "Adoçante líquido",
    "adocante liquido": "Adoçante líquido",
}

#: Os sinônimos que são uma decisão, e não só outro nome: a conferência diz a
#: decisão a ela, que corrige se não for. Pelo núcleo do nome da receita.
DECISOES_DO_SINONIMO: Final[dict[str, str]] = {
    "couro bacon": "o couro é a pele da mesma peça",
    "coracao alcatra": "é o mesmo corte, com outro nome",
}


def motivo_do_sinonimo(texto: str) -> str | None:
    """Por que a linha é o item dela, quando o sinônimo é uma decisão ("couro do bacon")."""
    return DECISOES_DO_SINONIMO.get(_nucleo(texto))


#: Numa receita de frango, o corte sozinho é o peito de frango dela: "1 peito
#: cortado em 4 filés" em "Frango com alcaparras". Só com o frango no nome da
#: receita; em outra receita, "peito" não diz de quê.
CORTES_DO_FRANGO: Final[frozenset[str]] = frozenset({"peito", "file", "filezinho", "sassami"})
_DO_FRANGO: Final = re.compile(r"\b(?:frango|galinha)\b")

#: Palavras que não ajudam a identificar o ingrediente.
_RUIDO: Final[frozenset[str]] = frozenset(
    {
        "de",
        "da",
        "do",
        "das",
        "dos",
        "e",
        "ou",
        "a",
        "o",
        "as",
        "os",
        "em",
        "com",
        "sem",
        "para",
        "ao",
        "à",
        "picado",
        "picada",
        "ralado",
        "ralada",
        "fatiado",
        "fatiada",
        "cortado",
        "cortada",
        "cubos",
        "tiras",
        "rodelas",
        "grande",
        "pequeno",
        "pequena",
        "medio",
        "media",
        "fresco",
        "fresca",
        "seco",
        "seca",
        "gosto",
        "bem",
        "cru",
        "crua",
        "grosso",
        "grossa",
        "fino",
        "fina",
        "limpo",
        "limpa",
        "inteiro",
        "inteira",
        # "coração da alcatra bovina": a alcatra é de boi, e a palavra não muda o corte.
        "bovino",
        "bovina",
        # "feijão da sua preferência": a receita aceita qualquer um, e o dela serve.
        "sua",
        "seu",
        "preferencia",
        "escolha",
    }
)

_PARENTESES = re.compile(r"\([^)]*\)")
_NAO_ALFANUM = re.compile(r"[^a-z0-9\s]")
_ESPACOS = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class Casamento:
    """O resultado de procurar um ingrediente da receita na despensa."""

    texto_receita: str
    item: Ingrediente | None
    estrategia: Estrategia
    score: float
    """0 a 100. Para casamentos exatos é 100."""

    @property
    def encontrado(self) -> bool:
        return self.item is not None

    @property
    def confiavel(self) -> bool:
        """Confiável o bastante para custear sem perguntar."""
        return self.item is not None and self.estrategia >= Estrategia.NUCLEO

    def explicacao(self) -> str:
        if self.item is None:
            return f"{self.texto_receita!r} não foi encontrado na despensa"
        como = {
            Estrategia.EXATO: "nome idêntico",
            Estrategia.NORMALIZADO: "mesmo nome, ignorando acento e pontuação",
            Estrategia.SINONIMO: "sinônimo conhecido",
            Estrategia.NUCLEO: "mesmo núcleo do nome",
            Estrategia.CONFIRMADO: "a senhora confirmou",
            Estrategia.PARCIAL: "só parecido: fica como compra, e a senhora corrige se for",
            Estrategia.APROXIMADO: f"semelhança de {self.score:.0f}%",
        }[self.estrategia]
        return f"{self.texto_receita!r} → {self.item.nome!r} ({como})"


def casar(texto: str, despensa: Despensa, *, contexto: str = "") -> Casamento:  # noqa: PLR0911
    """Procura `texto` na despensa, em cascata de confiança decrescente.

    Os `return` são a própria estrutura do algoritmo: cada estágio da cascata
    devolve assim que acerta. Transformar isso em `if` aninhado ou num laço de
    estratégias esconderia a ordem de precedência, que é justamente o que
    precisa ficar óbvio para quem for ajustar o limiar depois.

    `contexto` é o nome da receita: numa receita de frango, "peito" é o peito
    de frango dela (`CORTES_DO_FRANGO`).

    >>> # "carne moída" encontra "Carne moída (patinho)"
    >>> # "farinha de rosca" NÃO encontra "Farinha de trigo", e é isso que importa
    """
    original = texto.strip()
    if not original:
        return Casamento(texto, None, Estrategia.NENHUM, 0.0)
    # A marca não muda o ingrediente: "Queijo Parmesão TIROLEZ ralado" é o parmesão dela.
    bruto = sem_marca(original)

    # 0. "óleo para fritura" e "azeite ou manteiga": a linha diz mais que o ingrediente.
    if (por_partes := _casar_por_partes(bruto, despensa, contexto)) is not None:
        return replace(por_partes, texto_receita=original)

    # 1. nome idêntico
    if bruto in despensa:
        return Casamento(original, despensa[bruto], Estrategia.EXATO, 100.0)

    alvo = _normalizar(bruto)
    indice = {_normalizar(nome): nome for nome in despensa.nomes}

    # 2. mesmo nome sem acento/pontuação
    if alvo in indice:
        return Casamento(original, despensa[indice[alvo]], Estrategia.NORMALIZADO, 100.0)

    # 3. sinônimo conhecido, escrito à mão: vale mesmo quando a forma parece outra
    #    ("açafrão" é o açafrão em pó dela).
    if (canonico := SINONIMOS.get(alvo)) and canonico in despensa:
        return Casamento(original, despensa[canonico], Estrategia.SINONIMO, 95.0)

    # 4. mesmo núcleo, ignorando parênteses e palavras de ruído; a forma do
    #    produto tem de ser a mesma, senão o item dela é só um parecido.
    nucleo_alvo = _nucleo(bruto)
    if nucleo_alvo:
        for nome in despensa.nomes:
            if _nucleo(nome) == nucleo_alvo:
                return _pela_forma(original, bruto, despensa[nome], Estrategia.NUCLEO, 90.0)
        # sinônimo pelo núcleo ("filé de frango em tiras" -> "frango")
        if (canonico := _SINONIMOS_POR_NUCLEO.get(nucleo_alvo)) and canonico in despensa:
            return _pela_forma(original, bruto, despensa[canonico], Estrategia.SINONIMO, 92.0)

    # 4b. numa receita de frango, o corte sozinho é o peito de frango
    if _corte_do_frango(bruto, contexto) and PEITO_DE_FRANGO in despensa:
        return Casamento(original, despensa[PEITO_DE_FRANGO], Estrategia.SINONIMO, 90.0)

    # 4c. o nome do item dela contém o que a receita pede: parecido, nunca "tem"
    if (parcial := _parcial(nucleo_alvo, despensa)) is not None:
        return Casamento(original, despensa[parcial], Estrategia.PARCIAL, 85.0)

    # 5. semelhança: o último recurso, e o mais perigoso
    candidatos = list(indice)
    melhor = process.extractOne(alvo, candidatos, scorer=fuzz.token_set_ratio)
    if melhor and melhor[1] >= LIMIAR_APROXIMADO:
        return Casamento(original, despensa[indice[melhor[0]]], Estrategia.APROXIMADO, melhor[1])

    return Casamento(original, None, Estrategia.NENHUM, melhor[1] if melhor else 0.0)


def _pela_forma(
    original: str, bruto: str, item: Ingrediente, estrategia: Estrategia, score: float
) -> Casamento:
    """O casamento pelo núcleo, rebaixado a parecido quando a forma do produto é outra."""
    if forma_diferente(bruto, item.nome) is not None:
        return Casamento(original, item, Estrategia.PARCIAL, 85.0)
    return Casamento(original, item, estrategia, score)


def _casar_por_partes(bruto: str, despensa: Despensa, contexto: str) -> Casamento | None:
    """A linha que diz mais que o ingrediente: casa a parte que é o ingrediente, e a linha fica.

    "Óleo para fritura", "manteiga para untar": a finalidade diz para que o
    ingrediente serve, não o que se compra. "Azeite ou manteiga": a receita
    aceita qualquer um, e vale o que ela tem. `None` quando a linha é só o nome.
    """
    if (sem_finalidade := sem_a_finalidade(bruto)) != bruto:
        return replace(casar(sem_finalidade, despensa, contexto=contexto), texto_receita=bruto)
    if len(alternativas := _ALTERNATIVAS.split(bruto)) > 1:
        tentativas = [casar(a, despensa, contexto=contexto) for a in alternativas if a.strip()]
        escolhida = max(tentativas, key=lambda c: (c.estrategia, c.score))
        return replace(escolhida, texto_receita=bruto)
    return None


def casar_todos(textos: list[str], despensa: Despensa) -> list[Casamento]:
    return [casar(t, despensa) for t in textos]


def casar_confirmado(texto: str, item_da_despensa: str, despensa: Despensa) -> Casamento:
    """O casamento que ela decidiu: a linha é o item que ela disse, ou nenhum ("")."""
    if item_da_despensa and item_da_despensa in despensa:
        return Casamento(texto, despensa[item_da_despensa], Estrategia.CONFIRMADO, 100.0)
    return Casamento(texto, None, Estrategia.NENHUM, 0.0)


#: O item da despensa que o corte sozinho, numa receita de frango, quer dizer.
PEITO_DE_FRANGO: Final = "Peito de frango"

#: "azeite ou manteiga", "óleo ou manteiga": alternativas que a receita aceita.
_ALTERNATIVAS: Final = re.compile(r"\s+ou\s+", re.IGNORECASE)

#: Para que a receita usa o ingrediente: fritar, untar a forma, polvilhar,
#: pincelar, servir, decorar. Não muda o produto que se compra, e grudada no
#: nome deixava "óleo para fritura" sem casar com o óleo de soja dela, e ele
#: entrava na lista de compras. O que vem depois ("untar a assadeira") sai
#: junto. O que diz qual produto é ("tempero para aves", "chocolate para
#: cobertura", "farinha para quibe") não é finalidade e fica no nome.
FINALIDADES: Final[tuple[str, ...]] = (
    "fritura",
    "fritar",
    "untar",
    "polvilhar",
    "pincelar",
    "servir",
    "decorar",
    "empanar",
    "refogar",
    "finalizar",
    "regar",
)
_FINALIDADE: Final = re.compile(
    r"[\s,]+(?:para|pra)\s+(?:a\s+|o\s+)?(?:" + "|".join(FINALIDADES) + r")\b.*$",
    re.IGNORECASE,
)


def sem_a_finalidade(nome: str) -> str:
    """ "óleo para fritura" vira "óleo": o nome sem dizer para que serve."""
    return _FINALIDADE.sub("", nome).strip() or nome.strip()


#: Quantas palavras um nome precisa ter para, contido no da receita, virar pergunta.
_PALAVRAS_DO_ESPECIFICO: Final = 2


def _corte_do_frango(texto: str, contexto: str) -> bool:
    """ "peito", "filés", "1 peito cortado em 4 filés", numa receita com frango no nome."""
    if not _DO_FRANGO.search(_normalizar(contexto)):
        return False
    palavras = {_singular(p) for p in _normalizar(_PARENTESES.sub(" ", texto)).split()}
    significativas = {p for p in palavras if not p.isdigit() and p not in _RUIDO_E_PREPARO}
    return bool(significativas) and significativas <= CORTES_DO_FRANGO


def _parcial(nucleo_alvo: str, despensa: Despensa) -> str | None:
    """O único item da despensa cujo nome contém tudo o que a receita pede, e mais.

    "canela" está em "Canela em pó"; "caldo" em "Caldo de carne (tempero)". Com
    dois itens assim ("carne" está na moída e na de panela), não há um a
    perguntar, e fica sem casamento. Nunca é confiável: vira pergunta a ela.
    """
    pedidas = set(nucleo_alvo.split())
    if not pedidas:
        return None
    achados = {nome for nome in despensa.nomes if pedidas < set(_nucleo(nome).split())}
    # O contrário também pergunta, quando o que se reconhece é específico (duas
    # palavras ou mais): "coração da alcatra bovina Perdigão" contém "coração
    # da alcatra". Uma palavra só ("leite" em "leite condensado") não basta.
    achados |= {
        destino
        for chave, destino in _SINONIMOS_POR_NUCLEO.items()
        if len(chave.split()) >= _PALAVRAS_DO_ESPECIFICO
        and set(chave.split()) < pedidas
        and destino in despensa
    }
    return next(iter(achados)) if len(achados) == 1 else None


@lru_cache(maxsize=16384)
def _normalizar(texto: str) -> str:
    """Minúsculas, sem acento, sem pontuação, espaços colapsados."""
    decomposto = unicodedata.normalize("NFD", texto.lower())
    sem_acento = "".join(c for c in decomposto if unicodedata.category(c) != "Mn")
    return _ESPACOS.sub(" ", _NAO_ALFANUM.sub(" ", sem_acento)).strip()


@lru_cache(maxsize=16384)
def _nucleo(texto: str) -> str:
    """O nome sem parênteses, sem modo de preparo e no singular.

    "Carne moída (patinho)" e "carne moida picada" viram ambos "carne moida";
    "2 cebolas picadas" e "Cebola" viram "cebola"; "dentes de alho amassados"
    vira "alho". Quem escreve receita descreve o corte e o preparo; a despensa
    guarda o produto. Sem isso, ela ouviria que precisa comprar a cebola que
    já tem em casa. A finalidade também sai: "óleo para fritura" vira "oleo".
    """
    sem_parenteses = _PARENTESES.sub(" ", sem_a_finalidade(sem_marca(texto)))
    normalizado = _SEM_ALGO.sub(" ", _normalizar(sem_parenteses))
    palavras = (_DIMINUTIVOS.get(p, p) for p in (_singular(p) for p in normalizado.split()))
    return " ".join(p for p in palavras if p not in _DESCARTAVEL and not p.isdigit())


#: O diminutivo que é o mesmo produto: "4 linguicinhas defumadas" são linguiças.
#: A lista é fechada: "cebolinha" não é cebola, nem "farinha" é fara.
_DIMINUTIVOS: Final[dict[str, str]] = {"linguicinha": "linguica"}


# --------------------------------------------------------------------------- #
# A marca não muda o ingrediente                                               #
# --------------------------------------------------------------------------- #

#: Marcas que aparecem nas receitas de site e não dizem o que é o produto. Sai
#: só a palavra da marca: "Coração da Alcatra bovina Perdigão Montana" é o
#: coração da alcatra. Escritas sem acento e em minúscula.
MARCAS: Final[frozenset[str]] = frozenset(
    {
        "perdigao",
        "montana",
        "sadia",
        "seara",
        "aurora",
        "friboi",
        "swift",
        "tirolez",
        "quata",
        "itambe",
        "piracanjuba",
        "italac",
        "elege",
        "vigor",
        "batavo",
        "nestle",
        "maggi",
        "knorr",
        "kitano",
        "yoki",
        "qualy",
        "doriana",
        "camil",
        "hellmann s",
        "hellmanns",
        "heinz",
        "quero",
        "elefante",
        "pomarola",
        "fugini",
        "predilecta",
        "liza",
        "soya",
        "gallo",
        "andorinha",
        "arisco",
        "sakura",
        "pullman",
        "wickbold",
        "bauducco",
        "garoto",
        "lacta",
        "royal",
        "fleischmann",
        "oetker",
        "mococa",
        "siamar",
        "copra",
        "sococo",
        "ducoco",
        "coqueiro",
    }
)

#: A marca que virou nome do produto: fica, porque tirar mudaria o que se compra
#: ("leite Moça" sem a marca seria o leite dela, e é leite condensado).
MARCAS_QUE_SAO_O_PRODUTO: Final[frozenset[str]] = frozenset(
    {
        "moca",
        "ninho",
        "maizena",
        "nescau",
        "catupiry",
        "sazon",
        "toddy",
        "neston",
        "mucilon",
        "danoninho",
        "polenguinho",
    }
)

#: Siglas que dizem o tipo do produto, e não a marca: "leite UHT".
_SIGLAS_DO_PRODUTO: Final[frozenset[str]] = frozenset({"uht", "sem", "com", "tipo"})

_REGISTRADA: Final = re.compile(r"[®™©]")


@lru_cache(maxsize=16384)
def _chave_da_palavra(palavra: str) -> str:
    return _normalizar(_REGISTRADA.sub("", palavra))


@lru_cache(maxsize=16384)
def sem_marca(texto: str) -> str:
    """O nome sem a marca: a registrada (®, ™), a palavra toda em maiúscula e as conhecidas.

    "Queijo Parmesão TIROLEZ ralado" vira "Queijo Parmesão ralado"; "MAGGI® Caldo
    Galinha", "Caldo Galinha"; "stick de MAGGI® MEU SEGREDO 7 Vegetais", "stick de
    7 Vegetais". A marca que é o próprio produto (`MARCAS_QUE_SAO_O_PRODUTO`) fica.
    Um nome que é só marca volta como veio: sem ele não sobra ingrediente.
    """
    palavras = texto.split()
    tem_minuscula = any(c.islower() for c in texto)
    saem: set[int] = set()
    depois_da_registrada = False
    for posicao, palavra in enumerate(palavras):
        chave = _chave_da_palavra(palavra)
        letras = _REGISTRADA.sub("", palavra).strip(",.;:()")
        maiuscula = len(letras) >= 3 and letras.isupper() and letras.isalpha()  # noqa: PLR2004
        if chave in MARCAS_QUE_SAO_O_PRODUTO:
            depois_da_registrada = False
            continue
        registrada = bool(_REGISTRADA.search(palavra))
        if (
            registrada
            or chave in MARCAS
            or (maiuscula and tem_minuscula and chave not in _SIGLAS_DO_PRODUTO)
            or (depois_da_registrada and maiuscula)
        ):
            saem.add(posicao)
            depois_da_registrada = registrada or (depois_da_registrada and maiuscula)
            continue
        depois_da_registrada = False
    # "Hellmann's" são duas chaves normalizadas ("hellmann s"): confere o par também.
    for posicao in range(len(palavras) - 1):
        par = f"{_chave_da_palavra(palavras[posicao])} {_chave_da_palavra(palavras[posicao + 1])}"
        if par in MARCAS:
            saem |= {posicao, posicao + 1}
    restam = [p for posicao, p in enumerate(palavras) if posicao not in saem]
    sobra = " ".join(restam).strip()
    if not _normalizar(sobra) or not any(c.isalpha() for c in _normalizar(sobra)):
        return texto.strip()
    return sobra


# --------------------------------------------------------------------------- #
# A forma do produto                                                           #
# --------------------------------------------------------------------------- #

#: As formas processadas que são outro produto que o ingrediente cru: a farinha
#: de mandioca não é a mandioca, o extrato de tomate não é o tomate, a canela em
#: pó não é a canela que a receita não diz como é.
FORMAS: Final[frozenset[str]] = frozenset(
    {
        "farinha",
        "fuba",
        "polvilho",
        "extrato",
        "caldo",
        "molho",
        "creme",
        "leite",
        "oleo",
        "suco",
        "po",
        "polpa",
        "geleia",
        "xarope",
        "essencia",
        "farofa",
    }
)


def _formas(nome: str) -> frozenset[str]:
    return frozenset(p for p in _normalizar(sem_marca(nome)).split() if p in FORMAS)


def forma_diferente(pedido: str, item: str) -> str | None:
    """A forma que separa o que a receita pede do item dela ("farinha"), ou `None` se é a mesma.

    >>> forma_diferente("mandioca", "Farinha de mandioca")
    'farinha'
    """
    de_um, do_outro = _formas(pedido), _formas(item)
    if de_um == do_outro:
        return None
    return sorted(de_um ^ do_outro)[0]


def mesma_forma(pedido: str, item: str) -> bool:
    """O que a receita pede e o item dela são o mesmo produto na mesma forma (cru, farinha, pó)?"""
    return forma_diferente(pedido, item) is None


#: "sem pele", "sem osso", "sem semente": diz o que tirar, não o que é.
_SEM_ALGO: Final = re.compile(r"\bsem [a-z]+")

#: Palavras de medida e de corte que escapam para o nome: "dentes de alho",
#: "folhas de couve", "bifes de alcatra", "filés de frango", "postas de peixe",
#: "cebola cortada em quadrados".
_MEDIDA_NO_NOME: Final[frozenset[str]] = frozenset(
    {
        "dente",
        "folha",
        "ramo",
        "talo",
        "fatia",
        "pedaco",
        "punhado",
        "maco",
        "bife",
        "file",
        "posta",
        "quadrado",
        "cubinho",
        "pedacinho",
        "lamina",
        "gomo",
    }
)

#: Modos de preparo além dos já listados no ruído.
_PREPARO: Final[frozenset[str]] = frozenset(
    {
        "amassado",
        "desfiado",
        "cozido",
        "descascado",
        "lavado",
        "escorrido",
        "batido",
        "derretido",
        "peneirado",
        "triturado",
        "temperado",
        "congelado",
        "gelado",
        "morno",
        "quente",
        "maduro",
        "picadinho",
        "fatia",
        "ralo",
        "pre",
        "espremido",
    }
)


def _singular(palavra: str) -> str:
    """Singular simples do português, bom o bastante para nome de ingrediente.

    Também traz particípio para o masculino ("picadas" -> "picado"), que é
    como o ruído está listado. Palavra curta fica como está: "gás", "mês".
    """
    if len(palavra) <= 3:  # noqa: PLR2004
        return palavra
    for fim, troca in (("oes", "ao"), ("aes", "ao"), ("ais", "al"), ("eis", "el"), ("ns", "m")):
        if palavra.endswith(fim):
            return palavra[: -len(fim)] + troca
    if palavra.endswith("s") and palavra[-2] in "aeiou":
        palavra = palavra[:-1]
    if palavra.endswith("ada") or palavra.endswith("ida"):
        palavra = palavra[:-1] + "o"
    return palavra


#: Tudo que não identifica o ingrediente, já no singular, que é como as
#: palavras chegam depois de `_singular`.
_DESCARTAVEL: Final[frozenset[str]] = frozenset(
    {_singular(p) for p in _RUIDO | _PREPARO | _MEDIDA_NO_NOME}
    | _RUIDO
    | _PREPARO
    | _MEDIDA_NO_NOME
)

#: Os sinônimos com a mesma normalização do núcleo, para "filé de frango em
#: tiras" achar a entrada "file de frango" sem uma chave para cada preparo.
_SINONIMOS_POR_NUCLEO: Final[dict[str, str]] = {_nucleo(k): v for k, v in SINONIMOS.items()}

#: O ruído e o preparo, sem as palavras de corte: para reconhecer "peito" e "filé".
_RUIDO_E_PREPARO: Final[frozenset[str]] = frozenset(
    {_singular(p) for p in _RUIDO | _PREPARO} | _RUIDO | _PREPARO
)


__all__ = [
    "CORTES_DO_FRANGO",
    "FINALIDADES",
    "FORMAS",
    "LIMIAR_APROXIMADO",
    "MARCAS",
    "MARCAS_QUE_SAO_O_PRODUTO",
    "PEITO_DE_FRANGO",
    "SINONIMOS",
    "Casamento",
    "Estrategia",
    "casar",
    "casar_confirmado",
    "casar_todos",
    "forma_diferente",
    "mesma_forma",
    "motivo_do_sinonimo",
    "nucleo_do_nome",
    "sem_a_finalidade",
    "sem_marca",
]


@lru_cache(maxsize=16384)
def nucleo_do_nome(texto: str) -> str:
    """O núcleo de um nome ("cenouras médias" -> "cenoura"): o produto, sem corte e preparo."""
    return _nucleo(texto)
