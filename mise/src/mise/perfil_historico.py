"""O histórico da cozinha dela: cada resposta que mudou o perfil, por onde chegou.

O perfil em si é um instantâneo: `Dossie.salvar_perfil` sobrescreve a linha, e é
isso que o portão lê. Basta para decidir, mas não diz quem mudou o quê. A tela
precisa dizer "atualizado pela conversa, hoje às 09:12" ao lado do forno, e o
histórico precisa contar que ela disse "não tenho" pela tela e depois "não sei"
pela conversa. Por isso cada mudança vira uma linha em `perfil_eventos`, com o
valor de antes, o de depois e o canal.

Duas regras:

**Ler, mudar e gravar numa transação só.** A tela e a conversa gravam no mesmo
arquivo, de processos diferentes. Carregar o perfil, mudar um item e salvar em
três comandos soltos deixava a resposta de uma porta apagar a da outra (as duas
liam o mesmo perfil e a última a salvar vencia). `transacao()` segura a escrita
do começo ao fim.

**Só o que mudou vira evento.** Repetir a mesma resposta (o clique duplo, o
agente gravando de novo) não enche o histórico nem muda o "atualizado por".
Confirmar o que era suposto é mudança: o fogão passa de suposto a dito por ela.
E "não sei" é mudança mesmo quando o item já estava em aberto: de "ninguém
perguntou" para "perguntei, e ela não sabe", que é o que impede o agente de
insistir. Dois "não sei" seguidos são um só.

O impacto de uma mudança (`impacto_nas_receitas`) reavalia as receitas em
avaliação com o perfil de antes e o de depois, pelo mesmo portão, e diz quais
passaram a dar, quais deixaram de dar e quais continuam dependendo de uma resposta.
As receitas do catálogo que ela ainda não pôs em avaliação entram também, pela
conferência da cozinha (sem o gosto), que é a que decide a aba da grade: conta
a que muda de aba. O veredito é o do portão: aqui só se compara.
"""

from __future__ import annotations

import json
import sqlite3
import weakref
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

from mise.dossie import Canal
from mise.erros import ErroDeUso
from mise.perfil import PERGUNTAS_OPERACIONAIS, PerfilCozinha, Posse, contagem, horas_texto
from mise.taxonomia import equipamento, tecnica
from mise.viabilidade import Veredito

if TYPE_CHECKING:
    from mise.dossie import Dossie
    from mise.mcp_server import Sessao
    from mise.receita import Receita
    from mise.viabilidade import Avaliacao

ESQUEMA: Final = """
CREATE TABLE IF NOT EXISTS perfil_eventos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo        TEXT NOT NULL,
    campo       TEXT NOT NULL,
    antes       TEXT NOT NULL,
    depois      TEXT NOT NULL,
    nao_sei     INTEGER NOT NULL DEFAULT 0,
    canal       TEXT NOT NULL,
    registrado  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_perfil_eventos_item ON perfil_eventos(tipo, campo, id);
"""

#: O fuso dela, para "hoje" e "ontem". Brasília não tem horário de verão desde
#: 2019; um deslocamento fixo dispensa a base de fusos, que a imagem enxuta não tem.
FUSO_DELA: Final = timezone(timedelta(hours=-3))

#: Quantos nomes de receita o texto do impacto cita antes de resumir em "e mais N".
_NOMES_NO_TEXTO: Final = 3


class TipoDeItem(StrEnum):
    """Que parte da cozinha mudou: os mesmos tipos das perguntas do portão."""

    EQUIPAMENTO = "equipamento"
    TECNICA = "tecnica"
    OPERACIONAL = "operacional"


@dataclass(frozen=True, slots=True)
class EventoDoPerfil:
    """Uma mudança no perfil: o item, o valor de antes e o de depois, e por onde veio.

    `antes` e `depois` são `{"estado", "suposto"}` para equipamento e técnica e
    `{"valor"}` para restrição. `nao_sei` marca que a mudança foi ela dizer "não
    sei": o item voltou ao padrão, e isso não é a mesma coisa que ninguém ter
    perguntado.
    """

    id: int
    tipo: TipoDeItem
    campo: str
    antes: dict[str, Any]
    depois: dict[str, Any]
    nao_sei: bool
    canal: Canal
    registrado: datetime

    @property
    def texto(self) -> str:
        """O que mudou, dito para ela: "a senhora disse que tem forno"."""
        if self.tipo is TipoDeItem.OPERACIONAL:
            return f"a senhora disse que {_restricao_em_palavras(self.campo, self.depois)}"
        if self.tipo is TipoDeItem.EQUIPAMENTO:
            item = f"tem {equipamento(self.campo).nome.lower()}"
        else:
            item = f"tem prática com {tecnica(self.campo).nome.lower()}"
        if self.nao_sei:
            return f"a senhora disse que não sabe se {item}"
        if self.depois.get("estado") == Posse.NAO_TEM.value:
            return f"a senhora disse que não {item}"
        return f"a senhora disse que {item}"


