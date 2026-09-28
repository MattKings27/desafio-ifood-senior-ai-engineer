"""A chave do servidor de API e o estado do Hermes, numa pasta do Hermes de mentira.

Nenhum teste aqui encosta no `~/.hermes` de verdade: tudo roda num `tmp_path`,
com `HERMES_HOME` apontando para ele e um Hermes falso no lugar da rede. O que
mais importa: a chave nasce com modo 0600, é diferente em cada perfil, não é
regerada quando já existe e nunca sai no terminal.
"""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

import httpx
import pytest

from gateway import hermes_operacao as op
from gateway.hermes_cliente import ChaveAusente, ler_chave_do_env

PERFIL = "sabor-da-maria"
CHAVE = "chave-do-perfil-" + "a1" * 12


def _home(tmp_path: Path, *perfis: str) -> Path:
    home = tmp_path / "hermes"
    home.mkdir()
    for perfil in perfis:
        (home / "profiles" / perfil).mkdir(parents=True)
    return home


def _modo(caminho: Path) -> int:
    return stat.S_IMODE(caminho.stat().st_mode)


def _valor(caminho: Path) -> str:
    chave = ler_chave_do_env(caminho)
    assert chave is not None
    return chave.revelar()


# --------------------------------------------------------------------------- #
# Gerar a chave                                                                #
# --------------------------------------------------------------------------- #


def test_cria_o_env_com_modo_600(tmp_path: Path) -> None:
    home = _home(tmp_path)
    env = home / ".env"
    assert op.garantir_chave(env) is True
    assert _modo(env) == 0o600
    valor = _valor(env)
    assert len(valor) == 64
    int(valor, 16)  # hexadecimal


def test_acrescenta_sem_estragar_o_que_ja_havia(tmp_path: Path) -> None:
    home = _home(tmp_path)
    env = home / ".env"
    env.write_text("ANTHROPIC_OUTRA=1\n# comentário\nSEM_QUEBRA=fim", encoding="utf-8")
    env.chmod(0o600)
    assert op.garantir_chave(env) is True
    linhas = env.read_text(encoding="utf-8").splitlines()
    assert linhas[:3] == ["ANTHROPIC_OUTRA=1", "# comentário", "SEM_QUEBRA=fim"]
    assert linhas[3].startswith("API_SERVER_KEY=")


def test_chave_existente_nao_e_regerada_e_o_modo_aperta(tmp_path: Path) -> None:
    home = _home(tmp_path)
    env = home / ".env"
    env.write_text(f"API_SERVER_KEY={CHAVE}\n", encoding="utf-8")
    env.chmod(0o644)
    assert op.garantir_chave(env) is False
    assert _valor(env) == CHAVE
    assert _modo(env) == 0o600


def test_chave_existente_com_modo_certo_fica_como_esta(tmp_path: Path) -> None:
    home = _home(tmp_path)
    env = home / ".env"
    env.write_text(f"API_SERVER_KEY={CHAVE}\n", encoding="utf-8")
    env.chmod(0o600)
    antes = env.stat().st_mtime_ns
    assert op.garantir_chave(env) is False
    assert env.stat().st_mtime_ns == antes


@pytest.mark.parametrize("antiga", ["", "changeme", "curta"])
def test_chave_inutilizavel_ganha_uma_nova_no_fim(tmp_path: Path, antiga: str) -> None:
    """No `.env` vale a última linha: a nova passa por cima sem apagar a velha."""
    home = _home(tmp_path)
    env = home / ".env"
    env.write_text(f"API_SERVER_KEY={antiga}\n", encoding="utf-8")
    assert op.garantir_chave(env) is True
    assert len(_valor(env)) == 64


def test_arquivo_vazio_nao_ganha_linha_em_branco(tmp_path: Path) -> None:
    home = _home(tmp_path)
    env = home / ".env"
    env.write_text("", encoding="utf-8")
    op.garantir_chave(env)
    assert env.read_text(encoding="utf-8").startswith("API_SERVER_KEY=")


def test_perfil_inexistente_nao_vira_pasta_nova(tmp_path: Path) -> None:
    """Um perfil digitado errado não pode espalhar chave por onde o Hermes não olha."""
    home = _home(tmp_path)
    with pytest.raises(ChaveAusente, match="não existe"):
        op.garantir_chave(home / "profiles" / "digitado-errado" / ".env")
    assert not (home / "profiles" / "digitado-errado").exists()


def test_env_ilegivel_nao_e_sobrescrito(tmp_path: Path) -> None:
    home = _home(tmp_path)
    (home / ".env").mkdir()
    with pytest.raises(ChaveAusente, match="Não deu para ler"):
        op.garantir_chave(home / ".env")


