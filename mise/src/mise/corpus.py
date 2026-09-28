"""O site inteiro como corpus do agente: cada tela vira trechos com fonte e rota.

O agente responde sobre a plataforma lendo o que a própria plataforma
mostra, e não a memória do modelo. Aqui o estado do motor vira trechos
(`retrieval.corpus.Trecho`), um por registro, cada um com o cabeçalho que diz
de onde ele é:

- **despensa**: cada item com o estoque, quanto ela pagou e por quanto, o custo
  com a conta, a origem, a pergunta em aberto e as linhas da planilha dela; e um
  resumo com o total e os itens que mais seguram dinheiro;
- **cozinha**: cada equipamento, técnica e restrição, com a situação, quem disse
  (a tela ou a conversa) e quando;
- **receita**: as receitas em avaliação e as do catálogo, em pai e filhos: o
  cabeçalho (fonte, rendimento, tempos e a situação para ela), o bloco dos
  ingredientes e um trecho por passo, com o que o passo pede;
- **avaliacao**: o que ela disse de cada receita: se gosta de fazer, as
  estrelas, as notas e a pontuação com a conta (só leitura de `mise.avaliacoes`);
- **cardapio**: as decisões dela, prato a prato;
- **orcamento**: os R$ 80,00 dos complementos, cada compra e cada preço que ela
  informou;
- **conhecimento**: a base de cozinha com fonte (`retrieval.corpus.conhecimento`).

As datas saem por extenso ("em 25/09/2026, 10:20"), nunca "hoje": o texto de um
trecho só muda quando o registro muda, e é isso que deixa o índice ser refeito
só quando alguma coisa foi gravada (`carimbo`).

**As receitas do catálogo** entram por um adaptador sobre a leitura publicada
(`mise.catalogo.Catalogo(dossie).listar()`): as que a plataforma descobriu ou
ela trouxe, além das que estão em avaliação com ela.
"""

from __future__ import annotations

import functools
import hashlib
import logging
import re
import threading
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlsplit

from mise.despensa import id_do_item
from mise.perfil import Gosto, Posse

if TYPE_CHECKING:
    from retrieval.corpus import IndiceDoCorpus, Limiares, ResultadoDaBusca, Trecho, Vetorizador

    from mise.avaliacoes import EstrelasENotas
    from mise.dossie import OpiniaoSobrePrato, RegistroDecisao
    from mise.mcp_server import Sessao
    from mise.receita import Receita

logger = logging.getLogger(__name__)

#: Onde a tela mostra cada parte.
ROTA_DA_DESPENSA: Final = "/despensa"
ROTA_DA_COZINHA: Final = "/cozinha"
ROTA_DO_CARDAPIO: Final = "/cardapio"
ROTA_DO_ORCAMENTO: Final = "/despensa#orcamento"

#: A frase do "não sei", a mesma em toda resposta sem trecho.
NAO_SEI: Final = (
    "Não achei nada sobre isso na plataforma nem na base de cozinha. "
    "Não sei, e prefiro não chutar. Se a senhora quiser, posso procurar na internet."
)

#: Quantos itens o resumo da despensa cita como os que mais seguram dinheiro.
MAIORES_NO_RESUMO: Final = 5

#: Tabelas do dossiê que só crescem: a versão delas é o maior id e a contagem.
_TABELAS_DE_EVENTOS: Final = frozenset({"decisoes", "gastos", "despensa_eventos", "perfil_eventos"})

#: Por onde ela disse, como a frase lê.
_CANAL: Final[dict[str, str]] = {"tela": "pela tela", "conversa": "na conversa"}

#: O nome de cada restrição da rotina, como a tela chama.
_RESTRICOES: Final[dict[str, str]] = {
    "bocas_fogao": "Bocas do fogão",
    "tempo_max_por_fornada_min": "Tempo de fogo por cozinhada",
    "porcoes_por_fornada": "Marmitas por leva",
    "espaco_geladeira_litros": "Espaço na geladeira",
    "energia_aparelhos_simultaneos": "Aparelhos fortes ao mesmo tempo",
    "tem_gas_sobrando": "Botijão de gás de reserva",
}

#: O que cada decisão quer dizer, dito para ela.
_DECISOES: Final[dict[str, str]] = {
    "aceito": "aceitou pôr no cardápio",
    "recusado": "recusou",
    "adiado": "deixou para decidir depois",
}


def _quando(momento: datetime) -> str:
    """ "em 25/09/2026, 10:20", no horário dela."""
    from mise.despensa_json import FUSO  # noqa: PLC0415

    return f"em {momento.astimezone(FUSO):%d/%m/%Y, %H:%M}"


def _canal(canal: object) -> str:
    return _CANAL.get(str(getattr(canal, "value", canal)), "")


