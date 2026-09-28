"""Interpretação de linha de ingrediente escrita por gente.

Sites de receita brasileiros não escrevem quantidade num formato. Escrevem
"2 xícaras (chá) de farinha de trigo", "1 e 1/2 colher de sopa", "½ kg de carne",
"sal a gosto", "3 ovos", "200 g de queijo ralado". Nenhum deles está errado: é
assim que se escreve receita em português.

Este módulo transforma isso em `IngredienteReceita`, que é o que o motor
consegue custear. O que ele **não** faz é adivinhar: linha que não dá para
interpretar volta com `quantidade=None` em vez de virar um número plausível e
errado, porque um número plausível e errado atravessa o sistema inteiro sem
ninguém perceber e sai como preço.

Sem quantidade, a linha sai de um de dois jeitos, e a diferença importa:

- a receita **disse** que é a gosto ("sal a gosto", "azeite para untar",
  "salsinha (opcional)"): entra como "a gosto", e a marca vai em `observacao`;
- a linha traz **só o nome de tempero**, sem número e sem marca ("Sal", "Sal e
  pimenta-do-reino", "Azeite", "Cheiro-verde", "Orégano"): é a convenção da
  receita brasileira para o que vai a gosto, e entra como "a gosto", com a
  observação de que a receita não diz quanto (`mise.temperos`);
- a leitura **não entendeu** quanto vai ("temperos de sua preferência",
  "Milho" ou "Alho amassado" sozinhos): sai com `entendida=False`, e o motor
  pergunta a ela em vez de fingir que a linha é a gosto.

Quando a linha tem número, o número vale, mesmo com uma marca junto ("2
colheres de azeite ou o quanto baste"): a marca só explica, não apaga a
quantidade que a receita deu. "Opcional", "se desejar" e "se quiser" marcam o
ingrediente como opcional, com ou sem quantidade.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation

from mise.receita import IngredienteReceita
from mise.temperos import A_GOSTO_POR_CONVENCAO, TEMPEROS_A_GOSTO, so_tempero
from mise.unidades import MEDIDAS_CONTADAS, MEDIDAS_MASSA, MEDIDAS_VOLUME

#: A versão das regras de leitura. Sobe a cada mudança que muda o que uma linha
#: já lida vira: a receita guardada com uma versão antiga é lida de novo pelo
#: servidor, a partir das linhas originais que ela guarda, sem buscar a página
#: (`mise.catalogo.reler_as_linhas`). A 2 lê "1/2 de xícara", o "(ou a gosto)"
#: depois da medida, "colher (sopa) rasa" e "caldo de ½ limão"; a 3 lê "folhas
#: de 1 ramo de alecrim" como 1 ramo de alecrim.
VERSAO_DA_LEITURA = 3

#: Frações escritas como caractere único. `unicodedata.numeric` resolveria, mas
#: devolve float, e float em quantidade de receita vira centavo errado no CMV.
FRACOES_UNICODE: dict[str, Decimal] = {
    "½": Decimal("0.5"),
    "⅓": Decimal("1") / Decimal("3"),
    "⅔": Decimal("2") / Decimal("3"),
    "¼": Decimal("0.25"),
    "¾": Decimal("0.75"),
    "⅕": Decimal("0.2"),
    "⅛": Decimal("0.125"),
    "⅜": Decimal("0.375"),
    "⅝": Decimal("0.625"),
    "⅞": Decimal("0.875"),
}

#: O que marca um ingrediente como "a gosto": sem quantidade de propósito, custo
#: desprezível, mas contado, não esquecido. Uma linha sem número e sem nenhuma
#: destas marcas não é "a gosto": é uma linha que a leitura não entendeu.
MARCAS_A_GOSTO: tuple[str, ...] = (
    "a gosto",
    "à gosto",
    "a vontade",
    "à vontade",
    "quanto baste",
    "q.b.",
    "qb",
    "o quanto baste",
    "o quanto precisar",
    "a olho",
    "para polvilhar",
    "para untar",
    "para decorar",
    "para servir",
    "para fritar",
    "para empanar",
    "para pincelar",
    "para finalizar",
    "para refogar",
    "para acompanhar",
    "se desejar",
    "se quiser",
    "opcional",
)

#: O que marca um ingrediente como opcional: a receita diz que dá para fazer sem.
#: "Para acompanhar" também: o arroz e a farofa que acompanham o prato não fazem
#: parte dele.
MARCAS_OPCIONAL: tuple[str, ...] = (
    "opcional",
    "se desejar",
    "se quiser",
    "facultativo",
    "para acompanhar",
)

#: Abaixo disto, tirar "es" ou "s" deixaria um toco em vez de uma palavra.
MINIMO_PARA_TIRAR_ES = 3
MINIMO_PARA_TIRAR_S = 2

#: Palavras que aparecem entre a medida e o ingrediente e não fazem parte de
#: nenhum dos dois.
LIGACOES: tuple[str, ...] = ("de", "do", "da", "dos", "das")

#: Embalagens que aparecem como se fossem medida. Não são: "1 lata de leite
#: condensado" é uma quantidade que depende do tamanho da lata, e o motor tem um
#: caminho próprio para isso (`MassaDesconhecida`, que vira pergunta). O que este
#: módulo faz é não deixar a palavra grudada no nome do ingrediente, senão
#: "lata de leite condensado" não casa com "leite condensado" na despensa.
EMBALAGENS: tuple[str, ...] = (
    "lata",
    "latas",
    "pacote",
    "pacotes",
    "caixa",
    "caixas",
    "vidro",
    "vidros",
    "pote",
    "potes",
    "sache",
    "saches",
    "tablete",
    "tabletes",
    "envelope",
    "envelopes",
    "garrafa",
    "garrafas",
    "caixinha",
    "caixinhas",
    "saquinho",
    "saquinhos",
    "bandeja",
    "bandejas",
)

#: Números como se escrevem por extenso em receita. "Meia xícara" e "duas
#: colheres" viravam "a gosto", e um ingrediente com quantidade saía da conta.
POR_EXTENSO: dict[str, Decimal] = {
    "um": Decimal(1),
    "uma": Decimal(1),
    "dois": Decimal(2),
    "duas": Decimal(2),
    "tres": Decimal(3),
    "quatro": Decimal(4),
    "cinco": Decimal(5),
    "seis": Decimal(6),
    "sete": Decimal(7),
    "oito": Decimal(8),
    "nove": Decimal(9),
    "dez": Decimal(10),
    "meio": Decimal("0.5"),
    "meia": Decimal("0.5"),
}

_EXTENSO = re.compile(
    r"^\s*(?P<numero>" + "|".join(POR_EXTENSO) + r")\b(?:\s+e\s+(?P<meio>meio|meia)\b)?\s*",
    re.IGNORECASE,
)

_NUMERO = r"\d+(?:[.,]\d+)?"
_FRACAO = r"\d+\s*/\s*\d+"

# A ordem importa. "1/2" tem que ser testado antes de "1", senão o inteiro come
# o numerador e a linha vira "1" com resto "/2", que foi exatamente o defeito
# que este comentário existe para não deixar voltar.
_MISTO = re.compile(rf"^\s*(?P<inteiro>{_NUMERO})\s+(?:e\s+)?(?P<fracao>{_FRACAO})\s*")
_SO_FRACAO = re.compile(rf"^\s*(?P<fracao>{_FRACAO})\s*")
_SO_INTEIRO = re.compile(rf"^\s*(?P<inteiro>{_NUMERO})\s*")

# "(chá)", "(sopa)", "(rasa)" logo depois da medida
_PARENTESE = re.compile(r"\s*\(([^)]*)\)")

# "200g", "1kg", "500ml": número colado na unidade
_COLADO = re.compile(rf"^\s*({_NUMERO})\s*(kg|g|mg|l|ml|un|und|unidade)s?\b", re.IGNORECASE)


# "Suco de 1 limão", "raspas de 1 laranja": a receita pede uma parte da fruta,
# e o que se compra é a fruta. A quantidade é das frutas; a parte vai para a
# observação. Sem isto a linha inteira virava "não entendi".
_PARTE_DA_FRUTA = re.compile(
    r"^(?P<parte>suco|sumo|caldo|raspas?|cascas?)\s+(?:de|do|da|dos|das)\s+(?P<resto>.+)$",
    re.IGNORECASE,
)

# "Folhas de 1 ramo de alecrim": a receita pede as folhas, e o que se compra é o
# ramo. A quantidade é a do ramo; a parte vai para a observação. Só quando o que
# vem depois começa por número: "folhas de louro" é o louro, e fica como está.
_PARTE_DA_ERVA = re.compile(
    r"^(?P<parte>folhas?|folhinhas?|raminhos?)\s+(?:de|do|da|dos|das)\s+(?P<resto>[\d½¼¾⅓⅔].*)$",
    re.IGNORECASE,
)

#: "Caldo de ½ limão" é o suco dele. "Caldo" só é parte da fruta com fruta de
#: caldo: "caldo de 1 tablete" é outra coisa, e fica como está.
_FRUTAS_DE_CALDO: frozenset[str] = frozenset(
    {"limao", "limoes", "laranja", "laranjas", "lima", "limas", "tangerina", "tangerinas"}
)

# "2 a 3 colheres", "2 ou 3 dentes", "2-3 xícaras": uma faixa. Vale o maior
# número, que é o que a despensa precisa ter e o que a conta não pode esquecer;
# a faixa vai para a observação.
_FAIXA = re.compile(rf"^\s*(?:a|ou|até|-|\u2013)\s*(?P<ate>{_NUMERO})(?=\s|$)\s*", re.IGNORECASE)

# O peso que a própria receita dá: "(500 gramas)", "(cerca de 200 g)", "de
# aproximadamente 180 gramas cada", "de 1 kg". Vale mais que o peso típico da
# tabela e que a densidade: é a receita dizendo quanto vai.
_CERCA = r"(?:cerca\s+de\s+|aproximadamente\s+|aprox\.?\s+|mais\s+ou\s+menos\s+|uns\s+|umas\s+)?"
_PESO = rf"(?P<valor>{_NUMERO})\s*(?P<unidade>kg|g|gr|gramas?|quilos?)\.?"
_PESO_ENTRE_PARENTESES = re.compile(rf"\(\s*{_CERCA}{_PESO}\s*(?P<cada>cada)?\s*\)", re.IGNORECASE)
_PESO_DE_CADA = re.compile(
    rf",?\s+(?:de|com)\s+{_CERCA}{_PESO}\s+(?P<cada>cada)\b\s*,?", re.IGNORECASE
)
_PESO_NO_FIM = re.compile(rf"\s+(?:de|com)\s+{_CERCA}{_PESO}\s*$", re.IGNORECASE)

# O que vem depois do ingrediente dizendo como prepará-lo: "cortado em 4 filés",
# "picadinhas", "em cubos", "limpas e sem pele". Não é o ingrediente, e grudado
# no nome fazia "cebola cortada em quadrados" não casar com a cebola da despensa.
# Fica de fora o que muda o produto que se compra ("ralado", "moída", "em pó").
_PREPARO = re.compile(
    r"\s+(?:bem\s+)?(?:"
    r"(?:cortad|picad|picadinh|descascad|amassad|fatiad|cozid|pr[eé]-cozid|limp|espremid"
    r"|lavad|escorrid|desfiad)[oa]s?"
    r"|em\s+(?:cubos?|cubinhos?|rodelas?|rodelinhas?|tiras?|tirinhas?|peda[cç]os?"
    r"|pedacinhos?|quadrados?|l[aâ]minas?|fatias?|gomos?|metades?)"
    r")\b.*$",
    re.IGNORECASE,
)


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def _para_decimal(bruto: str) -> Decimal | None:
    try:
        return Decimal(bruto.strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


#: Uma fração tem numerador e denominador. "1/2/3" não é fração de nada.
PARTES_DE_UMA_FRACAO = 2


def _fracao(bruto: str) -> Decimal | None:
    partes = bruto.split("/")
    if len(partes) != PARTES_DE_UMA_FRACAO:
        return None
    cima, baixo = (_para_decimal(p) for p in partes)
    if cima is None or baixo is None or baixo == 0:
        return None
    return cima / baixo


def e_a_gosto(texto: str) -> bool:
    """A linha diz "a gosto" em alguma das muitas formas de dizer isso."""
    limpo = _sem_acento(texto)
    return any(_sem_acento(marca) in limpo for marca in MARCAS_A_GOSTO)


def e_opcional(texto: str) -> bool:
    """A linha diz que o ingrediente é opcional ("opcional", "se desejar", "se quiser")."""
    limpo = _sem_acento(texto)
    return any(_sem_acento(marca) in limpo for marca in MARCAS_OPCIONAL)


def _medida_conhecida(candidato: str) -> str | None:
    """Casa o começo do texto com o vocabulário de medidas do motor.

    Tenta do mais longo para o mais curto, senão "colher de sopa" seria
    reconhecido como "colher" e a conversão sairia por outro fator.
    """
    normalizado = _sem_acento(candidato).strip()
    conhecidas = sorted({*MEDIDAS_VOLUME, *MEDIDAS_MASSA, *MEDIDAS_CONTADAS}, key=len, reverse=True)
    for medida in conhecidas:
        alvo = _sem_acento(medida)
        if normalizado == alvo or normalizado.startswith(alvo + " "):
            return medida
    return None


def interpretar_linha(texto: str) -> IngredienteReceita:
    """Uma linha de ingrediente como o site escreveu, virando dado do motor.

    Devolve sempre um `IngredienteReceita`: o texto original fica guardado em
    `texto_original`, para a Dona Maria poder conferir o que interpretamos.
    """
    # NFC: "três" pode chegar com o acento como caractere separado, e aí o
    # número por extenso não casaria com o texto de onde ele foi cortado.
    original = " ".join(unicodedata.normalize("NFC", texto).split())
    if not original:
        return IngredienteReceita(texto_original=texto, nome="", entendida=False)

    marca = _marca_encontrada(original) if e_a_gosto(original) else ""
    opcional = e_opcional(original)

    # O número que a linha dá vale mais que a marca: "2 colheres de azeite ou o
    # quanto baste" pede duas colheres, e a marca só vai para a observação.
    if (lida := _ler_quantidade(original)) is not None:
        nome, preparo = _separar_preparo(lida.nome)
        return IngredienteReceita(
            texto_original=original,
            nome=nome,
            quantidade=lida.quantidade,
            medida=lida.medida,
            observacao=_juntar(lida.nota, preparo, marca),
            opcional=opcional,
        )

    # Sem número e com a marca, a receita escolheu não dar quantidade: "a gosto".
    # A marca vai para `observacao`, que é o que a Dona Maria vê quando pergunta
    # por que aquele item entrou na conta sem número.
    if marca:
        return IngredienteReceita(
            texto_original=original,
            nome=_nome_limpo(_sem_quantidade(original)),
            observacao=marca,
            opcional=opcional,
        )

    # Sem número e sem marca, mas só com nome de tempero ("Sal", "Sal e
    # pimenta-do-reino", "Azeite"): a receita brasileira escreve assim o que vai
    # a gosto. Entra como "a gosto", com a observação de que a receita não diz
    # quanto, em vez de segurar a receita inteira numa pergunta sobre o sal.
    if so_tempero(original):
        return IngredienteReceita(
            texto_original=original,
            nome=_nome_limpo(original),
            observacao=A_GOSTO_POR_CONVENCAO,
            opcional=opcional,
        )

    # Sem número e sem marca: a leitura não entendeu quanto vai. Devolve o que
    # deu, sem inventar e sem chamar de "a gosto": o motor pergunta a ela.
    return IngredienteReceita(
        texto_original=original, nome=_nome_limpo(original), opcional=opcional, entendida=False
    )


@dataclass(frozen=True, slots=True)
class _Lida:
    """A quantidade, a medida e o nome lidos de uma linha, e o que mais ela disse."""

    quantidade: Decimal
    medida: str
    nome: str
    #: O que a leitura tirou da linha e a Dona Maria precisa poder conferir:
    #: "suco", "entre 2 e 3", "2 postas de 180 gramas cada".
    nota: str = ""


def _ler_quantidade(original: str) -> _Lida | None:
    """A quantidade, a medida e o nome, quando a linha diz quanto vai de um jeito legível."""
    # "Suco de 1 limão": o que se compra é o limão, e a parte vai para a nota.
    if (
        (parte := _PARTE_DA_FRUTA.match(original)) is not None
        and (da_fruta := _ler_quantidade(parte.group("resto"))) is not None
        and _e_parte_da_fruta(parte.group("parte"), da_fruta.nome)
    ):
        return replace(da_fruta, nota=_juntar(parte.group("parte").lower(), da_fruta.nota))
    # "Folhas de 1 ramo de alecrim": compra-se o ramo, e as folhas vão para a nota.
    if (erva := _PARTE_DA_ERVA.match(original)) is not None and (
        do_ramo := _ler_quantidade(erva.group("resto"))
    ) is not None:
        return replace(do_ramo, nota=_juntar(erva.group("parte").lower(), do_ramo.nota))

    sem_peso, peso = _tirar_peso(original)
    lida = _ler_sem_peso(sem_peso)
    if lida is None or peso is None or _sem_acento(lida.medida) in _MEDIDAS_DE_MASSA:
        return lida if peso is None or lida is None else (_ler_sem_peso(original) or lida)
    gramas, de_cada, escrito = peso
    if _sem_acento(lida.medida) in EMBALAGENS:
        # "2 latas de milho (200 g)": compra-se lata, e o preço dela é por lata.
        # Trocar por 400 g faria a cotação de uma lata pagar as duas.
        return replace(lida, nota=_juntar(lida.nota, escrito))
    # O peso de cada um multiplica ("2 postas de 180 g cada"); o resto é o total
    # que a receita pede: "6 bifes de alcatra (500 gramas)" são 500 g, não 3 kg.
    total = gramas * lida.quantidade if de_cada else gramas
    return _Lida(total, "g", lida.nome, _juntar(lida.nota, escrito))


def _e_parte_da_fruta(parte: str, nome: str) -> bool:
    """Suco, raspas e casca são sempre da fruta; o caldo, só da fruta de caldo."""
    if parte.lower() != "caldo":
        return True
    primeira = _sem_acento(nome).split()[:1]
    return bool(primeira) and primeira[0] in _FRUTAS_DE_CALDO


#: As medidas que já são massa: um peso entre parênteses não muda nada nelas.
_MEDIDAS_DE_MASSA: frozenset[str] = frozenset({"g", "kg", "mg", "grama", "gramas", "quilo"})


def _tirar_peso(texto: str) -> tuple[str, tuple[Decimal, bool, str] | None]:
    """A linha sem o peso que ela declara, e o peso em gramas, se é de cada um e como veio."""
    for padrao in (_PESO_ENTRE_PARENTESES, _PESO_DE_CADA, _PESO_NO_FIM):
        casou = padrao.search(texto)
        if casou is None:
            continue
        valor = _para_decimal(casou.group("valor"))
        if valor is None or valor <= 0:
            continue
        unidade = casou.group("unidade").lower()
        gramas = valor * 1000 if unidade.startswith(("kg", "quilo")) else valor
        # "de 1 kg" no fim da linha é o peso de cada peça: "1 posta de salmão de 1 kg".
        de_cada = bool(casou.groupdict().get("cada")) or padrao is _PESO_NO_FIM
        sem = " ".join(f"{texto[: casou.start()]} {texto[casou.end() :]}".split())
        return sem, (gramas, de_cada, " ".join(casou.group(0).strip(" ,()").split()))
    return texto, None


def _ler_sem_peso(original: str) -> _Lida | None:
    """A quantidade, a medida e o nome, quando a linha começa por um número que dá para ler."""
    # "200g de queijo": número colado na unidade.
    if colado := _COLADO.match(original):
        valor = _para_decimal(colado.group(1))
        if valor is not None:
            resto = original[colado.end() :]
            return _Lida(valor, _medida_canonica(colado.group(2)), _nome_limpo(resto))

    quantidade, resto = _separar_quantidade(original)
    if quantidade is None:
        return None

    nota = ""
    faixa = _FAIXA.match(resto)
    ate = _para_decimal(faixa.group("ate")) if faixa is not None else None
    if faixa is not None and ate is not None and ate > quantidade:
        nota = f"entre {_numero_escrito(quantidade)} e {_numero_escrito(ate)}"
        quantidade, resto = ate, resto[faixa.end() :]

    medida, nome, enchimento = _medida_nome_e_enchimento(resto)
    limpo = _nome_limpo(nome)

    # "3 ovos", "3 cenouras médias": quando a medida é peso unitário, ela **é** o
    # ingrediente, não um qualificador dele. Tirá-la do nome deixaria "médias"
    # sozinho, que não casa com nada na despensa.
    if medida in MEDIDAS_CONTADAS:
        limpo = _nome_limpo(resto)
    elif not limpo and medida:
        limpo = _nome_limpo(resto) or medida
    return _Lida(quantidade, medida, limpo, _juntar(nota, enchimento))


def _separar_preparo(nome: str) -> tuple[str, str]:
    """ "cebola cortada em quadrados" vira ("cebola", "cortada em quadrados").

    A primeira palavra nunca sai: "picadinho de carne" é o prato, não o preparo.
    """
    casou = _PREPARO.search(nome)
    if casou is None or not (base := nome[: casou.start()].strip(" ,;")):
        return nome, ""
    return base, casou.group(0).strip(" ,;")


def _juntar(*partes: str) -> str:
    """As observações que a linha juntou, sem vazio e sem repetir."""
    return ", ".join(dict.fromkeys(p.strip() for p in partes if p and p.strip()))


def _numero_escrito(valor: Decimal) -> str:
    """ "2", "2,5": o número como se escreve numa receita brasileira."""
    normalizado = valor.normalize()
    if normalizado == normalizado.to_integral_value():
        return str(normalizado.quantize(Decimal(1)))
    return f"{normalizado:f}".replace(".", ",")


def _separar_quantidade(texto: str) -> tuple[Decimal | None, str]:
    """A quantidade do começo da linha, somando inteiro e fração.

    Testa do mais específico para o mais genérico: "1 e 1/2" antes de "1/2",
    "1/2" antes de "1". Trocar essa ordem faz "1/2 xícara" virar "1".
    """
    limpo = texto.strip()
    for tentar in (_fracao_unicode, _misto, _so_fracao, _so_inteiro, _por_extenso):
        if (achado := tentar(limpo)) is not None:
            return achado
    return None, texto


def _fracao_unicode(limpo: str) -> tuple[Decimal, str] | None:
    if limpo[:1] in FRACOES_UNICODE:
        return FRACOES_UNICODE[limpo[0]], limpo[1:]
    return None


def _misto(limpo: str) -> tuple[Decimal, str] | None:
    """ "1 e 1/2" e "1 1/2"."""
    if not (casou := _MISTO.match(limpo)):
        return None
    inteiro = _para_decimal(casou.group("inteiro"))
    fracionaria = _fracao(casou.group("fracao"))
    if inteiro is None or fracionaria is None:
        return None
    return inteiro + fracionaria, limpo[casou.end() :]


def _so_fracao(limpo: str) -> tuple[Decimal, str] | None:
    """ "1/2". Tem que ser testado antes do inteiro, senão vira 1."""
    if not (casou := _SO_FRACAO.match(limpo)):
        return None
    if (fracionaria := _fracao(casou.group("fracao"))) is None:
        return None
    return fracionaria, limpo[casou.end() :]


#: "1 e ½", "1 e meia": o "e" entre o inteiro e a metade que se soma a ele.
_E_MEIA = re.compile(r"^e\s+(?:(?P<fracao>[" + "".join(FRACOES_UNICODE) + r"])|(?:meia|meio)\b)\s*")


def _so_inteiro(limpo: str) -> tuple[Decimal, str] | None:
    if not (casou := _SO_INTEIRO.match(limpo)):
        return None
    if (inteiro := _para_decimal(casou.group("inteiro"))) is None:
        # Inalcançável hoje: tudo que `_SO_INTEIRO` casa o `_para_decimal` lê.
        # Fica como guarda contra os dois deixarem de concordar: mudar um dos
        # regex sem mexer no outro devolveria `None` aqui em vez de estourar,
        # e o motor pergunta em vez de custear em cima de lixo.
        return None  # pragma: sem cobertura
    resto = limpo[casou.end() :]
    # "1 ½ xícara": fração unicode logo depois do inteiro.
    if resto[:1] in FRACOES_UNICODE:
        return inteiro + FRACOES_UNICODE[resto[0]], resto[1:]
    # "1 e ½ xícara", "1 e meia xícara": sem isto, a metade ficava de fora da conta.
    if (e_meia := _E_MEIA.match(resto)) is not None:
        fracao = e_meia.group("fracao")
        metade = FRACOES_UNICODE[fracao] if fracao else Decimal("0.5")
        return inteiro + metade, resto[e_meia.end() :]
    return inteiro, resto


def _por_extenso(limpo: str) -> tuple[Decimal, str] | None:
    """ "meia xícara", "duas colheres", "uma e meia xícara", "um fio"."""
    casou = _EXTENSO.match(_sem_acento(limpo))
    if not casou:
        return None
    valor = POR_EXTENSO[casou.group("numero").lower()]
    if casou.group("meio"):
        valor += Decimal("0.5")
    return valor, limpo[casou.end() :]


#: O tipo da colher, da xícara e do copo, entre parênteses logo depois dela:
#: "xícaras (chá)", "colher (de sopa)", "colher (sopa rasa)", "copo (americano)".
#: Só isto qualifica a medida. Outro parêntese ("(ou a gosto)", "(opcional)")
#: não é da medida: tomado por ela, "1/2 colher de chá de sal (ou a gosto)" virou
#: "chá de sal" medido em colher de sopa.
_TIPO_ENTRE_PARENTESES = re.compile(
    r"^(?P<palavra>\S+)\s*\(\s*(?P<tipo>(?:de\s+)?(?:cha|sopa|sobremesa|cafe|requeijao)|americano)"
    r"(?:\s+(?P<enchimento>(?:bem\s+)?(?:rasas?|cheias?)))?\s*\)"
)

#: Como a colher vai cheia, logo depois da medida: "colher de sopa rasa", "(cheia)".
#: Não é o ingrediente, e grudado no nome fazia "rasa de açúcar" não casar com nada.
_ENCHIMENTO = re.compile(
    r"^\(?\s*(?P<enchimento>(?:bem\s+)?(?:rasas?|cheias?|niveladas?|generosas?))\s*\)?(?=\s|$)"
)

#: A ligação que alguns sites escrevem entre o número e a medida: "1/2 de xícara",
#: "1 e 1/4 de colher". Fica ali só quando o que vem depois é mesmo uma medida.
_LIGACAO_ANTES_DA_MEDIDA = re.compile(r"^(?:de|do|da)\s+")


def _separar_medida(texto: str) -> tuple[str, str]:
    """A medida logo depois da quantidade, e o nome do ingrediente depois dela.

    "xícaras (chá) de farinha": o parêntese qualifica a medida e vira parte
    dela, porque "colher de chá" e "colher de sopa" são fatores diferentes.
    """
    medida, nome, _ = _medida_nome_e_enchimento(texto)
    return medida, nome


def _medida_nome_e_enchimento(texto: str) -> tuple[str, str, str]:
    """A medida, o que vem depois dela e como ela vai cheia ("rasa", "cheia"), se a linha diz."""
    limpo = texto.strip()
    if not limpo:
        return "", "", ""

    # "1/2 de xícara de açúcar": o "de" entre o número e a medida não é do nome.
    ligacao = _LIGACAO_ANTES_DA_MEDIDA.match(_sem_acento(limpo))
    if ligacao is not None and _comeca_por_medida(limpo[ligacao.end() :]):
        limpo = limpo[ligacao.end() :]

    limpo, enchimento = _tipo_entre_parenteses(limpo)

    for forma in _singulares(limpo):
        if medida := _medida_conhecida(forma):
            resto = _resto_depois_da_medida(limpo, medida)
            if not enchimento and (cheia := _ENCHIMENTO.match(_sem_acento(resto))) is not None:
                enchimento = resto[cheia.start("enchimento") : cheia.end("enchimento")]
                resto = resto[cheia.end() :].strip()
            return medida, resto, enchimento

    # "1 lata de milho": a embalagem é a medida, e o motor compara lata com lata.
    primeira, _, resto = limpo.partition(" ")
    if _sem_acento(primeira) in EMBALAGENS:
        return _embalagem_no_singular(primeira), resto, ""

    return "", limpo, ""


def _comeca_por_medida(texto: str) -> bool:
    """O texto começa por uma medida que o motor conhece, ou por uma embalagem."""
    primeira = texto.split(maxsplit=1)[0] if texto.strip() else ""
    return _sem_acento(primeira) in EMBALAGENS or any(
        _medida_conhecida(forma) for forma in _singulares(texto)
    )


def _tipo_entre_parenteses(texto: str) -> tuple[str, str]:
    """ "xícaras (chá) de farinha" vira "xícaras de chá de farinha", e o enchimento à parte.

    O tipo só entra quando forma uma medida que o motor conhece ("xícara de
    chá", "copo americano"); senão o parêntese sai, e a medida fica sem ele.
    """
    casou = _TIPO_ENTRE_PARENTESES.match(_sem_acento(texto))
    if casou is None:
        return texto, ""
    palavra = texto[: casou.end("palavra")]
    tipo = casou.group("tipo")
    if tipo != "americano" and not tipo.startswith("de "):
        tipo = f"de {tipo}"
    depois = texto[casou.end() :].strip()
    enchimento = (
        texto[casou.start("enchimento") : casou.end("enchimento")]
        if casou.group("enchimento")
        else ""
    )
    com_tipo = f"{palavra} {tipo}"
    if any(_sem_acento(forma) == _medida_conhecida(forma) for forma in _singulares(com_tipo)):
        return f"{com_tipo} {depois}".strip(), enchimento
    return f"{palavra} {depois}".strip(), enchimento


def _embalagem_no_singular(palavra: str) -> str:
    chave = _sem_acento(palavra)
    return chave[:-1] if chave.endswith("s") and chave[:-1] in EMBALAGENS else chave


def _singulares(texto: str) -> tuple[str, ...]:
    """As formas singulares plausíveis da primeira palavra, em ordem de aposta.

    Não tenta acertar a regra do português: "colheres" vira "colher" tirando
    "es", mas "dentes" vira "dente" tirando só o "s", e as duas terminam igual.
    Em vez de codificar a morfologia, devolve as duas hipóteses e deixa o
    vocabulário do motor decidir qual existe: quem sabe o que é medida é ele.
    """
    palavras = texto.split()
    if not palavras:
        return (texto,)

    primeira, resto = palavras[0], palavras[1:]
    formas = [primeira]
    baixa = primeira.lower()
    if baixa.endswith("es") and len(primeira) > MINIMO_PARA_TIRAR_ES:
        formas.append(primeira[:-2])
    if baixa.endswith("s") and len(primeira) > MINIMO_PARA_TIRAR_S:
        formas.append(primeira[:-1])
    # "limões" -> "limão", "pães" -> "pão": o plural que troca a vogal.
    if baixa.endswith(("ões", "ães")) and len(primeira) > MINIMO_PARA_TIRAR_ES:
        formas.append(primeira[:-3] + "ão")
    # Sem duplicata e preservando a ordem das apostas.
    return tuple(" ".join([f, *resto]) for f in dict.fromkeys(formas))


def _resto_depois_da_medida(texto: str, medida: str) -> str:
    """O que sobra depois de tirar a medida: é o nome do ingrediente.

    A medida ocupa na linha as palavras que tem no vocabulário: "xícaras de chá
    de farinha" perde "xícaras de chá". O tipo entre parênteses já chega escrito
    por extenso (`_tipo_entre_parenteses`).
    """
    return " ".join(texto.split()[len(medida.split()) :])


#: As marcas da mais longa para a mais curta: "o quanto baste" antes de "quanto
#: baste", senão sobra um "o" solto no nome do ingrediente. As de "opcional" vão
#: por último: em "cheiro-verde a gosto (opcional)" a marca da quantidade é "a
#: gosto", e o opcional já fica dito em `opcional`.
_MARCAS_DA_MAIS_LONGA: tuple[str, ...] = tuple(
    sorted(MARCAS_A_GOSTO, key=lambda marca: (marca in MARCAS_OPCIONAL, -len(marca)))
)

#: Palavras que sobram penduradas no fim do nome quando a marca sai: "azeite ou".
_SOBRAS_DA_MARCA: frozenset[str] = frozenset({"ou", "e", "o", "a", "se"})


def _marca_encontrada(texto: str) -> str:
    """Qual das muitas formas de dizer "a gosto" esta linha usou."""
    limpo = _sem_acento(texto)
    for marca in _MARCAS_DA_MAIS_LONGA:
        if _sem_acento(marca) in limpo:
            return marca
    return "a gosto"


def _sem_quantidade(texto: str) -> str:
    quantidade, resto = _separar_quantidade(texto)
    return resto if quantidade is not None else texto


def _nome_limpo(texto: str) -> str:
    """Tira ligações, marcas de "a gosto" e pontuação solta das bordas."""
    limpo = " ".join(texto.split())
    tirou_marca = False
    for marca in _MARCAS_DA_MAIS_LONGA:
        limpo, trocas = re.subn(re.escape(marca), "", limpo, flags=re.IGNORECASE)
        tirou_marca = tirou_marca or trocas > 0
    limpo = _PARENTESE.sub(" ", limpo)
    palavras = limpo.split()
    while palavras and _sem_acento(palavras[0]) in (*LIGACOES, *EMBALAGENS):
        palavras.pop(0)
    while tirou_marca and palavras and _sem_acento(palavras[-1]).lower() in _SOBRAS_DA_MARCA:
        palavras.pop()
    return " ".join(palavras).strip(" ,;:.-" + "\u2013\u2014")


def _medida_canonica(bruta: str) -> str:
    """ "G" e "gr" viram "g"; "und" vira "un". O motor só conhece a forma canônica."""
    return {
        "mg": "mg",
        "g": "g",
        "kg": "kg",
        "l": "l",
        "ml": "ml",
        "un": "un",
        "und": "un",
        "unidade": "un",
    }.get(bruta.lower(), bruta.lower())


__all__ = [
    "A_GOSTO_POR_CONVENCAO",
    "FRACOES_UNICODE",
    "MARCAS_A_GOSTO",
    "MARCAS_OPCIONAL",
    "TEMPEROS_A_GOSTO",
    "e_a_gosto",
    "e_opcional",
    "interpretar_linha",
    "so_tempero",
]
