"""A segunda opinião sobre cada preço, antes de ele chegar à Dona Maria.

O auditor (`auditor/`) refaz a conta do §2.4 a partir do enunciado, sem
importar o motor: conferir com o mesmo código que produziu o número não é
auditoria. Este módulo decide como falar com ele:

- com `MISE_AUDITOR_URL` (o endereço do `/a2a` do auditor, por exemplo
  `http://127.0.0.1:8899/a2a`), pelo protocolo A2A (JSON-RPC `message/send`), como
  um agente separado, que pode rodar em outra máquina e ser de outra equipe;
- sem a variável, o mesmo código de conferência em processo, para que a
  checagem nunca fique desligada num clone recém-baixado.

Auditor fora do ar não para a consultoria: o parecer volta com `confere: null`
e a trilha registra que aquele preço saiu sem segunda opinião. Discordância é
outra coisa: o motor recusa o preço (`ContaNaoConfere`). Preço abaixo do mínimo
com a conta certa não é discordância: volta `da_prejuizo: true` com um `aviso`,
e a decisão continua sendo dela.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from typing import Any, Final

logger = logging.getLogger(__name__)

#: Quanto esperar pelo auditor remoto. É uma conta; não pode levar mais que isso.
TIMEOUT: Final = 5.0

#: Envia o corpo JSON ao endereço e devolve o corpo da resposta. Injetável em teste.
Postar = Callable[[str, bytes], bytes]


def _postar_http(url: str, corpo: bytes) -> bytes:
    requisicao = urllib.request.Request(
        url, data=corpo, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(requisicao, timeout=TIMEOUT) as resposta:
        dados: bytes = resposta.read()
    return dados


def auditor_em_processo(prato: dict[str, Any]) -> dict[str, Any]:
    """O código de conferência do auditor, chamado direto."""
    from auditor.conferencia import conferir  # noqa: PLC0415

    veredito = conferir(prato)
    return {
        "confere": veredito.confere,
        "observacao": veredito.observacao,
        "divergencias": [str(d) for d in veredito.divergencias],
        "da_prejuizo": veredito.da_prejuizo,
        "aviso": veredito.aviso,
        "por": "auditor independente, em processo",
    }


def auditor_a2a(
    url: str, postar: Postar = _postar_http
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Um auditor remoto, pelo protocolo A2A."""

    def auditar(prato: dict[str, Any]) -> dict[str, Any]:
        envelope = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "message/send",
            "params": {"message": {"role": "user", "parts": [{"kind": "data", "data": prato}]}},
        }
        try:
            bruto = postar(url, json.dumps(envelope, ensure_ascii=False).encode())
            resposta = json.loads(bruto)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as erro:
            logger.warning("auditor A2A em %s indisponível: %s", url, erro)
            return {"confere": None, "observacao": f"auditor indisponível: {erro}", "por": url}

        dados = _dados_do_parecer(resposta)
        if dados is None:
            motivo = resposta.get("error", {}).get("message", "resposta sem parecer")
            return {"confere": None, "observacao": f"auditor não respondeu: {motivo}", "por": url}
        return {**dados, "por": url}

    return auditar


def _dados_do_parecer(resposta: dict[str, Any]) -> dict[str, Any] | None:
    partes = (resposta.get("result") or {}).get("parts") or []
    for parte in partes:
        if isinstance(parte, dict) and isinstance(parte.get("data"), dict):
            return dict(parte["data"])
    return None


def auditor_do_ambiente() -> Callable[[dict[str, Any]], dict[str, Any]]:
    """A2A se `MISE_AUDITOR_URL` estiver definida; senão, em processo."""
    url = os.environ.get("MISE_AUDITOR_URL", "").strip()
    return auditor_a2a(url) if url else auditor_em_processo


__all__ = ["TIMEOUT", "auditor_a2a", "auditor_do_ambiente", "auditor_em_processo"]