#: O travessão usado como separador, que não chega a ela: vira vírgula.
_TRAVESSAO: Final = re.compile(r"\s+[\u2014\u2013]\s+")


def _frase(partes: Iterable[str]) -> str:
    """As partes em frases: cada uma começa com maiúscula e termina em ponto.

    Um texto de outro módulo com travessão de separador ("ponto de carne, mal
    passado, ao ponto?") sai com vírgula, como tudo o que chega a ela.
    """
    frases = " ".join(
        (p[:1].upper() + p[1:]) + ("" if p.endswith((".", "?", "!")) else ".") for p in partes if p
    )
    return _TRAVESSAO.sub(", ", frases)


def _lista(nomes: Sequence[str]) -> str:
    """ "a", "a e b", "a, b e c"."""
    if len(nomes) <= 1:
        return "".join(nomes)
    return ", ".join(nomes[:-1]) + " e " + nomes[-1]


def _minuscula(texto: str) -> str:
    return texto[:1].lower() + texto[1:]


# --------------------------------------------------------------------------- #
# Despensa
# --------------------------------------------------------------------------- #


@functools.lru_cache(maxsize=4)
def _linhas_da_planilha(caminho: str, _mudou_em: float) -> dict[str, list[str]]:
    """As linhas da planilha de cada item, pelo id: "aba Precos, linha 30 (… | R$ 82,00)".

    Lida uma vez por arquivo (e de novo se o arquivo mudar); a planilha que ela
    entregou não muda durante a consultoria.
    """
    from mise.planilha_txt import SEPARADOR, ler_celulas, texto_da_celula  # noqa: PLC0415

    linhas: dict[str, list[str]] = defaultdict(list)
    for aba, celulas in ler_celulas(caminho).items():
        for numero, linha in enumerate(celulas, start=1):
            textos = [texto_da_celula(c) for c in linha]
            if numero == 1 or not textos or not textos[0]:
                continue
            valores = SEPARADOR.join(t for t in textos if t)
            linhas[id_do_item(textos[0])].append(f"aba {aba}, linha {numero} ({valores})")
    return dict(linhas)


def _planilha(sessao: Sessao) -> dict[str, list[str]]:
    origem = sessao.planilha.origem
    if origem is None or not Path(origem).is_file():
        return {}
    try:
        return _linhas_da_planilha(str(origem), Path(origem).stat().st_mtime)
    except Exception as erro:  # sem a planilha, o item continua com a conta
        logger.warning("não consegui ler as linhas da planilha para o corpus: %s", erro)
        return {}


def trechos_da_despensa(sessao: Sessao) -> list[Trecho]:
    """Um trecho por item da despensa de agora, e o resumo dela."""
    from retrieval.corpus import Trecho  # noqa: PLC0415

    from mise import categorias  # noqa: PLC0415
    from mise.despensa_json import (  # noqa: PLC0415
        ORIGEM_ROTULO,
        comprado_texto,
        confianca_rotulo,
        custo_conhecido,
        custo_texto,
        derivacao_texto,
        estoque_texto,
        texto_do_evento,
    )

    estado = sessao.editavel.estado()
    despensa = estado.despensa
    planilha = _planilha(sessao)
    extrato = {linha.id: linha for linha in sessao.dossie.extrato()}
    trechos: list[Trecho] = []
    for item in despensa:
        estoque = estoque_texto(item)
        partes = [
            "o estoque acabou" if estoque == "acabou" else f"tem {estoque}",
            (
                f"comprou {comprado_texto(item)}"
                if item.preco_informado
                else "a senhora não disse quanto pagou"
            ),
            (
                f"custo de {custo_texto(item)} ({derivacao_texto(item)}), {confianca_rotulo(item)}"
                if custo_conhecido(item)
                else f"custo: {custo_texto(item)}"
            ),
            f"origem: {ORIGEM_ROTULO[item.origem]}",
        ]
        if (pendencia := despensa.pendencia_de(item.nome)) is not None:
            partes.append(f"falta saber: {pendencia.pergunta}")
        if linhas := planilha.get(item.id):
            partes.append(f"na planilha dela: {'; '.join(linhas)}")
        na_despensa = estado.item(item.id)
        if na_despensa is not None and na_despensa.eventos:
            ultimo = na_despensa.eventos[-1]
            mudanca = texto_do_evento(ultimo, item.nome, extrato, item.linha.unidade)
            quando = " ".join(filter(None, (_canal(ultimo.canal), _quando(ultimo.registrado))))
            partes.append(f"última mudança: {_minuscula(mudanca.rstrip('.'))}, {quando}")
        trechos.append(
            Trecho(
                id=f"despensa:{item.id}",
                tipo="despensa",
                rota=f"{ROTA_DA_DESPENSA}/{item.id}",
                fonte="a despensa da senhora",
                cabecalho=f"{item.nome}, na despensa da senhora:",
                corpo=_frase(partes),
                palavras=(categorias.categoria(item.categoria).rotulo,),
                rotulo=f"{item.nome}, na sua despensa",
            )
        )
    trechos.append(_resumo_da_despensa(sessao))
    return trechos


