"""O cardápio dela: os pratos aceitos, o que chega para ela, o lucro e as decisões em frases.

`GET /api/cardapio` (a forma de `contratos/web/cardapio.json`), o card `decisao`
da conversa e a tela inicial leem daqui.

**O preço é dela; a conta é refeita.** O preço de cada prato é o que ela
escolheu ao aceitar, gravado na decisão. O custo da porção, o que chega para
ela depois da taxa e o lucro saem da despensa de agora: se o frango encareceu,
o lucro do cardápio acompanha. Quando a receita deixou de passar na conferência
e a conta não fecha, valem os números do dia do aceite, e o `aviso` diz isso.

**O histórico é o registro inteiro, em frases dela.** Cada decisão vira uma
frase ("A senhora tirou o arroz com frango do cardápio."), lida junto com a
anterior do mesmo prato: aceitar de novo com outro preço é "mudou o preço", e
recusar o que estava no cardápio é "tirou do cardápio". Desfazer grava uma
decisão nova que volta ao estado de antes e aponta a que desfez; a tela diz que
ela voltou atrás, e nada some do registro.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Final

from mise import receitas_json
from mise.catalogo import chave_do_nome, id_da_receita
from mise.despensa import id_do_item
from mise.despensa_json import dinheiro_json, quando_texto
from mise.dinheiro import Dinheiro
from mise.dossie import Canal, Decisao, RegistroDecisao
from mise.erros import Ausente, ErroDeUso, ErroMise
from mise.genero import falar
from mise.perfil import Gosto
from mise.preco import TAXA_PLATAFORMA, Cenario, preco_minimo

if TYPE_CHECKING:
    from datetime import datetime

    from mise.catalogo import ReceitaDoCatalogo
    from mise.dossie import OpiniaoSobrePrato
    from mise.mcp_server import Sessao
    from mise.receitas_json import LeituraDaReceita

#: A rota da tela do cardápio, e a do painel dos R$ 80,00.
ROTA_DO_CARDAPIO: Final = "/cardapio"
ROTA_DO_ORCAMENTO: Final = "/despensa#orcamento"

#: O que cada passo do histórico é, dito em uma ou duas palavras na tela.
TIPO_ROTULO: Final[Mapping[str, str]] = {
    "aceito": "Aceitou",
    "preco": "Mudou o preço",
    "retirado": "Tirou do cardápio",
    "recusado": "Recusou",
    "adiado": "Deixou para depois",
    "desfeito": "Voltou atrás",
}

#: Diferença de custo que conta como "mudou desde o aceite": meio centavo.
_MEIO_CENTAVO: Final = Decimal("0.005")

#: O controle de preço anda de 50 em 50 centavos e começa, no mínimo, em R$ 0,50.
PASSO_DO_CONTROLE: Final = Decimal("0.50")

#: O teto do controle é seis vezes o custo da porção (o ingrediente em 17% do preço).
_VEZES_O_CUSTO: Final = 6

#: "R$ 1.234,56" e "-R$ 0,03", como `Dinheiro.__str__` escreve.
_REAIS: Final = re.compile(r"^(-?)R\$\s*([\d.]+,\d{2})$")


# --------------------------------------------------------------------------- #
# Dinheiro e nomes
# --------------------------------------------------------------------------- #


def dinheiro_do_texto(texto: object) -> Dinheiro | None:
    """O valor gravado na decisão ("R$ 18,00") de volta em `Dinheiro`; `None` se não é valor."""
    if not isinstance(texto, str):
        return None
    achado = _REAIS.fullmatch(texto.strip())
    if achado is None:
        return None
    sinal, numero = achado.groups()
    try:
        valor = Decimal(numero.replace(".", "").replace(",", "."))
    except InvalidOperation:  # pragma: no cover (a expressão só deixa passar número)
        return None
    return Dinheiro(-valor if sinal else valor)


def o_prato(prato: str) -> str:
    """ "o arroz com frango"; sem saber o gênero, "o prato moqueca"."""
    nome = falar(prato)
    return nome.com_artigo() or f"o prato {nome.minusculo}"


def do_prato(prato: str) -> str:
    """ "do arroz com frango"; sem saber o gênero, "do prato moqueca"."""
    nome = falar(prato)
    return nome.contraido("de") or f"do prato {nome.minusculo}"


def _maiuscula(texto: str) -> str:
    return texto[:1].upper() + texto[1:]


# --------------------------------------------------------------------------- #
# As decisões, em frases
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Passo:
    """Uma decisão e a que estava valendo antes dela, do mesmo prato."""

    registro: RegistroDecisao
    anterior: RegistroDecisao | None

    @property
    def tipo(self) -> str:
        """`aceito`, `preco`, `retirado`, `recusado`, `adiado` ou `desfeito`."""
        registro, anterior = self.registro, self.anterior
        estava_no_cardapio = anterior is not None and anterior.decisao is Decisao.ACEITO
        if registro.desfaz is not None:
            return "desfeito"
        if registro.decisao is Decisao.ACEITO:
            return "preco" if estava_no_cardapio else "aceito"
        if registro.decisao is Decisao.RECUSADO:
            return "retirado" if estava_no_cardapio else "recusado"
        return "adiado"

    @property
    def preco(self) -> str | None:
        valor = self.registro.detalhes.get("preco")
        return valor if isinstance(valor, str) else None

    def texto(self) -> str:
        """A decisão como ela diria, com o motivo quando houve."""
        frase = _FRASES[self.tipo](self, self.registro.prato)
        motivo = self.registro.motivo.strip().rstrip(".")
        return f"{frase} O motivo: {motivo}." if motivo else frase


def _frase_do_desfeito(passo: Passo, prato: str) -> str:
    decisao = passo.registro.decisao
    if decisao is Decisao.ACEITO:
        preco = f", a {passo.preco}" if passo.preco else ""
        return f"A senhora voltou atrás: {o_prato(prato)} está de novo no cardápio{preco}."
    if decisao is Decisao.RECUSADO:
        return f"A senhora voltou atrás: {o_prato(prato)} fica fora do cardápio."
    return f"A senhora voltou atrás: {o_prato(prato)} fica para decidir depois."


def _frase_do_preco(passo: Passo, prato: str) -> str:
    antes = passo.anterior.detalhes.get("preco") if passo.anterior is not None else None
    de_antes = f" de {antes}" if isinstance(antes, str) else ""
    para = f" para {passo.preco}" if passo.preco else ""
    return f"A senhora mudou o preço {do_prato(prato)}{de_antes}{para}."


def _frase_do_aceite(passo: Passo, prato: str) -> str:
    preco = f" a {passo.preco}" if passo.preco else ""
    return f"A senhora aceitou {o_prato(prato)}{preco}."


def _frase_da_retirada(_passo: Passo, prato: str) -> str:
    return f"A senhora tirou {o_prato(prato)} do cardápio."


def _frase_da_recusa(_passo: Passo, prato: str) -> str:
    return f"A senhora disse que não quer {o_prato(prato)} no cardápio."


def _frase_do_adiado(_passo: Passo, prato: str) -> str:
    return f"A senhora deixou {o_prato(prato)} para decidir depois."


_FRASES: Final[Mapping[str, Callable[[Passo, str], str]]] = {
    "desfeito": _frase_do_desfeito,
    "aceito": _frase_do_aceite,
    "preco": _frase_do_preco,
    "retirado": _frase_da_retirada,
    "recusado": _frase_da_recusa,
    "adiado": _frase_do_adiado,
}


def passos(historico: Iterable[RegistroDecisao]) -> list[Passo]:
    """Cada decisão com a anterior do mesmo prato, na ordem em que foram gravadas."""
    ultima: dict[str, RegistroDecisao] = {}
    saida = []
    for registro in historico:
        chave = chave_do_nome(registro.prato)
        saida.append(Passo(registro, ultima.get(chave)))
        ultima[chave] = registro
    return saida


def texto_da_decisao(registro: RegistroDecisao, historico: Sequence[RegistroDecisao]) -> str:
    """A frase de uma decisão que acabou de ser gravada, lida contra o histórico do prato."""
    for passo in reversed(passos(historico)):
        if passo.registro.id == registro.id:
            return passo.texto()
    return Passo(registro, None).texto()


def pode_desfazer(passo: Passo, *, atual: bool) -> bool:
    """Só a decisão que vale hoje se desfaz, e não a que já é um voltar atrás."""
    if not atual or passo.registro.desfaz is not None:
        return False
    # Adiar o prato que nunca teve decisão já é o "sem decisão": não há o que desfazer.
    return not (passo.anterior is None and passo.registro.decisao is Decisao.ADIADO)


# --------------------------------------------------------------------------- #
# A receita de cada prato
# --------------------------------------------------------------------------- #


def guardada_do_prato(sessao: Sessao, prato: str) -> ReceitaDoCatalogo | None:
    """A receita do prato no catálogo (ou em avaliação, de antes do catálogo); `None` se não há."""
    em_avaliacao = sessao.dossie.candidata(prato)
    if em_avaliacao is not None:
        try:
            return receitas_json.guardada_por_slug(sessao, id_da_receita(em_avaliacao))
        except Ausente:  # pragma: no cover (a candidata sempre acha a si mesma)
            return receitas_json.de_antes_do_catalogo(em_avaliacao)
    return sessao.catalogo.por_nome(prato)


def leituras_dos_pratos(sessao: Sessao, pratos: Iterable[str]) -> dict[str, LeituraDaReceita]:
    """A leitura de agora da receita de cada prato (pela chave do nome), numa conferência só."""
    guardadas = {chave_do_nome(prato): guardada_do_prato(sessao, prato) for prato in pratos}
    achadas = [g for g in guardadas.values() if g is not None]
    por_slug = {leitura.slug: leitura for leitura in receitas_json.ler(sessao, achadas)}
    return {
        chave: por_slug[guardada.slug]
        for chave, guardada in guardadas.items()
        if guardada is not None and guardada.slug in por_slug
    }


def _custo_agora(leitura: LeituraDaReceita | None) -> Dinheiro | None:
    """O custo de uma porção com a despensa de agora; `None` se a conta não fecha hoje."""
    from mise.cmv import calcular  # noqa: PLC0415

    if leitura is None or not leitura.avaliacao.permite_precificar:
        return None
    try:
        return calcular(leitura.guardada.receita, leitura.avaliacao).para_precificar
    except ErroMise:
        return None


def rota_do_prato(leitura: LeituraDaReceita | None) -> str:
    """A receita do prato, ou o cardápio quando o prato não tem receita guardada."""
    return receitas_json.rota_da_receita(leitura.slug) if leitura else ROTA_DO_CARDAPIO


def _aviso(
    cenario: Cenario | None, custo_agora: Dinheiro | None, no_aceite: Dinheiro | None
) -> str | None:
    """O que ela precisa saber da conta de um prato: não fechou hoje, dá prejuízo ou mudou."""
    if cenario is None:
        return None
    if custo_agora is None:
        return (
            "Não consegui refazer a conta com a despensa de agora: os números são os do "
            "dia em que a senhora aceitou."
        )
    if cenario.da_prejuizo:
        perda = (-cenario.lucro).arredondado()
        minimo = preco_minimo(cenario.cmv).arredondado_para_cima()
        return (
            f"A {cenario.preco}, a senhora perde {perda} em cada porção. "
            f"O mínimo sem prejuízo é {minimo}."
        )
    if no_aceite is not None and abs(no_aceite.valor - custo_agora.valor) > _MEIO_CENTAVO:
        return (
            f"O custo da porção mudou desde que a senhora aceitou: era {no_aceite}, "
            f"agora é {custo_agora}."
        )
    return None


@dataclass(frozen=True, slots=True)
class PratoNoCardapio:
    """Um prato aceito, com o preço dela e a conta de agora."""

    nome: str
    aceite: RegistroDecisao
    leitura: LeituraDaReceita | None
    preco: Dinheiro | None
    cenario: Cenario | None
    aviso: str | None

    @classmethod
    def ler(cls, aceite: RegistroDecisao, leitura: LeituraDaReceita | None) -> PratoNoCardapio:
        preco = dinheiro_do_texto(aceite.detalhes.get("preco"))
        no_aceite = dinheiro_do_texto(aceite.detalhes.get("cmv_por_porcao"))
        agora = _custo_agora(leitura)
        custo = agora or no_aceite
        cenario = (
            Cenario("", "", preco, custo, TAXA_PLATAFORMA)
            if preco is not None and custo is not None
            else None
        )
        aviso = _aviso(cenario, agora, no_aceite)
        return cls(aceite.prato, aceite, leitura, preco, cenario, aviso)

    def json(self, agora: datetime) -> dict[str, Any]:
        leitura, cenario = self.leitura, self.cenario
        return {
            "slug": leitura.slug if leitura else id_do_item(self.nome),
            "prato": self.nome,
            "imagem": receitas_json.imagem_json(leitura.guardada) if leitura else None,
            "preco": dinheiro_json(self.preco) if self.preco is not None else None,
            "recebe": dinheiro_json(cenario.recebe) if cenario else None,
            "custo_porcao": dinheiro_json(cenario.cmv) if cenario else None,
            "lucro_porcao": dinheiro_json(cenario.lucro) if cenario else None,
            "derivacao": cenario.explicacao() if cenario else "",
            "da_prejuizo": bool(cenario and cenario.da_prejuizo),
            "aviso": self.aviso,
            "nota": (
                receitas_json.pontuacao_json(leitura.pontuacao, com_conta=False)
                if leitura
                else None
            ),
            "decidido_texto": quando_texto(self.aceite.registrado, agora),
            "notas": (leitura.estrelas.notas or None) if leitura else None,
            "rota": rota_do_prato(leitura),
        }


# --------------------------------------------------------------------------- #
# O cardápio inteiro
# --------------------------------------------------------------------------- #


def _atuais(historico: Iterable[RegistroDecisao]) -> dict[str, RegistroDecisao]:
    """A decisão que vale hoje de cada prato, pela chave do nome."""
    return {chave_do_nome(r.prato): r for r in historico}


def _pratos_aceitos(
    historico: Sequence[RegistroDecisao], leituras: Mapping[str, LeituraDaReceita]
) -> list[PratoNoCardapio]:
    aceitos = sorted(
        (r for r in _atuais(historico).values() if r.decisao is Decisao.ACEITO),
        key=lambda r: chave_do_nome(r.prato),
    )
    return [PratoNoCardapio.ler(r, leituras.get(chave_do_nome(r.prato))) for r in aceitos]


def _texto_do_orcamento(sessao: Sessao) -> str:
    estado = sessao.dossie.orcamento()
    if estado.gasto:
        return (
            f"{estado.gasto} dos {estado.inicial} já foram para complementos; "
            f"restam {estado.restante}."
        )
    return f"Nada gasto dos {estado.inicial} dos complementos ainda."


def _resumo(sessao: Sessao, pratos: Sequence[PratoNoCardapio]) -> dict[str, Any]:
    contas = [p.cenario for p in pratos if p.cenario is not None]
    precos = sum((c.preco for c in contas), Dinheiro.zero())
    lucros = sum((c.lucro for c in contas), Dinheiro.zero())
    if contas and precos.valor > 0:
        media: Dinheiro | None = precos / len(contas)
        margem_texto = f"{lucros.valor / precos.valor:.0%} de sobra depois da taxa e do ingrediente"
    else:
        media = None
        margem_texto = "sem prato com a conta pronta ainda"
    quantos = len(pratos)
    texto = (
        "nenhum prato no cardápio ainda"
        if quantos == 0
        else f"{quantos} {'prato' if quantos == 1 else 'pratos'} no cardápio"
    )
    return {
        "pratos": quantos,
        "preco_medio": dinheiro_json(media) if media is not None else None,
        "margem_media_texto": margem_texto,
        "orcamento_usado": dinheiro_json(sessao.dossie.orcamento().gasto),
        "orcamento_texto": _texto_do_orcamento(sessao),
        "orcamento_rota": ROTA_DO_ORCAMENTO,
        "texto": texto,
    }


def _quem_nao_quer(
    passos_do_historico: Sequence[Passo], gostos: Iterable[OpiniaoSobrePrato]
) -> list[tuple[datetime, str, str]]:
    """`(quando, prato, motivo)`: os recusados, os tirados e os que ela não gosta de fazer."""
    ultimos = {chave_do_nome(p.registro.prato): p for p in passos_do_historico}
    vistos: set[str] = set()
    entradas: list[tuple[datetime, str, str]] = []
    for chave, passo in ultimos.items():
        registro = passo.registro
        if registro.decisao is not Decisao.RECUSADO:
            continue
        padrao = "tirou do cardápio" if passo.tipo == "retirado" else "não quer no cardápio"
        vistos.add(chave)
        entradas.append((registro.registrado, registro.prato, registro.motivo.strip() or padrao))
    for opiniao in gostos:
        chave = chave_do_nome(opiniao.prato)
        impedimento = opiniao.impedimento.strip()
        if chave in vistos or not (opiniao.gosto is Gosto.NAO_GOSTA or impedimento):
            continue
        vistos.add(chave)
        entradas.append((opiniao.registrado, opiniao.prato, impedimento or "não gosta de fazer"))
    entradas.sort(key=lambda entrada: entrada[0], reverse=True)
    return entradas


def historico_json(
    passos_do_historico: Sequence[Passo], agora: datetime, rotas: Mapping[str, str]
) -> list[dict[str, Any]]:
    """As decisões da mais nova para a mais antiga, em frases."""
    atuais = {chave_do_nome(p.registro.prato): p.registro.id for p in passos_do_historico}
    saida = []
    for passo in reversed(passos_do_historico):
        registro = passo.registro
        chave = chave_do_nome(registro.prato)
        saida.append(
            {
                "id": registro.id,
                "prato": registro.prato,
                "tipo": passo.tipo,
                "tipo_rotulo": TIPO_ROTULO[passo.tipo],
                "texto_humano": passo.texto(),
                "quando_texto": quando_texto(registro.registrado, agora),
                "canal": registro.canal,
                "pode_desfazer": pode_desfazer(passo, atual=atuais[chave] == registro.id),
                "rota": rotas.get(chave, ROTA_DO_CARDAPIO),
            }
        )
    return saida


def cardapio(sessao: Sessao) -> dict[str, Any]:
    """`GET /api/cardapio`: os pratos aceitos, o resumo, os que ela não quer e as decisões."""
    dossie = sessao.dossie
    agora = dossie.agora()
    historico = dossie.historico()
    todos = passos(historico)
    nao_quer = _quem_nao_quer(todos, dossie.gostos())
    nomes = {r.prato for r in historico} | {prato for _, prato, _ in nao_quer}
    leituras = leituras_dos_pratos(sessao, nomes)
    rotas = {chave: rota_do_prato(leitura) for chave, leitura in leituras.items()}
    pratos = _pratos_aceitos(historico, leituras)
    return {
        "pratos": [prato.json(agora) for prato in pratos],
        "resumo": _resumo(sessao, pratos),
        "nao_quer": [
            {
                "prato": prato,
                "motivo_texto": motivo,
                "decidido_texto": quando_texto(quando, agora),
                "rota": rotas.get(chave_do_nome(prato), ROTA_DO_CARDAPIO),
            }
            for quando, prato, motivo in nao_quer
        ],
        "historico": historico_json(todos, agora, rotas),
    }


# --------------------------------------------------------------------------- #
# Desfazer e as notas
# --------------------------------------------------------------------------- #


def prato_do_historico(sessao: Sessao, pedido: str) -> str:
    """O nome do prato, dito pelo nome (sem ligar para caixa e acento) ou pelo id."""
    alvo = pedido.strip()
    nomes = {chave_do_nome(r.prato): r.prato for r in sessao.dossie.historico()}
    if chave_do_nome(alvo) in nomes:
        return nomes[chave_do_nome(alvo)]
    for nome in nomes.values():
        guardada = guardada_do_prato(sessao, nome)
        if alvo.lower() in {id_do_item(nome), guardada.slug if guardada else ""}:
            return nome
    raise Ausente("não encontrei esse prato entre as decisões da senhora", prato=pedido)


def desfazer(sessao: Sessao, pedido: str, *, chave: str | None = None) -> dict[str, Any]:
    """Volta o prato ao que era antes da última decisão, com uma decisão nova que aponta a desfeita.

    Sem decisão antes (ela só tinha aceitado), o prato volta a ficar para
    decidir depois. Voltar ao cardápio passa pela conferência de novo, como
    aceitar da primeira vez.
    """
    prato = prato_do_historico(sessao, pedido)
    alvo = chave_do_nome(prato)
    ultimo = [
        p for p in passos(sessao.dossie.historico()) if chave_do_nome(p.registro.prato) == alvo
    ][-1]
    desfeito = ultimo.registro.id
    if desfeito is None or not pode_desfazer(ultimo, atual=True):
        raise ErroDeUso(f"Não há o que desfazer: {o_prato(prato)} já está como estava.")
    anterior = ultimo.anterior
    decisao, motivo, preco = Decisao.ADIADO, "", None
    if anterior is not None:
        valor = dinheiro_do_texto(anterior.detalhes.get("preco"))
        decisao, motivo = anterior.decisao, anterior.motivo
        preco = float(valor.valor) if valor is not None else None
    registro, _ = sessao.decidir(
        prato, decisao.value, motivo, preco, chave=chave, desfaz=desfeito, canal=Canal.TELA
    )
    texto = texto_da_decisao(registro, sessao.dossie.historico())
    return {**cardapio(sessao), "texto": texto}


def gravar_notas(sessao: Sessao, pedido: str, texto: str) -> dict[str, Any]:
    """As notas dela sobre um prato: as mesmas da receita (`PUT /api/receitas/{slug}/notas`)."""
    prato = prato_do_historico(sessao, pedido)
    guardada = guardada_do_prato(sessao, prato)
    if guardada is None:
        raise Ausente(f"{_maiuscula(o_prato(prato))} não tem receita guardada para anotar.")
    sessao.avaliacoes.gravar(guardada.slug, notas=texto.strip())
    anotado = "Anotei." if texto.strip() else "Apaguei as notas."
    return {**cardapio(sessao), "texto": anotado}


# --------------------------------------------------------------------------- #
# O controle de preço
# --------------------------------------------------------------------------- #


def controle_do_preco(cmv: Dinheiro, minimo: Dinheiro) -> dict[str, Any]:
    """Os limites do controle de preço: do mínimo sem prejuízo a seis vezes o custo.

    A tela não calcula os limites: um centavo abaixo do mínimo já é prejuízo, e a
    conta do teto é dinheiro também. O teto é inteiro, em reais, e fica pelo
    menos R$ 1,00 acima do piso. O passo é de 50 centavos.
    """
    piso = max(minimo.arredondado_para_cima(), Dinheiro(PASSO_DO_CONTROLE))
    seis_vezes = (cmv * _VEZES_O_CUSTO).valor.quantize(Decimal(1), rounding=ROUND_CEILING)
    teto = max(piso + Dinheiro.de(1), Dinheiro(seis_vezes))
    return {
        "min": dinheiro_json(piso),
        "max": dinheiro_json(teto),
        "passo": float(PASSO_DO_CONTROLE),
    }


__all__ = [
    "PASSO_DO_CONTROLE",
    "ROTA_DO_CARDAPIO",
    "ROTA_DO_ORCAMENTO",
    "TIPO_ROTULO",
    "Passo",
    "PratoNoCardapio",
    "cardapio",
    "controle_do_preco",
    "desfazer",
    "dinheiro_do_texto",
    "do_prato",
    "gravar_notas",
    "guardada_do_prato",
    "leituras_dos_pratos",
    "o_prato",
    "passos",
    "pode_desfazer",
    "prato_do_historico",
    "rota_do_prato",
    "texto_da_decisao",
]
