"""Concilia a plataforma com a planilha da Dona Maria, item por item, sem arredondar a conta.

A planilha é lida crua, com o openpyxl, nas duas abas (`Despensa` e `Precos`),
sem passar pelo motor: a conta de referência é feita aqui, de novo, por outro
caminho. Para cada um dos itens, confere o que a plataforma mostra:

- o nome;
- o estoque e a unidade (na unidade-base: "1 balde 2kg" são 2 kg);
- a quantidade comprada e a unidade da compra ("balde 2kg", "un 500ml");
- o total pago;
- o custo por unidade, total pago ÷ quantidade comprada depois de normalizar a
  unidade. A embalagem sem peso declarado (a cobertura de chocolate, "1 un")
  não tem custo inventado nem vira pergunta para ela: o peso vem estimado pela
  página de um supermercado, e a conta diz que é estimativa, com a fonte.

E confere o total pago (R$ 663,39) e os R$ 80,00 dos complementos. Com o estado
recém-restaurado, confere também que a cozinha não tem resposta dela (só o que
toda cozinha tem, suposto), que o cardápio, as decisões, as compras, os gostos,
os preços informados, as receitas em avaliação e as conversas estão vazios.

Por padrão, a plataforma roda aqui mesmo, num dossiê novo em pasta temporária:
a API em processo, e o motor por baixo dela, conferido em Decimal. Com `--api`,
confere a API que está no ar (só leitura, só GET).

    mise/.venv/bin/python scripts/conciliar_planilha.py
    mise/.venv/bin/python scripts/conciliar_planilha.py --api http://127.0.0.1:8777

Sai com 1 se qualquer coisa divergir, e diz o quê.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Final
from urllib.parse import quote

import openpyxl

RAIZ: Final = Path(__file__).resolve().parents[1]
PLANILHA: Final = RAIZ / "dados" / "despensa_dona_maria.xlsx"

#: O que a planilha da Dona Maria soma, e o que ela tem para os complementos.
TOTAL_PAGO: Final = Decimal("663.39")
ORCAMENTO: Final = Decimal("80.00")

ABA_DO_ESTOQUE: Final = "Despensa"
ABA_DOS_PRECOS: Final = "Precos"
CABECALHO_DO_ESTOQUE: Final = ("Ingrediente", "Quantidade em estoque", "Unidade")
CABECALHO_DOS_PRECOS: Final = (
    "Ingrediente",
    "Quantidade comprada",
    "Unidade",
    "Preço total pago (R$)",
)

#: A unidade simples: quanto vale na unidade-base, e qual é a base.
_SIMPLES: Final[dict[str, tuple[Decimal, str]]] = {
    "kg": (Decimal(1), "kg"),
    "g": (Decimal("0.001"), "kg"),
    "l": (Decimal(1), "L"),
    "ml": (Decimal("0.001"), "L"),
    "un": (Decimal(1), "un"),
}

#: "balde 2kg", "un 500ml": a embalagem e o que vem nela.
_EMBALAGEM: Final = re.compile(
    r"^(?P<embalagem>[^\d\s]+)\s*(?P<quanto>\d+(?:[.,]\d+)?)\s*(?P<unidade>kg|g|l|ml)$",
    re.IGNORECASE,
)

#: "1 balde de 2 kg por R$ 82,00", "30 unidades por R$ 24,00", "200 g por R$ 2,16".
_COMPRADO: Final = re.compile(
    r"^(?P<quanto>\d+(?:\.\d{3})*(?:,\d+)?)\s+(?P<resto>.+?)\s+por\s+(?P<pago>R\$\s*[\d.,]+)$"
)
_CONTEUDO_NO_TEXTO: Final = re.compile(
    r"de\s+(?P<quanto>\d+(?:,\d+)?)\s*(?P<unidade>kg|g|L|ml)$"
)


# --------------------------------------------------------------------------- #
# A planilha crua e a conta de referência                                      #
# --------------------------------------------------------------------------- #


def _decimal(valor: object) -> Decimal:
    """O número da célula sem o ruído do float: 24.9 é 24,90, e não 24,899999."""
    if isinstance(valor, bool) or not isinstance(valor, int | float | Decimal):
        raise TypeError(f"célula sem número: {valor!r}")
    return Decimal(str(valor))


def reais(valor: Decimal) -> str:
    """ "R$ 1.234,56", com arredondamento comercial nos centavos."""
    centavos = valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    inteiro, decimal = f"{abs(centavos):.2f}".split(".")
    milhar = f"{int(inteiro):,}".replace(",", ".")
    return f"{'-' if centavos < 0 else ''}R$ {milhar},{decimal}"


def numero(valor: Decimal) -> str:
    """ "1,5", "0,3", "30": como a tela escreve uma quantidade."""
    return f"{valor.normalize():f}".replace(".", ",")


@dataclass(frozen=True, slots=True)
class Unidade:
    """O rótulo da planilha, normalizado: quanto uma unidade vale na base."""

    rotulo: str
    fator: Decimal
    base: str
    #: "un" sem o conteúdo: a peça, sem saber quanto pesa.
    peca: bool


def interpretar(rotulo: str) -> Unidade:
    """ "kg", "L", "un", "balde 2kg", "un 500ml": o fator até a unidade-base."""
    limpo = " ".join(str(rotulo).split())
    chave = limpo.lower()
    if chave in _SIMPLES:
        fator, base = _SIMPLES[chave]
        return Unidade(limpo, fator, base, peca=chave == "un")
    achado = _EMBALAGEM.fullmatch(chave)
    if achado is None:
        raise ValueError(f"unidade que não sei ler: {rotulo!r}")
    fator, base = _SIMPLES[achado["unidade"].lower()]
    quanto = Decimal(achado["quanto"].replace(",", "."))
    return Unidade(limpo, quanto * fator, base, peca=False)


@dataclass(frozen=True, slots=True)
class LinhaDaPlanilha:
    """Um item como está nas duas abas, com a conta de referência."""

    nome: str
    estoque: Decimal
    unidade_do_estoque: Unidade
    comprado: Decimal
    unidade_da_compra: Unidade
    pago: Decimal

    @property
    def estoque_na_base(self) -> Decimal:
        return self.estoque * self.unidade_do_estoque.fator

    @property
    def comprado_na_base(self) -> Decimal:
        return self.comprado * self.unidade_da_compra.fator

    @property
    def sem_peso(self) -> bool:
        """Uma peça só, sem o peso: é embalagem, e o custo por quilo é uma pergunta."""
        return self.unidade_da_compra.peca and self.comprado == 1

    @property
    def custo(self) -> Decimal | None:
        """Total pago ÷ quantidade comprada na unidade-base; `None` quando é pergunta."""
        if self.sem_peso:
            return None
        return self.pago / self.comprado_na_base

    @property
    def custo_texto(self) -> str | None:
        custo = self.custo
        return (
            None if custo is None else f"{reais(custo)}/{self.unidade_da_compra.base}"
        )


def _linhas(aba: Any, cabecalho: Sequence[str]) -> list[tuple[Any, ...]]:
    linhas = [tuple(linha) for linha in aba.iter_rows(values_only=True)]
    if not linhas or tuple(linhas[0][: len(cabecalho)]) != tuple(cabecalho):
        raise ValueError(f"a aba {aba.title!r} não tem o cabeçalho {cabecalho}")
    return [linha for linha in linhas[1:] if any(c is not None for c in linha)]


def ler_planilha(caminho: Path = PLANILHA) -> list[LinhaDaPlanilha]:
    """As duas abas, cruzadas pelo nome, como estão no arquivo."""
    livro = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    try:
        estoque = _linhas(livro[ABA_DO_ESTOQUE], CABECALHO_DO_ESTOQUE)
        precos = {
            linha[0]: linha
            for linha in _linhas(livro[ABA_DOS_PRECOS], CABECALHO_DOS_PRECOS)
        }
    finally:
        livro.close()
    saida = []
    for nome, quanto, rotulo in (linha[:3] for linha in estoque):
        if nome not in precos:
            raise ValueError(f"{nome!r} está no estoque e não nos preços")
        _, comprado, rotulo_da_compra, pago = precos[nome][:4]
        saida.append(
            LinhaDaPlanilha(
                nome=str(nome),
                estoque=_decimal(quanto),
                unidade_do_estoque=interpretar(rotulo),
                comprado=_decimal(comprado),
                unidade_da_compra=interpretar(rotulo_da_compra),
                pago=_decimal(pago),
            )
        )
    if len(precos) != len(saida):
        raise ValueError("a aba de preços tem item que o estoque não tem")
    return saida


# --------------------------------------------------------------------------- #
# De onde vem o que a plataforma mostra                                        #
# --------------------------------------------------------------------------- #


class ErroDaFonte(RuntimeError):
    """A plataforma não respondeu o que devia (fora do ar, rota que falhou)."""


@dataclass
class Fonte:
    """Como pedir uma rota da API: `pedir("/api/despensa")` devolve o JSON."""

    descricao: str
    pedir: Callable[[str], Any]
    #: A sessão do motor, quando a API roda aqui: permite conferir a conta em Decimal.
    sessao: Any = None
    #: O cliente da API em processo, para quem precisa escrever antes de conferir (os testes).
    cliente: Any = None

    def dados(self, rota: str) -> Any:
        corpo = self.pedir(rota)
        if isinstance(corpo, dict) and "ok" in corpo and "dados" in corpo:
            if not corpo["ok"]:
                raise ErroDaFonte(f"{rota}: {corpo.get('erro')}")
            return corpo["dados"]
        return corpo


def fonte_da_api(url: str) -> Fonte:
    """A API no ar, só com GET: nada é gravado."""
    raiz = url.rstrip("/")

    def pedir(rota: str) -> Any:
        try:
            with urllib.request.urlopen(f"{raiz}{rota}", timeout=30) as resposta:
                return json.loads(resposta.read().decode("utf-8"))
        except OSError as erro:
            raise ErroDaFonte(f"não consegui ler {raiz}{rota}: {erro}") from erro

    return Fonte(f"a API em {raiz}", pedir)


@contextmanager
def fonte_em_processo(planilha: Path = PLANILHA) -> Iterator[Fonte]:
    """A plataforma inteira aqui mesmo, num dossiê novo: a API em processo e o motor."""
    # O cliente em processo chama com `Host: testserver`, que a API só aceita listado.
    hosts = [h for h in os.environ.get("MISE_HOSTS", "").split(",") if h.strip()]
    ambiente = {
        "MISE_PLANILHA": str(planilha),
        "SABOR_DESCOBERTA": "desligada",
        "SABOR_VETORIZADOR": "ngramas",
        "MISE_HOSTS": ",".join(dict.fromkeys([*hosts, "testserver"])),
    }
    antes = {
        chave: os.environ.get(chave)
        for chave in [*ambiente, "MISE_DOSSIE", "MISE_AUDITORIA"]
    }
    with tempfile.TemporaryDirectory(prefix="conciliar-") as pasta:
        os.environ.update(ambiente, MISE_DOSSIE=str(Path(pasta) / "dossie.db"))
        os.environ.pop("MISE_AUDITORIA", None)
        try:
            from fastapi.testclient import TestClient
            from gateway.http import criar_app

            app = criar_app()
            with TestClient(app) as cliente:
                yield Fonte(
                    "a plataforma em processo, num dossiê novo",
                    lambda rota: cliente.get(rota).json(),
                    sessao=app.state.sessao,
                    cliente=cliente,
                )
            app.state.sessao.dossie.fechar()
            app.state.conversa.banco.fechar()
        finally:
            for chave, valor in antes.items():
                if valor is None:
                    os.environ.pop(chave, None)
                else:
                    os.environ[chave] = valor


# --------------------------------------------------------------------------- #
# A conciliação                                                                #
# --------------------------------------------------------------------------- #


@dataclass
class Relatorio:
    """O que bateu e o que divergiu, para imprimir e para o código de saída."""

    itens: list[str] = field(default_factory=list)
    resumo: list[str] = field(default_factory=list)
    divergencias: list[str] = field(default_factory=list)

    def conferir(self, certo: bool, divergencia: str) -> bool:
        if not certo:
            self.divergencias.append(divergencia)
        return certo

    @property
    def ok(self) -> bool:
        return not self.divergencias

    def texto(self, origem: str) -> str:
        partes = [
            "Conciliação com a planilha (dados/despensa_dona_maria.xlsx, lida crua)",
            f"Plataforma: {origem}",
            "",
            *self.itens,
            "",
            *self.resumo,
            "",
        ]
        if self.ok:
            partes.append("0 divergências: a plataforma mostra exatamente a planilha.")
        else:
            quantas = len(self.divergencias)
            partes.append(
                f"{quantas} {'divergência' if quantas == 1 else 'divergências'}:"
            )
            partes.extend(f"  - {d}" for d in self.divergencias)
        return "\n".join(partes)


def _base(quanto: Decimal, unidade: str) -> Decimal:
    fator, _ = _SIMPLES[unidade.lower()]
    return quanto * fator


def comprado_do_texto(texto: str) -> tuple[Decimal, Decimal] | None:
    """ "1 balde de 2 kg por R$ 82,00" em (2 kg na base, 82,00); `None` se não dá para ler."""
    achado = _COMPRADO.fullmatch(texto.strip())
    if achado is None:
        return None
    quanto = Decimal(achado["quanto"].replace(".", "").replace(",", "."))
    resto = achado["resto"]
    pago = Decimal(
        achado["pago"].removeprefix("R$").strip().replace(".", "").replace(",", ".")
    )
    if (conteudo := _CONTEUDO_NO_TEXTO.search(resto)) is not None:
        por_embalagem = _base(
            Decimal(conteudo["quanto"].replace(",", ".")), conteudo["unidade"]
        )
        return quanto * por_embalagem, pago
    unidade = resto.split()[0]
    if unidade.lower() in _SIMPLES:
        return _base(quanto, unidade), pago
    # "30 unidades", "1 embalagem": peças.
    return quanto, pago


def _conferir_item(
    relatorio: Relatorio,
    linha: LinhaDaPlanilha,
    item: dict[str, Any] | None,
    detalhe: dict[str, Any] | None,
    pendencias: dict[str, dict[str, Any]],
) -> None:
    nome = linha.nome
    if item is None or detalhe is None:
        relatorio.conferir(False, f"{nome}: não aparece na despensa da plataforma")
        return
    antes = len(relatorio.divergencias)
    base = linha.unidade_da_compra.base
    if linha.sem_peso:
        # A embalagem sem peso na planilha vale pelo peso estimado: o estoque é
        # contado em embalagens, e o texto diz quantas.
        relatorio.conferir(
            f"({numero(linha.estoque)} embalage" in str(item.get("estoque_texto")),
            f"{nome}: estoque {item.get('estoque_texto')!r}, e a planilha diz "
            f"{numero(linha.estoque)} {linha.unidade_do_estoque.rotulo}",
        )
    else:
        relatorio.conferir(
            Decimal(str(item["estoque"])) == linha.estoque_na_base
            and item["unidade"] == base,
            f"{nome}: estoque {item['estoque']} {item['unidade']}, e a planilha diz "
            f"{numero(linha.estoque)} {linha.unidade_do_estoque.rotulo} = "
            f"{numero(linha.estoque_na_base)} {base}",
        )
    relatorio.conferir(
        detalhe.get("unidade_compra_rotulo") == linha.unidade_da_compra.rotulo,
        f"{nome}: unidade da compra {detalhe.get('unidade_compra_rotulo')!r}, e a planilha diz "
        f"{linha.unidade_da_compra.rotulo!r}",
    )
    lido = comprado_do_texto(str(detalhe.get("comprado_texto", "")))
    relatorio.conferir(
        lido == (linha.comprado_na_base, linha.pago),
        f"{nome}: a compra aparece como {detalhe.get('comprado_texto')!r}, e a planilha diz "
        f"{numero(linha.comprado)} {linha.unidade_da_compra.rotulo} por {reais(linha.pago)}",
    )
    pago = item.get("pago") or {}
    relatorio.conferir(
        Decimal(str(pago.get("valor"))) == linha.pago
        and pago.get("texto") == reais(linha.pago),
        f"{nome}: pago {pago.get('texto')}, e a planilha diz {reais(linha.pago)}",
    )
    custo = item.get("custo_unitario")
    if linha.sem_peso:
        derivacao = str(item.get("derivacao") or "")
        relatorio.conferir(
            custo is not None
            and item.get("pendente") is False
            and item["id"] not in pendencias
            and "estimativa" in derivacao
            and "a senhora pode corrigir" in derivacao,
            f"{nome}: sem o peso na planilha, o peso vem estimado com a fonte e sem pergunta, "
            f"e a plataforma mostra {custo} ({derivacao})",
        )
        conta = (
            "sem peso declarado: peso estimado pela página do supermercado, com a fonte"
        )
    else:
        esperado = linha.custo
        assert esperado is not None
        relatorio.conferir(
            custo is not None
            and custo.get("texto") == linha.custo_texto
            and Decimal(str(custo.get("valor")))
            == esperado.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            f"{nome}: custo {custo and custo.get('texto')}, e a conta da planilha dá "
            f"{reais(linha.pago)} ÷ {numero(linha.comprado_na_base)} {base} = {linha.custo_texto}",
        )
        conta = f"{reais(linha.pago)} ÷ {numero(linha.comprado_na_base)} {base} = {linha.custo_texto}"
    marca = "ok " if len(relatorio.divergencias) == antes else "ERR"
    relatorio.itens.append(
        f"  {marca} {nome}: {numero(linha.estoque)} {linha.unidade_do_estoque.rotulo} em estoque; "
        f"comprou {numero(linha.comprado)} {linha.unidade_da_compra.rotulo} por "
        f"{reais(linha.pago)}; {conta}"
    )


def _conferir_no_motor(
    relatorio: Relatorio, planilha: list[LinhaDaPlanilha], sessao: Any
) -> None:
    """A mesma conta no motor, em Decimal e sem arredondar nada."""
    despensa = sessao.despensa
    for linha in planilha:
        ingrediente = despensa.get(linha.nome)
        if ingrediente is None:
            relatorio.conferir(False, f"{linha.nome}: o motor não tem este item")
            continue
        relatorio.conferir(
            ingrediente.estoque.valor == linha.estoque_na_base
            and ingrediente.preco_pago.valor == linha.pago
            and ingrediente.quantidade_bruta == linha.comprado,
            f"{linha.nome}: no motor, estoque {ingrediente.estoque}, pago {ingrediente.preco_pago}",
        )
        if linha.custo is not None:
            relatorio.conferir(
                ingrediente.custo.valor.valor == linha.custo,
                f"{linha.nome}: no motor, custo {ingrediente.custo.valor.valor} e a conta exata "
                f"é {linha.custo}",
            )
    relatorio.conferir(
        despensa.total_investido.valor
        == sum((linha.pago for linha in planilha), Decimal(0)),
        f"no motor, total investido {despensa.total_investido}",
    )


def _conferir_o_resto(
    relatorio: Relatorio, fonte: Fonte, lista: dict[str, Any]
) -> None:
    """Os totais, os R$ 80,00, e o estado de quem acabou de chegar: sem nada dela ainda."""
    orcamento = lista["orcamento"]
    relatorio.conferir(
        Decimal(str(orcamento["inicial"]["valor"])) == ORCAMENTO
        and Decimal(str(orcamento["restante"]["valor"])) == ORCAMENTO
        and Decimal(str(orcamento["gasto"]["valor"])) == 0,
        f"complementos: {orcamento['texto']} (o certo é nada gasto, restam {reais(ORCAMENTO)})",
    )
    relatorio.resumo.append(
        f"Complementos: {orcamento['inicial']['texto']}, restam {orcamento['restante']['texto']}"
    )
    relatorio.conferir(
        orcamento["compras"] == [],
        f"compras com os complementos: {len(orcamento['compras'])}, e o certo é nenhuma",
    )
    cozinha = fonte.dados("/api/perfil")
    itens = [*cozinha["equipamentos"], *cozinha["tecnicas"]]
    dela = [i["nome"] for i in itens if i["atualizado_por"] is not None or i["nao_sei"]]
    restricoes = [
        campo
        for campo, r in cozinha["restricoes"].items()
        if r["valor"] is not None or r["nao_sei"] or r["atualizado_por"] is not None
    ]
    relatorio.conferir(
        cozinha["respondidos"] == 0 and not dela and not restricoes,
        f"cozinha com resposta dela: {', '.join([*dela, *restricoes]) or cozinha['resumo']}",
    )
    relatorio.resumo.append(
        f"Cozinha: {cozinha['resumo']} (nenhuma resposta dela; o que está como tem é suposto)"
    )
    cardapio = fonte.dados("/api/cardapio")
    relatorio.conferir(
        cardapio["pratos"] == [] and cardapio["historico"] == [],
        f"cardápio com pratos ({len(cardapio['pratos'])}) e decisões ({len(cardapio['historico'])})",
    )
    relatorio.resumo.append(f"Cardápio: {cardapio['resumo']['texto']}; nenhuma decisão")
    tudo = fonte.dados("/api/exportacao")
    for chave, rotulo in (
        ("despensa_eventos", "mudanças na despensa"),
        ("cozinha_eventos", "respostas sobre a cozinha"),
        ("decisoes", "decisões"),
        ("gostos", "gostos"),
        ("precos_de_mercado", "preços que ela informou"),
        ("receitas_em_avaliacao", "receitas em avaliação"),
        ("compras", "compras"),
    ):
        quantas = len(tudo.get(chave) or [])
        relatorio.conferir(quantas == 0, f"{rotulo}: {quantas}, e o certo é nenhuma")
    conversas = fonte.dados("/api/conversas")
    relatorio.conferir(
        conversas.get("conversas") == [],
        f"conversas guardadas: {len(conversas.get('conversas') or [])}, e o certo é nenhuma",
    )
    relatorio.resumo.append(
        "Compras, decisões, gostos, preços informados, receitas em avaliação e conversas: nenhum"
    )


def conciliar(fonte: Fonte, planilha: Path = PLANILHA) -> Relatorio:
    """Compara a planilha crua com o que a plataforma mostra; o relatório diz o que divergiu."""
    relatorio = Relatorio()
    linhas = ler_planilha(planilha)
    lista = fonte.dados("/api/despensa?ordem=nome")
    por_nome = {item["nome"]: item for item in lista["itens"]}
    pendencias = {p["id"]: p for p in lista["pendencias"]}
    for linha in linhas:
        item = por_nome.get(linha.nome)
        detalhe = (
            fonte.dados(f"/api/despensa/itens/{quote(item['id'])}") if item else None
        )
        _conferir_item(relatorio, linha, item, detalhe, pendencias)
    a_mais = sorted(set(por_nome) - {linha.nome for linha in linhas})
    relatorio.conferir(not a_mais, f"itens que a planilha não tem: {', '.join(a_mais)}")
    relatorio.conferir(
        lista["total_itens"] == len(linhas),
        f"a plataforma conta {lista['total_itens']} itens, e a planilha tem {len(linhas)}",
    )
    soma = sum((linha.pago for linha in linhas), Decimal(0))
    relatorio.conferir(
        soma == TOTAL_PAGO, f"a planilha soma {reais(soma)}, e não {reais(TOTAL_PAGO)}"
    )
    total = lista["total_investido"]
    relatorio.conferir(
        Decimal(str(total["valor"])) == soma and total["texto"] == reais(soma),
        f"total pago na plataforma: {total['texto']}, e a planilha soma {reais(soma)}",
    )
    sem_peso = [linha.nome for linha in linhas if linha.sem_peso]
    relatorio.resumo.extend(
        [
            f"Itens: {len(linhas)} na planilha, {lista['total_itens']} na plataforma",
            f"Total pago: {total['texto']} (a planilha soma {reais(soma)})",
            "Sem peso declarado, com o peso estimado e a fonte no lugar da pergunta: "
            + (", ".join(sem_peso) or "nenhum"),
        ]
    )
    if fonte.sessao is not None:
        antes = len(relatorio.divergencias)
        _conferir_no_motor(relatorio, linhas, fonte.sessao)
        relatorio.resumo.append(
            "Motor: a mesma conta em Decimal, sem arredondar, "
            + ("bateu" if len(relatorio.divergencias) == antes else "divergiu")
        )
    _conferir_o_resto(relatorio, fonte, lista)
    return relatorio


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--planilha", type=Path, default=PLANILHA)
    parser.add_argument("--api", help="a API no ar, por exemplo http://127.0.0.1:8777")
    args = parser.parse_args(argv)
    try:
        if args.api:
            fonte = fonte_da_api(args.api)
            relatorio = conciliar(fonte, args.planilha)
        else:
            with fonte_em_processo(args.planilha) as fonte:
                relatorio = conciliar(fonte, args.planilha)
    except ErroDaFonte as erro:
        print(f"não consegui conciliar: {erro}", file=sys.stderr)
        return 1
    print(relatorio.texto(fonte.descricao))
    return 0 if relatorio.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