def _resumo_da_despensa(sessao: Sessao) -> Trecho:
    from retrieval.corpus import Trecho  # noqa: PLC0415

    from mise.despensa_json import fracao_texto  # noqa: PLC0415

    despensa = sessao.despensa
    maiores = [i for i in despensa.por_valor() if i.preco_informado][:MAIORES_NO_RESUMO]
    citados = [
        f"{i.nome} ({i.preco_pago}, {fracao_texto(despensa.fracao_de(i), i)})" for i in maiores
    ]
    pendentes = [p.ingrediente for p in despensa.pendencias]
    partes = [
        f"{len(despensa)} itens, e a senhora pagou {despensa.total_investido} no total",
        f"os que mais seguram dinheiro: {_lista(citados)}" if citados else "",
        f"itens com pergunta em aberto: {_lista(pendentes)}" if pendentes else "",
    ]
    return Trecho(
        id="despensa:resumo",
        tipo="despensa",
        rota=ROTA_DA_DESPENSA,
        fonte="a despensa da senhora",
        cabecalho="Despensa da senhora, o resumo:",
        corpo=_frase(partes),
        palavras=("total", "investido", "parado"),
        rotulo="A sua despensa",
    )


# --------------------------------------------------------------------------- #
# Cozinha
# --------------------------------------------------------------------------- #


def trechos_da_cozinha(sessao: Sessao) -> list[Trecho]:
    """Cada equipamento, técnica e restrição, com a situação e quem disse."""
    from retrieval.corpus import Trecho  # noqa: PLC0415

    from mise import perfil_historico  # noqa: PLC0415
    from mise.perfil import PERGUNTAS_OPERACIONAIS  # noqa: PLC0415
    from mise.perfil_historico import TipoDeItem, _restricao_em_palavras  # noqa: PLC0415
    from mise.taxonomia import EQUIPAMENTOS, EQUIPAMENTOS_POR_ID, TECNICAS  # noqa: PLC0415

    perfil = sessao.perfil
    ultimos = perfil_historico.ultimos_por_item(sessao.dossie)
    receitas = _receitas(sessao)
    trechos: list[Trecho] = []

    def dito(tipo: TipoDeItem, campo: str) -> str | None:
        evento = ultimos.get((tipo, campo))
        if evento is None:
            return None
        quando = " ".join(filter(None, (_canal(evento.canal), _quando(evento.registrado))))
        return f"{evento.texto}, {quando}"

    def pedem(tipo: str, id_: str) -> str:
        nomes = [r.receita.nome for r in receitas if id_ in getattr(r.receita, tipo)]
        return f"receitas que pedem: {_lista(nomes)}" if nomes else ""

    for e in EQUIPAMENTOS:
        posse = perfil.tem_equipamento(e.id)
        situacao = dito(TipoDeItem.EQUIPAMENTO, e.id) or _situacao(
            posse, suposto=perfil.suposto(e.id), verbo="tem", pressuposto=e.pressuposto
        )
        substitutos = [EQUIPAMENTOS_POR_ID[s].nome.lower() for s in e.substitutos]
        partes = [
            situacao,
            f"o que faz o mesmo papel: {_lista(substitutos)}" if substitutos else "",
            pedem("equipamentos", e.id),
            "" if posse.resolvido and not perfil.suposto(e.id) else e.pergunta_para_ela(),
        ]
        trechos.append(
            Trecho(
                id=f"cozinha:equipamento:{e.id}",
                tipo="cozinha",
                rota=ROTA_DA_COZINHA,
                fonte="a cozinha da senhora",
                cabecalho=f"{e.nome}, equipamento na cozinha da senhora:",
                corpo=_frase(partes),
                palavras=e.padroes,
                rotulo=f"{e.nome}, na sua cozinha",
            )
        )
    for t in TECNICAS:
        posse = perfil.domina_tecnica(t.id)
        situacao = dito(TipoDeItem.TECNICA, t.id) or _situacao(
            posse, suposto=perfil.suposto(t.id), verbo="faz", pressuposto=t.pressuposta
        )
        partes = [
            situacao,
            f"dificuldade {t.dificuldade} de 5",
            pedem("tecnicas", t.id),
            "" if posse.resolvido and not perfil.suposto(t.id) else t.pergunta_para_ela(),
        ]
        trechos.append(
            Trecho(
                id=f"cozinha:tecnica:{t.id}",
                tipo="cozinha",
                rota=ROTA_DA_COZINHA,
                fonte="a cozinha da senhora",
                cabecalho=f"{t.nome}, técnica na cozinha da senhora:",
                corpo=_frase(partes),
                palavras=t.padroes,
                rotulo=f"{t.nome}, na sua cozinha",
            )
        )
    for campo, rotulo in _RESTRICOES.items():
        valor = getattr(perfil.restricoes, campo)
        anotado = (
            f"está anotado que {_restricao_em_palavras(campo, {'valor': valor})}"
            if valor is not None
            else f"ainda não perguntei. A pergunta é: {PERGUNTAS_OPERACIONAIS[campo]}"
        )
        restricao = dito(TipoDeItem.OPERACIONAL, campo) or anotado
        trechos.append(
            Trecho(
                id=f"cozinha:restricao:{campo}",
                tipo="cozinha",
                rota=ROTA_DA_COZINHA,
                fonte="a cozinha da senhora",
                cabecalho=f"{rotulo}, na rotina da senhora:",
                corpo=_frase([restricao]),
                rotulo=f"{rotulo}, na sua cozinha",
            )
        )
    return trechos


