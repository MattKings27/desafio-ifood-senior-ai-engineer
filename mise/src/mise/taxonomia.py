"""Vocabulário controlado de equipamentos e técnicas.

Uma receita da internet nunca diz "requer forno". Ela diz *"leve ao forno
preaquecido a 180°C"*, ou *"asse por 40 minutos"*, ou *"gratine até dourar"*.
Três frases diferentes, o mesmo equipamento. E se o extrator devolver texto
livre ("forno", "forninho", "oven"), nada casa com o perfil da Dona Maria.

Por isso tudo aqui é **identificador fechado**. O extrator (LLM ou regex) só
pode produzir ids desta lista; qualquer coisa fora dela é rejeitada na
validação. O perfil dela usa os mesmos ids. O casamento vira operação de
conjunto, que é testável e não depende de o modelo escolher as mesmas palavras
duas vezes seguidas.

Cada entrada carrega os padrões que a denunciam no texto da receita. A camada
determinística resolve o caso óbvio sem gastar token; o LLM entra só no que
sobrou.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from mise.erros import VocabularioDesconhecido


class CategoriaEquipamento(StrEnum):
    COCCAO = "cocção"
    PREPARO = "preparo"
    FRIO = "frio"
    MEDICAO = "medição"
    UTENSILIO = "utensílio"


class CategoriaTecnica(StrEnum):
    BASICA = "básica"
    MASSAS = "massas"
    MOLHOS = "molhos"
    CARNES = "carnes"
    CONFEITARIA = "confeitaria"
    AVANCADA = "avançada"


@dataclass(frozen=True, slots=True)
class Equipamento:
    """Um equipamento de cozinha, com o que o denuncia numa receita."""

    id: str
    nome: str
    categoria: CategoriaEquipamento
    padroes: tuple[str, ...] = ()
    pressuposto: bool = False
    """True para o que toda cozinha tem (faca, panela, colher).

    Não perguntamos sobre estes: perguntar "a senhora tem panela?" para uma
    cozinheira de mão cheia é ofensivo e queima a paciência dela para as
    perguntas que importam.
    """
    substitutos: tuple[str, ...] = ()
    """Ids que resolvem o mesmo problema. Air fryer no lugar de forno, por exemplo."""
    pergunta: str = ""
    indicios: tuple[str, ...] = ()
    """Palavras que também denunciam a exigência, sem dizer onde o tempo corre.

    Os `padroes` servem ainda ao passo a passo, que lê neles onde está o fogo de
    cada duração ("leve ao forno e cozinhe por 30 minutos" é forno). "Cozinhe"
    pede fogão, mas não pode tirar a duração do forno: por isso fica aqui.
    """
    outros_aparelhos: tuple[str, ...] = ()
    """Aparelhos que, citados na mesma frase, fazem o indício não valer.

    "Cozinhe na air fryer" e "cozinhe no micro-ondas" não pedem fogão: sem esta
    lista, a cozinha sem fogão perdia justamente as receitas que ela consegue.
    """

    @property
    def palavras(self) -> tuple[str, ...]:
        """Tudo que denuncia o equipamento: os padrões primeiro, depois os indícios."""
        return self.padroes + self.indicios

    def pergunta_para_ela(self) -> str:
        return self.pergunta or f"A senhora tem {self.nome.lower()} aí na cozinha?"


@dataclass(frozen=True, slots=True)
class Tecnica:
    """Uma habilidade culinária que a receita exige."""

    id: str
    nome: str
    categoria: CategoriaTecnica
    padroes: tuple[str, ...] = ()
    pressuposta: bool = False
    dificuldade: int = 2
    """1 = qualquer um faz, 5 = exige prática real."""
    pergunta: str = ""
    contexto: tuple[str, ...] = ()
    """Palavras que precisam aparecer junto para a técnica valer.

    "Ao ponto" é ponto de carne num bife e não é nada num refogado; "bem
    passado" no arroz não pede técnica nenhuma. Sem contexto, cada frase comum
    virava uma pergunta sem sentido para ela.
    """

    def pergunta_para_ela(self) -> str:
        return self.pergunta or f"A senhora tem prática com {self.nome.lower()}?"


# --------------------------------------------------------------------------- #
# Equipamentos
# --------------------------------------------------------------------------- #

EQUIPAMENTOS: Final[tuple[Equipamento, ...]] = (
    # --- cocção ---
    Equipamento(
        "fogao",
        "Fogão",
        CategoriaEquipamento.COCCAO,
        ("fogo baixo", "fogo alto", "fogo medio", "leve ao fogo", "na panela", "boca do fogao"),
        pressuposto=True,
        # O fogão que a receita pede sem dizer "fogo": refogar, ferver, cozinhar,
        # a panela. Sem estes, "não tenho fogão" não bloqueava o arroz refogado.
        # "Frite" e "doure" ficam de fora: servem também à air fryer e ao forno.
        indicios=(
            "fogo brando",
            "fogo",
            "panela",
            "refogue",
            "refogar",
            # A receita que ela conta vem em primeira pessoa ("refogo a cebola,
            # cozinho 20 minutos"); "cozinha" fica de fora, que é também o cômodo.
            "refogo",
            "refoga",
            "refogando",
            "refogamos",
            "ferva",
            "ferver",
            "fervo",
            "ferve",
            "fervendo",
            "fervura",
            "fervente",
            "cozinhe",
            "cozinhar",
            "cozinho",
            "cozinhando",
            "cozinhamos",
        ),
        outros_aparelhos=(
            "forno",
            "air fryer",
            "airfryer",
            "micro-ondas",
            "microondas",
            "micro ondas",
            "eletrica",
            "eletrico",
            "fritadeira",
            "chapa",
            "grill",
            "churrasqueira",
        ),
    ),
    Equipamento(
        "forno",
        "Forno",
        CategoriaEquipamento.COCCAO,
        (
            "forno",
            "asse",
            "assar",
            "assada",
            "assado",
            "gratine",
            "gratinar",
            "preaqueca",
            "pre-aqueca",
            "180 c",
            "200 c",
            "220 c",
            "leve para assar",
        ),
        substitutos=("air_fryer", "forno_eletrico"),
        pergunta="A senhora tem forno? Pode ser o do fogão mesmo, ou elétrico.",
    ),
    Equipamento(
        "forno_eletrico",
        "Forno elétrico",
        CategoriaEquipamento.COCCAO,
        ("forno eletrico",),
        substitutos=("forno", "air_fryer"),
    ),
    Equipamento(
        "air_fryer",
        "Air fryer",
        CategoriaEquipamento.COCCAO,
        ("air fryer", "airfryer", "fritadeira eletrica", "fritadeira sem oleo"),
        substitutos=("forno",),
    ),
    Equipamento(
        "microondas",
        "Micro-ondas",
        CategoriaEquipamento.COCCAO,
        ("micro-ondas", "microondas", "micro ondas"),
    ),
    Equipamento(
        "panela_pressao",
        "Panela de pressão",
        CategoriaEquipamento.COCCAO,
        ("panela de pressao", "pressao por", "na pressao"),
        pergunta="A senhora tem panela de pressão? Faz muita diferença pra carne e feijão.",
    ),
    Equipamento(
        "frigideira",
        "Frigideira",
        CategoriaEquipamento.COCCAO,
        ("frigideira", "sele", "selar", "doure na", "fritar em pouco oleo"),
        pressuposto=True,
    ),
    Equipamento(
        "frigideira_antiaderente",
        "Frigideira antiaderente",
        CategoriaEquipamento.COCCAO,
        ("antiaderente", "teflon"),
        substitutos=("frigideira",),
    ),
    Equipamento(
        "panela_funda",
        "Panela funda",
        CategoriaEquipamento.COCCAO,
        ("panela funda", "caldeirao", "imersao em oleo", "fritura por imersao"),
        pressuposto=True,
    ),
    Equipamento(
        "assadeira",
        "Assadeira",
        CategoriaEquipamento.COCCAO,
        ("assadeira", "refratario", "travessa que va ao forno", "forma retangular"),
    ),
    Equipamento(
        "forma_bolo",
        "Forma de bolo",
        CategoriaEquipamento.COCCAO,
        ("forma de bolo", "forma redonda", "forma com furo no meio", "forma de pudim"),
    ),
    Equipamento(
        "chapa",
        "Chapa ou grill",
        CategoriaEquipamento.COCCAO,
        ("chapa", "grill", "grelha"),
    ),
    Equipamento(
        "churrasqueira",
        "Churrasqueira",
        CategoriaEquipamento.COCCAO,
        ("churrasqueira", "brasa", "carvao"),
    ),
    Equipamento(
        "banho_maria",
        "Banho-maria",
        CategoriaEquipamento.COCCAO,
        ("banho-maria", "banho maria"),
    ),
    # --- preparo ---
    Equipamento(
        "liquidificador",
        "Liquidificador",
        CategoriaEquipamento.PREPARO,
        ("liquidificador", "bata no liquidificador"),
        substitutos=("mixer", "processador"),
    ),
    Equipamento(
        "batedeira",
        "Batedeira",
        CategoriaEquipamento.PREPARO,
        ("batedeira", "bata em velocidade", "bata ate ficar claro"),
        substitutos=("mixer",),
        pergunta="A senhora tem batedeira? Se for na mão dá, mas cansa bastante.",
    ),
    Equipamento(
        "mixer",
        "Mixer de mão",
        CategoriaEquipamento.PREPARO,
        ("mixer", "mixer de mao"),
        substitutos=("liquidificador", "processador"),
    ),
    Equipamento(
        "processador",
        "Processador de alimentos",
        CategoriaEquipamento.PREPARO,
        ("processador", "processe"),
        substitutos=("liquidificador",),
    ),
    Equipamento(
        "ralador",
        "Ralador",
        CategoriaEquipamento.PREPARO,
        ("ralador", "ralado na hora", "rale"),
        pressuposto=True,
    ),
    Equipamento(
        "peneira",
        "Peneira",
        CategoriaEquipamento.PREPARO,
        ("peneira", "peneire", "peneirada"),
        pressuposto=True,
    ),
    Equipamento(
        "rolo_massa",
        "Rolo de massa",
        CategoriaEquipamento.PREPARO,
        ("rolo de massa", "abra a massa", "abrir a massa com"),
    ),
    Equipamento(
        "cilindro",
        "Cilindro de massa",
        CategoriaEquipamento.PREPARO,
        ("cilindro", "maquina de massa"),
        substitutos=("rolo_massa",),
    ),
    Equipamento(
        "fouet",
        "Batedor de arame (fouet)",
        CategoriaEquipamento.PREPARO,
        ("fouet", "batedor de arame", "mexendo sem parar com"),
        substitutos=("batedeira", "mixer"),
        pressuposto=True,
    ),
    Equipamento(
        "saco_confeitar",
        "Saco de confeitar",
        CategoriaEquipamento.PREPARO,
        ("saco de confeitar", "bico de confeitar", "confeitar"),
    ),
    Equipamento(
        "espremedor",
        "Espremedor",
        CategoriaEquipamento.PREPARO,
        ("espremedor", "espremido", "amassador de batata", "espremedor de batata"),
    ),
    # --- frio ---
    Equipamento(
        "geladeira",
        "Geladeira",
        CategoriaEquipamento.FRIO,
        ("geladeira", "leve a geladeira", "refrigere", "gele por"),
        pressuposto=True,
        # As palavras que o passo a passo já lê como frio (`mise.passos`): "deixe
        # gelar por 2 horas" ocupa a geladeira tanto quanto "leve à geladeira".
        indicios=("gelar", "gele", "gelando", "refrigerar", "refrigerador"),
    ),
    Equipamento(
        "freezer",
        "Freezer",
        CategoriaEquipamento.FRIO,
        ("freezer", "congele", "congelador", "leve ao congelador"),
        pergunta="A senhora tem freezer separado, ou só o congelador da geladeira?",
    ),
    # --- medição ---
    Equipamento(
        "balanca",
        "Balança de cozinha",
        CategoriaEquipamento.MEDICAO,
        ("balanca", "pese", "pesados"),
        pergunta="A senhora tem balança de cozinha? Pra vender ajuda muito a padronizar a porção.",
    ),
    Equipamento(
        "termometro",
        "Termômetro culinário",
        CategoriaEquipamento.MEDICAO,
        ("termometro", "ate atingir 70", "temperatura interna"),
    ),
    # --- utensílios ---
    Equipamento(
        "faca",
        "Faca",
        CategoriaEquipamento.UTENSILIO,
        # "faca" sozinha casava com "faça" depois de tirar o acento: "faça o
        # molho" virava faca no passo. O substantivo vem com artigo; o verbo, não.
        ("a faca", "uma faca", "da faca", "na faca", "corte", "pique", "fatie"),
        pressuposto=True,
    ),
    Equipamento(
        "tabua", "Tábua de corte", CategoriaEquipamento.UTENSILIO, ("tabua",), pressuposto=True
    ),
)

EQUIPAMENTOS_POR_ID: Final[dict[str, Equipamento]] = {e.id: e for e in EQUIPAMENTOS}


# --------------------------------------------------------------------------- #
# Técnicas
# --------------------------------------------------------------------------- #

TECNICAS: Final[tuple[Tecnica, ...]] = (
    # --- básicas: pressupostas numa cozinheira de mão cheia ---
    Tecnica(
        "refogar",
        "Refogar",
        CategoriaTecnica.BASICA,
        (
            "refogue",
            "refogar",
            "refogado",
            "refogo",
            "refoga",
            "refogando",
            "refogamos",
            "doure a cebola",
        ),
        pressuposta=True,
        dificuldade=1,
    ),
    Tecnica(
        "cozinhar_arroz",
        "Cozinhar arroz",
        CategoriaTecnica.BASICA,
        ("arroz soltinho", "cozinhe o arroz"),
        pressuposta=True,
        dificuldade=1,
    ),
    Tecnica(
        "cozinhar_feijao",
        "Cozinhar feijão",
        CategoriaTecnica.BASICA,
        ("feijao cozido", "cozinhe o feijao", "caldo do feijao"),
        pressuposta=True,
        dificuldade=1,
    ),
    Tecnica(
        "fritar",
        "Fritar",
        CategoriaTecnica.BASICA,
        ("frite", "fritar", "oleo quente"),
        pressuposta=True,
        dificuldade=1,
    ),
    Tecnica(
        "empanar",
        "Empanar",
        CategoriaTecnica.BASICA,
        ("empane", "empanar", "passe na farinha de rosca", "farinha, ovo e farinha de rosca"),
        dificuldade=2,
    ),
    Tecnica(
        "assar",
        "Assar",
        CategoriaTecnica.BASICA,
        ("asse", "assar"),
        pressuposta=True,
        dificuldade=1,
    ),
    Tecnica("grelhar", "Grelhar", CategoriaTecnica.BASICA, ("grelhe", "grelhar"), dificuldade=2),
    # --- massas ---
    Tecnica(
        "massa_fresca",
        "Massa fresca",
        CategoriaTecnica.MASSAS,
        ("massa fresca", "massa caseira", "sove a massa", "descanse a massa"),
        dificuldade=4,
        pergunta="A senhora já fez massa fresca em casa? Dá certo, mas dá trabalho.",
    ),
    Tecnica(
        "sovar_pao",
        "Sovar e fermentar pão",
        CategoriaTecnica.MASSAS,
        ("sove", "sovar", "fermento biologico", "deixe crescer", "dobre de volume"),
        dificuldade=4,
    ),
    Tecnica(
        "massa_folhada",
        "Massa folhada",
        CategoriaTecnica.MASSAS,
        ("massa folhada", "folhear", "dobras da massa"),
        dificuldade=5,
    ),
    Tecnica(
        "massa_podre",
        "Massa podre / torta",
        CategoriaTecnica.MASSAS,
        ("massa podre", "massa de torta", "forre a forma com a massa"),
        dificuldade=3,
    ),
    # --- molhos ---
    Tecnica(
        "bechamel",
        "Molho béchamel",
        CategoriaTecnica.MOLHOS,
        ("bechamel", "molho branco", "roux"),
        dificuldade=3,
        pergunta="A senhora sabe fazer molho branco (béchamel)? Aquele da lasanha.",
    ),
    Tecnica("roux", "Roux", CategoriaTecnica.MOLHOS, ("roux", "manteiga e farinha"), dificuldade=3),
    Tecnica(
        "reducao",
        "Redução de molho",
        CategoriaTecnica.MOLHOS,
        ("reduza", "reducao", "ate encorpar", "apurar o molho"),
        dificuldade=3,
    ),
    Tecnica(
        "emulsao",
        "Emulsão / maionese",
        CategoriaTecnica.MOLHOS,
        ("emulsione", "maionese caseira", "fio de azeite batendo"),
        dificuldade=4,
    ),
    Tecnica(
        "molho_tomate",
        "Molho de tomate caseiro",
        CategoriaTecnica.MOLHOS,
        ("molho de tomate", "tomate pelado", "passata"),
        pressuposta=True,
        dificuldade=2,
    ),
    # --- carnes ---
    Tecnica(
        "ponto_carne",
        "Pontos de carne",
        CategoriaTecnica.CARNES,
        ("ao ponto", "mal passado", "bem passado", "ponto da carne"),
        contexto=(
            "carne",
            "bife",
            "file",
            "picanha",
            "alcatra",
            "maminha",
            "contrafile",
            "hamburguer",
            "costela",
            "lombo",
            "cordeiro",
            "steak",
        ),
        dificuldade=3,
        pergunta="A senhora se vira bem com ponto de carne, como mal passado e ao ponto?",
    ),
    Tecnica(
        "selar",
        "Selar carne",
        CategoriaTecnica.CARNES,
        ("sele a carne", "selar", "dourar dos dois lados"),
        dificuldade=2,
    ),
    Tecnica(
        "braseado",
        "Braseado / cozimento lento",
        CategoriaTecnica.CARNES,
        ("braseado", "cozinhe lentamente", "fogo baixo por 2 horas", "desmanchando"),
        dificuldade=3,
    ),
    Tecnica(
        "desossar",
        "Desossar",
        CategoriaTecnica.CARNES,
        ("desosse", "desossar", "retire o osso"),
        dificuldade=4,
    ),
    Tecnica(
        "limpar_peixe",
        "Limpar peixe",
        CategoriaTecnica.CARNES,
        ("limpe o peixe", "escame", "file de peixe fresco"),
        dificuldade=4,
    ),
    # --- confeitaria ---
    Tecnica(
        "ponto_caramelo",
        "Ponto de caramelo",
        CategoriaTecnica.CONFEITARIA,
        ("caramelo", "ponto de caramelo", "acucar derretido", "calda ambar"),
        dificuldade=4,
        pergunta="A senhora já fez calda de caramelo? Aquela que queima fácil se distrair.",
    ),
    Tecnica(
        "ponto_calda",
        "Ponto de calda",
        CategoriaTecnica.CONFEITARIA,
        ("ponto de fio", "ponto de bala", "calda em ponto"),
        contexto=("calda", "acucar", "caramelo", "xarope", "doce", "leite condensado"),
        dificuldade=4,
    ),
    Tecnica(
        "merengue",
        "Merengue / claras em neve",
        CategoriaTecnica.CONFEITARIA,
        ("claras em neve", "merengue", "suspiro", "picos firmes"),
        dificuldade=3,
    ),
    Tecnica(
        "ganache",
        "Ganache",
        CategoriaTecnica.CONFEITARIA,
        ("ganache", "chocolate com creme de leite"),
        dificuldade=2,
    ),
    Tecnica(
        "temperagem",
        "Temperagem de chocolate",
        CategoriaTecnica.CONFEITARIA,
        (
            "temperar o chocolate",
            "tempere o chocolate",
            "temperagem",
            "choque termico do chocolate",
        ),
        dificuldade=5,
        pergunta="A senhora já temperou chocolate? É aquele processo de esfriar e esquentar.",
    ),
    Tecnica(
        "brigadeiro",
        "Brigadeiro / doce de panela",
        CategoriaTecnica.CONFEITARIA,
        ("brigadeiro", "desgrudar do fundo da panela", "beijinho"),
        pressuposta=True,
        dificuldade=1,
    ),
    Tecnica(
        "bolo_simples",
        "Bolo caseiro",
        CategoriaTecnica.CONFEITARIA,
        ("massa de bolo", "bata os ovos com o acucar"),
        pressuposta=True,
        dificuldade=2,
    ),
    # --- avançadas ---
    Tecnica(
        "sous_vide",
        "Sous vide",
        CategoriaTecnica.AVANCADA,
        ("sous vide", "vacuo a 60"),
        dificuldade=5,
    ),
    Tecnica("defumar", "Defumar", CategoriaTecnica.AVANCADA, ("defume", "defumado"), dificuldade=5),
    Tecnica("flambar", "Flambar", CategoriaTecnica.AVANCADA, ("flambe", "flambar"), dificuldade=4),
    Tecnica(
        "confit",
        "Confit",
        CategoriaTecnica.AVANCADA,
        ("confit", "cozido na propria gordura"),
        dificuldade=4,
    ),
)

TECNICAS_POR_ID: Final[dict[str, Tecnica]] = {t.id: t for t in TECNICAS}


# --------------------------------------------------------------------------- #
# Detecção determinística no texto da receita
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Deteccao:
    """O que foi encontrado no texto, e o trecho que provocou o achado."""

    id: str
    nome: str
    evidencia: str
    """O trecho literal da receita que denunciou a exigência. Sem isso não há
    como a Dona Maria contestar, e ela tem que poder contestar."""


@dataclass(slots=True)
class ResultadoDeteccao:
    equipamentos: list[Deteccao] = field(default_factory=list)
    tecnicas: list[Deteccao] = field(default_factory=list)

    @property
    def ids_equipamentos(self) -> frozenset[str]:
        return frozenset(d.id for d in self.equipamentos)

    @property
    def ids_tecnicas(self) -> frozenset[str]:
        return frozenset(d.id for d in self.tecnicas)


def detectar(texto: str, *, contexto: str | None = None) -> ResultadoDeteccao:
    """Varre o texto de uma receita atrás de equipamentos e técnicas conhecidos.

    Determinístico e barato: resolve o caso óbvio sem gastar token de LLM.
    O que escapar daqui é trabalho do extrator estruturado, e o que ele
    devolver tem que ser um id desta mesma tabela.

    `contexto` é onde as palavras de contexto das técnicas são procuradas; sem
    ele, é o próprio `texto`. Serve a quem varre um passo de cada vez: "deixe ao
    ponto" num passo e "bife" no nome da receita são a mesma exigência de ponto
    de carne que a receita inteira já acusa.

    >>> r = detectar("Leve ao forno preaquecido a 180 C e asse por 40 minutos")
    >>> "forno" in r.ids_equipamentos
    True
    """
    normalizado = _normalizar(texto)
    onde_procurar_contexto = normalizado if contexto is None else _normalizar(contexto)
    resultado = ResultadoDeteccao()

    for equipamento in EQUIPAMENTOS:
        achado = _primeiro_padrao(normalizado, equipamento.padroes, exceto=TIRADO_DE)
        if achado is None and equipamento.indicios:
            achado = _primeiro_indicio(normalizado, equipamento)
        if achado:
            resultado.equipamentos.append(Deteccao(equipamento.id, equipamento.nome, achado))

    for tecnica in TECNICAS:
        if tecnica.contexto and not _primeiro_padrao(onde_procurar_contexto, tecnica.contexto):
            continue
        if achado := _primeiro_padrao(normalizado, tecnica.padroes):
            resultado.tecnicas.append(Deteccao(tecnica.id, tecnica.nome, achado))

    return resultado


#: O que, logo antes, diz que o aparelho sai de cena: "retire do forno", "tire o
#: frango da geladeira", "desligue o fogo", "fora da geladeira". O aparelho
#: citado assim não é exigência do passo. O passo a passo usa a mesma regra.
TIRADO_DE: Final = re.compile(
    r"(?:(?<![a-z])(?:retire|tire|remova)\s+(?:[a-z0-9-]+\s+){0,3}?(?:do|da|dos|das)"
    r"|(?<![a-z])fora\s+(?:do|da|dos|das)"
    r"|(?<![a-z])(?:desligue|apague)(?:\s+(?:o|a))?)\s+$"
)
#: Quanto do texto antes da palavra a regra acima olha.
OLHAR_ANTES: Final = 40

#: O fim de uma frase, para os indícios que valem frase a frase.
_FIM_DA_FRASE = re.compile(r"[.;!?]")


def _primeiro_padrao(
    texto_normalizado: str, padroes: tuple[str, ...], *, exceto: re.Pattern[str] | None = None
) -> str | None:
    """Devolve o primeiro padrão encontrado, com um pedaço do contexto ao redor.

    Palavra inteira, nunca pedaço de palavra: "asse" achado dentro de "passe"
    transformava "passe o frango no tempero" em receita de forno. Com `exceto`,
    pula o achado que vem logo depois dela ("retire do forno").
    """
    for padrao in padroes:
        for casou in re.finditer(
            rf"(?<![a-z0-9]){re.escape(padrao)}(?![a-z0-9])", texto_normalizado
        ):
            pos = casou.start()
            if exceto is not None and exceto.search(
                texto_normalizado[max(0, pos - OLHAR_ANTES) : pos]
            ):
                continue
            inicio = max(0, pos - 25)
            fim = min(len(texto_normalizado), pos + len(padrao) + 25)
            trecho = texto_normalizado[inicio:fim].strip()
            return f"...{trecho}..." if inicio > 0 else f"{trecho}..."
    return None


def _primeiro_indicio(texto_normalizado: str, equipamento: Equipamento) -> str | None:
    """O primeiro indício do equipamento, frase a frase, fora das frases de outro aparelho."""
    for frase in _FIM_DA_FRASE.split(texto_normalizado):
        if equipamento.outros_aparelhos and _primeiro_padrao(frase, equipamento.outros_aparelhos):
            continue
        if achado := _primeiro_padrao(frase, equipamento.indicios, exceto=TIRADO_DE):
            return achado
    return None


_ESPACOS = re.compile(r"\s+")


def _normalizar(texto: str) -> str:
    """Minúsculas, sem acento, espaços colapsados, para o `find` ser previsível."""
    decomposto = unicodedata.normalize("NFD", texto.lower())
    sem_acento = "".join(c for c in decomposto if unicodedata.category(c) != "Mn")
    return _ESPACOS.sub(" ", sem_acento)


def equipamento(id_: str) -> Equipamento:
    """Busca por id, com erro claro quando o vocabulário é violado."""
    if id_ not in EQUIPAMENTOS_POR_ID:
        raise VocabularioDesconhecido("equipamento", id_, tuple(EQUIPAMENTOS_POR_ID))
    return EQUIPAMENTOS_POR_ID[id_]


def tecnica(id_: str) -> Tecnica:
    """Busca por id, com erro claro quando o vocabulário é violado."""
    if id_ not in TECNICAS_POR_ID:
        raise VocabularioDesconhecido("técnica", id_, tuple(TECNICAS_POR_ID))
    return TECNICAS_POR_ID[id_]


__all__ = [
    "EQUIPAMENTOS",
    "EQUIPAMENTOS_POR_ID",
    "OLHAR_ANTES",
    "TECNICAS",
    "TECNICAS_POR_ID",
    "TIRADO_DE",
    "CategoriaEquipamento",
    "CategoriaTecnica",
    "Deteccao",
    "Equipamento",
    "ResultadoDeteccao",
    "Tecnica",
    "detectar",
    "equipamento",
    "tecnica",
]
