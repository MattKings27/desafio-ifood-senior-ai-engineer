"""O que ela quer no cardápio: as decisões dela e se gosta de fazer cada prato."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mise.dossie import Decisao
from mise.perfil import Gosto
from mise.serializacao import _resposta, protegido

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

    from mise.mcp_server import Sessao


def _ultimo_aceite(sessao: Sessao, prato: str) -> dict[str, Any]:
    """Preço, custo e lucro do aceite mais recente do prato, como foram gravados."""
    aceites = [r for r in sessao.dossie.historico(prato) if r.decisao is Decisao.ACEITO]
    return dict(aceites[-1].detalhes) if aceites else {}


def registrar(servidor: MCPServer, sessao: Sessao) -> None:
    """Decisões, gostos e cardápio."""

    # --- decisões e gostos -------------------------------------------------- #

    @servidor.tool()
    @protegido
    async def registrar_decisao(
        prato: str, decisao: str, motivo: str = "", preco: float | None = None
    ) -> str:
        """Grava a decisão DELA sobre um prato: aceito, recusado ou adiado.

        Aceitar exige o prato aprovado no portão, o preço que ela escolheu e a
        cozinha confirmada: se a receita usa algo que toda cozinha tem e ela
        ainda não confirmou (fogão, panela funda, refogar), a recusa traz a
        `pergunta`, uma só; faça essa pergunta e grave o sim dela com
        registrar_resposta(tipo="cozinha", campo=<receita_id>, resposta="tem").
        O preço fica na trilha com o lucro calculado. Abaixo do mínimo sem
        prejuízo a decisão ainda é dela, e a resposta diz quanto ela perde.
        Recusar e adiar valem sempre.
        """
        registro, detalhes = sessao.decidir(prato, decisao, motivo, preco)
        return _resposta(
            {
                "registrado": str(registro),
                **detalhes,
                "cardapio_atual": list(sessao.dossie.cardapio),
            }
        )

    @servidor.tool()
    @protegido
    async def registrar_gosto(prato: str, gosta: bool, impedimento: str = "") -> str:
        """Guarda se a Dona Maria gosta de fazer um prato, e o que ela vê de empecilho.

        É a quinta checagem do portão, e bloqueia como as outras quatro. Um prato
        que ela não gosta de fazer não entra no cardápio por mais barato que o CMV
        saia: quem cozinha é ela, todo dia.

        `impedimento` é o "vê algum impedimento?" do §2.1, em texto livre, e
        bloqueia mesmo quando ela gosta do prato: gostar de fazer e conseguir
        fazer não são a mesma coisa.
        """
        opiniao = sessao.dossie.registrar_gosto(
            prato, Gosto.GOSTA if gosta else Gosto.NAO_GOSTA, impedimento
        )
        return _resposta(
            {
                "registrado": str(opiniao),
                "efeito": (
                    "prato bloqueado no portão"
                    if opiniao.gosto.bloqueia or opiniao.impedimento
                    else "gosto confirmado; o portão segue para as outras checagens"
                ),
            }
        )

    @servidor.tool()
    @protegido
    async def consultar_gostos() -> str:
        """O que ela já disse sobre gostar ou não de fazer cada prato."""
        return _resposta({"gostos": [str(o) for o in sessao.dossie.gostos()]})

    # --- cardápio ------------------------------------------------------------ #

    @servidor.tool()
    @protegido
    async def consultar_cardapio() -> str:
        """Os pratos que ela aceitou, com o preço e o lucro gravados, e a trilha inteira."""
        return _resposta(
            {
                "cardapio": list(sessao.dossie.cardapio),
                "aceitos": [
                    {"prato": prato, **_ultimo_aceite(sessao, prato)}
                    for prato in sessao.dossie.cardapio
                ],
                "historico": [str(r) for r in sessao.dossie.historico()],
                "candidatas_em_avaliacao": sorted(sessao.candidatas),
            }
        )


__all__ = ["registrar"]
