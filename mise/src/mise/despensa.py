"""Leitura da planilha e derivação do custo unitário.

O desafio define o custo unitário como `preço total pago ÷ quantidade comprada`.
Tomada ao pé da letra, essa divisão produz números errados em 6 dos 37 itens,
porque a coluna `Unidade` mistura grandezas com embalagens:

    Alcaparras · 1 · "balde 2kg" · R$ 82,00

`82 ÷ 1 = 82` não é "R$ 82,00 por quilo" nem "por unidade de alcaparra": é
R$ 82,00 por balde, e o balde tem 2 kg. O custo correto é R$ 41,00/kg. A regra
do desafio continua valendo, apenas aplicada **depois** de normalizar a
unidade, não antes.

Um segundo caso é genuinamente indedutível:

    Cobertura de chocolate · 1 · "un" · R$ 79,90

Sabemos o custo por embalagem (R$ 79,90) mas não quanto ela pesa. Se a receita
pedir "200 g de cobertura", nenhuma conta da planilha resolve, e a Dona Maria
não é perguntada: o peso vem de uma fonte (`mise.embalagens`), dito como
estimativa, e ela corrige quando quiser. Sem fonte, o item fica sem custo por
quilo, e a receita que pede o peso dele fica de fora. Distinguimos isso de ovos
(`30 · "un" · R$ 24,00`), onde a unidade é o item em si e R$ 0,80/ovo é
exatamente o que a receita precisa. O sinal que separa os dois é a quantidade
comprada: **1** embalagem opaca contra **30** itens contados.

**A mesma conta para a planilha e para o que ela muda.** Cada item nasce de uma
`LinhaDaDespensa` (o que ela tem, em que unidade, quanto comprou e pagou) por
`montar_ingrediente`. A planilha é uma lista dessas linhas (`carregar_linhas`);
um item que ela acrescenta ou corrige na tela é outra linha, e passa pela mesma
função. Não existe um segundo lugar onde o custo unitário é derivado.

**Ids estáveis.** O item da planilha é o slug do nome (`alcaparras`,
`carne-moida-patinho`); o que ela acrescenta é `item-<8 hex>`. O nome continua
sendo a chave do motor (cotações e compras usam o nome canônico), e por isso um
item não muda de nome: corrigir é mudar quantidade, unidade ou preço.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Final

from mise import categorias
from mise.dinheiro import Dinheiro
from mise.embalagens import EmbalagemDeReferencia, embalagem_de_referencia
from mise.erros import (
    ErroDeDados,
    ErroDeUso,
    MassaDesconhecida,
    PlanilhaInvalida,
    PrecoDesconhecido,
    QuantidadeInvalida,
    UnidadeNaoNormalizavel,
)
from mise.unidades import (
    Dimensao,
    Quantidade,
    UnidadeCompra,
    interpretar_unidade_compra,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

ABA_DESPENSA: Final = "Despensa"
ABA_PRECOS: Final = "Precos"

COLUNAS_DESPENSA: Final = ("Ingrediente", "Quantidade em estoque", "Unidade")
COLUNAS_PRECOS: Final = ("Ingrediente", "Quantidade comprada", "Unidade", "Preço total pago (R$)")

#: Unidades que são a própria medida, sem embalagem: "500 g" é conversão, não palpite.
_UNIDADES_PURAS: Final = frozenset({"kg", "g", "mg", "l", "ml"})


def id_do_item(nome: str) -> str:
    """O id estável de um item da planilha: o slug do nome.

    >>> id_do_item("Carne moída (patinho)")
    'carne-moida-patinho'
    """
    return categorias.id_do_nome(nome)


class OrigemDoItem(StrEnum):
    """De onde veio o item. Só o que ela comprou com os complementos mexe nos R$ 80,00."""

    PLANILHA = "planilha"
    """Um dos itens da planilha que ela entregou. Editar nunca mexe no orçamento."""

    JA_TINHA = "ja_tinha"
    """Ela acrescentou algo que já tinha em casa. Não mexe no orçamento."""

    ORCAMENTO = "orcamento"
    """Ela comprou com os complementos: saiu dos R$ 80,00, e tirar o item devolve."""


class TipoDePendencia(StrEnum):
    """O que falta para o custo de um item ser dedutível, e como a tela pergunta."""

    EMBALAGEM = "conteudo_embalagem"
    """Embalagem única sem o peso ou o volume declarado."""

    PRECO = "preco_pago"
    """Item que ela já tinha e de que não disse quanto pagou."""


@dataclass(frozen=True, slots=True)
class LinhaDaDespensa:
    """Um item como ela o descreve: o que tem, em que unidade, quanto comprou e pagou.

    É a forma comum da linha da planilha (as duas abas já cruzadas) e do item que
    ela acrescenta ou corrige depois. `estoque` e `quantidade_comprada` estão na
    `unidade` da linha ("2" de "un 200g" são duas embalagens de 200 g).
    `preco_pago` é `None` quando ela não disse quanto pagou (o que já tinha em
    casa): o custo fica desconhecido e vira pergunta, nunca R$ 0,00.
    `conteudo_informado` marca a embalagem cujo peso ela mesma informou: a conta
    passa a existir, com confiança média.
    """

    nome: str
    estoque: Decimal
    unidade: str
    quantidade_comprada: Decimal
    preco_pago: Decimal | None
    id: str = ""
    categoria: str = ""
    origem: OrigemDoItem = OrigemDoItem.PLANILHA
    conteudo_informado: bool = False

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", id_do_item(self.nome))
        if not self.categoria:
            object.__setattr__(self, "categoria", categorias.do_item(self.id, self.nome).id)

    def com(self, **campos: object) -> LinhaDaDespensa:
        """A mesma linha com os campos trocados. O nome não se troca: é a chave do motor."""
        if "nome" in campos or "id" in campos:
            raise ErroDeUso(
                "o nome de um item não muda: cotações e compras usam o nome como chave",
                ingrediente=self.nome,
            )
        return replace(self, **campos)  # type: ignore[arg-type]


class Confianca(StrEnum):
    """Quanto confiamos no custo derivado."""

    ALTA = "alta"
    """Unidade-base explícita (`kg`, `L`) ou item contado: divisão direta."""

    MEDIA = "media"
    """Embalagem com conteúdo declarado no rótulo: normalizamos antes de dividir."""

    DESCONHECIDA = "desconhecida"
    """Não derivável a partir da planilha. Vira pergunta."""


@dataclass(frozen=True, slots=True)
class CustoUnitario:
    """Custo por unidade-base, com a conta que o produziu."""

    valor: Dinheiro
    dimensao: Dimensao
    derivacao: str
    confianca: Confianca

    def __str__(self) -> str:
        return f"{self.valor}/{self.dimensao.value}"


@dataclass(frozen=True, slots=True)
class Ingrediente:
    """Um item da despensa com preço e custo unitário derivado."""

    nome: str
    estoque: Quantidade
    comprado: Quantidade
    preco_pago: Dinheiro
    unidade_compra: UnidadeCompra
    custo: CustoUnitario
    quantidade_bruta: Decimal
    """A quantidade exatamente como escrita na planilha, antes de normalizar.

    Preservada porque a auditoria precisa reconstruir a linha original e porque
    o agente mostra à Dona Maria a diferença entre a conta ingênua e a correta.
    """
    linha: LinhaDaDespensa
    """A linha de onde o item saiu: é sobre ela que uma correção dela se aplica."""
    embalagem_estimada: EmbalagemDeReferencia | None = None
    """O peso da embalagem que a planilha não diz, estimado por uma página de supermercado."""

    @property
    def id(self) -> str:
        return self.linha.id

    @property
    def categoria(self) -> str:
        return self.linha.categoria

    @property
    def origem(self) -> OrigemDoItem:
        return self.linha.origem

    @property
    def preco_informado(self) -> bool:
        """Ela disse quanto pagou? Sem isso o custo é desconhecido, e não zero."""
        return self.linha.preco_pago is not None

    @property
    def dimensao(self) -> Dimensao:
        return self.custo.dimensao

    @property
    def custo_ingenuo(self) -> Dinheiro:
        """`preço ÷ quantidade` aplicado cru à planilha: o número **errado**.

        Existe para ser mostrado ao lado do correto, não para ser usado. Em 6
        dos 37 itens ele difere, e a diferença é o que justifica todo o módulo
        de normalização de unidades.
        """
        return self.preco_pago / self.quantidade_bruta

    @property
    def normalizacao_importou(self) -> bool:
        """True quando a conta ingênua daria um custo diferente do correto."""
        return self.custo_ingenuo.arredondado() != self.custo.valor.arredondado()

    @property
    def embalagem_opaca(self) -> bool:
        """Embalagem única cujo conteúdo não foi declarado.

        Custa-se por peça, mas qualquer receita que peça massa ou volume deste
        item precisa de uma pergunta à Dona Maria antes de virar CMV.
        """
        return self.unidade_compra.opaca and self.comprado.valor == 1

    def custo_de(self, quantidade: Quantidade) -> Dinheiro:
        """Custo de usar `quantidade` deste ingrediente.

        Levanta `MassaDesconhecida` quando a receita pede massa de um item cujo
        conteúdo por embalagem é desconhecido: preferimos recusar a estimar. E
        `PrecoDesconhecido` quando ela não disse quanto pagou: custo zero faria o
        prato parecer mais barato do que é.
        """
        if not self.preco_informado:
            raise PrecoDesconhecido(self.nome)
        if quantidade.dimensao is not self.dimensao:
            if self.embalagem_opaca:
                raise MassaDesconhecida(
                    self.nome, float(self.preco_pago.valor), self.unidade_compra.rotulo_original
                )
            raise UnidadeNaoNormalizavel(
                f"{quantidade.dimensao.value} (esperado {self.dimensao.value})", self.nome
            )
        return self.custo.valor * quantidade.valor


@dataclass(frozen=True, slots=True)
class Pendencia:
    """Algo que a planilha não resolve e que precisa da Dona Maria."""

    ingrediente: str
    motivo: str
    pergunta: str
    impacto: Dinheiro
    tipo: TipoDePendencia = TipoDePendencia.EMBALAGEM

    def __str__(self) -> str:
        return f"{self.ingrediente}: {self.motivo}"


@dataclass(slots=True)
class Despensa:
    """Catálogo normalizado da despensa, com custo e pendências.

    `itens` é indexado pelo nome, que é a chave do motor inteiro (casamento,
    cotação, compra). O id da tela (`por_id`) é outro índice sobre os mesmos
    itens.
    """

    itens: dict[str, Ingrediente] = field(default_factory=dict)
    pendencias: list[Pendencia] = field(default_factory=list)
    origem: Path | None = None

    def por_id(self, id_: str) -> Ingrediente | None:
        """O item pelo id da tela (`alcaparras`, `item-4f7a1c2e`), ou `None`."""
        return next((i for i in self.itens.values() if i.id == id_), None)

    def pendencia_de(self, nome: str) -> Pendencia | None:
        """A pendência do item, se houver."""
        return next((p for p in self.pendencias if p.ingrediente == nome), None)

    def fracao_de(self, item: Ingrediente) -> Decimal:
        """Quanto do que ela pagou está neste item. Despensa sem valor dá zero, e não erro."""
        total = self.total_investido.valor
        return item.preco_pago.valor / total if total else Decimal(0)

    def __len__(self) -> int:
        return len(self.itens)

    def __iter__(self) -> Iterator[Ingrediente]:
        return iter(self.itens.values())

    def __contains__(self, nome: str) -> bool:
        return nome in self.itens

    def __getitem__(self, nome: str) -> Ingrediente:
        return self.itens[nome]

    def get(self, nome: str) -> Ingrediente | None:
        return self.itens.get(nome)

    @property
    def total_investido(self) -> Dinheiro:
        """Quanto a Dona Maria já colocou na despensa."""
        total = Dinheiro.zero()
        for item in self.itens.values():
            total = total + item.preco_pago
        return total

    @property
    def nomes(self) -> tuple[str, ...]:
        return tuple(self.itens)

    def por_valor(self) -> list[Ingrediente]:
        """Itens ordenados por capital imobilizado, do maior para o menor."""
        return sorted(self.itens.values(), key=lambda i: i.preco_pago.valor, reverse=True)


# --------------------------------------------------------------------------- #
# Carregamento
# --------------------------------------------------------------------------- #


def carregar_despensa(caminho: str | Path) -> Despensa:
    """Lê a planilha, cruza as duas abas e deriva o custo unitário de cada item."""
    caminho = Path(caminho)
    return montar_despensa(carregar_linhas(caminho), origem=caminho)


def carregar_linhas(caminho: str | Path) -> list[LinhaDaDespensa]:
    """As linhas da planilha, com as duas abas cruzadas e conferidas, na ordem dela.

    Cada linha junta o estoque (aba `Despensa`) e a compra (aba `Precos`) do
    mesmo item, e leva o id (slug do nome) e a categoria. A unidade tem de ser a
    mesma nas duas abas: "2 L" no estoque e "2 ml" no preço não se cruzam.
    """
    caminho = Path(caminho)
    if not caminho.is_file():
        raise PlanilhaInvalida("arquivo não encontrado", str(caminho))

    estoque = _ler_aba_despensa(caminho)
    precos = _ler_aba_precos(caminho)

    faltando_preco = sorted(set(estoque) - set(precos))
    if faltando_preco:
        raise PlanilhaInvalida(
            f"{len(faltando_preco)} item(ns) da aba {ABA_DESPENSA!r} sem preço correspondente: "
            f"{', '.join(faltando_preco[:5])}",
            str(caminho),
        )

    linhas: list[LinhaDaDespensa] = []
    ids: dict[str, str] = {}
    for nome, (qtd_estoque, rotulo_estoque) in estoque.items():
        qtd_comprada, rotulo_compra, preco = precos[nome]
        # A unidade é interpretada antes do cruzamento: rótulo que ninguém lê é
        # erro da unidade, mesmo que as duas abas concordem nele.
        interpretar_unidade_compra(rotulo_compra)

        if _sem_espacos(rotulo_estoque) != _sem_espacos(rotulo_compra):
            raise PlanilhaInvalida(
                f"{nome!r} usa unidade {rotulo_estoque!r} no estoque e "
                f"{rotulo_compra!r} no preço; não dá para cruzar com segurança",
                str(caminho),
            )

        linha = LinhaDaDespensa(
            nome=nome,
            estoque=qtd_estoque,
            unidade=rotulo_compra,
            quantidade_comprada=qtd_comprada,
            preco_pago=preco,
        )
        if (outro := ids.get(linha.id)) is not None:
            raise PlanilhaInvalida(
                f"{outro!r} e {nome!r} dariam o mesmo id {linha.id!r}", str(caminho)
            )
        ids[linha.id] = nome
        linhas.append(linha)
    return linhas


def montar_despensa(linhas: list[LinhaDaDespensa], origem: Path | None = None) -> Despensa:
    """A despensa destas linhas, cada uma pela mesma conta de `montar_ingrediente`."""
    despensa = Despensa(origem=origem)
    for linha in linhas:
        ingrediente, pendencia = montar_ingrediente(linha)
        despensa.itens[ingrediente.nome] = ingrediente
        if pendencia is not None:
            despensa.pendencias.append(pendencia)
    return despensa


def montar_ingrediente(linha: LinhaDaDespensa) -> tuple[Ingrediente, Pendencia | None]:
    """O item e, se o custo não for dedutível, a pergunta que o destrava.

    É a única conta do custo unitário: a planilha e as mudanças dela passam por
    aqui. A unidade é interpretada, o preço é dividido **depois** de normalizar,
    e o que não dá para deduzir vira `Pendencia` em vez de número.
    """
    unidade = interpretar_unidade_compra(linha.unidade)
    if linha.quantidade_comprada <= 0:
        raise QuantidadeInvalida(
            linha.quantidade_comprada, f"quantidade comprada de {linha.nome!r}"
        )
    estimada = _embalagem_estimada(linha, unidade)
    if estimada is not None:
        unidade = UnidadeCompra(
            rotulo_original=unidade.rotulo_original,
            dimensao=estimada.conteudo.dimensao,
            conteudo_por_embalagem=estimada.conteudo,
            derivacao=estimada.texto(linha.nome, Dinheiro(linha.preco_pago or Decimal(0))),
        )
    pendencia: Pendencia | None
    if linha.preco_pago is None:
        custo, pendencia = _custo_sem_preco(linha.nome, unidade)
    else:
        custo, pendencia = _derivar_custo(
            linha.nome,
            unidade,
            linha.quantidade_comprada,
            linha.preco_pago,
            informado=linha.conteudo_informado,
            estimada=estimada,
        )
    ingrediente = Ingrediente(
        nome=linha.nome,
        estoque=_para_base(linha.estoque, unidade),
        comprado=Quantidade(linha.quantidade_comprada, Dimensao.CONTAGEM)
        if unidade.opaca
        else _para_base(linha.quantidade_comprada, unidade),
        preco_pago=Dinheiro(linha.preco_pago if linha.preco_pago is not None else Decimal(0)),
        unidade_compra=unidade,
        custo=custo,
        quantidade_bruta=linha.quantidade_comprada,
        linha=linha,
        embalagem_estimada=estimada,
    )
    return ingrediente, pendencia


def _embalagem_estimada(
    linha: LinhaDaDespensa, unidade: UnidadeCompra
) -> EmbalagemDeReferencia | None:
    """O peso estimado da embalagem única sem peso, quando uma página de supermercado diz."""
    if not unidade.opaca or linha.quantidade_comprada != 1 or linha.conteudo_informado:
        return None
    return embalagem_de_referencia(linha.nome)


def _custo_sem_preco(nome: str, unidade: UnidadeCompra) -> tuple[CustoUnitario, None]:
    """Item sem preço: o custo é desconhecido, e ninguém pergunta.

    Não vira pergunta: a receita que usa o item custa pelo preço de referência,
    dito como referência, ou fica de fora (`mise.viabilidade`). Ela diz o preço
    quando quiser, corrigindo o item.
    """
    del nome
    custo = CustoUnitario(
        valor=Dinheiro.zero(),
        dimensao=unidade.dimensao,
        derivacao="a senhora não disse quanto pagou; sem o preço, não dá para saber o custo",
        confianca=Confianca.DESCONHECIDA,
    )
    return custo, None


def _derivar_custo(
    nome: str,
    unidade: UnidadeCompra,
    quantidade_comprada: Decimal,
    preco_total: Decimal,
    *,
    informado: bool = False,
    estimada: EmbalagemDeReferencia | None = None,
) -> tuple[CustoUnitario, Pendencia | None]:
    """Aplica `preço ÷ quantidade` **depois** de normalizar a unidade.

    `informado` é a embalagem cujo peso ela mesma disse: a conta vale, mas com
    confiança média e escrita por inteiro, para ela ver de onde veio o número.
    """
    if quantidade_comprada <= 0:
        raise QuantidadeInvalida(quantidade_comprada, f"quantidade comprada de {nome!r}")

    # Embalagem opaca: custa-se por peça. Derivável para contagem, não para massa.
    if unidade.conteudo_por_embalagem is None:
        custo = CustoUnitario(
            valor=Dinheiro(preco_total / quantidade_comprada),
            dimensao=Dimensao.CONTAGEM,
            derivacao=(
                f"{Dinheiro(preco_total)} ÷ {_limpa(quantidade_comprada)} "
                f"{unidade.rotulo_original} = {Dinheiro(preco_total / quantidade_comprada)}/un"
            ),
            confianca=Confianca.ALTA,
        )
        pendencia = None
        if quantidade_comprada == 1:
            # Uma peça só: é uma embalagem, não uma contagem. Receitas vão pedir
            # massa. O peso não se pergunta: vem de uma fonte, ou fica sem custo
            # por quilo, e a receita que pede o peso fica de fora.
            custo = CustoUnitario(
                valor=custo.valor,
                dimensao=Dimensao.CONTAGEM,
                derivacao=custo.derivacao + " (peso da embalagem desconhecido)",
                confianca=Confianca.DESCONHECIDA,
            )
        return custo, pendencia

    # Unidade normalizável: converte para a base e divide.
    total_base = unidade.conteudo_por_embalagem.valor * quantidade_comprada
    if total_base <= 0:
        raise QuantidadeInvalida(total_base, f"conteúdo total de {nome!r}")

    por_base = Dinheiro(preco_total / total_base)
    pura = unidade.rotulo_original.strip().lower() in _UNIDADES_PURAS
    direta = (unidade.conteudo_por_embalagem.valor == 1 or pura) and not informado

    derivacao = (
        f"{Dinheiro(preco_total)} ÷ {_limpa(total_base)} {unidade.dimensao.value} "
        f"= {por_base}/{unidade.dimensao.value}"
    )
    if pura and unidade.conteudo_por_embalagem.valor != 1:
        # "500 g" é conversão de unidade, não embalagem: a conta diz só isso.
        derivacao = (
            f"{_limpa(quantidade_comprada)} {unidade.rotulo_original.strip()} "
            f"= {_limpa(total_base)} {unidade.dimensao.value}; " + derivacao
        )
    elif not direta:
        derivacao = (
            f"{_limpa(quantidade_comprada)} × {unidade.conteudo_por_embalagem} "
            f"= {_limpa(total_base)} {unidade.dimensao.value}; " + derivacao
        )
    if informado:
        derivacao += " (o peso da embalagem foi a senhora que informou)"
    if estimada is not None:
        derivacao += f"; o peso é {unidade.derivacao}"

    return (
        CustoUnitario(
            valor=por_base,
            dimensao=unidade.dimensao,
            derivacao=derivacao,
            confianca=Confianca.ALTA if direta and estimada is None else Confianca.MEDIA,
        ),
        None,
    )


def _para_base(quantidade: Decimal, unidade: UnidadeCompra) -> Quantidade:
    if unidade.conteudo_por_embalagem is None:
        return Quantidade(quantidade, Dimensao.CONTAGEM)
    return Quantidade(quantidade * unidade.conteudo_por_embalagem.valor, unidade.dimensao)


# --------------------------------------------------------------------------- #
# Leitura bruta das abas
# --------------------------------------------------------------------------- #


def _ler_aba_despensa(caminho: Path) -> dict[str, tuple[Decimal, str]]:
    resultado: dict[str, tuple[Decimal, str]] = {}
    for linha in _linhas(caminho, ABA_DESPENSA, COLUNAS_DESPENSA):
        nome = str(linha[0])
        resultado[nome] = (_decimal(linha[1], nome), str(linha[2]).strip())
    return resultado


def _ler_aba_precos(caminho: Path) -> dict[str, tuple[Decimal, str, Decimal]]:
    resultado: dict[str, tuple[Decimal, str, Decimal]] = {}
    for linha in _linhas(caminho, ABA_PRECOS, COLUNAS_PRECOS):
        nome = str(linha[0])
        resultado[nome] = (
            _decimal(linha[1], nome),
            str(linha[2]).strip(),
            _decimal(linha[3], f"preço de {nome}"),
        )
    return resultado


def _linhas(caminho: Path, aba: str, colunas: tuple[str, ...]) -> list[tuple[object, ...]]:
    """Lê uma aba validando o cabeçalho e ignorando linhas vazias."""
    import openpyxl  # noqa: PLC0415 (import tardio: openpyxl custa ~200ms)

    try:
        wb = openpyxl.load_workbook(caminho, data_only=True, read_only=True)
    except Exception as exc:
        raise PlanilhaInvalida(f"não foi possível abrir ({exc})", str(caminho)) from exc

    try:
        if aba not in wb.sheetnames:
            raise PlanilhaInvalida(
                f"aba {aba!r} não encontrada (existem: {', '.join(wb.sheetnames)})", str(caminho)
            )
        linhas = list(wb[aba].iter_rows(values_only=True))
    finally:
        wb.close()

    if not linhas:
        raise PlanilhaInvalida(f"aba {aba!r} está vazia", str(caminho))

    cabecalho = tuple(str(c).strip() if c is not None else "" for c in linhas[0][: len(colunas)])
    if cabecalho != colunas:
        raise PlanilhaInvalida(
            f"aba {aba!r} tem cabeçalho {cabecalho}, e o esperado é {colunas}", str(caminho)
        )

    corpo: list[tuple[object, ...]] = []
    vistos: set[str] = set()
    for linha in linhas[1:]:
        if not linha or linha[0] is None or not str(linha[0]).strip():
            continue
        nome = str(linha[0]).strip()
        if nome in vistos:
            raise PlanilhaInvalida(f"{nome!r} aparece duas vezes na aba {aba!r}", str(caminho))
        vistos.add(nome)
        corpo.append((nome, *linha[1 : len(colunas)]))

    if not corpo:
        raise PlanilhaInvalida(f"aba {aba!r} não tem linhas de dados", str(caminho))
    return corpo


def _decimal(valor: object, contexto: str) -> Decimal:
    if valor is None:
        raise PlanilhaInvalida(f"valor ausente em {contexto}")
    try:
        d = Decimal(str(valor).replace(",", "."))
    except Exception as exc:
        raise PlanilhaInvalida(f"valor não numérico {valor!r} em {contexto}") from exc
    if not d.is_finite() or d < 0:
        raise QuantidadeInvalida(valor, contexto)
    return d


def _sem_espacos(texto: str) -> str:
    return " ".join(texto.split()).lower()


def _limpa(valor: Decimal) -> str:
    """Como se escreve no Brasil: "0,5 kg", não "0.5 kg"."""
    n = valor.normalize()
    return (
        str(n.quantize(Decimal("1"))) if n == n.to_integral_value() else f"{n:f}".replace(".", ",")
    )


__all__ = [
    "Confianca",
    "CustoUnitario",
    "Despensa",
    "ErroDeDados",
    "Ingrediente",
    "LinhaDaDespensa",
    "OrigemDoItem",
    "Pendencia",
    "TipoDePendencia",
    "carregar_despensa",
    "carregar_linhas",
    "id_do_item",
    "montar_despensa",
    "montar_ingrediente",
]
