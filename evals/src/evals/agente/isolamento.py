"""Cada execução começa do zero: dossiê novo, auditoria nova, memória vazia.

Sem isso, a segunda execução de um cenário encontra no dossiê o que a primeira
respondeu ("não tem forno"), pula a pergunta, e o cenário passa ou falha por
causa da execução anterior. Repetir k vezes deixaria de medir consistência e
passaria a medir contaminação.

Só mexe em perfil com nome terminado em `-avaliacao`. O perfil de uso real
guarda o que a Dona Maria contou, e apagar isso para rodar um teste é
exatamente o tipo de estrago que um harness não pode causar.
"""

from __future__ import annotations

from pathlib import Path

import yaml

SUFIXO_OBRIGATORIO = "-avaliacao"


class PerfilProtegido(RuntimeError):
    """Tentativa de isolar um perfil que não é de avaliação."""


def isolar(dir_perfil: Path, destino: Path) -> dict[str, str]:
    """Aponta o servidor MCP do perfil para arquivos novos em `destino`.

    Devolve as variáveis gravadas, para a transcrição registrar onde ficou o
    estado daquela execução.
    """
    if not dir_perfil.name.endswith(SUFIXO_OBRIGATORIO):
        raise PerfilProtegido(
            f"'{dir_perfil.name}' não termina em '{SUFIXO_OBRIGATORIO}'; "
            "o harness não toca em perfil de uso real"
        )
    config = dir_perfil / "config.yaml"
    dados = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    try:
        env = dados["mcp_servers"]["mise"]["env"]
    except (KeyError, TypeError) as causa:
        raise RuntimeError(
            f"o perfil {dir_perfil.name} não tem o servidor MCP 'mise'; rode o bootstrap nele"
        ) from causa

    destino.mkdir(parents=True, exist_ok=True)
    novo = {
        "MISE_DOSSIE": str(destino / "dossie.db"),
        "MISE_AUDITORIA": str(destino / "auditoria.jsonl"),
    }
    env.update(novo)
    config.write_text(yaml.safe_dump(dados, allow_unicode=True, sort_keys=False), "utf-8")

    # A memória do Hermes sobrevive entre sessões por projeto. Numa avaliação,
    # lembrar da execução anterior é vazamento de gabarito.
    memorias = dir_perfil / "memories"
    if memorias.is_dir():
        for arquivo in memorias.iterdir():
            if arquivo.is_file():
                arquivo.unlink()
    return novo
