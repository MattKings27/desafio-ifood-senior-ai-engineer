"""LLM-as-judge, e a calibração que faz ele valer alguma coisa.

**A posição deste módulo, que é a mesma que eu defenderia numa discussão de
arquitetura:** um juiz LLM é *um* avaliador dentro de uma estratégia, não a
estratégia. Ele é, ele próprio, um sistema de medição baseado em modelo, com
vieses próprios, sensível ao prompt e não determinístico. Tratá-lo como verdade
troca "não sei medir qualidade" por "meço qualidade com um número que não sei
interpretar".

O que torna um juiz utilizável é **calibração**: medir o quanto ele concorda com
rótulo humano, num conjunto onde o humano já decidiu. Sem isso, "o juiz deu 0,8"
não significa nada.

Por isso este módulo tem três partes, nessa ordem de importância:

1. `concordancia()`: mede juiz contra humano. É o produto.
2. `Juiz`: a interface. Qualquer coisa que pontue serve.
3. `JuizDeterministico`: um juiz por regra, que serve de piso e de teste.

O adaptador para modelo de verdade fica atrás da mesma interface e só roda com
credencial configurada. **O portão do CI não depende dele**: um portão que
precisa de chave de API é um portão que falha por motivo alheio ao código, e
portão que falha por motivo alheio é portão que alguém desliga.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol

import yaml

CASOS: Final = Path(__file__).resolve().parents[2] / "casos"

#: Acima disto, a resposta é considerada boa pelo juiz.
LIMIAR: Final = 0.5

#: Concordância mínima com o humano para o juiz ser utilizável.
#: 0,8 não é número mágico: é o ponto em que o juiz erra menos de uma em cinco, o
#: que o torna útil para triagem sem substituir revisão humana.
CONCORDANCIA_MINIMA: Final = 0.8


@dataclass(frozen=True, slots=True)
class Resposta:
    """Uma resposta do agente, com o rótulo que um humano deu."""

    id: str
    pergunta: str
    resposta: str
    rotulo: str
    porque: str

    @property
    def humano_aprovou(self) -> bool:
        return self.rotulo == "boa"


@dataclass(frozen=True, slots=True)
class Nota:
    """O que um juiz devolve."""

    valor: float
    justificativa: str

    @property
    def aprovou(self) -> bool:
        return self.valor >= LIMIAR


class Juiz(Protocol):
    """Qualquer coisa que pontue uma resposta.

    A interface é estreita de propósito: é o que permite trocar juiz por juiz
    (determinístico, LLM ou um conjunto deles) sem mexer na calibração.
    """

    def julgar(self, resposta: Resposta) -> Nota: ...


# --------------------------------------------------------------------------- #
# Juiz determinístico                                                          #
# --------------------------------------------------------------------------- #

#: Sinais de que a resposta mostra a conta em vez de só o resultado.
#:
#: `×` e `÷` são intencionais e necessários: são os sinais que o próprio motor
#: escreve nas derivações ("500 g × R$ 14,00/kg = R$ 7,00"). Trocar por `x` e `/`
#: faria o juiz deixar de reconhecer justamente a marca de que a conta está
#: aberta, que é o que ele existe para premiar.
_MOSTRA_A_CONTA = re.compile(
    r"(÷|/|×|\bdividid|\bvezes\b|\bdá\b|\bsoma|\bconta\b|\bpor porção\b)",
    re.IGNORECASE,
)

#: Sinais de que a resposta reconhece a taxa da plataforma.
_RECONHECE_A_TAXA = re.compile(r"(10\s*%|0,90|90\s*%|plataforma fica|taxa)", re.IGNORECASE)

#: Sinais de recusa honesta em vez de estimativa.
_RECUSA = re.compile(r"(não dá para|preciso saber|não consigo|ainda não|falta)", re.IGNORECASE)

#: Sinais de chute apresentado como dado.
_CHUTE = re.compile(
    r"(típic|em média|geralmente|costuma ser|cerca de|aproximadamente)", re.IGNORECASE
)

#: Sinais de que a decisão fica com ela.
_DEVOLVE_A_DECISAO = re.compile(
    r"(a senhora (escolhe|decide|prefere)|quem decide|a senhora quer)", re.IGNORECASE
)

#: Sinais de que a resposta atropela o que ela disse.
_ATROPELA = re.compile(r"(recomendo fortemente|é onde a senhora ganha mais)", re.IGNORECASE)

#: Quando há número na resposta, ele precisa vir acompanhado da conta.
_TEM_NUMERO = re.compile(r"R\$\s*\d")

#: Abaixo disto, a resposta raramente explica o suficiente para ela agir.
#: Doze palavras é onde "está bloqueado" cai e "está bloqueado porque X, resolve
#: X e voltamos" não cai.
PALAVRAS_MINIMAS: Final = 12


class JuizDeterministico:
    """Julga por características observáveis do texto, sem chamar modelo.

    Não é um substituto para juiz LLM: é o **piso**. Ele codifica as poucas
    regras que este domínio tem e que são verificáveis sem interpretar linguagem:
    mostrou a conta? reconheceu a taxa? recusou em vez de chutar? devolveu a
    decisão?

    Existir é o que permite o portão do CI rodar sem credencial, e é contra ele
    que um juiz LLM precisa provar que acrescenta alguma coisa.
    """

    def julgar(self, resposta: Resposta) -> Nota:
        texto = resposta.resposta
        pontos: list[tuple[str, float]] = []

        if _TEM_NUMERO.search(texto):
            if _MOSTRA_A_CONTA.search(texto):
                pontos.append(("mostra a conta", 0.35))
            else:
                pontos.append(("dá número sem a conta", -0.45))

        # "Vendendo a X a senhora tem Y de lucro" sem citar a taxa é o erro mais
        # caro do enunciado, e o que mais parece certo.
        fala_de_preco = re.search(r"(vend|preço|cobra)", texto, re.IGNORECASE)
        if fala_de_preco and _TEM_NUMERO.search(texto):
            if _RECONHECE_A_TAXA.search(texto):
                pontos.append(("reconhece a taxa", 0.3))
            else:
                pontos.append(("ignora os 10% da plataforma", -0.6))

        if _RECUSA.search(texto):
            pontos.append(("recusa em vez de estimar", 0.35))
        if _CHUTE.search(texto) and _TEM_NUMERO.search(texto):
            pontos.append(("estimativa disfarçada de dado", -0.5))

        if _DEVOLVE_A_DECISAO.search(texto):
            pontos.append(("devolve a decisão", 0.25))
        if _ATROPELA.search(texto):
            pontos.append(("atropela a decisão dela", -0.5))

        # Resposta curta demais raramente explica o suficiente para ela agir.
        if len(texto.split()) < PALAVRAS_MINIMAS:
            pontos.append(("curta demais para ela agir", -0.35))

        valor = max(0.0, min(1.0, 0.5 + sum(p for _, p in pontos)))
        motivo = "; ".join(nome for nome, _ in pontos) or "nada de notável"
        return Nota(valor, motivo)


# --------------------------------------------------------------------------- #
# Juiz por modelo                                                              #
# --------------------------------------------------------------------------- #

PROMPT: Final = """Você avalia respostas de um agente de cardápio para uma cozinheira.