def _situacao(posse: Posse, *, suposto: bool, verbo: str, pressuposto: bool) -> str:
    """O estado de um item que ninguém mudou ainda, dito para ela."""
    if posse is Posse.TEM and (suposto or pressuposto):
        return "está como suposto: toda cozinha costuma ter, e a senhora ainda não confirmou"
    if posse is Posse.TEM:
        return f"está anotado que a senhora {verbo}"
    if posse is Posse.NAO_TEM:
        return f"está anotado que a senhora não {verbo}"
    return "ainda não perguntei à senhora"


# --------------------------------------------------------------------------- #
# Receitas
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ReceitaDaPlataforma:
    """Uma receita que a plataforma mostra, em avaliação ou no catálogo, com a fonte."""

    slug: str
    receita: Receita
    site: str | None
    url: str | None
    em_avaliacao: bool


def _site(receita: Receita) -> str | None:
    if receita.fonte:
        return receita.fonte
    if receita.url:
        return (urlsplit(receita.url).hostname or "").removeprefix("www.") or None
    return None


class ReceitasDaPlataforma:
    """O adaptador das receitas: as em avaliação e as do catálogo, sem repetir.

    A leitura do catálogo é a interface publicada (`Catalogo.listar`); a
    receita em avaliação vale mais que a mesma do catálogo, porque é nela que
    ficam o rendimento e as respostas que ela deu.
    """

    def __init__(self, sessao: Sessao) -> None:
        self._sessao = sessao

    def listar(self) -> list[ReceitaDaPlataforma]:
        from mise.catalogo import Catalogo  # noqa: PLC0415
        from mise.despensa_json import slug_da_receita  # noqa: PLC0415

        vistas: dict[str, ReceitaDaPlataforma] = {}
        for receita in self._sessao.candidatas.values():
            slug = slug_da_receita(receita)
            vistas[slug] = ReceitaDaPlataforma(slug, receita, _site(receita), receita.url, True)
        for guardada in Catalogo(self._sessao.dossie).listar():
            if guardada.slug not in vistas:
                vistas[guardada.slug] = ReceitaDaPlataforma(
                    guardada.slug,
                    guardada.receita,
                    guardada.site or _site(guardada.receita),
                    guardada.receita.url,
                    False,
                )
        return sorted(vistas.values(), key=lambda r: (r.receita.nome, r.slug))


def _receitas(sessao: Sessao) -> list[ReceitaDaPlataforma]:
    return ReceitasDaPlataforma(sessao).listar()


def _tempos(receita: Receita) -> str:
    partes = [
        f"{rotulo} {minutos} min"
        for rotulo, minutos in (
            ("preparo", receita.tempo_preparo_min),
            ("cozimento", receita.tempo_cozimento_min),
            ("total", receita.tempo_total_min),
        )
        if minutos is not None
    ]
    return "tempos que a receita declara: " + ", ".join(partes) if partes else ""


