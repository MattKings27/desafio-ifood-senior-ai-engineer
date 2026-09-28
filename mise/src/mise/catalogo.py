"""O catálogo de receitas: as que a plataforma encontrou, leu e guardou, com a fonte.

Só código do servidor escreve aqui: a descoberta automática, a busca do
agente (`buscar_receita_na_web`), a receita que ela traz pela URL e a que
ela dita. O modelo nunca escreve no catálogo e se refere a uma receita pelo
`receita_id`, que é o `slug` daqui.

**Receita da internet só entra pela página que o servidor leu.** A linha tem a
URL canônica (única), a receita estruturada que o extrator tirou do JSON-LD ou
do microdata, a foto, o autor, o site, os três tempos que a página declara e o
hash do conteúdo, para saber se a página mudou. A receita que ela dita entra
com origem `dita`, sem URL nem foto.

**O nome é a ponte com o resto do dossiê.** Decisão, cardápio, gosto e compra
se referem ao prato pelo nome, e a receita se refere a si pelo `receita_id`.
Cada linha do catálogo tem um nome único (sem ligar para caixa e acento): a
receita da internet que chega com o nome de outra ganha o site entre
parênteses ("Bolo de fubá (Panelinha)"), e a que ela dita com o nome de uma
receita da internet é recusada com o `receita_id` da outra, para quem chamou
dizer se é a mesma receita ou dar outro nome. Assim um nome nunca aponta para
duas receitas, e o gosto dela por uma não passa para a outra.

**O que ela responde sobre a receita fica junto dela.** O rendimento que o site
não dizia, o modo de preparo que faltava e quanto vai de uma linha que a
leitura não entendeu entram na receita guardada, e cada resposta fica anotada
em `respostas`, com a data: o que veio da página e o que ela disse continuam
distinguíveis.

A regra do id e a da foto moram aqui e valem no sistema inteiro: a tela, a API
e as ferramentas usam as mesmas.

**A leitura das linhas melhora, e a receita guardada acompanha.** Cada linha
guarda o texto como a página escreveu (`texto_original`). Quando as regras de
leitura mudam (`retrieval.quantidades.VERSAO_DA_LEITURA`), o servidor lê de
novo, na abertura, as linhas das receitas lidas com regras mais antigas
(`reler_as_linhas`), sem buscar a página: a linha que ela respondeu fica como
ela disse.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlsplit

from mise.erros import ErroDeUso
from mise.receita import Origem, Receita

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable, Iterable, Set
    from pathlib import Path

    from mise.dossie import Dossie
    from mise.receita import IngredienteReceita

#: Quantos caracteres hexadecimais tem o id de uma receita da internet.
TAMANHO_DO_ID: Final = 16

#: Quantos caracteres hexadecimais tem a chave de uma foto (`/motor/imagens/<chave>`).
TAMANHO_DA_CHAVE_DA_IMAGEM: Final = 32

#: Por onde a tela carrega uma foto: o proxy da API, nunca outro endereço.
PREFIXO_DA_IMAGEM: Final = "/motor/imagens/"

#: Quantas vezes o mesmo nome pode voltar do mesmo site antes de desistir de numerar.
_TENTATIVAS_DE_NOME: Final = 50

ESQUEMA_DO_CATALOGO: Final = """
CREATE TABLE IF NOT EXISTS catalogo (
    slug              TEXT PRIMARY KEY,
    nome              TEXT NOT NULL,
    chave_do_nome     TEXT NOT NULL UNIQUE,
    nome_original     TEXT NOT NULL,
    url_canonica      TEXT UNIQUE,
    url               TEXT,
    receita           TEXT NOT NULL,
    imagem_url        TEXT,
    credito_da_imagem TEXT,
    autor             TEXT,
    site              TEXT,
    preparo_min       INTEGER,
    cozimento_min     INTEGER,
    total_min         INTEGER,
    rendimento_texto  TEXT,
    origem            TEXT NOT NULL,
    hash_do_conteudo  TEXT NOT NULL DEFAULT '',
    respostas         TEXT NOT NULL DEFAULT '[]',
    criada_em         TEXT NOT NULL,
    atualizada_em     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_catalogo_criada ON catalogo(criada_em);
"""

#: Colunas que chegaram depois: `receita_lida` é a receita como a página veio, antes
#: do que ela respondeu, para "Restaurar os dados" voltar a ela sem ler a página de novo;
#: `versao_da_leitura` é a das regras que leram as linhas (vazia: de antes dela).
COLUNAS_DO_CATALOGO: Final = (
    ("catalogo", "receita_lida", "TEXT"),
    ("catalogo", "versao_da_leitura", "INTEGER"),
)

#: Num catálogo antigo, a receita que ela ainda não completou é a própria página.
_COPIAR_A_PAGINA: Final = (
    "UPDATE catalogo SET receita_lida = receita WHERE receita_lida IS NULL AND respostas = '[]' "
    "AND origem != 'dita'"
)


class OrigemNoCatalogo(StrEnum):
    """Como a receita entrou no catálogo."""

    DESCOBERTA = "descoberta"
    """A descoberta automática achou, a partir da despensa dela."""
    URL_DELA = "url_dela"
    """Ela trouxe pelo endereço, na tela de receitas."""
    CONVERSA = "conversa"
    """O agente buscou durante a conversa."""
    DITA = "dita"
    """Ela ditou a receita: não há página nem foto."""


# --------------------------------------------------------------------------- #
# Ids, nomes e imagens: as mesmas regras em todo o sistema
# --------------------------------------------------------------------------- #


def url_canonica(url: str) -> str:
    """O endereço sem o que não muda a página: host minúsculo sem `www.`, caminho sem barra final.

    Sem esquema, consulta nem fragmento: `https://www.TudoGostoso.com.br/r/1/?utm=x#topo`
    e `http://tudogostoso.com.br/r/1` são a mesma receita.
    """
    partes = urlsplit(url.strip())
    host = (partes.hostname or "").lower().removeprefix("www.")
    return f"{host}{partes.path.rstrip('/')}"


def id_da_url(url: str) -> str:
    """O `receita_id` de uma receita da internet: 16 hex do sha256 do endereço canônico."""
    return hashlib.sha256(url_canonica(url).encode()).hexdigest()[:TAMANHO_DO_ID]


def id_da_receita(receita: Receita) -> str:
    """O `receita_id`: o da URL quando a receita veio da internet, senão o slug do nome."""
    from mise.despensa import id_do_item  # noqa: PLC0415

    if receita.url and receita.url.strip():
        return id_da_url(receita.url)
    return id_do_item(receita.nome)


def chave_do_nome(nome: str) -> str:
    """O nome para comparar: sem acento, sem caixa e com os espaços normalizados.

    "Bolo de Fubá" e "bolo de fuba" são o mesmo prato para o dossiê: é a mesma
    regra que o gosto dela usa para achar o prato (`Dossie.gosto_por`).
    """
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.casefold().split())


def chave_da_imagem(url: str) -> str:
    """A chave de uma foto: 32 hex do sha256 do endereço original, como ele veio."""
    return hashlib.sha256(url.strip().encode()).hexdigest()[:TAMANHO_DA_CHAVE_DA_IMAGEM]


def rota_da_imagem(url: str) -> str:
    """Por onde a tela carrega a foto: `/motor/imagens/<chave>`."""
    return f"{PREFIXO_DA_IMAGEM}{chave_da_imagem(url)}"


#: O que, no endereço de uma foto, diz que ela é a imagem genérica do site, e
#: não a da receita: o "sem foto" que o site põe no lugar (o chapéu de
#: cozinheiro cinza do TudoGostoso mora em `.../placeholder-img-default-tdg.png`).
#: Olha só o caminho do endereço, em minúsculas.
MARCAS_DE_FOTO_GENERICA: Final[tuple[str, ...]] = (
    "placeholder",
    "no-image",
    "no_image",
    "noimage",
    "no-photo",
    "nophoto",
    "sem-foto",
    "sem_foto",
    "semfoto",
    "sem-imagem",
    "default-image",
    "image-default",
    "img-default",
    "imagem-padrao",
    "missing-image",
    "fallback-image",
)


#: Quadro tirado de um vídeo (a apresentadora na cozinha, a abertura do programa)
#: não é foto do prato. Vale para o endereço inteiro, porque os sites que
#: redimensionam imagem carregam o endereço original dentro do caminho.
MARCAS_DE_QUADRO_DE_VIDEO: Final[tuple[str, ...]] = (
    "video.glbimg.com",
    "i.ytimg.com",
    "img.youtube.com",
    "vimeocdn.com",
    "/videos/",
    "/video/",
    "video-thumb",
    "video_thumb",
)


def foto_generica(url: str) -> bool:
    """O endereço é o da imagem genérica que o site mostra quando a receita não tem foto?

    Foto genérica fica de fora: a tela mostra o gradiente com o ícone, que diz
    a verdade (não há foto), em vez de uma imagem que não é do prato.
    """
    try:
        caminho = urlsplit(url.strip()).path.lower()
    except ValueError:
        return True
    if any(marca in url.lower() for marca in MARCAS_DE_QUADRO_DE_VIDEO):
        return True
    return any(marca in caminho for marca in MARCAS_DE_FOTO_GENERICA)


# --------------------------------------------------------------------------- #
# A forma de uma receita do catálogo
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class TemposDaReceita:
    """Os tempos que a página declara, em minutos; `None` quando ela não diz."""

    preparo_min: int | None = None
    cozimento_min: int | None = None
    total_min: int | None = None


@dataclass(frozen=True, slots=True)
class RespostaSobreAReceita:
    """Uma coisa que ela disse sobre a receita e que a página não dizia."""

    campo: str
    """`rendimento_porcoes`, `modo_preparo`, ou o texto da linha de ingrediente."""
    valor: str
    """O que ela disse, como ficou gravado na receita."""
    quando: datetime


@dataclass(frozen=True, slots=True)
class ReceitaDoCatalogo:
    """Uma receita guardada no catálogo, com a procedência.

    `receita` é a receita estruturada que o servidor leu da página (ou que ela
    ditou), já com o nome único do dossiê e com o que ela respondeu sobre ela;
    o resto é o que a tela mostra ao lado dela. Quanto ela tem de cada
    ingrediente e se a cozinha dela dá conta não moram aqui: saem da
    conferência, na leitura, para acompanhar a despensa e a cozinha de agora.
    """

    slug: str
    receita: Receita
    origem: OrigemNoCatalogo
    url_canonica: str | None = None
    site: str | None = None
    autor: str | None = None
    #: O endereço original da foto. A tela nunca o recebe: recebe `rota_da_imagem`.
    imagem_url: str | None = None
    credito_da_imagem: str | None = None
    tempos: TemposDaReceita = field(default_factory=TemposDaReceita)
    #: O sha256 do conteúdo lido, para saber se a página mudou.
    hash_do_conteudo: str = ""
    criada_em: datetime | None = None
    atualizada_em: datetime | None = None
    #: O nome como a página escreveu, antes de ganhar o site para não repetir outro.
    nome_original: str = ""
    #: O rendimento como a página escreveu ("4 porções", "500 g").
    rendimento_texto: str | None = None
    #: O que ela respondeu sobre a receita (rendimento, preparo, linhas), com a data.
    respostas: tuple[RespostaSobreAReceita, ...] = ()

    @property
    def nome(self) -> str:
        return self.receita.nome

    @property
    def url(self) -> str | None:
        return self.receita.url

    @property
    def da_internet(self) -> bool:
        """Veio de uma página que o servidor leu (e não da boca dela)."""
        return self.origem is not OrigemNoCatalogo.DITA

    @property
    def rota_da_imagem(self) -> str | None:
        """`/motor/imagens/<chave>`, ou `None` quando não há foto (ou a que há é a genérica)."""
        if not self.imagem_url or foto_generica(self.imagem_url):
            return None
        return rota_da_imagem(self.imagem_url)


@dataclass(frozen=True, slots=True)
class FotoDaReceita:
    """A foto que uma página lida declarou: o endereço original, o crédito e a página."""

    imagem_url: str
    credito: str | None
    pagina: str | None

    @property
    def chave(self) -> str:
        return chave_da_imagem(self.imagem_url)


@dataclass(frozen=True, slots=True)
class PaginaLida:
    """O que o servidor leu de uma página de receita, pronto para entrar no catálogo.

    É o extrato da `retrieval.extrator.ReceitaExtraida` que o catálogo guarda:
    o motor não importa o pacote da busca, recebe só os dados.
    """

    receita: Receita
    site: str = ""
    autor: str = ""
    imagem_url: str | None = None
    tempos: TemposDaReceita = field(default_factory=TemposDaReceita)
    rendimento_texto: str = ""
    hash_do_conteudo: str = ""
    #: A versão das regras que leram as linhas (`retrieval.quantidades.VERSAO_DA_LEITURA`);
    #: `None` quando quem leu não disse, e a próxima abertura do servidor lê de novo.
    versao_da_leitura: int | None = None


# --------------------------------------------------------------------------- #
# O catálogo sobre o dossiê
# --------------------------------------------------------------------------- #


class Catalogo:
    """A leitura e a escrita do catálogo, sobre o dossiê.

    A tabela nasce no primeiro uso, pelo mesmo mecanismo do dossiê
    (`Dossie.garantir_esquema`). Ler o catálogo vazio devolve nada, sem erro.
    """

    __slots__ = ("_dossie", "_pronto")

    def __init__(self, dossie: Dossie) -> None:
        self._dossie = dossie
        self._pronto = False

    def _garantir(self) -> None:
        if not self._pronto:
            garantir_o_catalogo(self._dossie)
            self._pronto = True

    # -- leitura ------------------------------------------------------------ #

    def listar(
        self,
        *,
        q: str | None = None,
        origem: OrigemNoCatalogo | None = None,
        limite: int | None = None,
    ) -> tuple[ReceitaDoCatalogo, ...]:
        """As receitas do catálogo, da mais nova para a mais antiga.

        `q` busca no nome, sem ligar para caixa e acento; `origem` fica só com as
        que entraram por ali; `limite` corta a lista.
        """
        self._garantir()
        sql = "SELECT * FROM catalogo"
        parametros: tuple[str, ...] = ()
        if origem is not None:
            sql += " WHERE origem = ?"
            parametros = (origem.value,)
        sql += " ORDER BY criada_em DESC, rowid DESC"
        with self._dossie.cursor() as cur:
            linhas = cur.execute(sql, parametros).fetchall()
        receitas = [_da_linha(linha) for linha in linhas]
        if q and q.strip():
            alvo = chave_do_nome(q)
            receitas = [r for r in receitas if alvo in chave_do_nome(r.nome)]
        return tuple(receitas[:limite] if limite is not None else receitas)

    def obter(self, slug: str) -> ReceitaDoCatalogo | None:
        """A receita pelo `slug` (o `receita_id` das ferramentas), ou `None`."""
        return self._uma("SELECT * FROM catalogo WHERE slug = ?", slug.strip().lower())

    def por_url(self, url: str) -> ReceitaDoCatalogo | None:
        """A receita de um endereço, pela URL canônica, ou `None` se ainda não foi lida."""
        return self._uma("SELECT * FROM catalogo WHERE url_canonica = ?", url_canonica(url))

    def por_nome(self, nome: str) -> ReceitaDoCatalogo | None:
        """A receita pelo nome do dossiê, sem ligar para caixa e acento: a ponte nome e id."""
        return self._uma("SELECT * FROM catalogo WHERE chave_do_nome = ?", chave_do_nome(nome))

    def contar(self, origem: OrigemNoCatalogo | None = None) -> int:
        """Quantas receitas o catálogo tem, ou quantas entraram por uma origem."""
        self._garantir()
        with self._dossie.cursor() as cur:
            if origem is None:
                linha = cur.execute("SELECT COUNT(*) AS n FROM catalogo").fetchone()
            else:
                linha = cur.execute(
                    "SELECT COUNT(*) AS n FROM catalogo WHERE origem = ?", (origem.value,)
                ).fetchone()
        return int(linha["n"])

    def _uma(self, sql: str, valor: str) -> ReceitaDoCatalogo | None:
        self._garantir()
        with self._dossie.cursor() as cur:
            linha = cur.execute(sql, (valor,)).fetchone()
        return _da_linha(linha) if linha is not None else None

    def fotos(self) -> tuple[FotoDaReceita, ...]:
        """As fotos que as páginas lidas declararam, com o crédito e a página de cada uma.

        É o registro que o proxy de imagens consulta: só se serve foto de endereço
        que o servidor tirou de uma página que ele mesmo leu.
        """
        self._garantir()
        with self._dossie.cursor() as cur:
            linhas = cur.execute(
                "SELECT imagem_url, credito_da_imagem, url FROM catalogo "
                "WHERE imagem_url IS NOT NULL AND imagem_url != ''"
            ).fetchall()
        return tuple(
            FotoDaReceita(linha["imagem_url"], linha["credito_da_imagem"], linha["url"])
            for linha in linhas
            if not foto_generica(linha["imagem_url"])
        )

    def esquecer_foto(self, imagem_url: str) -> int:
        """Tira a foto das receitas que a declararam: ela chegou e é a imagem genérica do site.

        Quem descobre é o proxy de imagens, ao baixar (`retrieval.imagens.
        parece_generica`). A receita fica sem foto, e a tela mostra o gradiente.
        Devolve quantas receitas perderam a foto.
        """
        self._garantir()
        with self._dossie.transacao() as cur:
            cursor = cur.execute(
                "UPDATE catalogo SET imagem_url = NULL, credito_da_imagem = NULL "
                "WHERE imagem_url = ?",
                (imagem_url,),
            )
            return int(cursor.rowcount)

    # -- escrita: só o servidor --------------------------------------------- #

    def guardar_da_web(
        self, pagina: PaginaLida, origem: OrigemNoCatalogo
    ) -> tuple[ReceitaDoCatalogo, bool]:
        """Guarda a receita de uma página que o servidor leu. Devolve a linha e se é nova.

        A mesma URL canônica é a mesma receita: a página lida de novo atualiza o
        conteúdo (e só se o hash mudou), mantém o nome, a origem e o que ela
        respondeu. Receita nova com o nome de outra ganha o site no nome.
        """
        receita = pagina.receita
        if receita.origem is not Origem.WEB or not receita.url:
            raise ErroDeUso("só entra como receita da internet a página que o servidor leu")
        if origem is OrigemNoCatalogo.DITA:
            raise ErroDeUso("receita da internet não entra como ditada por ela")
        self._garantir()
        canonica = url_canonica(receita.url)
        slug = id_da_url(receita.url)
        agora = self._dossie.agora().isoformat()
        with self._dossie.transacao() as cur:
            existente = cur.execute(
                "SELECT * FROM catalogo WHERE url_canonica = ?", (canonica,)
            ).fetchone()
            if existente is not None:
                if existente["hash_do_conteudo"] != pagina.hash_do_conteudo:
                    nome = existente["nome"]
                    cur.execute(
                        "UPDATE catalogo SET receita = ?, receita_lida = ?, imagem_url = ?, "
                        "credito_da_imagem = ?, autor = ?, site = ?, preparo_min = ?, "
                        "cozimento_min = ?, total_min = ?, rendimento_texto = ?, "
                        "hash_do_conteudo = ?, atualizada_em = ?, versao_da_leitura = ? "
                        "WHERE slug = ?",
                        (
                            _json(replace(receita, nome=nome)),
                            _json(replace(receita, nome=nome)),
                            _foto(pagina),
                            _credito(pagina),
                            pagina.autor or None,
                            pagina.site or None,
                            pagina.tempos.preparo_min,
                            pagina.tempos.cozimento_min,
                            pagina.tempos.total_min,
                            pagina.rendimento_texto or None,
                            pagina.hash_do_conteudo,
                            agora,
                            pagina.versao_da_leitura,
                            existente["slug"],
                        ),
                    )
                linha = cur.execute(
                    "SELECT * FROM catalogo WHERE slug = ?", (existente["slug"],)
                ).fetchone()
                return _da_linha(linha), False
            nome = self._nome_livre(cur, receita.nome, slug, pagina.site)
            cur.execute(
                "INSERT INTO catalogo (slug, nome, chave_do_nome, nome_original, url_canonica, "
                "url, receita, receita_lida, imagem_url, credito_da_imagem, autor, site, "
                "preparo_min, cozimento_min, total_min, rendimento_texto, origem, "
                "hash_do_conteudo, respostas, criada_em, atualizada_em, versao_da_leitura) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?)",
                (
                    slug,
                    nome,
                    chave_do_nome(nome),
                    receita.nome,
                    canonica,
                    receita.url,
                    _json(replace(receita, nome=nome)),
                    _json(replace(receita, nome=nome)),
                    _foto(pagina),
                    _credito(pagina),
                    pagina.autor or None,
                    pagina.site or None,
                    pagina.tempos.preparo_min,
                    pagina.tempos.cozimento_min,
                    pagina.tempos.total_min,
                    pagina.rendimento_texto or None,
                    origem.value,
                    pagina.hash_do_conteudo,
                    agora,
                    agora,
                    pagina.versao_da_leitura,
                ),
            )
            linha = cur.execute("SELECT * FROM catalogo WHERE slug = ?", (slug,)).fetchone()
        return _da_linha(linha), True

    def guardar_dita(self, receita: Receita) -> ReceitaDoCatalogo:
        """Guarda a receita que ela ditou. A mesma receita ditada de novo é a correção dela.

        O id é o slug do nome. Nome que já é de uma receita da internet é
        recusado com o `receita_id` dela: ou é a mesma receita (e quem chamou usa
        o id), ou é a receita dela com outro nome.
        """
        if receita.origem is Origem.WEB or (receita.url or "").strip():
            raise ErroDeUso("receita ditada por ela não tem endereço de página")
        self._garantir()
        slug = id_da_receita(receita)
        chave = chave_do_nome(receita.nome)
        agora = self._dossie.agora().isoformat()
        with self._dossie.transacao() as cur:
            dona_do_nome = cur.execute(
                "SELECT slug, nome, site FROM catalogo WHERE chave_do_nome = ?", (chave,)
            ).fetchone()
            if dona_do_nome is not None and dona_do_nome["slug"] != slug:
                de_onde = f", de {dona_do_nome['site']}" if dona_do_nome["site"] else ""
                raise ErroDeUso(
                    f"já existe a receita {dona_do_nome['nome']!r}{de_onde}, vinda da internet. "
                    "Se for a mesma, use o receita_id dela; se for a receita da senhora, "
                    "dê um nome que a diferencie",
                    receita_id=dona_do_nome["slug"],
                )
            self._conferir_nome_das_candidatas(receita.nome, slug)
            existente = cur.execute("SELECT slug FROM catalogo WHERE slug = ?", (slug,)).fetchone()
            if existente is None:
                cur.execute(
                    "INSERT INTO catalogo (slug, nome, chave_do_nome, nome_original, receita, "
                    "origem, respostas, criada_em, atualizada_em) "
                    "VALUES (?, ?, ?, ?, ?, ?, '[]', ?, ?)",
                    (
                        slug,
                        receita.nome,
                        chave,
                        receita.nome,
                        _json(receita),
                        OrigemNoCatalogo.DITA.value,
                        agora,
                        agora,
                    ),
                )
            else:
                cur.execute(
                    "UPDATE catalogo SET nome = ?, chave_do_nome = ?, receita = ?, "
                    "atualizada_em = ? WHERE slug = ?",
                    (receita.nome, chave, _json(receita), agora, slug),
                )
            linha = cur.execute("SELECT * FROM catalogo WHERE slug = ?", (slug,)).fetchone()
        return _da_linha(linha)

    def completar(
        self, slug: str, receita: Receita, respostas: Iterable[tuple[str, str]]
    ) -> ReceitaDoCatalogo:
        """Grava na receita o que ela respondeu (rendimento, preparo, linhas), com a data.

        Quem chama já conferiu que a receita nova só acrescenta o que a página
        não dizia; aqui a receita guardada é trocada e cada resposta é anotada.
        """
        self._garantir()
        agora = self._dossie.agora().isoformat()
        with self._dossie.transacao() as cur:
            linha = cur.execute("SELECT * FROM catalogo WHERE slug = ?", (slug,)).fetchone()
            if linha is None:
                raise ErroDeUso("não encontrei essa receita no catálogo", receita_id=slug)
            anotadas = json.loads(linha["respostas"])
            anotadas.extend({"campo": c, "valor": v, "quando": agora} for c, v in respostas)
            cur.execute(
                "UPDATE catalogo SET receita = ?, respostas = ?, atualizada_em = ? WHERE slug = ?",
                (
                    _json(replace(receita, nome=linha["nome"])),
                    json.dumps(anotadas, ensure_ascii=False),
                    agora,
                    slug,
                ),
            )
            linha = cur.execute("SELECT * FROM catalogo WHERE slug = ?", (slug,)).fetchone()
        return _da_linha(linha)

    def marcar_como_descoberta(self, slug: str, desde: datetime) -> ReceitaDoCatalogo | None:
        """A receita que a descoberta trouxe passa a dizer que veio dela. Devolve a linha.

        A página entra pela mesma porta da conversa (`buscar_receita_na_web`),
        que grava a origem `conversa`; quem sabe que o pedido foi da descoberta
        é o servidor que a iniciou. Só muda a receita que entrou depois de
        `desde` (o começo da descoberta) e que veio de uma página: a que ela
        trouxe pelo endereço, a que ela ditou e a que já estava no catálogo
        ficam como estão, e voltam `None`.
        """
        guardada = self.obter(slug)
        if guardada is None or guardada.criada_em is None or guardada.criada_em < desde:
            return None
        if guardada.origem is OrigemNoCatalogo.DESCOBERTA:
            return guardada
        if guardada.origem is not OrigemNoCatalogo.CONVERSA:
            return None
        with self._dossie.transacao() as cur:
            cur.execute(
                "UPDATE catalogo SET origem = ? WHERE slug = ? AND origem = ?",
                (OrigemNoCatalogo.DESCOBERTA.value, guardada.slug, OrigemNoCatalogo.CONVERSA.value),
            )
        return replace(guardada, origem=OrigemNoCatalogo.DESCOBERTA)

    # -- o nome único ------------------------------------------------------- #

    def _nome_livre(self, cur: sqlite3.Cursor, nome: str, slug: str, site: str) -> str:
        """O nome da receita nova: o dela, ou com o site entre parênteses se já é de outra."""
        base = " ".join(nome.split()) or "Receita sem nome"
        de_onde = site.strip() or "internet"
        opcoes = [base, f"{base} ({de_onde})"] + [
            f"{base} ({de_onde} {n})" for n in range(2, _TENTATIVAS_DE_NOME)
        ]
        das_candidatas = self._nomes_das_candidatas(slug)
        for opcao in opcoes:
            chave = chave_do_nome(opcao)
            ocupado = cur.execute(
                "SELECT 1 FROM catalogo WHERE chave_do_nome = ? AND slug != ?", (chave, slug)
            ).fetchone()
            if ocupado is None and chave not in das_candidatas:
                return opcao
        raise ErroDeUso("há receitas demais com esse nome", nome=base)

    def _nomes_das_candidatas(self, slug: str) -> set[str]:
        """Os nomes que as receitas em avaliação de outro id já ocupam."""
        return {
            chave_do_nome(nome)
            for nome, receita in self._dossie.candidatas().items()
            if id_da_receita(receita) != slug
        }

    def _conferir_nome_das_candidatas(self, nome: str, slug: str) -> None:
        if chave_do_nome(nome) in self._nomes_das_candidatas(slug):
            raise ErroDeUso(
                f"já há outra receita em avaliação chamada {nome!r}; "
                "dê um nome que diferencie a receita da senhora"
            )


# --------------------------------------------------------------------------- #
# Linhas e JSON
# --------------------------------------------------------------------------- #


def garantir_o_catalogo(dossie: Dossie) -> None:
    """A tabela do catálogo com as colunas de agora, e a página copiada no catálogo antigo."""
    dossie.garantir_esquema(ESQUEMA_DO_CATALOGO, COLUNAS_DO_CATALOGO)
    with dossie.transacao() as cur:
        cur.execute(_COPIAR_A_PAGINA)


def semear_o_catalogo(dossie: Dossie, semente: Path) -> int:
    """Põe as receitas da semente no catálogo vazio; com receita no catálogo, não faz nada.

    A semente (`dados/catalogo_inicial.json`) são receitas reais que o servidor
    já leu das páginas, sem nenhuma resposta dela, para um clone novo abrir a
    tela de Receitas cheia em vez de esperar a primeira busca na internet. Só
    entram as colunas que a tabela tem, e tudo numa transação: ou a semente
    inteira, ou nada. Devolve quantas receitas entraram.
    """
    if not semente.is_file():
        return 0
    garantir_o_catalogo(dossie)
    linhas: list[dict[str, Any]] = json.loads(semente.read_text(encoding="utf-8"))
    with dossie.transacao() as cur:
        if cur.execute("SELECT 1 FROM catalogo LIMIT 1").fetchone():
            return 0
        conhecidas = {coluna[1] for coluna in cur.execute("PRAGMA table_info(catalogo)")}
        entraram = 0
        for linha in linhas:
            colunas = [c for c in linha if c in conhecidas]
            # Os nomes das colunas vêm da própria tabela (PRAGMA), nunca do arquivo.
            sql = (
                f"INSERT OR IGNORE INTO catalogo ({', '.join(colunas)}) "
                f"VALUES ({', '.join('?' * len(colunas))})"
            )
            entraram += cur.execute(sql, [linha[c] for c in colunas]).rowcount
    return entraram


@dataclass(frozen=True, slots=True)
class CatalogoDeVolta:
    """O que "Restaurar os dados" fez no catálogo: o que ficou e o que era dela."""

    mantidas: int
    """As receitas das páginas lidas, que continuam na grade."""
    sem_as_respostas: int
    """As que ela tinha completado (rendimento, peso, "é o seu miolo?") e voltaram à página."""
    ditas: int
    """As receitas que ela ditou, que saem: eram dela, como as conversas."""
    sem_a_pagina: int
    """As completadas antes de o catálogo guardar a página: saem, e voltam lidas de novo."""


def voltar_ao_que_foi_lido(cur: sqlite3.Cursor) -> CatalogoDeVolta:
    """Tira do catálogo tudo o que é dela, dentro da transação de quem chama.

    As receitas das páginas que o servidor leu ficam, como a página veio: sem o
    que ela respondeu sobre elas. As que ela ditou saem. A receita completada
    num catálogo de antes da coluna `receita_lida` não tem a página guardada:
    sai também, para nenhuma resposta dela ficar escondida na receita.
    """
    ditas = cur.execute(
        "DELETE FROM catalogo WHERE origem = ?", (OrigemNoCatalogo.DITA.value,)
    ).rowcount
    sem_a_pagina = cur.execute(
        "DELETE FROM catalogo WHERE receita_lida IS NULL AND respostas != '[]'"
    ).rowcount
    sem_as_respostas = cur.execute(
        "UPDATE catalogo SET receita = receita_lida, respostas = '[]' "
        "WHERE receita_lida IS NOT NULL AND (respostas != '[]' OR receita != receita_lida)"
    ).rowcount
    mantidas = int(cur.execute("SELECT COUNT(*) FROM catalogo").fetchone()[0])
    return CatalogoDeVolta(mantidas, sem_as_respostas, ditas, sem_a_pagina)


# --------------------------------------------------------------------------- #
# A releitura das linhas, quando as regras de leitura mudam
# --------------------------------------------------------------------------- #

#: Os campos de uma linha que a leitura decide. O que ela disse da linha
#: (`item_da_despensa`, `peso_g`) não é da leitura, e a releitura não toca.
CAMPOS_DA_LEITURA: Final = ("nome", "quantidade", "medida", "observacao", "opcional", "entendida")


@dataclass(frozen=True, slots=True)
class LinhaRelida:
    """Uma linha guardada que as regras de agora leem diferente: onde, e o antes e o depois."""

    slug: str
    receita: str
    #: `receita` (a do catálogo), `receita_lida` (a página como veio) ou `candidata`.
    onde: str
    texto_original: str
    antes: dict[str, Any]
    depois: dict[str, Any]


def reler_as_linhas(
    dossie: Dossie, ler_linha: Callable[[str], IngredienteReceita], versao: int
) -> tuple[LinhaRelida, ...]:
    """Lê de novo as linhas das receitas guardadas com regras de leitura mais antigas.

    A releitura parte do texto original de cada linha, que a receita guarda, e
    não busca a página. Só mudam os campos que a leitura decide
    (`CAMPOS_DA_LEITURA`), e só nas linhas que as regras de agora leem
    diferente. A linha que ela respondeu fica como ela disse: a que está nas
    respostas da receita, e a que tem o item da despensa ou o peso que ela deu.
    A receita que ela ditou não passou pela leitura, e fica como está. A receita
    em avaliação que é a mesma do catálogo acompanha a do catálogo.

    Tudo numa transação, e cada receita relida fica marcada com `versao`: a
    próxima abertura não lê de novo. Devolve cada linha que mudou.
    """
    garantir_o_catalogo(dossie)
    relidas: list[LinhaRelida] = []
    with dossie.transacao() as cur:
        linhas = cur.execute(
            "SELECT slug, nome, origem, receita, receita_lida, respostas FROM catalogo "
            "WHERE versao_da_leitura IS NULL OR versao_da_leitura < ?",
            (versao,),
        ).fetchall()
        for linha in linhas:
            if linha["origem"] != OrigemNoCatalogo.DITA.value:
                relidas += _reler_a_receita(cur, linha, ler_linha)
            cur.execute(
                "UPDATE catalogo SET versao_da_leitura = ? WHERE slug = ?", (versao, linha["slug"])
            )
    return tuple(relidas)


def _reler_a_receita(
    cur: sqlite3.Cursor, linha: sqlite3.Row, ler_linha: Callable[[str], IngredienteReceita]
) -> list[LinhaRelida]:
    """A receita do catálogo, a página guardada e a em avaliação dela, lidas de novo."""
    slug, nome = linha["slug"], linha["nome"]
    respostas: list[dict[str, Any]] = json.loads(linha["respostas"] or "[]")
    dela = frozenset(chave_do_nome(str(r.get("campo") or "")) for r in respostas)
    relidas: list[LinhaRelida] = []
    # A receita, com o que ela respondeu; a página, como veio (sem resposta dela).
    receita, trocas = _relida(linha["receita"], ler_linha, dela)
    if trocas:
        cur.execute("UPDATE catalogo SET receita = ? WHERE slug = ?", (receita, slug))
        relidas += [LinhaRelida(slug, nome, "receita", *troca) for troca in trocas]
    if linha["receita_lida"] is not None:
        pagina, trocas = _relida(linha["receita_lida"], ler_linha, frozenset())
        if trocas:
            cur.execute("UPDATE catalogo SET receita_lida = ? WHERE slug = ?", (pagina, slug))
            relidas += [LinhaRelida(slug, nome, "receita_lida", *troca) for troca in trocas]
    em_avaliacao = cur.execute(
        "SELECT nome, dados FROM candidatas WHERE receita_id = ?", (slug,)
    ).fetchall()
    for candidata in em_avaliacao:
        texto, trocas = _relida(candidata["dados"], ler_linha, dela)
        if trocas:
            cur.execute(
                "UPDATE candidatas SET dados = ? WHERE nome = ?", (texto, candidata["nome"])
            )
            relidas += [LinhaRelida(slug, candidata["nome"], "candidata", *t) for t in trocas]
    return relidas


def _relida(
    texto_json: str, ler_linha: Callable[[str], IngredienteReceita], respondidas: Set[str]
) -> tuple[str, list[tuple[str, dict[str, Any], dict[str, Any]]]]:
    """A receita em JSON com as linhas lidas de novo, e o antes e o depois de cada uma que mudou.

    O JSON é mexido no lugar, campo a campo: o que não mudou sai escrito igual.
    """
    dados: dict[str, Any] = json.loads(texto_json)
    trocas: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for posicao, guardada in enumerate(dados.get("ingredientes") or []):
        original = str(guardada.get("texto_original") or "")
        dela = (
            chave_do_nome(original) in respondidas
            or guardada.get("item_da_despensa") is not None
            or guardada.get("peso_g") is not None
        )
        if dela or not original.strip():
            continue
        lida = ler_linha(original)
        nova = {**guardada, **_campos_da_leitura(lida)}
        if nova != guardada:
            trocas.append(
                (
                    original,
                    {campo: guardada.get(campo) for campo in CAMPOS_DA_LEITURA},
                    {campo: nova[campo] for campo in CAMPOS_DA_LEITURA},
                )
            )
            dados["ingredientes"][posicao] = nova
    if not trocas:
        return texto_json, trocas
    return json.dumps(dados, ensure_ascii=False), trocas


def _campos_da_leitura(lida: IngredienteReceita) -> dict[str, Any]:
    """Os campos que a leitura decide, escritos como `Receita.para_dict` os escreve."""
    return {
        "nome": lida.nome,
        "quantidade": str(lida.quantidade) if lida.quantidade is not None else None,
        "medida": lida.medida,
        "observacao": lida.observacao,
        "opcional": lida.opcional,
        "entendida": lida.entendida,
    }


def _json(receita: Receita) -> str:
    return json.dumps(receita.para_dict(), ensure_ascii=False)


def _foto(pagina: PaginaLida) -> str | None:
    """A foto que a página declarou, se não é a genérica do site."""
    if not pagina.imagem_url or foto_generica(pagina.imagem_url):
        return None
    return pagina.imagem_url


def _credito(pagina: PaginaLida) -> str | None:
    """ "Foto: TudoGostoso": a foto é do site de onde a receita veio."""
    if _foto(pagina) is None:
        return None
    return f"Foto: {pagina.site}" if pagina.site else "Foto: a página da receita"


def _da_linha(linha: sqlite3.Row) -> ReceitaDoCatalogo:
    respostas: list[dict[str, Any]] = json.loads(linha["respostas"] or "[]")
    return ReceitaDoCatalogo(
        slug=linha["slug"],
        receita=Receita.de_dict(json.loads(linha["receita"])),
        origem=OrigemNoCatalogo(linha["origem"]),
        url_canonica=linha["url_canonica"],
        site=linha["site"],
        autor=linha["autor"],
        imagem_url=linha["imagem_url"],
        credito_da_imagem=linha["credito_da_imagem"],
        tempos=TemposDaReceita(
            preparo_min=linha["preparo_min"],
            cozimento_min=linha["cozimento_min"],
            total_min=linha["total_min"],
        ),
        hash_do_conteudo=linha["hash_do_conteudo"],
        criada_em=datetime.fromisoformat(linha["criada_em"]),
        atualizada_em=datetime.fromisoformat(linha["atualizada_em"]),
        nome_original=linha["nome_original"],
        rendimento_texto=linha["rendimento_texto"],
        respostas=tuple(
            RespostaSobreAReceita(r["campo"], r["valor"], datetime.fromisoformat(r["quando"]))
            for r in respostas
        ),
    )


__all__ = [
    "CAMPOS_DA_LEITURA",
    "COLUNAS_DO_CATALOGO",
    "ESQUEMA_DO_CATALOGO",
    "MARCAS_DE_FOTO_GENERICA",
    "PREFIXO_DA_IMAGEM",
    "TAMANHO_DA_CHAVE_DA_IMAGEM",
    "TAMANHO_DO_ID",
    "Catalogo",
    "CatalogoDeVolta",
    "FotoDaReceita",
    "LinhaRelida",
    "OrigemNoCatalogo",
    "PaginaLida",
    "ReceitaDoCatalogo",
    "RespostaSobreAReceita",
    "TemposDaReceita",
    "chave_da_imagem",
    "chave_do_nome",
    "foto_generica",
    "garantir_o_catalogo",
    "id_da_receita",
    "id_da_url",
    "reler_as_linhas",
    "rota_da_imagem",
    "url_canonica",
    "voltar_ao_que_foi_lido",
]
