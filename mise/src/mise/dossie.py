"""Persistência do dossiê da Dona Maria.

A memória embutida do Hermes guarda no máximo 1.375 caracteres de perfil de
usuário, e é um instantâneo tirado no início da sessão. Para "equipamentos,
técnicas, restrições, pratos aceitos e recusados, orçamento consumido" isso é
pequeno demais e tarde demais.

Então o dossiê estruturado mora aqui, em SQLite, e é a **fonte da verdade**. A
memória do Hermes fica com a versão compacta ("Dona Maria, fogão 4 bocas, sem
forno"), que é o que precisa estar no prompt em toda conversa.

Duas decisões que o resto do sistema depende:

**Log de decisões é append-only.** Aceitar e depois recusar um prato não apaga
o aceite: são dois eventos. A trilha é o que permite responder "por que este
prato entrou no cardápio?" três semanas depois. Desfazer também é um evento, que
aponta (`desfaz`) para o que desfez.

**Escritas são idempotentes por chave.** Um retry de rede não pode registrar a
mesma decisão duas vezes nem debitar o orçamento em dobro.

**A conexão atravessa threads.** O servidor MCP é single-thread, mas a API HTTP
roda endpoints síncronos num threadpool, e o SQLite prende a conexão à thread
que a criou. Em vez de abrir conexão por requisição (que perderia o WAL quente
e multiplicaria file handles), a conexão é compartilhada com
`check_same_thread=False` e um `RLock` serializa o acesso. O WAL já resolve
leitura concorrente; o lock existe para as escritas.

**E atravessa processos.** O servidor MCP que o gateway do Hermes sobe e a API
da tela abrem o mesmo arquivo. O `RLock` não enxerga o outro processo: conferir
o orçamento e depois gravar a compra, em dois comandos soltos, deixava as duas
portas verem o mesmo saldo e gastarem duas vezes. Sequência de conferir e gravar
vai em `transacao()`, que abre com `BEGIN IMMEDIATE` e segura a escrita até o
fim.

**Cada módulo cria as próprias tabelas.** `garantir_esquema(ddl, colunas)` é o
mesmo mecanismo que o dossiê usa para si: `CREATE TABLE IF NOT EXISTS` e as
colunas novas acrescentadas a um banco antigo sem apagar o que ele guarda.

**Estorno é uma linha nova, nunca um apagão.** Devolver uma compra aos R$ 80,00
grava em `gastos` uma linha com os centavos negativos e a coluna `estorna`
apontando a compra original. O saldo é a soma de tudo, então a devolução se
anula com a compra; `compras()` (o que vira estoque no portão) ignora as duas.
A compra que ela fez pela despensa ("comprei com os R$ 80") leva o `item_id`
do item, e é por ele que tirar o item devolve o dinheiro.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import unicodedata
import uuid
from collections.abc import Callable, Iterable
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from mise.compras import Comprado, Cotacao, Medida, medida
from mise.dinheiro import Dinheiro
from mise.erros import Ausente, ErroDeUso, OrcamentoExcedido
from mise.perfil import Gosto, PerfilCozinha
from mise.receita import Receita

if TYPE_CHECKING:
    from collections.abc import Iterator

#: Orçamento para compras complementares, conforme o enunciado.
ORCAMENTO_INICIAL: Final = Dinheiro(Decimal("80.00"))

#: Sem chave de quem chamou, a mesma compra dentro deste intervalo é a mesma
#: compra repetida (o retry, o agente chamando duas vezes), e não uma segunda.
JANELA_DE_COMPRA_REPETIDA: Final = timedelta(minutes=10)

ESQUEMA: Final = """
CREATE TABLE IF NOT EXISTS perfil (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    dados       TEXT NOT NULL,
    atualizado  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisoes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chave       TEXT NOT NULL UNIQUE,
    prato       TEXT NOT NULL,
    decisao     TEXT NOT NULL,
    motivo      TEXT NOT NULL DEFAULT '',
    detalhes    TEXT NOT NULL DEFAULT '{}',
    registrado  TEXT NOT NULL,
    canal       TEXT NOT NULL DEFAULT 'conversa',
    desfaz      INTEGER
);

CREATE INDEX IF NOT EXISTS idx_decisoes_prato ON decisoes(prato);