def trechos_das_receitas(sessao: Sessao) -> list[Trecho]:
    """Cada receita em pai e filhos, e o que ela disse sobre fazer cada uma."""
    from retrieval.corpus import Trecho  # noqa: PLC0415

    from mise.avaliacoes import Avaliacoes  # noqa: PLC0415
    from mise.passos import avaliar_passos, minutos_ativos  # noqa: PLC0415

    perfil = sessao.perfil
    avaliacoes = Avaliacoes(sessao.dossie).todas()
    trechos: list[Trecho] = []
    for item in _receitas(sessao):
        receita, slug = item.receita, item.slug
        onde = item.site or "receita que a senhora ditou"
        pai_id = f"receita:{slug}"
        rota = f"/receitas/{slug}"
        fonte = item.site or "receita ditada pela senhora"
        avaliacao = sessao.avaliar(receita)
        ativos = minutos_ativos(receita)
        partes = [
            (
                f"rende {receita.rendimento_porcoes} "
                f"{'porção' if receita.rendimento_porcoes == 1 else 'porções'}"
                if receita.rendimento_informado
                else "a receita não diz quantas porções rende"
            ),
            _tempos(receita),
            f"tempo com fogo ou aparelho ligado: {ativos.derivacao}" if ativos.derivacao else "",
            f"situação para a senhora: {avaliacao.veredito.rotulo_para_ela}. {avaliacao.resumo()}",
            *(f"falta saber: {p.texto}" for p in avaliacao.perguntas),
            "está em avaliação com a senhora" if item.em_avaliacao else "está no catálogo",
            f"a receita veio do site {item.site}" if item.url and item.site else "",
            f"endereço da receita: {item.url}" if item.url else "",
        ]
        trechos.append(
            Trecho(
                id=pai_id,
                tipo="receita",
                rota=rota,
                fonte=fonte,
                cabecalho=f"Receita {receita.nome}, {onde}:",
                corpo=_frase(partes),
                rotulo=f"Receita {receita.nome}",
            )
        )
        faltantes = [
            f"{f.nome} ({f.quantidade_texto}"
            + (f", {f.custo_estimado})" if f.custo_estimado is not None else ", sem preço ainda)")
            for f in avaliacao.faltantes
        ]
        ingredientes = [
            "; ".join(i.texto_original for i in receita.ingredientes),
            f"falta comprar: {_lista(faltantes)}" if faltantes else "",
            f"a gosto: {_lista(list(avaliacao.a_gosto))}" if avaliacao.a_gosto else "",
            (
                f"opcionais: {_lista([i.nome for i in receita.ingredientes if i.opcional])}"
                if any(i.opcional for i in receita.ingredientes)
                else ""
            ),
        ]
        trechos.append(
            Trecho(
                id=f"{pai_id}:ingredientes",
                tipo="receita",
                rota=rota,
                fonte=fonte,
                cabecalho=f"Receita {receita.nome}, {onde}, ingredientes:",
                corpo=_frase(ingredientes),
                pai=pai_id,
                ordem=0,
                rotulo=f"Receita {receita.nome}",
            )
        )
        passos = avaliar_passos(receita, perfil).passos
        for passo in passos:
            pede = [f"{r.nome.lower()} ({r.rotulo_estado})" for r in passo.requisitos]
            partes = [
                passo.texto,
                f"pede {_lista(pede)}" if pede else "",
                f"tempo: {_lista([limite.texto for limite in passo.limites])}"
                if passo.limites
                else "",
            ]
            trechos.append(
                Trecho(
                    id=f"{pai_id}:passo-{passo.ordem}",
                    tipo="receita",
                    rota=rota,
                    fonte=fonte,
                    cabecalho=(
                        f"Receita {receita.nome}, {onde}, passo {passo.ordem} de {len(passos)}:"
                    ),
                    corpo=_frase(partes),
                    pai=pai_id,
                    ordem=passo.ordem,
                    rotulo=f"Receita {receita.nome}",
                )
            )
        estrelas = avaliacoes.get(slug)
        avaliacao_dela = _avaliacao(
            slug, receita.nome, sessao.dossie.gosto_por(receita.nome), estrelas
        )
        if avaliacao_dela is not None:
            trechos.append(avaliacao_dela)
    return trechos


def _avaliacao(
    slug: str, nome: str, opiniao: OpiniaoSobrePrato | None, estrelas: EstrelasENotas | None
) -> Trecho | None:
    """O que ela disse da receita: o gosto, as estrelas, as notas e a pontuação com a conta.

    Só leitura, sobre `mise.avaliacoes`: o gosto mora nos `gostos` do dossiê, as
    estrelas e as notas na tabela das avaliações, e a pontuação é calculada.
    """
    from retrieval.corpus import Trecho  # noqa: PLC0415

    from mise.avaliacoes import NA_CONTA, ORDEM_DA_CONTA, pontuar  # noqa: PLC0415

    avaliada = estrelas is not None and (estrelas.avaliada or bool(estrelas.notas))
    if opiniao is None and not avaliada:
        return None
    partes: list[str] = []
    gosta: bool | None = None
    if opiniao is not None:
        gosta = {Gosto.GOSTA: True, Gosto.NAO_GOSTA: False}.get(opiniao.gosto)
        dito = {
            Gosto.GOSTA: "a senhora disse que gosta de fazer",
            Gosto.NAO_GOSTA: "a senhora disse que não gosta de fazer",
        }.get(opiniao.gosto, "a senhora ainda não disse se gosta de fazer")
        partes.append(f"{dito}, {_quando(opiniao.registrado)}")
        if opiniao.impedimento:
            partes.append(f"impedimento que ela vê: {opiniao.impedimento}")
    if estrelas is not None and estrelas.avaliada:
        dadas = [
            f"{NA_CONTA[c]} {estrelas.estrelas[c]}"
            for c in ORDEM_DA_CONTA
            if estrelas.estrelas.get(c) is not None
        ]
        partes.append(f"estrelas que ela deu, de 1 a 5: {_lista(dadas)}")
        pontuacao = pontuar(estrelas.estrelas, gosta)
        if pontuacao is not None:
            partes.append(f"pontuação {pontuacao.texto} de 100 ({pontuacao.derivacao})")
    if estrelas is not None and estrelas.notas:
        partes.append(f"notas dela: {estrelas.notas}")
    return Trecho(
        id=f"avaliacao:{slug}",
        tipo="avaliacao",
        rota=f"/receitas/{slug}",
        fonte="o que a senhora disse",
        cabecalho=f"Avaliação da receita {nome}:",
        corpo=_frase(partes),
        palavras=("gosto", "gosta", "estrelas", "nota", "pontuação", "ranking"),
        rotulo=f"O que a senhora disse de {nome}",
    )


