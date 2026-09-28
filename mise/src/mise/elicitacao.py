"""Que pergunta fazer primeiro.

O portão sabe dizer o que falta para cada receita. Mas se o agente simplesmente
despejar essa lista, a conversa vira formulário, e a Dona Maria desiste antes
de chegar ao cardápio.

A ordem certa não é a ordem em que as perguntas aparecem: é a ordem do **ganho
de informação**. "A senhora tem forno?" que decide 7 de 12 candidatas vem antes
de "a senhora sabe temperar chocolate?", que decide uma. Cada resposta compra o
máximo de decisão possível.

Duas métricas, e a segunda importa mais que a primeira:

- `receitas_afetadas`: em quantas candidatas a pergunta aparece.
- `receitas_destravadas`: em quantas ela é a **última** pendência. Responder
  essas converte `FALTA_INFO` em decisão imediata, que é o que a Dona Maria
  sente como progresso.

Uma pergunta que destrava 3 pratos na hora vale mais que uma que aparece em 8
mas não fecha nenhum.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from mise.passos import ENTRADAS_DA_RECEITA
from mise.perfil import Gosto, contagem
from mise.viabilidade import Avaliacao, Pergunta, TipoRestricao, Veredito, avaliar

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from mise.compras import Cotacao
    from mise.despensa import Despensa
    from mise.dinheiro import Dinheiro
    from mise.perfil import PerfilCozinha
    from mise.receita import Receita

#: Peso do destravamento imediato contra a mera aparição.
#: Alto de propósito: fechar um prato vale muito mais que avançar em vários.
PESO_DESTRAVE = 10


@dataclass(frozen=True, slots=True)
class PerguntaPriorizada:
    """Uma pergunta com o que ela compra em termos de decisão."""

    pergunta: Pergunta
    receitas_afetadas: tuple[str, ...]
    receitas_destravadas: tuple[str, ...]

    @property
    def ganho(self) -> int:
        return len(self.receitas_destravadas) * PESO_DESTRAVE + len(self.receitas_afetadas)

    @property
    def campo(self) -> str:
        return self.pergunta.campo

    @property
    def texto(self) -> str:
        return self.pergunta.texto

    def justificativa(self) -> str:
        """Por que esta pergunta antes das outras, para o log e para o agente."""
        if self.receitas_destravadas:
            quais = ", ".join(self.receitas_destravadas[:3])
            pratos = contagem(len(self.receitas_destravadas), "prato", "pratos")
            return f"responder isso decide {pratos} na hora ({quais})"
        candidatos = contagem(len(self.receitas_afetadas), "prato candidato", "pratos candidatos")
        return f"aparece em {candidatos}"

    def __str__(self) -> str:
        return self.texto


@dataclass(slots=True)
class PlanoDeElicitacao:
    """As perguntas em aberto, na ordem que rende mais decisão por resposta."""

    perguntas: tuple[PerguntaPriorizada, ...] = ()
    aptas: tuple[str, ...] = ()
    bloqueadas: tuple[str, ...] = ()
    pendentes: tuple[str, ...] = ()

    def __len__(self) -> int:
        return len(self.perguntas)

    def __bool__(self) -> bool:
        return bool(self.perguntas)

    @property
    def proxima(self) -> PerguntaPriorizada | None:
        """A pergunta que o agente deve fazer agora."""
        return self.perguntas[0] if self.perguntas else None

    def proximas(self, n: int = 3) -> tuple[PerguntaPriorizada, ...]:
        """As `n` melhores: o agente pode encadear duas ou três numa fala só."""
        return self.perguntas[:n]

    def resumo(self) -> str:
        """Uma linha para o agente, sem as palavras do sistema: pode chegar a ela."""
        return (
            f"{contagem(len(self.aptas), 'prato que dá', 'pratos que dão')} · "
            f"{len(self.pendentes)} aguardando resposta · "
            f"{contagem(len(self.bloqueadas), 'que não dá', 'que não dão')} · "
            f"{contagem(len(self.perguntas), 'pergunta em aberto', 'perguntas em aberto')}"
        )


def montar_plano(
    receitas: Sequence[Receita],
    perfil: PerfilCozinha,
    despensa: Despensa,
    *,
    gostos: Mapping[str, Gosto] | None = None,
    precos: Mapping[str, Dinheiro | Cotacao] | None = None,
    avaliador: Callable[[Receita], Avaliacao] | None = None,
) -> PlanoDeElicitacao:
    """Avalia todas as candidatas e ordena as perguntas por ganho de informação.

    Avaliar todas antes de perguntar qualquer coisa é o que permite comparar,
    e é barato, porque o portão é determinístico e não chama modelo nenhum.

    `gostos` e `precos` são o que já foi respondido. Sem eles a entrevista
    repetiria para sempre perguntas que ela já respondeu, que é a forma mais
    rápida de fazer alguém desistir da conversa.

    `avaliador` substitui a avaliação padrão pela da sessão, com orçamento,
    compras e impedimentos. Sem ele, a próxima pergunta podia sair de um
    parecer diferente do que `avaliar_receita` acabou de mostrar para o mesmo prato.
    """
    afetadas: dict[str, list[str]] = defaultdict(list)
    destravadas: dict[str, list[str]] = defaultdict(list)
    por_campo: dict[str, Pergunta] = {}

    aptas: list[str] = []
    bloqueadas: list[str] = []
    pendentes: list[str] = []

    for receita in receitas:
        avaliacao = (
            avaliador(receita)
            if avaliador is not None
            else avaliar(
                receita,
                perfil,
                despensa,
                precos=precos,
                gosto=(gostos or {}).get(receita.nome, Gosto.DESCONHECIDO),
            )
        )

        if avaliacao.veredito is Veredito.BLOQUEADO:
            bloqueadas.append(receita.nome)
            # Prato impossível não gera pergunta: seria gastar a paciência dela à toa.
            continue
        if avaliacao.veredito.permite_precificar:
            aptas.append(receita.nome)
            continue

        pendentes.append(receita.nome)
        chaves = {_chave(p): p for p in avaliacao.perguntas}
        for chave, pergunta in chaves.items():
            afetadas[chave].append(receita.nome)
            por_campo.setdefault(chave, pergunta)
            if len(chaves) == 1:
                destravadas[chave].append(receita.nome)

    priorizadas = tuple(
        sorted(
            (
                PerguntaPriorizada(
                    pergunta=por_campo[chave],
                    receitas_afetadas=tuple(nomes),
                    receitas_destravadas=tuple(destravadas.get(chave, ())),
                )
                for chave, nomes in afetadas.items()
            ),
            key=lambda p: (-p.ganho, _ordem_do_tipo(p.pergunta.tipo), p.campo),
        )
    )

    return PlanoDeElicitacao(
        perguntas=priorizadas,
        aptas=tuple(aptas),
        bloqueadas=tuple(bloqueadas),
        pendentes=tuple(pendentes),
    )


def proxima_pergunta(
    receitas: Sequence[Receita],
    perfil: PerfilCozinha,
    despensa: Despensa,
    *,
    gostos: Mapping[str, Gosto] | None = None,
    precos: Mapping[str, Dinheiro] | None = None,
) -> PerguntaPriorizada | None:
    """Atalho: só a próxima pergunta a fazer."""
    return montar_plano(receitas, perfil, despensa, gostos=gostos, precos=precos).proxima


#: Perguntas sobre a própria receita: a resposta volta nela e só decide ela.
CAMPOS_DA_RECEITA: Final[frozenset[str]] = frozenset({"modo_preparo", *ENTRADAS_DA_RECEITA})


def _chave(pergunta: Pergunta) -> str:
    """Identidade de uma pergunta, para agrupar entre receitas diferentes.

    A pergunta da cozinha ("tem forno?") é uma só para todas as receitas. A da
    receita ("quanto tempo esta receita fica no fogo?") é uma por receita: juntar
    as de pratos diferentes faria uma resposta parecer decidir vários.
    """
    if pergunta.campo in CAMPOS_DA_RECEITA:
        return f"{pergunta.tipo.name}:{pergunta.campo}:{pergunta.texto}"
    return f"{pergunta.tipo.name}:{pergunta.campo}"


def _ordem_do_tipo(tipo: TipoRestricao) -> int:
    """Desempate: gosto antes de tudo, depois equipamento, técnica, operação.

    **Gosto vem primeiro** porque é a pergunta mais barata de responder e a que
    mais elimina. Perguntar sobre bocas de fogão e depois descobrir que ela não
    gosta de fazer o prato gastou o tempo dela à toa, e o tempo dela é o
    recurso mais escasso desta conversa.

    Equipamento é binário e ela responde na hora. Técnica exige que ela julgue a
    própria habilidade, o que é mais lento e mais delicado. Preço de ingrediente
    é o que mais a tira do fluxo, porque exige consultar mercado.
    """
    ordem = {
        TipoRestricao.GOSTO: 0,
        TipoRestricao.EQUIPAMENTO: 1,
        TipoRestricao.TECNICA: 2,
        TipoRestricao.OPERACIONAL: 3,
        TipoRestricao.INGREDIENTE: 4,
    }
    # Um tipo novo vai para o fim em vez de derrubar a entrevista inteira com
    # KeyError. Perder o desempate ideal custa uma pergunta fora de ordem;
    # estourar aqui custa a conversa.
    return ordem.get(tipo, len(ordem))


__all__ = [
    "CAMPOS_DA_RECEITA",
    "PESO_DESTRAVE",
    "PerguntaPriorizada",
    "PlanoDeElicitacao",
    "montar_plano",
    "proxima_pergunta",
]