CREATE TABLE IF NOT EXISTS gostos (
    prato       TEXT PRIMARY KEY,
    gosto       TEXT NOT NULL,
    impedimento TEXT NOT NULL DEFAULT '',
    registrado  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS precos_mercado (
    ingrediente TEXT PRIMARY KEY,
    centavos    INTEGER NOT NULL CHECK (centavos >= 0),
    origem      TEXT NOT NULL,
    registrado  TEXT NOT NULL,
    quantidade  TEXT,
    unidade     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS candidatas (
    nome        TEXT PRIMARY KEY,
    dados       TEXT NOT NULL,
    registrado  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gastos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chave       TEXT NOT NULL UNIQUE,
    descricao   TEXT NOT NULL,
    centavos    INTEGER NOT NULL,
    registrado  TEXT NOT NULL,
    ingrediente TEXT,
    quantidade  TEXT,
    unidade     TEXT NOT NULL DEFAULT '',
    canal       TEXT NOT NULL DEFAULT 'conversa',
    estorna     INTEGER,
    item_id     TEXT
);
"""

#: Uma coluna acrescentada depois: (tabela, coluna, definição). A definição vem
#: do código, nunca de entrada de usuário.
ColunaNova = tuple[str, str, str]

#: Colunas que chegaram depois da primeira versão do esquema. Um dossiê antigo
#: guarda o que ela já respondeu; recriar a tabela apagaria isso.
COLUNAS_NOVAS: Final[tuple[ColunaNova, ...]] = (
    ("precos_mercado", "quantidade", "TEXT"),
    ("precos_mercado", "unidade", "TEXT NOT NULL DEFAULT ''"),
    ("gastos", "ingrediente", "TEXT"),
    ("gastos", "quantidade", "TEXT"),
    ("gastos", "unidade", "TEXT NOT NULL DEFAULT ''"),
    ("decisoes", "canal", "TEXT NOT NULL DEFAULT 'conversa'"),
    ("decisoes", "desfaz", "INTEGER"),
    ("gastos", "canal", "TEXT NOT NULL DEFAULT 'conversa'"),
    ("gastos", "estorna", "INTEGER"),
    ("gastos", "item_id", "TEXT"),
    # A ponte entre o nome da receita em avaliação e o id dela no catálogo.
    ("candidatas", "receita_id", "TEXT"),
)

#: Nome de tabela ou coluna que pode ir para dentro de um `ALTER TABLE`.
_IDENTIFICADOR: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: Relógio do dossiê: devolve o agora, com fuso. Injetável em teste.
Relogio = Callable[[], datetime]


class Canal(StrEnum):
    """Por onde a ação dela chegou: a tela ou a conversa com o agente.

    Fica gravado em cada decisão e em cada compra. O histórico diz "a senhora
    aceitou pela tela" ou "pela conversa", e desfazer sabe de onde veio o que
    está desfazendo. Cada ponto de entrada define o seu em `Sessao.canal`.
    """

    TELA = "tela"
    CONVERSA = "conversa"


def _canal(canal: Canal | str) -> Canal:
    try:
        return Canal(canal)
    except ValueError:
        validos = ", ".join(c.value for c in Canal)
        raise ErroDeUso(f"canal desconhecido: {canal}", validos=validos) from None


class Decisao(StrEnum):
    """O que a Dona Maria decidiu sobre um prato. **Ela** decide, não o agente."""

    ACEITO = "aceito"
    RECUSADO = "recusado"
    ADIADO = "adiado"


@dataclass(frozen=True, slots=True)
class RegistroDecisao:
    prato: str
    decisao: Decisao
    motivo: str
    detalhes: dict[str, Any]
    registrado: datetime
    #: A linha no dossiê: é por ela que uma decisão posterior diz qual desfaz.
    id: int | None = None
    #: Por onde chegou: `tela` ou `conversa` (ver `Canal`).
    canal: str = Canal.CONVERSA.value
    #: A decisão anterior, do mesmo prato, que esta desfaz; `None` se não desfaz nada.
    desfaz: int | None = None

    def __str__(self) -> str:
        quando = self.registrado.strftime("%d/%m %H:%M")
        porque = f" ({self.motivo})" if self.motivo else ""
        return f"[{quando}] {self.prato}: {self.decisao.value}{porque}"


@dataclass(frozen=True, slots=True)
class OpiniaoSobrePrato:
    """O que ela acha de fazer um prato, e o que ela mesma vê de empecilho.

    O impedimento é texto livre de propósito. Guarda o que o §2.1 pede ("vê
    algum impedimento?"), e é justamente a resposta que nenhuma taxonomia nossa
    antecipa: "meu filho tem alergia a camarão", "isso meleca o fogão todo",
    "não tenho paciência de ficar mexendo". Normalizar isso em enum perderia a
    única informação que só ela tem.
    """

    prato: str
    gosto: Gosto
    impedimento: str
    registrado: datetime

    def __str__(self) -> str:
        porque = f" ({self.impedimento})" if self.impedimento else ""
        return f"{self.prato}: {self.gosto.value.replace('_', ' ')}{porque}"


class OrigemPreco(StrEnum):
    """De onde veio a cotação de um ingrediente que falta comprar.

    Importa para a conversa, não só para o registro: "a senhora me disse que
    custa R$ 8,00" e "achei R$ 8,00 num mercado online" pedem confianças
    diferentes, e é ela quem decide se aceita a segunda.
    """

    INFORMADO_POR_ELA = "informado_por_ela"
    PESQUISADO_NA_WEB = "pesquisado_na_web"
    ESTIMADO = "estimado"


@dataclass(frozen=True, slots=True)
class PrecoMercado:
    """Quanto custa comprar um ingrediente, e por qual quantidade, como ela disse."""

    ingrediente: str
    valor: Dinheiro
    origem: OrigemPreco
    registrado: datetime
    quantidade: Decimal | None = None
    unidade: str = ""

    @property
    def cotacao(self) -> Cotacao:
        por = (
            medida(self.quantidade, self.unidade, self.ingrediente)
            if self.quantidade is not None
            else None
        )
        return Cotacao(self.valor, por, self.origem.value)

    def __str__(self) -> str:
        por = f" por {self.cotacao.por}" if self.cotacao.por else ""
        return f"{self.ingrediente}: {self.valor}{por} ({self.origem.value.replace('_', ' ')})"


@dataclass(frozen=True, slots=True)
class EstadoOrcamento:
    """Quanto dos R$ 80,00 já foi comprometido."""

    inicial: Dinheiro
    gasto: Dinheiro

    @property
    def restante(self) -> Dinheiro:
        return self.inicial - self.gasto

    @property
    def fracao_usada(self) -> float:
        if self.inicial.valor == 0:
            return 0.0
        return float(self.gasto.valor / self.inicial.valor)

    def cabe(self, valor: Dinheiro) -> bool:
        return valor.valor <= self.restante.valor

    def __str__(self) -> str:
        return f"{self.gasto} de {self.inicial} usados · restam {self.restante}"


@dataclass(frozen=True, slots=True)
class LinhaDoExtrato:
    """Uma linha dos R$ 80,00: uma compra, um gasto ou a devolução de um deles.

    `estorna` é a compra que esta linha devolve (e aí `valor` é negativo);
    `estornada` diz que esta compra já foi devolvida. `item_id` liga a compra ao
    item que ela acrescentou na despensa.
    """

    id: int
    descricao: str
    valor: Dinheiro
    registrado: datetime
    canal: str
    ingrediente: str | None = None
    item_id: str | None = None
    estorna: int | None = None
    estornada: bool = False

    @property
    def e_estorno(self) -> bool:
        return self.estorna is not None

    @property
    def ativa(self) -> bool:
        """Uma compra que conta: não é devolução e não foi devolvida."""
        return not self.e_estorno and not self.estornada


def _para_opiniao(linha: sqlite3.Row) -> OpiniaoSobrePrato:
    return OpiniaoSobrePrato(
        prato=linha["prato"],
        gosto=Gosto(linha["gosto"]),
        impedimento=linha["impedimento"],
        registrado=datetime.fromisoformat(linha["registrado"]),
    )


def _exigir_medida(ingrediente: str, quantidade: Decimal | None, unidade: str) -> None:
    """Quantidade informada tem que ser positiva e interpretável; senão é erro de uso.

    Guardar "0 kg" ou uma unidade que ninguém consegue ler produziria um custo
    por unidade infinito ou nenhum, e o erro só apareceria longe daqui.
    """
    if quantidade is None:
        return
    if quantidade <= 0 or medida(quantidade, unidade, ingrediente) is None:
        raise ErroDeUso(
            f"não consegui entender a quantidade {quantidade} {unidade}".strip(),
            ingrediente=ingrediente,
        )


def _chave_de_prato(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.casefold().split())


def _para_preco(linha: sqlite3.Row) -> PrecoMercado:
    return PrecoMercado(
        ingrediente=linha["ingrediente"],
        valor=Dinheiro(Decimal(linha["centavos"]) / 100),
        origem=OrigemPreco(linha["origem"]),
        registrado=datetime.fromisoformat(linha["registrado"]),
        quantidade=Decimal(linha["quantidade"]) if linha["quantidade"] else None,
        unidade=linha["unidade"] or "",
    )


class Dossie:
    """O estado durável da consultoria, em SQLite.

    Uso como contexto para garantir fechamento da conexão:

        with Dossie(caminho) as dossie:
            dossie.salvar_perfil(perfil)
    """

    def __init__(
        self,
        caminho: str | Path,
        orcamento: Dinheiro = ORCAMENTO_INICIAL,
        relogio: Relogio | None = None,
    ) -> None:
        self.caminho = Path(caminho)
        self.orcamento_inicial = orcamento
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._relogio: Relogio = relogio or _agora_utc
        self._trava = threading.RLock()
        self._profundidade = 0
        self._conexao = sqlite3.connect(self.caminho, isolation_level=None, check_same_thread=False)
        self._conexao.row_factory = sqlite3.Row
        with closing(self._conexao.cursor()) as cur:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
        self.garantir_esquema(ESQUEMA, COLUNAS_NOVAS)

    def __enter__(self) -> Dossie:
        return self

    def __exit__(self, *_: object) -> None:
        self.fechar()

    def fechar(self) -> None:
        with self._trava:
            self._conexao.close()

    def copiar_para(self, destino: str | Path) -> Path:
        """Uma cópia inteira do dossiê em `destino`, com o que ainda está no WAL.

        Usa a cópia do próprio SQLite (`backup`), que lê um retrato consistente
        enquanto o arquivo segue aberto por outros processos: o original não
        muda nem sai do lugar.
        """
        caminho = Path(destino)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with self._trava, closing(sqlite3.connect(caminho)) as copia:
            self._conexao.backup(copia)
        return caminho

    # -- esquema, transação e relógio -------------------------------------- #

    def garantir_esquema(self, ddl: str, colunas_novas: Iterable[ColunaNova] = ()) -> None:
        """Cria as tabelas de `ddl` e acrescenta as colunas que faltarem. Idempotente.

        É como cada módulo do motor cria as tabelas dele, no próprio módulo, sem
        um arquivo de esquema que todos editam. `ddl` usa `CREATE ... IF NOT
        EXISTS`; `colunas_novas` são as que chegaram depois da primeira versão
        da tabela, e entram num banco antigo sem apagar o que ele guarda.

        Não roda dentro de `transacao()`: o `executescript` do SQLite fecha a
        transação em aberto antes de executar.
        """
        colunas = tuple(colunas_novas)
        for tabela, coluna, _ in colunas:
            if not (_IDENTIFICADOR.fullmatch(tabela) and _IDENTIFICADOR.fullmatch(coluna)):
                raise ErroDeUso("nome de tabela ou coluna inválido", tabela=tabela, coluna=coluna)
        with self._trava:
            if self._profundidade or self._conexao.in_transaction:
                raise ErroDeUso("garantir_esquema não roda dentro de uma transação")
            with closing(self._conexao.cursor()) as cur:
                cur.executescript(ddl)
            # Dois processos podem abrir o mesmo banco antigo ao mesmo tempo: a
            # conferência e o ALTER vão juntos, senão os dois tentam acrescentar.
            with self.transacao() as cur:
                for tabela, coluna, tipo in colunas:
                    existentes = {c["name"] for c in cur.execute(f"PRAGMA table_info({tabela})")}
                    if coluna not in existentes:
                        cur.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")

    @contextmanager
    def transacao(self) -> Iterator[sqlite3.Cursor]:
        """Uma sequência de leitura e escrita que nenhum outro processo intercala.

        Abre com `BEGIN IMMEDIATE`: a trava de escrita do arquivo é tomada já no
        início, então quem confere o orçamento e depois grava a compra não vê o
        saldo mudar no meio. Outro processo que tente o mesmo espera a vez
        (até o `timeout` da conexão). Sai com `COMMIT`; com exceção, `ROLLBACK`.

        Aninhada, vira `SAVEPOINT`: o bloco de dentro desfaz só o que ele fez se
        falhar, e o de fora decide o resto.
        """
        with self._trava, closing(self._conexao.cursor()) as cur:
            nivel = self._profundidade
            ponto = f"nivel_{nivel}"
            cur.execute("BEGIN IMMEDIATE" if nivel == 0 else f"SAVEPOINT {ponto}")
            self._profundidade += 1
            try:
                yield cur
            except BaseException:
                if self._conexao.in_transaction:
                    if nivel == 0:
                        cur.execute("ROLLBACK")
                    else:
                        cur.execute(f"ROLLBACK TO {ponto}")
                        cur.execute(f"RELEASE {ponto}")
                raise
            else:
                cur.execute("COMMIT" if nivel == 0 else f"RELEASE {ponto}")
            finally:
                self._profundidade -= 1

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        """Um cursor sob a trava da conexão, fora de transação: para ler, ou gravar uma linha só.

        Para os módulos que guardam as próprias tabelas no dossiê. Conferir e
        depois gravar é `transacao()`.
        """
        with self._trava, closing(self._conexao.cursor()) as cur:
            yield cur

    def agora(self) -> datetime:
        """O agora do relógio do dossiê. Em teste, o relógio é falso e o tempo anda à mão."""
        return self._relogio()

    def _agora(self) -> str:
        return self.agora().isoformat()

    # -- perfil ----------------------------------------------------------- #

    def salvar_perfil(self, perfil: PerfilCozinha) -> None:
        """Grava o perfil inteiro. Só há um, e ele é sobrescrito."""
        with self._trava, closing(self._conexao.cursor()) as cur:
            cur.execute(
                "INSERT INTO perfil (id, dados, atualizado) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET dados=excluded.dados, "
                "atualizado=excluded.atualizado",
                (json.dumps(perfil.para_dict(), ensure_ascii=False), self._agora()),
            )

    def carregar_perfil(self) -> PerfilCozinha:
        """Devolve o perfil salvo, ou um novo se ainda não houver."""
        with self._trava, closing(self._conexao.cursor()) as cur:
            linha = cur.execute("SELECT dados FROM perfil WHERE id = 1").fetchone()
        if linha is None:
            return PerfilCozinha.inicial()
        return PerfilCozinha.de_dict(json.loads(linha["dados"]))

    # -- decisões (append-only) -------------------------------------------- #

    def registrar_decisao(
        self,
        prato: str,
        decisao: Decisao,
        motivo: str = "",
        detalhes: dict[str, Any] | None = None,
        chave: str | None = None,
        *,
        canal: Canal | str = Canal.CONVERSA,
        desfaz: int | None = None,
    ) -> RegistroDecisao:
        """Registra uma decisão. Repetir a que já vale não duplica a trilha.

        O que identifica uma decisão é o que ela decidiu e por quanto: a
        decisão e o `preco` dos `detalhes`. Sem `chave`, só é repetição o que
        for igual ao ÚLTIMO evento do prato: o retry de rede, o agente chamando
        duas vezes. O resto é um evento novo, com chave única. Aceitar a R$ X,
        recusar e aceitar a R$ X de novo são três linhas, e o prato volta ao
        cardápio. Antes, a chave era `prato:decisao:preco`; o terceiro evento
        batia na chave do primeiro, sumia em silêncio e o prato ficava fora.

        Com `chave` (a de idempotência de quem chamou), a chave é a identidade:
        a mesma chave devolve o registro que ela criou, mesmo que outras
        decisões tenham vindo depois, e chave nova é evento novo. A mesma chave
        para outra decisão é erro de quem chamou, não repetição.

        `desfaz` aponta a decisão, do mesmo prato, que esta desfaz.
        """
        de_onde = _canal(canal)
        preco = (detalhes or {}).get("preco")
        payload = json.dumps(detalhes or {}, ensure_ascii=False, default=str)

        with self.transacao() as cur:
            if chave is not None:
                existente = cur.execute(
                    "SELECT * FROM decisoes WHERE chave = ?", (chave,)
                ).fetchone()
                if existente is not None:
                    if not _mesma_decisao(existente, prato, decisao, preco):
                        raise ErroDeUso("essa chave já registrou outra decisão", chave=chave)
                    return _para_registro(existente)
            else:
                ultimo = cur.execute(
                    "SELECT * FROM decisoes WHERE prato = ? ORDER BY id DESC LIMIT 1", (prato,)
                ).fetchone()
                if ultimo is not None and _mesma_decisao(ultimo, prato, decisao, preco):
                    return _para_registro(ultimo)
                chave = f"decisao:{uuid.uuid4().hex}"
            if desfaz is not None:
                alvo = cur.execute("SELECT prato FROM decisoes WHERE id = ?", (desfaz,)).fetchone()
                if alvo is None or alvo["prato"] != prato:
                    raise ErroDeUso(
                        "a decisão a desfazer não existe para este prato",
                        desfaz=desfaz,
                        prato=prato,
                    )
            cur.execute(
                "INSERT INTO decisoes (chave, prato, decisao, motivo, detalhes, registrado, "
                "canal, desfaz) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    chave,
                    prato,
                    decisao.value,
                    motivo,
                    payload,
                    self._agora(),
                    de_onde.value,
                    desfaz,
                ),
            )
            linha = cur.execute("SELECT * FROM decisoes WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _para_registro(linha)

    def historico(self, prato: str | None = None) -> tuple[RegistroDecisao, ...]:
        """Todas as decisões, da mais antiga para a mais recente."""
        sql = "SELECT * FROM decisoes"
        params: tuple[str, ...] = ()
        if prato is not None:
            sql += " WHERE prato = ?"
            params = (prato,)
        sql += " ORDER BY id"
        with self._trava, closing(self._conexao.cursor()) as cur:
            return tuple(_para_registro(linha) for linha in cur.execute(sql, params))

    def decisao_atual(self, prato: str) -> Decisao | None:
        """A última decisão sobre o prato: a que vale hoje."""
        registros = self.historico(prato)
        return registros[-1].decisao if registros else None

    @property
    def cardapio(self) -> tuple[str, ...]:
        """Pratos cuja decisão mais recente é `aceito`."""
        pratos = {r.prato for r in self.historico()}
        return tuple(sorted(p for p in pratos if self.decisao_atual(p) is Decisao.ACEITO))

    # -- receitas em avaliação --------------------------------------------- #

    def guardar_candidata(self, receita: Receita) -> None:
        """Guarda a receita avaliada, para o próximo turno ainda saber qual é.

        Cada turno do Hermes sobe um processo novo do servidor MCP. Em memória,
        o prato avaliado num turno não existia no seguinte, e nenhuma ferramenta
        podia conferir contra o portão o prato que ela estava aceitando.
        """
        from mise.catalogo import id_da_receita  # noqa: PLC0415

        with self._trava, closing(self._conexao.cursor()) as cur:
            cur.execute(
                "INSERT INTO candidatas (nome, dados, registrado, receita_id) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(nome) DO UPDATE SET dados = excluded.dados, "
                "registrado = excluded.registrado, receita_id = excluded.receita_id",
                (
                    receita.nome,
                    json.dumps(receita.para_dict(), ensure_ascii=False),
                    self._agora(),
                    id_da_receita(receita),
                ),
            )

    def candidatas(self) -> dict[str, Receita]:
        with self._trava, closing(self._conexao.cursor()) as cur:
            linhas = cur.execute("SELECT dados FROM candidatas ORDER BY registrado").fetchall()
        receitas = (Receita.de_dict(json.loads(linha["dados"])) for linha in linhas)
        return {r.nome: r for r in receitas}

    def candidata(self, nome: str) -> Receita | None:
        """A receita pelo nome, sem ligar para caixa e espaço."""
        alvo = " ".join(nome.casefold().split())
        for chave, receita in self.candidatas().items():
            if " ".join(chave.casefold().split()) == alvo:
                return receita
        return None

    # -- orçamento --------------------------------------------------------- #

    def registrar_gasto(
        self,
        descricao: str,
        valor: Dinheiro,
        chave: str | None = None,
        *,
        canal: Canal | str = Canal.CONVERSA,
    ) -> EstadoOrcamento:
        """Compromete parte do orçamento. Idempotente por `chave`.

        Recusa se estourar o limite: o orçamento é dela, não uma sugestão. A
        conferência do saldo e a gravação vão na mesma transação: a tela e a
        conversa gravam no mesmo arquivo, de processos diferentes.
        """
        if valor.valor < 0:
            raise ErroDeUso("gasto não pode ser negativo", valor=str(valor))
        chave = chave or f"{descricao}:{valor.centavos}"
        de_onde = _canal(canal)

        with self.transacao() as cur:
            ja_existe = cur.execute("SELECT 1 FROM gastos WHERE chave = ?", (chave,)).fetchone()
            if not ja_existe:
                self._inserir_gasto(cur, chave, descricao, valor, canal=de_onde)
        return self.orcamento()

    def _inserir_gasto(
        self,
        cur: sqlite3.Cursor,
        chave: str,
        descricao: str,
        valor: Dinheiro,
        *,
        canal: Canal,
        compra: tuple[str, Decimal, str] | None = None,
        item_id: str | None = None,
    ) -> int:
        """Confere o saldo e grava o gasto. Só dentro de `transacao()`. Devolve o id.

        `compra` é (ingrediente, quantidade, unidade) quando o motor sabe o que
        foi comprado: vai na mesma linha, no mesmo comando, e ninguém lê uma
        compra sem o ingrediente. `item_id` é o item da despensa que a compra
        acrescentou.
        """
        estado = self.orcamento()
        if not estado.cabe(valor):
            raise OrcamentoExcedido(float(valor.valor), float(estado.restante.valor))
        ingrediente, quantidade, unidade = compra if compra else (None, None, "")
        cur.execute(
            "INSERT INTO gastos (chave, descricao, centavos, registrado, ingrediente, "
            "quantidade, unidade, canal, item_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                chave,
                descricao,
                valor.centavos,
                self._agora(),
                ingrediente,
                str(quantidade) if quantidade is not None else None,
                unidade,
                canal.value,
                item_id,
            ),
        )
        return int(cur.lastrowid or 0)

    # -- o que ela acha dos pratos ----------------------------------------- #

    def registrar_gosto(self, prato: str, gosto: Gosto, impedimento: str = "") -> OpiniaoSobrePrato:
        """Guarda se ela gosta de fazer um prato, e o que ela vê de empecilho.

        Substitui a opinião anterior: ela pode mudar de ideia depois de pensar,
        e é a de agora que vale. O histórico do que ela **decidiu** sobre o prato
        continua em `decisoes`, que é append-only. São coisas diferentes, e
        misturá-las apagaria a trilha.
        """
        nome = prato.strip()
        if not nome:
            raise ErroDeUso("prato sem nome")
        # O mesmo prato escrito de outro jeito ("arroz com FRANGO") é a mesma
        # opinião: grava na linha que já existe, e o gosto continua um só.
        existente = self.gosto_por(nome)
        if existente is not None:
            nome = existente.prato

        quando = self._agora()
        with self._trava, closing(self._conexao.cursor()) as cur:
            cur.execute(
                "INSERT INTO gostos (prato, gosto, impedimento, registrado) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(prato) DO UPDATE SET "
                "gosto = excluded.gosto, impedimento = excluded.impedimento, "
                "registrado = excluded.registrado",
                (nome, gosto.value, impedimento.strip(), quando),
            )
        return OpiniaoSobrePrato(nome, gosto, impedimento.strip(), datetime.fromisoformat(quando))

    def gosto_por(self, prato: str) -> OpiniaoSobrePrato | None:
        """A opinião dela sobre o prato, sem ligar para caixa, acento e espaço.

        O agente registra "strogonoff de frango"; a receita se chama "Strogonoff
        de Frango". Exigir a grafia exata fazia o portão perguntar de novo algo
        que ela já tinha respondido.
        """
        alvo = _chave_de_prato(prato)
        return next((o for o in self.gostos() if _chave_de_prato(o.prato) == alvo), None)

    def gostos(self) -> tuple[OpiniaoSobrePrato, ...]:
        with self._trava, closing(self._conexao.cursor()) as cur:
            linhas = cur.execute("SELECT * FROM gostos ORDER BY prato").fetchall()
        return tuple(_para_opiniao(linha) for linha in linhas)

    # -- preços do que falta comprar --------------------------------------- #

    def registrar_preco(
        self,
        ingrediente: str,
        valor: Dinheiro,
        origem: OrigemPreco,
        quantidade: Decimal | None = None,
        unidade: str = "",
    ) -> PrecoMercado:
        """Guarda quanto custa comprar um ingrediente ausente.

        Substitui a cotação anterior em vez de acumular: preço é fato corrente,
        e a de ontem só atrapalharia. O que é append-only é a decisão dela sobre
        o prato, não a cotação do feijão.

        Sem isto, `ItemFaltante.custo_estimado` nunca sai de `None` e o sistema
        pergunta o preço sem ter como receber a resposta, que era exatamente o
        buraco entre perguntar "quanto custa?" e responder "cabe no orçamento?".
        """
        nome = ingrediente.strip()
        if not nome:
            raise ErroDeUso("ingrediente sem nome")
        if valor.valor < 0:
            raise ErroDeUso("preço não pode ser negativo", valor=str(valor))
        _exigir_medida(nome, quantidade, unidade)

        quando = self._agora()
        with self._trava, closing(self._conexao.cursor()) as cur:
            cur.execute(
                "INSERT INTO precos_mercado "
                "(ingrediente, centavos, origem, registrado, quantidade, unidade) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(ingrediente) DO UPDATE SET "
                "centavos = excluded.centavos, origem = excluded.origem, "
                "registrado = excluded.registrado, quantidade = excluded.quantidade, "
                "unidade = excluded.unidade",
                (
                    nome,
                    valor.centavos,
                    origem.value,
                    quando,
                    str(quantidade) if quantidade is not None else None,
                    unidade.strip(),
                ),
            )
        return PrecoMercado(
            nome, valor, origem, datetime.fromisoformat(quando), quantidade, unidade.strip()
        )

    def preco_de(self, ingrediente: str) -> PrecoMercado | None:
        with self._trava, closing(self._conexao.cursor()) as cur:
            linha = cur.execute(
                "SELECT * FROM precos_mercado WHERE ingrediente = ?", (ingrediente.strip(),)
            ).fetchone()
        return _para_preco(linha) if linha else None

    def precos(self) -> tuple[PrecoMercado, ...]:
        with self._trava, closing(self._conexao.cursor()) as cur:
            linhas = cur.execute("SELECT * FROM precos_mercado ORDER BY ingrediente").fetchall()
        return tuple(_para_preco(linha) for linha in linhas)

    def precos_conhecidos(self) -> dict[str, Cotacao]:
        """O mapa que a checagem de viabilidade consome.

        Devolve `dict` simples de propósito: `viabilidade` não conhece o dossiê,
        e não deve conhecer. Ele recebe os preços, não vai buscá-los.
        """
        return {p.ingrediente: p.cotacao for p in self.precos()}

    def orcamento(self) -> EstadoOrcamento:
        with self._trava, closing(self._conexao.cursor()) as cur:
            linha = cur.execute("SELECT COALESCE(SUM(centavos), 0) AS t FROM gastos").fetchone()
        return EstadoOrcamento(
            inicial=self.orcamento_inicial,
            gasto=Dinheiro(Decimal(linha["t"]) / 100),
        )

    def registrar_compra(
        self,
        ingrediente: str,
        quantidade: Decimal,
        unidade: str,
        valor: Dinheiro,
        descricao: str = "",
        *,
        chave: str | None = None,
        canal: Canal | str = Canal.CONVERSA,
    ) -> EstadoOrcamento:
        """Uma compra de ingrediente: sai do orçamento e vira estoque do cardápio.

        Diferente de `registrar_gasto`, que só sabe o valor: aqui o motor sabe o
        que foi comprado, e o ingrediente deixa de faltar. É isso que impede o
        mesmo dinheiro de ser descontado de novo na próxima avaliação.

        Saldo conferido, valor e ingrediente gravados numa transação só. Antes o
        gasto entrava sem o ingrediente e um segundo comando o completava.

        Repetição: com `chave` (a de idempotência de quem chamou), a mesma chave
        é a mesma compra, e chave nova é compra nova. Sem chave, a mesma compra
        (ingrediente, quantidade, unidade e valor) dentro de
        `JANELA_DE_COMPRA_REPETIDA` é repetição. A chave era derivada do
        conteúdo, e a segunda lata de milho de verdade, comprada no dia
        seguinte, era descartada para sempre.
        """
        nome = ingrediente.strip()
        if not nome:
            raise ErroDeUso("ingrediente sem nome")
        _exigir_medida(nome, quantidade, unidade)
        if valor.valor < 0:
            raise ErroDeUso("gasto não pode ser negativo", valor=str(valor))
        texto = descricao.strip() or f"{nome}: {quantidade} {unidade}".strip()
        de_onde = _canal(canal)
        compra = (nome, quantidade, unidade.strip())
        with self.transacao() as cur:
            if chave is not None:
                existente = cur.execute("SELECT * FROM gastos WHERE chave = ?", (chave,)).fetchone()
                if existente is not None:
                    if not _mesma_compra(existente, compra, valor):
                        raise ErroDeUso("essa chave já registrou outra compra", chave=chave)
                    return self.orcamento()
            elif self._compra_recente(cur, compra, valor):
                return self.orcamento()
            chave = chave or f"compra:{uuid.uuid4().hex}"
            self._inserir_gasto(cur, chave, texto, valor, canal=de_onde, compra=compra)
        return self.orcamento()

    def _compra_recente(
        self, cur: sqlite3.Cursor, compra: tuple[str, Decimal, str], valor: Dinheiro
    ) -> bool:
        """A mesma compra já foi registrada dentro da janela de repetição?"""
        desde = self.agora() - JANELA_DE_COMPRA_REPETIDA
        linhas = cur.execute(
            "SELECT * FROM gastos WHERE ingrediente IS NOT NULL AND centavos = ? ORDER BY id DESC",
            (valor.centavos,),
        )
        return any(
            _mesma_compra(linha, compra, valor)
            and datetime.fromisoformat(linha["registrado"]) >= desde
            for linha in linhas
        )

    def tem_gasto(self, chave: str) -> bool:
        """Já há um gasto (ou compra) gravado com esta chave?"""
        with self._trava, closing(self._conexao.cursor()) as cur:
            return (
                cur.execute("SELECT 1 FROM gastos WHERE chave = ?", (chave,)).fetchone() is not None
            )

    def compras(self) -> dict[str, Comprado]:
        """O que ela comprou, somado por ingrediente, como a viabilidade consome.

        Compras do mesmo ingrediente em medidas que não se somam (1 kg e 1 lata)
        ficam com a primeira; a segunda continua no orçamento, que é o que conta
        dinheiro, mas não vira estoque que o motor não sabe medir.

        Compra devolvida (estornada) e a própria devolução não contam: o que foi
        devolvido não está mais na cozinha dela.
        """
        resultado: dict[str, Comprado] = {}
        with self._trava, closing(self._conexao.cursor()) as cur:
            linhas = cur.execute(
                "SELECT * FROM gastos WHERE ingrediente IS NOT NULL AND estorna IS NULL "
                "AND id NOT IN (SELECT estorna FROM gastos WHERE estorna IS NOT NULL) "
                "ORDER BY id"
            ).fetchall()
        for linha in linhas:
            m = medida(Decimal(linha["quantidade"]), linha["unidade"], linha["ingrediente"])
            if m is None:
                continue
            valor = Dinheiro(Decimal(linha["centavos"]) / 100)
            anterior = resultado.get(linha["ingrediente"])
            if anterior is None:
                resultado[linha["ingrediente"]] = Comprado(m, valor)
            elif anterior.medida.compativel(m):
                soma = Medida(anterior.medida.quantidade + m.quantidade, m.embalagem)
                resultado[linha["ingrediente"]] = Comprado(soma, anterior.valor + valor)
        return resultado

    def gastos(self) -> Iterator[tuple[str, Dinheiro, datetime]]:
        with self._trava, closing(self._conexao.cursor()) as cur:
            for linha in cur.execute("SELECT * FROM gastos ORDER BY id"):
                yield (
                    linha["descricao"],
                    Dinheiro(Decimal(linha["centavos"]) / 100),
                    datetime.fromisoformat(linha["registrado"]),
                )

    def extrato(self) -> tuple[LinhaDoExtrato, ...]:
        """Todas as linhas dos R$ 80,00, da mais antiga para a mais nova, com as devoluções."""
        with self._trava, closing(self._conexao.cursor()) as cur:
            linhas = cur.execute("SELECT * FROM gastos ORDER BY id").fetchall()
        devolvidas = {linha["estorna"] for linha in linhas if linha["estorna"] is not None}
        return tuple(_para_extrato(linha, linha["id"] in devolvidas) for linha in linhas)

    def compra(self, compra_id: int) -> LinhaDoExtrato | None:
        """Uma linha dos R$ 80,00 pelo id, ou `None`."""
        return next((linha for linha in self.extrato() if linha.id == compra_id), None)

    def compras_do_item(self, item_id: str) -> tuple[LinhaDoExtrato, ...]:
        """As compras que acrescentaram este item da despensa e ainda contam."""
        return tuple(linha for linha in self.extrato() if linha.item_id == item_id and linha.ativa)

    def debitar_item(
        self,
        item_id: str,
        descricao: str,
        valor: Dinheiro,
        chave: str,
        *,
        canal: Canal | str = Canal.TELA,
    ) -> LinhaDoExtrato:
        """A compra de um item da despensa com os complementos: sai dos R$ 80,00 agora.

        É o "comprei com os R$ 80" da tela: a escolha é dela, e não passa pelo
        portão de prato (a compra que o agente sugere, `registrar_compra`, passa).
        Recusa se não couber. A mesma `chave` não debita duas vezes.
        """
        if valor.valor <= 0:
            raise ErroDeUso("a compra precisa de um valor maior que zero", valor=str(valor))
        de_onde = _canal(canal)
        with self.transacao() as cur:
            existente = cur.execute("SELECT id FROM gastos WHERE chave = ?", (chave,)).fetchone()
            compra_id = (
                int(existente["id"])
                if existente is not None
                else self._inserir_gasto(
                    cur, chave, descricao, valor, canal=de_onde, item_id=item_id
                )
            )
        linha = self.compra(compra_id)
        assert linha is not None
        return linha

    def estornar(self, compra_id: int, *, canal: Canal | str = Canal.TELA) -> LinhaDoExtrato:
        """Devolve uma compra aos R$ 80,00: grava a devolução e devolve a linha dela.

        A devolução é uma linha nova, com os centavos negativos e `estorna`
        apontando a original; nada é apagado. Devolver de novo a mesma compra
        não devolve duas vezes: devolve a linha que já existe. Devolução não se
        devolve.
        """
        de_onde = _canal(canal)
        chave = f"estorno:{compra_id}"
        with self.transacao() as cur:
            original = cur.execute("SELECT * FROM gastos WHERE id = ?", (compra_id,)).fetchone()
            if original is None:
                raise Ausente("não encontrei essa compra", compra=compra_id)
            if original["estorna"] is not None:
                raise ErroDeUso("isso já é uma devolução; não dá para devolver", compra=compra_id)
            if original["centavos"] <= 0:
                raise ErroDeUso("essa linha não tirou dinheiro dos complementos", compra=compra_id)
            existente = cur.execute("SELECT id FROM gastos WHERE chave = ?", (chave,)).fetchone()
            if existente is None:
                cur.execute(
                    "INSERT INTO gastos (chave, descricao, centavos, registrado, unidade, canal, "
                    "estorna, item_id) VALUES (?, ?, ?, ?, '', ?, ?, ?)",
                    (
                        chave,
                        f"Devolução: {original['descricao']}",
                        -int(original["centavos"]),
                        self._agora(),
                        de_onde.value,
                        compra_id,
                        original["item_id"],
                    ),
                )
                estorno_id = int(cur.lastrowid or 0)
            else:
                estorno_id = int(existente["id"])
        linha = self.compra(estorno_id)
        assert linha is not None
        return linha

    # -- panorama ---------------------------------------------------------- #

    def resumo(self) -> str:
        perfil = self.carregar_perfil()
        pratos = len(self.cardapio)
        no_cardapio = "1 prato no cardápio" if pratos == 1 else f"{pratos} pratos no cardápio"
        return f"{perfil.resumo()} · {no_cardapio} · orçamento: {self.orcamento()}"


def _para_registro(linha: sqlite3.Row) -> RegistroDecisao:
    return RegistroDecisao(
        prato=linha["prato"],
        decisao=Decisao(linha["decisao"]),
        motivo=linha["motivo"],
        detalhes=json.loads(linha["detalhes"]),
        registrado=datetime.fromisoformat(linha["registrado"]),
        id=linha["id"],
        canal=linha["canal"],
        desfaz=linha["desfaz"],
    )


def _para_extrato(linha: sqlite3.Row, estornada: bool) -> LinhaDoExtrato:
    return LinhaDoExtrato(
        id=int(linha["id"]),
        descricao=linha["descricao"],
        valor=Dinheiro(Decimal(linha["centavos"]) / 100),
        registrado=datetime.fromisoformat(linha["registrado"]),
        canal=linha["canal"],
        ingrediente=linha["ingrediente"],
        item_id=linha["item_id"],
        estorna=linha["estorna"],
        estornada=estornada,
    )


def _mesma_compra(linha: sqlite3.Row, compra: tuple[str, Decimal, str], valor: Dinheiro) -> bool:
    """O mesmo ingrediente, na mesma quantidade e unidade, pelo mesmo valor."""
    nome, quantidade, unidade = compra
    return (
        linha["ingrediente"] is not None
        and linha["ingrediente"].casefold() == nome.casefold()
        and Decimal(linha["quantidade"]) == quantidade
        and linha["unidade"] == unidade
        and linha["centavos"] == valor.centavos
    )


def _mesma_decisao(linha: sqlite3.Row, prato: str, decisao: Decisao, preco: object) -> bool:
    """A mesma decisão, sobre o mesmo prato e pelo mesmo preço (ou sem preço, as duas)."""
    gravada: dict[str, Any] = json.loads(linha["detalhes"])
    return bool(
        linha["prato"] == prato
        and linha["decisao"] == decisao.value
        and gravada.get("preco") == preco
    )


def _agora_utc() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "COLUNAS_NOVAS",
    "ESQUEMA",
    "JANELA_DE_COMPRA_REPETIDA",
    "ORCAMENTO_INICIAL",
    "Canal",
    "ColunaNova",
    "Decisao",
    "Dossie",
    "EstadoOrcamento",
    "LinhaDoExtrato",
    "RegistroDecisao",
    "Relogio",
]