# --------------------------------------------------------------------------- #
# Cardápio e orçamento
# --------------------------------------------------------------------------- #


def _decisao(registro: RegistroDecisao) -> str:
    feito = _DECISOES.get(registro.decisao.value, registro.decisao.value)
    preco = registro.detalhes.get("preco") if registro.decisao.value == "aceito" else None
    partes = [
        f"a senhora {feito}" + (f" a {preco}" if preco else ""),
        _canal(registro.canal),
        _quando(registro.registrado),
    ]
    frase = " ".join(p for p in partes if p)
    return f"{frase} (motivo: {registro.motivo})" if registro.motivo else frase


def trechos_do_cardapio(sessao: Sessao) -> list[Trecho]:
    """Um trecho por prato decidido, com a decisão de agora e as de antes."""
    from retrieval.corpus import Trecho  # noqa: PLC0415

    por_prato: dict[str, list[RegistroDecisao]] = defaultdict(list)
    for registro in sessao.dossie.historico():
        por_prato[registro.prato].append(registro)
    trechos: list[Trecho] = []
    for prato, registros in sorted(por_prato.items()):
        ordenados = sorted(registros, key=lambda r: (r.registrado, r.id or 0))
        atual, anteriores = ordenados[-1], ordenados[:-1]
        partes = [_decisao(atual)]
        if anteriores:
            partes.append("antes, " + "; ".join(_decisao(r) for r in reversed(anteriores)))
        trechos.append(
            Trecho(
                id=f"cardapio:{id_do_item(prato)}",
                tipo="cardapio",
                rota=ROTA_DO_CARDAPIO,
                fonte="o cardápio da senhora",
                cabecalho=f"Cardápio, {prato}:",
                corpo=_frase(partes),
                palavras=("decisão", "preço", "vender", "venda"),
                rotulo=f"{prato}, no seu cardápio",
            )
        )
    no_cardapio = sessao.dossie.cardapio
    trechos.append(
        Trecho(
            id="cardapio:resumo",
            tipo="cardapio",
            rota=ROTA_DO_CARDAPIO,
            fonte="o cardápio da senhora",
            cabecalho="Cardápio da senhora, o resumo:",
            rotulo="O seu cardápio",
            corpo=_frase(
                [
                    f"pratos no cardápio: {_lista(list(no_cardapio))}"
                    if no_cardapio
                    else "ainda não há prato no cardápio"
                ]
            ),
        )
    )
    return trechos


def _compras_contando(n: int) -> str:
    if n == 0:
        return "nenhuma compra contando: as que houve foram devolvidas"
    return "1 compra contando" if n == 1 else f"{n} compras contando"


