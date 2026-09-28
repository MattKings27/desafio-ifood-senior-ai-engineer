"""Operação do agente: a chave do servidor de API do Hermes e o estado dele, sem mostrar segredo.

Duas portas usam este módulo: a etapa "API do agente" do bootstrap
(`hermes/api_da_agente.sh`) e `make agente-status`.

    python -m gateway.hermes_operacao garantir-chave --perfil sabor-da-maria
    python -m gateway.hermes_operacao status --perfil sabor-da-maria [--esperar 90] [--curto]

São duas chaves, e a diferença importa. A do `~/.hermes/.env` (perfil padrão) é
a que faz o gateway abrir a porta 8642 quando sobe; sem ela não há servidor. A
do `.env` do perfil é a que autentica `/p/<perfil>/`; a do padrão dá 401 ali.
O Hermes relê o `.env` do perfil a cada pedido, então a chave do perfil vale na
hora; a do padrão só depois de reiniciar o gateway (`make reiniciar-agente`).

Nenhum caminho daqui imprime o valor de uma chave: ele sai do
`secrets.token_hex(32)` direto para o arquivo, que nasce com modo 0600.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import secrets
import sys
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import httpx
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from gateway.hermes_cliente import (
    NOME_DA_CHAVE,
    PERFIL_PADRAO,
    URL_PADRAO,
    VAR_PERFIL,
    VAR_URL,
    ChaveAusente,
    ChaveEncontrada,
    ClienteHermes,
    ErroDoHermes,
    HermesForaDoAr,
    TempoEsgotado,
    caminho_do_env,
    chave_utilizavel,
    descobrir_chave,
    hermes_home,
    ler_chave_do_env,
    validar_perfil,
)

#: 32 bytes = 64 caracteres hexadecimais, o dobro do mínimo que o Hermes aceita.
BYTES_DA_CHAVE: Final = 32
_SO_O_DONO: Final = 0o600
_INTERVALO_DE_ESPERA_S: Final = 2.0
_LINHA_DA_CHAVE: Final = re.compile(rb"^\s*(?:export\s+)?" + NOME_DA_CHAVE.encode() + rb"\s*=")

Dormir = Callable[[float], Awaitable[None]]
Relogio = Callable[[], float]


# --------------------------------------------------------------------------- #
# A chave                                                                      #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ChaveGarantida:
    """Uma das duas chaves: onde ficou, para que serve e se foi criada (ou trocada) agora."""

    caminho: Path
    papel: str
    criada: bool
    trocada: bool = False


def _termina_sem_quebra(caminho: Path) -> bool:
    try:
        with caminho.open("rb") as arquivo:
            arquivo.seek(0, os.SEEK_END)
            if arquivo.tell() == 0:
                return False
            arquivo.seek(-1, os.SEEK_END)
            return arquivo.read(1) != b"\n"
    except FileNotFoundError:
        return False


def _so_o_dono(caminho: Path) -> None:
    """Aperta para 0600 um `.env` que alguém deixou legível por outros."""
    if caminho.exists() and caminho.stat().st_mode & 0o077:
        os.chmod(caminho, _SO_O_DONO)


def garantir_chave(caminho: Path) -> bool:
    """Grava uma `API_SERVER_KEY` nova no `.env` se não houver uma utilizável.

    Devolve `True` quando gravou. A pasta tem que existir: criar `~/.hermes` ou
    um perfil por engano de digitação espalharia chave por onde o Hermes nunca
    olha. Uma linha antiga inutilizável (vazia, curta) fica onde está, e a nova
    vai no fim: no `.env`, vale a última, para o Hermes e para o python-dotenv.
    """
    if not caminho.parent.is_dir():
        raise ChaveAusente(
            f"A pasta {caminho.parent} não existe: crie o perfil antes (rode o bootstrap)."
        )
    if chave_utilizavel(ler_chave_do_env(caminho)):
        _so_o_dono(caminho)
        return False
    quebra = b"\n" if _termina_sem_quebra(caminho) else b""
    descritor = os.open(caminho, os.O_WRONLY | os.O_APPEND | os.O_CREAT, _SO_O_DONO)
    try:
        os.fchmod(descritor, _SO_O_DONO)
        os.write(
            descritor,
            quebra + f"{NOME_DA_CHAVE}={secrets.token_hex(BYTES_DA_CHAVE)}\n".encode("ascii"),
        )
    finally:
        os.close(descritor)
    return True


def trocar_chave(caminho: Path) -> None:
    """Troca a `API_SERVER_KEY` do arquivo por uma nova, sem mexer em nenhuma outra linha.

    As linhas antigas da chave saem (o valor velho não fica para trás), a nova
    entra no fim, e o arquivo é trocado de uma vez (`os.replace`), já em 0600:
    ele guarda os outros segredos do perfil, e um arquivo pela metade os perderia.
    """
    mantidas = [
        linha
        for linha in caminho.read_bytes().splitlines(keepends=True)
        if not _LINHA_DA_CHAVE.match(linha)
    ]
    if mantidas and not mantidas[-1].endswith(b"\n"):
        mantidas[-1] += b"\n"
    novo = b"".join(mantidas) + f"{NOME_DA_CHAVE}={secrets.token_hex(BYTES_DA_CHAVE)}\n".encode()
    provisorio = caminho.with_name(caminho.name + ".novo")
    descritor = os.open(provisorio, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _SO_O_DONO)
    try:
        os.fchmod(descritor, _SO_O_DONO)
        os.write(descritor, novo)
        os.fsync(descritor)
    finally:
        os.close(descritor)
    os.replace(provisorio, caminho)


def garantir_chaves(perfil: str, home: Path) -> list[ChaveGarantida]:
    """A do perfil padrão (abre a porta) e a do perfil (autentica o prefixo dele).

    `hermes profile create --clone` copia o `.env` do perfil padrão
    (`_CLONE_CONFIG_FILES` em hermes_cli/profiles.py), então um perfil criado
    depois que o padrão ganhou chave nasce com a mesma. Ela funcionaria, mas
    abriria o perfil com a chave do padrão, que é justamente o que o Hermes
    passou a recusar. Chave igual à do padrão é trocada.
    """
    validar_perfil(perfil)
    padrao = caminho_do_env("default", home)
    garantidas = [ChaveGarantida(padrao, "perfil padrão, que abre a porta", garantir_chave(padrao))]
    if perfil != "default":
        do_perfil = caminho_do_env(perfil, home)
        criada = garantir_chave(do_perfil)
        trocada = not criada and chaves_iguais(home, perfil)
        if trocada:
            trocar_chave(do_perfil)
        garantidas.append(ChaveGarantida(do_perfil, f"perfil {perfil}", criada, trocada))
    return garantidas


def chaves_iguais(home: Path, perfil: str) -> bool:
    """A do perfil igual à do padrão? Funciona, mas o Hermes pede uma por perfil."""
    if perfil == "default":
        return False
    padrao = ler_chave_do_env(caminho_do_env("default", home))
    do_perfil = ler_chave_do_env(caminho_do_env(perfil, home))
    return padrao is not None and do_perfil is not None and padrao.igual_a(do_perfil)


# --------------------------------------------------------------------------- #
# O estado                                                                     #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Linha:
    """Uma linha do relatório. `ok=None` é informação, não veredito."""

    ok: bool | None
    texto: str


@dataclass
class Relatorio:
    perfil: str
    linhas: list[Linha] = field(default_factory=list)
    versao: str | None = None
    pronto: bool = False

    def anotar(self, ok: bool | None, texto: str) -> None:
        self.linhas.append(Linha(ok, texto))

    @property
    def primeira_falha(self) -> str | None:
        return next((linha.texto for linha in self.linhas if linha.ok is False), None)


def _encurtar(caminho: Path | str) -> str:
    texto = str(caminho)
    casa = str(Path.home())
    return "~" + texto[len(casa) :] if texto.startswith(casa + os.sep) else texto


def _e_o_gateway(partes: list[str]) -> bool:
    """`python -m hermes_cli.main gateway run` (o serviço) ou `hermes gateway run`."""
    return (
        "gateway" in partes
        and "run" in partes
        and any("hermes" in parte for parte in partes[: partes.index("gateway")])
    )


def pids_do_gateway(proc: Path = Path("/proc")) -> list[int] | None:
    """Os processos do gateway do Hermes, lidos de /proc. `None` fora do Linux."""
    if not proc.is_dir():
        return None
    achados: list[int] = []
    for entrada in proc.iterdir():
        if not entrada.name.isdigit():
            continue
        try:
            bruto = (entrada / "cmdline").read_bytes()
        except OSError:
            continue
        partes = [p.decode("utf-8", "replace") for p in bruto.split(b"\0") if p]
        if _e_o_gateway(partes):
            achados.append(int(entrada.name))
    return sorted(achados)


def _secao(dados: dict[str, Any], nome: str) -> dict[str, Any]:
    secao = dados.get(nome)
    return secao if isinstance(secao, dict) else {}


def ler_modelo(home: Path, perfil: str) -> dict[str, Any] | None:
    """Modelo, provedor, esforço e reservas do `config.yaml` do perfil. Nada de credencial."""
    pasta = home if perfil == "default" else home / "profiles" / perfil
    caminho = pasta / "config.yaml"
    try:
        dados = YAML(typ="safe").load(caminho.read_text(encoding="utf-8"))
    except (OSError, YAMLError):
        return None
    if not isinstance(dados, dict):
        return None
    modelo = _secao(dados, "model")
    agente = _secao(dados, "agent")
    reservas = dados.get("fallback_providers")
    return {
        "modelo": modelo.get("default"),
        "provedor": modelo.get("provider"),
        "esforco": agente.get("reasoning_effort"),
        "reservas": [
            str(r.get("model"))
            for r in (reservas if isinstance(reservas, list) else [])
            if isinstance(r, dict) and r.get("model")
        ],
    }


def _linha_do_modelo(info: dict[str, Any] | None, perfil: str) -> str:
    if info is None:
        return f"sem config.yaml legível no perfil {perfil}"
    modelo, provedor = info["modelo"] or "?", info["provedor"] or "?"
    texto = f"modelo {modelo} ({provedor}), esforço {info['esforco'] or '?'}"
    if info["reservas"]:
        texto += f", reserva {', '.join(info['reservas'])}"
    return texto


async def _versao(
    cliente: ClienteHermes, esperar_s: float, dormir: Dormir, relogio: Relogio
) -> str:
    """Espera a porta responder, até `esperar_s` (o gateway leva um tempo para subir)."""
    limite = relogio() + max(esperar_s, 0.0)
    while True:
        try:
            return await cliente.versao()
        except (HermesForaDoAr, TempoEsgotado):
            if relogio() >= limite:
                raise
            await dormir(_INTERVALO_DE_ESPERA_S)


def _anotar_gateway(relatorio: Relatorio, proc: Path) -> None:
    pids = pids_do_gateway(proc)
    if pids:
        relatorio.anotar(True, f"gateway do Hermes rodando (PID {', '.join(map(str, pids))})")
    elif pids is not None:
        relatorio.anotar(
            False, "gateway do Hermes parado (e o chat da web junto): veja `hermes gateway status`"
        )


def _anotar_chaves(
    relatorio: Relatorio, perfil: str, home: Path, ambiente: Mapping[str, str]
) -> ChaveEncontrada | None:
    padrao = caminho_do_env("default", home)
    if chave_utilizavel(ler_chave_do_env(padrao)):
        relatorio.anotar(True, f"chave do perfil padrão presente ({_encurtar(padrao)})")
    else:
        relatorio.anotar(
            False,
            f"sem {NOME_DA_CHAVE} no perfil padrão ({_encurtar(padrao)}): a porta não abre; "
            "rode a etapa 'API do agente' do bootstrap",
        )
    try:
        encontrada = descobrir_chave(perfil, ambiente=ambiente, home=home)
    except ChaveAusente as causa:
        relatorio.anotar(False, str(causa))
        return None
    relatorio.anotar(True, f"chave do perfil {perfil} presente ({_encurtar(encontrada.origem)})")
    if chaves_iguais(home, perfil):
        relatorio.anotar(
            False, f"a chave do perfil {perfil} é igual à do padrão: gere outra, uma por perfil"
        )
    return encontrada


async def _anotar_servidor(
    relatorio: Relatorio,
    cliente: ClienteHermes,
    *,
    esperar_s: float,
    dormir: Dormir,
    relogio: Relogio,
) -> None:
    try:
        relatorio.versao = await _versao(cliente, esperar_s, dormir, relogio)
    except HermesForaDoAr:
        relatorio.anotar(
            False,
            f"servidor de API fora do ar em {cliente.url}: o gateway está parado ou subiu sem a "
            "chave do perfil padrão (gerada a chave, falta 'make reiniciar-agente')",
        )
        return
    except ErroDoHermes as causa:
        relatorio.anotar(False, f"servidor de API fora do ar: {causa}")
        return
    relatorio.anotar(True, f"servidor de API no ar em {cliente.url} (Hermes {relatorio.versao})")
    if not cliente.tem_chave:
        return
    try:
        await cliente.listar_sessoes(limite=1, fonte=None)
    except ErroDoHermes as causa:
        relatorio.anotar(False, str(causa))
        return
    relatorio.anotar(True, f"o servidor aceitou a chave do perfil {relatorio.perfil}")
    relatorio.pronto = True


async def conferir(
    perfil: str,
    *,
    home: Path,
    ambiente: Mapping[str, str],
    esperar_s: float = 0.0,
    transporte: httpx.AsyncBaseTransport | None = None,
    proc: Path = Path("/proc"),
    dormir: Dormir = asyncio.sleep,
    relogio: Relogio = time.monotonic,
) -> Relatorio:
    """Gateway, as duas chaves, a porta, a chave aceita e o modelo, nessa ordem."""
    relatorio = Relatorio(perfil=validar_perfil(perfil))
    _anotar_gateway(relatorio, proc)
    encontrada = _anotar_chaves(relatorio, perfil, home, ambiente)
    async with ClienteHermes(
        url=ambiente.get(VAR_URL, "").strip() or URL_PADRAO,
        perfil=perfil,
        chave=encontrada.chave if encontrada else None,
        origem_da_chave=encontrada.origem if encontrada else None,
        transporte=transporte,
    ) as cliente:
        await _anotar_servidor(
            relatorio, cliente, esperar_s=esperar_s, dormir=dormir, relogio=relogio
        )
    relatorio.anotar(None, _linha_do_modelo(ler_modelo(home, perfil), perfil))
    return relatorio


# --------------------------------------------------------------------------- #
# Linha de comando                                                             #
# --------------------------------------------------------------------------- #


def _marca(ok: bool | None, cores: bool) -> str:
    simbolo, cor = {True: ("✓", "32"), False: ("✗", "31"), None: ("·", "36")}[ok]
    return f"\033[{cor}m{simbolo}\033[0m" if cores else simbolo


def _imprimir(relatorio: Relatorio, *, curto: bool) -> None:
    cores = sys.stdout.isatty()
    if curto:
        if relatorio.pronto:
            print(
                f"{_marca(True, cores)} agente pronto "
                f"(Hermes {relatorio.versao}, perfil {relatorio.perfil})"
            )
        else:
            print(f"{_marca(False, cores)} agente indisponível: {relatorio.primeira_falha}")
        return
    print(f"Agente (Hermes) · perfil {relatorio.perfil}")
    for linha in relatorio.linhas:
        print(f"  {_marca(linha.ok, cores)} {linha.texto}")


def _garantir(perfil: str, home: Path) -> int:
    try:
        garantidas = garantir_chaves(perfil, home)
    except (ChaveAusente, ValueError) as causa:
        print(f"✗ {causa}", file=sys.stderr)
        return 1
    for g in garantidas:
        if g.trocada:
            feito = "chave trocada (era a do perfil padrão, copiada pelo --clone)"
        else:
            feito = "chave nova" if g.criada else "chave já existia"
        print(f"  ✓ {feito} no {g.papel} ({_encurtar(g.caminho)}, modo 600)")
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    ambiente: Mapping[str, str] | None = None,
    transporte: httpx.AsyncBaseTransport | None = None,
    proc: Path = Path("/proc"),
    dormir: Dormir = asyncio.sleep,
) -> int:
    amb = os.environ if ambiente is None else ambiente
    perfil_padrao = amb.get("PERFIL_HERMES") or amb.get(VAR_PERFIL) or PERFIL_PADRAO
    parser = argparse.ArgumentParser(
        prog="python -m gateway.hermes_operacao",
        description="Chave e estado do servidor de API do Hermes, sem mostrar segredo.",
    )
    comandos = parser.add_subparsers(dest="comando", required=True)
    garantir = comandos.add_parser("garantir-chave", help="gera a API_SERVER_KEY que faltar")
    garantir.add_argument("--perfil", default=perfil_padrao)
    status = comandos.add_parser("status", help="gateway, porta, chaves e modelo")
    status.add_argument("--perfil", default=perfil_padrao)
    status.add_argument("--esperar", type=float, default=0.0, help="segundos esperando a porta")
    status.add_argument("--curto", action="store_true", help="uma linha só")
    args = parser.parse_args(argv)

    home = hermes_home(amb)
    if args.comando == "garantir-chave":
        return _garantir(args.perfil, home)
    try:
        relatorio = asyncio.run(
            conferir(
                args.perfil,
                home=home,
                ambiente=amb,
                esperar_s=args.esperar,
                transporte=transporte,
                proc=proc,
                dormir=dormir,
            )
        )
    except ValueError as causa:
        print(f"✗ {causa}", file=sys.stderr)
        return 1
    _imprimir(relatorio, curto=args.curto)
    return 0 if relatorio.pronto else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