def test_duas_chaves_diferentes_padrao_e_perfil(tmp_path: Path) -> None:
    home = _home(tmp_path, PERFIL)
    garantidas = op.garantir_chaves(PERFIL, home)
    assert [g.caminho for g in garantidas] == [home / ".env", home / "profiles" / PERFIL / ".env"]
    assert all(g.criada for g in garantidas)
    assert _valor(home / ".env") != _valor(home / "profiles" / PERFIL / ".env")
    assert not op.chaves_iguais(home, PERFIL)
    # de novo: nada muda
    antes = (_valor(home / ".env"), _valor(home / "profiles" / PERFIL / ".env"))
    assert not any(g.criada for g in op.garantir_chaves(PERFIL, home))
    assert (_valor(home / ".env"), _valor(home / "profiles" / PERFIL / ".env")) == antes


def test_perfil_de_avaliacao_ganha_chave_propria(tmp_path: Path) -> None:
    home = _home(tmp_path, PERFIL, f"{PERFIL}-avaliacao")
    op.garantir_chaves(PERFIL, home)
    op.garantir_chaves(f"{PERFIL}-avaliacao", home)
    valores = {
        _valor(home / ".env"),
        _valor(home / "profiles" / PERFIL / ".env"),
        _valor(home / "profiles" / f"{PERFIL}-avaliacao" / ".env"),
    }
    assert len(valores) == 3


def test_perfil_default_tem_uma_chave_so(tmp_path: Path) -> None:
    home = _home(tmp_path)
    assert [g.caminho for g in op.garantir_chaves("default", home)] == [home / ".env"]
    assert not op.chaves_iguais(home, "default")


def test_chaves_iguais_e_detectado(tmp_path: Path) -> None:
    home = _home(tmp_path, PERFIL)
    (home / ".env").write_text(f"API_SERVER_KEY={CHAVE}\n", encoding="utf-8")
    assert not op.chaves_iguais(home, PERFIL), "sem a do perfil não há o que comparar"
    (home / "profiles" / PERFIL / ".env").write_text(f"API_SERVER_KEY={CHAVE}\n", encoding="utf-8")
    assert op.chaves_iguais(home, PERFIL)


# --------------------------------------------------------------------------- #
# O processo do gateway                                                        #
# --------------------------------------------------------------------------- #


def _processo(proc: Path, pid: str, *args: str) -> None:
    pasta = proc / pid
    pasta.mkdir(parents=True)
    (pasta / "cmdline").write_bytes(b"\0".join(a.encode() for a in args) + b"\0")


def _proc(tmp_path: Path, com_gateway: bool = True) -> Path:
    proc = tmp_path / ("proc" if com_gateway else "proc-sem-gateway")
    if proc.exists():
        return proc
    proc.mkdir()
    if com_gateway:
        _processo(
            proc,
            "363",
            "/h/.hermes/hermes-agent/venv/bin/python",
            "-m",
            "hermes_cli.main",
            "gateway",
            "run",
        )
        _processo(proc, "900", "/usr/bin/python3", "/usr/local/bin/hermes", "gateway", "run")
    _processo(proc, "1741", "/x/venv/bin/python", "-m", "gateway.principal")
    _processo(proc, "1800", "/usr/bin/python3", "/usr/local/bin/hermes", "chat")
    _processo(proc, "1801", "/usr/bin/bash", "-c", "echo gateway run")
    (proc / "1802").mkdir()  # sem cmdline: processo que acabou no meio da leitura
    (proc / "self").mkdir()
    return proc


def test_acha_o_gateway_em_proc(tmp_path: Path) -> None:
    assert op.pids_do_gateway(_proc(tmp_path)) == [363, 900]


def test_sem_gateway_rodando(tmp_path: Path) -> None:
    assert op.pids_do_gateway(_proc(tmp_path, com_gateway=False)) == []


def test_fora_do_linux_nao_sabe(tmp_path: Path) -> None:
    assert op.pids_do_gateway(tmp_path / "nao-existe") is None


# --------------------------------------------------------------------------- #
# O modelo do perfil                                                           #
# --------------------------------------------------------------------------- #


def _config(home: Path, texto: str, perfil: str = PERFIL) -> None:
    pasta = home if perfil == "default" else home / "profiles" / perfil
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "config.yaml").write_text(texto, encoding="utf-8")


