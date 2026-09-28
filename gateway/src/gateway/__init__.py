"""MCP Gateway: a política de acesso ao motor determinístico.

O agente decide o que chamar a partir de texto, e parte desse texto vem da
internet. A política de acesso não pode depender do julgamento dele.
"""

from gateway.politica import (
    Auditoria,
    Autenticacao,
    Autorizacao,
    CircuitBreaker,
    Credencial,
    ErroDePolitica,
    Escopo,
    EstadoBreaker,
    Quota,
    RateLimit,
    pilha_padrao,
)

__version__ = "0.1.0"

__all__ = [
    "Auditoria",
    "Autenticacao",
    "Autorizacao",
    "CircuitBreaker",
    "Credencial",
    "ErroDePolitica",
    "Escopo",
    "EstadoBreaker",
    "Quota",
    "RateLimit",
    "__version__",
    "pilha_padrao",
]
