#!/usr/bin/env python3
"""Confere se esta máquina roda o Sabor da Maria e diz o comando que conserta cada item.

    make verificar                      # o mesmo que: python3 scripts/verificar_ambiente.py

Cada linha sai com ✓ ou ✗; embaixo de cada ✗ vem o comando que resolve. As
linhas com · são só informação. Sai com 0 quando não há ✗, e com 1 quando há.

O que confere, na ordem em que quem acabou de clonar vai precisando:

1. o sistema (Linux, macOS ou o WSL2 no Windows);
2. Python 3.11 a 3.13, Node 22 ou mais novo com npm, git e make;
3. o ambiente Python do projeto e as dependências da interface;
4. o Hermes Agent e a versão dele (a testada é a 0.21.4, commit ee8a919f);
5. a credencial da Anthropic, só a presença, onde o agente a procura;
6. o perfil do agente que o `make bootstrap` cria, apontando para esta cópia;
7. as duas chaves do servidor de API do Hermes, só a presença;
8. as portas 3000 (interface), 8777 (API do motor) e 8642 (servidor de API do
   agente): livres, ou em uso por este projeto.

Só lê. Nenhum valor de chave é impresso, nem guardado além da conferência. O
`hermes --version` roda numa pasta descartável, com a consulta ao GitHub
desligada: perguntar a versão não sai para a rede nem escreve no `~/.hermes`.

Usa só a biblioteca padrão, e roda no Python do sistema: é o comando que diz o
que falta antes de existir o ambiente do projeto. Por isso lê os `.env` com um
leitor pequeno daqui, e não com o `gateway.hermes_cliente`, que mora nesse
ambiente. O mesmo motivo mantém a sintaxe de Python 3.8: num sistema com um
Python velho, o script roda e diz qual versão falta, em vez de quebrar.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Só para quem lê e para o mypy: com o `from __future__ import annotations`,
    # nenhuma anotação é avaliada, e `tuple[...] | None` em tempo de execução
    # quebraria num Python 3.8 antes de dizer que ele é velho.
    from collections.abc import Callable, Mapping, Sequence

    Rodar = Callable[[Sequence[str], Mapping[str, str] | None], tuple[int, str]]
    Http = Callable[[str, float], tuple[int, bytes] | None]

RAIZ = Path(__file__).resolve().parents[1]

VERSAO_DO_HERMES = "0.21.4"
COMMIT_DO_HERMES = "ee8a919fd2769166d45ebf67f45ff5b1acec69fe"
PERFIL_PADRAO = "sabor-da-maria"
PYTHON_MINIMO = (3, 11)
PYTHON_ACIMA_DO_MAXIMO = (3, 14)
NODE_MINIMO = 22

#: Onde o Hermes procura a credencial da Anthropic, em ordem (agent/anthropic_credentials.py).
NOMES_DA_CREDENCIAL = (
    "ANTHROPIC_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_API_KEY",
)
NOME_DA_CHAVE_DA_API = "API_SERVER_KEY"
#: O Hermes só abre a porta com 16 caracteres ou mais (gateway.hermes_cliente).
TAMANHO_MINIMO_DA_CHAVE = 16


@dataclass
class Item:
    """Uma linha do relatório: ✓ (True), ✗ (False) ou · (None, só informação)."""

    ok: bool | None
    texto: str
    conserto: str = ""


@dataclass
class Maquina:
    """O que se lê da máquina. Os testes trocam cada peça por uma falsa."""

    raiz: Path
    casa: Path
    ambiente: Mapping[str, str]
    sistema: str
    kernel: str
    versao_do_python: tuple[int, int, int]
    rodar: Rodar
    http: Http
    porta_ocupada: Callable[[int], bool]
    macos: str = ""
    caminhos: dict[str, str | None] = field(default_factory=dict)

    def achar(self, comando: str) -> str | None:
        if comando not in self.caminhos:
            self.caminhos[comando] = shutil.which(
                comando, path=self.ambiente.get("PATH", os.defpath)
            )
        return self.caminhos[comando]

    @property
    def hermes_home(self) -> Path:
        valor = self.ambiente.get("HERMES_HOME", "").strip()
        return Path(valor).expanduser() if valor else self.casa / ".hermes"

    @property
    def perfil(self) -> str:
        return self.ambiente.get("PERFIL_HERMES", "").strip() or PERFIL_PADRAO

    @property
    def pasta_do_perfil(self) -> Path:
        return self.hermes_home / "profiles" / self.perfil

    def curto(self, caminho: Path) -> str:
        """`~/.hermes/.env` em vez do caminho inteiro: a pasta pessoal não interessa a ninguém."""
        texto, casa = str(caminho), str(self.casa)
        return "~" + texto[len(casa) :] if texto.startswith(casa + os.sep) else texto

    @property
    def e_macos(self) -> bool:
        return self.sistema == "Darwin"


# --------------------------------------------------------------------------- #
# Leitores pequenos                                                            #
# --------------------------------------------------------------------------- #


def valor_no_env(caminho: Path, nome: str) -> str:
    """O valor de `nome` num `.env`, do jeito que o Hermes lê: vale a última linha.

    `export` na frente, comentário no fim e aspas. Um arquivo que não existe, ou
    que não se deixa ler, é um valor vazio: aqui só importa se há valor.
    """
    try:
        texto = caminho.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""
    achado = ""
    for bruta in texto.splitlines():
        linha = bruta.strip()
        if not linha or linha.startswith("#"):
            continue
        if linha.startswith("export "):
            linha = linha[len("export ") :].lstrip()
        chave, separador, valor = linha.partition("=")
        if not separador or chave.strip() != nome:
            continue
        valor = valor.strip()
        if valor[:1] in ("'", '"') and valor[:1] in valor[1:]:
            valor = valor[1 : valor.index(valor[0], 1)]
        else:
            valor = re.split(r"\s+#", valor, maxsplit=1)[0].strip()
        achado = valor
    return achado


def credencial_no_pool(caminho: Path) -> bool:
    """O `auth.json` do Hermes tem uma credencial da Anthropic no pool (`hermes auth add`)."""
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    pool = dados.get("credential_pool") if isinstance(dados, dict) else None
    anthropic = pool.get("anthropic") if isinstance(pool, dict) else None
    return isinstance(anthropic, list) and len(anthropic) > 0


def mise_dossie_do_perfil(config: Path) -> str | None:
    """Para onde o servidor MCP `mise` do perfil aponta (a linha que o bootstrap escreve)."""
    try:
        texto = config.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    achado = re.search(r"^\s*MISE_DOSSIE:\s*(.+?)\s*$", texto, flags=re.MULTILINE)
    return achado.group(1).strip("'\"") if achado else None


def primeira_versao(texto: str) -> str:
    """A versão no texto: 4.3 em "GNU Make 4.3", 24.19.0 em "v24.19.0"."""
    achado = re.search(r"\d+\.\d+(?:\.\d+)?", texto)
    return achado.group(0) if achado else ""


def iguais(a: Path, b: Path) -> bool:
    try:
        return a.read_bytes() == b.read_bytes()
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# As conferências                                                              #
# --------------------------------------------------------------------------- #


def conferir_sistema(m: Maquina) -> list[Item]:
    if m.e_macos:
        return [Item(True, f"macOS {m.macos}".strip())]
    if m.sistema != "Linux":
        return [
            Item(
                False,
                f"sistema {m.sistema or 'desconhecido'}: o projeto roda em Linux, macOS ou no WSL2",
                "no Windows, instale o WSL2 (no PowerShell: wsl --install) e rode tudo dentro dele",
            )
        ]
    kernel = m.kernel.lower()
    if "microsoft" not in kernel:
        return [Item(True, "Linux")]
    if "wsl2" not in kernel and "microsoft-standard" not in kernel:
        return [
            Item(
                False,
                "WSL1: o projeto precisa do WSL2",
                "no PowerShell: wsl --set-version <sua distribuição> 2",
            )
        ]
    itens = [Item(True, "Linux no WSL2")]
    if re.match(r"^/mnt/[a-z]/", str(m.raiz)):
        itens.append(
            Item(
                None,
                "o repositório está num disco do Windows: funciona, mas o primeiro build e os "
                "testes ficam mais lentos; clonado dentro do Linux (em ~), tudo vai mais rápido",
            )
        )
    return itens


def conferir_python(m: Maquina) -> Item:
    versao = ".".join(map(str, m.versao_do_python))
    if PYTHON_MINIMO <= m.versao_do_python[:2] < PYTHON_ACIMA_DO_MAXIMO:
        return Item(True, f"Python {versao}")
    return Item(
        False,
        f"Python {versao}: o projeto e o Hermes pedem do 3.11 ao 3.13",
        "instale o Python 3.12 (python.org, ou o gerenciador de pacotes do sistema) "
        "e rode de novo",
    )


def _versao_do_comando(m: Maquina, comando: str) -> str | None:
    caminho = m.achar(comando)
    if caminho is None:
        return None
    codigo, saida = m.rodar([caminho, "--version"], None)
    return primeira_versao(saida) if codigo == 0 else ""


def conferir_node(m: Maquina) -> list[Item]:
    conserto = "instale o Node 22 ou mais novo, que traz o npm: https://nodejs.org (ou nvm install 22)"
    node = _versao_do_comando(m, "node")
    if node is None:
        return [
            Item(
                False,
                "Node não encontrado: a interface pede o 22 ou mais novo",
                conserto,
            )
        ]
    if not node or int(node.split(".")[0]) < NODE_MINIMO:
        return [
            Item(
                False,
                f"Node {node or 'de versão desconhecida'}: a interface pede o 22 ou mais novo",
                conserto,
            )
        ]
    npm = _versao_do_comando(m, "npm")
    if npm is None:
        return [Item(True, f"Node {node}"), Item(False, "npm não encontrado", conserto)]
    return [Item(True, f"Node {node} e npm {npm}")]


def conferir_ferramenta(m: Maquina, comando: str, conserto: str) -> Item:
    versao = _versao_do_comando(m, comando)
    if versao is None:
        return Item(False, f"{comando} não encontrado", conserto)
    return Item(True, f"{comando} {versao}".strip())


def conferir_projeto(m: Maquina) -> list[Item]:
    itens = []
    python = m.raiz / "mise" / ".venv" / "bin" / "python"
    if not os.access(str(python), os.X_OK):
        itens.append(
            Item(
                False,
                "ambiente Python do projeto ainda não existe (mise/.venv)",
                "make bootstrap (sem o Hermes: scripts/preparar_ambiente.sh)",
            )
        )
    else:
        codigo, _ = m.rodar([str(python), "-c", "import gateway.http"], None)
        if codigo == 0:
            itens.append(
                Item(
                    True, "ambiente Python do projeto (mise/.venv), com os seis pacotes"
                )
            )
        else:
            itens.append(
                Item(
                    False,
                    "o ambiente Python do projeto não importa o gateway",
                    "scripts/preparar_ambiente.sh",
                )
            )
    if (m.raiz / "webapp" / "node_modules" / ".bin" / "next").exists():
        itens.append(Item(True, "dependências da interface (webapp/node_modules)"))
    else:
        itens.append(
            Item(
                False,
                "dependências da interface não instaladas",
                "(cd webapp && npm ci)",
            )
        )
    return itens


def achar_hermes(m: Maquina) -> tuple[str | None, bool]:
    """O comando `hermes` e se ele está no PATH (o Makefile também olha o ~/.local/bin)."""
    no_path = m.achar("hermes")
    if no_path:
        return no_path, True
    local = m.casa / ".local" / "bin" / "hermes"
    return (str(local), False) if os.access(str(local), os.X_OK) else (None, False)


def versao_do_hermes(m: Maquina, comando: str) -> tuple[str, Path | None]:
    """A versão e a pasta de instalação, perguntadas numa pasta do Hermes descartável."""
    with tempfile.TemporaryDirectory(prefix="versao-do-hermes.") as casa_falsa:
        (Path(casa_falsa) / "config.yaml").write_text(
            "updates:\n  check: false\n", encoding="utf-8"
        )
        ambiente = dict(m.ambiente)
        ambiente["HERMES_HOME"] = casa_falsa
        codigo, saida = m.rodar([comando, "--version"], ambiente)
    if codigo != 0:
        return "", None
    achado = re.search(r"v(\d+\.\d+\.\d+)", saida)
    pasta = re.search(r"^Install directory:\s*(.+?)\s*$", saida, flags=re.MULTILINE)
    return (achado.group(1) if achado else ""), (
        Path(pasta.group(1)) if pasta else None
    )


def conferir_hermes(m: Maquina) -> list[Item]:
    comando, no_path = achar_hermes(m)
    if comando is None:
        return [Item(False, "Hermes Agent não encontrado", "make instalar-hermes")]
    versao, pasta = versao_do_hermes(m, comando)
    if versao != VERSAO_DO_HERMES:
        return [
            Item(
                False,
                f"Hermes {versao or 'de versão desconhecida'}: o projeto foi testado na "
                f"{VERSAO_DO_HERMES} (commit {COMMIT_DO_HERMES[:8]})",
                "make instalar-hermes FORCAR=1",
            )
        ]
    commit = ""
    git = m.achar("git")
    if pasta is not None and git:
        codigo, saida = m.rodar([git, "-C", str(pasta), "rev-parse", "HEAD"], None)
        commit = saida.strip() if codigo == 0 else ""
    if not commit or commit == COMMIT_DO_HERMES:
        detalhe = f"commit {COMMIT_DO_HERMES[:8]}" if commit else "a versão testada"
        itens = [Item(True, f"Hermes {versao} ({detalhe})")]
    else:
        itens = [
            Item(
                True,
                f"Hermes {versao}, no commit {commit[:8]} (o testado é o {COMMIT_DO_HERMES[:8]}; "
                "make instalar-hermes FORCAR=1 o fixa)",
            )
        ]
    if not no_path:
        itens.append(
            Item(
                None,
                "o comando hermes não está no PATH deste terminal: abra um terminal novo, ou "
                'rode export PATH="$HOME/.local/bin:$PATH"',
            )
        )
    return itens


def _credencial_em_env(m: Maquina, caminho: Path) -> str | None:
    for nome in NOMES_DA_CREDENCIAL:
        if valor_no_env(caminho, nome):
            return f"{nome} em {m.curto(caminho)}"
    return None


def _credencial_no_pool(m: Maquina, pasta: Path) -> str | None:
    auth = pasta / "auth.json"
    return f"no pool de {m.curto(auth)}" if credencial_no_pool(auth) else None


def conferir_credencial(m: Maquina) -> Item:
    """A credencial da Anthropic, só a presença, onde o perfil do agente a procura.

    O chat da web roda no gateway do Hermes, que atende cada perfil com as
    credenciais do próprio perfil (agent/secret_scope.py, get_secret): a chave
    que só existe no `~/.hermes/.env`, ou só neste terminal, não chega ao
    agente. O `make bootstrap` cria o perfil como cópia do padrão, `.env`
    junto; por isso a ordem é a chave primeiro, o bootstrap depois.
    """
    perfil, pasta = m.perfil, m.pasta_do_perfil
    do_claude_code = (
        "o login do Claude Code, que o Hermes aproveita"
        if (m.casa / ".claude" / ".credentials.json").is_file()
        else None
    )
    do_padrao = _credencial_em_env(m, m.hermes_home / ".env") or _credencial_no_pool(
        m, m.hermes_home
    )
    do_ambiente = next(
        (
            f"só na variável {nome} deste terminal"
            for nome in NOMES_DA_CREDENCIAL
            if m.ambiente.get(nome, "").strip()
        ),
        None,
    )
    configurar = (
        "hermes setup model (escolha Anthropic e cole a chave), e depois make bootstrap"
    )

    if not pasta.is_dir():
        if do_padrao:
            return Item(
                True,
                f"credencial da Anthropic presente ({do_padrao}); "
                "o make bootstrap a copia para o perfil do agente",
            )
        if do_claude_code:
            return Item(True, f"credencial da Anthropic presente ({do_claude_code})")
        if do_ambiente:
            return Item(
                False,
                f"a credencial da Anthropic está {do_ambiente}, e o perfil do agente nasce "
                "do ~/.hermes/.env",
                configurar,
            )
        return Item(False, "nenhuma credencial da Anthropic", configurar)

    do_perfil = (
        _credencial_em_env(m, pasta / ".env")
        or _credencial_no_pool(m, pasta)
        or do_claude_code
    )
    if do_perfil:
        return Item(
            True,
            f"credencial da Anthropic presente para o perfil {perfil} ({do_perfil})",
        )
    no_perfil = (
        f"hermes -p {perfil} setup model (escolha Anthropic e cole a chave), "
        "e depois make bootstrap"
    )
    if do_padrao:
        return Item(
            False,
            f"a credencial da Anthropic está no perfil padrão ({do_padrao}), mas o perfil "
            f"{perfil} foi criado antes dela e não a tem: o chat da web não a enxerga",
            no_perfil,
        )
    if do_ambiente:
        return Item(
            False,
            f"a credencial da Anthropic está {do_ambiente}: o make chat a usa, mas o chat "
            "da web não a enxerga",
            no_perfil,
        )
    return Item(False, "nenhuma credencial da Anthropic", configurar)


def conferir_perfil(m: Maquina) -> list[Item]:
    perfil, pasta = m.perfil, m.pasta_do_perfil
    if not pasta.is_dir():
        return [
            Item(
                False, f"o perfil {perfil} do agente ainda não existe", "make bootstrap"
            )
        ]

    apontado = mise_dossie_do_perfil(pasta / "config.yaml")
    esperado = m.raiz / ".estado" / "dossie.db"
    if apontado is None:
        return [
            Item(
                False,
                f"o perfil {perfil} existe, mas sem o servidor MCP mise",
                "make bootstrap",
            )
        ]
    if os.path.realpath(apontado) != os.path.realpath(str(esperado)):
        outra = Path(apontado).parent.parent
        return [
            Item(
                False,
                f"o perfil {perfil} aponta para outra cópia do repositório ({m.curto(outra)}): "
                "o agente e as telas leriam dossiês diferentes",
                "make bootstrap, rodado nesta pasta",
            )
        ]

    origem = m.raiz / "hermes"
    pares = [(origem / "SOUL.md", pasta / "SOUL.md")]
    skills = sorted((origem / "skills" / "consultoria-gastronomica").glob("*/SKILL.md"))
    pares += [
        (s, pasta / "skills" / "consultoria-gastronomica" / s.parent.name / "SKILL.md")
        for s in skills
    ]
    pares += [
        (
            origem / "plugins" / "guardrail-numerico" / nome,
            pasta / "plugins" / "guardrail-numerico" / nome,
        )
        for nome in ("__init__.py", "plugin.yaml")
    ]
    velhos = [
        str(r.relative_to(origem)) for r, instalado in pares if not iguais(r, instalado)
    ]
    if velhos:
        lista = ", ".join(velhos[:3]) + (
            f" e mais {len(velhos) - 3}" if len(velhos) > 3 else ""
        )
        return [
            Item(
                False,
                f"o perfil {perfil} está diferente do repositório ({lista})",
                "make bootstrap",
            )
        ]
    return [
        Item(
            True,
            f"perfil {perfil}: SOUL, {len(skills)} skills, guard-rail e o servidor MCP mise "
            "apontando para esta cópia",
        )
    ]


def conferir_chaves_da_api(m: Maquina) -> Item:
    padrao = valor_no_env(m.hermes_home / ".env", NOME_DA_CHAVE_DA_API)
    do_perfil = m.ambiente.get("MISE_HERMES_CHAVE", "").strip() or valor_no_env(
        m.pasta_do_perfil / ".env", NOME_DA_CHAVE_DA_API
    )
    gerar = (
        "hermes/api_da_agente.sh (gera o que faltar, sem mostrar, e reinicia o gateway)"
    )
    faltam = [
        onde
        for onde, valor in (
            ("no perfil padrão", padrao),
            (f"no perfil {m.perfil}", do_perfil),
        )
        if len(valor.strip()) < TAMANHO_MINIMO_DA_CHAVE
    ]
    if faltam:
        return Item(
            False,
            f"sem {NOME_DA_CHAVE_DA_API} utilizável {' e '.join(faltam)}: o chat da web não fala com o agente",
            gerar,
        )
    if padrao == do_perfil:
        return Item(
            False,
            f"a {NOME_DA_CHAVE_DA_API} do perfil {m.perfil} é igual à do padrão, e o Hermes a recusa ali",
            gerar,
        )
    return Item(
        True,
        f"chaves do servidor de API presentes no perfil padrão e no perfil {m.perfil}",
    )


def _descobrir_quem_usa(m: Maquina, porta: int) -> str:
    if m.e_macos:
        return f"lsof -nP -iTCP:{porta} -sTCP:LISTEN"
    return f"ss -ltnp 'sport = :{porta}'"


def _vivo(resposta: tuple[int, bytes] | None) -> bool:
    if resposta is None or resposta[0] != 200:
        return False
    try:
        return json.loads(resposta[1].decode("utf-8")).get("estado") == "vivo"
    except (ValueError, AttributeError):
        return False


def conferir_porta_do_projeto(m: Maquina, porta: int, papel: str) -> Item:
    if not m.porta_ocupada(porta):
        return Item(True, f"porta {porta} livre para a {papel}")
    if _vivo(m.http(f"http://127.0.0.1:{porta}/saude/vivo", 3.0)):
        return Item(
            True,
            f"porta {porta} em uso pela {papel} deste projeto (o make demo já está no ar)",
        )
    return Item(
        False,
        f"a porta {porta} está ocupada por outro programa, e o make demo precisa dela para a {papel}",
        f"descubra qual com {_descobrir_quem_usa(m, porta)} e encerre-o",
    )


def conferir_servidor_da_agente(m: Maquina) -> Item:
    url = (
        m.ambiente.get("MISE_HERMES_URL", "").strip() or "http://127.0.0.1:8642"
    ).rstrip("/")
    try:
        porta = urllib.parse.urlsplit(url).port or 8642
    except ValueError:
        porta = 8642
    resposta = m.http(f"{url}/health", 3.0)
    if resposta is None:
        return Item(
            False,
            f"nada responde em :{porta}: o gateway do Hermes, onde mora o servidor de API do "
            "agente, está parado (o chat da web fica sem o agente)",
            "make reiniciar-agente (sem systemd, deixe hermes gateway run aberto num terminal); "
            "diagnóstico completo: make agente-status",
        )
    try:
        dados = json.loads(resposta[1].decode("utf-8"))
    except ValueError:
        dados = {}
    if (
        resposta[0] == 200
        and isinstance(dados, dict)
        and dados.get("platform") == "hermes-agent"
    ):
        versao = dados.get("version") or "?"
        return Item(
            True, f"servidor de API do agente no ar em :{porta} (Hermes {versao})"
        )
    return Item(
        False,
        f"a porta {porta} responde, mas não é o servidor de API do Hermes",
        f"descubra quem a usa com {_descobrir_quem_usa(m, porta)}, libere-a e rode "
        "make reiniciar-agente",
    )


def _porta(m: Maquina, variavel: str, padrao: int) -> int:
    """As mesmas variáveis do `make dev` (scripts/dev.sh), para trocar de porta."""
    valor = m.ambiente.get(variavel, "").strip()
    return int(valor) if valor.isdigit() else padrao


def conferir(m: Maquina) -> list[tuple[str, list[Item]]]:
    """Todas as conferências, em seções, na ordem em que quem instala precisa delas."""
    instalar = {
        "git": "instale o git (apt install git; no macOS, xcode-select --install)",
        "make": "instale o make (apt install make; no macOS, xcode-select --install)",
    }
    agente = conferir_hermes(m)
    perfil = conferir_perfil(m)
    agente.append(conferir_credencial(m))
    agente.extend(perfil)
    if m.pasta_do_perfil.is_dir():
        agente.append(conferir_chaves_da_api(m))
    else:
        agente.append(
            Item(None, "as chaves do servidor de API nascem no make bootstrap")
        )
    return [
        ("Sistema", conferir_sistema(m)),
        (
            "Ferramentas",
            [conferir_python(m), *conferir_node(m)]
            + [conferir_ferramenta(m, c, instalar[c]) for c in ("git", "make")],
        ),
        ("Projeto", conferir_projeto(m)),
        ("Agente (Hermes)", agente),
        (
            "Portas",
            [
                conferir_porta_do_projeto(
                    m, _porta(m, "DEV_PORTA_WEB", 3000), "interface"
                ),
                conferir_porta_do_projeto(
                    m, _porta(m, "MISE_HTTP_PORT", 8777), "API do motor"
                ),
                conferir_servidor_da_agente(m),
            ],
        ),
    ]


# --------------------------------------------------------------------------- #
# A máquina de verdade                                                         #
# --------------------------------------------------------------------------- #


def _rodar(
    comando: Sequence[str], ambiente: Mapping[str, str] | None
) -> tuple[int, str]:
    try:
        feito = subprocess.run(
            list(comando),
            env=dict(ambiente) if ambiente is not None else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return feito.returncode, feito.stdout or ""


def _http(url: str, prazo: float) -> tuple[int, bytes] | None:
    """Status e corpo de um GET, ou `None` quando não há ninguém do outro lado."""
    pedido = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(pedido, timeout=prazo) as resposta:
            return resposta.status, resposta.read(65536)
    except urllib.error.HTTPError as erro:
        return erro.code, erro.read(65536)
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _porta_ocupada(porta: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", porta), timeout=0.5):
            return True
    except OSError:
        return False


def maquina_de_verdade() -> Maquina:
    return Maquina(
        raiz=RAIZ,
        casa=Path.home(),
        ambiente=os.environ,
        sistema=platform.system(),
        kernel=platform.release(),
        versao_do_python=tuple(sys.version_info[:3]),  # type: ignore[arg-type]
        rodar=_rodar,
        http=_http,
        porta_ocupada=_porta_ocupada,
        macos=platform.mac_ver()[0],
    )


def imprimir(secoes: list[tuple[str, list[Item]]], cores: bool) -> int:
    """O relatório; devolve quantos ✗ houve."""

    def pintar(codigo: str, texto: str) -> str:
        return f"\033[{codigo}m{texto}\033[0m" if cores else texto

    marcas = {
        True: pintar("32", "✓"),
        False: pintar("31", "✗"),
        None: pintar("36", "·"),
    }
    print("Sabor da Maria: conferindo o ambiente")
    falhas = 0
    for titulo, itens in secoes:
        print()
        print(pintar("1", titulo))
        for item in itens:
            print(f"  {marcas[item.ok]} {item.texto}")
            if item.ok is False:
                falhas += 1
                if item.conserto:
                    print(f"      {pintar('33', '→')} {item.conserto}")
    print()
    if falhas == 0:
        print(
            pintar("32", "Tudo certo. Agora: make demo, e abra http://localhost:3000")
        )
    else:
        quantos = "item precisa" if falhas == 1 else "itens precisam"
        print(
            pintar("31", f"{falhas} {quantos} de atenção.")
            + " Rode os comandos indicados, na ordem, e depois make verificar de novo."
        )
    return falhas


def main(maquina: Maquina | None = None) -> int:
    m = maquina or maquina_de_verdade()
    return 1 if imprimir(conferir(m), cores=sys.stdout.isatty()) else 0


if __name__ == "__main__":
    sys.exit(main())
