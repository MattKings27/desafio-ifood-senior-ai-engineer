"""Os R$ 80,00 de complementos: quanto resta e o que ela comprou."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mise.serializacao import _reais, _resposta, protegido

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

    from mise.mcp_server import Sessao


def registrar(servidor: MCPServer, sessao: Sessao) -> None:
    """Os R$ 80,00 de complementos: quanto resta e o que ela comprou."""

    @servidor.tool()
    @protegido
    async def consultar_orcamento() -> str:
        """Quanto dos R$ 80,00 de complementos ainda resta."""
        estado = sessao.dossie.orcamento()
        return _resposta(
            {
                "inicial": _reais(estado.inicial),
                "gasto": _reais(estado.gasto),
                "restante": _reais(estado.restante),
                "fracao_usada": round(estado.fracao_usada, 4),
                "texto": str(estado),
                "compras": [
                    {"descricao": d, "valor": _reais(v)} for d, v, _ in sessao.dossie.gastos()
                ],
            }
        )

    @servidor.tool()
    @protegido
    async def registrar_compra(
        prato: str, ingrediente: str, quantidade: float, unidade: str, valor: float
    ) -> str:
        """Registra o que ela comprou para um prato: sai do orçamento e vira estoque.

        Passa pelo portão: só depois que equipamento, técnica, rotina e gosto do
        prato estão confirmados, com o que toda cozinha tem confirmado por ela
        (a recusa traz a pergunta, uma só), e só para um ingrediente que o prato
        precisa comprar. Recusa se estourar os R$ 80,00, que são o limite dela.
        Ex.: prato="Frango com milho", ingrediente="milho verde", quantidade=1,
        unidade="lata", valor=6.
        """
        resultado = sessao.comprar(prato, ingrediente, quantidade, unidade, valor)
        resultado["orcamento_restante"] = _reais(resultado["orcamento_restante"])
        return _resposta(resultado)


__all__ = ["registrar"]