def test_le_modelo_esforco_e_reservas(tmp_path: Path) -> None:
    home = _home(tmp_path)
    _config(
        home,
        "model: {default: claude-opus-5, provider: anthropic}\n"
        "agent: {reasoning_effort: high}\n"
        "fallback_providers:\n  - {provider: anthropic, model: claude-opus-4-8}\n  - {provider: x}\n  - lixo\n",
    )
    info = op.ler_modelo(home, PERFIL)
    assert info == {
        "modelo": "claude-opus-5",
        "provedor": "anthropic",
        "esforco": "high",
        "reservas": ["claude-opus-4-8"],
    }
    assert op._linha_do_modelo(info, PERFIL) == (
        "modelo claude-opus-5 (anthropic), esforço high, reserva claude-opus-4-8"
    )


@pytest.mark.parametrize("texto", ["model: [\n", "- lista\n", "model: 3\nagent: 4\n"])
def test_config_torto(tmp_path: Path, texto: str) -> None:
    home = _home(tmp_path)
    _config(home, texto)
    info = op.ler_modelo(home, PERFIL)
    if info is not None:
        assert op._linha_do_modelo(info, PERFIL) == "modelo ? (?), esforço ?"
    else:
        assert op._linha_do_modelo(info, PERFIL).startswith("sem config.yaml")


def test_config_do_perfil_padrao_e_ausente(tmp_path: Path) -> None:
    home = _home(tmp_path)
    assert op.ler_modelo(home, PERFIL) is None
    _config(home, "model: {default: m}\n", perfil="default")
    assert op.ler_modelo(home, "default") == {
        "modelo": "m",
        "provedor": None,
        "esforco": None,
        "reservas": [],
    }


# --------------------------------------------------------------------------- #
# O relatório                                                                  #
# --------------------------------------------------------------------------- #


class Hermes:
    """Um servidor de API falso: `/health` e as sessões do perfil, com a chave dele."""

    def __init__(
        self, chave: str | None, *, falhas_ate_subir: int = 0, status_sessoes: int = 200
    ) -> None:
        self.chave = chave
        self.falhas_ate_subir = falhas_ate_subir
        self.status_sessoes = status_sessoes
        self.pedidos: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.pedidos.append(request)
        if self.falhas_ate_subir > 0:
            self.falhas_ate_subir -= 1
            raise httpx.ConnectError("Connection refused")
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "version": "0.21.4"})
        if request.url.path == f"/p/{PERFIL}/api/sessions":
            if request.headers.get("Authorization") != f"Bearer {self.chave}":
                return httpx.Response(401, json={"error": {"message": "Invalid gateway API key"}})
            return httpx.Response(self.status_sessoes, json={"data": []})
        return httpx.Response(404, json={"error": "Unknown or unconfigured profile"})


def _com_chaves(tmp_path: Path) -> Path:
    home = _home(tmp_path, PERFIL)
    (home / ".env").write_text("API_SERVER_KEY=" + "b2" * 32 + "\n", encoding="utf-8")
    (home / "profiles" / PERFIL / ".env").write_text(f"API_SERVER_KEY={CHAVE}\n", encoding="utf-8")
    _config(
        home,
        "model: {default: claude-opus-5, provider: anthropic}\nagent: {reasoning_effort: high}\n",
    )
    return home


async def _conferir(home: Path, hermes: Hermes, proc: Path, **opcoes: Any) -> op.Relatorio:
    opcoes.setdefault("ambiente", {})
    return await op.conferir(
        PERFIL, home=home, transporte=httpx.MockTransport(hermes), proc=proc, **opcoes
    )


async def test_tudo_pronto(tmp_path: Path) -> None:
    home = _com_chaves(tmp_path)
    hermes = Hermes(CHAVE)
    relatorio = await _conferir(home, hermes, _proc(tmp_path))
    assert relatorio.pronto
    assert relatorio.versao == "0.21.4"
    assert relatorio.primeira_falha is None
    textos = [linha.texto for linha in relatorio.linhas]
    assert textos[0] == "gateway do Hermes rodando (PID 363, 900)"
    assert any("aceitou a chave do perfil" in t for t in textos)
    assert textos[-1] == "modelo claude-opus-5 (anthropic), esforço high"
    assert "Authorization" not in hermes.pedidos[0].headers
    assert all(CHAVE not in t for t in textos)