@dataclass(frozen=True, slots=True)
class MudancaNoPerfil:
    """O perfil antes e depois de uma resposta, e o evento gravado (`None` se nada mudou)."""

    tipo: TipoDeItem
    campo: str
    antes: PerfilCozinha
    depois: PerfilCozinha
    nao_sei: bool
    evento: EventoDoPerfil | None

    @property
    def mudou(self) -> bool:
        return self.evento is not None


@dataclass(frozen=True, slots=True)
class Impacto:
    """O que uma mudança na cozinha muda nas receitas em avaliação.

    `liberadas` passaram a dar (com ou sem compra); `bloqueadas` deixaram de dar;
    `pendentes` continuam dependendo de uma resposta dela, mas o quadro mudou:
    voltaram a depender de uma pergunta, ganharam uma pergunta nova (sem forno,
    a da air fryer) ou tiveram uma resolvida e ainda esperam outra. Receita em
    que nada mudou não entra em lista nenhuma.
    """

    texto: str
    liberadas: tuple[str, ...] = ()
    bloqueadas: tuple[str, ...] = ()
    pendentes: tuple[str, ...] = ()

    def para_json(self) -> dict[str, Any]:
        return {
            "liberadas": list(self.liberadas),
            "bloqueadas": list(self.bloqueadas),
            "pendentes": list(self.pendentes),
            "texto": self.texto,
        }


# --------------------------------------------------------------------------- #
# Esquema
# --------------------------------------------------------------------------- #

#: Dossiês que já têm a tabela, para não refazer o `CREATE` a cada leitura.
_COM_ESQUEMA: Final[weakref.WeakSet[Dossie]] = weakref.WeakSet()


def garantir(dossie: Dossie) -> None:
    """Cria `perfil_eventos` no dossiê, uma vez por conexão aberta. Idempotente."""
    if dossie in _COM_ESQUEMA:
        return
    dossie.garantir_esquema(ESQUEMA)
    _COM_ESQUEMA.add(dossie)


# --------------------------------------------------------------------------- #
# Mudanças
# --------------------------------------------------------------------------- #


def mudar_item(
    dossie: Dossie,
    tipo: TipoDeItem,
    id_: str,
    posse: Posse | None,
    canal: Canal | str,
) -> MudancaNoPerfil:
    """Grava o que ela disse de um equipamento ou técnica. `None` é "não sei".

    "Tem" e "não tem" contam como resposta dela (`confirmados`). "Não sei" volta
    o item ao padrão da taxonomia e o tira de `confirmados`: o portão pergunta de
    novo quando uma receita precisar.
    """
    if tipo is TipoDeItem.OPERACIONAL:
        raise ErroDeUso("restrição muda por mudar_restricao, não por mudar_item", campo=id_)
    # Valida o vocabulário antes de abrir a transação: o id errado é erro de quem chamou.
    if tipo is TipoDeItem.EQUIPAMENTO:
        equipamento(id_)
    else:
        tecnica(id_)

    def aplicar(perfil: PerfilCozinha) -> PerfilCozinha:
        if posse is None:
            return perfil.sem_resposta(id_)
        if tipo is TipoDeItem.EQUIPAMENTO:
            return perfil.com_equipamento(id_, posse)
        return perfil.com_tecnica(id_, posse)

    return _mudar(dossie, tipo, id_, aplicar, nao_sei=posse is None, canal=canal)


