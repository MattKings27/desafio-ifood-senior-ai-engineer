"""A cozinha dela na tela: ler e mudar cada item, com o que isso muda nas receitas.

`GET /api/perfil` substitui a rota antiga de `http.py` e acrescenta, a cada item,
quantas receitas em avaliação o pedem, quem o mudou por último (a tela, ou a
conversa com o agente), já em texto ("hoje, 09:12"), e a miniatura do
Commons (`imagem {url, credito}` pelo proxy de imagens, ou `null`). As restrições vêm com o
tipo da resposta, a unidade e a faixa, para a tela perguntar sem adivinhar.

Os `PUT` gravam o que ela escolheu na tela: "tem", "não tem" ou "não sei" para
equipamento e técnica, e o número, o sim ou não, ou `null` ("não sei") para as
restrições. Cada um devolve o item como ficou, o impacto nas receitas (as que
passaram a dar, as que deixaram de dar e as que continuam dependendo de uma resposta,
todas pelo mesmo portão) e as contagens do perfil. Forma em
`contratos/web/perfil.json` e `contratos/web/perfil-escrita.json`.

O que toda cozinha tem (fogão, panela funda, refogar) começa como suposto, e o
aceite de um prato pede que ela confirme o que a receita usa. `toda_cozinha`,
no `GET`, é o bloco "O que toda cozinha tem", com o estado de cada item; o
`POST /api/perfil/supostos/confirmar` grava o "Tenho tudo isso", o que uma
receita usa, ou item por item (`contratos/web/perfil-supostos.json`).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final, Literal

from fastapi import APIRouter
from mise import perfil_historico
from mise.certeza import texto_da_confirmacao
from mise.erros import Ausente, ErroDeUso
from mise.fotos import Foto, fotos_da_cozinha
from mise.mcp_server import Sessao
from mise.passos import entrada_da_restricao
from mise.perfil import (
    FORMATOS_OPERACIONAIS,
    PERGUNTAS_OPERACIONAIS,
    PerfilCozinha,
    Posse,
    TipoDeCampo,
    contagem,
    em_horas,
    horas_texto,
)
from mise.perfil_historico import EventoDoPerfil, MudancaNoPerfil, TipoDeItem
from mise.taxonomia import (
    EQUIPAMENTOS,
    EQUIPAMENTOS_POR_ID,
    TECNICAS,
    TECNICAS_POR_ID,
    Equipamento,
    Tecnica,
)
from pydantic import BaseModel, Field, StrictBool, StrictFloat, StrictInt

from gateway.rotas._comum import RespostaPadrao, SessaoDaApp, responder

roteador = APIRouter()

#: O que a tela manda para equipamento e técnica, e o que isso é para o perfil.
_POSSE_DA_TELA: Final[dict[str, Posse | None]] = {
    "tem": Posse.TEM,
    "nao_tem": Posse.NAO_TEM,
    "nao_sei": None,
}

#: Quem mudou por último, e o que ainda não mudou ninguém.
_Ultimos = dict[tuple[TipoDeItem, str], EventoDoPerfil]


class EstadoDoItem(BaseModel):
    """O que ela escolheu para um equipamento ou técnica: tem, não tem ou não sei."""

    estado: Literal["tem", "nao_tem", "nao_sei"]


class ValorDaRestricao(BaseModel):
    """O valor de uma restrição: número, sim ou não, ou `null` quando ela não sabe.

    Tipos estritos: `"4"` não é número e `1` não é sim. A faixa de cada restrição
    é conferida pelo motor (`FORMATOS_OPERACIONAIS`), que devolve a mensagem para ela.
    O tempo por cozinhada vem em horas (`1.5`), como a tela pergunta.
    """

    valor: StrictBool | StrictInt | StrictFloat | None


class ItemAConfirmar(BaseModel):
    """Um equipamento ou técnica que ela confirma que tem, ou faz."""

    tipo: Literal["equipamento", "tecnica"]
    id: str = Field(min_length=1, max_length=64)


class ConfirmacaoDaCozinha(BaseModel):
    """O que ela confirma de uma vez: os itens ditos, o que uma receita usa, ou tudo.

    Sem `itens` nem `receita`, confirma tudo o que ainda está como suposto (o
    "Tenho tudo isso" da cozinha). Com `receita` (o slug), o que ela usa do
    suposto: a pergunta do aceite. Com `itens`, só eles.
    """

    receita: str | None = Field(default=None, min_length=1, max_length=200)
    itens: list[ItemAConfirmar] | None = Field(default=None, max_length=80)


# --------------------------------------------------------------------------- #
# Rotas
# --------------------------------------------------------------------------- #


@roteador.get("/api/perfil", response_model=RespostaPadrao)
def ler_perfil(sessao: SessaoDaApp) -> RespostaPadrao:
    """Equipamentos, técnicas e restrições, com o que está em aberto e quem mudou o quê."""

    def montar() -> dict[str, Any]:
        leitura = _Leitura.da(sessao, sessao.perfil)
        p = leitura.perfil
        return {
            "completude": round(p.completude, 4),
            **_contagens(p, leitura.ultimos),
            "equipamentos": [leitura.equipamento(e) for e in EQUIPAMENTOS],
            "tecnicas": [leitura.tecnica(t) for t in TECNICAS],
            "restricoes": {campo: leitura.restricao(campo) for campo in PERGUNTAS_OPERACIONAIS},
            "toda_cozinha": leitura.toda_cozinha(),
        }

    return responder(montar)


@roteador.post("/api/perfil/supostos/confirmar", response_model=RespostaPadrao)
def confirmar_supostos(corpo: ConfirmacaoDaCozinha, sessao: SessaoDaApp) -> RespostaPadrao:
    """Ela confirma o que toda cozinha tem: tudo, o que uma receita usa, ou item por item.

    Cada item vira "tem", dito por ela, pelo mesmo caminho de uma resposta (o
    histórico com o canal). Responde o que foi confirmado, a frase para ela, as
    contagens do perfil e o bloco "O que toda cozinha tem" como ficou.
    """

    def montar() -> dict[str, Any]:
        if corpo.itens is not None and corpo.receita is not None:
            raise ErroDeUso("mande os itens ou a receita, não os dois")
        itens = None
        if corpo.itens is not None:
            itens = [(i.tipo, i.id) for i in corpo.itens]
            for tipo, id_ in itens:
                vocabulario = EQUIPAMENTOS_POR_ID if tipo == "equipamento" else TECNICAS_POR_ID
                if id_ not in vocabulario:
                    raise Ausente("esse item não está na lista da cozinha", id=id_)
        confirmados = sessao.confirmar_a_cozinha(receita_id=corpo.receita, itens=itens)
        leitura = _Leitura.da(sessao, sessao.perfil)
        return {
            "confirmados": [i.para_json() for i in confirmados],
            "texto": texto_da_confirmacao(confirmados),
            "perfil": _contagens(leitura.perfil, leitura.ultimos),
            "toda_cozinha": leitura.toda_cozinha(),
        }

    return responder(montar)


@roteador.put("/api/perfil/equipamentos/{id_}", response_model=RespostaPadrao)
def mudar_equipamento(id_: str, corpo: EstadoDoItem, sessao: SessaoDaApp) -> RespostaPadrao:
    """Ela tem, não tem ou não sabe se tem este equipamento."""
    return responder(lambda: _mudar_item(sessao, TipoDeItem.EQUIPAMENTO, id_, corpo.estado))


@roteador.put("/api/perfil/tecnicas/{id_}", response_model=RespostaPadrao)
def mudar_tecnica(id_: str, corpo: EstadoDoItem, sessao: SessaoDaApp) -> RespostaPadrao:
    """Ela faz, não faz ou não sabe se faz esta técnica."""
    return responder(lambda: _mudar_item(sessao, TipoDeItem.TECNICA, id_, corpo.estado))


@roteador.put("/api/perfil/restricoes/{campo}", response_model=RespostaPadrao)
def mudar_restricao(campo: str, corpo: ValorDaRestricao, sessao: SessaoDaApp) -> RespostaPadrao:
    """Uma restrição da rotina dela: bocas, tempo, porções, geladeira, energia ou gás."""

    def montar() -> dict[str, Any]:
        formato = FORMATOS_OPERACIONAIS.get(campo)
        if formato is None:
            raise Ausente("essa restrição não está na lista da cozinha", campo=campo)
        valor = formato.conferir(corpo.valor)
        mudanca = perfil_historico.mudar_restricao(sessao.dossie, campo, valor, sessao.canal)
        return _depois_da_mudanca(sessao, mudanca)

    return responder(montar)


def _mudar_item(sessao: Sessao, tipo: TipoDeItem, id_: str, estado: str) -> dict[str, Any]:
    vocabulario = EQUIPAMENTOS_POR_ID if tipo is TipoDeItem.EQUIPAMENTO else TECNICAS_POR_ID
    if id_ not in vocabulario:
        o_que = "esse equipamento" if tipo is TipoDeItem.EQUIPAMENTO else "essa técnica"
        raise Ausente(f"{o_que} não está na lista da cozinha", id=id_)
    mudanca = perfil_historico.mudar_item(
        sessao.dossie, tipo, id_, _POSSE_DA_TELA[estado], sessao.canal
    )
    return _depois_da_mudanca(sessao, mudanca)


def _depois_da_mudanca(sessao: Sessao, mudanca: MudancaNoPerfil) -> dict[str, Any]:
    """O item como ficou, o impacto nas receitas e as contagens: `perfil-escrita.json`."""
    leitura = _Leitura.da(sessao, mudanca.depois)
    if mudanca.tipo is TipoDeItem.EQUIPAMENTO:
        item = leitura.equipamento(EQUIPAMENTOS_POR_ID[mudanca.campo])
    elif mudanca.tipo is TipoDeItem.TECNICA:
        item = leitura.tecnica(TECNICAS_POR_ID[mudanca.campo])
    else:
        item = {"id": mudanca.campo, **leitura.restricao(mudanca.campo)}
    return {
        "item": item,
        "impacto": perfil_historico.impacto_nas_receitas(sessao, mudanca).para_json(),
        "perfil": _contagens(mudanca.depois, leitura.ultimos),
    }


# --------------------------------------------------------------------------- #
# Como cada item sai
# --------------------------------------------------------------------------- #


def _contagens(perfil: PerfilCozinha, ultimos: _Ultimos) -> dict[str, Any]:
    """Os números do perfil, e a mesma conta em texto: o plural não é trabalho da tela.

    "Não sei" é resposta dela: o resumo conta à parte o que ela disse que não
    sabe, e só chama de "ainda não perguntei" o que ninguém perguntou. O
    progresso ("1 de 63 respondidos pela senhora") é a mesma conta de
    `fracao_respondida`, dita em texto.
    """
    nao_sabe = sum(
        1
        for (tipo, campo), evento in ultimos.items()
        if evento.nao_sei and _em_aberto(perfil, tipo, campo)
    )
    return {
        "respondidos": perfil.respondidos,
        "supostos": perfil.supostos,
        "em_aberto": perfil.em_aberto,
        "fracao_respondida": perfil.fracao_respondida,
        "resumo": perfil.resumo_para_a_tela(nao_sabe),
        "progresso_texto": perfil.progresso_para_a_tela(),
    }


def _em_aberto(perfil: PerfilCozinha, tipo: TipoDeItem, campo: str) -> bool:
    """O equipamento ou a técnica está sem resposta de "tem" ou "não tem" agora."""
    if tipo is TipoDeItem.EQUIPAMENTO:
        return perfil.tem_equipamento(campo) is Posse.DESCONHECIDO
    if tipo is TipoDeItem.TECNICA:
        return perfil.domina_tecnica(campo) is Posse.DESCONHECIDO
    return False


class _Leitura:
    """O perfil com o que a tela mostra ao lado de cada item, lido uma vez por requisição."""

    __slots__ = ("afetadas", "agora", "fotos", "perfil", "ultimos")

    def __init__(
        self,
        perfil: PerfilCozinha,
        afetadas: Counter[tuple[str, str]],
        ultimos: _Ultimos,
        agora: datetime,
        fotos: Mapping[str, Foto],
    ) -> None:
        self.perfil = perfil
        self.afetadas = afetadas
        self.ultimos = ultimos
        self.agora = agora
        self.fotos = fotos

    @classmethod
    def da(cls, sessao: Sessao, perfil: PerfilCozinha) -> _Leitura:
        """`perfil` é o que vai para a tela: depois de um `PUT`, o que acabou de ser gravado."""
        afetadas: Counter[tuple[str, str]] = Counter()
        for receita in perfil_historico.receitas_em_avaliacao(sessao):
            afetadas.update(("equipamento", i) for i in receita.equipamentos)
            afetadas.update(("tecnica", i) for i in receita.tecnicas)
        return cls(
            perfil,
            afetadas,
            perfil_historico.ultimos_por_item(sessao.dossie),
            sessao.dossie.agora(),
            fotos_da_cozinha(sessao.planilha),
        )

    def equipamento(self, e: Equipamento) -> dict[str, Any]:
        return {
            "id": e.id,
            "nome": e.nome,
            "categoria": e.categoria.value,
            "estado": self.perfil.tem_equipamento(e.id).value,
            "pressuposto": e.pressuposto,
            "suposto": self.perfil.suposto(e.id),
            "pergunta": e.pergunta_para_ela(),
            "imagem": self._imagem(e.id),
            **self._afetadas("equipamento", e.id),
            **self._atualizacao(TipoDeItem.EQUIPAMENTO, e.id),
        }

    def tecnica(self, t: Tecnica) -> dict[str, Any]:
        return {
            "id": t.id,
            "nome": t.nome,
            "categoria": t.categoria.value,
            "dificuldade": t.dificuldade,
            "estado": self.perfil.domina_tecnica(t.id).value,
            "pressuposta": t.pressuposta,
            "suposto": self.perfil.suposto(t.id),
            "pergunta": t.pergunta_para_ela(),
            "imagem": self._imagem(t.id),
            **self._afetadas("tecnica", t.id),
            **self._atualizacao(TipoDeItem.TECNICA, t.id),
        }

    def toda_cozinha(self) -> dict[str, Any]:
        """ "O que toda cozinha tem": o que é pressuposto, com o estado de cada um para ela.

        O que está como suposto espera o "Tenho tudo isso" (ou o "Não tenho" de um
        item); o que ela já respondeu aparece com a resposta dela.
        """
        itens = [
            self._da_toda_cozinha(TipoDeItem.EQUIPAMENTO, e.id, e.nome)
            for e in EQUIPAMENTOS
            if e.pressuposto
        ] + [
            self._da_toda_cozinha(TipoDeItem.TECNICA, t.id, t.nome)
            for t in TECNICAS
            if t.pressuposta
        ]
        a_confirmar = sum(1 for i in itens if i["status"] == "suposto")
        return {
            "titulo": "O que toda cozinha tem",
            "texto": (
                "Eu supus que a senhora tem estas coisas e faz estes pratos do dia a dia. "
                "Confirme para eu ter certeza antes de qualquer compra."
                if a_confirmar
                else "A senhora já me disse de tudo isso."
            ),
            "a_confirmar": a_confirmar,
            "a_confirmar_texto": contagem(a_confirmar, "para confirmar", "para confirmar"),
            "tudo_confirmado": a_confirmar == 0,
            "itens": itens,
        }

    def _da_toda_cozinha(self, tipo: TipoDeItem, id_: str, nome: str) -> dict[str, Any]:
        de_ter = tipo is TipoDeItem.EQUIPAMENTO
        posse = self.perfil.tem_equipamento(id_) if de_ter else self.perfil.domina_tecnica(id_)
        if self.perfil.suposto(id_):
            status, texto = "suposto", "suposto: confirme"
        elif posse is Posse.TEM:
            status, texto = "confirmado", "a senhora tem" if de_ter else "a senhora faz"
        elif posse is Posse.NAO_TEM:
            status, texto = "nao_da", "a senhora não tem" if de_ter else "a senhora não faz"
        else:
            nao_sei = self._atualizacao(tipo, id_)["nao_sei"]
            status, texto = "falta_saber", "a senhora não sabe" if nao_sei else "falta saber"
        return {
            "tipo": tipo.value,
            "id": id_,
            "nome": nome,
            "imagem": self._imagem(id_),
            "estado": posse.value,
            "status": status,
            "status_texto": texto,
        }

    def restricao(self, campo: str) -> dict[str, Any]:
        formato = FORMATOS_OPERACIONAIS[campo]
        valor = getattr(self.perfil.restricoes, campo)
        saida: dict[str, Any] = {"valor": valor, "tipo": formato.tipo.value}
        if formato.tipo is TipoDeCampo.HORAS:
            # Guardado em minutos, mostrado e pedido em horas ("1,5 hora").
            saida = {
                **entrada_da_restricao(formato),
                "valor": float(em_horas(valor)) if valor is not None else None,
                "valor_texto": horas_texto(valor) if valor is not None else None,
            }
        elif formato.tipo is TipoDeCampo.INTEIRO:
            saida |= {"unidade": formato.unidade, "min": formato.minimo, "max": formato.maximo}
        return {
            **saida,
            "pergunta": PERGUNTAS_OPERACIONAIS[campo],
            **self._atualizacao(TipoDeItem.OPERACIONAL, campo),
        }

    def _imagem(self, id_: str) -> dict[str, str] | None:
        """A miniatura do Commons pelo proxy (`{url, credito}`), ou `None`: fica o ícone."""
        foto = self.fotos.get(id_)
        return foto.para_tela() if foto is not None else None

    def _afetadas(self, tipo: str, id_: str) -> dict[str, Any]:
        """Quantas receitas em avaliação pedem o item, em número e em texto ("1 receita")."""
        n = self.afetadas[(tipo, id_)]
        return {
            "receitas_afetadas": n,
            "receitas_afetadas_texto": contagem(n, "receita", "receitas"),
        }

    def _atualizacao(self, tipo: TipoDeItem, campo: str) -> dict[str, Any]:
        """Quem mudou por último e quando; `nao_sei` quando a última resposta foi "não sei"."""
        evento = self.ultimos.get((tipo, campo))
        if evento is None:
            return {"atualizado_por": None, "atualizado_texto": None, "nao_sei": False}
        return {
            "atualizado_por": evento.canal.value,
            "atualizado_texto": perfil_historico.quando_texto(evento.registrado, self.agora),
            "nao_sei": evento.nao_sei,
        }


__all__ = [
    "ConfirmacaoDaCozinha",
    "EstadoDoItem",
    "ItemAConfirmar",
    "ValorDaRestricao",
    "roteador",
]