def trechos_do_orcamento(sessao: Sessao) -> list[Trecho]:
    """Os R$ 80,00 dos complementos, cada compra e cada preço que ela informou."""
    from retrieval.corpus import Trecho  # noqa: PLC0415

    dossie = sessao.dossie
    estado = dossie.orcamento()
    extrato = dossie.extrato()
    compras = [linha for linha in extrato if not linha.e_estorno]
    trechos = [
        Trecho(
            id="orcamento",
            tipo="orcamento",
            rota=ROTA_DO_ORCAMENTO,
            fonte="o orçamento dos complementos",
            cabecalho="Orçamento dos complementos da senhora:",
            corpo=_frase(
                [
                    f"são {estado.inicial} para comprar o que falta",
                    f"a senhora já usou {estado.gasto} e restam {estado.restante}",
                    _compras_contando(len([c for c in compras if c.ativa]))
                    if compras
                    else "nenhuma compra ainda",
                ]
            ),
            palavras=("orcamento", "complementos", "sobrou", "restam"),
            rotulo="O seu orçamento dos complementos",
        )
    ]
    for linha in compras:
        partes = [
            f"{linha.descricao}: {linha.valor}",
            " ".join(filter(None, (_canal(linha.canal), _quando(linha.registrado)))),
            "depois devolvida aos complementos" if linha.estornada else "",
        ]
        trechos.append(
            Trecho(
                id=f"orcamento:compra-{linha.id}",
                tipo="orcamento",
                rota=ROTA_DO_ORCAMENTO,
                fonte="o extrato dos complementos",
                cabecalho="Compra com os complementos:",
                corpo=_frase([", ".join(p for p in partes if p)]),
                palavras=(linha.ingrediente,) if linha.ingrediente else (),
                rotulo=f"Compra de {linha.descricao}, no seu orçamento",
            )
        )
    for preco in dossie.precos():
        por = f" por {preco.cotacao.por}" if preco.cotacao.por else ""
        origem = {
            "informado_por_ela": "a senhora informou",
            "pesquisado_na_web": "foi pesquisado na internet",
            "estimado": "é uma estimativa",
        }.get(preco.origem.value, "foi anotado")
        trechos.append(
            Trecho(
                id=f"orcamento:preco-{id_do_item(preco.ingrediente)}",
                tipo="orcamento",
                rota=ROTA_DO_ORCAMENTO,
                fonte="os preços que a senhora informou",
                cabecalho=f"Preço de {preco.ingrediente} para comprar:",
                corpo=_frase([f"{preco.valor}{por}, {origem} {_quando(preco.registrado)}"]),
                palavras=("mercado", "custa"),
                rotulo=f"Preço de {preco.ingrediente}, no seu orçamento",
            )
        )
    return trechos


# --------------------------------------------------------------------------- #
# O corpus, a versão e a consulta
# --------------------------------------------------------------------------- #


def montar_trechos(sessao: Sessao, *, conhecimento: bool = True) -> list[Trecho]:
    """Todos os trechos da plataforma, na ordem das telas."""
    from retrieval.corpus import trechos_do_conhecimento  # noqa: PLC0415

    trechos = [
        *trechos_da_despensa(sessao),
        *trechos_da_cozinha(sessao),
        *trechos_das_receitas(sessao),
        *trechos_do_cardapio(sessao),
        *trechos_do_orcamento(sessao),
    ]
    if conhecimento:
        trechos.extend(trechos_do_conhecimento())
    return trechos


