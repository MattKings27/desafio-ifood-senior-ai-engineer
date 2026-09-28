"""O histórico: tudo o que aconteceu na plataforma, em frases, numa linha do tempo só.

`GET /api/atividades` (a forma de `contratos/web/atividades.json`) junta, do
mais novo para o mais antigo:

- as decisões do cardápio, com as frases do próprio cardápio (`gateway.cardapio`);
- as mudanças da despensa (acrescentar, corrigir, acabou, tirar, desfazer,
  devolver aos complementos) e as compras feitas para um prato;
- as respostas dela sobre a cozinha (`mise.perfil_historico`);
- o gosto, as estrelas e as notas dela sobre cada receita, e o que ela respondeu
  sobre uma receita;
- os preços que ela informou (ou que o agente achou) do que falta comprar;
- as receitas que entraram na grade, e por onde entraram;
- o que o agente consultou para responder (a trilha das ferramentas), só as
  de leitura: o que ela gravou já aparece pelo que mudou.

Cada atividade diz **quem** fez (`senhora`, `consultora` para o agente, ou
`tela`, a própria plataforma), a **categoria** (despensa, receitas, cozinha, preço, cardápio), a
frase, quando, por onde (a tela ou a conversa) e o link para a coisa de que
fala. Nunca vai para a tela o nome de uma ferramenta, a identidade de quem
chamou, milissegundos ou o caminho de um arquivo: a trilha das ferramentas só
empresta o momento e a frase de `gateway.frases`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from mise import perfil_historico, receitas_json
from mise.catalogo import OrigemNoCatalogo, chave_do_nome
from mise.despensa import OrigemDoItem, id_do_item
from mise.despensa_editavel import Acao, TipoDeEvento
from mise.despensa_json import (
    FUSO,
    MESES,
    _campo_texto,
    _conteudo_da_unidade,
    _resumo_da_linha,
    _valor_da_compra,
    _valor_devolvido,
    numero_texto,
    quando_texto,
)
from mise.dossie import OrigemPreco
from mise.erros import ErroDeUso
from mise.genero import NomeFalado, falar
from mise.perfil import Gosto

from gateway.cardapio import guardada_do_prato, o_prato, passos
from gateway.frases import FRASES_DO_MOTOR
from gateway.politica import ESCOPOS, Escopo

if TYPE_CHECKING:
    from mise.despensa_editavel import EstadoDaDespensa, Evento
    from mise.dossie import LinhaDoExtrato
    from mise.mcp_server import Sessao

#: As categorias, na ordem dos chips da tela.
CATEGORIAS: Final[Mapping[str, str]] = {
    "despensa": "Despensa",
    "receitas": "Receitas",
    "cozinha": "Cozinha",
    "preco": "Preço",
    "cardapio": "Cardápio",
}

#: Quem fez: ela, o agente, ou a própria plataforma (a grade que se enche sozinha).
QUEM: Final[Mapping[str, str]] = {
    "senhora": "A senhora",
    "consultora": "O agente",
    "tela": "A tela",
}

#: Por onde a ação dela chegou, dito para ela.
CANAL_TEXTO: Final[Mapping[str, str]] = {"tela": "pela tela", "conversa": "pela conversa"}

#: A tela de cada categoria: é para lá que a consulta do agente leva.
ROTA_DA_CATEGORIA: Final[Mapping[str, str]] = {
    "despensa": "/despensa",
    "receitas": "/receitas",
    "cozinha": "/cozinha",
    "preco": "/precificar",
    "cardapio": "/cardapio",
}

#: A categoria de cada ferramenta de leitura do agente.
CATEGORIA_DA_FERRAMENTA: Final[Mapping[str, str]] = {
    "diagnostico_despensa": "despensa",
    "custo_unitario": "despensa",
    "converter_medida_culinaria": "despensa",
    "consultar_planilha": "despensa",
    "consultar_orcamento": "despensa",
    "consultar_perfil": "cozinha",
    "proxima_pergunta": "cozinha",
    "avaliar_receita": "receitas",
    "comparar_candidatas": "receitas",
    "consultar_gostos": "receitas",
    "consultar_conhecimento": "receitas",
    "pauta_de_descoberta": "receitas",
    "calcular_cmv": "preco",
    "cenarios_preco": "preco",
    "testar_sensibilidade": "preco",
    "consultar_precos_de_mercado": "preco",
    "buscar_preco_na_web": "preco",
    "estimar_preco_preliminar": "preco",
    "consultar_cardapio": "cardapio",
}

#: Ferramentas de leitura que também gravam algo que já aparece no histórico: a
#: receita que o agente trouxe entra pelo catálogo, não pela chamada.
_JA_CONTADAS: Final = frozenset({"buscar_receita_na_web"})

#: Quantas linhas da trilha das ferramentas o histórico lê (as mais novas).
LINHAS_DA_TRILHA: Final = 2000

#: A mesma consulta repetida dentro deste intervalo conta uma vez só.
_JANELA_DA_REPETICAO: Final = 10 * 60

#: Tamanho da página e o maior que se pode pedir.
LIMITE_PADRAO: Final = 40
LIMITE_MAXIMO: Final = 200

#: Quantos dias o filtro de dia oferece, dos mais novos.
DIAS_NO_FILTRO: Final = 14


@dataclass(frozen=True, slots=True)
class Atividade:
    """Uma coisa que aconteceu, dita para ela."""

    id: str
    quem: str
    categoria: str
    texto: str
    quando: datetime
    link: str | None
    canal: str | None = None
    resultado: str = "ok"

    @property
    def local(self) -> datetime:
        """O momento no horário dela."""
        quando = self.quando if self.quando.tzinfo is not None else self.quando.replace(tzinfo=UTC)
        return quando.astimezone(FUSO)

    @property
    def dia(self) -> str:
        return self.local.date().isoformat()

    def json(self, agora: datetime) -> dict[str, Any]:
        return {
            "id": self.id,
            "quem": self.quem,
            "quem_rotulo": QUEM[self.quem],
            "categoria": self.categoria,
            "categoria_rotulo": CATEGORIAS[self.categoria],
            "texto": self.texto,
            "quando_texto": quando_texto(self.local, agora),
            "hora_texto": f"{self.local:%H:%M}",
            "dia": self.dia,
            "canal_texto": CANAL_TEXTO.get(self.canal or ""),
            "resultado": self.resultado,
            "link": self.link,
        }


def _maiuscula(texto: str) -> str:
    return texto[:1].upper() + texto[1:]


def _o(nome: NomeFalado) -> str:
    """ "o creme de leite", ou o nome sozinho quando o gênero não é conhecido."""
    return nome.com_artigo() or nome.minusculo


# --------------------------------------------------------------------------- #
# O cardápio
# --------------------------------------------------------------------------- #


def das_decisoes(sessao: Sessao) -> list[Atividade]:
    """As decisões do cardápio, com a frase do próprio cardápio e o link para a receita."""
    rotas: dict[str, str] = {}
    atividades = []
    for passo in passos(sessao.dossie.historico()):
        registro = passo.registro
        chave = chave_do_nome(registro.prato)
        if chave not in rotas:
            guardada = guardada_do_prato(sessao, registro.prato)
            rotas[chave] = receitas_json.rota_da_receita(guardada.slug) if guardada else "/cardapio"
        atividades.append(
            Atividade(
                id=f"decisao-{registro.id}",
                quem="senhora",
                categoria="cardapio",
                texto=passo.texto(),
                quando=registro.registrado,
                link=rotas[chave],
                canal=registro.canal,
            )
        )
    return atividades


# --------------------------------------------------------------------------- #
# A despensa e as compras
# --------------------------------------------------------------------------- #

FrasesDaDespensa = Callable[["Evento", NomeFalado, "Mapping[int, LinhaDoExtrato]", str], str]


def _adicionou(evento: Evento, nome: NomeFalado, _extrato: Any, _unidade: str) -> str:
    resumo = _resumo_da_linha(evento)
    if str(evento.dados.get("linha", {}).get("origem", "")) == OrigemDoItem.ORCAMENTO.value:
        return f"A senhora comprou {_o(nome)} com os complementos: {resumo}."
    return f"A senhora acrescentou {_o(nome)} à despensa: {resumo}."


def _tirou(evento: Evento, nome: NomeFalado, extrato: Any, _unidade: str) -> str:
    devolvido = _valor_devolvido(evento, extrato)
    if evento.acao is Acao.ESTORNO:
        return (
            f"A compra {nome.de()} voltou para os complementos ({devolvido}), "
            "e o item saiu da despensa."
        )
    if evento.acao is Acao.DESFAZER:
        frase = f"Desfeito: {_o(nome)} saiu da despensa."
    else:
        frase = f"A senhora tirou {_o(nome)} da despensa."
    return f"{frase} {devolvido} voltaram para os complementos." if devolvido else frase


def _voltou(evento: Evento, nome: NomeFalado, extrato: Any, _unidade: str) -> str:
    compra = _valor_da_compra(evento, extrato)
    frase = f"{_maiuscula(_o(nome))} {nome.verbo('voltou', 'voltaram')} para a despensa."
    return f"{frase} {compra} saíram de novo dos complementos." if compra else frase


def _corrigiu(evento: Evento, nome: NomeFalado, extrato: Any, unidade: str) -> str:
    if evento.acao is Acao.ACABOU:
        return f"A senhora avisou que {_o(nome)} {nome.verbo('acabou', 'acabaram')}."
    campos = evento.dados.get("campos", {})
    if evento.acao is Acao.INFORMAR_EMBALAGEM:
        conteudo = _conteudo_da_unidade(campos.get("unidade"))
        return f"A senhora informou que a embalagem {nome.de()} tem {conteudo}."
    antes = evento.dados.get("antes", {})
    unidade = str(campos.get("unidade") or unidade)
    detalhes = [
        texto
        for campo in ("estoque", "quantidade_comprada", "preco_pago", "unidade", "categoria")
        if campo in campos
        and (texto := _campo_texto(campo, antes.get(campo), campos[campo], unidade))
    ]
    corpo = "; ".join(detalhes) or "dados corrigidos"
    if evento.acao is Acao.DESFAZER:
        frase = f"Desfeita a correção {nome.de()}: {corpo}."
    else:
        frase = f"A senhora corrigiu {_o(nome)}: {corpo}."
    devolvido = _valor_devolvido(evento, extrato)
    compra = _valor_da_compra(evento, extrato)
    if devolvido and compra is not None:
        frase += f" Voltaram {devolvido} e saíram {compra} dos complementos."
    return frase


_FRASES_DA_DESPENSA: Final[Mapping[TipoDeEvento, FrasesDaDespensa]] = {
    TipoDeEvento.ADICIONAR: _adicionou,
    TipoDeEvento.REMOVER: _tirou,
    TipoDeEvento.RESTAURAR: _voltou,
    TipoDeEvento.CORRIGIR: _corrigiu,
}


def _nome_do_evento(evento: Evento, estado: EstadoDaDespensa) -> tuple[str, str]:
    """O nome do item e a unidade da linha dele, mesmo depois de tirado."""
    item = estado.item(evento.item_id)
    if item is not None:
        return item.linha.nome, item.linha.unidade
    return str(evento.dados.get("linha", {}).get("nome", "o item")), ""


def da_despensa(sessao: Sessao) -> list[Atividade]:
    """As mudanças dela na despensa, cada uma com o nome do item."""
    estado = sessao.editavel.estado()
    extrato = {linha.id: linha for linha in sessao.dossie.extrato()}
    atividades = []
    for evento in estado.eventos:
        nome, unidade = _nome_do_evento(evento, estado)
        item = estado.item(evento.item_id)
        atividades.append(
            Atividade(
                id=f"despensa-{evento.rotulo}",
                quem="senhora",
                categoria="despensa",
                texto=_FRASES_DA_DESPENSA[evento.tipo](evento, falar(nome), extrato, unidade),
                quando=evento.registrado,
                link=f"/despensa/{evento.item_id}"
                if item is not None and item.ativo
                else "/despensa",
                canal=evento.canal,
            )
        )
    return atividades


def das_compras(sessao: Sessao) -> list[Atividade]:
    """As compras com os R$ 80,00 feitas para um prato (as da despensa já contam lá)."""
    extrato = sessao.dossie.extrato()
    por_id = {linha.id: linha for linha in extrato}
    atividades = []
    for linha in extrato:
        if linha.item_id is not None:
            continue
        original = por_id.get(linha.estorna) if linha.estorna is not None else linha
        nome = falar((original.ingrediente if original else None) or linha.descricao)
        if linha.e_estorno:
            texto = f"A compra {nome.de()} voltou para os complementos ({-linha.valor})."
        else:
            texto = f"A senhora comprou {_o(nome)} com os complementos: {linha.valor}."
        atividades.append(
            Atividade(
                id=f"compra-{linha.id}",
                quem="senhora",
                categoria="despensa",
                texto=texto,
                quando=linha.registrado,
                link="/despensa#orcamento",
                canal=linha.canal,
            )
        )
    return atividades


# --------------------------------------------------------------------------- #
# A cozinha
# --------------------------------------------------------------------------- #


def da_cozinha(sessao: Sessao) -> list[Atividade]:
    """O que ela respondeu sobre a cozinha: "A senhora disse que tem forno."."""
    return [
        Atividade(
            id=f"cozinha-{evento.id}",
            quem="senhora",
            categoria="cozinha",
            texto=f"{_maiuscula(evento.texto)}.",
            quando=evento.registrado,
            link="/cozinha",
            canal=evento.canal.value,
        )
        for evento in perfil_historico.eventos(sessao.dossie)
    ]


# --------------------------------------------------------------------------- #
# As receitas: o gosto, as estrelas, as respostas e as que entraram na grade
# --------------------------------------------------------------------------- #


def _rota_pelo_nome(sessao: Sessao, prato: str) -> str:
    guardada = sessao.catalogo.por_nome(prato)
    return receitas_json.rota_da_receita(guardada.slug) if guardada else "/receitas"


def dos_gostos(sessao: Sessao) -> list[Atividade]:
    """Se ela gosta de fazer cada prato, e o impedimento que ela vê."""
    atividades = []
    for opiniao in sessao.dossie.gostos():
        impedimento = opiniao.impedimento.strip()
        if opiniao.gosto is Gosto.GOSTA:
            texto = f"A senhora disse que gosta de fazer {o_prato(opiniao.prato)}."
        elif opiniao.gosto is Gosto.NAO_GOSTA:
            texto = f"A senhora disse que não gosta de fazer {o_prato(opiniao.prato)}."
        elif impedimento:
            texto = f"A senhora apontou um impedimento para {o_prato(opiniao.prato)}."
        else:
            continue
        if impedimento:
            texto += f" O impedimento: {impedimento.rstrip('.')}."
        atividades.append(
            Atividade(
                id=f"gosto-{id_do_item(opiniao.prato)}",
                quem="senhora",
                categoria="receitas",
                texto=texto,
                quando=opiniao.registrado,
                link=_rota_pelo_nome(sessao, opiniao.prato),
            )
        )
    return atividades


def das_avaliacoes(sessao: Sessao) -> list[Atividade]:
    """As estrelas e as notas dela, com a pontuação que deram."""
    from mise.avaliacoes import pontuar  # noqa: PLC0415

    gostos = {chave_do_nome(o.prato): o.gosto for o in sessao.dossie.gostos()}
    atividades = []
    for slug, avaliada in sessao.avaliacoes.todas().items():
        guardada = sessao.catalogo.obter(slug)
        if guardada is None or avaliada.atualizada_em is None:
            continue
        gosto = gostos.get(chave_do_nome(guardada.nome))
        gosta = {Gosto.GOSTA: True, Gosto.NAO_GOSTA: False}.get(gosto) if gosto else None
        pontuacao = pontuar(avaliada.estrelas, gosta)
        if pontuacao is not None:
            texto = (
                f"A senhora deu estrelas para {o_prato(guardada.nome)}: pontuação "
                f"{pontuacao.texto}."
            )
        elif avaliada.notas.strip():
            texto = f"A senhora anotou sobre {o_prato(guardada.nome)}."
        else:
            continue
        atividades.append(
            Atividade(
                id=f"avaliacao-{slug}",
                quem="senhora",
                categoria="receitas",
                texto=texto,
                quando=avaliada.atualizada_em,
                link=receitas_json.rota_da_receita(slug),
            )
        )
    return atividades


#: Quem pôs a receita na grade, e como se diz.
_ENTRADA_NA_GRADE: Final[Mapping[OrigemNoCatalogo, tuple[str, str]]] = {
    OrigemNoCatalogo.DESCOBERTA: ("tela", "Receita nova na grade: {nome}{site}."),
    OrigemNoCatalogo.CONVERSA: ("consultora", "Trouxe a receita {nome}{site}."),
    OrigemNoCatalogo.URL_DELA: ("senhora", "A senhora trouxe a receita {nome}{site}."),
    OrigemNoCatalogo.DITA: ("senhora", "A senhora ditou a receita {nome}."),
}


def do_catalogo(sessao: Sessao) -> list[Atividade]:
    """As receitas que entraram na grade, e o que ela respondeu sobre cada uma."""
    atividades = []
    for guardada in sessao.catalogo.listar():
        rota = receitas_json.rota_da_receita(guardada.slug)
        if guardada.criada_em is not None:
            quem, modelo = _ENTRADA_NA_GRADE[guardada.origem]
            site = f", do {guardada.site}" if guardada.site else ""
            atividades.append(
                Atividade(
                    id=f"receita-{guardada.slug}",
                    quem=quem,
                    categoria="receitas",
                    texto=modelo.format(nome=guardada.nome, site=site),
                    quando=guardada.criada_em,
                    link=rota,
                )
            )
        for indice, resposta in enumerate(guardada.respostas):
            dito = receitas_json._resposta_texto(resposta.campo, resposta.valor).rstrip(".")
            atividades.append(
                Atividade(
                    id=f"resposta-{guardada.slug}-{indice}",
                    quem="senhora",
                    categoria="receitas",
                    texto=f"{dito} ({guardada.nome}).",
                    quando=resposta.quando,
                    link=rota,
                )
            )
    return atividades


# --------------------------------------------------------------------------- #
# Os preços do que falta comprar
# --------------------------------------------------------------------------- #


def dos_precos(sessao: Sessao) -> list[Atividade]:
    """O preço de cada coisa que falta comprar: o que ela disse, ou o que o agente achou."""
    atividades = []
    for preco in sessao.dossie.precos():
        nome = falar(preco.ingrediente)
        por = (
            f" por {numero_texto(preco.quantidade)} {preco.unidade}".rstrip()
            if preco.quantidade is not None
            else ""
        )
        valor = f"{preco.valor}{por}"
        if preco.origem is OrigemPreco.INFORMADO_POR_ELA:
            quem, texto = "senhora", f"A senhora informou o preço {nome.de()}: {valor}."
        elif preco.origem is OrigemPreco.PESQUISADO_NA_WEB:
            quem, texto = "consultora", f"Achei o preço {nome.de()} na internet: {valor}."
        else:
            quem, texto = "consultora", f"Estimei o preço {nome.de()}: {valor}."
        atividades.append(
            Atividade(
                id=f"preco-{id_do_item(preco.ingrediente)}",
                quem=quem,
                categoria="preco",
                texto=texto,
                quando=preco.registrado,
                link="/receitas",
            )
        )
    return atividades


# --------------------------------------------------------------------------- #
# O que o agente consultou
# --------------------------------------------------------------------------- #


def ler_trilha(caminho: str | None, limite: int = LINHAS_DA_TRILHA) -> list[dict[str, Any]]:
    """As últimas chamadas das ferramentas; sem arquivo (ou ilegível), nada. Linha ruim é pulada."""
    if not caminho:
        return []
    try:
        linhas = Path(caminho).expanduser().read_text(encoding="utf-8").splitlines()[-limite:]
    except OSError:
        return []
    eventos = []
    for linha in linhas:
        try:
            evento = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if isinstance(evento, dict):
            eventos.append(evento)
    return eventos


def _consulta(evento: Mapping[str, Any], indice: int) -> Atividade | None:
    ferramenta = evento.get("ferramenta")
    momento = evento.get("momento")
    if (
        not isinstance(ferramenta, str)
        or not isinstance(momento, int | float)
        or ESCOPOS.get(ferramenta) is not Escopo.LEITURA
        or ferramenta in _JA_CONTADAS
        or ferramenta not in CATEGORIA_DA_FERRAMENTA
    ):
        return None
    frase = FRASES_DO_MOTOR[ferramenta]
    feito = frase.generica[1] if frase.generica else frase.rotulo_feito
    resultado = str(evento.get("resultado") or "ok")
    texto = (
        f"{_maiuscula(feito)}." if resultado == "ok" else f"{_maiuscula(feito)}, mas não deu certo."
    )
    categoria = CATEGORIA_DA_FERRAMENTA[ferramenta]
    return Atividade(
        id=f"consulta-{int(momento * 1000)}-{indice}",
        quem="consultora",
        categoria=categoria,
        texto=texto,
        quando=datetime.fromtimestamp(momento, UTC),
        link=ROTA_DA_CATEGORIA[categoria],
        canal="conversa",
        resultado=resultado,
    )


def da_consultora(eventos: Iterable[Mapping[str, Any]]) -> list[Atividade]:
    """As consultas dela, sem repetir a mesma frase seguida em poucos minutos."""
    atividades: list[Atividade] = []
    for indice, evento in enumerate(eventos):
        atividade = _consulta(evento, indice)
        if atividade is None:
            continue
        anterior = atividades[-1] if atividades else None
        if (
            anterior is not None
            and anterior.texto == atividade.texto
            and abs((atividade.quando - anterior.quando).total_seconds()) <= _JANELA_DA_REPETICAO
        ):
            continue
        atividades.append(atividade)
    return atividades


# --------------------------------------------------------------------------- #
# A linha do tempo, com a busca, os filtros e os dias
# --------------------------------------------------------------------------- #


def todas(sessao: Sessao, trilha: Iterable[Mapping[str, Any]] = ()) -> list[Atividade]:
    """Tudo, do mais novo para o mais antigo."""
    fontes: list[Atividade] = [
        *das_decisoes(sessao),
        *da_despensa(sessao),
        *das_compras(sessao),
        *da_cozinha(sessao),
        *dos_gostos(sessao),
        *das_avaliacoes(sessao),
        *do_catalogo(sessao),
        *dos_precos(sessao),
        *da_consultora(trilha),
    ]
    return sorted(fontes, key=lambda a: (a.local, a.id), reverse=True)


@dataclass(frozen=True, slots=True)
class Filtros:
    """Os filtros do histórico, já conferidos."""

    q: str | None = None
    categoria: str | None = None
    quem: str | None = None
    dia: str | None = None

    def __post_init__(self) -> None:
        if self.categoria is not None and self.categoria not in CATEGORIAS:
            raise ErroDeUso("essa categoria não existe", categoria=self.categoria)
        if self.quem is not None and self.quem not in QUEM:
            raise ErroDeUso("não sei quem é esse", quem=self.quem)

    def aceita(self, atividade: Atividade, *, com_o_dia: bool = True) -> bool:
        if self.categoria and atividade.categoria != self.categoria:
            return False
        if self.quem and atividade.quem != self.quem:
            return False
        if com_o_dia and self.dia and atividade.dia != self.dia:
            return False
        if self.q and self.q.strip():
            alvo = chave_do_nome(self.q)
            return alvo in chave_do_nome(atividade.texto)
        return True


def rotulo_do_dia(dia: str, agora: datetime) -> str:
    """ "Hoje", "Ontem", "24 de setembro", "24 de setembro de 2025"."""
    data = datetime.fromisoformat(dia).date()
    hoje = agora.astimezone(FUSO).date()
    if data == hoje:
        return "Hoje"
    if (hoje - data).days == 1:
        return "Ontem"
    texto = f"{data.day} de {MESES[data.month - 1]}"
    return texto if data.year == hoje.year else f"{texto} de {data.year}"


def _grupos(itens: Iterable[Atividade], agora: datetime) -> list[dict[str, Any]]:
    grupos: list[dict[str, Any]] = []
    for atividade in itens:
        if not grupos or grupos[-1]["dia"] != atividade.dia:
            grupos.append(
                {"dia": atividade.dia, "rotulo": rotulo_do_dia(atividade.dia, agora), "itens": []}
            )
        grupos[-1]["itens"].append(atividade.json(agora))
    return grupos


def pagina(
    sessao: Sessao,
    filtros: Filtros,
    *,
    cursor: str | None = None,
    limite: int = LIMITE_PADRAO,
    trilha: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """`GET /api/atividades`: uma página do histórico, agrupada por dia.

    `cursor` é o id da última atividade da página anterior; a próxima começa
    depois dela. Os dias do filtro são os que têm alguma atividade com os outros
    filtros, para ela nunca escolher um dia vazio.
    """
    agora = sessao.dossie.agora()
    eventos = ler_trilha(os.environ.get("MISE_AUDITORIA")) if trilha is None else trilha
    tudo = todas(sessao, eventos)
    sem_o_dia = [a for a in tudo if filtros.aceita(a, com_o_dia=False)]
    filtradas = [a for a in sem_o_dia if filtros.aceita(a)]
    inicio = 0
    if cursor:
        posicao = next((i for i, a in enumerate(filtradas) if a.id == cursor), None)
        if posicao is None:
            raise ErroDeUso("esse ponto do histórico não existe mais", cursor=cursor)
        inicio = posicao + 1
    fatia = filtradas[inicio : inicio + limite]
    tem_mais = inicio + limite < len(filtradas)
    dias = list(dict.fromkeys(a.dia for a in sem_o_dia))[:DIAS_NO_FILTRO]
    total = len(filtradas)
    return {
        "grupos": _grupos(fatia, agora),
        "total": total,
        "texto": "nada por aqui ainda"
        if total == 0
        else f"{total} {'registro' if total == 1 else 'registros'}",
        "proximo_cursor": fatia[-1].id if tem_mais and fatia else None,
        "categorias": [{"id": i, "rotulo": r} for i, r in CATEGORIAS.items()],
        "quem": [{"id": i, "rotulo": r} for i, r in QUEM.items()],
        "dias": [{"id": dia, "rotulo": rotulo_do_dia(dia, agora)} for dia in dias],
    }


__all__ = [
    "CATEGORIAS",
    "CATEGORIA_DA_FERRAMENTA",
    "DIAS_NO_FILTRO",
    "LIMITE_MAXIMO",
    "LIMITE_PADRAO",
    "QUEM",
    "Atividade",
    "Filtros",
    "da_consultora",
    "da_cozinha",
    "da_despensa",
    "das_avaliacoes",
    "das_compras",
    "das_decisoes",
    "do_catalogo",
    "dos_gostos",
    "dos_precos",
    "ler_trilha",
    "pagina",
    "rotulo_do_dia",
    "todas",
]
