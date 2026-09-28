"""Restaurar os dados da planilha: tudo o que ela mudou volta ao começo, dentro dos mesmos arquivos.

"Restaurar os dados da planilha" (nas Preferências) leva a plataforma de volta
ao dia em que ela entregou a planilha: a despensa e os preços, os itens que ela
acrescentou ou tirou, as compras e os R$ 80,00, as respostas sobre a cozinha,
os gostos, as estrelas e as notas, as decisões e o cardápio, as premissas do
preço, as respostas sobre as receitas e as receitas que ela ditou. As receitas
das páginas que o servidor leu continuam no catálogo, como a página veio.

**Dentro dos mesmos arquivos.** O servidor MCP do agente mantém o dossiê
aberto, e no disco do Windows mover ou apagar um arquivo aberto falha. Então as
linhas saem das tabelas, numa transação só (`BEGIN IMMEDIATE`), e o arquivo
fica onde está: a outra conexão vê o dossiê restaurado na leitura seguinte
(`PRAGMA data_version` muda, e a despensa em cache é refeita). Nenhuma tabela é
apagada: cada módulo lembra que já criou a sua, e continua certo.

**Os ids continuam andando.** A contagem do `AUTOINCREMENT` não volta a zero:
um evento novo nunca reaproveita o id de um que existiu, e nada que ainda se
lembre do id antigo aponta para outra coisa.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from mise.catalogo import CatalogoDeVolta, garantir_o_catalogo, voltar_ao_que_foi_lido

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mise.dossie import Dossie

#: As tabelas que guardam o que ela fez, e o que cada uma é, dito para ela.
TABELAS_DELA: Final[Mapping[str, str]] = MappingProxyType(
    {
        "despensa_eventos": "mudanças na despensa",
        "gastos": "compras com os complementos",
        "perfil": "respostas sobre a cozinha",
        "perfil_eventos": "histórico da cozinha",
        "gostos": "gostos",
        "avaliacoes": "estrelas e notas",
        "decisoes": "decisões do cardápio",
        "precos_mercado": "preços que ela informou",
        "candidatas": "receitas em avaliação",
        "parametros": "premissas do preço",
    }
)


@dataclass(frozen=True, slots=True)
class DossieRestaurado:
    """Quantas linhas saíram de cada tabela, e o que aconteceu no catálogo."""

    apagadas: Mapping[str, int]
    catalogo: CatalogoDeVolta

    @property
    def mudou(self) -> bool:
        """Havia alguma coisa dela para tirar."""
        return any(self.apagadas.values()) or bool(
            self.catalogo.sem_as_respostas or self.catalogo.ditas or self.catalogo.sem_a_pagina
        )


def restaurar_dossie(dossie: Dossie) -> DossieRestaurado:
    """Tira do dossiê tudo o que ela mudou, numa transação só; o arquivo fica onde está.

    Restaurar o que já está restaurado não muda nada (e diz que nada mudou).
    """
    # O catálogo com a coluna da página, antes da transação: o esquema não roda dentro dela.
    garantir_o_catalogo(dossie)
    apagadas: dict[str, int] = {}
    with dossie.transacao() as cur:
        existentes = {
            linha[0] for linha in cur.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        for tabela in TABELAS_DELA:
            if tabela in existentes:
                # O nome vem da constante acima, nunca de quem chamou.
                apagadas[tabela] = int(cur.execute(f"DELETE FROM {tabela}").rowcount)
        catalogo = voltar_ao_que_foi_lido(cur)
    return DossieRestaurado(MappingProxyType(apagadas), catalogo)


__all__ = ["TABELAS_DELA", "DossieRestaurado", "restaurar_dossie"]
