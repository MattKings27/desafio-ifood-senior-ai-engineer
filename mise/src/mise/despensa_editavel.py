"""A despensa que ela edita: a planilha mais as mudanças dela, em eventos.

A planilha que ela entregou nunca é reescrita. O que ela muda (acrescentar o que
já tinha, comprar com os complementos, corrigir, "acabou", tirar, informar o
peso da embalagem) vira uma linha em `despensa_eventos`, e a despensa de agora é
a planilha com os eventos aplicados, em ordem. Desfazer também é um evento, que
aponta (`desfaz`) para o que desfez: nada se apaga, e o histórico de cada item
responde "de onde veio este número?".

**A mesma conta.** Cada item de agora sai de `montar_ingrediente`, a mesma
função que monta os 37 da planilha. Uma correção muda a linha do item
(quantidade, unidade, preço) e o custo é refeito por ela, com a pendência junto:
informar o peso da cobertura de chocolate troca a unidade por uma que a conta lê
("un 1kg"), o custo passa a existir com confiança média e a pergunta some.

**Nome não muda.** Cotações e compras são guardadas pelo nome canônico do item;
trocar o nome desligaria o item de tudo o que já foi dito sobre ele.

**Os R$ 80,00.** Só o item que ela comprou com os complementos (origem
`orcamento`) mexe no orçamento: debita na hora, e tirar o item grava a devolução
(`Dossie.estornar`). Acrescentar o que já tinha e editar os itens da planilha
nunca mexem. A compra sugerida pelo agente continua em `registrar_compra`, pelo
portão do prato.

**Dois processos, uma despensa.** O servidor MCP que o Hermes mantém aberto e a
API da tela são processos diferentes sobre o mesmo arquivo. A despensa de agora
fica em cache pela dupla (`PRAGMA data_version`, último evento): o primeiro muda
quando outra conexão grava, o segundo quando esta grava. Qualquer mudança refaz
a despensa na leitura seguinte, e sem mudança nenhuma o objeto é o mesmo.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import unicodedata
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Final

from mise import categorias
from mise.despensa import (
    Despensa,
    Ingrediente,
    LinhaDaDespensa,
    OrigemDoItem,
    Pendencia,
    montar_despensa,
    montar_ingrediente,
)
from mise.dinheiro import Dinheiro
from mise.dossie import Canal, Dossie, LinhaDoExtrato
from mise.erros import Ausente, ErroDeUso, ErroMise, QuantidadeInvalida, UnidadeNaoNormalizavel
from mise.unidades import interpretar_unidade_compra

logger = logging.getLogger(__name__)

ESQUEMA: Final = """
CREATE TABLE IF NOT EXISTS despensa_eventos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chave       TEXT NOT NULL UNIQUE,
    item_id     TEXT NOT NULL,
    tipo        TEXT NOT NULL
                CHECK (tipo IN ('adicionar', 'corrigir', 'remover', 'restaurar')),
    dados       TEXT NOT NULL DEFAULT '{}',
    motivo      TEXT NOT NULL DEFAULT '',
    canal       TEXT NOT NULL DEFAULT 'conversa',
    desfaz      INTEGER,
    registrado  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_despensa_eventos_item ON despensa_eventos(item_id);
