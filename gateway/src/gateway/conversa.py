"""O dono de cada turno de conversa da web.

Quando ela manda uma mensagem, o navegador recebe `202 {turno_id}` na hora e
assina os eventos do turno (SSE). O turno não é do navegador: é deste serviço.

- **Uma tarefa em segundo plano, nossa, fala com o Hermes.** O `chat/stream` do
  Hermes interrompe o turno quando a conexão cai; a conexão é desta tarefa, e
  não da aba dela. Fechar a aba, recarregar ou perder o sinal não cancela nada:
  o turno vai até o fim e a resposta fica gravada.
- **Os eventos ficam num buffer numerado**, pela vida do turno e mais 10
  minutos. Quem assina de novo manda o último `seq` que viu (`Last-Event-ID` ou
  `?desde=`) e recebe o resto; outra aba recebe tudo desde o começo.
- **Parar é pedir ao Hermes** (`POST /v1/runs/{run_id}/stop`). Se ele não
  parar em alguns segundos, a tarefa fecha a conexão, e o próprio Hermes para.
- **O backend caiu no meio?** No arranque seguinte, o turno que estava em
  andamento vira `interrompido`, e a tela oferece reenviar.
- **Ação de card primeiro.** Um botão ("Tenho forno", "Vou cobrar este") é
  executado pelo motor antes de o agente ser chamado, e o agente fica sabendo o
  que já ficou gravado (`gateway.acoes_da_conversa`).
- **A sessão do Hermes é detalhe.** Uma conversa daqui atravessa várias sessões
  de lá: o id que o Hermes devolve no fim do turno (a compressão troca) é
  adotado, e quando o contexto passa do limite (150 mil tokens, por padrão) a
  conversa segue numa sessão nova, cuja primeira mensagem pede ao agente que
  retome pelo resumo da consultoria.
- **A instrução de sistema da web é fixa**, os mesmos bytes em todo turno:
  mudá-la no meio da sessão é editar o histórico, e os modelos com histórico
  preservado perdem o raciocínio guardado. O que muda a cada turno (o que ela
  está vendo na tela, o que o botão gravou) vai na mensagem dela, entre
  colchetes, sem dinheiro.

O histórico que a tela mostra sai sempre do banco de conversas
(`gateway.conversas_db`): o Hermes guarda o texto de antes do guard-rail.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import httpx
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from gateway.acoes_da_conversa import executar, sem_dinheiro
from gateway.cartoes_da_conversa import (
    MontadorDeCartoes,
    gerado_texto,
    slug,
    slug_da_receita,
)
from gateway.conversas_db import (
    DOSSIE_PADRAO,
    BancoDeConversas,
    Conversa,
    EstadoDoTurno,
    Mensagem,
    Papel,
    Turno,
    fuso_dela,
    novo_id,
    quando_texto,
)
from gateway.eventos_do_turno import (
    DEMOROU,
    FORA_DO_AR,
    INTERROMPIDO,
    PROBLEMA,
    Desfecho,
    Falha,
    Normalizador,
)
from gateway.frases import SENTINELA
from gateway.hermes_cliente import (
    AgenteOcupada,
    ChaveAusente,
    ChaveRecusada,
    ClienteHermes,
    ErroDoHermes,
    NaoEncontrado,
    PedidoRecusado,
    hermes_home,
)
from gateway.hermes_operacao import ler_modelo
from gateway.mascara import valores_da_fala
from gateway.politica import ESCOPOS
from gateway.seguranca import TAMANHO_DA_MENSAGEM, LimiteDeTaxa

if TYPE_CHECKING:
    from fastapi import FastAPI
    from mise.mcp_server import Sessao

logger = logging.getLogger(__name__)

#: A instrução de sistema da web: a mesma em todo turno de toda sessão (ver o módulo).
INSTRUCAO_DA_WEB: Final = (
    "Você está no chat da plataforma Sabor da Maria, aberto ao lado de todas as telas. "
    "Abaixo da sua resposta a tela mostra sozinha um cartão para cada ferramenta que você "
    "chamou, com os dados já conferidos: a receita, a conferência da cozinha, a comparação, a "
    "pergunta com botões, o item da despensa, o orçamento, o custo por porção, os caminhos de "
    "preço, o preço preliminar, a decisão, a avaliação e as fontes. Não repita o que o cartão "
    "mostra: diga a conclusão e o número principal, e deixe a lista e a conta inteira com ele. "
    "A tela desenha **negrito**, *itálico*, listas com hífen no começo da linha e links no "
    "formato [texto](https://...); título, tabela e código aparecem como texto cru, então não "
    "use. Escreva em parágrafos curtos e use lista quando ela ajudar a ler, como três opções "
    "ou o que falta comprar. Dentro da frase, ligue as ideias com vírgula ou ponto, nunca com "
    "travessão. "
    "Linhas entre colchetes no fim da mensagem dela vêm da tela, não da boca dela: "
    "'[a senhora está vendo ...]' diz o que ela tem aberto agora, e é disso que ela fala quando "
    "diz 'isso'; '[a senhora já respondeu pela tela: ...]' e as parecidas contam o que um botão "
    "já gravou, então não grave de novo."
)

VAR_LIMITE_DE_TOKENS: Final = "MISE_CONVERSA_LIMITE_TOKENS"
#: Acima disso a conversa segue numa sessão nova do Hermes (ele comprime em 256 mil).
LIMITE_DE_TOKENS: Final = 150_000
#: Por quanto tempo os eventos de um turno que terminou continuam na memória.
RETENCAO_S: Final = 600.0
#: O maior silêncio no SSE: o proxy do Next desiste depois de 30 s parado.
KEEPALIVE_S: Final = 10.0
#: Depois de pedir para parar, quanto esperar o Hermes antes de fechar a conexão.
ESPERA_DA_PARADA_S: Final = 10.0
#: O turno mais longo que o backend espera (a mediana medida é de 40 s).
DURACAO_MAXIMA_S: Final = 900.0
#: Por quanto tempo o estado do chat vale sem perguntar de novo ao Hermes.
CACHE_DO_ESTADO_S: Final = 5.0
#: Quantas mensagens anteriores a sessão nova recebe, para retomar.
TROCAS_NA_RETOMADA: Final = 4
TAMANHO_NA_RETOMADA: Final = 280
TAMANHO_DA_PREVIA: Final = 90

MOTIVO_FORA_DO_AR: Final = (
    "O agente está fora do ar agora. As telas continuam funcionando normalmente."
)
AVISO_DE_DOSSIE: Final = (
    "O agente está olhando outro caderno de anotações agora: os cartões podem não "
    "bater com o que ele diz."
)

_DESCRICAO_DO_CONTEXTO: Final[dict[str, str]] = {
    "ingrediente": "o ingrediente",
    "pendencia": "a pendência de",
    "receita": "a receita",
    "prato": "o prato",
    "equipamento": "o equipamento",
    "tecnica": "a técnica",
    "restricao": "a rotina da cozinha:",
    "tela": "a tela",
}

_TELAS: Final[dict[str, str]] = {
    "inicio": "Início",
    "despensa": "Despensa",
    "orcamento": "Orçamento",
    "receitas": "Receitas",
    "cozinha": "Cozinha",
    "precificar": "Pôr preço",
    "cardapio": "Cardápio",
    "historico": "Histórico",
    "trilha": "Histórico",
    "conversa": "Conversa",
}


# --------------------------------------------------------------------------- #
# Configuração e erros                                                         #
# --------------------------------------------------------------------------- #


def _limite_do_ambiente(ambiente: Mapping[str, str]) -> int:
    bruto = ambiente.get(VAR_LIMITE_DE_TOKENS, "").strip()
    try:
        valor = int(bruto) if bruto else LIMITE_DE_TOKENS
    except ValueError:
        logger.warning("%s inválido (%r); usando %d", VAR_LIMITE_DE_TOKENS, bruto, LIMITE_DE_TOKENS)
        return LIMITE_DE_TOKENS
    return valor if valor > 0 else LIMITE_DE_TOKENS


@dataclass(frozen=True, slots=True)
class Configuracao:
    limite_de_tokens: int = LIMITE_DE_TOKENS
    retencao_s: float = RETENCAO_S
    keepalive_s: float = KEEPALIVE_S
    espera_da_parada_s: float = ESPERA_DA_PARADA_S
    duracao_maxima_s: float = DURACAO_MAXIMA_S
    cache_do_estado_s: float = CACHE_DO_ESTADO_S

    @classmethod
    def do_ambiente(cls, ambiente: Mapping[str, str] | None = None) -> Configuracao:
        amb = os.environ if ambiente is None else ambiente
        return cls(limite_de_tokens=_limite_do_ambiente(amb))


class ErroDaConversa(Exception):
    """Um pedido que a conversa recusa, já com o status HTTP e a frase para ela."""

    status: int = 400
    categoria: str = "uso"

    def __init__(
        self,
        mensagem: str,
        *,
        dados: Mapping[str, Any] | None = None,
        cabecalhos: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.dados = dict(dados) if dados is not None else None
        self.cabecalhos = dict(cabecalhos or {})


class ConversaAusente(ErroDaConversa):
    status, categoria = 404, "ausente"


class TurnoAusente(ErroDaConversa):
    status, categoria = 404, "ausente"


class PedidoInvalido(ErroDaConversa):
    status, categoria = 422, "uso"


class TurnoEmAndamento(ErroDaConversa):
    status, categoria = 409, "ocupado"


class MuitasMensagens(ErroDaConversa):
    status, categoria = 429, "regra"


@dataclass(frozen=True, slots=True)
class Pedido:
    """O que o navegador mandou num turno: o texto dela e, talvez, contexto e ação."""

    texto: str
    id_cliente: str
    contexto: Mapping[str, Any] | None = None
    acao: Mapping[str, Any] | None = None


# --------------------------------------------------------------------------- #
# O turno vivo                                                                 #
# --------------------------------------------------------------------------- #


def quadro_sse(evento: Mapping[str, Any]) -> str:
    """Um evento em SSE: `id: <seq>` e o JSON inteiro em `data:`, sem campo `event`.

    Sem `event:` de propósito: o `EventSource` só entrega ao `onmessage` o que
    não tem nome, e a tela lê o `tipo` de dentro do JSON.
    """
    dados = json.dumps(evento, ensure_ascii=False, separators=(",", ":"), default=str)
    return f"id: {evento['seq']}\ndata: {dados}\n\n"


@dataclass(slots=True)
class TurnoVivo:
    """Um turno na memória: os eventos numerados e quem espera por eles."""

    id: str
    conversa_id: str
    mensagem_id: str | None
    id_cliente: str
    iniciado: datetime
    estado: EstadoDoTurno = EstadoDoTurno.EM_ANDAMENTO
    run_id: str | None = None
    parar_pedido: bool = False
    tarefa: asyncio.Task[None] | None = None
    terminado_em: float | None = None
    eventos: list[dict[str, Any]] = field(default_factory=list)
    _sinal: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def ultimo_seq(self) -> int:
        return len(self.eventos)

    @property
    def sinal(self) -> asyncio.Event:
        """Dispara no próximo evento. Pegue antes de ler, para não perder o aviso."""
        return self._sinal

    def emitir(self, tipo: str, campos: Mapping[str, Any]) -> dict[str, Any]:
        evento = {"seq": self.ultimo_seq + 1, "turno_id": self.id, "tipo": tipo, **campos}
        self.eventos.append(evento)
        sinal, self._sinal = self._sinal, asyncio.Event()
        sinal.set()
        return evento

    def terminar(self, estado: EstadoDoTurno, tipo: str, campos: Mapping[str, Any]) -> None:
        self.estado = estado
        self.terminado_em = time.monotonic()
        self.emitir(tipo, campos)

    def depois_de(self, seq: int) -> list[dict[str, Any]]:
        return self.eventos[max(0, seq) :]


# --------------------------------------------------------------------------- #
# O que vai para o agente                                                      #
# --------------------------------------------------------------------------- #


def resolver_contexto(sessao: Sessao, bruto: Mapping[str, Any]) -> dict[str, Any] | None:
    """O contexto que a tela mandou, se aponta para algo que existe; o rótulo é o nosso.

    O navegador é cliente não confiável: só entra o que casa com um id conhecido, e
    o nome vem dos dados do motor, nunca do `rotulo` que ele mandou.
    """
    from mise.perfil import PERGUNTAS_OPERACIONAIS  # noqa: PLC0415
    from mise.taxonomia import EQUIPAMENTOS_POR_ID, TECNICAS_POR_ID  # noqa: PLC0415

    tipo, ident = str(bruto.get("tipo") or ""), str(bruto.get("id") or "")
    rotulo: str | None = None
    if tipo in ("ingrediente", "pendencia"):
        item = sessao.despensa.por_id(ident)
        rotulo = item.nome if item is not None else None
    elif tipo in ("receita", "prato"):
        alvo = ident.casefold()
        for receita in sessao.candidatas.values():
            if alvo in (slug_da_receita(receita), slug(receita.nome), receita.nome.casefold()):
                rotulo = receita.nome
                break
        else:
            # A receita da grade está no catálogo, mesmo antes de entrar em avaliação.
            guardada = sessao.catalogo.obter(alvo) or sessao.catalogo.por_nome(ident)
            rotulo = (
                guardada.nome
                if guardada is not None
                else next(
                    (p for p in sessao.dossie.cardapio if alvo in (slug(p), p.casefold())), None
                )
            )
    elif tipo == "equipamento" and ident in EQUIPAMENTOS_POR_ID:
        rotulo = EQUIPAMENTOS_POR_ID[ident].nome
    elif tipo == "tecnica" and ident in TECNICAS_POR_ID:
        rotulo = TECNICAS_POR_ID[ident].nome
    elif tipo == "restricao" and ident in PERGUNTAS_OPERACIONAIS:
        rotulo = ident.replace("_", " ")
    elif tipo == "tela" and ident in _TELAS:
        rotulo = _TELAS[ident]
    if rotulo is None:
        return None
    tela = bruto.get("tela")
    return {
        "tela": tela if isinstance(tela, str) and tela in _TELAS else None,
        "tipo": tipo,
        "id": ident,
        "rotulo": rotulo,
    }


def linha_do_contexto(contexto: Mapping[str, Any] | None) -> str | None:
    if not contexto:
        return None
    descricao = _DESCRICAO_DO_CONTEXTO.get(str(contexto["tipo"]), "")
    return sem_dinheiro(f"[a senhora está vendo {descricao} {contexto['rotulo']}]")


def mensagem_para_a_agente(texto: str, *extras: str | None) -> str:
    """O texto dela, e depois as linhas da tela entre colchetes."""
    return "\n\n".join([texto.strip(), *(e for e in extras if e)])


def _dossie_do_perfil(home: Path, perfil: str) -> tuple[bool, Path | None]:
    """(o perfil pôde ser lido, o dossiê que o servidor `mise` do perfil usa).

    Sem servidor `mise` no perfil, o dossiê é `None`: o agente não faz conta.
    """
    pasta = home if perfil == "default" else home / "profiles" / perfil
    try:
        dados = YAML(typ="safe").load((pasta / "config.yaml").read_text(encoding="utf-8"))
    except (OSError, YAMLError):
        return False, None
    servidores = dados.get("mcp_servers") if isinstance(dados, dict) else None
    mise = servidores.get("mise") if isinstance(servidores, dict) else None
    if not isinstance(mise, dict):
        return True, None
    ambiente = mise.get("env")
    bruto = ambiente.get("MISE_DOSSIE") if isinstance(ambiente, dict) else None
    bruto = str(bruto or DOSSIE_PADRAO).strip()
    return True, Path(bruto).expanduser()


def conferir_dossie(home: Path, perfil: str, dossie_da_api: Path) -> tuple[str, str] | None:
    """(aviso para a tela, detalhe para quem opera) se o agente e a tela leem dossiês diferentes."""
    legivel, do_perfil = _dossie_do_perfil(home, perfil)
    if not legivel:
        return None
    if do_perfil is None:
        return (
            "O agente está sem acesso às contas agora.",
            f"o perfil {perfil} do Hermes não tem o servidor MCP 'mise'",
        )
    if do_perfil.resolve() == dossie_da_api.expanduser().resolve():
        return None
    return (
        AVISO_DE_DOSSIE,
        f"o servidor 'mise' do perfil {perfil} usa MISE_DOSSIE={do_perfil}, e esta API usa "
        f"{dossie_da_api}; rode o bootstrap desta worktree ou alinhe os dois (e reinicie o "
        "gateway, que só relê o config.yaml ao subir)",
    )


def _falha_do_hermes(erro: ErroDoHermes) -> Falha:
    if isinstance(erro, AgenteOcupada):
        return Falha("consultora", "Estou atendendo outra conversa agora. Tente de novo já já.")
    if erro.categoria == "rede" or isinstance(erro, ChaveAusente | ChaveRecusada):
        return Falha("rede", FORA_DO_AR)
    if erro.categoria == "tempo":
        return Falha("tempo", DEMOROU)
    return Falha("consultora", PROBLEMA)


def _previa(texto: str) -> str:
    limpo = " ".join(texto.replace("**", "").replace("__", "").split())
    limpo = limpo.replace(SENTINELA, "R$ ···")
    if len(limpo) > TAMANHO_DA_PREVIA:
        limpo = limpo[: TAMANHO_DA_PREVIA - 1].rsplit(" ", 1)[0].rstrip(" .,;:") + "…"
    return limpo


def _texto_da(mensagem: Mensagem) -> str | None:
    """O texto que a mensagem mostra, se é texto de verdade (não rascunho mascarado)."""
    if mensagem.papel is Papel.CONSULTORA:
        return mensagem.texto_final
    for parte in mensagem.partes:
        if isinstance(parte, dict) and parte.get("tipo") == "texto":
            return str(parte.get("texto") or "")
    return None


# --------------------------------------------------------------------------- #
# O serviço                                                                    #
# --------------------------------------------------------------------------- #


class ServicoDeConversa:
    """As conversas da web e os turnos em andamento, sobre a sessão do app."""

    def __init__(
        self,
        banco: BancoDeConversas,
        sessao: Sessao,
        *,
        app: FastAPI | None = None,
        fabrica_do_cliente: Callable[[], ClienteHermes] | None = None,
        configuracao: Configuracao | None = None,
        limite: LimiteDeTaxa | None = None,
        home: Path | None = None,
    ) -> None:
        self.banco = banco
        self.sessao = sessao
        self.app = app
        self.fabrica_do_cliente = fabrica_do_cliente or ClienteHermes.do_ambiente
        self.configuracao = configuracao or Configuracao()
        self.limite = limite or LimiteDeTaxa()
        self.home = home
        self._fuso = fuso_dela()
        self._cliente: ClienteHermes | None = None
        self._interno: httpx.AsyncClient | None = None
        self._vivos: dict[str, TurnoVivo] = {}
        self._tarefas: set[asyncio.Task[None]] = set()
        self._estado_do_chat: tuple[float, dict[str, Any]] | None = None
        self._recuperar_interrompidos()

    @classmethod
    def do_ambiente(cls, sessao: Sessao, app: FastAPI | None = None) -> ServicoDeConversa:
        return cls(
            BancoDeConversas.do_ambiente(), sessao, app=app, configuracao=Configuracao.do_ambiente()
        )

    async def fechar(self) -> None:
        for vivo in list(self._vivos.values()):
            if vivo.tarefa is not None and not vivo.tarefa.done():
                vivo.tarefa.cancel()
        if self._tarefas:
            await asyncio.gather(*self._tarefas, return_exceptions=True)
        for cliente in (self._cliente, self._interno):
            if cliente is not None:
                await (cliente.fechar() if isinstance(cliente, ClienteHermes) else cliente.aclose())
        self._cliente = self._interno = None

    # -- infraestrutura --------------------------------------------------------- #

    def cliente(self) -> ClienteHermes:
        """O cliente do Hermes, criado na primeira vez, dentro do laço que vai usá-lo."""
        if self._cliente is None:
            self._cliente = self.fabrica_do_cliente()
        return self._cliente

    def _agora(self) -> datetime:
        return self.banco.agora()

    def _quando(self, momento: str | datetime, *, com_hora: bool = True) -> str:
        instante = datetime.fromisoformat(momento) if isinstance(momento, str) else momento
        return quando_texto(instante, self._agora(), com_hora=com_hora, fuso=self._fuso)

    async def _buscar_na_api(self, rota: str) -> tuple[int, Any]:
        """Uma rota da própria API, em processo: os dados de um card, como a tela os leria."""
        if self.app is None:
            return 404, {"detail": "Not Found"}
        if self._interno is None:
            self._interno = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app), base_url="http://127.0.0.1"
            )
        try:
            resposta = await self._interno.get(rota, timeout=15)
        except Exception:
            logger.exception("a rota %s do card falhou", rota)
            return 500, None
        try:
            return resposta.status_code, resposta.json()
        except ValueError:
            return resposta.status_code, None

    def _montador(self) -> MontadorDeCartoes:
        return MontadorDeCartoes(self.sessao, self._buscar_na_api, self._agora)

    def _recuperar_interrompidos(self) -> None:
        """No arranque: o turno que estava em andamento morreu com o processo anterior."""
        for turno_id in self.banco.marcar_interrompidos():
            turno = self.banco.turno(turno_id)
            if turno is None:  # pragma: no cover (acabou de ser marcado)
                continue
            self.banco.inserir_mensagem(
                turno.conversa_id,
                Papel.CONSULTORA,
                [],
                estado=EstadoDoTurno.INTERROMPIDO.value,
                turno_id=turno.id,
                extras={"erro": {"categoria": "rede", "mensagem": INTERROMPIDO}},
            )
            logger.info("turno %s interrompido pela queda do backend", turno_id)

    def _limpar(self) -> None:
        """Esquece os turnos que terminaram há mais que a retenção."""
        agora = time.monotonic()
        vencidos = [
            turno_id
            for turno_id, vivo in self._vivos.items()
            if vivo.terminado_em is not None
            and agora - vivo.terminado_em > self.configuracao.retencao_s
        ]
        for turno_id in vencidos:
            del self._vivos[turno_id]

    @property
    def ocupada(self) -> bool:
        """Algum turno em andamento agora, em qualquer conversa (a descoberta espera por ele)."""
        return any(not v.estado.terminado for v in self._vivos.values())

    def _em_andamento(self, conversa_id: str) -> TurnoVivo | None:
        return next(
            (
                v
                for v in self._vivos.values()
                if v.conversa_id == conversa_id and not v.estado.terminado
            ),
            None,
        )

    def _conversa(self, conversa_id: str) -> Conversa:
        conversa = self.banco.conversa(conversa_id)
        if conversa is None:
            raise ConversaAusente("Essa conversa não existe mais.")
        return conversa

    # -- conversas ------------------------------------------------------------ #

    def listar(self) -> dict[str, Any]:
        self._limpar()
        conversas = [
            {
                "id": c.id,
                "titulo": c.titulo,
                "previa": self._previa_de(c.id),
                "atualizado_texto": self._quando(c.atualizada, com_hora=False),
                "respondendo": self._em_andamento(c.id) is not None,
            }
            for c in self.banco.conversas()
        ]
        return {"atual": self.banco.atual(), "conversas": conversas}

    def _previa_de(self, conversa_id: str) -> str:
        for mensagem in reversed(self.banco.mensagens(conversa_id, limite=8)):
            texto = _texto_da(mensagem)
            if texto:
                return _previa(texto)
        return ""

    def criar(self, titulo: str | None = None) -> dict[str, Any]:
        return self.detalhar(self.banco.criar_conversa(titulo).id)

    def detalhar(self, conversa_id: str) -> dict[str, Any]:
        self._limpar()
        conversa = self._conversa(conversa_id)
        vivo = self._em_andamento(conversa_id)
        return {
            "id": conversa.id,
            "titulo": conversa.titulo,
            "atual": conversa.atual,
            "turno_em_andamento": self._estado_vivo(vivo) if vivo is not None else None,
            "mensagens": [self._mensagem(m) for m in self.banco.mensagens(conversa_id)],
        }

    def alterar(
        self, conversa_id: str, *, titulo: str | None = None, atual: bool | None = None
    ) -> dict[str, Any]:
        self._conversa(conversa_id)
        if titulo is not None:
            self.banco.renomear(conversa_id, titulo)
        if atual:
            self.banco.marcar_atual(conversa_id)
        conversa = self._conversa(conversa_id)
        return {"id": conversa.id, "titulo": conversa.titulo, "atual": conversa.atual}

    async def parar_todos(self) -> None:
        """Para todo turno em andamento e esquece os turnos da memória (o "Restaurar os dados").

        A resposta que o agente estava escrevendo ia gravar numa conversa
        que vai sumir, e mudar a despensa depois da restauração.
        """
        tarefas = []
        for vivo in list(self._vivos.values()):
            if not vivo.estado.terminado:
                await self._parar_vivo(vivo)
                if vivo.tarefa is not None:
                    vivo.tarefa.cancel()
                    tarefas.append(vivo.tarefa)
            self.limite.esquecer(vivo.conversa_id)
        if tarefas:
            # O que o turno grava ao ser parado entra antes de as conversas saírem.
            await asyncio.wait(tarefas, timeout=5)
        self._vivos.clear()

    async def apagar(self, conversa_id: str) -> dict[str, Any]:
        self._conversa(conversa_id)
        vivo = self._em_andamento(conversa_id)
        if vivo is not None:
            await self._parar_vivo(vivo)
            if vivo.tarefa is not None:
                vivo.tarefa.cancel()
        atual = self.banco.apagar(conversa_id)
        self.limite.esquecer(conversa_id)
        return {"apagada": conversa_id, "atual": atual}

    def _mensagem(self, mensagem: Mensagem) -> dict[str, Any]:
        saida: dict[str, Any] = {
            "id": mensagem.id,
            "papel": mensagem.papel.value,
            "turno_id": mensagem.turno_id,
            "partes": [self._parte(p) for p in mensagem.partes if isinstance(p, dict)],
            "quando_texto": self._quando(mensagem.criada),
        }
        extras = mensagem.extras
        if mensagem.papel is Papel.CONSULTORA:
            saida["estado"] = mensagem.estado
            saida["retirados"] = mensagem.retirados
            saida["atividades"] = [
                {"rotulo_feito": a.get("rotulo_feito", ""), "ok": bool(a.get("ok", True))}
                for a in extras.get("atividades", [])
                if isinstance(a, dict)
            ]
            for chave in ("acao_resultado", "erro", "sugestoes"):
                if chave in extras:
                    saida[chave] = extras[chave]
        elif extras.get("contexto"):
            saida["contexto"] = extras["contexto"]
        return saida

    def _parte(self, parte: dict[str, Any]) -> dict[str, Any]:
        if parte.get("tipo") != "cartao" or not isinstance(parte.get("cartao"), dict):
            return parte
        cartao = {k: v for k, v in parte["cartao"].items() if k != "gerado"}
        gerado = parte["cartao"].get("gerado")
        if isinstance(gerado, str):
            cartao["gerado_texto"] = gerado_texto(
                str(cartao.get("tipo_cartao")), self._quando(gerado)
            )
        return {"tipo": "cartao", "cartao": cartao}

    # -- turnos: começar --------------------------------------------------------- #

    async def iniciar_turno(self, conversa_id: str, pedido: Pedido) -> str:
        """Grava a mensagem dela, agenda o turno e devolve o id. O turno roda sozinho."""
        self._limpar()
        self._conversa(conversa_id)
        texto = pedido.texto.strip()
        if not texto:
            raise PedidoInvalido("A mensagem está vazia.")
        if len(texto) > TAMANHO_DA_MENSAGEM:
            raise PedidoInvalido(f"A mensagem passou de {TAMANHO_DA_MENSAGEM} caracteres.")

        anterior = self.banco.turno_do_cliente(conversa_id, pedido.id_cliente)
        if anterior is not None and (
            anterior.estado is EstadoDoTurno.CONCLUIDO
            or (anterior.estado is EstadoDoTurno.EM_ANDAMENTO and anterior.id in self._vivos)
        ):
            # O mesmo clique de novo (a resposta do POST se perdeu): é o mesmo turno.
            # O que falhou, parou ou foi interrompido abre um turno novo, com a mesma bolha.
            return anterior.id
        rodando = self._em_andamento(conversa_id)
        if rodando is not None:
            raise TurnoEmAndamento(
                "Ainda estou respondendo a mensagem anterior.", dados={"turno_id": rodando.id}
            )
        espera = self.limite.espera(conversa_id)
        if espera is not None:
            segundos = max(1, round(espera))
            raise MuitasMensagens(
                f"Muitas mensagens em pouco tempo. Espere {segundos} s e mande de novo.",
                cabecalhos={"Retry-After": str(segundos)},
            )

        # Daqui até a tarefa ser criada não há `await`: conferir o 409 e registrar o
        # turno é atômico no laço, e dois cliques juntos não abrem dois turnos.
        contexto = resolver_contexto(self.sessao, pedido.contexto) if pedido.contexto else None
        turno_id = novo_id("t")
        mensagem_id = self._mensagem_dela(
            conversa_id, turno_id, texto, contexto=contexto, pedido=pedido, anterior=anterior
        )
        self.banco.criar_turno(conversa_id, mensagem_id, pedido.id_cliente, turno_id=turno_id)
        self.banco.marcar_atual(conversa_id)
        self.banco.dar_titulo_automatico(conversa_id, texto)
        self.banco.tocar(conversa_id)

        vivo = TurnoVivo(turno_id, conversa_id, mensagem_id, pedido.id_cliente, self._agora())
        self._vivos[turno_id] = vivo
        tarefa = asyncio.create_task(
            self._conduzir(vivo, texto, contexto, pedido.acao), name=f"turno {turno_id}"
        )
        vivo.tarefa = tarefa
        self._tarefas.add(tarefa)
        tarefa.add_done_callback(self._tarefas.discard)
        return turno_id

    def _mensagem_dela(
        self,
        conversa_id: str,
        turno_id: str,
        texto: str,
        *,
        contexto: dict[str, Any] | None,
        pedido: Pedido,
        anterior: Turno | None,
    ) -> str:
        """A mensagem dela. Reenviar o que falhou (mesmo `id_cliente`) não duplica a bolha."""
        if anterior is not None and anterior.mensagem_id is not None:
            existente = self.banco.mensagem(anterior.mensagem_id)
            if existente is not None:
                return existente.id
        extras: dict[str, Any] = {"id_cliente": pedido.id_cliente}
        if contexto is not None:
            extras["contexto"] = contexto
        if pedido.acao is not None:
            extras["acao"] = dict(pedido.acao)
        return self.banco.inserir_mensagem(
            conversa_id,
            Papel.SENHORA,
            [{"tipo": "texto", "texto": texto}],
            estado="enviada",
            turno_id=turno_id,
            extras=extras,
        )

    # -- turnos: conduzir ------------------------------------------------------ #

    async def _conduzir(
        self,
        vivo: TurnoVivo,
        texto: str,
        contexto: dict[str, Any] | None,
        acao: Mapping[str, Any] | None,
    ) -> None:
        normalizador = Normalizador(
            vivo.emitir,
            self._montador(),
            novo_cartao_id=lambda: novo_id("k"),
            quando=self._quando,
            ao_saber_do_run=lambda run_id: self._ao_saber_do_run(vivo, run_id),
        )
        acao_resultado: dict[str, Any] | None = None
        falha: Falha | None = None
        try:
            vivo.emitir(
                "turno.iniciado",
                {
                    "conversa_id": vivo.conversa_id,
                    "mensagem_id": vivo.mensagem_id,
                    "id_cliente": vivo.id_cliente,
                },
            )
            nota_da_acao: str | None = None
            if acao is not None:
                acao_resultado, nota_da_acao = await self._executar_acao(vivo, normalizador, acao)
            if not vivo.parar_pedido:
                await self._falar_com_a_agente(vivo, normalizador, texto, contexto, nota_da_acao)
        except asyncio.CancelledError:
            interrompido = not vivo.parar_pedido
            self._fechar_turno(
                vivo,
                normalizador,
                acao_resultado,
                falha=Falha("rede", INTERROMPIDO) if interrompido else None,
                cancelado=not interrompido,
                interrompido=interrompido,
            )
            raise
        except ErroDoHermes as erro:
            logger.warning("turno %s: o Hermes falhou (%s): %s", vivo.id, type(erro).__name__, erro)
            falha = _falha_do_hermes(erro)
        except TimeoutError:
            logger.warning(
                "turno %s passou de %.0f s; parando", vivo.id, self.configuracao.duracao_maxima_s
            )
            await self._pedir_parada(vivo)
            falha = Falha("tempo", DEMOROU)
        except Exception:
            logger.exception("turno %s quebrou", vivo.id)
            falha = Falha("consultora", PROBLEMA)
        # Pediu para parar e o Hermes não chegou ao fim: cancelado. Se o fim chegou
        # antes do pedido fazer efeito, vale o fim: a resposta inteira não se perde.
        cancelado = vivo.parar_pedido and not normalizador.terminou
        self._fechar_turno(vivo, normalizador, acao_resultado, falha=falha, cancelado=cancelado)

    async def _executar_acao(
        self, vivo: TurnoVivo, normalizador: Normalizador, acao: Mapping[str, Any]
    ) -> tuple[dict[str, Any], str]:
        resultado = await asyncio.to_thread(executar, self.sessao, acao, vivo.id_cliente)
        campos: dict[str, Any] = {"ok": resultado.ok, "texto": resultado.texto}
        if resultado.ok and resultado.cartao is not None:
            cartao = await normalizador.montar_cartao(resultado.cartao)
            if cartao is not None:
                campos["cartao"] = cartao
        vivo.emitir("acao.resultado", campos)
        if resultado.ok:
            normalizador.alterou(resultado.recursos)
        return {"ok": resultado.ok, "texto": resultado.texto}, resultado.nota

    async def _falar_com_a_agente(
        self,
        vivo: TurnoVivo,
        normalizador: Normalizador,
        texto: str,
        contexto: dict[str, Any] | None,
        nota_da_acao: str | None,
    ) -> None:
        cliente = self.cliente()
        forcar_nova = False
        while True:
            conversa = self._conversa(vivo.conversa_id)
            sessao_id, retomada = await self._sessao_do_turno(conversa, forcar_nova=forcar_nova)
            mensagem = mensagem_para_a_agente(
                texto, linha_do_contexto(contexto), nota_da_acao, retomada
            )
            try:
                async with asyncio.timeout(self.configuracao.duracao_maxima_s):
                    async for evento in cliente.stream_chat(
                        sessao_id, mensagem, instrucao_de_sistema=INSTRUCAO_DA_WEB
                    ):
                        await normalizador.processar(evento)
                return
            except NaoEncontrado:
                if forcar_nova or normalizador.recebeu_algo:
                    raise
                logger.info("a sessão %s não existe mais no Hermes; abrindo outra", sessao_id)
                forcar_nova = True

    async def _sessao_do_turno(
        self, conversa: Conversa, *, forcar_nova: bool
    ) -> tuple[str, str | None]:
        """A sessão do Hermes para o turno, e a nota de retomada se ela abre agora."""
        limite = self.configuracao.limite_de_tokens
        atual = conversa.hermes_session_id
        if atual and not forcar_nova and conversa.tokens_prompt_ultimo <= limite:
            return atual, None
        cliente = self.cliente()
        titulo = f"Sabor da Maria na web: {conversa.id} ({conversa.sessoes_hermes + 1})"
        try:
            sessao = await cliente.criar_sessao(titulo)
        except PedidoRecusado:
            sessao = await cliente.criar_sessao()  # título repetido: o Hermes escolhe
        nova = str(sessao["id"])
        self.banco.usar_sessao_hermes(conversa.id, nova, nova=True)
        ja_conversou = bool(self.banco.textos_finais(conversa.id))
        if atual:
            logger.info("conversa %s passa da sessão %s para %s", conversa.id, atual, nova)
        return nova, self._nota_de_retomada(conversa.id) if ja_conversou else None

    def _nota_de_retomada(self, conversa_id: str) -> str:
        """A primeira mensagem de uma sessão nova numa conversa em curso: como retomar."""
        if "resumo_da_consultoria" in ESCOPOS:
            como = "chame resumo_da_consultoria"
        else:
            como = "chame diagnostico_despensa e consultar_perfil"
        linhas: list[str] = []
        for mensagem in self.banco.mensagens(conversa_id, limite=TROCAS_NA_RETOMADA + 2):
            texto = _texto_da(mensagem)
            if not texto:
                continue
            quem = "a senhora" if mensagem.papel is Papel.SENHORA else "você"
            curto = " ".join(sem_dinheiro(texto).split())[:TAMANHO_NA_RETOMADA]
            linhas.append(f'- {quem}: "{curto}"')
        recentes = "\n".join(linhas[-TROCAS_NA_RETOMADA:])
        return (
            "[nota da tela: esta conversa continua de antes, numa sessão nova sua. Antes de "
            f"responder, {como} para retomar de onde paramos. As últimas mensagens foram:\n"
            f"{recentes}]"
        )

    async def _ao_saber_do_run(self, vivo: TurnoVivo, run_id: str) -> None:
        vivo.run_id = run_id
        self.banco.registrar_run(vivo.id, run_id)
        if vivo.parar_pedido:
            await self._pedir_parada(vivo)

    # -- turnos: parar --------------------------------------------------------- #

    async def _pedir_parada(self, vivo: TurnoVivo) -> None:
        if vivo.run_id is None:
            return
        try:
            await self.cliente().parar(vivo.run_id)
        except ErroDoHermes as erro:
            logger.warning("o Hermes não aceitou parar o run %s: %s", vivo.run_id, erro)

    def _cancelar_se_preciso(self, vivo: TurnoVivo) -> None:
        if vivo.tarefa is not None and not vivo.tarefa.done():
            logger.info("turno %s não parou a tempo; fechando a conexão", vivo.id)
            vivo.tarefa.cancel()

    async def _parar_vivo(self, vivo: TurnoVivo) -> None:
        if vivo.parar_pedido:
            return
        vivo.parar_pedido = True
        await self._pedir_parada(vivo)
        asyncio.get_running_loop().call_later(
            self.configuracao.espera_da_parada_s, self._cancelar_se_preciso, vivo
        )

    async def parar(self, conversa_id: str, turno_id: str) -> tuple[int, dict[str, Any]]:
        """Pede para parar. 202 enquanto para; 200 com o estado se já tinha terminado."""
        vivo = self._vivo(conversa_id, turno_id)
        if vivo is None:
            return 200, self._estado_gravado(self._turno_gravado(conversa_id, turno_id))
        if vivo.estado.terminado:
            return 200, self._estado_vivo(vivo)
        await self._parar_vivo(vivo)
        return 202, {"turno_id": vivo.id, "estado": "cancelando"}

    # -- turnos: fechar -------------------------------------------------------- #

    def _autorizados(self, conversa_id: str) -> set[Decimal]:
        """O que já tinha procedência antes deste turno: o motor, ela e o já conferido."""
        valores = self.banco.valores_conferidos(conversa_id)
        for texto in [*self.banco.falas_dela(conversa_id), *self.banco.textos_finais(conversa_id)]:
            valores.update(valores_da_fala(texto))
        return valores

    def _fechar_turno(
        self,
        vivo: TurnoVivo,
        normalizador: Normalizador,
        acao_resultado: dict[str, Any] | None,
        *,
        falha: Falha | None,
        cancelado: bool,
        interrompido: bool = False,
    ) -> None:
        """Confere o texto, grava a resposta e só então emite o fim do turno."""
        try:
            autorizados = self._autorizados(vivo.conversa_id)
        except sqlite3.Error:
            logger.exception("não consegui ler a conversa %s", vivo.conversa_id)
            autorizados = set()
        desfecho = normalizador.concluir(autorizados, falha=falha, cancelado=cancelado)
        estado = EstadoDoTurno.INTERROMPIDO if interrompido else desfecho.estado
        partes: list[dict[str, Any]] = []
        texto = desfecho.texto_final if desfecho.texto_final is not None else desfecho.rascunho
        if texto:
            parte: dict[str, Any] = {"tipo": "texto", "texto": texto}
            if desfecho.texto_final is None:
                parte["rascunho"] = True
            partes.append(parte)
        partes.extend({"tipo": "cartao", "cartao": c} for c in normalizador.cartoes())
        extras: dict[str, Any] = {"atividades": normalizador.atividades()}
        if acao_resultado is not None:
            extras["acao_resultado"] = acao_resultado
        if desfecho.texto_final is not None and normalizador.sugestoes():
            extras["sugestoes"] = normalizador.sugestoes()
        if desfecho.falha is not None:
            extras["erro"] = {
                "categoria": desfecho.falha.categoria,
                "mensagem": desfecho.falha.mensagem,
            }
        try:
            self._gravar(vivo, estado, desfecho, partes=partes, extras=extras)
        except sqlite3.Error:
            logger.exception("não consegui gravar o turno %s (a conversa foi apagada?)", vivo.id)

        if estado is EstadoDoTurno.CONCLUIDO:
            vivo.terminar(estado, "turno.concluido", {})
        elif estado is EstadoDoTurno.CANCELADO:
            vivo.terminar(estado, "turno.cancelado", {})
        else:
            assert desfecho.falha is not None
            campos: dict[str, Any] = {
                "categoria": desfecho.falha.categoria,
                "mensagem": desfecho.falha.mensagem,
            }
            if interrompido:
                campos["interrompido"] = True
            vivo.terminar(estado, "turno.falhou", campos)

    def _gravar(
        self,
        vivo: TurnoVivo,
        estado: EstadoDoTurno,
        desfecho: Desfecho,
        *,
        partes: list[dict[str, Any]],
        extras: dict[str, Any],
    ) -> None:
        falha = desfecho.falha
        conversa_id = vivo.conversa_id
        if desfecho.sessao_id:
            self.banco.usar_sessao_hermes(conversa_id, desfecho.sessao_id, nova=False)
        if falha is not None and falha.sessao_nova:
            self.banco.registrar_tokens(conversa_id, self.configuracao.limite_de_tokens + 1)
        elif desfecho.tokens_de_contexto:
            self.banco.registrar_tokens(conversa_id, desfecho.tokens_de_contexto)
        self.banco.inserir_mensagem(
            conversa_id,
            Papel.CONSULTORA,
            partes,
            estado=estado.value,
            turno_id=vivo.id,
            texto_final=desfecho.texto_final,
            retirados=desfecho.retirados,
            extras=extras,
        )
        self.banco.terminar_turno(
            vivo.id,
            estado,
            # O fim do turno é o próximo evento, emitido logo depois de gravar.
            ultimo_seq=vivo.ultimo_seq + 1,
            erro_categoria=falha.categoria if falha else None,
            erro_mensagem=falha.mensagem if falha else None,
            valores=desfecho.valores_do_motor,
        )
        self.banco.tocar(conversa_id)

    # -- turnos: ler ---------------------------------------------------------- #

    def _vivo(self, conversa_id: str, turno_id: str) -> TurnoVivo | None:
        self._limpar()
        vivo = self._vivos.get(turno_id)
        return vivo if vivo is not None and vivo.conversa_id == conversa_id else None

    def _turno_gravado(self, conversa_id: str, turno_id: str) -> Turno:
        turno = self.banco.turno(turno_id)
        if turno is None or turno.conversa_id != conversa_id:
            raise TurnoAusente("Esse turno não existe nesta conversa.")
        return turno

    def _estado_vivo(self, vivo: TurnoVivo) -> dict[str, Any]:
        return {
            "turno_id": vivo.id,
            "estado": vivo.estado.value,
            "ultimo_seq": vivo.ultimo_seq,
            "iniciado_texto": self._quando(vivo.iniciado),
        }

    def _estado_gravado(self, turno: Turno) -> dict[str, Any]:
        dados: dict[str, Any] = {
            "turno_id": turno.id,
            "estado": turno.estado.value,
            "ultimo_seq": turno.ultimo_seq,
            "iniciado_texto": self._quando(turno.iniciado),
        }
        if turno.terminado is not None:
            dados["terminado_texto"] = self._quando(turno.terminado)
        if turno.erro_categoria:
            dados["erro"] = {"categoria": turno.erro_categoria, "mensagem": turno.erro_mensagem}
        return dados

    def estado_do_turno(self, conversa_id: str, turno_id: str) -> dict[str, Any]:
        self._conversa(conversa_id)
        vivo = self._vivo(conversa_id, turno_id)
        if vivo is not None:
            return self._estado_vivo(vivo)
        return self._estado_gravado(self._turno_gravado(conversa_id, turno_id))

    def assinar(self, conversa_id: str, turno_id: str, desde: int) -> AsyncIterator[str] | None:
        """Os eventos depois de `desde`, em SSE; `None` quando não há mais nada a mandar."""
        self._conversa(conversa_id)
        vivo = self._vivo(conversa_id, turno_id)
        if vivo is not None:
            if vivo.estado.terminado and desde >= vivo.ultimo_seq:
                return None
            return self._transmitir(vivo, desde)
        turno = self._turno_gravado(conversa_id, turno_id)
        final = self._evento_final_gravado(turno)
        if desde >= final["seq"]:
            return None
        return _uma_vez(quadro_sse(final))

    def _evento_final_gravado(self, turno: Turno) -> dict[str, Any]:
        """O fim de um turno que já saiu da memória, reconstruído do banco."""
        seq = max(turno.ultimo_seq, 1)
        base: dict[str, Any] = {"seq": seq, "turno_id": turno.id}
        if turno.estado is EstadoDoTurno.CONCLUIDO:
            return {**base, "tipo": "turno.concluido"}
        if turno.estado is EstadoDoTurno.CANCELADO:
            return {**base, "tipo": "turno.cancelado"}
        falhou = {
            **base,
            "tipo": "turno.falhou",
            "categoria": turno.erro_categoria or "rede",
            "mensagem": turno.erro_mensagem or INTERROMPIDO,
        }
        if turno.estado is EstadoDoTurno.INTERROMPIDO:
            falhou["interrompido"] = True
        return falhou

    async def _transmitir(self, vivo: TurnoVivo, desde: int) -> AsyncIterator[str]:
        visto = max(0, desde)
        yield ": conectado\n\n"
        while True:
            sinal = vivo.sinal
            for evento in vivo.depois_de(visto):
                yield quadro_sse(evento)
                visto = int(evento["seq"])
            if vivo.estado.terminado and visto >= vivo.ultimo_seq:
                return
            try:
                await asyncio.wait_for(sinal.wait(), self.configuracao.keepalive_s)
            except TimeoutError:
                yield ": keepalive\n\n"

    async def esperar(self, turno_id: str) -> None:
        """Espera o turno terminar (para testes e para quem precisa do resultado)."""
        vivo = self._vivos.get(turno_id)
        if vivo is not None and vivo.tarefa is not None:
            await asyncio.gather(vivo.tarefa, return_exceptions=True)

    # -- o estado do chat ------------------------------------------------------ #

    async def estado_do_chat(self) -> dict[str, Any]:
        """Se o agente atende agora, e com que modelo. Nunca levanta: fora do ar é dado."""
        agora = time.monotonic()
        guardado = self._estado_do_chat
        if guardado is not None and agora - guardado[0] < self.configuracao.cache_do_estado_s:
            return guardado[1]
        dados = await self._medir_estado()
        self._estado_do_chat = (agora, dados)
        return dados

    async def _medir_estado(self) -> dict[str, Any]:
        home = self.home or hermes_home()
        try:
            cliente = self.cliente()
            perfil = cliente.perfil
        except Exception as erro:
            logger.warning("não consegui montar o cliente do Hermes: %s", erro)
            return {
                "disponivel": False,
                "motivo": MOTIVO_FORA_DO_AR,
                "detalhe_tecnico": str(erro),
                "perfil": None,
                "modelo": None,
            }
        modelo = ler_modelo(home, perfil)
        dados: dict[str, Any] = {
            "disponivel": False,
            "perfil": perfil,
            "modelo": modelo["modelo"] if modelo else None,
        }
        try:
            await cliente.saude()
            dados["disponivel"] = True
        except Exception as erro:
            dados["motivo"] = MOTIVO_FORA_DO_AR
            dados["detalhe_tecnico"] = str(erro)
        aviso = conferir_dossie(home, perfil, self.sessao.dossie.caminho)
        if aviso is not None:
            dados["aviso"], dados["aviso_tecnico"] = aviso
        return dados


async def _uma_vez(quadro: str) -> AsyncIterator[str]:
    yield quadro


__all__ = [
    "INSTRUCAO_DA_WEB",
    "LIMITE_DE_TOKENS",
    "Configuracao",
    "ConversaAusente",
    "ErroDaConversa",
    "MuitasMensagens",
    "Pedido",
    "PedidoInvalido",
    "ServicoDeConversa",
    "TurnoAusente",
    "TurnoEmAndamento",
    "TurnoVivo",
    "conferir_dossie",
    "linha_do_contexto",
    "mensagem_para_a_agente",
    "quadro_sse",
    "resolver_contexto",
]
