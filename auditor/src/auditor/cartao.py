"""O cartão do agente auditor, conforme o A2A.

**Por que A2A e não mais uma ferramenta MCP.** São protocolos para problemas
diferentes, e a diferença é a razão de este pacote existir separado:

    MCP   agente → ferramenta/dado     capacidade que o agente usa
    A2A   agente ↔ agente              par que colabora sem expor implementação

Se o auditor fosse uma ferramenta MCP do próprio motor, ele conferiria a conta
usando o mesmo código que a produziu. Isso não é auditoria, é tautologia: um erro
na fórmula passaria pelos dois lados. O auditor precisa ser **um par**, com
implementação própria e sem estado compartilhado, e A2A é o protocolo para isso.

O cartão é como um agente se apresenta: quem é, o que sabe fazer, por onde falar.
Fica em `/.well-known/agent-card.json`, que é onde a especificação manda procurar.
"""

from __future__ import annotations

from typing import Any, Final

VERSAO_A2A: Final = "0.3.0"
NOME: Final = "auditor-de-conta"


def cartao(base: str = "http://127.0.0.1:8899") -> dict[str, Any]:
    """O cartão do agente, como a especificação A2A descreve.

    `capabilities` diz o que **não** temos também: sem streaming e sem push. É
    honestidade de protocolo: um cliente que anuncia capacidade que não tem gera
    falha no par, não no próprio.
    """
    return {
        "protocolVersion": VERSAO_A2A,
        "name": NOME,
        "description": (
            "Recalcula de forma independente o CMV e o preço de um prato já "
            "aceito, e recusa a exibição quando diverge do motor principal."
        ),
        "url": f"{base}/a2a",
        "preferredTransport": "JSONRPC",
        "version": "1.0.0",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": False,
        },
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "skills": [
            {
                "id": "conferir-cmv",
                "name": "Conferir CMV",
                "description": (
                    "Soma as linhas informadas e compara com o total delas. Quando o "
                    "custo usado no preço é o topo de uma faixa, confere também que ele "
                    "não fica abaixo dessa soma."
                ),
                "tags": ["auditoria", "custo"],
                "examples": ["Confira se o CMV de R$ 4,31 do frango à parmegiana está certo."],
            },
            {
                "id": "conferir-preco",
                "name": "Conferir preço",
                "description": (
                    "Recalcula preço mínimo e lucro a partir do CMV e da taxa da "
                    "plataforma, e confere as duas fórmulas do enunciado. Preço "
                    "abaixo do mínimo com a conta certa volta com aviso, sem recusa."
                ),
                "tags": ["auditoria", "preco"],
                "examples": ["O lucro de R$ 6,77 a R$ 12,31 confere?"],
            },
        ],
    }


__all__ = ["NOME", "VERSAO_A2A", "cartao"]
