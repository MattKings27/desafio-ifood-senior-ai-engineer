"""A pauta da descoberta de receitas: o que procurar na internet, pela despensa dela.

A descoberta automática roda em segundo plano: a plataforma pede ao agente
que procure receitas na internet, e cada página entra no catálogo pelo
servidor (`buscar_receita_na_web`). O que procurar não fica a critério do
modelo: sai daqui, só com dados do motor, sem modelo nenhum no meio.

**Por onde começar.** Por dois caminhos, nesta ordem. Primeiro, os pratos
clássicos do dia a dia que a despensa dela já cobre (`PRATOS_CLASSICOS`): o
feijão tropeiro, o escondidinho de carne moída, a farofa de bacon. Procurar só
pelo item mais caro trazia receita que pede compra (salmão com alcaparras,
feijão com cominho), e nenhuma dava para fazer; o prato clássico feito com o
que ela tem é o que costuma sair sem compra nenhuma. Depois, o dinheiro
parado: os itens da despensa em que ela mais pagou e que nenhuma receita do
catálogo (nem das que estão em avaliação) usa ainda. Se esses não bastam, entram
os maiores investimentos dela, mesmo os que já têm receita. Os itens que vão em
quase todo prato (sal, açúcar, óleo e azeite) não viram busca: procurar
receita por eles não aponta para nada.

**Como se procura.** O prato é procurado pelo nome ("receita de feijão
tropeiro"); o item, por "receita com" e o nome dele como se fala numa receita:
"carne moída", e não "Carne moída (patinho)". Os nomes dos 37 itens da
planilha estão escritos à mão aqui; o item que ela acrescentou é procurado pelo
nome que ela deu, sem o que estiver entre parênteses.

**O que não precisa ser lido de novo.** Os endereços que já estão no catálogo
vão na pauta, e a ferramenta que traz a página também os recusa sem buscar.

A cada descoberta a pauta muda sozinha: o prato que entrou no catálogo sai da
pauta, a receita que entrou passa a usar os itens dela, e a próxima busca
começa pelo próximo prato e pelo próximo dinheiro parado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

from mise.catalogo import chave_do_nome, id_da_receita
from mise.despensa_json import receitas_por_item

if TYPE_CHECKING:
    from mise.despensa import Despensa, Ingrediente
    from mise.mcp_server import Sessao
    from mise.receita import Receita

#: Quantas pesquisas na internet uma descoberta faz, no máximo.
MAXIMO_DE_BUSCAS: Final = 8
#: Quantas buscas a pauta tenta montar, quando a despensa tem itens para isso: os
#: pratos clássicos e, depois deles, pelo menos uma busca pelo dinheiro dela.
MINIMO_DE_BUSCAS: Final = 5
#: Quantas páginas de receita uma descoberta lê, no máximo.
MAXIMO_DE_PAGINAS: Final = 20
#: Quantos endereços conhecidos a pauta lista (os mais recentes primeiro).
MAXIMO_DE_URLS_CONHECIDAS: Final = 300
#: Quantas das buscas vão para pratos clássicos que a despensa dela cobre: metade.
MAXIMO_DE_PRATOS: Final = 4
#: Quantas páginas cada pesquisa traz, no máximo: as leituras divididas entre as buscas,
#: para a primeira pesquisa não gastar as leituras das outras. A divisão é arredondada
#: para cima (20 páginas em 8 buscas dão 3 por busca), senão as buscas nunca chegariam
#: ao total de páginas.
PAGINAS_POR_BUSCA: Final = -(-MAXIMO_DE_PAGINAS // MAXIMO_DE_BUSCAS)

#: Os itens que vão em quase todo prato: procurar receita por eles não aponta para nada.
BASICOS: Final = frozenset({"sal", "acucar", "oleo-de-soja", "azeite-de-oliva-extra-virgem"})

#: Como cada item da planilha aparece numa receita, para a busca na internet.
TERMOS_DA_PLANILHA: Final[dict[str, str]] = {
    "arroz-branco-tipo-1": "arroz",
    "feijao-carioquinha": "feijão carioca",
    "feijao-preto": "feijão preto",
    "peito-de-frango": "peito de frango",
    "carne-moida-patinho": "carne moída",
    "carne-de-panela-acem": "acém",
    "miolo-de-alcatra": "alcatra",
    "bacon": "bacon",
    "ovos": "ovos",
    "farinha-de-trigo": "farinha de trigo",
    "farinha-de-mandioca": "farinha de mandioca",
    "macarrao-espaguete": "espaguete",
    "polenta-fuba": "fubá",
    "batata": "batata",
    "queijo-mussarela": "mussarela",
    "queijo-parmesao-ralado": "parmesão",
    "tomate": "tomate",
    "cebola": "cebola",
    "alho": "alho",
    "oleo-de-soja": "óleo de soja",
    "manteiga": "manteiga",
    "sal": "sal",
    "acucar": "açúcar",
    "leite-integral": "leite",
    "couve": "couve",
    "salsinha-cheiro-verde": "cheiro-verde",
    "caldo-de-carne-tempero": "caldo de carne",
    "acafrao-em-po-curcuma": "açafrão",
    "alcaparras": "alcaparras",
    "amendoa-fatiada": "amêndoas",
    "chantilly": "chantilly",
    "leite-ninho-em-po": "leite em pó",
    "cobertura-de-chocolate": "cobertura de chocolate",
    "azeite-de-oliva-extra-virgem": "azeite",
    "aceto-balsamico": "aceto balsâmico",
    "canela-em-po": "canela",
    "adocante-liquido": "adoçante",
}

#: Os sites brasileiros de receita mais visitados que publicam a receita em dado
#: estruturado (`schema.org/Recipe` em JSON-LD), que é o que o servidor lê. A
#: pauta os entrega para a busca preferir essas páginas: página sem dado
#: estruturado é recusada pelo servidor e gasta à toa uma das leituras da rodada.
#: A lista é curada à mão e só orienta a escolha; quem decide se a página
#: serve continua sendo o servidor, ao ler.
SITES_POPULARES: Final[tuple[str, ...]] = (
    # O maior acervo de receitas de quem cozinha em casa, com ingredientes e
    # quantidades em JSON-LD.
    "tudogostoso.com.br",
    # Receitas dos programas da Globo (Ana Maria Braga, Rita Lobo e outros).
    "receitas.globo.com",
    # Receitas testadas pela cozinha experimental da Nestlé.
    "receitasnestle.com.br",
    # O site da Rita Lobo: receita testada, com rendimento e tempo.
    "panelinha.com.br",
    # O Guia da Cozinha, das revistas de receita da editora Alto Astral.
    "guiadacozinha.com.br",
    # Receitas do dia a dia, com foto e rendimento declarados.
    "receiteria.com.br",
    # Um dos acervos mais antigos da internet brasileira.
    "cybercook.com.br",
    # Acervo grande de receitas simples, em português do Brasil.
    "tudoreceitas.com",
)


@dataclass(frozen=True, slots=True)
class PratoClassico:
    """Um prato do dia a dia brasileiro e os itens da planilha que fazem a base dele."""

    nome: str
    #: Os ids dos itens da planilha (`categorias.DA_PLANILHA`) sem os quais o prato não sai.
    itens: tuple[str, ...]

    @property
    def busca(self) -> str:
        return f"receita de {self.nome}"


#: Um mapa curado à mão, da despensa para os pratos clássicos que ela cobre sem
#: compra, ou com uma compra pequena. Cada prato traz os itens da planilha que
#: fazem a base dele; o sal, o óleo, o azeite e os temperos que vão a gosto não
#: contam. O prato só entra na pauta quando todos os itens da base estão na
#: despensa dela, com estoque: a escolha sai da despensa, não do modelo. O mapa
#: só orienta a busca. Quem decide se a receita dá para fazer é o portão, lendo
#: a página de verdade que a pesquisa trouxe, linha por linha, contra a despensa
#: e a cozinha dela; a receita que pede o que ela não tem mostra a compra. O
#: modelo nunca escreve o catálogo. A ordem é a da lista.
PRATOS_CLASSICOS: Final[tuple[PratoClassico, ...]] = (
    PratoClassico(
        "feijão tropeiro",
        (
            "feijao-carioquinha",
            "bacon",
            "farinha-de-mandioca",
            "ovos",
            "couve",
            "cebola",
            "alho",
        ),
    ),
    PratoClassico(
        "escondidinho de carne moída",
        ("carne-moida-patinho", "batata", "queijo-mussarela", "leite-integral", "manteiga"),
    ),
    PratoClassico("farofa de bacon", ("farinha-de-mandioca", "bacon", "cebola")),
    PratoClassico("polenta com queijo", ("polenta-fuba", "queijo-parmesao-ralado", "manteiga")),
    PratoClassico("purê de batata", ("batata", "leite-integral", "manteiga")),
    PratoClassico("frango acebolado", ("peito-de-frango", "cebola", "alho")),
    PratoClassico("bife acebolado", ("miolo-de-alcatra", "cebola", "alho")),
    PratoClassico("macarrão alho e óleo", ("macarrao-espaguete", "alho")),
    PratoClassico("omelete de queijo", ("ovos", "queijo-mussarela")),
    PratoClassico("couve refogada", ("couve", "alho")),
    PratoClassico("carne moída refogada", ("carne-moida-patinho", "cebola", "alho", "tomate")),
    PratoClassico(
        "arroz com frango",
        ("arroz-branco-tipo-1", "peito-de-frango", "cebola", "alho", "tomate"),
    ),
    PratoClassico(
        "carne de panela com batata",
        ("carne-de-panela-acem", "batata", "cebola", "alho", "tomate"),
    ),
    PratoClassico(
        "espaguete à carbonara",
        ("macarrao-espaguete", "bacon", "ovos", "queijo-parmesao-ralado"),
    ),
    PratoClassico(
        "galinhada",
        ("arroz-branco-tipo-1", "peito-de-frango", "acafrao-em-po-curcuma", "cebola", "alho"),
    ),
    PratoClassico("tutu de feijão", ("feijao-carioquinha", "farinha-de-mandioca", "bacon", "alho")),
    PratoClassico("caldo de feijão", ("feijao-carioquinha", "bacon", "cebola", "alho")),
    PratoClassico("picadinho de carne", ("carne-de-panela-acem", "cebola", "alho", "tomate")),
    PratoClassico(
        "bolinho de arroz",
        ("arroz-branco-tipo-1", "ovos", "farinha-de-trigo", "queijo-parmesao-ralado"),
    ),
    PratoClassico("macarrão ao sugo", ("macarrao-espaguete", "tomate", "cebola", "alho")),
    PratoClassico(
        "arroz doce",
        ("arroz-branco-tipo-1", "leite-integral", "acucar", "canela-em-po"),
    ),
)

_ENTRE_PARENTESES: Final = re.compile(r"\s*\([^)]*\)")


class MotivoDaPauta(StrEnum):
    """Por que um item entrou na pauta."""

    SEM_RECEITA = "sem_receita"
    """Ela pagou por ele e nenhuma receita o usa ainda: é o dinheiro parado."""
    MAIOR_INVESTIMENTO = "maior_investimento"
    """Já tem receita, mas está entre os itens em que ela mais pagou."""


@dataclass(frozen=True, slots=True)
class ItemDaPauta:
    """Um item da despensa a procurar, com o termo da busca e o motivo."""

    item: Ingrediente
    termo: str
    motivo: MotivoDaPauta
    receitas_que_usam: int

    @property
    def busca(self) -> str:
        return f"receita com {self.termo}"

    def para_json(self) -> dict[str, Any]:
        from mise.serializacao import _reais  # noqa: PLC0415

        pago = self.item.preco_pago
        if self.motivo is MotivoDaPauta.SEM_RECEITA:
            motivo_texto = f"{pago} pagos, e nenhuma receita usa ainda"
        else:
            quantas = self.receitas_que_usam
            motivo_texto = (
                f"{pago} pagos; já entra em {quantas} {'receita' if quantas == 1 else 'receitas'}"
            )
        return {
            "item_id": self.item.id,
            "ingrediente": self.item.nome,
            "termo": self.termo,
            "pago": _reais(pago),
            "receitas_que_usam": self.receitas_que_usam,
            "motivo": self.motivo.value,
            "motivo_texto": motivo_texto,
        }


@dataclass(frozen=True, slots=True)
class PratoDaPauta:
    """Um prato clássico a procurar: a base inteira dele está na despensa dela."""

    prato: PratoClassico
    itens: tuple[Ingrediente, ...]

    @property
    def busca(self) -> str:
        return self.prato.busca

    def para_json(self) -> dict[str, Any]:
        nomes = [item.nome for item in self.itens]
        return {
            "prato": self.prato.nome,
            "busca": self.busca,
            "itens_da_despensa": nomes,
            "motivo_texto": (
                f"a despensa dela tem a base: {_lista([n[:1].lower() + n[1:] for n in nomes])}"
            ),
        }


def _lista(partes: list[str]) -> str:
    """ "a, b e c": a lista como se fala."""
    if len(partes) <= 1:
        return "".join(partes)
    return f"{', '.join(partes[:-1])} e {partes[-1]}"


def termo_de_busca(item: Ingrediente) -> str:
    """O item como se fala numa receita: o da planilha escrito à mão, ou o nome dela."""
    escrito = TERMOS_DA_PLANILHA.get(item.id)
    if escrito is not None:
        return escrito
    sem_parenteses = _ENTRE_PARENTESES.sub("", item.nome)
    return " ".join(sem_parenteses.split()).lower() or item.nome.strip().lower()


def receitas_conhecidas(sessao: Sessao) -> dict[str, Receita]:
    """As receitas do catálogo e as que estão em avaliação, uma vez cada, pelo id."""
    receitas = {id_da_receita(r): r for r in sessao.candidatas.values()}
    receitas.update({g.slug: g.receita for g in sessao.catalogo.listar()})
    return receitas


def pratos_da_pauta(despensa: Despensa, receitas: dict[str, Receita]) -> list[PratoDaPauta]:
    """Os pratos clássicos a procurar, na ordem de `PRATOS_CLASSICOS`, até `MAXIMO_DE_PRATOS`.

    Entra o prato cuja base inteira está na despensa dela, com estoque. Sai o
    que já tem receita conhecida (no catálogo ou em avaliação) com o nome dele
    no nome da receita ("Feijão tropeiro mineiro" é feijão tropeiro): a próxima
    descoberta procura o próximo prato.
    """
    conhecidos = [chave_do_nome(receita.nome) for receita in receitas.values()]
    pauta: list[PratoDaPauta] = []
    for prato in PRATOS_CLASSICOS:
        if len(pauta) >= MAXIMO_DE_PRATOS:
            break
        itens = [despensa.por_id(id_) for id_ in prato.itens]
        base = [item for item in itens if item is not None and item.estoque.valor > 0]
        if len(base) < len(prato.itens):
            continue
        chave = chave_do_nome(prato.nome)
        if any(chave in nome for nome in conhecidos):
            continue
        pauta.append(PratoDaPauta(prato, tuple(base)))
    return pauta


def itens_da_pauta(
    despensa: Despensa,
    receitas: dict[str, Receita],
    *,
    vagas: int = MAXIMO_DE_BUSCAS,
    minimo: int = MINIMO_DE_BUSCAS,
) -> list[ItemDaPauta]:
    """Os itens a procurar, na ordem: o dinheiro parado primeiro, depois os maiores gastos.

    Só entra item com o preço que ela pagou e com estoque: sem preço não se sabe
    quanto está parado, e o que acabou não está parado em lugar nenhum. `vagas`
    são as buscas que sobram depois dos pratos clássicos; os maiores gastos só
    entram até a pauta chegar a `minimo` buscas de item.
    """
    usos = receitas_por_item(despensa, receitas)
    candidatos = [
        item
        for item in despensa.por_valor()
        if item.preco_informado
        and item.preco_pago.valor > 0
        and item.estoque.valor > 0
        and item.id not in BASICOS
    ]
    pauta: list[ItemDaPauta] = []
    termos: set[str] = set()

    def acrescentar(item: Ingrediente, motivo: MotivoDaPauta) -> None:
        termo = termo_de_busca(item)
        if termo in termos or len(pauta) >= vagas:
            return
        termos.add(termo)
        pauta.append(ItemDaPauta(item, termo, motivo, len(usos.get(item.nome, []))))

    for item in candidatos:
        if not usos.get(item.nome):
            acrescentar(item, MotivoDaPauta.SEM_RECEITA)
    for item in candidatos:
        if len(pauta) >= min(minimo, vagas):
            break
        if usos.get(item.nome):
            acrescentar(item, MotivoDaPauta.MAIOR_INVESTIMENTO)
    return pauta


def _sites(urls: list[str]) -> list[str]:
    """Os sites de onde o servidor já leu receita, pelo endereço canônico, sem repetir."""
    return list(dict.fromkeys(url.split("/", 1)[0] for url in urls if url))


def _texto_da_pauta(pratos: int, parados: int, maiores: int) -> str:
    """ "Separei 8 buscas: 4 por pratos clássicos que a despensa dela já cobre e 4 pelo..."."""
    total = pratos + parados + maiores
    separei = f"Separei {total} {'busca' if total == 1 else 'buscas'}"
    motivos = [
        (pratos, "por pratos clássicos que a despensa dela já cobre"),
        (parados, "pelo dinheiro parado sem receita"),
        (maiores, "pelos itens em que ela mais gastou"),
    ]
    presentes = [(quantas, motivo) for quantas, motivo in motivos if quantas]
    if len(presentes) == 1:
        sozinho = {
            "pelo dinheiro parado sem receita": (
                "pelos itens em que mais dinheiro está parado sem receita"
            ),
        }
        motivo = presentes[0][1]
        return f"{separei} {sozinho.get(motivo, motivo)}."
    return f"{separei}: {_lista([f'{quantas} {motivo}' for quantas, motivo in presentes])}."


def montar_pauta(sessao: Sessao) -> dict[str, Any]:
    """A resposta de `pauta_de_descoberta`: o que procurar, o que pular e os limites."""
    guardadas = sessao.catalogo.listar()
    urls = [g.url_canonica for g in guardadas if g.url_canonica]
    receitas = receitas_conhecidas(sessao)
    pratos = pratos_da_pauta(sessao.despensa, receitas)
    pauta = itens_da_pauta(
        sessao.despensa,
        receitas,
        vagas=MAXIMO_DE_BUSCAS - len(pratos),
        minimo=max(0, MINIMO_DE_BUSCAS - len(pratos)),
    )
    buscas = [prato.busca for prato in pratos] + [item.busca for item in pauta]
    limites = {
        "buscas": MAXIMO_DE_BUSCAS,
        "paginas": MAXIMO_DE_PAGINAS,
        "paginas_por_busca": PAGINAS_POR_BUSCA,
    }
    base = {
        "pratos_para_procurar": [prato.para_json() for prato in pratos],
        "itens_para_procurar": [item.para_json() for item in pauta],
        "buscas": buscas,
        "urls_conhecidas": urls[:MAXIMO_DE_URLS_CONHECIDAS],
        "sites_que_ja_funcionaram": _sites(urls),
        "sites_populares": list(SITES_POPULARES),
        "limites": limites,
    }
    if not buscas:
        return {
            "disponivel": False,
            **base,
            "texto": "A despensa não tem item com preço e estoque para orientar a busca.",
            "orientacao": "Não procure receitas agora: não há por onde começar.",
        }
    parados = sum(1 for item in pauta if item.motivo is MotivoDaPauta.SEM_RECEITA)
    return {
        "disponivel": True,
        **base,
        "texto": _texto_da_pauta(len(pratos), parados, len(pauta) - parados),
        "orientacao": (
            f"Faça no máximo {MAXIMO_DE_BUSCAS} pesquisas com web_search, uma para cada texto "
            f"de 'buscas', na ordem, e traga no máximo {MAXIMO_DE_PAGINAS} páginas de uma "
            f"receita cada com buscar_receita_na_web, até {PAGINAS_POR_BUSCA} de cada "
            "pesquisa, pulando os endereços de 'urls_conhecidas'. Entre os resultados, prefira "
            "primeiro as páginas dos sites de 'sites_populares' e depois as dos sites de "
            "'sites_que_ja_funcionaram'."
        ),
    }


__all__ = [
    "BASICOS",
    "MAXIMO_DE_BUSCAS",
    "MAXIMO_DE_PAGINAS",
    "MAXIMO_DE_PRATOS",
    "MAXIMO_DE_URLS_CONHECIDAS",
    "MINIMO_DE_BUSCAS",
    "PAGINAS_POR_BUSCA",
    "PRATOS_CLASSICOS",
    "SITES_POPULARES",
    "TERMOS_DA_PLANILHA",
    "ItemDaPauta",
    "MotivoDaPauta",
    "PratoClassico",
    "PratoDaPauta",
    "itens_da_pauta",
    "montar_pauta",
    "pratos_da_pauta",
    "receitas_conhecidas",
    "termo_de_busca",
]
