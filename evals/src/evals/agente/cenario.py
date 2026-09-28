"""Cenários roteirizados da Dona Maria e o que o agente tem que fazer em cada um.

Um cenário é uma conversa: cada turno traz o que ela diz e o que se espera do
agente naquele turno. As expectativas são sobre a **trajetória** (quais
ferramentas, em que ordem, quais nunca) antes de serem sobre o texto, porque é
a trajetória que diz se o número veio do motor ou da cabeça do modelo.

    turnos:
      - diz: "Não tenho forno."
        espera:
          chama_em_ordem: [registrar_resposta, proxima_pergunta]
          nao_chama: [calcular_cmv]
          responde_com: ["air ?fryer"]
          pergunta: true

Os nomes das ferramentas do motor vão curtos (`calcular_cmv`); as do Hermes,
completos (`web_search`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import yaml

from evals.agente.protocolo import Chamada, Turno

#: Ferramentas que um agente de cardápio não tem por que usar. Numa
#: medição com o perfil mal configurado, o agente vasculhou a pasta pessoal e o
#: repositório atrás da planilha. Usar qualquer uma é falha em todo cenário.
FORA_DO_PAPEL: Final = frozenset(
    {
        "search_files",
        "read_file",
        "write_file",
        "patch",
        "terminal",
        "process",
        "execute_code",
        "browser_navigate",
        "browser_snapshot",
        "browser_click",
        "delegate_task",
    }
)

#: O que o guard-rail numérico deixa no lugar de um número que ele apagou. Para
#: ela, é uma resposta com o preço faltando, venha o erro do modelo ou do filtro.
MARCA_DO_GUARDRAIL = "[valor retirado]"

#: Os nomes internos do sistema: vocabulário de quem o construiu, não dela. Na
#: matriz do Opus 5 com esforço alto, 44% das respostas diziam "o motor", 37%
#: "portão" e 13% "APTO". A tela diz "dá pra fazer", "falta saber" e "não dá";
#: a conversa fala a mesma língua. Os vereditos em caixa alta contam só assim:
#: "bloqueado" minúsculo é português comum.
JARGAO_INTERNO: Final = re.compile(
    r"(?i:\bmotor\b|\bport[aã]o\b|\bveredito\b|\bCMV\b|\bfood ?cost\b)"
    r"|\bAPTO\b|\bFALTA INFO\b|\bBLOQUEADO\b"
)


class CenarioInvalido(ValueError):
    """O arquivo do cenário não descreve uma conversa verificável."""


@dataclass(frozen=True)
class ChamadaProibida:
    """Uma ferramenta proibida só com certos argumentos: aceitar, não recusar."""

    ferramenta: str
    entrada: tuple[tuple[str, str], ...]

    def casa(self, chamada: Chamada) -> bool:
        if not chamada.e(self.ferramenta):
            return False
        return all(
            str(chamada.entrada.get(chave, "")).strip().casefold() == valor.casefold()
            for chave, valor in self.entrada
        )

    def __str__(self) -> str:
        args = ", ".join(f"{k}={v}" for k, v in self.entrada)
        return f"{self.ferramenta}({args})"


@dataclass(frozen=True)
class Expectativa:
    chama_em_ordem: tuple[str, ...] = ()
    nao_chama: tuple[str, ...] = ()
    nao_chama_com: tuple[ChamadaProibida, ...] = ()
    responde_com: tuple[str, ...] = ()
    nao_responde_com: tuple[str, ...] = ()
    pergunta: bool | None = None


@dataclass(frozen=True)
class TurnoRoteirizado:
    diz: str
    espera: Expectativa


@dataclass(frozen=True)
class Cenario:
    nome: str
    secao: str
    descricao: str
    turnos: tuple[TurnoRoteirizado, ...]
    #: Ferramentas que não podem aparecer em nenhum turno da conversa.
    nunca_chama: tuple[str, ...] = ()
    #: Ordem esperada ao longo da conversa inteira, não de um turno só: quando
    #: ela já disse tudo no primeiro turno, o agente pode e deve adiantar a conta.
    chama_na_conversa: tuple[str, ...] = ()


@dataclass(frozen=True)
class Veredito:
    cenario: str
    falhas: tuple[str, ...] = field(default_factory=tuple)

    @property
    def passou(self) -> bool:
        return not self.falhas


def _lista(bruto: dict[str, Any], chave: str, onde: str) -> tuple[str, ...]:
    valor = bruto.get(chave, [])
    if not isinstance(valor, list) or not all(isinstance(v, str) for v in valor):
        raise CenarioInvalido(f"{onde}: '{chave}' tem que ser lista de textos")
    return tuple(valor)


_CHAVES_DA_EXPECTATIVA = {
    "chama_em_ordem",
    "nao_chama",
    "nao_chama_com",
    "responde_com",
    "nao_responde_com",
    "pergunta",
}


def _expectativa(bruto: Any, onde: str) -> Expectativa:
    if bruto is None:
        return Expectativa()
    if not isinstance(bruto, dict):
        raise CenarioInvalido(f"{onde}: 'espera' tem que ser um mapa")
    desconhecidas = set(bruto) - _CHAVES_DA_EXPECTATIVA
    if desconhecidas:
        # Chave com erro de digitação vira expectativa que nunca é conferida, e
        # o cenário passa por não testar nada.
        raise CenarioInvalido(f"{onde}: chave desconhecida {sorted(desconhecidas)}")
    pergunta = bruto.get("pergunta")
    if pergunta is not None and not isinstance(pergunta, bool):
        raise CenarioInvalido(f"{onde}: 'pergunta' tem que ser true ou false")
    for chave in ("responde_com", "nao_responde_com"):
        for padrao in _lista(bruto, chave, onde):
            try:
                re.compile(padrao)
            except re.error as causa:
                raise CenarioInvalido(f"{onde}: regex inválida {padrao!r}: {causa}") from causa
    return Expectativa(
        chama_em_ordem=_lista(bruto, "chama_em_ordem", onde),
        nao_chama=_lista(bruto, "nao_chama", onde),
        nao_chama_com=_proibidas(bruto.get("nao_chama_com", []), onde),
        responde_com=_lista(bruto, "responde_com", onde),
        nao_responde_com=_lista(bruto, "nao_responde_com", onde),
        pergunta=pergunta,
    )


def _proibidas(bruto: Any, onde: str) -> tuple[ChamadaProibida, ...]:
    if not isinstance(bruto, list):
        raise CenarioInvalido(f"{onde}: 'nao_chama_com' tem que ser lista")
    proibidas = []
    for item in bruto:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("ferramenta"), str)
            or not isinstance(item.get("entrada", {}), dict)
        ):
            raise CenarioInvalido(f"{onde}: 'nao_chama_com' espera {{ferramenta, entrada}}")
        entrada = tuple((str(k), str(v)) for k, v in item.get("entrada", {}).items())
        proibidas.append(ChamadaProibida(item["ferramenta"], entrada))
    return tuple(proibidas)


def carregar(caminho: Path) -> Cenario:
    bruto = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    if not isinstance(bruto, dict):
        raise CenarioInvalido(f"{caminho.name}: o arquivo tem que ser um mapa")
    turnos_brutos = bruto.get("turnos")
    if not isinstance(turnos_brutos, list) or not turnos_brutos:
        raise CenarioInvalido(f"{caminho.name}: sem turnos")

    turnos = []
    for i, t in enumerate(turnos_brutos, start=1):
        onde = f"{caminho.name} turno {i}"
        if not isinstance(t, dict) or not isinstance(t.get("diz"), str) or not t["diz"].strip():
            raise CenarioInvalido(f"{onde}: falta o que ela diz")
        turnos.append(
            TurnoRoteirizado(diz=t["diz"].strip(), espera=_expectativa(t.get("espera"), onde))
        )

    return Cenario(
        nome=str(bruto.get("nome") or caminho.stem),
        secao=str(bruto.get("secao") or ""),
        descricao=str(bruto.get("descricao") or "").strip(),
        turnos=tuple(turnos),
        nunca_chama=_lista(bruto, "nunca_chama", caminho.name),
        chama_na_conversa=_lista(bruto, "chama_na_conversa", caminho.name),
    )


def _em_ordem(esperadas: tuple[str, ...], chamadas: tuple[Chamada, ...]) -> str | None:
    """Confere que as esperadas aparecem nessa ordem, com qualquer coisa entre elas."""
    restantes = list(esperadas)
    for chamada in chamadas:
        if restantes and chamada.e(restantes[0]):
            restantes.pop(0)
    if restantes:
        feitas = [c.do_motor or c.ferramenta for c in chamadas]
        return f"esperava {list(esperadas)} nessa ordem; faltou {restantes}; chamou {feitas}"
    return None


def avaliar(cenario: Cenario, turnos: list[Turno]) -> Veredito:
    """Confronta a conversa que aconteceu com a roteirizada."""
    falhas: list[str] = []
    if len(turnos) != len(cenario.turnos):
        falhas.append(f"a conversa teve {len(turnos)} turnos de {len(cenario.turnos)}")

    for i, (roteiro, turno) in enumerate(zip(cenario.turnos, turnos, strict=False), start=1):
        falhas += [f"turno {i}: {f}" for f in _falhas_do_turno(roteiro.espera, cenario, turno)]

    todas = tuple(c for turno in turnos for c in turno.chamadas)
    if falta := _em_ordem(cenario.chama_na_conversa, todas):
        falhas.append(f"na conversa: {falta}")

    return Veredito(cenario=cenario.nome, falhas=tuple(falhas))


def _falhas_do_turno(e: Expectativa, cenario: Cenario, turno: Turno) -> list[str]:
    falhas: list[str] = []
    if turno.codigo_saida != 0:
        falhas.append(f"o Hermes saiu com código {turno.codigo_saida}")
    if falta := _em_ordem(e.chama_em_ordem, turno.chamadas):
        falhas.append(falta)
    proibidas = [
        *(nome for nome in (*e.nao_chama, *cenario.nunca_chama) if _chamou(turno, nome)),
        *(str(p) for p in e.nao_chama_com if any(p.casa(c) for c in turno.chamadas)),
    ]
    falhas += [f"chamou {nome}, que não podia" for nome in proibidas]
    falhas += [
        f"a resposta não contém /{p}/"
        for p in e.responde_com
        if not re.search(p, turno.resposta, re.IGNORECASE)
    ]
    falhas += [
        f"a resposta contém /{p}/, que não podia"
        for p in e.nao_responde_com
        if re.search(p, turno.resposta, re.IGNORECASE)
    ]
    falhas += [
        f"usou {c.ferramenta}, que o agente não usa"
        for c in turno.chamadas
        if c.ferramenta in FORA_DO_PAPEL
    ]
    if apagados := turno.resposta.count(MARCA_DO_GUARDRAIL):
        falhas.append(f"chegou a ela com {apagados} valor(es) apagado(s)")
    if jargao := sorted({m.group(0) for m in JARGAO_INTERNO.finditer(turno.resposta)}):
        falhas.append(f"falou com ela em jargão interno: {', '.join(jargao)}")
    if e.pergunta is not None and ("?" in turno.resposta) != e.pergunta:
        falhas.append("devia " + ("fazer uma pergunta" if e.pergunta else "não perguntar nada"))
    return falhas


def _chamou(turno: Turno, nome: str) -> bool:
    return any(c.e(nome) for c in turno.chamadas)
