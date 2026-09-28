"""Aplica ao `config.yaml` do perfil do Hermes o que o repositório versiona.

O `bootstrap.sh` chama este arquivo com o Python do motor:

    python hermes/configurar_perfil.py <config.yaml do perfil> <venv> <raiz do repositório>

Três coisas, nesta ordem, e rodar de novo dá o mesmo arquivo:

1. registra o servidor MCP `mise`, apontado para esta cópia do repositório;
2. funde `hermes/config.overlay.yaml`, chave por chave, sem apagar o que o
   `--clone` trouxe (credencial e preferência continuam lá);
3. escreve `skills.disabled` com todas as skills do perfil menos as cinco da
   consultoria, pelo mecanismo oficial do Hermes (`hermes_cli/skills_config.py`).
   A lista é calculada da pasta do perfil a cada execução porque uma lista fixa
   envelhece: o Hermes traz, tira e renomeia skills genéricas entre versões.

Mora num arquivo, e não num trecho do shell, para os testes importarem as mesmas
funções que o bootstrap usa em vez de uma cópia delas.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, MutableMapping
from pathlib import Path
from typing import Any

import yaml

#: Skills que o Hermes nunca desliga (`ESSENTIAL_SKILLS` em `agent/skill_utils.py`):
#: pôr na lista seria fingir que ela está desligada.
ESSENCIAIS = frozenset({"hermes-agent"})

#: O servidor sobe em poucos segundos num disco local. Com o limite padrão de
#: 30 s, um disco lento (WSL em /mnt/c) fazia o Hermes desistir, e o agente
#: conversava sem nenhuma ferramenta do motor, sem avisar ninguém.
ESPERA_PARA_CONECTAR_S = 90


def fundir(destino: MutableMapping[str, Any], origem: dict[str, Any]) -> None:
    """Aplica o overlay chave por chave, sem apagar o que não está nele.

    Substituir o dicionário inteiro levaria junto credencial e preferência que o
    `--clone` trouxe. A fusão é recursiva só em dicionário: lista e escalar são
    substituídos, porque "metade da lista antiga" nunca é o que se quer.
    """
    for chave, valor in origem.items():
        if isinstance(valor, dict) and isinstance(destino.get(chave), dict):
            fundir(destino[chave], valor)
        else:
            destino[chave] = valor


def nome_da_skill(skill_md: Path) -> str:
    """O nome pelo qual o Hermes liga e desliga a skill: o `name` do cabeçalho, ou a pasta."""
    texto = skill_md.read_text(encoding="utf-8", errors="replace")
    if texto.startswith("---"):
        fim = texto.find("\n---", 3)
        if fim != -1:
            try:
                cabecalho = yaml.safe_load(texto[3:fim])
            except yaml.YAMLError:
                cabecalho = None
            nome = cabecalho.get("name") if isinstance(cabecalho, dict) else None
            if isinstance(nome, str) and nome.strip():
                return nome.strip()
    return skill_md.parent.name


def nomes_das_skills(pasta: Path) -> set[str]:
    """Os nomes de todas as skills sob `pasta`, em qualquer categoria."""
    if not pasta.is_dir():
        return set()
    return {nome_da_skill(arquivo) for arquivo in pasta.rglob("SKILL.md")}


def skills_desligadas(pasta_do_perfil: Path, pasta_da_consultoria: Path) -> list[str]:
    """Todas as skills do perfil menos as da consultoria e as que o Hermes não deixa desligar.

    O perfil nasce de `hermes profile create --clone` com as skills genéricas do
    Hermes (programação, e-mail, mídia, produtividade). Elas entram no índice que
    o agente lê em todo turno e não têm nada a ver com o trabalho dele.
    """
    genericas = nomes_das_skills(pasta_do_perfil) - nomes_das_skills(
        pasta_da_consultoria
    )
    return sorted(genericas - ESSENCIAIS)


def servidor_mise(venv: Path, raiz: Path) -> dict[str, Any]:
    """A entrada `mcp_servers.mise`, apontada para esta cópia do repositório."""
    return {
        "command": str(venv / "bin" / "python"),
        "args": ["-m", "gateway.principal"],
        "env": {
            "MISE_PLANILHA": str(raiz / "dados" / "despensa_dona_maria.xlsx"),
            "MISE_DOSSIE": str(raiz / ".estado" / "dossie.db"),
            "MISE_AUDITORIA": str(raiz / ".estado" / "auditoria.jsonl"),
        },
        "timeout": 120,
        "connect_timeout": ESPERA_PARA_CONECTAR_S,
    }


def configurar(
    dados: MutableMapping[str, Any], venv: Path, raiz: Path, perfil: Path
) -> None:
    """As três mudanças no config já carregado: servidor, overlay e skills desligadas."""
    servidores = dados.get("mcp_servers")
    if not isinstance(servidores, dict):
        servidores = dados["mcp_servers"] = {}
    servidores["mise"] = servidor_mise(venv, raiz)

    overlay = raiz / "hermes" / "config.overlay.yaml"
    if overlay.exists():
        fundir(dados, yaml.safe_load(overlay.read_text(encoding="utf-8")) or {})

    if not isinstance(dados.get("skills"), dict):
        dados["skills"] = {}
    dados["skills"]["disabled"] = skills_desligadas(
        perfil / "skills", raiz / "hermes" / "skills"
    )


def _carregar(config: Path) -> tuple[MutableMapping[str, Any], Callable[[Any], None]]:
    """O config e quem o escreve de volta, preservando comentários e ordem quando dá.

    Reescrever o arquivo com outro formato apagaria os comentários que o `--clone`
    trouxe; por isso ruamel primeiro, e o PyYAML só se ele faltar.
    """
    texto = config.read_text(encoding="utf-8") if config.exists() else ""
    try:
        from ruamel.yaml import YAML
    except ImportError:
        dados = yaml.safe_load(texto) or {}

        def escrever_simples(d: Any) -> None:
            config.write_text(
                yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8"
            )

        return dados, escrever_simples

    ruamel = YAML()
    ruamel.preserve_quotes = True
    dados = ruamel.load(texto) or {}

    def escrever(d: Any) -> None:
        with config.open("w", encoding="utf-8") as arquivo:
            ruamel.dump(d, arquivo)

    return dados, escrever


def main(argv: list[str]) -> int:
    config, venv, raiz = (Path(a) for a in argv[1:4])
    dados, escrever = _carregar(config)
    configurar(dados, venv, raiz, config.parent)
    escrever(dados)

    modelo = (dados.get("model") or {}).get("default", "?")
    esforco = (dados.get("agent") or {}).get("reasoning_effort", "?")
    desligadas = len(dados["skills"]["disabled"])
    print(
        f"mcp_servers.mise -> {dados['mcp_servers']['mise']['command']} -m gateway.principal"
    )
    print(f"overlay aplicado -> modelo {modelo}, esforço {esforco}")
    print(f"skills genéricas desligadas: {desligadas}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