Uma resposta é BOA quando:
- mostra a conta que produziu cada número, não só o número;
- reconhece a taxa de 10% da plataforma ao falar de preço;
- recusa e diz o que falta, em vez de estimar;
- devolve a decisão para ela.

É RUIM quando dá número sem conta, ignora a taxa, disfarça chute de dado, ou
atropela o que ela decidiu.

Pergunta: {pergunta}
Resposta: {resposta}

Devolva só um número entre 0 e 1."""


#: A temperatura do juiz: zero, a mesma nota para a mesma resposta. O Haiku 4.5
#: é o único modelo daqui que ainda aceita o parâmetro; os modelos do agente
#: o recusam, e lá a repetibilidade vem da arquitetura.
TEMPERATURA_DO_JUIZ: Final = 0


class JuizDeModelo:
    """Adaptador para um modelo de verdade.

    Só roda com `ANTHROPIC_API_KEY` no ambiente. **Não é o portão do CI**: um
    portão que precisa de chave falha por motivo alheio ao código, e portão que
    falha por motivo alheio é portão que alguém desliga.
    """

    def __init__(self, modelo: str = "claude-haiku-4-5") -> None:
        self.modelo = modelo

    @staticmethod
    def disponivel() -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())

    def pedido(self, resposta: Resposta) -> dict[str, Any]:
        """O pedido ao modelo, com a temperatura fixa em zero."""
        return {
            "model": self.modelo,
            "max_tokens": 16,
            "temperature": TEMPERATURA_DO_JUIZ,
            "messages": [
                {
                    "role": "user",
                    "content": PROMPT.format(
                        pergunta=resposta.pergunta, resposta=resposta.resposta
                    ),
                }
            ],
        }

    def julgar(self, resposta: Resposta) -> Nota:  # pragma: sem cobertura
        from anthropic import Anthropic  # noqa: PLC0415

        cliente = Anthropic()
        saida = cliente.messages.create(**self.pedido(resposta))
        texto = "".join(b.text for b in saida.content if b.type == "text")
        achado = re.search(r"[01](?:[.,]\d+)?", texto)
        valor = float(achado.group().replace(",", ".")) if achado else 0.5
        return Nota(min(1.0, max(0.0, valor)), f"juiz {self.modelo}: {texto.strip()[:60]}")


# --------------------------------------------------------------------------- #
# Calibração: o produto deste módulo                                           #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Calibracao:
    """O quanto o juiz concorda com o humano, e onde ele erra."""

    total: int
    concordou: int
    falsos_positivos: tuple[str, ...]
    falsos_negativos: tuple[str, ...]

    @property
    def concordancia(self) -> float:
        return self.concordou / self.total if self.total else 0.0

    @property
    def utilizavel(self) -> bool:
        return self.concordancia >= CONCORDANCIA_MINIMA

    def __str__(self) -> str:
        linhas = [
            f"concordância com o humano: {self.concordou}/{self.total} ({self.concordancia:.0%})"
        ]
        if self.falsos_positivos:
            linhas.append(f"  aprovou o que o humano reprovou: {', '.join(self.falsos_positivos)}")
        if self.falsos_negativos:
            linhas.append(f"  reprovou o que o humano aprovou: {', '.join(self.falsos_negativos)}")
        return "\n".join(linhas)


def carregar_respostas(caminho: Path | None = None) -> list[Resposta]:
    bruto = yaml.safe_load((caminho or CASOS / "respostas.yaml").read_text("utf-8"))
    return [
        Resposta(
            id=r["id"],
            pergunta=r["pergunta"],
            resposta=" ".join(r["resposta"].split()),
            rotulo=r["rotulo"],
            porque=" ".join(r["porque"].split()),
        )
        for r in bruto
    ]


def calibrar(juiz: Juiz, respostas: list[Resposta] | None = None) -> Calibracao:
    """Mede o juiz contra o rótulo humano.

    Separa falso positivo de falso negativo de propósito: eles custam coisas
    diferentes. Aprovar resposta ruim deixa passar um número errado para a Dona
    Maria; reprovar resposta boa só gasta revisão humana. Um juiz com a mesma
    concordância mas concentrada em falso positivo é pior.
    """
    casos = respostas if respostas is not None else carregar_respostas()
    concordou = 0
    falsos_positivos: list[str] = []
    falsos_negativos: list[str] = []

    for caso in casos:
        aprovou = juiz.julgar(caso).aprovou
        if aprovou == caso.humano_aprovou:
            concordou += 1
        elif aprovou:
            falsos_positivos.append(caso.id)
        else:
            falsos_negativos.append(caso.id)

    return Calibracao(len(casos), concordou, tuple(falsos_positivos), tuple(falsos_negativos))


__all__ = [
    "CONCORDANCIA_MINIMA",
    "LIMIAR",
    "Calibracao",
    "Juiz",
    "JuizDeModelo",
    "JuizDeterministico",
    "Nota",
    "Resposta",
    "calibrar",
    "carregar_respostas",
]
