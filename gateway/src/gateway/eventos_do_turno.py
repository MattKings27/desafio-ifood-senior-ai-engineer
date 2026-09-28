"""Do stream do Hermes aos eventos que a tela desenha (contratos/web/LEIA.md).

O `chat/stream` do Hermes fala a língua dele: `assistant.delta`, `tool.started`
com o nome cru da ferramenta, o resumo do raciocínio em `tool.progress`, e um
texto final que o guard-rail já conferiu. O `Normalizador` traduz isso, evento
por evento, para o que a Dona Maria vê:

- `texto.parcial`: o rascunho, com todo valor em reais mascarado
  (`mascara.MascaraDeValores`). O texto que o agente escreve entre uma ferramenta
  e outra ("Agora vou conferir se a cozinha dela dá conta dessas três") é
  bastidor: não vira resposta, e o comentário que o Hermes manda à parte
  (`assistant.commentary`) não vai para a tela;
- `atividade.iniciada` e `atividade.concluida`: a linha do tempo, com as frases
  de `gateway.frases`. As ferramentas de bastidor (ler as próprias anotações,
  descrever ferramenta, lista de tarefas) não aparecem: não dizem nada a ela;
- `cartao`: no fim de cada chamada que deu certo, montado pelo
  `MontadorDeCartoes` com os dados do motor. O mesmo card no mesmo turno não se
  repete: se os dados mudaram (o orçamento depois de uma compra), sai de novo
  com o mesmo `cartao_id`, e a tela troca o antigo;
- `estado.alterado`: o que uma escrita mudou, para a tela recarregar;
- `texto.final` e `sugestoes`, no fim (`concluir`).

Nunca chegam à tela: o raciocínio (`tool.progress` / `_thinking`), as prévias de
ferramenta, o nome cru de ferramenta e o aviso em inglês do Hermes ("⚠️ …"),
que vira frase em pt-BR.

**O texto final** é só o que o agente escreveu depois da última ferramenta: a
resposta final (que o guard-rail confere), sem a nota de rodapé do guard-rail,
com cada valor conferido de novo contra o que tem procedência
(`retirar_sem_procedencia`). O que veio antes, entre as ferramentas, era o
agente narrando o próprio trabalho, às vezes na terceira pessoa ("a
cozinha dela"): fica de fora, e a linha do tempo já conta o que ele fez. Só
quando não vem texto nenhum depois da última ferramenta ("Vou anotar que a
senhora gosta", e a anotação) o último comentário é a resposta. O rascunho
guardado de um turno que não terminou também é só o trecho depois da última
ferramenta.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final

from gateway.cartoes import Cartao, cartao_para
from gateway.cartoes_da_conversa import (
    MontadorDeCartoes,
    dados_iguais,
    gerado_texto,
    sugestoes_para,
)
from gateway.conversas_db import EstadoDoTurno
from gateway.frases import frase_para, nome_da_ferramenta
from gateway.hermes_cliente import EventoSSE
from gateway.mascara import (
    REDACAO,
    MascaraDeValores,
    retirar_sem_procedencia,
    valores_com_cifrao,
)

logger = logging.getLogger(__name__)

#: Os tipos de evento que a tela conhece (contratos/web/LEIA.md).
TIPOS_DE_EVENTO: Final = frozenset(
    {
        "turno.iniciado",
        "acao.resultado",
        "atividade.iniciada",
        "atividade.concluida",
        "cartao",
        "texto.parcial",
        "texto.comentario",
        "texto.final",
        "estado.alterado",
        "sugestoes",
        "turno.concluido",
        "turno.cancelado",
        "turno.falhou",
    }
)

#: Ferramentas do próprio Hermes que só organizam o trabalho do agente: fora da linha do tempo.
FERRAMENTAS_DE_BASTIDOR: Final = frozenset(
    {
        "skill_view",
        "skills_list",
        "skill_manage",
        "tool_describe",
        "tool_search",
        "list_prompts",
        "get_prompt",
        "list_resources",
        "read_resource",
        "_thinking",
    }
)

#: O que cada escrita muda na tela. Ferramenta de escrita que não está aqui muda o histórico.
RECURSOS_DA_ESCRITA: Final[Mapping[str, tuple[str, ...]]] = {
    "registrar_resposta": ("perfil", "receitas", "atividades"),
    "registrar_preco_mercado": ("receitas", "precos", "atividades"),
    # O gosto é o mesmo da avaliação da receita: as duas telas mudam.
    "registrar_gosto": ("receitas", "avaliacoes", "atividades"),
    "registrar_decisao": ("cardapio", "receitas", "atividades"),
    "registrar_compra": ("orcamento", "despensa", "receitas", "atividades"),
    # Não mudam o dossiê de decisões: põem a receita em avaliação, guardam no
    # catálogo o que ela respondeu sobre ela, ou trazem uma receita nova.
    "avaliar_receita": ("receitas",),
    "buscar_receita_na_web": ("receitas",),
    # O preço achado entra na conta das receitas.
    "buscar_preco_na_web": ("receitas",),
    "atualizar_despensa": ("despensa", "orcamento", "receitas"),
    "registrar_avaliacao_da_receita": ("receitas", "avaliacoes", "cardapio", "atividades"),
}

#: As ferramentas do servidor `mise`, pelo prefixo que o Hermes põe (o mesmo do guard-rail).
_DO_MOTOR: Final = re.compile(r"^mcp_{1,2}mise_{1,2}\w+$")

#: A nota que o guard-rail acrescenta quando retira valor (`nota_rodape` do plugin):
#: "1 valor ... o número" ou "2 valores ... cada um". A forma antiga ("valor(es)")
#: continua reconhecida, para as conversas gravadas antes da mudança.
_NOTA_DO_GUARD_RAIL: Final = re.compile(
    r"\s*---\s*Tirei \d+ valor(?:\(es\)|es)? desta resposta que eu não consegui conferir na "
    r"conta do sistema\. Me peça de novo que eu trago (?:o número|cada um) com a conta "
    r"aberta\.\s*\Z"
)

#: O "(empty)" que o Hermes devolve quando o modelo não produziu nada.
_VAZIO: Final = frozenset({"", "(empty)"})

# --------------------------------------------------------------------------- #
# O que ela lê quando o turno não dá certo                                     #
# --------------------------------------------------------------------------- #

RECUSA: Final = (
    "Não consegui responder a esse pedido do jeito que ele veio. "
    "A senhora pode me contar de outro jeito?"
)
CONTEXTO_CHEIO: Final = (
    "Nossa conversa ficou comprida demais para eu acompanhar de uma vez. Na próxima mensagem "
    "eu continuo numa página nova, sem perder nada do que já foi anotado."
)
DEMOROU: Final = (
    "Demorei demais e parei no meio. O que já foi anotado continua anotado; "
    "a senhora pode perguntar de novo?"
)
OCUPADA: Final = "Estou atendendo muita coisa ao mesmo tempo agora. Tente de novo daqui a pouco."
SEM_ACESSO: Final = "Estou sem acesso ao meu serviço agora. Tente de novo daqui a pouco."
SEM_RESPOSTA: Final = (
    "Não consegui escrever a resposta desta vez. O que já foi anotado continua anotado; "
    "a senhora pode perguntar de novo?"
)
PROBLEMA: Final = (
    "Tive um problema do meu lado e não consegui responder. A senhora pode perguntar de novo?"
)
CONEXAO_CAIU: Final = (
    "A conexão caiu no meio da resposta. O que já foi anotado continua anotado; "
    "a senhora pode perguntar de novo?"
)
FORA_DO_AR: Final = (
    "Não consegui me conectar agora. As telas continuam funcionando; tente de novo daqui a pouco."
)
INTERROMPIDO: Final = (
    "Fui interrompido antes de terminar. A senhora pode mandar a mensagem de novo."
)


@dataclass(frozen=True, slots=True)
class Falha:
    """Por que o turno não terminou bem: a categoria do contrato e a frase para ela."""

    categoria: str
    mensagem: str
    #: A conversa precisa de sessão nova no Hermes (o contexto encheu).
    sessao_nova: bool = False


#: Os avisos do Hermes, pelo que dizem em inglês, e o que ela lê no lugar. O primeiro que
#: casa vale; o aviso que nenhum descreve vira `PROBLEMA`.
_AVISOS: Final[tuple[tuple[tuple[str, ...], Falha], ...]] = (
    (("safety", "refus", "declined"), Falha("consultora", RECUSA)),
    (("context window", "context is full"), Falha("consultora", CONTEXTO_CHEIO, sessao_nova=True)),
    (("liveness", "making progress", "aborted"), Falha("tempo", DEMOROU)),
    (("rate-limit", "rate limit"), Falha("consultora", OCUPADA)),
    (("authentication",), Falha("consultora", SEM_ACESSO)),
    (
        ("no reply", "no visible answer", "produce a reply", "budget"),
        Falha("consultora", SEM_RESPOSTA),
    ),
)


def traduzir_aviso(texto: str | None) -> Falha | None:
    """O aviso em inglês do Hermes ("⚠️ …") como frase em pt-BR; `None` se não é aviso."""
    limpo = (texto or "").strip()
    if not limpo.startswith("⚠"):
        return None
    baixo = limpo.casefold()
    for pistas, falha in _AVISOS:
        if any(pista in baixo for pista in pistas):
            return falha
    return Falha("consultora", PROBLEMA)


def sem_nota_do_guard_rail(texto: str) -> str:
    """O texto sem a nota de rodapé que o guard-rail acrescenta: a tela avisa do jeito dela."""
    return _NOTA_DO_GUARD_RAIL.sub("", texto)


def de_bastidor(ferramenta: str) -> bool:
    """A ferramenta só organiza o trabalho do agente: não entra na linha do tempo."""
    return ferramenta in FERRAMENTAS_DE_BASTIDOR or ferramenta.startswith("todo")


def recursos_da_escrita(ferramenta: str) -> tuple[str, ...]:
    """O que a tela recarrega depois desta chamada; nada, se ela só leu."""
    if ferramenta in RECURSOS_DA_ESCRITA:
        return RECURSOS_DA_ESCRITA[ferramenta]
    if ferramenta.startswith(("registrar_", "atualizar_")):
        return ("atividades",)
    return ()


def e_do_motor(ferramenta: object) -> bool:
    return isinstance(ferramenta, str) and bool(_DO_MOTOR.match(ferramenta))


def _conteudo(bruto: object) -> str:
    """O conteúdo de uma mensagem do Hermes como texto (texto, lista de partes ou JSON)."""
    if isinstance(bruto, str):
        return bruto
    if isinstance(bruto, list):
        return "\n".join(str(p.get("text") or "") if isinstance(p, dict) else str(p) for p in bruto)
    return "" if bruto is None else str(bruto)


def valores_do_motor(mensagens: Iterable[object]) -> tuple[Decimal, ...]:
    """Os valores em reais que as ferramentas do motor devolveram neste turno."""
    valores: list[Decimal] = []
    for mensagem in mensagens:
        if not isinstance(mensagem, dict) or mensagem.get("role") != "tool":
            continue
        if e_do_motor(mensagem.get("tool_name") or mensagem.get("name")):
            valores.extend(valores_com_cifrao(_conteudo(mensagem.get("content"))))
    return tuple(dict.fromkeys(valores))


def estimar_contexto(uso: object, mensagens: Iterable[object]) -> int:
    """O tamanho do contexto no fim do turno, em tokens, estimado pelo uso do turno.

    O Hermes devolve a soma dos tokens de entrada de todas as chamadas do turno,
    e cada chamada manda o contexto inteiro: a média por chamada (uma por
    mensagem do agente) é uma estimativa por baixo do tamanho atual.
    """
    entrada = uso.get("input_tokens") if isinstance(uso, dict) else None
    if not isinstance(entrada, int) or entrada <= 0:
        return 0
    chamadas = sum(1 for m in mensagens if isinstance(m, dict) and m.get("role") == "assistant")
    return entrada // max(1, chamadas)


# --------------------------------------------------------------------------- #
# O desfecho do turno                                                          #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Desfecho:
    estado: EstadoDoTurno
    #: O texto conferido; `None` quando o turno não terminou bem.
    texto_final: str | None
    retirados: int
    #: O que a tela mostrou, mascarado: fica assim para sempre se o turno não terminou.
    rascunho: str
    falha: Falha | None
    valores_do_motor: tuple[Decimal, ...]
    #: A sessão do Hermes ao fim do turno (a compressão troca o id).
    sessao_id: str | None
    tokens_de_contexto: int


# --------------------------------------------------------------------------- #
# O normalizador                                                               #
# --------------------------------------------------------------------------- #

#: Põe um evento no buffer do turno: `emitir(tipo, campos)`.
Emitir = Callable[[str, dict[str, Any]], object]


@dataclass(slots=True)
class _Chamada:
    ferramenta: str
    #: `None` para as de bastidor: o fim delas também não aparece.
    atividade_id: str | None
    cartao: Cartao | None = None


@dataclass(slots=True)
class _Atividade:
    atividade_id: str
    ferramenta: str
    rotulo: str
    rotulo_feito: str
    ok: bool | None = None


@dataclass(slots=True)
class _Estado:
    run_id: str | None = None
    sessao_id: str | None = None
    conteudo: str | None = None
    interrompido: bool = False
    status: str | None = None
    erro: str | None = None
    uso: object = None
    mensagens: list[object] = field(default_factory=list)


class Normalizador:
    """Traduz os eventos de um turno do Hermes para os da tela, na ordem em que chegam."""

    def __init__(
        self,
        emitir: Emitir,
        montador: MontadorDeCartoes | None,
        *,
        novo_cartao_id: Callable[[], str],
        quando: Callable[[str], str],
        ao_saber_do_run: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._emitir = emitir
        self._montador = montador
        self._novo_cartao_id = novo_cartao_id
        self._quando = quando
        self._ao_saber_do_run = ao_saber_do_run
        self._mascara = MascaraDeValores()
        self._estado = _Estado()
        self._pendentes: dict[str, deque[_Chamada]] = {}
        self._atividades: list[_Atividade] = []
        self._cartoes: dict[str, dict[str, Any]] = {}
        self._ultimo_cartao: dict[str, Any] | None = None
        self._comentarios: list[str] = []
        self._recursos: set[str] = set()
        #: Onde começa, no rascunho mascarado, o trecho depois da última ferramenta.
        self._inicio_do_trecho = 0

    # -- o que o serviço lê -------------------------------------------------- #

    @property
    def run_id(self) -> str | None:
        return self._estado.run_id

    @property
    def recebeu_algo(self) -> bool:
        """O Hermes já mandou algum evento deste turno."""
        return self._estado.run_id is not None

    @property
    def terminou(self) -> bool:
        """O Hermes disse como o turno terminou (`run.completed`, `failed` ou `cancelled`)."""
        return self._estado.status is not None

    def atividades(self) -> list[dict[str, Any]]:
        """A linha do tempo como fica gravada: o que foi feito, e se deu certo."""
        return [
            {
                "atividade_id": a.atividade_id,
                "ferramenta": a.ferramenta,
                "rotulo_feito": a.rotulo_feito,
                "ok": bool(a.ok),
            }
            for a in self._atividades
        ]

    def cartoes(self) -> list[dict[str, Any]]:
        """Os cards do turno, na ordem em que apareceram, com a última versão de cada um."""
        return list(self._cartoes.values())

    def sugestoes(self) -> list[dict[str, Any]]:
        return sugestoes_para(self._ultimo_cartao)

    # -- cards ---------------------------------------------------------------- #

    def para_a_tela(self, cartao: Mapping[str, Any]) -> dict[str, Any]:
        """O card como vai no evento: sem o instante cru, com o `gerado_texto`."""
        pronto = {k: v for k, v in cartao.items() if k != "gerado"}
        pronto["gerado_texto"] = gerado_texto(
            str(cartao["tipo_cartao"]), self._quando(str(cartao["gerado"]))
        )
        return pronto

    async def montar_cartao(self, cartao: Cartao) -> dict[str, Any] | None:
        """Monta e guarda o card; devolve-o como vai à tela, ou `None` se não há o que mostrar.

        Um card que já saiu neste turno com os mesmos dados devolve `None`: não se repete.
        """
        if self._montador is None:
            return None
        try:
            ref = await asyncio.to_thread(self._montador.resolver, cartao)
            if ref is None:
                return None
            anterior = self._cartoes.get(ref.chave)
            cartao_id = anterior["cartao_id"] if anterior else self._novo_cartao_id()
            pronto = await self._montador.montar_resolvido(ref, cartao_id=cartao_id)
        except Exception:
            # O card é acessório: um erro aqui nunca derruba o turno.
            logger.exception("não consegui montar o card %s", cartao.get("tipo_cartao"))
            return None
        if pronto is None or (anterior and dados_iguais(anterior["dados"], pronto["dados"])):
            return None
        self._cartoes[ref.chave] = pronto
        self._ultimo_cartao = pronto
        return self.para_a_tela(pronto)

    # -- os eventos do Hermes ------------------------------------------------- #

    async def processar(self, evento: EventoSSE) -> None:
        """Um evento do Hermes; o que a tela precisa ver sai por `emitir`."""
        dados = evento.dados if isinstance(evento.dados, dict) else {}
        await self._anotar_run(dados)
        nome = evento.nome
        if nome == "assistant.delta":
            self._rascunho(dados.get("delta"))
        elif nome == "assistant.commentary":
            self._comentario(dados)
        elif nome == "tool.started":
            self._inicio_de_chamada(dados)
        elif nome in ("tool.completed", "tool.failed"):
            await self._fim_de_chamada(dados, ok=nome == "tool.completed")
        elif nome == "assistant.completed":
            conteudo = dados.get("content")
            self._estado.conteudo = conteudo if isinstance(conteudo, str) else ""
            self._estado.interrompido = bool(dados.get("interrupted"))
            self._adotar_sessao(dados)
        elif nome in ("run.completed", "run.failed", "run.cancelled"):
            self._estado.status = nome.removeprefix("run.")
            mensagens = dados.get("messages")
            self._estado.mensagens = mensagens if isinstance(mensagens, list) else []
            self._estado.uso = dados.get("usage")
            self._adotar_sessao(dados)
        elif nome == "error":
            self._estado.erro = str(dados.get("message") or "erro sem mensagem")
            logger.warning("o Hermes falhou no turno: %s", self._estado.erro)
        # tool.progress (o raciocínio), message.started e done: nada para a tela.

    async def _anotar_run(self, dados: Mapping[str, Any]) -> None:
        run_id = dados.get("run_id")
        if self._estado.run_id is None and isinstance(run_id, str) and run_id:
            self._estado.run_id = run_id
            if self._ao_saber_do_run is not None:
                await self._ao_saber_do_run(run_id)

    def _adotar_sessao(self, dados: Mapping[str, Any]) -> None:
        sessao = dados.get("session_id")
        if isinstance(sessao, str) and sessao:
            self._estado.sessao_id = sessao

    def _rascunho(self, delta: object) -> None:
        if isinstance(delta, str) and delta:
            saida = self._mascara.alimentar(delta)
            if saida:
                self._emitir("texto.parcial", {"delta": saida})

    def _comentario(self, dados: Mapping[str, Any]) -> None:
        """O texto do meio do turno: guardado só para o caso de não vir resposta depois."""
        texto = dados.get("text")
        if isinstance(texto, str) and texto.strip():
            self._comentarios.append(texto)

    def _fechar_o_trecho(self) -> None:
        """Uma ferramenta começou: o que o agente escreveu até aqui é bastidor, não resposta."""
        resto = self._mascara.finalizar()
        if resto:
            self._emitir("texto.parcial", {"delta": resto})
        self._inicio_do_trecho = len(self._mascara.mascarado)

    def _inicio_de_chamada(self, dados: Mapping[str, Any]) -> None:
        bruto = dados.get("tool_name")
        if not isinstance(bruto, str) or not bruto:
            return
        self._fechar_o_trecho()
        ferramenta = nome_da_ferramenta(bruto)
        fila = self._pendentes.setdefault(ferramenta, deque())
        if de_bastidor(ferramenta):
            fila.append(_Chamada(ferramenta, None))
            return
        atividade_id = f"at-{len(self._atividades) + 1}"
        argumentos = dados.get("args")
        frase = frase_para(bruto, argumentos)
        self._atividades.append(
            _Atividade(atividade_id, ferramenta, frase["rotulo"], frase["rotulo_feito"])
        )
        fila.append(_Chamada(ferramenta, atividade_id, cartao_para(bruto, argumentos)))
        self._emitir(
            "atividade.iniciada",
            {
                "atividade_id": atividade_id,
                "ferramenta": ferramenta,
                "rotulo": frase["rotulo"],
                "rotulo_feito": frase["rotulo_feito"],
            },
        )

    def _concluir_atividade(self, atividade_id: str, ok: bool) -> None:
        for atividade in self._atividades:
            if atividade.atividade_id == atividade_id:
                atividade.ok = ok
        self._emitir("atividade.concluida", {"atividade_id": atividade_id, "ok": ok})

    async def _fim_de_chamada(self, dados: Mapping[str, Any], *, ok: bool) -> None:
        bruto = dados.get("tool_name")
        fila = self._pendentes.get(nome_da_ferramenta(bruto)) if isinstance(bruto, str) else None
        if not fila:
            return
        chamada = fila.popleft()
        if chamada.atividade_id is None:
            return
        self._concluir_atividade(chamada.atividade_id, ok)
        if not ok:
            return
        if chamada.cartao is not None:
            pronto = await self.montar_cartao(chamada.cartao)
            if pronto is not None:
                self._emitir("cartao", pronto)
        self.alterou(recursos_da_escrita(chamada.ferramenta))

    def alterou(self, recursos: Iterable[str]) -> None:
        """Avisa a tela do que mudou, se mudou alguma coisa."""
        lista = sorted(set(recursos))
        if lista:
            self._recursos.update(lista)
            self._emitir("estado.alterado", {"recursos": lista})

    # -- o fim -------------------------------------------------------------- #

    def _texto_composto(self) -> str:
        """A resposta: o texto depois da última ferramenta, ou, sem ele, o último comentário."""
        conteudo = self._estado.conteudo or ""
        final = "" if conteudo.strip() in _VAZIO else sem_nota_do_guard_rail(conteudo).strip()
        if final:
            return final
        return next((c.strip() for c in reversed(self._comentarios) if c.strip()), "")

    def _falha(self) -> Falha | None:
        estado = self._estado
        if estado.status == "completed":
            return traduzir_aviso(estado.conteudo)
        if estado.status == "failed":
            return traduzir_aviso(estado.conteudo) or Falha("consultora", SEM_RESPOSTA)
        if estado.erro is not None:
            return Falha("consultora", PROBLEMA)
        return Falha("rede", CONEXAO_CAIU)

    def concluir(
        self,
        autorizados: Iterable[Decimal],
        *,
        falha: Falha | None = None,
        cancelado: bool = False,
    ) -> Desfecho:
        """Fecha o turno: libera o rascunho retido, confere o texto final e sugere respostas.

        `autorizados` é o que já tinha procedência antes deste turno (as saídas do
        motor dos turnos anteriores, o que ela disse, o que já foi conferido);
        as saídas do motor deste turno entram aqui. `falha` é o que o serviço
        viu dar errado fora do stream (rede, tempo); `cancelado`, que ela pediu
        para parar e o serviço fechou a conexão antes de o Hermes confirmar.
        """
        resto = self._mascara.finalizar()
        if resto:
            self._emitir("texto.parcial", {"delta": resto})
        for fila in self._pendentes.values():
            for chamada in fila:
                if chamada.atividade_id is not None:
                    self._concluir_atividade(chamada.atividade_id, False)
            fila.clear()

        valores = valores_do_motor(self._estado.mensagens)
        cancelado = cancelado or (
            falha is None and (self._estado.status == "cancelled" or self._estado.interrompido)
        )
        falha = None if cancelado else falha or self._falha()
        texto_final: str | None = None
        retirados = 0
        if not cancelado and falha is None:
            composto = self._texto_composto()
            if composto:
                conferido, _ = retirar_sem_procedencia(composto, {*autorizados, *valores})
                texto_final, retirados = conferido, conferido.count(REDACAO)
            else:
                falha = Falha("consultora", SEM_RESPOSTA)
        if texto_final is not None:
            self._emitir("texto.final", {"texto": texto_final, "retirados": retirados})
            opcoes = self.sugestoes()
            if opcoes:
                self._emitir("sugestoes", {"opcoes": opcoes})

        if cancelado:
            estado = EstadoDoTurno.CANCELADO
        elif falha is not None:
            estado = EstadoDoTurno.FALHOU
        else:
            estado = EstadoDoTurno.CONCLUIDO
        return Desfecho(
            estado=estado,
            texto_final=texto_final,
            retirados=retirados,
            rascunho=self._mascara.mascarado[self._inicio_do_trecho :],
            falha=falha,
            valores_do_motor=valores,
            sessao_id=self._estado.sessao_id,
            tokens_de_contexto=estimar_contexto(self._estado.uso, self._estado.mensagens),
        )


__all__ = [
    "CONEXAO_CAIU",
    "CONTEXTO_CHEIO",
    "DEMOROU",
    "FERRAMENTAS_DE_BASTIDOR",
    "FORA_DO_AR",
    "INTERROMPIDO",
    "PROBLEMA",
    "RECURSOS_DA_ESCRITA",
    "RECUSA",
    "SEM_RESPOSTA",
    "TIPOS_DE_EVENTO",
    "Desfecho",
    "Emitir",
    "Falha",
    "Normalizador",
    "de_bastidor",
    "e_do_motor",
    "estimar_contexto",
    "recursos_da_escrita",
    "sem_nota_do_guard_rail",
    "traduzir_aviso",
    "valores_do_motor",
]
