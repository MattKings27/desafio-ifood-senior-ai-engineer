"""O `make verificar`: cada conferência com uma máquina falsa, e o script inteiro de fora.

Cada teste parte de uma máquina em que tudo está certo e estraga uma coisa só.
A máquina é falsa de ponta a ponta: um repositório mínimo e uma pasta pessoal
num diretório temporário, comandos que respondem o que o teste manda, portas e
servidores de mentira. Nada aqui lê o `~/.hermes` de quem roda os testes nem
encosta nas portas 3000, 8777 e 8642.
"""

from __future__ import annotations

import http.server
import json
import os
import socket
import subprocess
import sys
import threading
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import verificar_ambiente as va

SCRIPT = Path(__file__).resolve().parents[1] / "verificar_ambiente.py"
COMMIT = va.COMMIT_DO_HERMES
# Montados por partes, para que este arquivo não carregue o que a higiene procura.
DISCO_DO_WINDOWS = "/" + "mnt/d/projetos/sabor"
SEGREDO_DA_ANTHROPIC = "sk-ant-api03-" + "x" * 40
CHAVE_PADRAO = "a" * 64
CHAVE_DO_PERFIL = "b" * 64
SAUDE_DO_HERMES = (
    200,
    b'{"status": "ok", "platform": "hermes-agent", "version": "0.21.4"}',
)


class Falsa:
    """As respostas da máquina falsa, que cada teste ajusta."""

    def __init__(self) -> None:
        self.versoes = {
            "node": "v24.19.0",
            "npm": "11.17.0",
            "git": "git version 2.43.0",
            "make": "GNU Make 4.3",
        }
        self.hermes = "Hermes Agent v0.21.4 (2026.9.21) · upstream ee8a919f"
        self.commit_do_hermes = COMMIT
        self.importa_o_gateway = True
        self.ocupadas: set[int] = set()
        self.respostas: dict[str, tuple[int, bytes]] = {
            "http://127.0.0.1:8642/health": SAUDE_DO_HERMES
        }
        self.pastas_do_hermes: list[str] = []
        self.config_na_pasta_do_hermes: list[str] = []

    def rodar(
        self, comando: Sequence[str], ambiente: Mapping[str, str] | None
    ) -> tuple[int, str]:
        nome = Path(comando[0]).name
        if nome == "hermes":
            pasta = Path((ambiente or {})["HERMES_HOME"])
            self.pastas_do_hermes.append(str(pasta))
            self.config_na_pasta_do_hermes.append(
                (pasta / "config.yaml").read_text(encoding="utf-8")
            )
            return 0, f"{self.hermes}\nInstall directory: /opt/hermes-agent\n"
        if nome == "git" and "rev-parse" in comando:
            return 0, self.commit_do_hermes + "\n"
        if nome == "python":
            return (0 if self.importa_o_gateway else 1), ""
        return 0, self.versoes[nome]

    def http(self, url: str, _prazo: float) -> tuple[int, bytes] | None:
        return self.respostas.get(url)


def _escrever(caminho: Path, texto: str) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def _executavel(caminho: Path) -> Path:
    _escrever(caminho, "#!/bin/sh\nexit 0\n").chmod(0o755)
    return caminho


def _repositorio(raiz: Path) -> None:
    _escrever(raiz / "hermes" / "SOUL.md", "o agente\n")
    for skill in ("diagnostico-despensa", "precificacao-delivery"):
        _escrever(
            raiz
            / "hermes"
            / "skills"
            / "consultoria-gastronomica"
            / skill
            / "SKILL.md",
            f"# {skill}\n",
        )
    plugin = raiz / "hermes" / "plugins" / "guardrail-numerico"
    _escrever(plugin / "__init__.py", "# guard-rail\n")
    _escrever(plugin / "plugin.yaml", "name: guardrail-numerico\n")
    _executavel(raiz / "mise" / ".venv" / "bin" / "python")
    _executavel(raiz / "webapp" / "node_modules" / ".bin" / "next")