def carimbo(sessao: Sessao) -> str:
    """A versão do estado: muda quando qualquer coisa é gravada no dossiê.

    As tabelas que só crescem entram pelo maior id e pela contagem; as que se
    reescrevem no lugar (o perfil, o gosto, a receita em avaliação, o preço),
    pelo conteúdo. Nenhuma data relativa entra nos trechos, então a mesma
    versão é sempre o mesmo texto.
    """
    resumo = hashlib.sha256()
    with sessao.dossie.cursor() as cur:
        tabelas = [
            linha[0]
            for linha in cur.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for tabela in tabelas:
            if tabela in _TABELAS_DE_EVENTOS:
                contagem, maior = cur.execute(
                    f"SELECT count(*), max(rowid) FROM {tabela}"
                ).fetchone()
                resumo.update(f"{tabela}:{contagem}:{maior}\n".encode())
            else:
                for linha in cur.execute(f"SELECT * FROM {tabela} ORDER BY rowid"):
                    resumo.update(f"{tabela}:{tuple(linha)!r}\n".encode())
    resumo.update(str(sessao.planilha.origem).encode())
    return resumo.hexdigest()[:16]


@functools.cache
def _vetorizador(pasta: str | None, modo: str) -> Vetorizador:
    """Um braço vetorial por pasta de estado e modo, para o processo inteiro."""
    from retrieval.corpus.vetores import vetorizador_padrao  # noqa: PLC0415

    return vetorizador_padrao(Path(pasta) if pasta else None, modo=modo)


def vetorizador_da_sessao(sessao: Sessao) -> Vetorizador:
    """O braço vetorial da sessão, com o cache ao lado do dossiê (`.estado/`)."""
    from retrieval.corpus.vetores import modo_escolhido  # noqa: PLC0415

    return _vetorizador(str(sessao.dossie.caminho.parent), modo_escolhido())


def analisador_da_plataforma() -> Any:
    """O analisador com os sinônimos da cozinha e os do casamento de ingrediente."""
    from retrieval.corpus.analisador import (  # noqa: PLC0415
        SINONIMOS_DA_COZINHA,
        Analisador,
        sinonimos_do_casamento,
    )

    from mise.casamento import SINONIMOS  # noqa: PLC0415

    return Analisador([*SINONIMOS_DA_COZINHA, *sinonimos_do_casamento(SINONIMOS)])


class CorpusDaSessao:
    """O índice da sessão, refeito só quando o estado muda."""

    def __init__(
        self,
        sessao: Sessao,
        *,
        vetorizador: Vetorizador | None = None,
        limiares: Limiares | None = None,
    ) -> None:
        self.sessao = sessao
        self._vetorizador = vetorizador
        self._limiares = limiares
        self._indice: IndiceDoCorpus | None = None
        self._trava = threading.Lock()
        self.reconstrucoes = 0

    def indice(self) -> IndiceDoCorpus:
        """O índice do estado de agora: o mesmo objeto enquanto nada for gravado."""
        from retrieval.corpus import IndiceDoCorpus  # noqa: PLC0415

        with self._trava:
            if self._indice is None or self._indice.versao != carimbo(self.sessao):
                trechos = montar_trechos(self.sessao)
                # A versão é lida depois de montar: a primeira leitura da cozinha
                # cria a tabela do histórico, e isso não é mudança dela.
                self._indice = IndiceDoCorpus(
                    trechos,
                    analisador_da_plataforma(),
                    self._vetorizador or vetorizador_da_sessao(self.sessao),
                    versao=carimbo(self.sessao),
                    limiares=self._limiares,
                )
                self.reconstrucoes += 1
            return self._indice

    def buscar(
        self, pergunta: str, tipos: Sequence[str] | None = None, k: int | None = None
    ) -> ResultadoDaBusca:
        from retrieval.corpus import K_PADRAO  # noqa: PLC0415

        return self.indice().buscar(pergunta, tipos=tipos, k=K_PADRAO if k is None else k)

    def consultar(
        self, pergunta: str, tipos: Sequence[str] | None = None, k: int | None = None
    ) -> dict[str, Any]:
        """A resposta de `consultar_conhecimento`, na forma de `contratos/web/conhecimento.json`."""
        return resposta_da_busca(self.buscar(pergunta, tipos, k))


def resposta_da_busca(resultado: ResultadoDaBusca) -> dict[str, Any]:
    """`{trechos[{id, tipo, rota, fonte, texto, pontuacao}], nada_relevante, texto}`."""
    trechos = [
        {
            "id": a.trecho.id,
            "tipo": a.trecho.tipo,
            "rota": a.trecho.rota,
            "fonte": a.trecho.fonte,
            "texto": a.texto,
            "pontuacao": a.pontuacao,
        }
        for a in resultado.achados
    ]
    if not trechos:
        texto = NAO_SEI
    elif len(trechos) == 1:
        texto = "Achei 1 trecho com fonte sobre a pergunta."
    else:
        texto = f"Achei {len(trechos)} trechos com fonte sobre a pergunta."
    return {"trechos": trechos, "nada_relevante": not trechos, "texto": texto}


#: Um corpus por sessão do processo (a do servidor do agente, a da API).
_POR_SESSAO: dict[int, CorpusDaSessao] = {}
_TRAVA_GLOBAL = threading.Lock()


def corpus_da_sessao(sessao: Sessao) -> CorpusDaSessao:
    """O corpus desta sessão, criado na primeira consulta e guardado para as próximas."""
    with _TRAVA_GLOBAL:
        atual = _POR_SESSAO.get(id(sessao))
        if atual is None or atual.sessao is not sessao:
            atual = _POR_SESSAO[id(sessao)] = CorpusDaSessao(sessao)
        return atual


def fontes_do_resultado(resultado: ResultadoDaBusca) -> dict[str, Any] | None:
    """Os dados do card "De onde eu tirei isso": um chip por registro, sem repetir.

    Trecho da plataforma vira chip com o nome do registro e a tela dele ("Óleo de
    soja, na sua despensa"); fato da base de cozinha, chip com o nome da fonte e
    sem tela. Sem trecho, não há card: "não sei" não tem fonte para mostrar.
    """
    chips: dict[tuple[str, str | None], None] = {}
    for achado in resultado.achados:
        trecho = achado.trecho
        rotulo = trecho.fonte if trecho.tipo == "conhecimento" else trecho.nome
        chips.setdefault((rotulo, trecho.rota))
    if not chips:
        return None
    return {
        "texto": "De onde eu tirei isso",
        "chips": [{"rotulo": rotulo, "rota": rota} for rotulo, rota in chips],
    }


__all__ = [
    "NAO_SEI",
    "ROTA_DA_COZINHA",
    "ROTA_DA_DESPENSA",
    "ROTA_DO_CARDAPIO",
    "ROTA_DO_ORCAMENTO",
    "CorpusDaSessao",
    "ReceitaDaPlataforma",
    "ReceitasDaPlataforma",
    "analisador_da_plataforma",
    "carimbo",
    "corpus_da_sessao",
    "fontes_do_resultado",
    "montar_trechos",
    "resposta_da_busca",
    "trechos_da_cozinha",
    "trechos_da_despensa",
    "trechos_das_receitas",
    "trechos_do_cardapio",
    "trechos_do_orcamento",
    "vetorizador_da_sessao",
]
