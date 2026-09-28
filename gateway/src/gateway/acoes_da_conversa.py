"""Os botões dos cards: o backend registra primeiro, pelo motor, e só depois conta ao agente.

Quando ela aperta "Tenho forno" ou "Vou cobrar este" num card, o turno chega com
uma `acao`. Deixar o agente registrar a partir do texto seria pedir ao modelo
que chame a ferramenta certa com o argumento certo, e uma segunda vez se ela
reenviar. Então a ação é executada aqui, de forma determinística, pela mesma
porta que a tela usa (`Sessao.responder`, `Sessao.decidir`, com o portão e o
auditor no caminho), e o agente recebe na mensagem o que já ficou gravado, para
não gravar de novo.

- `responder`: a resposta a uma pergunta da cozinha (equipamento, técnica,
  rotina) ou o gosto por um prato. Com `receita_id`, é a correção dela num
  valor que a receita trouxe estimado (o item parecido, a medida, o
  rendimento), gravada na receita pela porta da tela
  (`Sessao.responder_sobre_a_receita`).
- `decidir`: o aceite, a recusa ou o adiamento de um prato. O `id_cliente` do
  turno é a chave de idempotência: o reenvio do mesmo clique não grava duas vezes.
- `avaliar`: o gosto, as estrelas e as notas dela sobre uma receita, pela
  mesma porta da tela (`Sessao.registrar_avaliacao`): o gosto vai para a
  conferência, e a pontuação sai do motor, com a conta.

O que vai para o agente nunca leva dinheiro: texto que o backend acrescenta à
mensagem dela conta como fala dela para o guard-rail, e um valor ali passaria a
ter procedência sem ter vindo do motor. O que vai para ela (`texto`) vem do
motor, e pode levar o preço que ela escolheu.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from gateway.cartoes import PRECO_MAXIMO, TAMANHO_DO_NOME, Cartao

if TYPE_CHECKING:
    from mise.mcp_server import Sessao

logger = logging.getLogger(__name__)

#: Dinheiro, para tirar do que vai ao agente: "R$ 12,50", "US$ 3", "6 reais".
_DINHEIRO: Final = re.compile(
    r"(?:[a-z]{1,2})?\$\s*\d(?:[\d.,]*\d)?|\b\d(?:[\d.,]*\d)?\s*(?:reais|real)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ResultadoDaAcao:
    """O que a ação fez: para ela, para o agente e para a tela."""

    ok: bool
    #: Para ela, em pt-BR, sem jargão.
    texto: str
    #: Para o agente, sem dinheiro: vai no fim da mensagem dela, entre colchetes.
    nota: str
    #: O card do que mudou, para o resolvedor montar (`None` se não há).
    cartao: Cartao | None = None
    #: O que a tela precisa recarregar.
    recursos: tuple[str, ...] = field(default=())


Executor = Callable[["Sessao", Mapping[str, Any], str], ResultadoDaAcao]


class AcaoInvalida(ValueError):
    """A ação veio sem o que precisa, ou com o que não se aceita."""


def sem_dinheiro(texto: str) -> str:
    """O texto sem nenhum valor em reais: "…" no lugar."""
    return _DINHEIRO.sub("…", texto)


def _texto(acao: Mapping[str, Any], campo: str) -> str:
    valor = acao.get(campo)
    if not isinstance(valor, str) or not valor.strip() or len(valor) > TAMANHO_DO_NOME:
        raise AcaoInvalida(f"a ação precisa de {campo}")
    return " ".join(valor.split())


def _cartao(tipo_cartao: str, rota: str, **parametros: str | float) -> Cartao:
    return {"tipo_cartao": tipo_cartao, "ref": {"rota": rota, "parametros": dict(parametros)}}


# --------------------------------------------------------------------------- #
# responder                                                                    #
# --------------------------------------------------------------------------- #


def _nome_do_campo(tipo: str, campo: str) -> str:
    from mise.perfil import PERGUNTAS_OPERACIONAIS  # noqa: PLC0415
    from mise.taxonomia import EQUIPAMENTOS_POR_ID, TECNICAS_POR_ID  # noqa: PLC0415

    if tipo == "equipamento" and campo in EQUIPAMENTOS_POR_ID:
        return EQUIPAMENTOS_POR_ID[campo].nome.lower()
    if tipo == "tecnica" and campo in TECNICAS_POR_ID:
        return TECNICAS_POR_ID[campo].nome.lower()
    if tipo == "operacional" and campo in PERGUNTAS_OPERACIONAIS:
        return campo.replace("_", " ")
    return campo


def _anotado(tipo: str, campo: str, resposta: str) -> str:
    """O que ela vê no card da ação ("Anotei: a senhora tem forno.")."""
    nome = _nome_do_campo(tipo, campo)
    sim = resposta.strip().lower() in {"sim", "tem", "tenho", "s", "gosta", "gosto"}
    if tipo == "equipamento":
        return f"Anotei: a senhora {'tem' if sim else 'não tem'} {nome}."
    if tipo == "tecnica":
        return f"Anotei: a senhora {'sabe' if sim else 'não sabe'} fazer {nome}."
    if tipo == "gosto":
        return f"Anotei que a senhora {'gosta' if sim else 'não gosta'} de fazer {campo}."
    return f"Anotei a resposta da senhora sobre {nome}: {resposta}."


def _responder_na_receita(
    sessao: Sessao, receita_id: str, campo: str, resposta: str
) -> ResultadoDaAcao:
    """A resposta a uma pergunta da própria receita: fica gravada nela, e o card dela se refaz."""
    completa = sessao.responder_sobre_a_receita(receita_id, campo, resposta)
    nota = sem_dinheiro(
        f"[a senhora já respondeu pela tela, sobre a receita {completa.nome}: "
        f"“{campo}” = {resposta}. Está gravado na receita; não registre de novo.]"
    )
    return ResultadoDaAcao(
        ok=True,
        texto=f"Anotei a resposta da senhora sobre “{campo}”, na receita {completa.nome}.",
        nota=nota,
        cartao=_cartao("viabilidade", "/api/receitas/{slug}", receita_id=completa.slug),
        recursos=("receitas", "atividades"),
    )


def executar_responder(sessao: Sessao, acao: Mapping[str, Any], _chave: str) -> ResultadoDaAcao:
    tipo = _texto(acao, "tipo_pergunta").lower()
    campo = _texto(acao, "campo")
    resposta = _texto(acao, "resposta")
    if acao.get("receita_id") is not None:
        return _responder_na_receita(sessao, _texto(acao, "receita_id"), campo, resposta)
    sessao.responder(tipo, campo, resposta)
    nota = sem_dinheiro(
        f"[a senhora já respondeu pela tela: {tipo} {campo} = {resposta}. "
        "Está gravado; não registre de novo.]"
    )
    if tipo == "gosto":
        return ResultadoDaAcao(
            ok=True,
            texto=_anotado(tipo, campo, resposta),
            nota=nota,
            recursos=("receitas", "atividades"),
        )
    return ResultadoDaAcao(
        ok=True,
        texto=_anotado(tipo, campo, resposta),
        nota=nota,
        cartao=_cartao("cozinha_atualizada", "/api/perfil", tipo=tipo, campo=campo),
        recursos=("perfil", "receitas", "atividades"),
    )


# --------------------------------------------------------------------------- #
# decidir                                                                      #
# --------------------------------------------------------------------------- #


def _preco(acao: Mapping[str, Any]) -> float | None:
    valor = acao.get("preco")
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, int | float):
        raise AcaoInvalida("o preço tem que ser um número")
    if not 0 < valor <= PRECO_MAXIMO:
        raise AcaoInvalida("o preço está fora do que um prato custa")
    return float(valor)


def executar_decidir(sessao: Sessao, acao: Mapping[str, Any], chave: str) -> ResultadoDaAcao:
    from mise.dossie import Canal  # noqa: PLC0415

    prato = _texto(acao, "prato")
    decisao = _texto(acao, "decisao").lower()
    preco = _preco(acao)
    # Um botão da conversa é ela decidindo na conversa: o histórico diz "pela conversa".
    registro, detalhes = sessao.decidir(
        prato, decisao, "", preco, chave=chave, canal=Canal.CONVERSA
    )
    nome, valor = registro.prato, registro.decisao.value
    if valor == "aceito":
        texto = f"Anotado: {nome} entra no cardápio a {detalhes.get('preco', 'esse preço')}."
        if detalhes.get("da_prejuizo") and detalhes.get("aviso"):
            texto += f" {detalhes['aviso']}"
        nota = (
            f"[a senhora já decidiu pela tela: aceitou {nome} no cardápio, pelo preço que "
            "escolheu. Está gravado; não registre de novo.]"
        )
    elif valor == "recusado":
        texto = f"Anotado: {nome} fica fora do cardápio."
        nota = (
            f"[a senhora já decidiu pela tela: recusou {nome}. Está gravado; não registre de novo.]"
        )
    else:
        texto = f"Anotado: a senhora vai pensar mais sobre {nome}."
        nota = (
            f"[a senhora já decidiu pela tela: adiou {nome}. Está gravado; não registre de novo.]"
        )
    return ResultadoDaAcao(
        ok=True,
        texto=texto,
        nota=sem_dinheiro(nota),
        cartao=_cartao("decisao", "/api/cardapio", prato=nome),
        recursos=("cardapio", "receitas", "atividades"),
    )


# --------------------------------------------------------------------------- #
# avaliar                                                                      #
# --------------------------------------------------------------------------- #


def _do_gosto(gosta: object) -> str:
    if gosta is True:
        return "gosta de fazer"
    if gosta is False:
        return "não gosta de fazer"
    return "ainda não disse se gosta"


def executar_avaliar(sessao: Sessao, acao: Mapping[str, Any], _chave: str) -> ResultadoDaAcao:
    receita_id = _texto(acao, "receita_id")
    muda_o_gosto = "gosta" in acao
    gosta = acao.get("gosta")
    if gosta is not None and not isinstance(gosta, bool):
        raise AcaoInvalida("o gosto tem que ser sim, não ou em branco")
    estrelas = acao.get("estrelas")
    if estrelas is not None and not isinstance(estrelas, dict):
        raise AcaoInvalida("as estrelas vêm por categoria")
    notas = acao.get("notas")
    if notas is not None and not isinstance(notas, str):
        raise AcaoInvalida("as notas são texto")
    resposta = sessao.registrar_avaliacao(
        receita_id, gosta=gosta, muda_o_gosto=muda_o_gosto, estrelas=estrelas, notas=notas
    )
    partes = []
    if muda_o_gosto:
        partes.append(_do_gosto(gosta))
    if estrelas:
        partes.append(
            "estrelas "
            + ", ".join(f"{c} {'apagada' if v is None else v}" for c, v in estrelas.items())
        )
    if notas is not None:
        partes.append("anotação guardada")
    feito = "; ".join(partes) or "nada mudou"
    return ResultadoDaAcao(
        ok=True,
        texto=str(resposta["texto"]),
        nota=sem_dinheiro(
            f"[a senhora já avaliou pela tela a receita {resposta['nome']}: {feito}. "
            "Está gravado; não registre de novo.]"
        ),
        cartao=_cartao(
            "avaliacao_da_receita", "/api/receitas/{slug}/avaliacao", receita_id=resposta["slug"]
        ),
        recursos=("receitas", "avaliacoes", "atividades"),
    )


#: Os executores por tipo de ação.
EXECUTORES: Final[dict[str, Executor]] = {
    "responder": executar_responder,
    "decidir": executar_decidir,
    "avaliar": executar_avaliar,
}

_O_QUE_FAZ: Final[dict[str, str]] = {
    "responder": "registrar a resposta da senhora",
    "decidir": "registrar a decisão da senhora",
    "avaliar": "registrar a avaliação da receita",
}


def executar(sessao: Sessao, acao: Mapping[str, Any], chave: str) -> ResultadoDaAcao:
    """Executa a ação pelo motor. Nunca levanta: o que der errado vira `ok: false`."""
    from mise.erros import ContaNaoConfere, CozinhaNaoConfirmada, ErroMise  # noqa: PLC0415

    tipo = str(acao.get("tipo") or "")
    executor = EXECUTORES.get(tipo)
    if executor is None:
        return ResultadoDaAcao(
            ok=False,
            texto="Não reconheci esse botão; nada foi gravado.",
            nota="[a tela mandou um botão que o sistema não conhece; nada foi gravado.]",
        )
    o_que = _O_QUE_FAZ[tipo]
    try:
        return executor(sessao, acao, chave)
    except AcaoInvalida as erro:
        return ResultadoDaAcao(
            ok=False,
            texto=f"Não consegui {o_que}: o botão veio incompleto.",
            nota=sem_dinheiro(
                f"[a tela tentou {o_que}, mas o pedido veio incompleto ({erro}); nada foi gravado.]"
            ),
        )
    except ContaNaoConfere as erro:
        logger.warning("ação %s recusada pelo auditor: %s", tipo, erro)
        return ResultadoDaAcao(
            ok=False,
            texto=(
                "A conta não bateu na conferência, então não registrei. Vou refazer com a senhora."
            ),
            nota=sem_dinheiro(
                f"[a tela tentou {o_que} e a conferência independente recusou: "
                f"{erro.mensagem}. Nada foi gravado.]"
            ),
        )
    except CozinhaNaoConfirmada as erro:
        # A recusa já é a pergunta dela, uma só: vai para ela como veio, e o agente
        # recebe como gravar o sim.
        return ResultadoDaAcao(
            ok=False,
            texto=erro.pergunta,
            nota=sem_dinheiro(
                f"[a tela tentou {o_que}, e o aceite espera a senhora confirmar o que toda "
                f"cozinha tem e a receita usa. A pergunta já foi feita a ela: {erro.pergunta} "
                "Se ela confirmar, grave com registrar_resposta(tipo='cozinha', "
                f"campo='{erro.receita_id}', resposta='tem') e registre a decisão de novo. "
                "Nada foi gravado.]"
            ),
        )
    except ErroMise as erro:
        # A mensagem do motor é escrita para o agente ("pergunte de novo a ela",
        # nome de ferramenta): ela lê a frase geral, e o agente explica com a nota.
        return ResultadoDaAcao(
            ok=False,
            texto=f"Não consegui {o_que} agora.",
            nota=sem_dinheiro(
                f"[a tela tentou {o_que} e o sistema recusou: {erro.mensagem}. Nada foi gravado.]"
            ),
        )


__all__ = [
    "EXECUTORES",
    "AcaoInvalida",
    "Executor",
    "ResultadoDaAcao",
    "executar",
    "executar_avaliar",
    "executar_decidir",
    "executar_responder",
    "sem_dinheiro",
]