def _perfil(raiz: Path, pasta: Path, dossie: Path) -> None:
    """O que o bootstrap deixa no perfil: as cópias, o config com o MCP e o `.env`."""
    for origem in (raiz / "hermes").rglob("*"):
        if origem.is_file():
            relativo = origem.relative_to(raiz / "hermes")
            _escrever(pasta / relativo, origem.read_text(encoding="utf-8"))
    _escrever(
        pasta / "config.yaml",
        "model:\n  default: claude-fable-5-1\nmcp_servers:\n  mise:\n    env:\n"
        f"      MISE_DOSSIE: {dossie}\n",
    )
    _escrever(
        pasta / ".env",
        f"ANTHROPIC_API_KEY={SEGREDO_DA_ANTHROPIC}\nAPI_SERVER_KEY={CHAVE_DO_PERFIL}\n",
    )


class Cenario:
    def __init__(self, tmp_path: Path) -> None:
        self.raiz = tmp_path / "repo"
        self.casa = tmp_path / "casa"
        self.hermes_home = self.casa / ".hermes"
        self.pasta_do_perfil = self.hermes_home / "profiles" / "sabor-da-maria"
        self.falsa = Falsa()
        self.ambiente: dict[str, str] = {"PATH": "/usr/bin"}
        self.sistema = "Linux"
        self.kernel = "6.8.0-45-generic"
        self.python = (3, 12, 3)
        self.caminhos: dict[str, str | None] = {
            nome: f"/usr/bin/{nome}"
            for nome in ("node", "npm", "git", "make", "hermes")
        }
        _repositorio(self.raiz)
        _escrever(self.hermes_home / ".env", f"API_SERVER_KEY={CHAVE_PADRAO}\n")
        _perfil(self.raiz, self.pasta_do_perfil, self.raiz / ".estado" / "dossie.db")

    def maquina(self) -> va.Maquina:
        return va.Maquina(
            raiz=self.raiz,
            casa=self.casa,
            ambiente=self.ambiente,
            sistema=self.sistema,
            kernel=self.kernel,
            versao_do_python=self.python,
            rodar=self.falsa.rodar,
            http=self.falsa.http,
            porta_ocupada=lambda porta: porta in self.falsa.ocupadas,
            macos="15.1",
            caminhos=dict(self.caminhos),
        )

    def itens(self) -> list[va.Item]:
        return [item for _, itens in va.conferir(self.maquina()) for item in itens]

    def falhas(self) -> list[va.Item]:
        return [item for item in self.itens() if item.ok is False]

    def unica_falha(self) -> va.Item:
        falhas = self.falhas()
        assert len(falhas) == 1, [f.texto for f in falhas]
        return falhas[0]


@pytest.fixture
def cenario(tmp_path: Path) -> Cenario:
    return Cenario(tmp_path)


def _textos(itens: list[va.Item]) -> str:
    return "\n".join(f"{item.texto} {item.conserto}" for item in itens)


# --------------------------------------------------------------------------- #
# A máquina inteira certa                                                      #
# --------------------------------------------------------------------------- #


def test_tudo_certo_nao_tem_nenhum_x(cenario: Cenario) -> None:
    assert cenario.falhas() == []
    textos = _textos(cenario.itens())
    assert "Hermes 0.21.4 (commit ee8a919f)" in textos
    assert "Node 24.19.0 e npm 11.17.0" in textos
    assert "make 4.3" in textos
    assert "ANTHROPIC_API_KEY em ~/.hermes/profiles/sabor-da-maria/.env" in textos
    assert "perfil sabor-da-maria: SOUL, 2 skills, guard-rail" in textos
    assert "servidor de API do agente no ar em :8642 (Hermes 0.21.4)" in textos


