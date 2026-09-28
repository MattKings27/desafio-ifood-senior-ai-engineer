"""Avaliação do portão de viabilidade contra o dataset dourado.

A diferença entre isto e os testes unitários: os testes verificam unidades; este
avalia **a decisão**, que é o produto. Cada caso é uma afirmação sobre o que o
sistema deve decidir, escrita em YAML para poder ser lida por quem não lê Python,
inclusive por quem escreveu o enunciado.

Roda como portão do CI. Um caso que falha aqui não é um teste quebrado: é o
sistema decidindo diferente do que combinamos.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

import yaml
from mise.despensa import Despensa, carregar_despensa
from mise.dinheiro import Dinheiro
from mise.perfil import Gosto, PerfilCozinha, Posse
from mise.receita import IngredienteReceita, Receita
from mise.referencias import PrecosDeReferencia, ler_precos
from mise.taxonomia import EQUIPAMENTOS, EQUIPAMENTOS_POR_ID, TECNICAS
from mise.viabilidade import AjusteDoIngrediente, Avaliacao, avaliar

CASOS = Path(__file__).resolve().parents[2] / "casos"


#: Tempo por fornada, gás sobrando e litros de geladeira de cada variante do perfil completo.
_ROTINAS: Final[dict[str, tuple[int, bool, int]]] = {
    "completo": (240, True, 30),
    "completo_sem_gas": (240, False, 30),
    "completo_sem_geladeira": (240, True, 0),
    "completo_rapido": (60, True, 30),
    # Dez horas por cozinhada, como a Dona Maria disse: o tempo que a receita
    # não diz deixa de ser pergunta (`LIMITE_FOLGADO_MIN`).
    "completo_dez_horas": (600, True, 30),
}

#: O que toda cozinha tem, pela taxonomia: equipamentos e técnicas pressupostos.
_PRESSUPOSTOS: Final = frozenset(
    [e.id for e in EQUIPAMENTOS if e.pressuposto] + [t.id for t in TECNICAS if t.pressuposta]
)

#: O que muda no perfil completo, e o que ela disse ou deixou de saber.
_AJUSTES: Final[dict[str, Callable[[PerfilCozinha], PerfilCozinha]]] = {
    # O fogão é suposto em toda cozinha; aqui ela mesma disse que não tem.
    "completo_sem_fogao": lambda p: p.com_equipamento("fogao", Posse.NAO_TEM),
    # "Não sei se tenho fogão": fica em aberto, não volta a suposto.
    "completo_sem_saber_do_fogao": lambda p: p.sem_resposta("fogao"),
    "completo_sem_refogar": lambda p: p.com_tecnica("refogar", Posse.NAO_TEM),
    "completo_uma_boca": lambda p: p.com_restricao("bocas_fogao", 1),
    "completo_duas_bocas": lambda p: p.com_restricao("bocas_fogao", 2),
    "completo_sem_saber_as_bocas": lambda p: p.sem_resposta("bocas_fogao"),
    "completo_sem_saber_da_geladeira": lambda p: p.sem_resposta("espaco_geladeira_litros"),
    "completo_rapido_uma_boca": lambda p: p.com_restricao(
        "tempo_max_por_fornada_min", 60
    ).com_restricao("bocas_fogao", 1),
    # Tudo respondido, menos o que toda cozinha tem: isso ficou suposto, como
    # fica quando ninguém pergunta. O portão libera; o aceite pede a confirmação.
    "completo_basico_suposto": lambda p: replace(p, confirmados=p.confirmados - _PRESSUPOSTOS),
}


def _perfil(nome: str) -> PerfilCozinha:
    """Os perfis nomeados que os casos usam.

    Ficam aqui, e não no YAML, porque montar um perfil é código: são dezenas de
    equipamentos e técnicas. O YAML guarda a **decisão esperada**, que é o que
    precisa ser legível. Nome que não existe é erro: um perfil digitado errado
    viraria o completo em silêncio, e o caso passaria sem provar nada.
    """
    vazio = PerfilCozinha.inicial()
    sem_forno = vazio.com_equipamento("forno", Posse.NAO_TEM)
    parciais = {
        "vazio": vazio,
        # Ela disse que não tem forno; dos substitutos, ninguém perguntou ainda.
        "so_sem_forno": sem_forno,
        "sem_forno": sem_forno.com_equipamento("air_fryer", Posse.NAO_TEM).com_equipamento(
            "forno_eletrico", Posse.NAO_TEM
        ),
    }
    if nome in parciais:
        return parciais[nome]
    if nome not in _ROTINAS and nome not in _AJUSTES:
        conhecidos = sorted([*parciais, *_ROTINAS, *_AJUSTES])
        raise ValueError(f"perfil {nome!r} não existe; os que existem: {', '.join(conhecidos)}")

    completo = vazio.com_equipamentos((e, Posse.TEM) for e in vazio.equipamentos)
    completo = completo.com_tecnicas((t, Posse.TEM) for t in completo.tecnicas)
    tempo, gas, geladeira = _ROTINAS.get(nome, _ROTINAS["completo"])
    completo = (
        completo.com_restricao("bocas_fogao", 4)
        .com_restricao("porcoes_por_fornada", 20)
        .com_restricao("energia_aparelhos_simultaneos", 3)
        .com_restricao("tempo_max_por_fornada_min", tempo)
        .com_restricao("tem_gas_sobrando", gas)
        .com_restricao("espaco_geladeira_litros", geladeira)
    )
    ajuste = _AJUSTES.get(nome)
    return ajuste(completo) if ajuste is not None else completo


def _do_caso(caso: dict[str, Any]) -> PerfilCozinha:
    """O perfil nomeado do caso, com o que ela confirmou (`confirmou`) do que era suposto."""
    perfil = _perfil(caso.get("perfil", "completo"))
    for id_ in caso.get("confirmou") or ():
        perfil = (
            perfil.com_equipamento(id_, Posse.TEM)
            if id_ in EQUIPAMENTOS_POR_ID
            else perfil.com_tecnica(id_, Posse.TEM)
        )
    return perfil


def _ingrediente(bruto: dict[str, Any]) -> IngredienteReceita:
    """Uma linha do caso: já interpretada, ou (`linha`) lida pelo mesmo leitor das páginas.

    `linha` passa por `retrieval.quantidades.interpretar_linha`, que é como a
    receita da internet e a digitada são lidas: é o que prova o que a leitura
    faz com "temperos de sua preferência" ou "uva-passa (opcional)".
    """
    if "linha" in bruto:
        from retrieval.quantidades import interpretar_linha  # noqa: PLC0415

        return interpretar_linha(bruto["linha"])
    return IngredienteReceita(
        texto_original=bruto["texto"],
        nome=bruto["nome"],
        quantidade=Decimal(str(bruto["quantidade"]))
        if bruto.get("quantidade") is not None
        else None,
        medida=bruto.get("medida", ""),
        opcional=bruto.get("opcional", False),
    )


def _receita_digitada(bruta: dict[str, Any]) -> Receita:
    """A receita como o modelo a digita numa ferramenta (`ReceitaEntrada`), endereço junto."""
    from mise.mcp_server import ReceitaEntrada  # noqa: PLC0415

    return ReceitaEntrada(**bruta).para_dominio()


def _receita(bruta: dict[str, Any]) -> Receita:
    ingredientes = tuple(_ingrediente(i) for i in bruta["ingredientes"])
    return Receita(
        nome=bruta["nome"],
        ingredientes=ingredientes,
        rendimento_porcoes=bruta.get("rendimento_porcoes", 1),
        modo_preparo=tuple(bruta.get("modo_preparo", [])),
        # Os três tempos como a receita declara: preparo, cozimento e total.
        tempo_preparo_min=bruta.get("tempo_preparo_min"),
        tempo_cozimento_min=bruta.get("tempo_cozimento_min"),
        tempo_total_min=bruta.get("tempo_total_min"),
        rendimento_informado=bruta.get("rendimento_informado", True),
    ).com_exigencias_detectadas()


@dataclass(frozen=True, slots=True)
class Resultado:
    """O veredito de um caso, com o porquê quando falha."""

    nome: str
    passou: bool
    motivo: str = ""

    def __str__(self) -> str:
        marca = "ok  " if self.passou else "FALHA"
        porque = f": {self.motivo}" if self.motivo else ""
        return f"  {marca} {self.nome}{porque}"


def _referencias(despensa: Despensa) -> PrecosDeReferencia:
    """Os preços de referência ao lado da planilha, como na plataforma.

    O caso que diz `sem_precos_de_referencia` confere o caminho sem fonte nenhuma.
    """
    if despensa.origem is None:
        return PrecosDeReferencia()
    return ler_precos((Path(despensa.origem).parent / "precos_de_referencia.json").resolve())


def avaliar_caso(caso: dict[str, Any], despensa: Despensa) -> Resultado:
    """Roda um caso pelo caminho real e compara com o esperado.

    Com `resposta_dela`, o caso confere a decisão antes (`antes_da_resposta`) e
    depois do que ela respondeu: o peso de uma linha cuja medida não se
    converte, gravado pelo mesmo `responder_peso` da tela e da conversa.
    """
    orcamento = caso.get("orcamento_restante")
    precos = {k: Dinheiro.de(v) for k, v in (caso.get("precos") or {}).items()}
    referencias = (
        PrecosDeReferencia() if caso.get("sem_precos_de_referencia") else _referencias(despensa)
    )

    def conferir(receita: Receita) -> Avaliacao:
        return avaliar(
            receita,
            _do_caso(caso),
            despensa,
            orcamento_restante=Dinheiro.de(orcamento) if orcamento is not None else None,
            precos=precos or None,
            gosto=Gosto(caso.get("gosto", "desconhecido")),
            impedimento_dela=caso.get("impedimento_dela", ""),
            referencias=referencias,
        )

    receita = (
        _receita_digitada(caso["receita"])
        if caso.get("entrada") == "digitada"
        else _receita(caso["receita"])
    )
    a = conferir(receita)
    divergencias: list[str] = []
    if respostas := caso.get("resposta_dela"):
        if antes := caso.get("antes_da_resposta"):
            divergencias += [f"antes da resposta, {d}" for d in _divergencias(antes, a)]
        receita, sem_pergunta = _com_as_respostas(receita, respostas, a)
        divergencias += sem_pergunta
        a = conferir(receita)
    divergencias += _divergencias(caso["espera"], a) + _da_receita(caso["espera"], receita, a)
    divergencias += _do_custo(caso["espera"], receita, a)
    divergencias += _do_aceite(caso["espera"], receita, _do_caso(caso), a)
    return Resultado(caso["nome"], not divergencias, divergencias[0] if divergencias else "")


def _com_as_respostas(
    receita: Receita, respostas: list[dict[str, Any]], a: Avaliacao
) -> tuple[Receita, list[str]]:
    """A receita com o peso que ela disse de cada linha; só a linha que a conferência perguntou."""
    from mise.complemento import responder_peso  # noqa: PLC0415

    sem_pergunta: list[str] = []
    for resposta in respostas:
        # A pergunta de medida da linha, ou a medida de referência que ela corrige.
        pedido = next(
            (p.peso for p in a.perguntas if p.peso is not None and p.campo == resposta["linha"]),
            None,
        ) or next(
            (
                ajuste.corrigir_peso
                for ajuste in a.ajustes
                if ajuste.corrigir_peso is not None
                and ajuste.ingrediente.texto_original == resposta["linha"]
            ),
            None,
        )
        if pedido is None:
            sem_pergunta.append(f"a linha {resposta['linha']!r} não perguntava o peso")
            continue
        receita = responder_peso(
            receita,
            resposta["linha"],
            str(resposta["peso"]),
            uma=pedido.uma,
            por_unidade=resposta.get("por_unidade"),
        ).receita
    return receita, sem_pergunta


def _do_aceite(
    espera: dict[str, Any], receita: Receita, perfil: PerfilCozinha, a: Avaliacao
) -> list[str]:
    """O aceite, que pede o que toda cozinha tem confirmado por ela (`mise.certeza`).

    `aceite` é `recusado` ou `liberado`; `confirmar_a_cozinha` são os ids que a
    receita usa do suposto, na ordem da pergunta; `pergunta_do_aceite` é a
    pergunta, uma só, como ela ouve.
    """
    from mise.certeza import (  # noqa: PLC0415
        Acao,
        exigir_cozinha_confirmada,
        pergunta_de_confirmacao,
        pressupostos_da_receita,
    )
    from mise.erros import CozinhaNaoConfirmada  # noqa: PLC0415

    divergencias: list[str] = []
    itens = pressupostos_da_receita(receita, perfil)
    if "confirmar_a_cozinha" in espera and [i.id for i in itens] != espera["confirmar_a_cozinha"]:
        divergencias.append(
            f"a confirmação devia pedir {espera['confirmar_a_cozinha']}, "
            f"e pede {[i.id for i in itens]}"
        )
    if (pergunta := espera.get("pergunta_do_aceite")) and (
        not itens or pergunta_de_confirmacao(itens, Acao.ACEITAR) != pergunta
    ):
        divergencias.append(f"a pergunta do aceite devia ser {pergunta!r}")
    if aceite := espera.get("aceite"):
        try:
            exigir_cozinha_confirmada(receita, perfil, Acao.ACEITAR)
            liberado = a.permite_precificar
        except CozinhaNaoConfirmada:
            liberado = False
        if ("liberado" if liberado else "recusado") != aceite:
            divergencias.append(f"o aceite devia ser {aceite}")
    return divergencias


def _do_custo(espera: dict[str, Any], receita: Receita, a: Avaliacao) -> list[str]:
    """O custo de uma porção, quando o caso diz qual é: sai da conta de verdade (`calcular`)."""
    esperado = espera.get("custo_por_porcao")
    if esperado is None:
        return []
    if not a.permite_precificar:
        return [f"o custo devia sair ({esperado}), e a conferência não libera"]
    from mise.cmv import calcular  # noqa: PLC0415

    custo = str(calcular(receita, a).para_precificar)
    return [] if custo == esperado else [f"o custo devia ser {esperado}, e saiu {custo}"]


def _da_receita(espera: dict[str, Any], receita: Receita, a: Avaliacao) -> list[str]:
    """O que o caso diz sobre cada ingrediente e sobre a procedência da receita.

    `situacao` confere o ajuste de cada linha à despensa (`tem`, `tem_parte`,
    `falta`, `a_gosto`, `opcional`, `nao_entendi`), pelo nome do item ou pelo
    texto da linha; `opcional_listado` confere que o opcional aparece como
    opcional, e não some; `origem` e `sem_endereco` conferem que a receita
    digitada não vira receita da internet.
    """
    divergencias: list[str] = []
    ajustes: dict[str, AjusteDoIngrediente] = {}
    for ajuste in a.ajustes:
        for nome in (ajuste.ingrediente.texto_original, ajuste.ingrediente.nome):
            ajustes[nome.casefold()] = ajuste
        if ajuste.item is not None:
            ajustes[ajuste.item.nome.casefold()] = ajuste
    for nome, situacao in (espera.get("situacao") or {}).items():
        achado = ajustes.get(nome.casefold())
        if achado is None:
            divergencias.append(f"nenhuma linha da receita é {nome!r}")
        elif achado.situacao.value != situacao:
            divergencias.append(f"{nome} devia ser {situacao}, e ficou {achado.situacao.value}")
    if (opcional := espera.get("opcional_listado")) and not any(
        o.casefold() == opcional.casefold() for o in a.opcionais_de_fora
    ):
        divergencias.append(f"{opcional!r} não ficou listado como opcional")
    if (origem := espera.get("origem")) and receita.origem.value != origem:
        divergencias.append(f"a origem devia ser {origem}, e é {receita.origem.value}")
    if espera.get("sem_endereco") and receita.url:
        divergencias.append(f"a receita ficou com o endereço {receita.url!r}")
    return divergencias


def _divergencias(espera: dict[str, Any], a: Avaliacao) -> list[str]:
    """O que a decisão tem de diferente do combinado, na ordem em que se confere."""
    if a.veredito.rotulo != espera["veredito"]:
        return [f"esperava {espera['veredito']}, veio {a.veredito.rotulo}"]

    divergencias: list[str] = []
    if "permite_precificar" in espera and a.permite_precificar != espera["permite_precificar"]:
        divergencias.append(f"permite_precificar deveria ser {espera['permite_precificar']}")

    # Aviso não muda veredito: sem conferir o aviso, "uma boca só" passaria calado.
    for chave, textos, onde in (
        ("pergunta_contendo", [p.texto for p in a.perguntas], "nenhuma pergunta menciona"),
        (
            "rendimento_contendo",
            [a.rendimento.texto] if a.rendimento is not None else [],
            "o rendimento não diz",
        ),
        (
            "impedimento_contendo",
            [i.descricao for i in a.impedimentos],
            "nenhum impedimento menciona",
        ),
        ("aviso_contendo", [av.texto for av in a.avisos], "nenhum aviso menciona"),
    ):
        trecho = espera.get(chave)
        if trecho and trecho.casefold() not in " ".join(textos).casefold():
            divergencias.append(f"{onde} {trecho!r}")

    if espera.get("sem_aviso") and a.avisos:
        divergencias.append(f"não devia avisar, e avisou: {a.avisos[0].texto!r}")
    return divergencias


def _planilha() -> Path:
    """A planilha real da Dona Maria. Avaliar contra dado sintético não prova nada."""
    bruto = os.environ.get("MISE_PLANILHA")
    if bruto:
        return Path(bruto)
    return CASOS.parents[1] / "dados" / "despensa_dona_maria.xlsx"


def rodar(caminho: Path | None = None, despensa: Despensa | None = None) -> list[Resultado]:
    casos = yaml.safe_load((caminho or CASOS / "portao.yaml").read_text(encoding="utf-8"))
    pantry = despensa if despensa is not None else carregar_despensa(_planilha())
    return [avaliar_caso(c, pantry) for c in casos]


__all__ = ["Resultado", "avaliar_caso", "rodar"]