async def test_nada_ligado(tmp_path: Path) -> None:
    home = _home(tmp_path, PERFIL)
    hermes = Hermes(None, falhas_ate_subir=99)
    relatorio = await _conferir(home, hermes, _proc(tmp_path, com_gateway=False))
    assert not relatorio.pronto
    assert relatorio.primeira_falha is not None
    assert relatorio.primeira_falha.startswith("gateway do Hermes parado")
    falhas = [linha.texto for linha in relatorio.linhas if linha.ok is False]
    assert any("sem API_SERVER_KEY no perfil padrão" in t for t in falhas)
    assert any("Sem chave para o perfil" in t for t in falhas)
    assert any("servidor de API fora do ar" in t for t in falhas)


async def test_porta_que_responde_torto(tmp_path: Path) -> None:
    home = _com_chaves(tmp_path)

    def quebrado(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "boom"}})

    relatorio = await op.conferir(
        PERFIL,
        home=home,
        ambiente={},
        transporte=httpx.MockTransport(quebrado),
        proc=_proc(tmp_path),
    )
    assert not relatorio.pronto
    assert any("HTTP 500" in linha.texto for linha in relatorio.linhas if linha.ok is False)


async def test_porta_no_ar_mas_sem_chave_do_perfil(tmp_path: Path) -> None:
    home = _com_chaves(tmp_path)
    (home / "profiles" / PERFIL / ".env").unlink()
    hermes = Hermes(CHAVE)
    relatorio = await _conferir(home, hermes, _proc(tmp_path))
    assert not relatorio.pronto
    assert relatorio.versao == "0.21.4"
    assert [pedido.url.path for pedido in hermes.pedidos] == ["/health"]


async def test_chave_recusada(tmp_path: Path) -> None:
    home = _com_chaves(tmp_path)
    relatorio = await _conferir(home, Hermes("outra-chave-qualquer-123"), _proc(tmp_path))
    assert not relatorio.pronto
    assert any(
        "recusou a chave" in (linha.texto) for linha in relatorio.linhas if linha.ok is False
    )


async def test_chave_da_variavel_e_o_aviso_de_chaves_iguais(tmp_path: Path) -> None:
    home = _com_chaves(tmp_path)
    (home / ".env").write_text(f"API_SERVER_KEY={CHAVE}\n", encoding="utf-8")
    relatorio = await _conferir(
        home, Hermes(CHAVE), _proc(tmp_path), ambiente={"MISE_HERMES_CHAVE": CHAVE}
    )
    textos = [linha.texto for linha in relatorio.linhas]
    assert f"chave do perfil {PERFIL} presente (MISE_HERMES_CHAVE)" in textos
    assert any("igual à do padrão" in t for t in textos)


async def test_espera_o_gateway_subir(tmp_path: Path) -> None:
    home = _com_chaves(tmp_path)
    cochilos: list[float] = []

    async def dormir(segundos: float) -> None:
        cochilos.append(segundos)

    relatorio = await _conferir(
        home, Hermes(CHAVE, falhas_ate_subir=2), _proc(tmp_path), esperar_s=90, dormir=dormir
    )
    assert relatorio.pronto
    assert cochilos == [2.0, 2.0]


async def test_desiste_quando_o_prazo_acaba(tmp_path: Path) -> None:
    home = _com_chaves(tmp_path)
    agora = [0.0]

    async def dormir(segundos: float) -> None:
        agora[0] += segundos

    relatorio = await _conferir(
        home,
        Hermes(CHAVE, falhas_ate_subir=99),
        _proc(tmp_path),
        esperar_s=5,
        dormir=dormir,
        relogio=lambda: agora[0],
    )
    assert not relatorio.pronto
    assert agora[0] == 6.0  # três cochilos de 2 s e desiste


async def test_fora_do_linux_nao_ha_linha_do_gateway(tmp_path: Path) -> None:
    home = _com_chaves(tmp_path)
    relatorio = await _conferir(home, Hermes(CHAVE), tmp_path / "sem-proc")
    assert not relatorio.linhas[0].texto.startswith("gateway")


# --------------------------------------------------------------------------- #
# Linha de comando                                                             #
# --------------------------------------------------------------------------- #


def test_garantir_chave_nunca_imprime_o_valor(tmp_path: Path, capsys) -> None:
    home = _home(tmp_path, PERFIL)
    ambiente = {"HERMES_HOME": str(home)}
    assert op.main(["garantir-chave", "--perfil", PERFIL], ambiente=ambiente) == 0
    saida = capsys.readouterr()
    valores = [_valor(home / ".env"), _valor(home / "profiles" / PERFIL / ".env")]
    for valor in valores:
        assert valor not in saida.out
        assert valor not in saida.err
    assert saida.out.count("chave nova") == 2
    assert op.main(["garantir-chave"], ambiente={**ambiente, "PERFIL_HERMES": PERFIL}) == 0
    assert capsys.readouterr().out.count("já existia") == 2