def test_nenhum_valor_de_chave_aparece(cenario: Cenario) -> None:
    textos = _textos(cenario.itens())
    for segredo in (SEGREDO_DA_ANTHROPIC, CHAVE_PADRAO, CHAVE_DO_PERFIL):
        assert segredo not in textos


# --------------------------------------------------------------------------- #
# Sistema e ferramentas                                                        #
# --------------------------------------------------------------------------- #


def test_macos_e_suportado(cenario: Cenario) -> None:
    cenario.sistema = "Darwin"
    assert cenario.falhas() == []
    assert "macOS 15.1" in _textos(cenario.itens())


def test_wsl2_e_suportado_e_avisa_do_disco_do_windows(cenario: Cenario) -> None:
    cenario.kernel = "6.6.87.2-microsoft-standard-WSL2"
    cenario.raiz = Path(DISCO_DO_WINDOWS)
    [sistema, *aviso] = va.conferir_sistema(cenario.maquina())
    assert sistema.ok is True
    assert sistema.texto == "Linux no WSL2"
    assert [a.ok for a in aviso] == [None]
    assert "disco do Windows" in aviso[0].texto


def test_wsl1_nao_serve(cenario: Cenario) -> None:
    cenario.kernel = "4.4.0-22621-Microsoft"
    falha = cenario.unica_falha()
    assert "WSL1" in falha.texto
    assert "wsl --set-version" in falha.conserto


def test_windows_sem_wsl_nao_serve(cenario: Cenario) -> None:
    cenario.sistema = "Windows"
    falha = va.conferir_sistema(cenario.maquina())[0]
    assert falha.ok is False
    assert "wsl --install" in falha.conserto


@pytest.mark.parametrize("versao", [(3, 10, 12), (3, 14, 0), (3, 9, 6)])
def test_python_fora_da_faixa(cenario: Cenario, versao: tuple[int, int, int]) -> None:
    cenario.python = versao
    falha = cenario.unica_falha()
    assert falha.texto.startswith(f"Python {'.'.join(map(str, versao))}")
    assert "3.12" in falha.conserto


@pytest.mark.parametrize("versao", [(3, 11, 0), (3, 13, 7)])
def test_python_na_faixa(cenario: Cenario, versao: tuple[int, int, int]) -> None:
    cenario.python = versao
    assert cenario.falhas() == []


def test_node_velho(cenario: Cenario) -> None:
    cenario.falsa.versoes["node"] = "v20.11.1"
    falha = cenario.unica_falha()
    assert "Node 20.11.1" in falha.texto
    assert "nodejs.org" in falha.conserto


def test_sem_node(cenario: Cenario) -> None:
    cenario.caminhos["node"] = None
    assert "Node não encontrado" in cenario.unica_falha().texto


def test_sem_npm(cenario: Cenario) -> None:
    cenario.caminhos["npm"] = None
    assert cenario.unica_falha().texto == "npm não encontrado"


@pytest.mark.parametrize("comando", ["git", "make"])
def test_sem_git_ou_make(cenario: Cenario, comando: str) -> None:
    # Sem o git, a versão do Hermes aparece sem o commit, e isso não é outra falha.
    cenario.caminhos[comando] = None
    falha = cenario.unica_falha()
    assert falha.texto == f"{comando} não encontrado"
    assert "xcode-select --install" in falha.conserto


# --------------------------------------------------------------------------- #
# O projeto                                                                    #
# --------------------------------------------------------------------------- #


def test_sem_o_ambiente_python(cenario: Cenario) -> None:
    (cenario.raiz / "mise" / ".venv" / "bin" / "python").unlink()
    falha = cenario.unica_falha()
    assert "mise/.venv" in falha.texto
    assert falha.conserto.startswith("make bootstrap")


def test_ambiente_que_nao_importa_o_gateway(cenario: Cenario) -> None:
    cenario.falsa.importa_o_gateway = False
    assert cenario.unica_falha().conserto == "scripts/preparar_ambiente.sh"


