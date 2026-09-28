"""A certeza antes do aceite: o que toda cozinha tem, confirmado por ela.

O portão deixa passar como suposto o que qualquer cozinha tem: fogão, panela
funda, faca, refogar, fazer arroz. Perguntar item por item a uma cozinheira de
mão cheia gastaria a paciência dela nas perguntas que não decidem nada. Mas o
§2.2 é explícito: antes de ela aceitar um prato, a plataforma precisa garantir
que ela consegue produzi-lo, e ela não pode comprar ingrediente e descobrir
depois que não consegue cozinhar. Suposto não é garantia.

A saída é perguntar uma vez só, e só o que a receita usa: no aceite e na
compra, o que a receita tira do suposto vira uma pergunta ("Antes de aceitar, a
senhora confirma que tem fogão e panela funda e que sabe refogar?"), que ela
responde num toque. O que ela confirmou uma vez vale para todas as receitas; o
que a receita não usa não é perguntado.

A grade continua mostrando o que o portão decide ("Dá pra fazer"), com o
lembrete de confirmar a cozinha; quem segura é o aceite e a compra
(`exigir_cozinha_confirmada`), pelas duas portas: a tela e a conversa.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

from mise.erros import CozinhaNaoConfirmada
from mise.perfil import Posse
from mise.perfil_historico import TipoDeItem
from mise.taxonomia import EQUIPAMENTOS, TECNICAS, equipamento

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from mise.perfil import PerfilCozinha
    from mise.receita import Receita
    from mise.viabilidade import Avaliacao


#: O `campo` de `registrar_resposta(tipo="cozinha")` que confirma tudo o que ainda é suposto.
TODA_COZINHA: Final = "toda_cozinha"

#: A nota do card da grade que dá para fazer apoiado no que ela ainda não confirmou.
NOTA_DA_GRADE: Final = "Confirme a cozinha"


class Acao(StrEnum):
    """O que a pergunta de confirmação antecede: o aceite do prato ou a compra para ele."""

    ACEITAR = "aceitar"
    COMPRAR = "comprar"


@dataclass(frozen=True, slots=True)
class ItemSuposto:
    """Um equipamento ou uma técnica que está como "tem" só porque toda cozinha tem."""

    tipo: TipoDeItem
    id: str
    nome: str

    @property
    def falado(self) -> str:
        """Como o item entra na frase: "fogão", "refogar", "fazer bolo caseiro"."""
        if self.tipo is TipoDeItem.EQUIPAMENTO:
            return self.nome[:1].lower() + self.nome[1:]
        return tecnica_falada(self.nome)

    def para_json(self) -> dict[str, str]:
        return {"tipo": self.tipo.value, "id": self.id, "nome": self.nome}


#: A ordem da taxonomia: o fogão antes da faca, refogar antes de assar.
_ORDEM_DOS_EQUIPAMENTOS: Final[dict[str, int]] = {e.id: n for n, e in enumerate(EQUIPAMENTOS)}
_ORDEM_DAS_TECNICAS: Final[dict[str, int]] = {t.id: n for n, t in enumerate(TECNICAS)}

#: As terminações do infinitivo: "Refogar" já é o que ela sabe; "Bolo caseiro" é o que ela faz.
_INFINITIVO: Final = ("ar", "er", "ir")


def tecnica_falada(nome: str) -> str:
    """A técnica no meio da frase "sabe ...": "refogar", "fazer brigadeiro ou doce de panela"."""
    minusculo = nome.replace(" / ", " ou ").strip()
    minusculo = minusculo[:1].lower() + minusculo[1:]
    primeira = minusculo.split(" ", 1)[0]
    return minusculo if primeira.endswith(_INFINITIVO) else f"fazer {minusculo}"


def _lista(partes: Sequence[str]) -> str:
    """ "fogão", "fogão e faca", "fogão, faca e tábua de corte"."""
    if len(partes) <= 1:
        return "".join(partes)
    return ", ".join(partes[:-1]) + " e " + partes[-1]


# --------------------------------------------------------------------------- #
# O que a receita tira do suposto
# --------------------------------------------------------------------------- #


def apoio_suposto(id_: str, perfil: PerfilCozinha) -> str | None:
    """O item suposto em que a receita se apoia para este equipamento, ou `None`.

    Se ela confirmou o equipamento, ou um substituto dele (a air fryer do
    forno), nada é suposto. Senão, o primeiro que resolve e está como suposto:
    o próprio item, e depois os substitutos, na ordem em que o portão os aceita.
    O que ela disse que não tem, ou não sabe, o portão já trata: bloqueia ou
    pergunta.
    """
    candidatos = (id_, *equipamento(id_).substitutos)
    if any(perfil.tem_equipamento(c) is Posse.TEM and not perfil.suposto(c) for c in candidatos):
        return None
    return next((c for c in candidatos if perfil.suposto(c)), None)


def pressupostos_da_receita(receita: Receita, perfil: PerfilCozinha) -> tuple[ItemSuposto, ...]:
    """O que a receita usa do que toda cozinha tem e ela ainda não confirmou.

    Na ordem da taxonomia, equipamentos antes das técnicas, sem repetir: é a
    ordem da pergunta. Vazio quando a receita não se apoia em suposição nenhuma.
    """
    equipamentos = {
        suposto
        for id_ in receita.equipamentos
        if (suposto := apoio_suposto(id_, perfil)) is not None
    }
    tecnicas = {id_ for id_ in receita.tecnicas if perfil.suposto(id_)}
    return _itens(equipamentos, tecnicas)


def pressupostos_da_cozinha(perfil: PerfilCozinha) -> tuple[ItemSuposto, ...]:
    """Tudo que ainda está como suposto no perfil dela: o "O que toda cozinha tem" da tela."""
    equipamentos = {e.id for e in EQUIPAMENTOS if perfil.suposto(e.id)}
    tecnicas = {t.id for t in TECNICAS if perfil.suposto(t.id)}
    return _itens(equipamentos, tecnicas)


def _itens(equipamentos: Iterable[str], tecnicas: Iterable[str]) -> tuple[ItemSuposto, ...]:
    por_id_e = {e.id: e for e in EQUIPAMENTOS}
    por_id_t = {t.id: t for t in TECNICAS}
    return tuple(
        [
            ItemSuposto(TipoDeItem.EQUIPAMENTO, i, por_id_e[i].nome)
            for i in sorted(equipamentos, key=_ORDEM_DOS_EQUIPAMENTOS.__getitem__)
        ]
        + [
            ItemSuposto(TipoDeItem.TECNICA, i, por_id_t[i].nome)
            for i in sorted(tecnicas, key=_ORDEM_DAS_TECNICAS.__getitem__)
        ]
    )


# --------------------------------------------------------------------------- #
# A pergunta, a recusa e o que volta
# --------------------------------------------------------------------------- #


def o_que_ela_confirma(itens: Sequence[ItemSuposto]) -> str:
    """ "tem fogão e panela funda e que sabe refogar": o miolo da pergunta e da resposta."""
    tem = [i.falado for i in itens if i.tipo is TipoDeItem.EQUIPAMENTO]
    sabe = [i.falado for i in itens if i.tipo is TipoDeItem.TECNICA]
    partes = ([f"tem {_lista(tem)}"] if tem else []) + ([f"sabe {_lista(sabe)}"] if sabe else [])
    return " e que ".join(partes)


def pergunta_de_confirmacao(itens: Sequence[ItemSuposto], acao: Acao = Acao.ACEITAR) -> str:
    """Uma pergunta só: "Antes de aceitar, a senhora confirma que tem fogão e sabe refogar?"."""
    return f"Antes de {acao.value}, a senhora confirma que {o_que_ela_confirma(itens)}?"


def texto_da_confirmacao(itens: Sequence[ItemSuposto]) -> str:
    """O que volta para ela depois de confirmar: "Anotei: a senhora tem fogão e sabe refogar."."""
    if not itens:
        return "Não havia nada para confirmar: a senhora já tinha dito tudo isso."
    miolo = o_que_ela_confirma(itens).replace(" e que ", " e ")
    return f"Anotei: a senhora {miolo}."


def confirmacao_json(
    receita: Receita, perfil: PerfilCozinha, acao: Acao = Acao.ACEITAR
) -> dict[str, Any] | None:
    """`{pergunta, itens}` do que falta ela confirmar para esta receita; `None` se nada falta."""
    itens = pressupostos_da_receita(receita, perfil)
    if not itens:
        return None
    return {
        "pergunta": pergunta_de_confirmacao(itens, acao),
        "itens": [i.para_json() for i in itens],
    }


def exigir_cozinha_confirmada(
    receita: Receita, perfil: PerfilCozinha, acao: Acao, *, receita_id: str = ""
) -> None:
    """Recusa o aceite ou a compra enquanto a receita se apoiar em algo que ela não confirmou."""
    itens = pressupostos_da_receita(receita, perfil)
    if itens:
        raise CozinhaNaoConfirmada(
            receita.nome,
            pergunta_de_confirmacao(itens, acao),
            tuple(i.id for i in itens),
            receita_id=receita_id,
        )


def nota_da_grade(receita: Receita, perfil: PerfilCozinha, avaliacao: Avaliacao) -> str | None:
    """ "Confirme a cozinha" no card que dá para fazer apoiado no que ela não confirmou.

    A grade continua com o veredito do portão ("Dá pra fazer"); a nota lembra
    que o aceite vai pedir a confirmação. Receita que não dá, ou que ainda
    espera outra resposta, não ganha a nota: a pergunta dela vem antes.
    """
    if not avaliacao.veredito_da_cozinha.permite_precificar:
        return None
    return NOTA_DA_GRADE if pressupostos_da_receita(receita, perfil) else None


__all__ = [
    "NOTA_DA_GRADE",
    "TODA_COZINHA",
    "Acao",
    "ItemSuposto",
    "apoio_suposto",
    "confirmacao_json",
    "exigir_cozinha_confirmada",
    "nota_da_grade",
    "o_que_ela_confirma",
    "pergunta_de_confirmacao",
    "pressupostos_da_cozinha",
    "pressupostos_da_receita",
    "tecnica_falada",
    "texto_da_confirmacao",
]