def test_perfil_clonado_depois_da_chave_do_padrao_ganha_a_sua(tmp_path: Path, capsys) -> None:
    """`hermes profile create --clone` copia o `.env` do padrão, chave junto."""
    home = _home(tmp_path, PERFIL)
    (home / ".env").write_text(f"API_SERVER_KEY={CHAVE}\n", encoding="utf-8")
    clonado = home / "profiles" / PERFIL / ".env"
    clonado.write_text(f"OUTRA_VARIAVEL=1\nAPI_SERVER_KEY={CHAVE}\n# fim\n", encoding="utf-8")
    clonado.chmod(0o600)
    assert op.main(["garantir-chave", "--perfil", PERFIL], ambiente={"HERMES_HOME": str(home)}) == 0
    saida = capsys.readouterr().out
    assert "chave trocada (era a do perfil padrão" in saida
    assert CHAVE not in saida
    assert _valor(home / ".env") == CHAVE, "a do padrão não muda"
    assert _valor(clonado) != CHAVE
    texto = clonado.read_text(encoding="utf-8")
    assert CHAVE not in texto, "o valor copiado do padrão não fica para trás"
    assert texto.startswith("OUTRA_VARIAVEL=1\n# fim\nAPI_SERVER_KEY=")
    assert _modo(clonado) == 0o600
    assert not op.chaves_iguais(home, PERFIL)


def test_trocar_chave_mexe_so_na_linha_dela(tmp_path: Path) -> None:
    home = _home(tmp_path)
    env = home / ".env"
    env.write_bytes(
        b"A=1\nexport API_SERVER_KEY=velha-velha-velha-1\nB=2\n  API_SERVER_KEY = de-novo\nC=3"
    )
    op.trocar_chave(env)
    linhas = env.read_text(encoding="utf-8").splitlines()
    assert linhas[:3] == ["A=1", "B=2", "C=3"]
    assert len(linhas) == 4
    assert linhas[3].startswith("API_SERVER_KEY=")
    assert len(_valor(env)) == 64
    assert _modo(env) == 0o600
    assert not (home / ".env.novo").exists()


def test_trocar_chave_de_arquivo_so_com_a_chave(tmp_path: Path) -> None:
    home = _home(tmp_path)
    env = home / ".env"
    env.write_text(f"API_SERVER_KEY={CHAVE}\n", encoding="utf-8")
    op.trocar_chave(env)
    assert env.read_text(encoding="utf-8").count("\n") == 1
    assert _valor(env) != CHAVE


@pytest.mark.parametrize("perfil", ["nao-existe", "../fora"])
def test_garantir_chave_perfil_ruim(tmp_path: Path, capsys, perfil: str) -> None:
    home = _home(tmp_path)
    assert op.main(["garantir-chave", "--perfil", perfil], ambiente={"HERMES_HOME": str(home)}) == 1
    assert capsys.readouterr().err.startswith("✗")


def _status(tmp_path: Path, home: Path, hermes: Hermes, *argv: str) -> int:
    ambiente = {"HERMES_HOME": str(home), "MISE_HERMES_URL": "http://127.0.0.1:8642"}
    return op.main(
        ["status", "--perfil", PERFIL, *argv],
        ambiente=ambiente,
        transporte=httpx.MockTransport(hermes),
        proc=_proc(tmp_path),
    )


def test_status_completo(tmp_path: Path, capsys) -> None:
    home = _com_chaves(tmp_path)
    assert _status(tmp_path, home, Hermes(CHAVE)) == 0
    saida = capsys.readouterr().out
    assert saida.startswith(f"Agente (Hermes) · perfil {PERFIL}")
    assert "✓ o servidor aceitou a chave do perfil" in saida
    assert CHAVE not in saida


def test_status_curto(tmp_path: Path, capsys, monkeypatch) -> None:
    home = _com_chaves(tmp_path)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    assert _status(tmp_path, home, Hermes(CHAVE), "--curto") == 0
    assert "agente pronto (Hermes 0.21.4" in capsys.readouterr().out
    assert _status(tmp_path, home, Hermes("recusada-0123456789"), "--curto") == 1
    saida = capsys.readouterr().out
    assert "agente indisponível" in saida
    assert "\033[31m" in saida


def test_status_perfil_invalido(tmp_path: Path, capsys) -> None:
    home = _home(tmp_path)
    assert op.main(["status", "--perfil", "../x"], ambiente={"HERMES_HOME": str(home)}) == 1
    assert "perfil inválido" in capsys.readouterr().err