def test_sem_node_modules(cenario: Cenario) -> None:
    (cenario.raiz / "webapp" / "node_modules" / ".bin" / "next").unlink()
    assert cenario.unica_falha().conserto == "(cd webapp && npm ci)"


# --------------------------------------------------------------------------- #
# O Hermes                                                                     #
# --------------------------------------------------------------------------- #


def test_sem_hermes(cenario: Cenario) -> None:
    cenario.caminhos["hermes"] = None
    falha = cenario.unica_falha()
    assert falha.texto == "Hermes Agent não encontrado"
    assert falha.conserto == "make instalar-hermes"


def test_hermes_so_no_local_bin_vale_com_aviso(cenario: Cenario) -> None:
    cenario.caminhos["hermes"] = None
    _executavel(cenario.casa / ".local" / "bin" / "hermes")
    assert cenario.falhas() == []
    avisos = [i.texto for i in cenario.itens() if i.ok is None]
    assert any("não está no PATH" in aviso for aviso in avisos)


def test_hermes_de_outra_versao(cenario: Cenario) -> None:
    cenario.falsa.hermes = "Hermes Agent v0.22.1 (2026.10.2) · upstream 0123abcd"
    falha = cenario.unica_falha()
    assert "Hermes 0.22.1" in falha.texto
    assert falha.conserto == "make instalar-hermes FORCAR=1"


def test_hermes_na_versao_certa_em_outro_commit_passa_e_diz_qual(
    cenario: Cenario,
) -> None:
    cenario.falsa.commit_do_hermes = "0123abcd" * 5
    assert cenario.falhas() == []
    assert "no commit 0123abcd (o testado é o ee8a919f" in _textos(cenario.itens())


def test_a_versao_e_perguntada_numa_pasta_descartavel(cenario: Cenario) -> None:
    cenario.itens()
    [pasta] = cenario.falsa.pastas_do_hermes
    assert not pasta.startswith(str(cenario.casa))
    assert not Path(pasta).exists(), "a pasta descartável é apagada"
    assert cenario.falsa.config_na_pasta_do_hermes == ["updates:\n  check: false\n"]


# --------------------------------------------------------------------------- #
# A credencial da Anthropic                                                    #
# --------------------------------------------------------------------------- #


def _sem_credencial_no_perfil(cenario: Cenario) -> None:
    _escrever(cenario.pasta_do_perfil / ".env", f"API_SERVER_KEY={CHAVE_DO_PERFIL}\n")


def test_sem_credencial_nenhuma(cenario: Cenario) -> None:
    _sem_credencial_no_perfil(cenario)
    falha = cenario.unica_falha()
    assert falha.texto == "nenhuma credencial da Anthropic"
    assert falha.conserto.startswith("hermes setup model")


def test_credencial_so_no_padrao_com_o_perfil_criado_antes(cenario: Cenario) -> None:
    _sem_credencial_no_perfil(cenario)
    with (cenario.hermes_home / ".env").open("a", encoding="utf-8") as env:
        env.write(f'export ANTHROPIC_API_KEY="{SEGREDO_DA_ANTHROPIC}"\n')
    falha = cenario.unica_falha()
    assert "ANTHROPIC_API_KEY em ~/.hermes/.env" in falha.texto
    assert "criado antes dela" in falha.texto
    assert falha.conserto.startswith("hermes -p sabor-da-maria setup model")
    assert SEGREDO_DA_ANTHROPIC not in falha.texto + falha.conserto


def test_credencial_so_no_terminal(cenario: Cenario) -> None:
    _sem_credencial_no_perfil(cenario)
    cenario.ambiente["ANTHROPIC_API_KEY"] = SEGREDO_DA_ANTHROPIC
    falha = cenario.unica_falha()
    assert "só na variável ANTHROPIC_API_KEY deste terminal" in falha.texto
    assert "o make chat a usa" in falha.texto


