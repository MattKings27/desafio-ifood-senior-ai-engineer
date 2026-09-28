"""Ponto de entrada de produção: motor + política.

Esta é a composição raiz. É o único lugar do sistema que conhece as duas
camadas ao mesmo tempo: o motor não sabe que existe política, e a política não
sabe cozinhar. Cada uma muda por um motivo diferente, e essa é a razão de
estarem separadas.

Uso pelo Hermes, via `mcp_servers` no `config.yaml`:

    mcp_servers:
      mise:
        command: "/caminho/para/.venv/bin/python"
        args: ["-m", "gateway.principal"]
        env:
          MISE_PLANILHA: "/caminho/dados/despensa_dona_maria.xlsx"
          MISE_DOSSIE: "/caminho/estado/dossie.db"
          MISE_AUDITORIA: "/caminho/estado/auditoria.jsonl"
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Final

from gateway.auditoria_independente import auditor_do_ambiente
from gateway.politica import Auditoria, Autenticacao, pilha_padrao

NIVEL_LOG: Final = os.environ.get("MISE_LOG", "INFO").upper()


def configurar_log() -> None:
    """Log vai para stderr: stdout é do protocolo JSON-RPC e não pode ser poluído."""
    logging.basicConfig(
        level=getattr(logging, NIVEL_LOG, logging.INFO),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s [gateway] %(message)s",
    )


def main() -> None:
    from mise.dossie import Canal  # noqa: PLC0415
    from mise.mcp_server import abrir_sessao, construir_servidor  # noqa: PLC0415

    configurar_log()
    log = logging.getLogger(__name__)

    autenticacao = Autenticacao.do_ambiente()
    auditoria = Auditoria.do_ambiente()

    if autenticacao.aberto:
        log.warning(
            "sem MISE_TOKEN_LEITURA/MISE_TOKEN_ESCRITA: gateway em modo aberto. "
            "Aceitável em desenvolvimento; configure os tokens antes de expor."
        )
    if auditoria.destino is None:
        log.warning("sem MISE_AUDITORIA: trilha de auditoria só em memória")

    from mise.precos_na_web import ligada  # noqa: PLC0415

    sessao = abrir_sessao()
    # Todo preço passa por uma segunda opinião antes de chegar a ela.
    sessao.auditor = auditor_do_ambiente()
    # O que falta sem preço é procurado nos mercados de São Paulo (`SABOR_PRECOS_NA_WEB`).
    sessao.pesquisar_precos_ao_guardar = ligada()
    # Quem chama por aqui é o agente, na conversa com ela.
    sessao.canal = Canal.CONVERSA
    log.info(
        "despensa carregada: %d itens, %s investidos, %d pendência(s)",
        len(sessao.despensa),
        sessao.despensa.total_investido,
        len(sessao.despensa.pendencias),
    )

    servidor = construir_servidor(
        sessao, middleware=pilha_padrao(autenticacao=autenticacao, auditoria=auditoria)
    )
    servidor.run(transport="stdio")


if __name__ == "__main__":
    main()
