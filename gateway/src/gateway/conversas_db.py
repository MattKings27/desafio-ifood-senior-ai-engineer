"""As conversas da web: o que ela escreveu e o que o agente respondeu, já conferido.

O Hermes guarda o próprio histórico de cada sessão, mas guarda o texto de ANTES
do guard-rail: um valor que o plugin retirou continua lá. Por isso o histórico
que a tela mostra sai sempre daqui, e nunca do Hermes. Aqui mora:

- `conversas`: uma conversa da tela, com o título, qual é a atual e a sessão do
  Hermes em uso. Uma conversa atravessa várias sessões do Hermes (a compressão
  troca o id, e o backend abre sessão nova quando o contexto cresce demais), e
  para ela continua sendo uma conversa só;
- `mensagens`: a fala dela e a resposta do agente, em partes (texto e
  cards), com as atividades, o que foi retirado e como o turno terminou;
- `turnos`: cada vez que ela manda uma mensagem. O estado do turno sobrevive ao
  backend: um turno que estava em andamento quando o processo caiu vira
  `interrompido` no arranque seguinte, e a tela oferece reenviar. Os valores em
  reais que o motor devolveu em cada turno ficam guardados: são o que sustenta,
  nos turnos seguintes, um valor que o agente repete.

O arquivo é `.estado/conversas.db` ao lado do dossiê (`MISE_CONVERSAS` troca). É
um banco separado do dossiê de propósito: apagar as conversas não mexe em nada
do que ela decidiu, e o dossiê continua sendo a fonte da verdade do negócio.

As datas saem prontas para a tela (`quando_texto`: "hoje, 14:32", "ontem"), no
fuso dela (`MISE_FUSO`, padrão America/Sao_Paulo): o cliente não formata data.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

VAR_CONVERSAS: Final = "MISE_CONVERSAS"
VAR_DOSSIE: Final = "MISE_DOSSIE"
VAR_FUSO: Final = "MISE_FUSO"
#: O mesmo padrão de `mise.mcp_server.abrir_sessao`.
DOSSIE_PADRAO: Final = "~/.mise/dossie.db"
NOME_DO_ARQUIVO: Final = "conversas.db"
FUSO_PADRAO: Final = "America/Sao_Paulo"
#: O título de uma conversa até a primeira mensagem dela dar um melhor.
TITULO_PADRAO: Final = "Nova conversa"
#: O mais longo que um título pode ficar (o automático e o que ela escreve).
TAMANHO_DO_TITULO: Final = 80
#: O título automático corta a primeira mensagem aqui, na palavra.
TAMANHO_DO_TITULO_AUTOMATICO: Final = 48
#: Quantas mensagens uma conversa devolve de uma vez (as mais recentes).
LIMITE_DE_MENSAGENS: Final = 400

_DIAS_DA_SEMANA: Final = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
_UMA_SEMANA: Final = 6

ESQUEMA: Final = """
CREATE TABLE IF NOT EXISTS conversas (
    id                   TEXT PRIMARY KEY,
    titulo               TEXT NOT NULL,
    titulo_dela          INTEGER NOT NULL DEFAULT 0,
    criada               TEXT NOT NULL,
    atualizada           TEXT NOT NULL,
    atual                INTEGER NOT NULL DEFAULT 0,
    hermes_session_id    TEXT,
    sessoes_hermes       INTEGER NOT NULL DEFAULT 0,
    tokens_prompt_ultimo INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS mensagens (
    id          TEXT PRIMARY KEY,
    conversa_id TEXT NOT NULL REFERENCES conversas(id) ON DELETE CASCADE,
    turno_id    TEXT,
    papel       TEXT NOT NULL CHECK (papel IN ('senhora', 'consultora')),
    partes      TEXT NOT NULL DEFAULT '[]',
    texto_final TEXT,
    retirados   INTEGER NOT NULL DEFAULT 0,
    estado      TEXT NOT NULL,
    extras      TEXT NOT NULL DEFAULT '{}',
    criada      TEXT NOT NULL,
    ordem       INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mensagens_conversa ON mensagens(conversa_id, ordem);

CREATE TABLE IF NOT EXISTS turnos (
    id             TEXT PRIMARY KEY,
    conversa_id    TEXT NOT NULL REFERENCES conversas(id) ON DELETE CASCADE,
    mensagem_id    TEXT,
    id_cliente     TEXT,
    run_id         TEXT,
    estado         TEXT NOT NULL,
    iniciado       TEXT NOT NULL,
    terminado      TEXT,
    erro_categoria TEXT,
    erro_mensagem  TEXT,
    ultimo_seq     INTEGER NOT NULL DEFAULT 0,
    valores        TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_turnos_conversa ON turnos(conversa_id, iniciado);
CREATE INDEX IF NOT EXISTS idx_turnos_cliente ON turnos(conversa_id, id_cliente);
"""

#: Relógio do banco: devolve o agora, com fuso. Injetável em teste.
Relogio = Callable[[], datetime]


class Papel(StrEnum):
    """Quem fala: ela ou o agente."""

    SENHORA = "senhora"
    CONSULTORA = "consultora"


class EstadoDoTurno(StrEnum):
    """Como um turno está, ou como terminou."""

    EM_ANDAMENTO = "em_andamento"
    CONCLUIDO = "concluido"
    CANCELADO = "cancelado"
    FALHOU = "falhou"
    #: O backend caiu no meio: a tela oferece mandar de novo.
    INTERROMPIDO = "interrompido"

    @property
    def terminado(self) -> bool:
        return self is not EstadoDoTurno.EM_ANDAMENTO


@dataclass(frozen=True, slots=True)
class Conversa:
    id: str
    titulo: str
    #: Ela deu o título: o automático não troca mais.
    titulo_dela: bool
    criada: datetime
    atualizada: datetime
    atual: bool
    hermes_session_id: str | None
    #: Quantas sessões do Hermes a conversa já abriu (dá o título da próxima).
    sessoes_hermes: int
    #: O tamanho estimado do contexto no último turno: passa do limite, sessão nova.
    tokens_prompt_ultimo: int


@dataclass(frozen=True, slots=True)
class Mensagem:
    id: str
    conversa_id: str
    turno_id: str | None
    papel: Papel
    partes: list[dict[str, Any]]
    texto_final: str | None
    retirados: int
    estado: str
    #: Atividades, sugestões, resultado da ação, erro, contexto: o que acompanha a fala.
    extras: dict[str, Any]
    criada: datetime


@dataclass(frozen=True, slots=True)
class Turno:
    id: str
    conversa_id: str
    mensagem_id: str | None
    id_cliente: str | None
    run_id: str | None
    estado: EstadoDoTurno
    iniciado: datetime
    terminado: datetime | None
    erro_categoria: str | None
    erro_mensagem: str | None
    ultimo_seq: int
    #: Os valores em reais que o motor devolveu neste turno.
    valores: tuple[Decimal, ...] = field(default=())


def novo_id(prefixo: str) -> str:
    """`cv-3f9a0c1b2d4e`: prefixo e 12 hexadecimais aleatórios."""
    return f"{prefixo}-{secrets.token_hex(6)}"


def _agora_utc() -> datetime:
    return datetime.now(UTC)


def _data(texto: str) -> datetime:
    return datetime.fromisoformat(texto)


def _data_ou_nada(texto: str | None) -> datetime | None:
    return _data(texto) if texto else None


def _decimais(bruto: str) -> tuple[Decimal, ...]:
    try:
        return tuple(Decimal(str(v)) for v in json.loads(bruto or "[]"))
    except (ValueError, TypeError, InvalidOperation):
        logger.warning("valores de turno ilegíveis no banco de conversas; ignorados")
        return ()


def _json(valor: object) -> str:
    return json.dumps(valor, ensure_ascii=False, separators=(",", ":"), default=str)


def _carregar(bruto: str | None, padrao: Any) -> Any:
    try:
        return json.loads(bruto) if bruto else padrao
    except ValueError:
        return padrao


def _para_conversa(linha: sqlite3.Row) -> Conversa:
    return Conversa(
        id=linha["id"],
        titulo=linha["titulo"],
        titulo_dela=bool(linha["titulo_dela"]),
        criada=_data(linha["criada"]),
        atualizada=_data(linha["atualizada"]),
        atual=bool(linha["atual"]),
        hermes_session_id=linha["hermes_session_id"],
        sessoes_hermes=int(linha["sessoes_hermes"]),
        tokens_prompt_ultimo=int(linha["tokens_prompt_ultimo"]),
    )


def _para_mensagem(linha: sqlite3.Row) -> Mensagem:
    partes = _carregar(linha["partes"], [])
    extras = _carregar(linha["extras"], {})
    return Mensagem(
        id=linha["id"],
        conversa_id=linha["conversa_id"],
        turno_id=linha["turno_id"],
        papel=Papel(linha["papel"]),
        partes=partes if isinstance(partes, list) else [],
        texto_final=linha["texto_final"],
        retirados=int(linha["retirados"]),
        estado=linha["estado"],
        extras=extras if isinstance(extras, dict) else {},
        criada=_data(linha["criada"]),
    )


def _para_turno(linha: sqlite3.Row) -> Turno:
    return Turno(
        id=linha["id"],
        conversa_id=linha["conversa_id"],
        mensagem_id=linha["mensagem_id"],
        id_cliente=linha["id_cliente"],
        run_id=linha["run_id"],
        estado=EstadoDoTurno(linha["estado"]),
        iniciado=_data(linha["iniciado"]),
        terminado=_data_ou_nada(linha["terminado"]),
        erro_categoria=linha["erro_categoria"],
        erro_mensagem=linha["erro_mensagem"],
        ultimo_seq=int(linha["ultimo_seq"]),
        valores=_decimais(linha["valores"]),
    )


def limpar_titulo(titulo: str) -> str:
    """Uma linha, sem espaço sobrando, no tamanho máximo."""
    limpo = " ".join(titulo.split())
    return limpo[:TAMANHO_DO_TITULO].rstrip()


def titulo_automatico(texto: str) -> str | None:
    """O título tirado da primeira mensagem dela: a primeira linha, cortada na palavra."""
    primeira = next((linha for linha in texto.splitlines() if linha.strip()), "")
    limpo = " ".join(primeira.split()).strip(" .,;:!?")
    if not limpo:
        return None
    if len(limpo) > TAMANHO_DO_TITULO_AUTOMATICO:
        corte = limpo[:TAMANHO_DO_TITULO_AUTOMATICO].rsplit(" ", 1)[0]
        limpo = corte.rstrip(" .,;:") + "…"
    return limpo[:1].upper() + limpo[1:]


def caminho_do_banco(ambiente: Mapping[str, str] | None = None) -> Path:
    """`MISE_CONVERSAS`; senão `conversas.db` na mesma pasta do dossiê."""
    amb = os.environ if ambiente is None else ambiente
    explicito = amb.get(VAR_CONVERSAS, "").strip()
    if explicito:
        return Path(explicito).expanduser()
    dossie = Path(amb.get(VAR_DOSSIE, "").strip() or DOSSIE_PADRAO).expanduser()
    return dossie.parent / NOME_DO_ARQUIVO


# --------------------------------------------------------------------------- #
# Datas prontas para a tela                                                    #
# --------------------------------------------------------------------------- #


def fuso_dela(ambiente: Mapping[str, str] | None = None) -> tzinfo:
    """O fuso da Dona Maria. Sem a base de fusos no sistema, UTC−3 (sem horário de verão)."""
    amb = os.environ if ambiente is None else ambiente
    nome = amb.get(VAR_FUSO, "").strip() or FUSO_PADRAO
    try:
        return ZoneInfo(nome)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("fuso %s indisponível; usando UTC-3", nome)
        return timezone(timedelta(hours=-3))


def quando_texto(
    momento: datetime, agora: datetime, *, com_hora: bool = True, fuso: tzinfo | None = None
) -> str:
    """ "hoje, 14:32", "ontem, 09:10", "terça, 18:00", "12/09, 08:15", "12/09/2025".

    Sem `com_hora`, só o dia de hoje leva a hora: é o jeito da lista de conversas
    ("hoje, 15:02", "ontem").
    """
    zona = fuso or fuso_dela()
    local, hoje = momento.astimezone(zona), agora.astimezone(zona)
    hora = local.strftime("%H:%M")
    dias = (hoje.date() - local.date()).days
    if dias <= 0:
        return f"hoje, {hora}"
    if dias == 1:
        dia = "ontem"
    elif dias <= _UMA_SEMANA:
        dia = _DIAS_DA_SEMANA[local.weekday()]
    elif local.year == hoje.year:
        dia = local.strftime("%d/%m")
    else:
        return local.strftime("%d/%m/%Y")
    return f"{dia}, {hora}" if com_hora else dia


# --------------------------------------------------------------------------- #
# O banco                                                                      #
# --------------------------------------------------------------------------- #


class BancoDeConversas:
    """As conversas, as mensagens e os turnos, em SQLite.

    Uma conexão compartilhada entre as threads (a API roda rotas síncronas num
    pool), serializada por um `RLock`, como o dossiê. WAL para ler enquanto
    alguém grava; chaves estrangeiras ligadas, para apagar uma conversa levar
    junto as mensagens e os turnos dela.
    """

    def __init__(self, caminho: str | Path, relogio: Relogio | None = None) -> None:
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._relogio: Relogio = relogio or _agora_utc
        self._trava = threading.RLock()
        self._conexao = sqlite3.connect(
            self.caminho, isolation_level=None, check_same_thread=False, timeout=10
        )
        self._conexao.row_factory = sqlite3.Row
        with closing(self._conexao.cursor()) as cur:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.executescript(ESQUEMA)

    @classmethod
    def do_ambiente(
        cls, ambiente: Mapping[str, str] | None = None, relogio: Relogio | None = None
    ) -> BancoDeConversas:
        return cls(caminho_do_banco(ambiente), relogio)

    def fechar(self) -> None:
        with self._trava:
            self._conexao.close()

    def agora(self) -> datetime:
        return self._relogio()

    @contextmanager
    def _transacao(self) -> Iterator[sqlite3.Cursor]:
        with self._trava, closing(self._conexao.cursor()) as cur:
            cur.execute("BEGIN IMMEDIATE")
            try:
                yield cur
            except BaseException:
                cur.execute("ROLLBACK")
                raise
            cur.execute("COMMIT")

    @contextmanager
    def _leitura(self) -> Iterator[sqlite3.Cursor]:
        with self._trava, closing(self._conexao.cursor()) as cur:
            yield cur

    # -- conversas ---------------------------------------------------------- #

    def criar_conversa(self, titulo: str | None = None, *, atual: bool = True) -> Conversa:
        """Uma conversa nova. Por padrão ela vira a atual, como quem abre uma aba."""
        agora = self.agora().isoformat()
        conversa_id = novo_id("cv")
        limpo = limpar_titulo(titulo or "")
        with self._transacao() as cur:
            if atual:
                cur.execute("UPDATE conversas SET atual = 0 WHERE atual = 1")
            cur.execute(
                "INSERT INTO conversas (id, titulo, titulo_dela, criada, atualizada, atual) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (conversa_id, limpo or TITULO_PADRAO, int(bool(limpo)), agora, agora, int(atual)),
            )
        conversa = self.conversa(conversa_id)
        assert conversa is not None
        return conversa

    def conversa(self, conversa_id: str) -> Conversa | None:
        with self._leitura() as cur:
            linha = cur.execute("SELECT * FROM conversas WHERE id = ?", (conversa_id,)).fetchone()
        return _para_conversa(linha) if linha else None

    def conversas(self) -> list[Conversa]:
        """Da mais recente para a mais antiga."""
        with self._leitura() as cur:
            linhas = cur.execute(
                "SELECT * FROM conversas ORDER BY atualizada DESC, criada DESC, id"
            ).fetchall()
        return [_para_conversa(linha) for linha in linhas]

    def atual(self) -> str | None:
        with self._leitura() as cur:
            linha = cur.execute("SELECT id FROM conversas WHERE atual = 1").fetchone()
        return str(linha["id"]) if linha else None

    def marcar_atual(self, conversa_id: str) -> None:
        with self._transacao() as cur:
            cur.execute(
                "UPDATE conversas SET atual = 0 WHERE atual = 1 AND id != ?", (conversa_id,)
            )
            cur.execute("UPDATE conversas SET atual = 1 WHERE id = ?", (conversa_id,))

    def renomear(self, conversa_id: str, titulo: str) -> None:
        """O título que ela escolheu; o automático não troca mais."""
        limpo = limpar_titulo(titulo)
        with self._transacao() as cur:
            cur.execute(
                "UPDATE conversas SET titulo = ?, titulo_dela = 1 WHERE id = ?",
                (limpo or TITULO_PADRAO, conversa_id),
            )

    def dar_titulo_automatico(self, conversa_id: str, texto: str) -> None:
        """O título da primeira mensagem, se ela não deu um e a conversa ainda tem o padrão."""
        titulo = titulo_automatico(texto)
        if titulo is None:
            return
        with self._transacao() as cur:
            cur.execute(
                "UPDATE conversas SET titulo = ? WHERE id = ? AND titulo_dela = 0 AND titulo = ?",
                (titulo, conversa_id, TITULO_PADRAO),
            )

    def tocar(self, conversa_id: str) -> None:
        """A conversa mexeu agora: sobe na lista."""
        with self._transacao() as cur:
            cur.execute(
                "UPDATE conversas SET atualizada = ? WHERE id = ?",
                (self.agora().isoformat(), conversa_id),
            )

    def apagar(self, conversa_id: str) -> str | None:
        """Apaga a conversa, com as mensagens e os turnos. Devolve qual ficou sendo a atual."""
        with self._transacao() as cur:
            era_atual = cur.execute(
                "SELECT atual FROM conversas WHERE id = ?", (conversa_id,)
            ).fetchone()
            cur.execute("DELETE FROM conversas WHERE id = ?", (conversa_id,))
            if era_atual is not None and era_atual["atual"]:
                seguinte = cur.execute(
                    "SELECT id FROM conversas ORDER BY atualizada DESC, criada DESC LIMIT 1"
                ).fetchone()
                if seguinte is not None:
                    cur.execute("UPDATE conversas SET atual = 1 WHERE id = ?", (seguinte["id"],))
        return self.atual()

    def apagar_tudo(self) -> int:
        """Apaga todas as conversas, com as mensagens e os turnos, sem mexer no arquivo.

        Devolve quantas conversas havia. É o "Restaurar os dados": o arquivo
        continua aberto e no lugar, só as linhas saem.
        """
        with self._transacao() as cur:
            quantas = int(cur.execute("SELECT COUNT(*) FROM conversas").fetchone()[0])
            cur.execute("DELETE FROM turnos")
            cur.execute("DELETE FROM mensagens")
            cur.execute("DELETE FROM conversas")
        return quantas

    def copiar_para(self, destino: str | Path) -> Path:
        """Uma cópia inteira das conversas em `destino`, com o que ainda está no WAL."""
        caminho = Path(destino)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with self._trava, closing(sqlite3.connect(caminho)) as copia:
            self._conexao.backup(copia)
        return caminho

    def usar_sessao_hermes(self, conversa_id: str, sessao_id: str, *, nova: bool) -> None:
        """A sessão do Hermes em uso. `nova` quando o backend abriu a sessão (conta mais uma)."""
        with self._transacao() as cur:
            if nova:
                cur.execute(
                    "UPDATE conversas SET hermes_session_id = ?, "
                    "sessoes_hermes = sessoes_hermes + 1, tokens_prompt_ultimo = 0 WHERE id = ?",
                    (sessao_id, conversa_id),
                )
            else:
                cur.execute(
                    "UPDATE conversas SET hermes_session_id = ? WHERE id = ?",
                    (sessao_id, conversa_id),
                )

    def registrar_tokens(self, conversa_id: str, tokens: int) -> None:
        with self._transacao() as cur:
            cur.execute(
                "UPDATE conversas SET tokens_prompt_ultimo = ? WHERE id = ?",
                (max(0, int(tokens)), conversa_id),
            )

    # -- mensagens ---------------------------------------------------------- #

    def inserir_mensagem(
        self,
        conversa_id: str,
        papel: Papel,
        partes: list[dict[str, Any]],
        *,
        estado: str,
        turno_id: str | None = None,
        texto_final: str | None = None,
        retirados: int = 0,
        extras: Mapping[str, Any] | None = None,
    ) -> str:
        mensagem_id = novo_id("m")
        with self._transacao() as cur:
            ordem = cur.execute(
                "SELECT COALESCE(MAX(ordem), 0) + 1 AS proxima FROM mensagens "
                "WHERE conversa_id = ?",
                (conversa_id,),
            ).fetchone()["proxima"]
            cur.execute(
                "INSERT INTO mensagens (id, conversa_id, turno_id, papel, partes, texto_final, "
                "retirados, estado, extras, criada, ordem) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    mensagem_id,
                    conversa_id,
                    turno_id,
                    papel.value,
                    _json(partes),
                    texto_final,
                    retirados,
                    estado,
                    _json(dict(extras or {})),
                    self.agora().isoformat(),
                    ordem,
                ),
            )
        return mensagem_id

    def mensagem(self, mensagem_id: str) -> Mensagem | None:
        with self._leitura() as cur:
            linha = cur.execute("SELECT * FROM mensagens WHERE id = ?", (mensagem_id,)).fetchone()
        return _para_mensagem(linha) if linha else None

    def mensagens(self, conversa_id: str, limite: int = LIMITE_DE_MENSAGENS) -> list[Mensagem]:
        """As `limite` mais recentes, da mais antiga para a mais nova."""
        with self._leitura() as cur:
            linhas = cur.execute(
                "SELECT * FROM (SELECT * FROM mensagens WHERE conversa_id = ? "
                "ORDER BY ordem DESC LIMIT ?) ORDER BY ordem",
                (conversa_id, limite),
            ).fetchall()
        return [_para_mensagem(linha) for linha in linhas]

    def contar_mensagens(self, conversa_id: str) -> int:
        with self._leitura() as cur:
            linha = cur.execute(
                "SELECT COUNT(*) AS n FROM mensagens WHERE conversa_id = ?", (conversa_id,)
            ).fetchone()
        return int(linha["n"])

    def falas_dela(self, conversa_id: str) -> list[str]:
        """Tudo o que ela escreveu nesta conversa: o que ela disse tem procedência."""
        with self._leitura() as cur:
            linhas = cur.execute(
                "SELECT partes FROM mensagens WHERE conversa_id = ? AND papel = 'senhora' "
                "ORDER BY ordem",
                (conversa_id,),
            ).fetchall()
        falas: list[str] = []
        for linha in linhas:
            for parte in _carregar(linha["partes"], []):
                if isinstance(parte, dict) and parte.get("tipo") == "texto":
                    falas.append(str(parte.get("texto") or ""))
        return falas

    def textos_finais(self, conversa_id: str) -> list[str]:
        """Os textos do agente que já passaram pela conferência."""
        with self._leitura() as cur:
            linhas = cur.execute(
                "SELECT texto_final FROM mensagens WHERE conversa_id = ? AND papel = 'consultora' "
                "AND texto_final IS NOT NULL ORDER BY ordem",
                (conversa_id,),
            ).fetchall()
        return [str(linha["texto_final"]) for linha in linhas]

    # -- turnos ------------------------------------------------------------- #

    def criar_turno(
        self,
        conversa_id: str,
        mensagem_id: str | None,
        id_cliente: str | None,
        *,
        turno_id: str | None = None,
    ) -> Turno:
        """Um turno em andamento. `turno_id` quando quem chama já precisou do id antes."""
        turno_id = turno_id or novo_id("t")
        with self._transacao() as cur:
            cur.execute(
                "INSERT INTO turnos (id, conversa_id, mensagem_id, id_cliente, estado, iniciado) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    turno_id,
                    conversa_id,
                    mensagem_id,
                    id_cliente,
                    EstadoDoTurno.EM_ANDAMENTO.value,
                    self.agora().isoformat(),
                ),
            )
        turno = self.turno(turno_id)
        assert turno is not None
        return turno

    def turno(self, turno_id: str) -> Turno | None:
        with self._leitura() as cur:
            linha = cur.execute("SELECT * FROM turnos WHERE id = ?", (turno_id,)).fetchone()
        return _para_turno(linha) if linha else None

    def turno_do_cliente(self, conversa_id: str, id_cliente: str) -> Turno | None:
        """O turno mais recente que este `id_cliente` abriu nesta conversa."""
        with self._leitura() as cur:
            linha = cur.execute(
                "SELECT * FROM turnos WHERE conversa_id = ? AND id_cliente = ? "
                "ORDER BY iniciado DESC, rowid DESC LIMIT 1",
                (conversa_id, id_cliente),
            ).fetchone()
        return _para_turno(linha) if linha else None

    def turno_em_andamento(self, conversa_id: str) -> Turno | None:
        with self._leitura() as cur:
            linha = cur.execute(
                "SELECT * FROM turnos WHERE conversa_id = ? AND estado = ? "
                "ORDER BY iniciado DESC LIMIT 1",
                (conversa_id, EstadoDoTurno.EM_ANDAMENTO.value),
            ).fetchone()
        return _para_turno(linha) if linha else None

    def registrar_run(self, turno_id: str, run_id: str) -> None:
        with self._transacao() as cur:
            cur.execute("UPDATE turnos SET run_id = ? WHERE id = ?", (run_id, turno_id))

    def terminar_turno(
        self,
        turno_id: str,
        estado: EstadoDoTurno,
        *,
        ultimo_seq: int,
        erro_categoria: str | None = None,
        erro_mensagem: str | None = None,
        valores: tuple[Decimal, ...] = (),
    ) -> None:
        with self._transacao() as cur:
            cur.execute(
                "UPDATE turnos SET estado = ?, terminado = ?, ultimo_seq = ?, erro_categoria = ?, "
                "erro_mensagem = ?, valores = ? WHERE id = ?",
                (
                    estado.value,
                    self.agora().isoformat(),
                    ultimo_seq,
                    erro_categoria,
                    erro_mensagem,
                    _json([str(v) for v in valores]),
                    turno_id,
                ),
            )

    def marcar_interrompidos(self) -> list[str]:
        """No arranque: o que estava em andamento morreu com o processo anterior."""
        with self._transacao() as cur:
            ids = [
                str(linha["id"])
                for linha in cur.execute(
                    "SELECT id FROM turnos WHERE estado = ?", (EstadoDoTurno.EM_ANDAMENTO.value,)
                ).fetchall()
            ]
            cur.execute(
                "UPDATE turnos SET estado = ?, terminado = ? WHERE estado = ?",
                (
                    EstadoDoTurno.INTERROMPIDO.value,
                    self.agora().isoformat(),
                    EstadoDoTurno.EM_ANDAMENTO.value,
                ),
            )
        return ids

    def valores_conferidos(self, conversa_id: str) -> set[Decimal]:
        """Todo valor em reais que o motor devolveu, em qualquer turno desta conversa."""
        with self._leitura() as cur:
            linhas = cur.execute(
                "SELECT valores FROM turnos WHERE conversa_id = ?", (conversa_id,)
            ).fetchall()
        valores: set[Decimal] = set()
        for linha in linhas:
            valores.update(_decimais(linha["valores"]))
        return valores


__all__ = [
    "DOSSIE_PADRAO",
    "FUSO_PADRAO",
    "LIMITE_DE_MENSAGENS",
    "TITULO_PADRAO",
    "BancoDeConversas",
    "Conversa",
    "EstadoDoTurno",
    "Mensagem",
    "Papel",
    "Turno",
    "caminho_do_banco",
    "fuso_dela",
    "limpar_titulo",
    "novo_id",
    "quando_texto",
    "titulo_automatico",
]