def test_linha_vazia_nao_conta(cenario: Cenario) -> None:
    """O `hermes setup` que troca de credencial deixa as outras linhas vazias."""
    _escrever(
        cenario.pasta_do_perfil / ".env",
        f"ANTHROPIC_TOKEN=\nANTHROPIC_API_KEY=''\nAPI_SERVER_KEY={CHAVE_DO_PERFIL}\n",
    )
    assert cenario.unica_falha().texto == "nenhuma credencial da Anthropic"


def test_credencial_no_pool_do_perfil(cenario: Cenario) -> None:
    _sem_credencial_no_perfil(cenario)
    _escrever(
        cenario.pasta_do_perfil / "auth.json",
        json.dumps({"credential_pool": {"anthropic": [{"auth_type": "api_key"}]}}),
    )
    assert cenario.falhas() == []
    assert "no pool de ~/.hermes/profiles/sabor-da-maria/auth.json" in _textos(
        cenario.itens()
    )


def test_login_do_claude_code_vale(cenario: Cenario) -> None:
    _sem_credencial_no_perfil(cenario)
    _escrever(cenario.casa / ".claude" / ".credentials.json", "{}")
    assert cenario.falhas() == []
    assert "login do Claude Code" in _textos(cenario.itens())


def test_antes_do_bootstrap_a_credencial_do_padrao_basta(cenario: Cenario) -> None:
    for arquivo in sorted(cenario.pasta_do_perfil.rglob("*"), reverse=True):
        arquivo.unlink() if arquivo.is_file() else arquivo.rmdir()
    cenario.pasta_do_perfil.rmdir()
    _escrever(
        cenario.hermes_home / ".env", f"ANTHROPIC_API_KEY={SEGREDO_DA_ANTHROPIC}\n"
    )
    credencial = va.conferir_credencial(cenario.maquina())
    assert credencial.ok is True
    assert "o make bootstrap a copia para o perfil" in credencial.texto
    # Sem perfil, o que falta é o bootstrap, uma vez só.
    falhas = cenario.falhas()
    assert [f.conserto for f in falhas] == ["make bootstrap"]
    avisos = [i.texto for i in cenario.itens() if i.ok is None]
    assert "as chaves do servidor de API nascem no make bootstrap" in avisos


# --------------------------------------------------------------------------- #
# O perfil                                                                     #
# --------------------------------------------------------------------------- #


def test_perfil_apontando_para_outra_copia(cenario: Cenario, tmp_path: Path) -> None:
    config = cenario.pasta_do_perfil / "config.yaml"
    outra = tmp_path / "outra-copia" / ".estado" / "dossie.db"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            str(cenario.raiz / ".estado" / "dossie.db"), str(outra)
        ),
        encoding="utf-8",
    )
    falha = cenario.unica_falha()
    assert "aponta para outra cópia do repositório" in falha.texto
    assert str(tmp_path / "outra-copia") in falha.texto
    assert falha.conserto == "make bootstrap, rodado nesta pasta"


def test_perfil_sem_o_servidor_mcp(cenario: Cenario) -> None:
    _escrever(cenario.pasta_do_perfil / "config.yaml", "model: {}\n")
    assert "sem o servidor MCP mise" in cenario.unica_falha().texto


def test_skill_mudada_no_repositorio_pede_bootstrap(cenario: Cenario) -> None:
    skill = (
        cenario.raiz
        / "hermes"
        / "skills"
        / "consultoria-gastronomica"
        / "precificacao-delivery"
        / "SKILL.md"
    )
    skill.write_text("# precificacao-delivery, versão nova\n", encoding="utf-8")
    falha = cenario.unica_falha()
    assert "precificacao-delivery/SKILL.md" in falha.texto
    assert falha.conserto == "make bootstrap"


# --------------------------------------------------------------------------- #
# As chaves do servidor de API                                                 #
# --------------------------------------------------------------------------- #


