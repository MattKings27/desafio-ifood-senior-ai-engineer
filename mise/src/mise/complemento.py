"""O que ela responde sobre uma receita guardada, e a conferência de que a receita é a mesma.

A receita da internet é a que o servidor leu da página, e o modelo não a
redigita. Mas a página às vezes não diz quantas porções rende, não traz o modo
de preparo, ou tem uma linha em que a leitura não achou quanto vai. A
conferência pergunta, e a resposta dela tem de voltar para a receita. Por isso
`completar` compara a receita guardada com a que veio junto do `receita_id` e
aceita só o que a página não dizia:

- o rendimento, quando a página não informou;
- o modo de preparo, quando a página não trouxe nenhum;
- o tempo no fogo (`tempo_cozimento_min`), quando a página não declarou e os
  passos não dizem;
- a quantidade de uma linha que a leitura não entendeu, ou de uma linha "a
  gosto", quando ela diz quanto usa.

`responder` faz o mesmo com uma resposta só, do jeito que a tela pergunta: o
campo da pergunta e o que ela respondeu. `responder_peso` anota quanto pesa a
linha cuja medida não se converte ("Não sei quanto pesa um peito de frango"):
quem chama já conferiu, pela conferência, que a pergunta é essa.

Qualquer outra diferença (outra quantidade numa linha que a página diz, uma
linha que a página não tem, outro rendimento) é recusada com o que mudou: é o
modelo redigitando a receita, e a conta passaria a ser de uma receita que
ninguém conferiu.

`diferencas` é a mesma comparação sem aceitar nada: o custo e o preço só saem
da receita que passou pela conferência, e uma receita digitada de novo precisa
ser igual a ela.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from mise.erros import ErroDeUso
from mise.receita import IngredienteReceita, Receita

if TYPE_CHECKING:
    from collections.abc import Iterable

#: Como a observação diz que a quantidade veio dela, e não da página.
DITO_POR_ELA: Final = "quantidade dita pela senhora"
A_GOSTO_DITO_POR_ELA: Final = "a gosto, como a senhora disse"

#: Como fica anotada a resposta a "A receita pede alcatra. É o seu miolo de alcatra?".
E_O_ITEM: Final = "é o item da despensa: "
NAO_E_O_ITEM: Final = "não é o item da despensa"

#: Como fica anotado o peso que ela disse: "peso: um peito de frango pesa 300 g".
PESO_DITO: Final = "peso: "
#: O maior peso que se aceita para uma linha da receita: 50 kg.
MAIOR_PESO_G: Final = Decimal(50_000)

#: As respostas de sim e de não, como ela escreve ou como o botão manda.
_SIM: Final = frozenset({"sim", "s", "e", "e sim", "isso", "e esse", "e essa"})
_NAO: Final = frozenset({"nao", "n", "nao e", "nao e esse", "nao e essa"})

#: O rendimento, o preparo, o tempo no fogo e cada linha: os campos das respostas dela.
CAMPO_DO_RENDIMENTO: Final = "rendimento_porcoes"
CAMPO_DO_PREPARO: Final = "modo_preparo"
CAMPO_DO_TEMPO: Final = "tempo_cozimento_min"

#: O maior tempo no fogo que se aceita como resposta: um dia.
MAIOR_TEMPO_MIN: Final = 24 * 60
#: O maior rendimento que se aceita como resposta.
MAIOR_RENDIMENTO: Final = 500


@dataclass(frozen=True, slots=True)
class Complemento:
    """A receita guardada com o que ela respondeu, e cada resposta anotada."""

    receita: Receita
    respostas: tuple[tuple[str, str], ...] = ()

    @property
    def mudou(self) -> bool:
        return bool(self.respostas)


def _chave(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.casefold().split())


def _numero(valor: Decimal) -> str:
    n = valor.normalize()
    return str(n.quantize(Decimal(1))) if n == n.to_integral_value() else f"{n:f}".replace(".", ",")


def _quanto(ingrediente: IngredienteReceita) -> str:
    """ "2 colheres de sopa", "a gosto": o que ela disse, como fica anotado."""
    from mise.unidades import _medida_escrita  # noqa: PLC0415

    if ingrediente.quantidade is None:
        return "a gosto"
    medida = _medida_escrita(ingrediente.medida, ingrediente.quantidade)
    return f"{_numero(ingrediente.quantidade)} {medida}".strip()


def _mesma_quantidade(a: IngredienteReceita, b: IngredienteReceita) -> bool:
    return a.quantidade == b.quantidade and _chave(a.medida) == _chave(b.medida)


def _par(linha: IngredienteReceita, guardadas: Iterable[IngredienteReceita]) -> int | None:
    """A posição da linha guardada que corresponde a esta: pelo texto, depois pelo nome."""
    lista = list(guardadas)
    for campo in ("texto_original", "nome"):
        alvo = _chave(getattr(linha, campo))
        if not alvo:
            continue
        for posicao, guardada in enumerate(lista):
            if _chave(getattr(guardada, campo)) == alvo:
                return posicao
    return None


def completar(guardada: Receita, nova: Receita) -> Complemento:
    """A receita guardada com as respostas dela que vieram em `nova`; recusa o resto.

    `nova` pode trazer só as linhas que ela respondeu: as que não vierem ficam
    como estão. Levanta `ErroDeUso` dizendo o que mudou quando `nova` muda algo
    que a página já dizia.
    """
    ingredientes = list(guardada.ingredientes)
    respostas: list[tuple[str, str]] = []
    recusas: list[str] = []

    for linha in nova.ingredientes:
        posicao = _par(linha, ingredientes)
        if posicao is None:
            recusas.append(f"a linha {linha.texto_original!r} não está na receita guardada")
            continue
        antes = ingredientes[posicao]
        if antes.quantidade is not None:
            if linha.quantidade is not None and not _mesma_quantidade(antes, linha):
                recusas.append(
                    f"a receita guardada já diz quanto vai de {antes.nome}: {antes.texto_original}"
                )
            elif linha.item_da_despensa not in (None, antes.item_da_despensa):
                # "É o seu miolo de alcatra?": a resposta dela fica na linha.
                ingredientes[posicao] = replace(antes, item_da_despensa=linha.item_da_despensa)
                respostas.append((antes.texto_original, _dito_do_item(linha.item_da_despensa)))
            continue
        if linha.quantidade is None and not (antes.nao_entendida and linha.a_gosto):
            continue
        ingredientes[posicao] = IngredienteReceita(
            texto_original=antes.texto_original,
            nome=antes.nome or linha.nome,
            quantidade=linha.quantidade,
            medida=linha.medida,
            observacao=DITO_POR_ELA if linha.quantidade is not None else A_GOSTO_DITO_POR_ELA,
            opcional=antes.opcional,
            entendida=True,
            item_da_despensa=antes.item_da_despensa,
        )
        respostas.append((antes.texto_original, _quanto(linha)))

    receita = replace(guardada, ingredientes=tuple(ingredientes))
    receita, do_rendimento = _rendimento(receita, nova, recusas)
    receita, do_preparo = _preparo(receita, nova, recusas)
    receita, do_tempo = _tempo(receita, nova, recusas)
    if recusas:
        raise MudaAReceita(guardada.nome, tuple(recusas))
    return Complemento(receita, (*respostas, *do_rendimento, *do_preparo, *do_tempo))


def _dito_do_item(item_da_despensa: str | None) -> str:
    """A resposta sobre o item parecido, como fica anotada na receita."""
    return f"{E_O_ITEM}{item_da_despensa}" if item_da_despensa else NAO_E_O_ITEM


def sim_ou_nao(resposta: str) -> bool | None:
    """ "sim", "É, sim", "não é": a resposta de um botão de sim ou não; `None` se não é isso."""
    chave = _chave(resposta).strip(" .!,")
    chave = " ".join(chave.replace(",", " ").split())
    if chave in _SIM:
        return True
    if chave in _NAO:
        return False
    return None


class MudaAReceita(ErroDeUso):
    """A receita digitada muda o que a receita guardada já diz: é redigitação, e não resposta.

    A mensagem é para quem chamou a ferramenta; `recusas` são as frases do que
    mudou, para a tela dizer a ela com as palavras dela.
    """

    def __init__(self, receita: str, recusas: tuple[str, ...]) -> None:
        super().__init__(
            "a receita que veio junto do receita_id muda o que a receita guardada já diz: "
            + "; ".join(recusas)
            + ". Mande só o receita_id, e junto só o que ela respondeu (o rendimento, o "
            "modo de preparo ou o tempo no fogo que faltavam, quanto vai de uma linha "
            "que eu não entendi, com o mesmo texto da linha, ou, na pergunta de quanto "
            "pesa uma linha, o peso que ela disse em `peso`, sem mudar a quantidade)",
            receita=receita,
        )
        self.recusas = recusas


def _rendimento(
    receita: Receita, nova: Receita, recusas: list[str]
) -> tuple[Receita, tuple[tuple[str, str], ...]]:
    if not nova.rendimento_informado:
        return receita, ()
    if not receita.rendimento_informado:
        porcoes = nova.rendimento_porcoes
        completa = replace(receita, rendimento_porcoes=porcoes, rendimento_informado=True)
        texto = f"{porcoes} {'porção' if porcoes == 1 else 'porções'}"
        return completa, ((CAMPO_DO_RENDIMENTO, texto),)
    if nova.rendimento_porcoes != receita.rendimento_porcoes:
        recusas.append(f"a receita guardada já diz que rende {receita.rendimento_porcoes} porções")
    return receita, ()


def _preparo(
    receita: Receita, nova: Receita, recusas: list[str]
) -> tuple[Receita, tuple[tuple[str, str], ...]]:
    if not nova.modo_preparo:
        return receita, ()
    if not receita.modo_preparo:
        completa = replace(receita, modo_preparo=nova.modo_preparo).com_exigencias_detectadas()
        return completa, ((CAMPO_DO_PREPARO, " ".join(nova.modo_preparo)),)
    if [_chave(p) for p in nova.modo_preparo] != [_chave(p) for p in receita.modo_preparo]:
        recusas.append("a receita guardada já traz o modo de preparo")
    return receita, ()


def _tempo(
    receita: Receita, nova: Receita, recusas: list[str]
) -> tuple[Receita, tuple[tuple[str, str], ...]]:
    minutos = nova.tempo_cozimento_min
    if minutos is None:
        return receita, ()
    if receita.tempo_cozimento_min is None:
        completa = replace(receita, tempo_cozimento_min=minutos)
        return completa, ((CAMPO_DO_TEMPO, f"{minutos} min no fogo"),)
    if minutos != receita.tempo_cozimento_min:
        recusas.append(
            f"a receita guardada já diz que o cozimento leva {receita.tempo_cozimento_min} min"
        )
    return receita, ()


# --------------------------------------------------------------------------- #
# Uma resposta de cada vez, como a tela pergunta                               #
# --------------------------------------------------------------------------- #

_NUMERO: Final = re.compile(r"\d+(?:[.,]\d+)?")
_HORAS: Final = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:h\b|hs\b|horas?\b)", re.IGNORECASE)
_MINUTOS: Final = re.compile(r"(\d+)\s*(?:min\b|mins\b|minutos?\b)", re.IGNORECASE)
_OUTRAS_UNIDADES: Final = re.compile(r"\b(?:dias?|semanas?|segundos?)\b", re.IGNORECASE)


#: Como cada pergunta da receita se diz para ela, e em que o número vem.
_DITO: Final[dict[str, tuple[str, str]]] = {
    CAMPO_DO_RENDIMENTO: ("o rendimento", "porções"),
    CAMPO_DO_TEMPO: ("o tempo no fogo", "minutos"),
}


def _inteiro(resposta: str, campo: str, maior: int) -> int:
    nome, unidade = _DITO[campo]
    casou = _NUMERO.search(resposta)
    if casou is None:
        raise ErroDeUso(f"Para {nome}, preciso de um número de {unidade}.", campo=campo)
    valor = Decimal(casou.group().replace(",", "."))
    if valor != valor.to_integral_value() or not 1 <= valor <= maior:
        raise ErroDeUso(
            f"{_maiuscula(nome)} vai de 1 a {maior} {unidade}, em número inteiro.", campo=campo
        )
    return int(valor)


def _maiuscula(texto: str) -> str:
    return texto[:1].upper() + texto[1:]


def _minutos(resposta: str) -> int:
    """ "40", "40 minutos", "1 hora", "1 h 30 min": o tempo em minutos."""
    if _OUTRAS_UNIDADES.search(resposta):
        raise ErroDeUso("O tempo no fogo vem em minutos ou em horas.", campo=CAMPO_DO_TEMPO)
    horas = _HORAS.search(resposta)
    minutos = _MINUTOS.search(resposta)
    if horas is None and minutos is None:
        return _inteiro(resposta, CAMPO_DO_TEMPO, MAIOR_TEMPO_MIN)
    total = Decimal(0)
    if horas is not None:
        total += Decimal(horas.group(1).replace(",", ".")) * 60
    if minutos is not None:
        total += Decimal(minutos.group(1))
    return _inteiro(str(total.to_integral_value()), CAMPO_DO_TEMPO, MAIOR_TEMPO_MIN)


def responder(
    guardada: Receita, campo: str, resposta: str, *, parecido: str | None = None
) -> Complemento:
    """A resposta dela a uma pergunta da receita, gravada como se viesse junto do id.

    `campo` é o da pergunta: `rendimento_porcoes`, `tempo_cozimento_min`,
    `modo_preparo`, ou o texto de uma linha de ingrediente: a que a leitura não
    entendeu (a resposta é quanto vai), ou a que se parece com um item da
    despensa (`parecido`, o item de "É o seu miolo de alcatra?"; a resposta é
    sim ou não). A resposta vai pelas mesmas regras de `completar`.
    """
    from retrieval.quantidades import interpretar_linha  # noqa: PLC0415

    texto = " ".join(resposta.split())
    if not texto:
        raise ErroDeUso("A resposta veio vazia.", campo=campo)
    # A receita guardada, só com o campo respondido trocado: o resto é igual e não muda nada.
    base = guardada
    nova: Receita
    if campo == CAMPO_DO_RENDIMENTO:
        porcoes = _inteiro(texto, campo, MAIOR_RENDIMENTO)
        nova = replace(base, rendimento_porcoes=porcoes, rendimento_informado=True)
    elif campo == CAMPO_DO_TEMPO:
        nova = replace(base, tempo_cozimento_min=_minutos(texto))
    elif campo == CAMPO_DO_PREPARO:
        passos = tuple(p.strip() for p in resposta.splitlines() if p.strip())
        nova = replace(base, modo_preparo=passos)
    else:
        linha = next(
            (i for i in guardada.ingredientes if _chave(i.texto_original) == _chave(campo)), None
        )
        if linha is None:
            raise ErroDeUso("Essa linha não está na receita.", campo=campo)
        e_o_mesmo = sim_ou_nao(texto)
        if parecido is not None and e_o_mesmo is not None and linha.quantidade is not None:
            escolha = replace(linha, item_da_despensa=parecido if e_o_mesmo else "")
            return _completar_sem_linhas_vazias(guardada, replace(base, ingredientes=(escolha,)))
        lida = interpretar_linha(texto)
        nova = replace(
            base,
            ingredientes=(
                IngredienteReceita(
                    texto_original=linha.texto_original,
                    nome=linha.nome,
                    quantidade=lida.quantidade,
                    medida=lida.medida,
                    entendida=lida.quantidade is not None or lida.a_gosto,
                ),
            ),
        )
    return _completar_sem_linhas_vazias(guardada, nova)


def _completar_sem_linhas_vazias(guardada: Receita, nova: Receita) -> Complemento:
    """A resposta que não muda nada é recusada: ou a receita já dizia, ou ela não disse quanto."""
    try:
        feito = completar(guardada, nova)
    except MudaAReceita as erro:
        # A tela recebe a frase de por que não muda, sem o recado para o agente.
        raise ErroDeUso(_maiuscula("; ".join(erro.recusas)) + ".", receita=guardada.nome) from erro
    if not feito.mudou:
        raise ErroDeUso(
            "Essa resposta não muda a receita: a receita já diz isso, ou a resposta não diz "
            "quanto vai.",
            receita=guardada.nome,
        )
    return feito


# --------------------------------------------------------------------------- #
# O peso de uma linha cuja medida não se converte                              #
# --------------------------------------------------------------------------- #

#: Um número e a palavra que vem logo depois dele: "300 g", "0,3 kg", "2 colheres".
_NUMERO_E_UNIDADE: Final = re.compile(r"(\d+(?:[.,]\d+)*(?:/\d+)?)\s*([a-z]+)?")
_GRAMAS: Final = frozenset({"g", "gr", "grs", "grama", "gramas"})
_QUILOS: Final = frozenset(
    {"kg", "kgs", "k", "quilo", "quilos", "kilo", "kilos", "quilograma", "quilogramas"}
)
#: O número que mede outra coisa: não é peso ("2 colheres", "200 ml").
_NAO_E_PESO: Final = re.compile(
    r"^(?:ml|l|lt|litros?|mg|xicaras?|colher(?:es)?|copos?|latas?|caixas?|pitadas?|"
    r"unidades?|dentes?|fatias?|pacotes?|potes?|macos?)$"
)
#: "cada", "cada uma", "por unidade": o peso é de uma unidade.
_DE_CADA: Final = re.compile(r"\b(?:cada|por unidade|a unidade)\b")
#: "as duas", "todas", "juntas", "ao todo": o peso é da linha inteira.
_DE_TUDO: Final = re.compile(
    r"\b(?:dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|todas|todos|tudo|"
    r"juntas|juntos|ao todo|no total|linha inteira)\b"
)
_MILHAR: Final = re.compile(r"[1-9]\d{0,2}(?:\.\d{3})+(?:,\d+)?")
_MIL: Final = Decimal(1000)


def _decimal_escrito(texto: str) -> Decimal | None:
    """ "300", "0,3", "0.3", "1.500", "1/2": o número como ela escreve; `None` se não é um."""
    if "/" in texto:
        de_cima, de_baixo = (_decimal_escrito(parte) for parte in texto.split("/", 1))
        return None if de_cima is None or not de_baixo else de_cima / de_baixo
    limpo = texto.replace(".", "").replace(",", ".") if _MILHAR.fullmatch(texto) else texto
    limpo = limpo.replace(",", ".")
    if limpo.count(".") > 1:
        return None
    return Decimal(limpo)


def ler_peso(resposta: str) -> tuple[Decimal, bool | None]:
    """ "300 g", "0,3 kg", "uns 300 gramas cada", "20 g as duas colheres": os gramas e de quanto.

    O segundo valor diz se o peso é de uma unidade (`True`, "cada"), da linha
    inteira (`False`, "as duas", "todas", "juntas") ou se ela não disse (`None`).
    Sem a unidade, o número é em gramas, como a pergunta pede. Sem número, ou
    com o número em outra medida ("200 ml"), é recusa: peso não se adivinha.
    """
    chave = _chave(resposta)
    pesos: list[Decimal] = []
    soltos: list[Decimal] = []
    medidas: list[Decimal] = []
    for casou in _NUMERO_E_UNIDADE.finditer(chave):
        numero = _decimal_escrito(casou.group(1))
        palavra = casou.group(2) or ""
        if numero is None:
            continue
        if palavra in _GRAMAS:
            pesos.append(numero)
        elif palavra in _QUILOS:
            pesos.append(numero * _MIL)
        elif _NAO_E_PESO.match(palavra):
            medidas.append(numero)
        else:
            soltos.append(numero)
    if pesos:
        gramas = pesos[0]
    elif len(soltos) == 1:
        gramas = soltos[0]
    elif medidas:
        raise ErroDeUso("O peso vem em gramas ou em quilos: por exemplo, 300 g.")
    else:
        raise ErroDeUso(
            "Para o peso, preciso de um número em gramas ou quilos: por exemplo, 300 g."
        )
    if _DE_CADA.search(chave):
        return gramas, True
    # "2 colheres dão 20 g" é o peso das duas; "1 colher dá 10 g", o de uma.
    if _DE_TUDO.search(chave) or any(n > 1 for n in medidas):
        return gramas, False
    return gramas, None


def _peso_texto(gramas: Decimal) -> str:
    """ "300 g", "12,5 g", "1,5 kg": o peso como ela lê."""
    if gramas >= _MIL:
        return f"{_numero(gramas / _MIL)} kg"
    return f"{_numero(gramas)} g"


def responder_peso(
    guardada: Receita,
    texto_da_linha: str,
    resposta: str,
    *,
    uma: str,
    por_unidade: bool | None = None,
) -> Complemento:
    """Quanto pesa a linha cuja medida não se converte, como ela disse; fica anotado.

    `uma` é o que a pergunta pede em gramas ("um peito de frango"). O peso é de
    uma unidade quando `por_unidade` é `True`, ou quando ela não disse de quanto
    é (é o que a pergunta pede); com `False`, ou com "as duas", é da linha
    inteira. A linha guarda o peso da linha inteira, em gramas.
    """
    posicao = next(
        (
            i
            for i, linha in enumerate(guardada.ingredientes)
            if _chave(linha.texto_original) == _chave(texto_da_linha)
        ),
        None,
    )
    if posicao is None:
        raise ErroDeUso("Essa linha não está na receita.", campo=texto_da_linha)
    linha = guardada.ingredientes[posicao]
    if linha.quantidade is None or linha.quantidade <= 0:
        raise ErroDeUso("Essa linha não diz quanto vai: responda quanto vai, e não o peso.")
    gramas, dito = ler_peso(resposta)
    de_cada = por_unidade if por_unidade is not None else dito is not False
    total = gramas * linha.quantidade if de_cada else gramas
    if not 0 < total <= MAIOR_PESO_G:
        raise ErroDeUso(
            "O peso de uma linha da receita vai de 1 grama a 50 kg.", campo=texto_da_linha
        )
    if de_cada or linha.quantidade == 1:
        frase = f"{uma} pesa {_peso_texto(gramas)}"
    else:
        verbo = "pesam" if linha.quantidade >= _DOIS else "pesa"
        frase = f"“{linha.texto_original}” {verbo} {_peso_texto(gramas)}"
    ingredientes = list(guardada.ingredientes)
    ingredientes[posicao] = replace(linha, peso_g=total)
    return Complemento(
        replace(guardada, ingredientes=tuple(ingredientes)),
        ((linha.texto_original, f"{PESO_DITO}{frase}"),),
    )


_DOIS: Final = Decimal(2)


def diferencas(guardada: Receita, nova: Receita) -> tuple[str, ...]:
    """O que `nova` tem de diferente da receita guardada; vazio quando é a mesma receita.

    Compara o que decide a conta: cada linha (texto, quantidade, medida e se é
    opcional), o rendimento e o modo de preparo. O nome só pela grafia
    ("arroz com FRANGO" é o mesmo prato).
    """
    achadas: list[str] = []
    if _chave(guardada.nome) != _chave(nova.nome):
        achadas.append(f"o nome ({nova.nome!r} no lugar de {guardada.nome!r})")
    linhas = [_assinatura(i) for i in guardada.ingredientes]
    novas = [_assinatura(i) for i in nova.ingredientes]
    if linhas != novas:
        faltando = [texto for texto, *_ in linhas if texto not in {n[0] for n in novas}]
        a_mais = [texto for texto, *_ in novas if texto not in {g[0] for g in linhas}]
        detalhe = [f"sem {t!r}" for t in faltando] + [f"com {t!r}" for t in a_mais]
        achadas.append(
            "os ingredientes" + (f" ({', '.join(detalhe)})" if detalhe else " (as quantidades)")
        )
    if (guardada.rendimento_porcoes, guardada.rendimento_informado) != (
        nova.rendimento_porcoes,
        nova.rendimento_informado,
    ):
        achadas.append("o rendimento")
    if [_chave(p) for p in guardada.modo_preparo] != [_chave(p) for p in nova.modo_preparo]:
        achadas.append("o modo de preparo")
    return tuple(achadas)


def _assinatura(ingrediente: IngredienteReceita) -> tuple[str, Decimal | None, str, bool]:
    return (
        _chave(ingrediente.texto_original),
        ingrediente.quantidade,
        _chave(ingrediente.medida),
        ingrediente.opcional,
    )


__all__ = [
    "A_GOSTO_DITO_POR_ELA",
    "CAMPO_DO_PREPARO",
    "CAMPO_DO_RENDIMENTO",
    "CAMPO_DO_TEMPO",
    "DITO_POR_ELA",
    "E_O_ITEM",
    "MAIOR_PESO_G",
    "NAO_E_O_ITEM",
    "PESO_DITO",
    "Complemento",
    "MudaAReceita",
    "completar",
    "diferencas",
    "ler_peso",
    "responder",
    "responder_peso",
    "sim_ou_nao",
]