"""

#: O maior nome de item que ela escreve: mais que isso é texto colado por engano.
TAMANHO_DO_NOME: Final = 80

#: Campos da linha que uma correção pode trocar. O nome e o id nunca.
CAMPOS_CORRIGIVEIS: Final = frozenset(
    {"estoque", "unidade", "quantidade_comprada", "preco_pago", "categoria", "conteudo_informado"}
)


class TipoDeEvento(StrEnum):
    """O que aconteceu com o item."""

    ADICIONAR = "adicionar"
    CORRIGIR = "corrigir"
    REMOVER = "remover"
    RESTAURAR = "restaurar"


class Acao(StrEnum):
    """Como ela disse a mudança: é o que o histórico conta, em palavras dela."""

    ADICIONAR = "adicionar"
    CORRIGIR = "corrigir"
    ACABOU = "acabou"
    REMOVER = "remover"
    INFORMAR_EMBALAGEM = "informar_embalagem"
    DESFAZER = "desfazer"
    ESTORNO = "estorno"


@dataclass(frozen=True, slots=True)
class Evento:
    """Uma mudança dela na despensa, como está gravada."""

    id: int
    chave: str
    item_id: str
    tipo: TipoDeEvento
    dados: Mapping[str, Any]
    motivo: str
    canal: str
    desfaz: int | None
    registrado: datetime

    @property
    def acao(self) -> Acao:
        bruto = self.dados.get("acao") or self.tipo.value
        try:
            return Acao(bruto)
        except ValueError:
            return Acao.CORRIGIR

    @property
    def rotulo(self) -> str:
        """O id do evento na tela: `ev-0012`."""
        return rotulo_do_evento(self.id)


def rotulo_do_evento(id_: int) -> str:
    return f"ev-{id_:04d}"


def id_do_rotulo(rotulo: str) -> int:
    """`ev-0012` ou `12` → 12. Qualquer outra coisa é evento que não existe."""
    bruto = rotulo.strip().removeprefix("ev-")
    if not bruto.isdigit():
        raise Ausente("não encontrei essa mudança na despensa", evento=rotulo)
    return int(bruto)


@dataclass(frozen=True, slots=True)
class ItemNaDespensa:
    """Um item com a linha de agora, se ainda está na despensa e o que aconteceu com ele."""

    linha: LinhaDaDespensa
    ativo: bool
    eventos: tuple[Evento, ...] = ()

    @property
    def id(self) -> str:
        return self.linha.id


@dataclass(frozen=True, slots=True)
class EstadoDaDespensa:
    """A despensa de agora, com todos os itens (também os tirados) e os eventos."""

    despensa: Despensa
    itens: Mapping[str, ItemNaDespensa]
    eventos: tuple[Evento, ...] = ()
    #: Eventos gravados que não deu para aplicar (a conta de hoje recusa a linha):
    #: ficam de fora, com aviso no log, em vez de derrubar a despensa inteira.
    ignorados: tuple[int, ...] = ()

    @property
    def versao(self) -> int:
        """O id do último evento: sobe a cada mudança dela."""
        return self.eventos[-1].id if self.eventos else 0

    def item(self, id_: str) -> ItemNaDespensa | None:
        return self.itens.get(id_)

    def evento(self, id_: int) -> Evento | None:
        return next((e for e in self.eventos if e.id == id_), None)

    def desfeito_por(self, evento: Evento) -> Evento | None:
        """O evento que desfez este, se algum desfez."""
        return next((e for e in self.eventos if e.desfaz == evento.id), None)

    def pode_desfazer(self, evento: Evento) -> bool:
        """Só a última mudança de cada item se desfaz: desfazer uma antiga apagaria as novas."""
        item = self.itens.get(evento.item_id)
        return (
            item is not None
            and bool(item.eventos)
            and item.eventos[-1].id == evento.id
            and evento.id not in self.ignorados
        )


@dataclass(frozen=True, slots=True)
class Mudanca:
    """O resultado de uma mudança: o item antes e depois, e o que ela fez com os R$ 80,00."""

    evento: Evento | None
    antes: Ingrediente | None
    depois: Ingrediente | None
    pendencia_antes: Pendencia | None = None
    pendencia_depois: Pendencia | None = None
    compra: LinhaDoExtrato | None = None
    estornos: tuple[LinhaDoExtrato, ...] = ()
    #: A mesma chave de idempotência de antes: nada foi gravado de novo.
    repetida: bool = False
    item_id: str = ""
    nome: str = ""

    @property
    def mudou(self) -> bool:
        return self.evento is not None and not self.repetida

    @property
    def pendencia_resolvida(self) -> Pendencia | None:
        """A pergunta que esta mudança respondeu, se respondeu alguma."""
        if self.pendencia_antes is not None and self.pendencia_depois is None:
            return self.pendencia_antes
        return None

    @property
    def estornado(self) -> Dinheiro:
        """Quanto voltou para os complementos (positivo)."""
        return -sum((e.valor for e in self.estornos), Dinheiro.zero())


# --------------------------------------------------------------------------- #
# Serialização da linha nos eventos
# --------------------------------------------------------------------------- #


def _decimal_ou_none(valor: object) -> Decimal | None:
    if valor is None:
        return None
    try:
        return Decimal(str(valor))
    except InvalidOperation as erro:
        raise ErroDeUso("número ilegível no evento da despensa", valor=str(valor)) from erro


def _valor_para_dados(campo: str, valor: object) -> object:
    if campo == "origem" and isinstance(valor, OrigemDoItem):
        return valor.value
    if isinstance(valor, Decimal):
        return str(valor)
    return valor


def _campos_para_dados(campos: Mapping[str, object]) -> dict[str, object]:
    return {campo: _valor_para_dados(campo, valor) for campo, valor in campos.items()}


def _campos_dos_dados(dados: Mapping[str, object]) -> dict[str, object]:
    """Os campos de uma correção de volta aos tipos da linha. Campo desconhecido é ignorado."""
    campos: dict[str, object] = {}
    for campo, valor in dados.items():
        if campo not in CAMPOS_CORRIGIVEIS:
            continue
        if campo in ("estoque", "quantidade_comprada"):
            convertido = _decimal_ou_none(valor)
            if convertido is None:
                raise ErroDeUso("quantidade ausente no evento da despensa", campo=campo)
            campos[campo] = convertido
        elif campo == "preco_pago":
            campos[campo] = _decimal_ou_none(valor)
        elif campo == "conteudo_informado":
            campos[campo] = bool(valor)
        else:
            campos[campo] = str(valor)
    return campos


def _linha_para_dados(linha: LinhaDaDespensa) -> dict[str, object]:
    return {
        "nome": linha.nome,
        "estoque": str(linha.estoque),
        "unidade": linha.unidade,
        "quantidade_comprada": str(linha.quantidade_comprada),
        "preco_pago": str(linha.preco_pago) if linha.preco_pago is not None else None,
        "categoria": linha.categoria,
        "origem": linha.origem.value,
        "conteudo_informado": linha.conteudo_informado,
    }


def _linha_dos_dados(item_id: str, dados: Mapping[str, Any]) -> LinhaDaDespensa:
    campos = _campos_dos_dados(dados)
    return LinhaDaDespensa(
        nome=str(dados["nome"]),
        estoque=Decimal(str(dados["estoque"])),
        unidade=str(dados["unidade"]),
        quantidade_comprada=Decimal(str(dados["quantidade_comprada"])),
        preco_pago=_decimal_ou_none(dados.get("preco_pago")),
        id=item_id,
        categoria=str(campos.get("categoria", "")),
        origem=OrigemDoItem(dados.get("origem", OrigemDoItem.JA_TINHA.value)),
        conteudo_informado=bool(dados.get("conteudo_informado", False)),
    )


def _para_evento(linha: sqlite3.Row) -> Evento:
    return Evento(
        id=int(linha["id"]),
        chave=linha["chave"],
        item_id=linha["item_id"],
        tipo=TipoDeEvento(linha["tipo"]),
        dados=json.loads(linha["dados"]),
        motivo=linha["motivo"],
        canal=linha["canal"],
        desfaz=linha["desfaz"],
        registrado=datetime.fromisoformat(linha["registrado"]),
    )


# --------------------------------------------------------------------------- #
# Reconstrução: a planilha com os eventos aplicados
# --------------------------------------------------------------------------- #


def chave_do_nome(nome: str) -> str:
    """O nome para comparar: sem acento, sem caixa e com um espaço só."""
    decomposto = unicodedata.normalize("NFKD", nome)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return " ".join(sem_acento.casefold().split())


@dataclass(slots=True)
class _Rascunho:
    linha: LinhaDaDespensa
    ativo: bool = True
    eventos: list[Evento] = field(default_factory=list)


def _aplicar(rascunhos: dict[str, _Rascunho], evento: Evento) -> None:
    """Aplica um evento aos itens. Levanta se o evento não cabe no estado de agora."""
    atual = rascunhos.get(evento.item_id)
    ativos = {chave_do_nome(r.linha.nome) for r in rascunhos.values() if r.ativo}
    if evento.tipo is TipoDeEvento.ADICIONAR:
        if atual is not None:
            raise ErroDeUso("o item já existe", item=evento.item_id)
        linha = _linha_dos_dados(evento.item_id, evento.dados["linha"])
        if chave_do_nome(linha.nome) in ativos:
            raise ErroDeUso("já há um item com esse nome", item=evento.item_id)
        montar_ingrediente(linha)
        rascunhos[evento.item_id] = _Rascunho(linha, eventos=[evento])
        return
    if atual is None:
        raise ErroDeUso("o item não existe", item=evento.item_id)
    if evento.tipo is TipoDeEvento.CORRIGIR:
        if not atual.ativo:
            raise ErroDeUso("o item foi tirado da despensa", item=evento.item_id)
        linha = atual.linha.com(**_campos_dos_dados(evento.dados.get("campos", {})))
        montar_ingrediente(linha)
        atual.linha = linha
    elif evento.tipo is TipoDeEvento.REMOVER:
        if not atual.ativo:
            raise ErroDeUso("o item já tinha sido tirado", item=evento.item_id)
        atual.ativo = False
    else:  # RESTAURAR
        if atual.ativo:
            raise ErroDeUso("o item já está na despensa", item=evento.item_id)
        if chave_do_nome(atual.linha.nome) in ativos:
            raise ErroDeUso("já há outro item com esse nome", item=evento.item_id)
        atual.ativo = True
    atual.eventos.append(evento)


def reconstruir(planilha: Despensa, eventos: Sequence[Evento]) -> EstadoDaDespensa:
    """A despensa de agora: os itens da planilha, com os eventos aplicados em ordem.

    Sem evento nenhum, a despensa de agora é a própria planilha, o mesmo objeto.
    Um evento que a conta de hoje recusa fica de fora, com aviso, e o resto da
    despensa continua de pé.
    """
    rascunhos = {item.id: _Rascunho(item.linha) for item in planilha}
    if not eventos:
        itens = {id_: ItemNaDespensa(r.linha, ativo=True) for id_, r in rascunhos.items()}
        return EstadoDaDespensa(despensa=planilha, itens=itens)

    ignorados: list[int] = []
    for evento in eventos:
        try:
            _aplicar(rascunhos, evento)
        except (ErroMise, KeyError, ValueError) as erro:
            ignorados.append(evento.id)
            logger.warning("evento %s da despensa ignorado: %s", evento.rotulo, erro)

    ativos = [r.linha for r in rascunhos.values() if r.ativo]
    despensa = montar_despensa(ativos, origem=planilha.origem)
    itens = {
        id_: ItemNaDespensa(r.linha, r.ativo, tuple(r.eventos)) for id_, r in rascunhos.items()
    }
    return EstadoDaDespensa(
        despensa=despensa, itens=itens, eventos=tuple(eventos), ignorados=tuple(ignorados)
    )


# --------------------------------------------------------------------------- #
# A despensa editável
# --------------------------------------------------------------------------- #


def _texto_limpo(texto: str) -> str:
    return " ".join(texto.split())


def _exigir_unidade(unidade: str) -> str:
    """A unidade que ela escreveu, se a conta sabe ler; senão, um erro que diz como escrever."""
    limpa = _texto_limpo(unidade)
    try:
        interpretar_unidade_compra(limpa)
    except (UnidadeNaoNormalizavel, QuantidadeInvalida) as erro:
        raise ErroDeUso(
            f"não entendi a unidade {limpa!r}: use kg, g, L, ml, un, ou a embalagem com o "
            "peso, como 'pacote 500 g'",
            unidade=limpa,
        ) from erro
    return limpa


def _positivo_ou_zero(valor: Decimal | None, contexto: str) -> Decimal | None:
    if valor is None:
        return None
    if not valor.is_finite() or valor < 0:
        raise ErroDeUso(f"{contexto} não pode ser negativo", valor=str(valor))
    return valor


#: O que vem na embalagem, como ela diz: "1 kg", "400g", "1,5 litro", "500 ml".
_CONTEUDO: Final = re.compile(
    r"^\s*(?P<num>\d+(?:[.,]\d+)?)\s*(?P<sym>kg|quilos?|g|gramas?|mg|ml|l|litros?)\s*$",
    re.IGNORECASE,
)

#: O símbolo com que cada forma escrita entra no rótulo da unidade.
_SIMBOLO: Final[dict[str, str]] = {
    "kg": "kg",
    "quilo": "kg",
    "quilos": "kg",
    "g": "g",
    "grama": "g",
    "gramas": "g",
    "mg": "mg",
    "ml": "ml",
    "l": "L",
    "litro": "L",
    "litros": "L",
}

#: O conteúdo já escrito num rótulo de embalagem ("un 400g" → "400g").
_CONTEUDO_NO_ROTULO: Final = re.compile(r"\d+(?:[.,]\d+)?\s*(?:kg|mg|g|ml|l)\b", re.IGNORECASE)


def unidade_com_conteudo(unidade: str, conteudo: str) -> str:
    """A unidade da embalagem com o peso que ela informou: ("un", "1 kg") → "un 1kg".

    O que vem na embalagem tem de ser massa ou volume ("400 g", "1 kg", "500 ml").
    Um conteúdo que já estava no rótulo é trocado pelo novo. Item medido direto
    em peso ou volume ("kg", "L") não tem embalagem a informar.
    """
    achado = _CONTEUDO.match(conteudo)
    if achado is None:
        raise ErroDeUso(
            "diga quanto vem na embalagem em gramas, quilos, mililitros ou litros, "
            "como '400 g' ou '1 kg'",
            conteudo=conteudo,
        )
    numero = Decimal(achado.group("num").replace(",", "."))
    if numero <= 0:
        raise ErroDeUso("a embalagem precisa ter mais que zero", conteudo=conteudo)
    base = unidade.strip()
    if base.lower() in {"kg", "g", "mg", "l", "ml"}:
        raise ErroDeUso(
            "esse item já é medido direto em peso ou volume; corrija a quantidade", unidade=unidade
        )
    base = " ".join(_CONTEUDO_NO_ROTULO.sub(" ", base).split()) or "un"
    simbolo = _SIMBOLO[achado.group("sym").lower()]
    return f"{base} {achado.group('num').replace('.', ',')}{simbolo}"


class DespensaEditavel:
    """A planilha mais os eventos dela, no dossiê. Uma por sessão."""

    def __init__(self, dossie: Dossie, planilha: Despensa) -> None:
        self.dossie = dossie
        self.planilha = planilha
        self._cache: EstadoDaDespensa | None = None
        self._chave_do_cache: tuple[int, int] | None = None
        dossie.garantir_esquema(ESQUEMA)

    # -- leitura --------------------------------------------------------- #

    def estado(self) -> EstadoDaDespensa:
        """A despensa de agora, refeita só quando algum processo gravou algo.

        Tudo sob a trava do dossiê (o `cursor()` segura a mesma trava que as
        escritas): conferir a versão e refazer não se intercalam com uma escrita
        desta conexão, em nenhuma thread.
        """
        with self.dossie.cursor() as cur:
            versao_do_banco = int(cur.execute("PRAGMA data_version").fetchone()[0])
            ultimo = int(
                cur.execute("SELECT COALESCE(MAX(id), 0) FROM despensa_eventos").fetchone()[0]
            )
            chave = (versao_do_banco, ultimo)
            if self._cache is not None and chave == self._chave_do_cache:
                return self._cache
            linhas = cur.execute(
                "SELECT * FROM despensa_eventos WHERE id <= ? ORDER BY id", (ultimo,)
            ).fetchall()
            self._cache = reconstruir(self.planilha, [_para_evento(linha) for linha in linhas])
            self._chave_do_cache = chave
            return self._cache

    @property
    def despensa(self) -> Despensa:
        return self.estado().despensa

    def recarregar(self) -> None:
        """Esquece a despensa em cache: a próxima leitura refaz, do dossiê.

        Para quando as mudanças dela saem todas de uma vez ("Restaurar os
        dados"): nesta conexão, o `data_version` não muda com a própria escrita.
        """
        with self.dossie.cursor():
            self._cache = None
            self._chave_do_cache = None

    def item(self, id_: str) -> Ingrediente:
        """O item de agora pelo id; `Ausente` se não existe ou foi tirado."""
        ingrediente = self.despensa.por_id(id_)
        if ingrediente is None:
            raise Ausente("não encontrei esse ingrediente na despensa", id=id_)
        return ingrediente

    def eventos(self) -> tuple[Evento, ...]:
        return self.estado().eventos

    # -- escrita ---------------------------------------------------------- #

    @contextmanager
    def _escrevendo(self) -> Iterator[sqlite3.Cursor]:
        """A transação de uma escrita. Se ela não se confirma, o cache não fica com o que voltou.

        A leitura feita no meio da escrita (o item de depois) enxerga o evento
        ainda não confirmado; se a transação desfaz, o id do evento pode ser
        reaproveitado por outro, e o cache com a chave antiga mentiria.
        """
        try:
            with self.dossie.transacao() as cur:
                yield cur
        except BaseException:
            self._cache = None
            self._chave_do_cache = None
            raise

    def adicionar(
        self,
        *,
        nome: str,
        estoque: Decimal,
        unidade: str,
        quantidade_comprada: Decimal | None = None,
        preco_pago: Decimal | None = None,
        origem: OrigemDoItem = OrigemDoItem.JA_TINHA,
        categoria: str | None = None,
        prato: str | None = None,
        motivo: str = "",
        chave: str | None = None,
        canal: Canal = Canal.CONVERSA,
    ) -> Mudanca:
        """Acrescenta um item que ela tem. Comprado com os complementos, debita agora.

        `origem` é `ja_tinha` (não mexe nos R$ 80,00) ou `orcamento` (ela comprou
        com eles: o valor sai na hora, e tirar o item devolve). Item da planilha
        não se acrescenta: já está lá. O nome não pode repetir o de um item que
        está na despensa (a correção é pelo item que já existe).
        """
        limpo, comprado = _validar_item_novo(
            nome,
            estoque,
            quantidade_comprada=quantidade_comprada,
            preco_pago=preco_pago,
            origem=origem,
            categoria=categoria,
        )
        chave_evento = self._chave(chave)
        with self._escrevendo() as cur:
            repetido = self._repetido(cur, chave_evento, TipoDeEvento.ADICIONAR, nome=limpo)
            if repetido is not None:
                return repetido
            estado = self.estado()
            existente = _ativo_pelo_nome(estado, limpo)
            if existente is not None:
                raise ErroDeUso(
                    f"{existente.linha.nome} já está na despensa; corrija o item em vez de "
                    "acrescentar outro",
                    id=existente.id,
                )
            item_id = self._novo_id(estado)
            linha = LinhaDaDespensa(
                nome=limpo,
                estoque=estoque,
                unidade=_exigir_unidade(unidade),
                quantidade_comprada=comprado,
                preco_pago=preco_pago,
                id=item_id,
                categoria=categoria or "",
                origem=origem,
            )
            _, pendencia = montar_ingrediente(linha)
            compra = None
            if origem is OrigemDoItem.ORCAMENTO:
                assert preco_pago is not None
                para = f", para {_texto_limpo(prato)}" if prato and prato.strip() else ""
                compra = self.dossie.debitar_item(
                    item_id,
                    f"{limpo} (despensa{para})",
                    Dinheiro(preco_pago),
                    chave=f"despensa:{chave_evento}",
                    canal=canal,
                )
            dados: dict[str, object] = {
                "acao": Acao.ADICIONAR.value,
                "linha": _linha_para_dados(linha),
            }
            if compra is not None:
                dados["compra_id"] = compra.id
            if prato and prato.strip():
                dados["prato"] = _texto_limpo(prato)
            evento = self._gravar(
                cur,
                chave=chave_evento,
                item_id=item_id,
                tipo=TipoDeEvento.ADICIONAR,
                dados=dados,
                motivo=motivo,
                canal=canal,
            )
        depois = self.estado().despensa.por_id(item_id)
        return Mudanca(
            evento=evento,
            antes=None,
            depois=depois,
            pendencia_depois=pendencia,
            compra=compra,
            item_id=item_id,
            nome=limpo,
        )

    def corrigir(
        self,
        item_id: str,
        *,
        estoque: Decimal | None = None,
        unidade: str | None = None,
        quantidade_comprada: Decimal | None = None,
        preco_pago: Decimal | None = None,
        categoria: str | None = None,
        conteudo_da_embalagem: str | None = None,
        acao: Acao = Acao.CORRIGIR,
        motivo: str = "",
        chave: str | None = None,
        canal: Canal = Canal.CONVERSA,
    ) -> Mudanca:
        """Corrige o que ela tem, a unidade, quanto comprou ou pagou, ou a categoria.

        O nome não muda. Informar o peso da embalagem (`conteudo_da_embalagem`)
        troca a unidade por uma que a conta lê e marca a confiança como média.
        Item da planilha ou que ela já tinha: nada nos R$ 80,00. Item comprado
        com os complementos com o preço corrigido: a compra antiga volta e a
        nova sai, na mesma transação. Nada mudou, nada é gravado.
        """
        _positivo_ou_zero(estoque, "o estoque")
        _positivo_ou_zero(preco_pago, "o preço")
        if quantidade_comprada is not None and quantidade_comprada <= 0:
            raise ErroDeUso("a quantidade comprada precisa ser maior que zero")
        pedidos: dict[str, object] = {}
        if estoque is not None:
            pedidos["estoque"] = estoque
        if quantidade_comprada is not None:
            pedidos["quantidade_comprada"] = quantidade_comprada
        if preco_pago is not None:
            pedidos["preco_pago"] = preco_pago
        if categoria is not None:
            _exigir_categoria(categoria)
            pedidos["categoria"] = categoria
        if unidade is not None and _texto_limpo(unidade):
            pedidos["unidade"] = _exigir_unidade(unidade)
        tem_conteudo = conteudo_da_embalagem is not None and bool(conteudo_da_embalagem.strip())
        if not pedidos and not tem_conteudo:
            raise ErroDeUso(
                "diga o que mudou: o estoque, a unidade, quanto comprou, quanto pagou, a "
                "categoria ou quanto vem na embalagem"
            )

        chave_evento = self._chave(chave)
        with self._escrevendo() as cur:
            repetido = self._repetido(cur, chave_evento, TipoDeEvento.CORRIGIR, item_id=item_id)
            if repetido is not None:
                return repetido
            estado = self.estado()
            atual = self._ativo(estado, item_id)
            if tem_conteudo:
                assert conteudo_da_embalagem is not None
                base = str(pedidos.get("unidade", atual.linha.unidade))
                pedidos["unidade"] = unidade_com_conteudo(base, conteudo_da_embalagem)
                pedidos["conteudo_informado"] = True
            return self._corrigir(
                cur,
                estado,
                atual,
                pedidos,
                acao=acao,
                motivo=motivo,
                chave=chave_evento,
                canal=canal,
            )

    def acabou(
        self,
        item_id: str,
        *,
        motivo: str = "",
        chave: str | None = None,
        canal: Canal = Canal.CONVERSA,
    ) -> Mudanca:
        """O item acabou: estoque zero. Continua na despensa, com o preço que ela pagou."""
        return self.corrigir(
            item_id, estoque=Decimal(0), acao=Acao.ACABOU, motivo=motivo, chave=chave, canal=canal
        )

    def informar_embalagem(
        self,
        item_id: str,
        conteudo: str,
        *,
        motivo: str = "",
        chave: str | None = None,
        canal: Canal = Canal.CONVERSA,
    ) -> Mudanca:
        """Quanto vem na embalagem: a pendência da cobertura de chocolate se resolve aqui."""
        if not conteudo.strip():
            raise ErroDeUso("diga quanto vem na embalagem, como '1 kg' ou '400 g'")
        return self.corrigir(
            item_id,
            conteudo_da_embalagem=conteudo,
            acao=Acao.INFORMAR_EMBALAGEM,
            motivo=motivo,
            chave=chave,
            canal=canal,
        )

    def remover(
        self,
        item_id: str,
        *,
        motivo: str = "",
        chave: str | None = None,
        canal: Canal = Canal.CONVERSA,
    ) -> Mudanca:
        """Tira o item da despensa. Se ela o comprou com os complementos, o valor volta."""
        chave_evento = self._chave(chave)
        with self._escrevendo() as cur:
            repetido = self._repetido(cur, chave_evento, TipoDeEvento.REMOVER, item_id=item_id)
            if repetido is not None:
                return repetido
            estado = self.estado()
            atual = self._ativo(estado, item_id)
            return self._remover(
                cur,
                estado,
                atual,
                acao=Acao.REMOVER,
                motivo=motivo,
                chave=chave_evento,
                canal=canal,
            )

    def desfazer(
        self, evento_id: int, *, chave: str | None = None, canal: Canal = Canal.CONVERSA
    ) -> Mudanca:
        """Desfaz a última mudança de um item, com um evento novo que aponta para ela.

        Acrescentar se desfaz tirando (e devolvendo o valor, se foi comprado com os
        complementos); corrigir, voltando os valores de antes; tirar, trazendo de
        volta (e debitando de novo o que tinha sido devolvido). Desfazer de novo o
        mesmo evento devolve o que já foi feito.
        """
        chave_evento = self._chave(chave)
        with self._escrevendo() as cur:
            estado = self.estado()
            alvo = estado.evento(evento_id)
            if alvo is None:
                raise Ausente("não encontrei essa mudança na despensa", evento=evento_id)
            ja = estado.desfeito_por(alvo)
            if ja is not None:
                return self._mudanca_repetida(ja)
            repetido = self._repetido(cur, chave_evento, None, item_id=alvo.item_id)
            if repetido is not None:
                return repetido
            if not estado.pode_desfazer(alvo):
                raise ErroDeUso(
                    "só dá para desfazer a última mudança deste item", evento=alvo.rotulo
                )
            item = estado.itens[alvo.item_id]
            if alvo.tipo in (TipoDeEvento.ADICIONAR, TipoDeEvento.RESTAURAR):
                return self._remover(
                    cur,
                    estado,
                    item,
                    acao=Acao.DESFAZER,
                    motivo="",
                    chave=chave_evento,
                    canal=canal,
                    desfaz=alvo.id,
                )
            if alvo.tipo is TipoDeEvento.CORRIGIR:
                antes = _campos_dos_dados(alvo.dados.get("antes", {}))
                return self._corrigir(
                    cur,
                    estado,
                    item,
                    dict(antes),
                    acao=Acao.DESFAZER,
                    motivo="",
                    chave=chave_evento,
                    canal=canal,
                    desfaz=alvo.id,
                )
            return self._restaurar(cur, estado, item, alvo, chave=chave_evento, canal=canal)

    def estornar_compra(
        self, compra_id: int, *, canal: Canal = Canal.TELA
    ) -> tuple[LinhaDoExtrato, Mudanca | None]:
        """Devolve uma compra aos R$ 80,00. Se ela acrescentou um item, o item sai junto.

        O item comprado com os complementos só existe porque o dinheiro saiu:
        devolvido o dinheiro, o item deixa a despensa (e desfazer traz os dois de
        volta). Compra feita para um prato, pelo agente, só volta ao orçamento.
        """
        with self._escrevendo() as cur:
            estorno = self.dossie.estornar(compra_id, canal=canal)
            if estorno.item_id is None:
                return estorno, None
            estado = self.estado()
            item = estado.item(estorno.item_id)
            if item is None or not item.ativo or self.dossie.compras_do_item(item.id):
                return estorno, None
            mudanca = self._remover(
                cur,
                estado,
                item,
                acao=Acao.ESTORNO,
                motivo="",
                chave=self._chave(None),
                canal=canal,
                ja_estornadas=(estorno,),
            )
        return estorno, mudanca

    # -- por dentro ------------------------------------------------------- #

    def _corrigir(
        self,
        cur: sqlite3.Cursor,
        estado: EstadoDaDespensa,
        atual: ItemNaDespensa,
        pedidos: Mapping[str, object],
        *,
        acao: Acao,
        motivo: str,
        chave: str,
        canal: Canal,
        desfaz: int | None = None,
    ) -> Mudanca:
        antes_linha = atual.linha
        campos = {
            campo: valor
            for campo, valor in pedidos.items()
            if campo in CAMPOS_CORRIGIVEIS and getattr(antes_linha, campo) != valor
        }
        ingrediente_antes = estado.despensa.por_id(atual.id)
        pendencia_antes = (
            estado.despensa.pendencia_de(antes_linha.nome) if ingrediente_antes else None
        )
        if not campos:
            return Mudanca(
                evento=None,
                antes=ingrediente_antes,
                depois=ingrediente_antes,
                pendencia_antes=pendencia_antes,
                pendencia_depois=pendencia_antes,
                item_id=atual.id,
                nome=antes_linha.nome,
            )
        depois_linha = antes_linha.com(**campos)
        _, pendencia_depois = montar_ingrediente(depois_linha)

        estornos: tuple[LinhaDoExtrato, ...] = ()
        compra = None
        mexe_no_dinheiro = (
            antes_linha.origem is OrigemDoItem.ORCAMENTO
            and depois_linha.preco_pago != antes_linha.preco_pago
        )
        if mexe_no_dinheiro:
            if depois_linha.preco_pago is None or depois_linha.preco_pago <= 0:
                raise ErroDeUso("o que foi comprado com os complementos precisa do valor pago")
            estornos = tuple(
                self.dossie.estornar(c.id, canal=canal)
                for c in self.dossie.compras_do_item(atual.id)
            )
            compra = self.dossie.debitar_item(
                atual.id,
                f"{antes_linha.nome} (despensa, valor corrigido)",
                Dinheiro(depois_linha.preco_pago),
                chave=f"despensa:{chave}",
                canal=canal,
            )
        dados: dict[str, object] = {
            "acao": acao.value,
            "campos": _campos_para_dados(campos),
            "antes": _campos_para_dados({c: getattr(antes_linha, c) for c in campos}),
        }
        if estornos:
            dados["estornos"] = [e.id for e in estornos]
        if compra is not None:
            dados["compra_id"] = compra.id
        evento = self._gravar(
            cur,
            chave=chave,
            item_id=atual.id,
            tipo=TipoDeEvento.CORRIGIR,
            dados=dados,
            motivo=motivo,
            canal=canal,
            desfaz=desfaz,
        )
        depois = self.estado().despensa.por_id(atual.id)
        return Mudanca(
            evento=evento,
            antes=ingrediente_antes,
            depois=depois,
            pendencia_antes=pendencia_antes,
            pendencia_depois=pendencia_depois,
            compra=compra,
            estornos=estornos,
            item_id=atual.id,
            nome=antes_linha.nome,
        )

    def _remover(
        self,
        cur: sqlite3.Cursor,
        estado: EstadoDaDespensa,
        atual: ItemNaDespensa,
        *,
        acao: Acao,
        motivo: str,
        chave: str,
        canal: Canal,
        desfaz: int | None = None,
        ja_estornadas: tuple[LinhaDoExtrato, ...] = (),
    ) -> Mudanca:
        if not atual.ativo:
            raise Ausente("esse ingrediente já não está na despensa", id=atual.id)
        antes = estado.despensa.por_id(atual.id)
        estornos = ja_estornadas + tuple(
            self.dossie.estornar(c.id, canal=canal) for c in self.dossie.compras_do_item(atual.id)
        )
        dados: dict[str, object] = {"acao": acao.value}
        if estornos:
            dados["estornos"] = [e.id for e in estornos]
        evento = self._gravar(
            cur,
            chave=chave,
            item_id=atual.id,
            tipo=TipoDeEvento.REMOVER,
            dados=dados,
            motivo=motivo,
            canal=canal,
            desfaz=desfaz,
        )
        return Mudanca(
            evento=evento,
            antes=antes,
            depois=None,
            pendencia_antes=estado.despensa.pendencia_de(atual.linha.nome) if antes else None,
            estornos=estornos,
            item_id=atual.id,
            nome=atual.linha.nome,
        )

    def _restaurar(
        self,
        cur: sqlite3.Cursor,
        estado: EstadoDaDespensa,
        item: ItemNaDespensa,
        alvo: Evento,
        *,
        chave: str,
        canal: Canal,
    ) -> Mudanca:
        if item.ativo:
            raise ErroDeUso("esse ingrediente já está na despensa", id=item.id)
        outro = _ativo_pelo_nome(estado, item.linha.nome)
        if outro is not None:
            raise ErroDeUso(
                f"já há outro {item.linha.nome} na despensa; tire aquele antes", id=outro.id
            )
        compra = None
        if alvo.dados.get("estornos") and item.linha.origem is OrigemDoItem.ORCAMENTO:
            assert item.linha.preco_pago is not None
            compra = self.dossie.debitar_item(
                item.id,
                f"{item.linha.nome} (despensa, de volta)",
                Dinheiro(item.linha.preco_pago),
                chave=f"despensa:{chave}",
                canal=canal,
            )
        dados: dict[str, object] = {"acao": Acao.DESFAZER.value}
        if compra is not None:
            dados["compra_id"] = compra.id
        evento = self._gravar(
            cur,
            chave=chave,
            item_id=item.id,
            tipo=TipoDeEvento.RESTAURAR,
            dados=dados,
            motivo="",
            canal=canal,
            desfaz=alvo.id,
        )
        depois_estado = self.estado()
        depois = depois_estado.despensa.por_id(item.id)
        return Mudanca(
            evento=evento,
            antes=None,
            depois=depois,
            pendencia_depois=depois_estado.despensa.pendencia_de(item.linha.nome),
            compra=compra,
            item_id=item.id,
            nome=item.linha.nome,
        )

    def _gravar(
        self,
        cur: sqlite3.Cursor,
        *,
        chave: str,
        item_id: str,
        tipo: TipoDeEvento,
        dados: Mapping[str, object],
        motivo: str,
        canal: Canal,
        desfaz: int | None = None,
    ) -> Evento:
        cur.execute(
            "INSERT INTO despensa_eventos (chave, item_id, tipo, dados, motivo, canal, desfaz, "
            "registrado) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                chave,
                item_id,
                tipo.value,
                json.dumps(dados, ensure_ascii=False),
                _texto_limpo(motivo)[:300],
                Canal(canal).value,
                desfaz,
                self.dossie.agora().isoformat(),
            ),
        )
        linha = cur.execute(
            "SELECT * FROM despensa_eventos WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _para_evento(linha)

    def _chave(self, chave: str | None) -> str:
        """A chave do evento: a de idempotência de quem chamou, prefixada, ou uma nova."""
        if chave is not None and chave.strip():
            return f"cliente:{chave.strip()}"
        return f"evento:{uuid.uuid4().hex}"

    def _repetido(
        self,
        cur: sqlite3.Cursor,
        chave: str,
        tipo: TipoDeEvento | None,
        *,
        item_id: str | None = None,
        nome: str | None = None,
    ) -> Mudanca | None:
        """A mudança que esta chave já gravou, ou `None`. A mesma chave para outra coisa é erro."""
        linha = cur.execute("SELECT * FROM despensa_eventos WHERE chave = ?", (chave,)).fetchone()
        if linha is None:
            return None
        evento = _para_evento(linha)
        mesma = (tipo is None or evento.tipo is tipo) and (
            (item_id is not None and evento.item_id == item_id)
            or (
                nome is not None
                and chave_do_nome(str(evento.dados.get("linha", {}).get("nome", "")))
                == chave_do_nome(nome)
            )
        )
        if not mesma:
            raise ErroDeUso("essa chave já registrou outra mudança na despensa", chave=chave)
        return self._mudanca_repetida(evento)

    def _mudanca_repetida(self, evento: Evento) -> Mudanca:
        estado = self.estado()
        item = estado.itens.get(evento.item_id)
        depois = estado.despensa.por_id(evento.item_id)
        compra_id = evento.dados.get("compra_id")
        compra = self.dossie.compra(int(compra_id)) if isinstance(compra_id, int) else None
        estornos = tuple(
            linha
            for id_ in evento.dados.get("estornos", [])
            if isinstance(id_, int) and (linha := self.dossie.compra(id_)) is not None
        )
        return Mudanca(
            evento=evento,
            antes=None,
            depois=depois,
            pendencia_depois=estado.despensa.pendencia_de(item.linha.nome) if item else None,
            compra=compra,
            estornos=estornos,
            repetida=True,
            item_id=evento.item_id,
            nome=item.linha.nome if item else "",
        )

    def _ativo(self, estado: EstadoDaDespensa, item_id: str) -> ItemNaDespensa:
        item = estado.item(item_id)
        if item is None or not item.ativo:
            raise Ausente("não encontrei esse ingrediente na despensa", id=item_id)
        return item

    def _novo_id(self, estado: EstadoDaDespensa) -> str:
        while True:
            candidato = f"item-{uuid.uuid4().hex[:8]}"
            if candidato not in estado.itens:
                return candidato


def _exigir_categoria(categoria: str) -> None:
    if not categorias.valida(categoria):
        raise ErroDeUso(
            "categoria desconhecida",
            categoria=categoria,
            validas=", ".join(c.id for c in categorias.CATEGORIAS),
        )


def _validar_item_novo(
    nome: str,
    estoque: Decimal,
    *,
    quantidade_comprada: Decimal | None,
    preco_pago: Decimal | None,
    origem: OrigemDoItem,
    categoria: str | None,
) -> tuple[str, Decimal]:
    """O nome limpo e a quantidade comprada de um item novo, ou o erro que ela entende."""
    limpo = _texto_limpo(nome)
    if not limpo:
        raise ErroDeUso("diga o nome do ingrediente")
    if len(limpo) > TAMANHO_DO_NOME:
        raise ErroDeUso("nome de ingrediente longo demais", tamanho=len(limpo))
    if origem is OrigemDoItem.PLANILHA:
        raise ErroDeUso("item novo é 'ja_tinha' ou 'orcamento'; a planilha não muda")
    _positivo_ou_zero(estoque, "o estoque")
    _positivo_ou_zero(preco_pago, "o preço")
    if origem is OrigemDoItem.ORCAMENTO and (preco_pago is None or preco_pago <= 0):
        raise ErroDeUso("para comprar com os complementos, diga quanto a senhora pagou")
    if quantidade_comprada is not None and quantidade_comprada <= 0:
        raise ErroDeUso("a quantidade comprada precisa ser maior que zero")
    if preco_pago is not None and quantidade_comprada is None and estoque <= 0:
        raise ErroDeUso("diga quanto a senhora comprou por esse preço")
    if categoria is not None:
        _exigir_categoria(categoria)
    # Sem dizer quanto comprou, ela comprou o que tem. Sem preço, a quantidade
    # comprada não entra em conta nenhuma, e uma unidade basta.
    return limpo, quantidade_comprada or (estoque if estoque > 0 else Decimal(1))


def _ativo_pelo_nome(estado: EstadoDaDespensa, nome: str) -> ItemNaDespensa | None:
    alvo = chave_do_nome(nome)
    return next(
        (i for i in estado.itens.values() if i.ativo and chave_do_nome(i.linha.nome) == alvo),
        None,
    )


def linha_do_evento(evento: Evento) -> LinhaDaDespensa:
    """A linha que um evento `adicionar` gravou."""
    return _linha_dos_dados(evento.item_id, evento.dados["linha"])


__all__ = [
    "CAMPOS_CORRIGIVEIS",
    "ESQUEMA",
    "TAMANHO_DO_NOME",
    "Acao",
    "DespensaEditavel",
    "EstadoDaDespensa",
    "Evento",
    "ItemNaDespensa",
    "Mudanca",
    "TipoDeEvento",
    "chave_do_nome",
    "id_do_rotulo",
    "linha_do_evento",
    "reconstruir",
    "rotulo_do_evento",
    "unidade_com_conteudo",
]