def test_sem_a_chave_do_padrao(cenario: Cenario) -> None:
    _escrever(cenario.hermes_home / ".env", "")
    falha = cenario.unica_falha()
    assert "no perfil padrão" in falha.texto
    assert falha.conserto.startswith("hermes/api_da_agente.sh")


def test_chave_curta_nao_conta(cenario: Cenario) -> None:
    _escrever(
        cenario.pasta_do_perfil / ".env",
        f"ANTHROPIC_API_KEY={SEGREDO_DA_ANTHROPIC}\nAPI_SERVER_KEY=changeme\n",
    )
    assert "no perfil sabor-da-maria" in cenario.unica_falha().texto


def test_chave_do_perfil_igual_a_do_padrao(cenario: Cenario) -> None:
    _escrever(
        cenario.pasta_do_perfil / ".env",
        f"ANTHROPIC_API_KEY={SEGREDO_DA_ANTHROPIC}\nAPI_SERVER_KEY={CHAVE_PADRAO}\n",
    )
    assert "igual à do padrão" in cenario.unica_falha().texto


# --------------------------------------------------------------------------- #
# As portas                                                                    #
# --------------------------------------------------------------------------- #


def test_portas_em_uso_por_este_projeto(cenario: Cenario) -> None:
    cenario.falsa.ocupadas = {3000, 8777}
    for porta in (3000, 8777):
        cenario.falsa.respostas[f"http://127.0.0.1:{porta}/saude/vivo"] = (
            200,
            b'{"estado": "vivo"}',
        )
    assert cenario.falhas() == []
    assert "o make demo já está no ar" in _textos(cenario.itens())


def test_porta_ocupada_por_outro_programa(cenario: Cenario) -> None:
    cenario.falsa.ocupadas = {3000}
    cenario.falsa.respostas["http://127.0.0.1:3000/saude/vivo"] = (404, b"<html>")
    falha = cenario.unica_falha()
    assert "a porta 3000 está ocupada por outro programa" in falha.texto
    assert "ss -ltnp 'sport = :3000'" in falha.conserto


def test_no_macos_o_comando_para_achar_a_porta_e_o_lsof(cenario: Cenario) -> None:
    cenario.sistema = "Darwin"
    cenario.falsa.ocupadas = {8777}
    assert "lsof -nP -iTCP:8777" in cenario.unica_falha().conserto


def test_as_portas_seguem_as_variaveis_do_make_dev(cenario: Cenario) -> None:
    cenario.ambiente.update({"DEV_PORTA_WEB": "3001", "MISE_HTTP_PORT": "8778"})
    cenario.falsa.ocupadas = {3000, 8777}
    assert cenario.falhas() == []
    assert "porta 3001 livre" in _textos(cenario.itens())


def test_agente_fora_do_ar(cenario: Cenario) -> None:
    cenario.falsa.respostas.clear()
    falha = cenario.unica_falha()
    assert "nada responde em :8642" in falha.texto
    assert "make reiniciar-agente" in falha.conserto
    assert "hermes gateway run" in falha.conserto


def test_outra_coisa_na_porta_da_agente(cenario: Cenario) -> None:
    cenario.falsa.respostas["http://127.0.0.1:8642/health"] = (200, b"<html>oi</html>")
    assert "não é o servidor de API do Hermes" in cenario.unica_falha().texto


# --------------------------------------------------------------------------- #
# O relatório e o script inteiro                                               #
# --------------------------------------------------------------------------- #


def test_relatorio_mostra_o_conserto_embaixo_do_x(
    cenario: Cenario, capsys: pytest.CaptureFixture[str]
) -> None:
    cenario.caminhos["hermes"] = None
    assert va.main(cenario.maquina()) == 1
    saida = capsys.readouterr().out
    assert "✗ Hermes Agent não encontrado\n      → make instalar-hermes" in saida
    assert "1 item precisa de atenção" in saida