def confirmar_itens(
    dossie: Dossie, itens: Sequence[tuple[TipoDeItem, str]], canal: Canal | str
) -> tuple[MudancaNoPerfil, ...]:
    """Ela confirma de uma vez que tem, ou faz, cada um destes itens.

    É o "Tenho tudo isso" do que toda cozinha tem, e a confirmação que o aceite
    pede: cada item vira "tem", dito por ela, pelo mesmo `mudar_item` de uma
    resposta sozinha, com o evento no histórico e o canal. Tudo numa transação:
    ou fica tudo gravado, ou nada. O que ela já tinha confirmado não vira evento.
    """
    for tipo, id_ in itens:
        if tipo is TipoDeItem.OPERACIONAL:
            raise ErroDeUso("só equipamento e técnica se confirmam assim", campo=id_)
        if tipo is TipoDeItem.EQUIPAMENTO:
            equipamento(id_)
        else:
            tecnica(id_)
    # O esquema antes da transação: criar tabela fecha a transação em aberto.
    garantir(dossie)
    with dossie.transacao():
        return tuple(mudar_item(dossie, tipo, id_, Posse.TEM, canal) for tipo, id_ in itens)


def mudar_restricao(
    dossie: Dossie, campo: str, valor: int | bool | None, canal: Canal | str
) -> MudancaNoPerfil:
    """Grava uma restrição da rotina dela. `None` é "não sei": volta a ninguém ter perguntado."""
    if campo not in PERGUNTAS_OPERACIONAIS:
        raise ErroDeUso(f"restrição operacional {campo!r} desconhecida", campo=campo)
    return _mudar(
        dossie,
        TipoDeItem.OPERACIONAL,
        campo,
        lambda perfil: perfil.com_restricao(campo, valor),
        nao_sei=valor is None,
        canal=canal,
    )


def _mudar(
    dossie: Dossie,
    tipo: TipoDeItem,
    campo: str,
    aplicar: Callable[[PerfilCozinha], PerfilCozinha],
    *,
    nao_sei: bool,
    canal: Canal | str,
) -> MudancaNoPerfil:
    de_onde = _canal(canal)
    garantir(dossie)
    evento: EventoDoPerfil | None = None
    with dossie.transacao() as cur:
        antes = dossie.carregar_perfil()
        depois = aplicar(antes)
        valor_antes = valor_do_item(antes, tipo, campo)
        valor_depois = valor_do_item(depois, tipo, campo)
        mudou_o_valor = valor_antes != valor_depois
        if mudou_o_valor or (nao_sei and not _ultimo_foi_nao_sei(cur, tipo, campo)):
            if mudou_o_valor:
                dossie.salvar_perfil(depois)
            evento = _inserir(
                cur,
                dossie,
                tipo=tipo,
                campo=campo,
                antes=valor_antes,
                depois=valor_depois,
                nao_sei=nao_sei,
                canal=de_onde,
            )
    return MudancaNoPerfil(tipo, campo, antes, depois, nao_sei, evento)


def _ultimo_foi_nao_sei(cur: sqlite3.Cursor, tipo: TipoDeItem, campo: str) -> bool:
    linha = cur.execute(
        "SELECT nao_sei FROM perfil_eventos WHERE tipo = ? AND campo = ? ORDER BY id DESC LIMIT 1",
        (tipo.value, campo),
    ).fetchone()
    return linha is not None and bool(linha["nao_sei"])


def _inserir(
    cur: sqlite3.Cursor,
    dossie: Dossie,
    *,
    tipo: TipoDeItem,
    campo: str,
    antes: dict[str, Any],
    depois: dict[str, Any],
    nao_sei: bool,
    canal: Canal,
) -> EventoDoPerfil:
    quando = dossie.agora()
    cur.execute(
        "INSERT INTO perfil_eventos (tipo, campo, antes, depois, nao_sei, canal, registrado) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            tipo.value,
            campo,
            json.dumps(antes, ensure_ascii=False),
            json.dumps(depois, ensure_ascii=False),
            int(nao_sei),
            canal.value,
            quando.isoformat(),
        ),
    )
    assert cur.lastrowid is not None
    return EventoDoPerfil(cur.lastrowid, tipo, campo, antes, depois, nao_sei, canal, quando)


def valor_do_item(perfil: PerfilCozinha, tipo: TipoDeItem, campo: str) -> dict[str, Any]:
    """O estado de um item como vai para o histórico: o que muda quando ela responde."""
    if tipo is TipoDeItem.OPERACIONAL:
        return {"valor": getattr(perfil.restricoes, campo)}
    if tipo is TipoDeItem.EQUIPAMENTO:
        posse = perfil.tem_equipamento(campo)
    else:
        posse = perfil.domina_tecnica(campo)
    return {"estado": posse.value, "suposto": perfil.suposto(campo)}


def _canal(canal: Canal | str) -> Canal:
    try:
        return Canal(canal)
    except ValueError:
        validos = ", ".join(c.value for c in Canal)
        raise ErroDeUso(f"canal desconhecido: {canal}", validos=validos) from None


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #


def eventos(dossie: Dossie, limite: int | None = None) -> tuple[EventoDoPerfil, ...]:
    """As mudanças no perfil, da mais recente para a mais antiga."""
    garantir(dossie)
    sql = "SELECT * FROM perfil_eventos ORDER BY id DESC"
    parametros: tuple[int, ...] = ()
    if limite is not None:
        sql += " LIMIT ?"
        parametros = (limite,)
    with dossie.cursor() as cur:
        return tuple(_para_evento(linha) for linha in cur.execute(sql, parametros))


def ultimos_por_item(dossie: Dossie) -> dict[tuple[TipoDeItem, str], EventoDoPerfil]:
    """A última mudança de cada item: é ela que diz "atualizado por" na tela."""
    garantir(dossie)
    with dossie.cursor() as cur:
        linhas = cur.execute(
            "SELECT e.* FROM perfil_eventos AS e JOIN ("
            "  SELECT MAX(id) AS id FROM perfil_eventos GROUP BY tipo, campo"
            ") AS u ON e.id = u.id"
        ).fetchall()
    return {(evento.tipo, evento.campo): evento for evento in map(_para_evento, linhas)}


def _para_evento(linha: sqlite3.Row) -> EventoDoPerfil:
    return EventoDoPerfil(
        id=linha["id"],
        tipo=TipoDeItem(linha["tipo"]),
        campo=linha["campo"],
        antes=json.loads(linha["antes"]),
        depois=json.loads(linha["depois"]),
        nao_sei=bool(linha["nao_sei"]),
        canal=Canal(linha["canal"]),
        registrado=datetime.fromisoformat(linha["registrado"]),
    )


def quando_texto(momento: datetime, agora: datetime) -> str:
    """A data como ela lê: "hoje, 09:12", "ontem, 18:40", "12/09, 14:32".

    Pronta para a tela, que não formata data: formatar no navegador trocava o
    fuso e fazia a hidratação discordar do servidor.
    """
    local = _com_fuso(momento).astimezone(FUSO_DELA)
    hoje = _com_fuso(agora).astimezone(FUSO_DELA).date()
    hora = local.strftime("%H:%M")
    if local.date() == hoje:
        return f"hoje, {hora}"
    if local.date() == hoje - timedelta(days=1):
        return f"ontem, {hora}"
    if local.year == hoje.year:
        return f"{local:%d/%m}, {hora}"
    return f"{local:%d/%m/%Y}, {hora}"


