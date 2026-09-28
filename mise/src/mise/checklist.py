"""O checklist de produção de uma receita: tudo o que precisa estar certo antes do aceite.

A conferência (`mise.viabilidade`) dá o veredito; o checklist mostra, item por
item, de onde vem a certeza dele. São cinco grupos, na ordem em que ela pensa
na produção:

    Equipamentos · Técnicas · Rotina · Ingredientes · Pré-determinados

Cada item tem um estado (`Status`) e uma origem (`Origem`), já ditos para ela:
"confirmado pela senhora", "suposto: confirme", "falta saber", "não dá"; "a
senhora disse", "suposto", "referência de ...", "receita". O que ela pode
responder ali mesmo vem com a `pergunta`, na forma de
`contratos/web/receita.json#perguntas[]`; o que a plataforma pré-determinou
(porções, pesos e preços de referência) vem com o `editar`, na mesma forma, e
ela muda quando quiser. Nada disso é pergunta obrigatória: o aceite só espera o
que é dela decidir.

A tela não calcula nada daqui: `pode_aceitar`, o que falta para aceitar e a
pergunta de confirmar a cozinha saem prontos. As regras são as do portão e as de
`mise.certeza`, lidas, nunca refeitas: a rotina, por exemplo, pergunta ao próprio
portão se a receita depende de cada limite (a conferência com o limite em
aberto), para o checklist nunca dizer uma coisa e o portão decidir outra.

Os campos que a pesquisa de referência acrescenta à conferência (o rendimento
estimado da `Avaliacao`, a medida de referência do ajuste, o preço de
referência do que falta) são lidos quando existem, e o grupo dos
pré-determinados fica só com o que houver.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

from mise.certeza import (
    Acao,
    ItemSuposto,
    apoio_suposto,
    confirmacao_json,
    o_que_ela_confirma,
    pressupostos_da_receita,
)
from mise.perfil import Posse, contagem, horas_texto
from mise.perfil_historico import TipoDeItem
from mise.taxonomia import EQUIPAMENTOS, TECNICAS, equipamento, tecnica
from mise.viabilidade import (
    SEM_PRECO,
    AssuntoDaPergunta,
    Pergunta,
    SituacaoDoIngrediente,
    TipoRestricao,
    Veredito,
    assunto_da,
    checar_operacional,
    pergunta_do_mesmo_item,
)

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Sequence

    from mise.dossie import EstadoOrcamento
    from mise.passos import PassosDaReceita
    from mise.perfil import PerfilCozinha
    from mise.receita import Receita
    from mise.viabilidade import (
        AjusteDoIngrediente,
        Avaliacao,
        Checagem,
        ItemFaltante,
    )


class Status(StrEnum):
    """O estado de um item do checklist, do que libera ao que segura."""

    CONFIRMADO = "confirmado"
    """Certo: ela disse, a despensa dela mostra, ou a receita não precisa."""
    PRE_DETERMINADO = "pre_determinado"
    """A plataforma pôs o valor (porções, peso, preço de referência); ela muda se quiser."""
    SUPOSTO = "suposto"
    """Toda cozinha tem, e ela ainda não confirmou: o aceite pede a confirmação."""
    FALTA_SABER = "falta_saber"
    """Uma pergunta dela em aberto."""
    NAO_DA = "nao_da"
    """Pelo que ela disse, a receita não dá."""


class Origem(StrEnum):
    """De onde veio o que o item diz."""

    A_SENHORA_DISSE = "a_senhora_disse"
    SUPOSTO = "suposto"
    REFERENCIA = "referencia"
    RECEITA = "receita"


_STATUS_TEXTO: Final[dict[Status, str]] = {
    Status.CONFIRMADO: "confirmado pela senhora",
    Status.PRE_DETERMINADO: "pré-determinado",
    Status.SUPOSTO: "suposto: confirme",
    Status.FALTA_SABER: "falta saber",
    Status.NAO_DA: "não dá",
}

#: Do que libera ao que segura: o estado de um grupo é o do seu pior item.
_GRAVIDADE: Final[dict[Status, int]] = {
    Status.CONFIRMADO: 0,
    Status.PRE_DETERMINADO: 1,
    Status.SUPOSTO: 2,
    Status.FALTA_SABER: 3,
    Status.NAO_DA: 4,
}

#: Não precisa: a receita não depende disso, e a certeza vem dela mesma.
NAO_PRECISA: Final = "não precisa"

#: A ordem da taxonomia, a mesma da pergunta de confirmar a cozinha.
_ORDEM: Final[dict[str, int]] = {
    **{e.id: n for n, e in enumerate(EQUIPAMENTOS)},
    **{t.id: n for n, t in enumerate(TECNICAS)},
}


@dataclass(frozen=True, slots=True)
class ItemDaLista:
    """Uma linha do checklist."""

    id: str
    #: `equipamento`, `tecnica`, `rotina`, `ingrediente`, `compra`, `orcamento`,
    #: `porcoes`, `peso`, `preco` ou `modo_preparo`.
    tipo: str
    nome: str
    status: Status
    origem: Origem
    detalhe: str | None = None
    #: O estado dito para ela, quando a frase padrão do estado não serve ("tem", "não precisa").
    status_texto: str | None = None
    #: De onde veio a referência ("medidas do IBGE", "preço no Savegnago").
    fonte: str = ""
    pergunta: dict[str, Any] | None = None
    editar: dict[str, Any] | None = None

    @property
    def origem_texto(self) -> str:
        if self.origem is Origem.REFERENCIA:
            return f"referência de {self.fonte}" if self.fonte else "referência"
        return {
            Origem.A_SENHORA_DISSE: "a senhora disse",
            Origem.SUPOSTO: "suposto",
            Origem.RECEITA: "receita",
        }[self.origem]

    def para_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tipo": self.tipo,
            "nome": self.nome,
            "detalhe": self.detalhe,
            "status": self.status.value,
            "status_texto": self.status_texto or _STATUS_TEXTO[self.status],
            "origem": self.origem.value,
            "origem_texto": self.origem_texto,
            "pergunta": self.pergunta,
            "editar": self.editar,
        }


@dataclass(frozen=True, slots=True)
class GrupoDaLista:
    """Um dos cinco grupos, com o que dizer quando a receita não pede nada dele."""

    id: str
    titulo: str
    itens: tuple[ItemDaLista, ...]
    vazio_texto: str

    @property
    def status(self) -> Status:
        return max(
            (i.status for i in self.itens), key=_GRAVIDADE.__getitem__, default=Status.CONFIRMADO
        )

    def para_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "titulo": self.titulo,
            "status": self.status.value,
            "itens": [i.para_json() for i in self.itens],
            "vazio_texto": self.vazio_texto,
        }


def _maiuscula(texto: str) -> str:
    return texto[:1].upper() + texto[1:]


def _frase(texto: str) -> str:
    """Com maiúscula e ponto final: o motivo do portão vem em minúscula e sem ponto."""
    limpo = texto.strip()
    if not limpo:
        return limpo
    return _maiuscula(limpo) if limpo.endswith((".", "?", "!")) else f"{_maiuscula(limpo)}."


class _Perguntas:
    """As perguntas na forma da tela, com as opções e os passos que as pedem."""

    def __init__(self, passos: PassosDaReceita | None) -> None:
        self.passos = passos

    def json(self, pergunta: Pergunta | None) -> dict[str, Any] | None:
        if pergunta is None:
            return None
        from mise.passos import perguntas_com_opcoes  # noqa: PLC0415

        return perguntas_com_opcoes([pergunta], self.passos)[0]


def _checagem(avaliacao: Avaliacao, nome: str) -> Checagem | None:
    return next((c for c in avaliacao.checagens if c.nome == nome), None)


def _pergunta_do_campo(checagem: Checagem | None, *campos: str) -> Pergunta | None:
    if checagem is None:
        return None
    return next((p for p in checagem.perguntas if p.campo in campos), None)


def _impedimento_do_id(checagem: Checagem | None, id_: str) -> str | None:
    if checagem is None:
        return None
    return next((i.descricao for i in checagem.impedimentos if i.id == id_), None)


# --------------------------------------------------------------------------- #
# Equipamentos e técnicas
# --------------------------------------------------------------------------- #


def _pergunta_de_confirmar(item: ItemSuposto, receita: Receita) -> Pergunta:
    """A pergunta de um suposto, para ela responder só ele ("Não tenho", por exemplo)."""
    if item.tipo is TipoDeItem.EQUIPAMENTO:
        texto = equipamento(item.id).pergunta_para_ela()
        tipo = TipoRestricao.EQUIPAMENTO
    else:
        texto = tecnica(item.id).pergunta_para_ela()
        tipo = TipoRestricao.TECNICA
    # O motivo como o portão diz: "usa fogão", "pede refogar".
    pede = (
        f"usa {item.falado}" if tipo is TipoRestricao.EQUIPAMENTO else f"pede {item.nome.lower()}"
    )
    return Pergunta(tipo, item.id, texto, motivo=f"{receita.nome} {pede}")


def _equipamentos(
    receita: Receita, perfil: PerfilCozinha, avaliacao: Avaliacao, perguntas: _Perguntas
) -> GrupoDaLista:
    checagem = _checagem(avaliacao, "equipamentos")
    supostos = {i.id: i for i in pressupostos_da_receita(receita, perfil)}
    itens: list[ItemDaLista] = []
    for id_ in sorted(receita.equipamentos, key=_ORDEM.__getitem__):
        equip = equipamento(id_)
        nome = equip.nome
        impedimento = _impedimento_do_id(checagem, id_)
        posse, substituto = perfil.tem_equipamento_ou_substituto(id_)
        if impedimento is not None:
            itens.append(
                ItemDaLista(
                    id_,
                    "equipamento",
                    nome,
                    Status.NAO_DA,
                    Origem.A_SENHORA_DISSE,
                    detalhe=_frase(impedimento),
                )
            )
            continue
        if posse is not Posse.TEM:
            # A pergunta do portão: pelo item, ou pelo substituto, quando ela já disse que não tem.
            campo = id_
            if perfil.tem_equipamento(id_) is Posse.NAO_TEM:
                campo = next(
                    (
                        s
                        for s in equip.substitutos
                        if perfil.tem_equipamento(s) is Posse.DESCONHECIDO
                    ),
                    id_,
                )
            pergunta = _pergunta_do_campo(checagem, campo)
            itens.append(
                ItemDaLista(
                    id_,
                    "equipamento",
                    nome,
                    Status.FALTA_SABER,
                    Origem.RECEITA,
                    detalhe=pergunta.texto if pergunta is not None else None,
                    pergunta=perguntas.json(pergunta),
                )
            )
            continue
        apoio = apoio_suposto(id_, perfil)
        if apoio is not None:
            suposto = supostos[apoio]
            detalhe = (
                "Toda cozinha tem, e a senhora ainda não confirmou."
                if apoio == id_
                else f"A senhora resolve com {suposto.falado}, que toda cozinha tem; confirme."
            )
            itens.append(
                ItemDaLista(
                    id_,
                    "equipamento",
                    nome,
                    Status.SUPOSTO,
                    Origem.SUPOSTO,
                    detalhe=detalhe,
                    pergunta=perguntas.json(_pergunta_de_confirmar(suposto, receita)),
                )
            )
            continue
        resolve = (
            f"A senhora resolve com {equipamento(substituto).nome.lower()}."
            if substituto is not None
            else None
        )
        itens.append(
            ItemDaLista(
                id_, "equipamento", nome, Status.CONFIRMADO, Origem.A_SENHORA_DISSE, detalhe=resolve
            )
        )
    sem_preparo = _pergunta_do_campo(checagem, "modo_preparo")
    if sem_preparo is not None:
        itens.append(
            ItemDaLista(
                "modo_preparo",
                "modo_preparo",
                "Modo de preparo",
                Status.FALTA_SABER,
                Origem.RECEITA,
                detalhe=sem_preparo.texto,
                pergunta=perguntas.json(sem_preparo),
            )
        )
    return GrupoDaLista(
        "equipamentos", "Equipamentos", tuple(itens), "Esta receita não pede equipamento."
    )


def _tecnicas(
    receita: Receita, perfil: PerfilCozinha, avaliacao: Avaliacao, perguntas: _Perguntas
) -> GrupoDaLista:
    checagem = _checagem(avaliacao, "tecnicas")
    itens: list[ItemDaLista] = []
    for id_ in sorted(receita.tecnicas, key=_ORDEM.__getitem__):
        nome = tecnica(id_).nome
        impedimento = _impedimento_do_id(checagem, id_)
        posse = perfil.domina_tecnica(id_)
        if impedimento is not None:
            item = ItemDaLista(
                id_,
                "tecnica",
                nome,
                Status.NAO_DA,
                Origem.A_SENHORA_DISSE,
                detalhe=_frase(impedimento),
            )
        elif posse is Posse.DESCONHECIDO:
            pergunta = _pergunta_do_campo(checagem, id_)
            item = ItemDaLista(
                id_,
                "tecnica",
                nome,
                Status.FALTA_SABER,
                Origem.RECEITA,
                detalhe=pergunta.texto if pergunta is not None else None,
                pergunta=perguntas.json(pergunta),
            )
        elif perfil.suposto(id_):
            suposto = ItemSuposto(TipoDeItem.TECNICA, id_, nome)
            item = ItemDaLista(
                id_,
                "tecnica",
                nome,
                Status.SUPOSTO,
                Origem.SUPOSTO,
                detalhe="Toda cozinheira faz, e a senhora ainda não confirmou.",
                pergunta=perguntas.json(_pergunta_de_confirmar(suposto, receita)),
            )
        else:
            item = ItemDaLista(id_, "tecnica", nome, Status.CONFIRMADO, Origem.A_SENHORA_DISSE)
        itens.append(item)
    return GrupoDaLista(
        "tecnicas", "Técnicas", tuple(itens), "Esta receita não pede técnica especial."
    )


# --------------------------------------------------------------------------- #
# Rotina
# --------------------------------------------------------------------------- #

#: Os limites da rotina, na ordem do checklist, com o nome que ela lê.
ROTINA: Final[tuple[tuple[str, str], ...]] = (
    ("tempo_max_por_fornada_min", "Tempo por cozinhada"),
    ("tem_gas_sobrando", "Gás"),
    ("espaco_geladeira_litros", "Espaço na geladeira"),
    ("energia_aparelhos_simultaneos", "Energia"),
    ("bocas_fogao", "Bocas do fogão"),
)

#: Por que a receita não depende de cada limite, dito para ela.
_NAO_DEPENDE: Final[dict[str, str]] = {
    "tempo_max_por_fornada_min": "A receita não fica no fogo, no forno nem com aparelho ligado.",
    "tem_gas_sobrando": "A receita fica menos de 1 hora no fogo.",
    "espaco_geladeira_litros": "A receita não vai à geladeira.",
    "energia_aparelhos_simultaneos": "A receita não liga dois aparelhos fortes ao mesmo tempo.",
    "bocas_fogao": "A receita usa uma panela no fogo de cada vez.",
}

#: As perguntas da própria receita que moram num limite da rotina.
_DA_RECEITA_NA_ROTINA: Final[dict[str, str]] = {"tempo_max_por_fornada_min": "tempo_cozimento_min"}

#: Os avisos do portão que falam de cada limite.
_AVISO_DO_LIMITE: Final[dict[str, str]] = {
    "bocas_fogao": "bocas",
    "tempo_max_por_fornada_min": "tempo",
}


def _tempo_da_receita(receita: Receita) -> Pergunta:
    """A forma de ela dizer o tempo no fogo que a receita não diz (o `editar`, nunca pergunta)."""
    return Pergunta(
        TipoRestricao.OPERACIONAL,
        "tempo_cozimento_min",
        f"Quanto tempo a receita de {receita.nome.lower()} fica no fogo na sua cozinha? Em "
        "minutos, eu refaço a conta.",
        motivo="o tempo da sua cozinha vale mais que o que a receita não diz",
        assunto=AssuntoDaPergunta.TEMPO_COZIMENTO,
    )


def _o_que_ela_disse(campo: str, valor: int | bool) -> str:
    """O limite dela em palavras: "a senhora tem 2 horas por cozinhada"."""
    if campo == "tempo_max_por_fornada_min":
        return f"a senhora tem {horas_texto(int(valor))} por cozinhada"
    if campo == "tem_gas_sobrando":
        return "a senhora tem botijão de reserva" if valor else "a senhora não tem gás de reserva"
    if campo == "espaco_geladeira_litros":
        return (
            f"a senhora tem {contagem(int(valor), 'litro', 'litros')} livres na geladeira"
            if valor
            else "a senhora disse que não sobra espaço"
        )
    if campo == "energia_aparelhos_simultaneos":
        aparelhos = contagem(int(valor), "aparelho forte", "aparelhos fortes")
        return f"a instalação aguenta {aparelhos} juntos"
    return f"o fogão tem {contagem(int(valor), 'boca', 'bocas')}"


def _sem_o_nome(motivo: str, receita: Receita) -> str:
    """ "Arroz com frango fica 40 minutos no fogo" vira "A receita fica 40 minutos no fogo"."""
    if motivo.startswith(receita.nome):
        return "A receita" + motivo[len(receita.nome) :]
    return _maiuscula(motivo)


def _rotina(
    receita: Receita, perfil: PerfilCozinha, avaliacao: Avaliacao, perguntas: _Perguntas
) -> GrupoDaLista:
    from mise.passos import minutos_ativos  # noqa: PLC0415

    checagem = _checagem(avaliacao, "operacional")
    avisos = {a.tipo: a.texto for a in (checagem.avisos if checagem is not None else [])}
    itens: list[ItemDaLista] = []
    for campo, nome in ROTINA:
        impedimento = _impedimento_do_id(checagem, campo)
        pergunta = _pergunta_do_campo(checagem, campo, _DA_RECEITA_NA_ROTINA.get(campo, campo))
        if impedimento is not None:
            # O tempo que a receita não diz nunca é pergunta: ela corrige, se quiser.
            sem_tempo = (
                campo == "tempo_max_por_fornada_min" and not minutos_ativos(receita).conhecido
            )
            itens.append(
                ItemDaLista(
                    campo,
                    "rotina",
                    nome,
                    Status.NAO_DA,
                    Origem.A_SENHORA_DISSE,
                    detalhe=_frase(impedimento),
                    editar=perguntas.json(_tempo_da_receita(receita)) if sem_tempo else None,
                )
            )
            continue
        if pergunta is not None:
            itens.append(
                ItemDaLista(
                    campo,
                    "rotina",
                    nome,
                    Status.FALTA_SABER,
                    Origem.RECEITA,
                    detalhe=_frase(pergunta.motivo) if pergunta.motivo else None,
                    pergunta=perguntas.json(pergunta),
                )
            )
            continue
        # Depende do limite? O próprio portão diz: com o limite em aberto, ele perguntaria.
        em_aberto = checar_operacional(receita, perfil.com_restricao(campo, None))
        dependencia = _pergunta_do_campo(em_aberto, campo)
        valor = getattr(perfil.restricoes, campo)
        if dependencia is None or valor is None:
            itens.append(
                ItemDaLista(
                    campo,
                    "rotina",
                    nome,
                    Status.CONFIRMADO,
                    Origem.RECEITA,
                    detalhe=_NAO_DEPENDE[campo],
                    status_texto=NAO_PRECISA,
                )
            )
            continue
        aviso = avisos.get(_AVISO_DO_LIMITE.get(campo, ""))
        if aviso is not None:
            detalhe = aviso
        elif dependencia.motivo and dependencia.motivo.startswith(receita.nome):
            detalhe = (
                f"{_sem_o_nome(dependencia.motivo, receita)}; {_o_que_ela_disse(campo, valor)}."
            )
        else:
            detalhe = f"{_maiuscula(_o_que_ela_disse(campo, valor))}, e a receita cabe."
        itens.append(
            ItemDaLista(
                campo, "rotina", nome, Status.CONFIRMADO, Origem.A_SENHORA_DISSE, detalhe=detalhe
            )
        )
    return GrupoDaLista("rotina", "Rotina", tuple(itens), "")


# --------------------------------------------------------------------------- #
# Ingredientes
# --------------------------------------------------------------------------- #

#: De onde veio o preço do que falta, como origem do checklist.
_ORIGEM_DO_PRECO: Final[dict[str, tuple[Origem, str]]] = {
    "informado_por_ela": (Origem.A_SENHORA_DISSE, ""),
    "planilha": (Origem.A_SENHORA_DISSE, ""),
    "pesquisado_na_web": (Origem.REFERENCIA, "preço na internet"),
    "estimado": (Origem.REFERENCIA, "preço estimado na conversa"),
}


def _origem_do_preco(faltante: ItemFaltante) -> tuple[Origem, str]:
    referencia = getattr(faltante, "referencia", None)
    if referencia is not None:
        return Origem.REFERENCIA, f"preço no {referencia.site}"
    return _ORIGEM_DO_PRECO.get(faltante.origem_do_preco, (Origem.A_SENHORA_DISSE, ""))


def _quanto(ajuste: AjusteDoIngrediente, faltante: ItemFaltante) -> str:
    from mise.receitas_json import medida_texto  # noqa: PLC0415

    return medida_texto(ajuste.falta) if ajuste.falta is not None else faltante.quantidade_texto


def _pergunta_de_preco(faltante: ItemFaltante, quanto: str, *, editar: bool) -> Pergunta:
    nome = faltante.nome.lower()
    texto = (
        f"Quanto a senhora paga em {nome}? O preço e por qual quantidade (o quilo, a lata)."
        if editar
        else f"Quanto custa {quanto} de {nome} aí na sua região, e por qual quantidade?"
    )
    motivo = (
        "o preço da senhora vale mais que a referência"
        if editar
        else "sem o preço não dá para saber se cabe no orçamento"
    )
    return Pergunta(
        TipoRestricao.INGREDIENTE,
        faltante.nome,
        texto,
        motivo=motivo,
        assunto=AssuntoDaPergunta.PRECO_DE_COMPRA,
        compras=(faltante,),
    )


def _ingredientes(
    avaliacao: Avaliacao, orcamento: EstadoOrcamento, perguntas: _Perguntas
) -> GrupoDaLista:
    checagem = _checagem(avaliacao, "ingredientes")
    itens: list[ItemDaLista] = []
    ajustes = avaliacao.ajustes
    em_casa = [
        (a.item.nome if a.item is not None else a.ingrediente.nome).lower()
        for a in ajustes
        if a.situacao in (SituacaoDoIngrediente.TEM, SituacaoDoIngrediente.TEM_PARTE)
        and a.pergunta is None
        and not a.sem_dado
        and not a.da_torneira
    ]
    if em_casa:
        itens.append(
            ItemDaLista(
                "na_despensa",
                "ingrediente",
                "Tem na despensa",
                Status.CONFIRMADO,
                Origem.A_SENHORA_DISSE,
                detalhe=_frase(_lista_curta(em_casa)),
                status_texto="tem",
            )
        )
    com_falta = [a for a in ajustes if a.faltante is not None]
    for ajuste in com_falta:
        faltante = ajuste.faltante
        assert faltante is not None
        quanto = _quanto(ajuste, faltante)
        origem, fonte = _origem_do_preco(faltante)
        if faltante.custo_estimado is None:
            # Sem preço em fonte nenhuma: não se pergunta. Não dá para confirmar
            # que cabe, e o preço dela vale, se ela quiser dizer.
            itens.append(
                ItemDaLista(
                    f"compra:{faltante.nome}",
                    "compra",
                    _maiuscula(faltante.nome),
                    Status.NAO_DA,
                    Origem.RECEITA,
                    detalhe=(
                        f"Comprar {quanto}; não achei o preço em página de supermercado, e sem "
                        "ele não dá para confirmar que cabe."
                    ),
                    editar=perguntas.json(_pergunta_de_preco(faltante, quanto, editar=True)),
                )
            )
            continue
        itens.append(
            ItemDaLista(
                f"compra:{faltante.nome}",
                "compra",
                _maiuscula(faltante.nome),
                Status.CONFIRMADO,
                origem,
                detalhe=f"Comprar {quanto}, {faltante.custo_estimado}.",
                status_texto="vai comprar",
                fonte=fonte,
            )
        )
    itens.append(_orcamento(avaliacao, orcamento, checagem, com_falta))
    # O que segura um ingrediente e não é preço: a linha não lida, o item parecido, o peso.
    for pergunta in checagem.perguntas if checagem is not None else []:
        if assunto_da(pergunta) is AssuntoDaPergunta.PRECO_DE_COMPRA:
            continue
        itens.append(
            ItemDaLista(
                f"pergunta:{pergunta.campo}",
                "ingrediente",
                _maiuscula(pergunta.campo),
                Status.FALTA_SABER,
                Origem.RECEITA,
                detalhe=pergunta.texto,
                pergunta=perguntas.json(pergunta),
            )
        )
    for impedimento in checagem.impedimentos if checagem is not None else []:
        if impedimento.id in ("orcamento", SEM_PRECO):
            continue
        itens.append(
            ItemDaLista(
                f"impedimento:{impedimento.id}",
                "ingrediente",
                _maiuscula(impedimento.id),
                Status.NAO_DA,
                Origem.RECEITA,
                detalhe=_frase(impedimento.descricao),
            )
        )
    return GrupoDaLista("ingredientes", "Ingredientes", tuple(itens), "")


def _orcamento(
    avaliacao: Avaliacao,
    orcamento: EstadoOrcamento,
    checagem: Checagem | None,
    com_falta: Sequence[AjusteDoIngrediente],
) -> ItemDaLista:
    """Se a compra cabe no que resta dos complementos."""
    nome = f"Cabe nos {orcamento.inicial}"
    if not com_falta:
        return ItemDaLista(
            "orcamento",
            "orcamento",
            nome,
            Status.CONFIRMADO,
            Origem.RECEITA,
            detalhe=f"Nada a comprar; restam {orcamento.restante}.",
            status_texto=NAO_PRECISA,
        )
    total = avaliacao.custo_das_compras
    if total is None:
        return ItemDaLista(
            "orcamento",
            "orcamento",
            nome,
            Status.NAO_DA,
            Origem.RECEITA,
            detalhe=(
                "Sem o preço de tudo o que falta comprar, não dá para confirmar que a compra cabe."
            ),
        )
    impedimento = _impedimento_do_id(checagem, "orcamento")
    if impedimento is not None:
        return ItemDaLista(
            "orcamento",
            "orcamento",
            nome,
            Status.NAO_DA,
            Origem.A_SENHORA_DISSE,
            detalhe=_frase(impedimento),
        )
    pela_referencia = [
        fonte
        for a in com_falta
        if a.faltante is not None
        for origem, fonte in [_origem_do_preco(a.faltante)]
        if origem is Origem.REFERENCIA
    ]
    return ItemDaLista(
        "orcamento",
        "orcamento",
        nome,
        Status.CONFIRMADO,
        Origem.REFERENCIA if pela_referencia else Origem.A_SENHORA_DISSE,
        detalhe=f"A compra dá {total}; restam {orcamento.restante}.",
        status_texto="cabe",
        fonte=pela_referencia[0] if pela_referencia else "",
    )


def _lista_curta(nomes: Sequence[str]) -> str:
    """ "arroz, cebola e alho"."""
    if len(nomes) <= 1:
        return "".join(nomes)
    return ", ".join(nomes[:-1]) + " e " + nomes[-1]


# --------------------------------------------------------------------------- #
# Pré-determinados: porções, pesos e preços de referência
# --------------------------------------------------------------------------- #


def _pergunta_das_porcoes(receita: Receita, motivo: str) -> Pergunta:
    return Pergunta(
        TipoRestricao.OPERACIONAL,
        "rendimento_porcoes",
        f"Quantas porções a receita de {receita.nome.lower()} rende na sua cozinha?",
        motivo=motivo,
        assunto=AssuntoDaPergunta.RENDIMENTO,
    )


def _porcoes(
    receita: Receita, avaliacao: Avaliacao, respondidos: Collection[str], perguntas: _Perguntas
) -> ItemDaLista:
    pendente = _pergunta_do_campo(_checagem(avaliacao, "operacional"), "rendimento_porcoes")
    if pendente is not None:
        return ItemDaLista(
            "porcoes",
            "porcoes",
            "Porções",
            Status.FALTA_SABER,
            Origem.RECEITA,
            detalhe=pendente.texto,
            pergunta=perguntas.json(pendente),
        )
    rendimento = getattr(avaliacao, "rendimento", None)
    porcoes = rendimento.porcoes if rendimento is not None else receita.rendimento_porcoes
    quantas = contagem(porcoes, "porção", "porções")
    editar = perguntas.json(
        _pergunta_das_porcoes(
            receita, "o custo de cada porção é o custo da receita dividido por elas"
        )
    )
    if "rendimento_porcoes" in respondidos:
        return ItemDaLista(
            "porcoes",
            "porcoes",
            "Porções",
            Status.CONFIRMADO,
            Origem.A_SENHORA_DISSE,
            detalhe=f"Rende {quantas}.",
            editar=editar,
        )
    if rendimento is not None and rendimento.estimado:
        return ItemDaLista(
            "porcoes",
            "porcoes",
            "Porções",
            Status.PRE_DETERMINADO,
            Origem.REFERENCIA,
            detalhe=_frase(rendimento.derivacao or rendimento.texto),
            fonte=f"porções de {_gramas(rendimento.porcao_g)} g",
            editar=editar,
        )
    return ItemDaLista(
        "porcoes",
        "porcoes",
        "Porções",
        Status.PRE_DETERMINADO,
        Origem.RECEITA,
        detalhe=f"Rende {quantas}, como a receita diz.",
        editar=editar,
    )


def _gramas(valor: Any) -> str:
    texto = f"{valor.normalize():f}" if hasattr(valor, "normalize") else str(valor)
    return texto.replace(".", ",")


def _pesos(avaliacao: Avaliacao, perguntas: _Perguntas) -> list[ItemDaLista]:
    itens: list[ItemDaLista] = []
    for ajuste in avaliacao.ajustes:
        linha = ajuste.ingrediente
        nome = _maiuscula(ajuste.item.nome if ajuste.item is not None else linha.nome)
        chave = f"peso:{linha.texto_original or linha.nome}"
        if "(a senhora disse)" in ajuste.conversao:
            itens.append(
                ItemDaLista(
                    chave,
                    "peso",
                    nome,
                    Status.CONFIRMADO,
                    Origem.A_SENHORA_DISSE,
                    detalhe=_frase(ajuste.conversao.replace(" (a senhora disse)", "")),
                )
            )
            continue
        referencia = getattr(ajuste, "medida_de_referencia", None)
        corrigir = getattr(ajuste, "corrigir_peso", None)
        if referencia is None or corrigir is None:
            continue
        editar = Pergunta(
            TipoRestricao.INGREDIENTE,
            linha.texto_original or linha.nome,
            f"Quanto pesa {corrigir.uma} na sua cozinha? Em gramas, eu refaço a conta.",
            motivo="o peso da sua cozinha vale mais que a média da tabela",
            assunto=AssuntoDaPergunta.MEDIDA,
            peso=corrigir,
        )
        itens.append(
            ItemDaLista(
                chave,
                "peso",
                nome,
                Status.PRE_DETERMINADO,
                Origem.REFERENCIA,
                detalhe=f"{_maiuscula(corrigir.uma)} pesa cerca de {_gramas(referencia.gramas)} g.",
                fonte=getattr(getattr(referencia, "fonte", None), "curto", "medidas do IBGE"),
                editar=perguntas.json(editar),
            )
        )
    return itens


def _precos(avaliacao: Avaliacao, perguntas: _Perguntas) -> list[ItemDaLista]:
    itens: list[ItemDaLista] = []
    for ajuste in avaliacao.ajustes:
        faltante = ajuste.faltante
        if faltante is None or faltante.custo_estimado is None:
            continue
        origem, fonte = _origem_do_preco(faltante)
        if origem is not Origem.REFERENCIA:
            continue
        referencia = getattr(faltante, "referencia", None)
        detalhe = (
            _frase(referencia.preco_texto)
            if referencia is not None
            else _frase(faltante.premissa or faltante.derivacao or str(faltante.custo_estimado))
        )
        quanto = _quanto(ajuste, faltante)
        itens.append(
            ItemDaLista(
                f"preco:{faltante.nome}",
                "preco",
                f"Preço de {faltante.nome.lower()}",
                Status.PRE_DETERMINADO,
                Origem.REFERENCIA,
                detalhe=detalhe,
                fonte=fonte,
                editar=perguntas.json(_pergunta_de_preco(faltante, quanto, editar=True)),
            )
        )
    return itens


def _quantidades(avaliacao: Avaliacao, perguntas: _Perguntas) -> list[ItemDaLista]:
    """A quantidade que a receita não diz: a unidade de venda, com a fonte, e ela corrige."""
    itens: list[ItemDaLista] = []
    for ajuste in avaliacao.ajustes:
        estimada = ajuste.quantidade_estimada
        if estimada is None:
            continue
        linha = ajuste.ingrediente
        campo = linha.texto_original or linha.nome
        editar = Pergunta(
            TipoRestricao.INGREDIENTE,
            campo,
            f"Quanto vai de {linha.nome.lower()} na sua receita? Eu considerei {estimada.texto}.",
            motivo="a quantidade da sua cozinha vale mais que a unidade de venda",
            assunto=AssuntoDaPergunta.LINHA_NAO_LIDA,
        )
        itens.append(
            ItemDaLista(
                f"quantidade:{campo}",
                "quantidade",
                _maiuscula(linha.nome or campo),
                Status.PRE_DETERMINADO,
                Origem.REFERENCIA,
                detalhe=_frase(estimada.frase),
                fonte=estimada.fonte,
                editar=perguntas.json(editar),
            )
        )
    return itens


def _decisoes(avaliacao: Avaliacao, perguntas: _Perguntas) -> list[ItemDaLista]:
    """O item parecido que ficou como compra, ou o sinônimo que é o dela, com a decisão dita."""
    itens: list[ItemDaLista] = []
    for ajuste in avaliacao.ajustes:
        considerado = ajuste.item_considerado or (ajuste.item.nome if ajuste.item else "")
        if not ajuste.decisao or not considerado:
            continue
        linha = ajuste.ingrediente
        campo = linha.texto_original or linha.nome
        editar = Pergunta(
            TipoRestricao.INGREDIENTE,
            campo,
            pergunta_do_mesmo_item(linha.nome, considerado),
            motivo="se for, a receita usa o que a senhora já tem",
            assunto=AssuntoDaPergunta.MESMO_INGREDIENTE,
        )
        itens.append(
            ItemDaLista(
                f"item:{campo}",
                "mesmo_ingrediente",
                _maiuscula(linha.nome or campo),
                Status.PRE_DETERMINADO,
                Origem.RECEITA,
                detalhe=ajuste.decisao,
                editar=perguntas.json(editar),
            )
        )
    return itens


def _pre_determinados(
    receita: Receita, avaliacao: Avaliacao, respondidos: Collection[str], perguntas: _Perguntas
) -> GrupoDaLista:
    itens = [_porcoes(receita, avaliacao, respondidos, perguntas)]
    itens += _quantidades(avaliacao, perguntas)
    itens += _decisoes(avaliacao, perguntas)
    itens += _pesos(avaliacao, perguntas)
    itens += _precos(avaliacao, perguntas)
    return GrupoDaLista("pre_determinados", "Pré-determinados", tuple(itens), "")


# --------------------------------------------------------------------------- #
# O que falta para aceitar, e o checklist inteiro
# --------------------------------------------------------------------------- #


def o_que_falta_para_aceitar(
    receita: Receita, avaliacao: Avaliacao, supostos: Sequence[ItemSuposto]
) -> list[str]:
    """Cada coisa que segura o aceite, dita para ela; vazia quando ela pode aceitar.

    Receita que não dá diz só por que não dá: o resto não muda nada. Fora isso,
    as perguntas em aberto, o gosto e o que toda cozinha tem sem ela confirmar.
    """
    if avaliacao.veredito is Veredito.BLOQUEADO:
        return [_frase(i.descricao) for i in avaliacao.impedimentos]
    faltam = [f"Responder: {p.texto}" for p in avaliacao.perguntas_da_cozinha]
    if any(p.tipo is TipoRestricao.GOSTO for p in avaliacao.perguntas):
        faltam.append(f"Dizer se a senhora gosta de fazer {receita.nome.lower()}.")
    if supostos:
        faltam.append(f"Confirmar que a senhora {o_que_ela_confirma(supostos)}.")
    return faltam


def _resumo(pode_aceitar: bool, bloqueada: bool, faltam: Sequence[str]) -> str:
    if pode_aceitar:
        return "Está tudo certo para a senhora aceitar este prato."
    if bloqueada:
        return "Pelo que a senhora me disse, esta receita não dá."
    verbo = "falta" if len(faltam) == 1 else "faltam"
    return f"Antes de aceitar, {verbo} {contagem(len(faltam), 'coisa', 'coisas')}."


def lista_de_producao(
    receita: Receita,
    perfil: PerfilCozinha,
    avaliacao: Avaliacao,
    orcamento: EstadoOrcamento,
    *,
    passos: PassosDaReceita | None = None,
    respondidos: Iterable[str] = (),
) -> dict[str, Any]:
    """O checklist de produção (`receita.json#checklist`).

    `perfil` tem de ser o mesmo que a avaliação usou; `respondidos` são os campos
    da receita que ela mesma respondeu (o rendimento, por exemplo), e `passos` a
    receita passo a passo, para as perguntas dizerem em que passo o item aparece.
    """
    perguntas = _Perguntas(passos)
    supostos = pressupostos_da_receita(receita, perfil)
    pode_aceitar = avaliacao.permite_precificar and not supostos
    faltam = [] if pode_aceitar else o_que_falta_para_aceitar(receita, avaliacao, supostos)
    grupos = (
        _equipamentos(receita, perfil, avaliacao, perguntas),
        _tecnicas(receita, perfil, avaliacao, perguntas),
        _rotina(receita, perfil, avaliacao, perguntas),
        _ingredientes(avaliacao, orcamento, perguntas),
        _pre_determinados(receita, avaliacao, frozenset(respondidos), perguntas),
    )
    return {
        "titulo": "Checklist de produção",
        "pode_aceitar": pode_aceitar,
        "resumo": _resumo(pode_aceitar, avaliacao.veredito is Veredito.BLOQUEADO, faltam),
        "falta_para_aceitar": faltam,
        "confirmar_a_cozinha": confirmacao_json(receita, perfil, Acao.ACEITAR),
        "grupos": [g.para_json() for g in grupos],
    }


__all__ = [
    "NAO_PRECISA",
    "ROTINA",
    "GrupoDaLista",
    "ItemDaLista",
    "Origem",
    "Status",
    "lista_de_producao",
    "o_que_falta_para_aceitar",
]