def test_relatorio_limpo_sai_com_zero(
    cenario: Cenario, capsys: pytest.CaptureFixture[str]
) -> None:
    assert va.main(cenario.maquina()) == 0
    saida = capsys.readouterr().out
    assert "✗" not in saida
    assert "Tudo certo. Agora: make demo" in saida


@pytest.mark.parametrize(
    ("linha", "valor"),
    [
        ("NOME=valor", "valor"),
        ("export NOME=valor", "valor"),
        ('NOME="com espaço" # comentário', "com espaço"),
        ("NOME='simples'", "simples"),
        ("NOME=valor # comentário", "valor"),
        ("NOME=", ""),
        ("# NOME=comentado", ""),
    ],
)
def test_leitor_de_env(tmp_path: Path, linha: str, valor: str) -> None:
    assert va.valor_no_env(_escrever(tmp_path / ".env", linha + "\n"), "NOME") == valor


def test_no_env_vale_a_ultima_linha(tmp_path: Path) -> None:
    env = _escrever(tmp_path / ".env", "NOME=primeira\nNOME=segunda\n")
    assert va.valor_no_env(env, "NOME") == "segunda"


def _porta_fechada() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def agente_falsa() -> Iterator[str]:
    """Um servidor de API do Hermes de mentira, numa porta livre."""

    class Saude(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            corpo = SAUDE_DO_HERMES[1]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *_args: object) -> None:
            return None

    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Saude)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{servidor.server_address[1]}"
    finally:
        servidor.shutdown()
        servidor.server_close()


def test_o_script_inteiro_so_le(tmp_path: Path, agente_falsa: str) -> None:
    """De fora: numa casa falsa, sem Hermes, com uma credencial que não pode vazar."""
    casa = tmp_path / "casa"
    _escrever(casa / ".hermes" / ".env", f"ANTHROPIC_API_KEY={SEGREDO_DA_ANTHROPIC}\n")
    antes = sorted(str(p) for p in casa.rglob("*"))
    binarios = tmp_path / "bin"
    for nome, versao in (
        ("node", "v22.9.0"),
        ("npm", "10.8.3"),
        ("git", "git version 2.47.0"),
    ):
        _escrever(binarios / nome, f"#!/bin/sh\necho '{versao}'\n").chmod(0o755)
    feito = subprocess.run(
        [sys.executable, str(SCRIPT)],
        env={
            "HOME": str(casa),
            "PATH": os.pathsep.join([str(binarios), "/usr/bin", "/bin"]),
            "TMPDIR": str(tmp_path),
            "DEV_PORTA_WEB": str(_porta_fechada()),
            "MISE_HTTP_PORT": str(_porta_fechada()),
            "MISE_HERMES_URL": agente_falsa,
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )
    assert feito.returncode == 1, feito.stdout + feito.stderr
    saida = feito.stdout
    assert "Node 22.9.0 e npm 10.8.3" in saida
    assert "✗ Hermes Agent não encontrado\n      → make instalar-hermes" in saida
    assert (
        "credencial da Anthropic presente (ANTHROPIC_API_KEY em ~/.hermes/.env)"
        in saida
    )
    assert "servidor de API do agente no ar" in saida
    assert SEGREDO_DA_ANTHROPIC not in saida + feito.stderr
    assert sorted(str(p) for p in casa.rglob("*")) == antes, (
        "verificar não escreve nada"
    )


def test_o_makefile_expoe_o_alvo() -> None:
    makefile = (SCRIPT.parents[1] / "Makefile").read_text(encoding="utf-8")
    assert "python3 scripts/verificar_ambiente.py" in makefile
    assert "\nverificar:  ## " in makefile


def test_as_versoes_batem_com_o_instalador() -> None:
    instalador = (SCRIPT.parent / "instalar_hermes.sh").read_text(encoding="utf-8")
    assert f'COMMIT="{va.COMMIT_DO_HERMES}"' in instalador
    assert f'VERSAO="{va.VERSAO_DO_HERMES}"' in instalador