def _com_fuso(momento: datetime) -> datetime:
    """Data sem fuso é UTC: é como o dossiê grava."""
    return momento if momento.tzinfo is not None else momento.replace(tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Impacto nas receitas
# --------------------------------------------------------------------------- #


def receitas_em_avaliacao(sessao: Sessao) -> list[Receita]:
    """As receitas que uma mudança na cozinha pode mudar: as candidatas do dossiê.

    É o único lugar que decide isso: o impacto e a contagem de receitas afetadas
    de cada item (`GET /api/perfil`) leem daqui. O catálogo de receitas
    descobertas, quando existir, entra aqui também.
    """
    return list(sessao.candidatas.values())


@dataclass(frozen=True, slots=True)
class DaGrade:
    """Uma receita do catálogo fora de avaliação, e se ela disse que não quer fazê-la."""

    receita: Receita
    nao_quer: bool = False


def receitas_do_catalogo(sessao: Sessao) -> list[DaGrade]:
    """As receitas do catálogo que não estão em avaliação: as da grade, lidas só pela cozinha."""
    from mise.catalogo import chave_do_nome, id_da_receita  # noqa: PLC0415
    from mise.perfil import Gosto  # noqa: PLC0415

    em_avaliacao = {id_da_receita(r) for r in receitas_em_avaliacao(sessao)}
    nao_quer = {
        chave_do_nome(o.prato)
        for o in sessao.dossie.gostos()
        if o.gosto is Gosto.NAO_GOSTA or o.impedimento.strip()
    }
    return [
        DaGrade(g.receita, chave_do_nome(g.nome) in nao_quer)
        for g in sessao.catalogo.listar()
        if g.slug not in em_avaliacao
    ]


def _aba(veredito_da_cozinha: Veredito, nao_quer: bool) -> str | None:
    """A aba da grade (`mise.receitas_json`): a que a cozinha não permite não aparece."""
    if veredito_da_cozinha is Veredito.BLOQUEADO:
        return None
    if nao_quer:
        return "nao_quer"
    return "falta_resposta" if veredito_da_cozinha is Veredito.FALTA_INFO else "pode_fazer"


def impacto_nas_receitas(sessao: Sessao, mudanca: MudancaNoPerfil) -> Impacto:
    """O impacto da mudança nas receitas em avaliação e nas do catálogo, pelo portão da sessão."""
    return calcular_impacto(
        mudanca,
        receitas_em_avaliacao(sessao),
        lambda receita, perfil: sessao.avaliar(receita, perfil=perfil),
        do_catalogo=receitas_do_catalogo(sessao) if mudanca.mudou else (),
    )


def calcular_impacto(
    mudanca: MudancaNoPerfil,
    receitas: Sequence[Receita],
    avaliar: Callable[[Receita, PerfilCozinha], Avaliacao],
    *,
    do_catalogo: Sequence[DaGrade] = (),
) -> Impacto:
    """Reavalia cada receita com o perfil de antes e o de depois, e compara os vereditos.

    As receitas em avaliação comparam a conferência inteira (a que libera o
    preço); as do catálogo, só a da cozinha, que é a que muda a aba da grade.
    """
    if not mudanca.mudou:
        return Impacto("Isso já estava anotado assim; nada muda nas receitas.")
    if not receitas and not do_catalogo:
        return Impacto("Anotado. Ainda não há receita em avaliação para conferir com isso.")

    liberadas: list[str] = []
    bloqueadas: list[str] = []
    pendentes: list[str] = []
    for receita in receitas:
        antes = avaliar(receita, mudanca.antes)
        depois = avaliar(receita, mudanca.depois)
        if depois.permite_precificar and not antes.permite_precificar:
            liberadas.append(receita.nome)
        elif depois.veredito is Veredito.BLOQUEADO and antes.veredito is not Veredito.BLOQUEADO:
            bloqueadas.append(receita.nome)
        elif depois.veredito is Veredito.FALTA_INFO and (
            antes.veredito is not Veredito.FALTA_INFO or _chaves(depois) != _chaves(antes)
        ):
            pendentes.append(receita.nome)
    for da_grade in do_catalogo:
        receita = da_grade.receita
        antes_aba = _aba(avaliar(receita, mudanca.antes).veredito_da_cozinha, da_grade.nao_quer)
        depois_aba = _aba(avaliar(receita, mudanca.depois).veredito_da_cozinha, da_grade.nao_quer)
        if depois_aba == antes_aba:
            continue
        if depois_aba is None:
            bloqueadas.append(receita.nome)
        elif depois_aba == "falta_resposta":
            pendentes.append(receita.nome)
        else:
            liberadas.append(receita.nome)

    return Impacto(
        _texto_do_impacto(
            _causa(mudanca), liberadas, bloqueadas, pendentes, com_catalogo=bool(do_catalogo)
        ),
        tuple(liberadas),
        tuple(bloqueadas),
        tuple(pendentes),
    )


def _chaves(avaliacao: Avaliacao) -> set[tuple[str, str]]:
    return {(p.tipo.name, p.campo) for p in avaliacao.perguntas}


def _causa(mudanca: MudancaNoPerfil) -> str:
    """ "Sem forno, " ou "Com forno, ": só para equipamento, que é coisa que se tem."""
    if mudanca.tipo is not TipoDeItem.EQUIPAMENTO or mudanca.nao_sei:
        return ""
    nome = equipamento(mudanca.campo).nome.lower()
    posse = mudanca.depois.tem_equipamento(mudanca.campo)
    return f"sem {nome}, " if posse is Posse.NAO_TEM else f"com {nome}, "


def _texto_do_impacto(
    causa: str,
    liberadas: Sequence[str],
    bloqueadas: Sequence[str],
    pendentes: Sequence[str],
    *,
    com_catalogo: bool = False,
) -> str:
    partes = []
    if liberadas:
        partes.append(f"{_lista(liberadas)} {_conjugar(liberadas, 'passa', 'passam')} a dar")
    if bloqueadas:
        partes.append(f"{_lista(bloqueadas)} {_conjugar(bloqueadas, 'deixa', 'deixam')} de dar")
    if pendentes:
        partes.append(
            f"{_lista(pendentes)} {_conjugar(pendentes, 'fica', 'ficam')} "
            "dependendo de uma resposta da senhora"
        )
    if not partes:
        if com_catalogo:
            return "Anotado. Nenhuma receita muda com isso."
        return "Anotado. Nenhuma receita em avaliação muda com isso."
    frase = causa + "; ".join(partes) + "."
    return frase[:1].upper() + frase[1:]


def _lista(nomes: Sequence[str]) -> str:
    """ "A", "A e B", "A, B e C", "A, B, C e mais 1 receita", "… e mais 2 receitas"."""
    if len(nomes) > _NOMES_NO_TEXTO:
        resto = contagem(len(nomes) - _NOMES_NO_TEXTO, "receita", "receitas")
        return f"{', '.join(nomes[:_NOMES_NO_TEXTO])} e mais {resto}"
    if len(nomes) == 1:
        return nomes[0]
    return f"{', '.join(nomes[:-1])} e {nomes[-1]}"


def _conjugar(nomes: Sequence[str], singular: str, plural: str) -> str:
    return singular if len(nomes) == 1 else plural


# --------------------------------------------------------------------------- #
# Restrições em palavras
# --------------------------------------------------------------------------- #

#: O que ela respondeu de cada restrição, para o histórico. `{}` é o valor.
_RESTRICAO_DITA: Final[dict[str, tuple[str, str]]] = {
    "bocas_fogao": ("o fogão tem {} boca", "o fogão tem {} bocas"),
    "porcoes_por_fornada": ("monta {} marmita numa leva", "monta {} marmitas numa leva"),
    "espaco_geladeira_litros": (
        "cabe {} litro de preparo na geladeira",
        "cabem {} litros de preparo na geladeira",
    ),
    "energia_aparelhos_simultaneos": (
        "liga {} aparelho forte de cada vez",
        "liga {} aparelhos fortes ao mesmo tempo",
    ),
}

#: O que ela não sabe de cada restrição: "a senhora disse que não sabe …".
_RESTRICAO_NAO_SABIDA: Final[dict[str, str]] = {
    "bocas_fogao": "quantas bocas o fogão tem",
    "tempo_max_por_fornada_min": "quanto tempo consegue cozinhar de uma vez",
    "porcoes_por_fornada": "quantas marmitas monta numa leva",
    "espaco_geladeira_litros": "quanto espaço sobra na geladeira",
    "energia_aparelhos_simultaneos": "quantos aparelhos fortes liga ao mesmo tempo",
    "tem_gas_sobrando": "se tem botijão de gás de reserva",
}


def _restricao_em_palavras(campo: str, depois: dict[str, Any]) -> str:
    valor = depois.get("valor")
    if valor is None:
        return f"não sabe {_RESTRICAO_NAO_SABIDA[campo]}"
    if campo == "tem_gas_sobrando":
        return "tem botijão de gás de reserva" if valor else "não tem botijão de gás de reserva"
    if campo == "espaco_geladeira_litros" and valor == 0:
        return "não sobra espaço na geladeira"
    if campo == "energia_aparelhos_simultaneos" and valor == 0:
        return "não consegue ligar nenhum aparelho forte"
    if campo == "tempo_max_por_fornada_min":
        # Guardado em minutos, dito em horas, como ela respondeu.
        return f"consegue cozinhar {horas_texto(int(valor))} de uma vez"
    singular, plural = _RESTRICAO_DITA[campo]
    return (singular if valor == 1 else plural).format(valor)


def itens_que_ela_nao_sabe(ultimos: Iterable[EventoDoPerfil]) -> list[EventoDoPerfil]:
    """Os itens cuja última resposta foi "não sei": o agente não insiste neles."""
    return [e for e in ultimos if e.nao_sei]


def ela_disse_que_nao_sabe(dossie: Dossie, tipo: str, campo: str) -> bool:
    """A última resposta dela a este item foi "não sei"? Gosto e ingrediente não têm histórico."""
    try:
        chave = (TipoDeItem(tipo), campo)
    except ValueError:
        return False
    ultima = ultimos_por_item(dossie).get(chave)
    return ultima is not None and ultima.nao_sei


__all__ = [
    "ESQUEMA",
    "FUSO_DELA",
    "DaGrade",
    "EventoDoPerfil",
    "Impacto",
    "MudancaNoPerfil",
    "TipoDeItem",
    "calcular_impacto",
    "confirmar_itens",
    "ela_disse_que_nao_sabe",
    "eventos",
    "garantir",
    "impacto_nas_receitas",
    "itens_que_ela_nao_sabe",
    "mudar_item",
    "mudar_restricao",
    "quando_texto",
    "receitas_do_catalogo",
    "receitas_em_avaliacao",
    "ultimos_por_item",
    "valor_do_item",
]
