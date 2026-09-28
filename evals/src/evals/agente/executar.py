"""Roda cenários contra o agente de verdade, no Hermes, e mede o que aconteceu.

    python -m evals.agente evals/casos/agente/*.yaml --k 3

Cada cenário roda `k` vezes, cada vez com o estado zerado (`isolamento`). O
resumo traz `pass^k` (o cenário passou nas k, não em pelo menos uma: a Dona
Maria conversa com o agente todo dia, e acertar às vezes não serve), latência
p50/p95 por turno e os tokens gastos, com cache separado.

Custa dinheiro e minutos: é um portão manual, não de todo commit.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from telemetria.custo import FONTE_DOS_PRECOS, ModeloDesconhecido, Orcamento, UsoDeModelo

from evals.agente.cenario import Cenario, Veredito, avaliar, carregar
from evals.agente.isolamento import isolar
from evals.agente.protocolo import ProtocoloInvalido, Turno, ler_turno
from evals.agente.sessao import completar, mensagens_de_ferramenta, tokens_das_sessoes

PERFIL_PADRAO = "sabor-da-maria-avaliacao"

#: Assinatura de `subprocess.run` que o executor usa; os testes trocam por um falso.
Rodar = Callable[..., "subprocess.CompletedProcess[str]"]


@dataclass(frozen=True)
class Opcoes:
    perfil: str = PERFIL_PADRAO
    hermes: str = "hermes"
    modelo: str | None = None
    esforco: str | None = None
    max_turnos: int = 40
    timeout_s: int = 600
    #: `state.db` do perfil, de onde vêm as saídas que o stream não traz.
    banco: Path | None = None
    #: Onde o Hermes roda. Fora do repositório, de propósito: o Hermes lê
    #: arquivos de contexto da pasta em que abre, e a avaliação tem que ver a
    #: mesmo agente que a Dona Maria vê pelo chat da web, servido pelo gateway do
    #: Hermes, que não abre ali.
    pasta: Path | None = None


@dataclass(frozen=True)
class Execucao:
    cenario: str
    indice: int
    turnos: tuple[Turno, ...]
    veredito: Veredito
    erro: str | None = None

    def para_json(self) -> dict[str, Any]:
        return {
            "cenario": self.cenario,
            "execucao": self.indice,
            "passou": self.veredito.passou and self.erro is None,
            "falhas": list(self.veredito.falhas),
            "erro": self.erro,
            "turnos": [t.para_json() for t in self.turnos],
        }


def comando(opcoes: Opcoes, sessao: str | None) -> list[str]:
    """A linha do Hermes para um turno. A fala vai pelo stdin, nunca pelo argv."""
    cmd = [
        opcoes.hermes,
        "-p",
        opcoes.perfil,
        "chat",
        "--query-file",
        "-",
        "-Q",
        "--format",
        "stream-json",
        "--source",
        "eval",
        "--max-turns",
        str(opcoes.max_turnos),
    ]
    if opcoes.modelo:
        cmd += ["-m", opcoes.modelo]
    if opcoes.esforco:
        cmd += ["--reasoning", opcoes.esforco]
    if sessao:
        cmd += ["--resume", sessao]
    return cmd


def conversar(
    cenario: Cenario,
    indice: int,
    opcoes: Opcoes,
    rodar: Rodar = subprocess.run,
) -> Execucao:
    """Uma conversa inteira, turno a turno, na mesma sessão do Hermes."""
    turnos: list[Turno] = []
    sessao: str | None = None
    erro: str | None = None
    for roteiro in cenario.turnos:
        try:
            processo = rodar(
                comando(opcoes, sessao),
                input=roteiro.diz,
                cwd=opcoes.pasta,
                capture_output=True,
                text=True,
                timeout=opcoes.timeout_s,
                check=False,
            )
            turno = ler_turno(roteiro.diz, processo.stdout.splitlines())
        except subprocess.TimeoutExpired:
            erro = f"turno {len(turnos) + 1} passou de {opcoes.timeout_s}s"
            break
        except ProtocoloInvalido as causa:
            cauda = (processo.stderr or "").strip().splitlines()[-3:]
            erro = f"turno {len(turnos) + 1}: {causa}; stderr: {' | '.join(cauda)}"
            break
        turnos.append(turno)
        sessao = turno.sessao or sessao

    if opcoes.banco is not None and sessao:
        turnos = completar(turnos, mensagens_de_ferramenta(opcoes.banco, sessao))

    return Execucao(
        cenario=cenario.nome,
        indice=indice,
        turnos=tuple(turnos),
        veredito=avaliar(cenario, turnos),
        erro=erro,
    )


def _percentil(valores: Sequence[float], p: float) -> float:
    if not valores:
        return 0.0
    if len(valores) == 1:
        return float(valores[0])
    return statistics.quantiles(valores, n=100, method="inclusive")[round(p) - 1]


def _custo(turnos: Sequence[Turno]) -> dict[str, Any]:
    """Custo em dólar pelos preços versionados em `telemetria.custo`.

    A gravação de cache é contada a 5 minutos de vida; a 1 hora ela custaria
    60% mais, e o resumo diz qual premissa usou.
    """
    orcamento = Orcamento()
    try:
        for t in turnos:
            orcamento.registrar(
                UsoDeModelo(
                    t.modelo,
                    entrada=t.uso.entrada,
                    saida=t.uso.saida,
                    leitura_de_cache=t.uso.cache_leitura,
                    gravacao_de_cache=t.uso.cache_escrita,
                )
            )
        # O preço só é consultado aqui; modelo sem preço tem que cair no except.
        partes = orcamento.partes_usd()
    except ModeloDesconhecido as erro:
        return {"usd": None, "motivo": str(erro)}
    return {
        "usd": round(float(orcamento.total_usd), 6),
        "partes_usd": {k: round(float(v), 6) for k, v in partes.items()},
        "premissa": "gravação de cache com vida de 5 minutos",
        "fonte_dos_precos": FONTE_DOS_PRECOS,
    }


def _media_por_conversa(execucoes: Sequence[Execucao]) -> float | None:
    custos: list[float | None] = [_custo(e.turnos)["usd"] for e in execucoes]
    validos = [c for c in custos if c is not None]
    if not custos or len(validos) != len(custos):
        return None
    return round(sum(validos) / len(validos), 6)


def resumir(
    execucoes: Sequence[Execucao], tokens_do_hermes: dict[str, int] | None = None
) -> dict[str, Any]:
    """O número que responde "dá para confiar?" e o que custou saber."""
    por_cenario: dict[str, list[Execucao]] = {}
    for e in execucoes:
        por_cenario.setdefault(e.cenario, []).append(e)

    turnos = [t for e in execucoes for t in e.turnos]
    duracoes = [t.duracao_ms / 1000 for t in turnos]
    tokens = {
        "entrada": sum(t.uso.entrada for t in turnos),
        "saida": sum(t.uso.saida for t in turnos),
        "cache_leitura": sum(t.uso.cache_leitura for t in turnos),
        "cache_escrita": sum(t.uso.cache_escrita for t in turnos),
    }
    return {
        "cenarios": {
            nome: {
                "execucoes": len(lista),
                "passaram": sum(1 for e in lista if e.veredito.passou and e.erro is None),
                "pass_k": all(e.veredito.passou and e.erro is None for e in lista),
                "falhas": sorted({f for e in lista for f in (*e.veredito.falhas, e.erro) if f}),
            }
            for nome, lista in por_cenario.items()
        },
        "pass_k_geral": sum(
            1
            for lista in por_cenario.values()
            if all(e.veredito.passou and not e.erro for e in lista)
        ),
        "total_de_cenarios": len(por_cenario),
        "turnos": len(turnos),
        "latencia_por_turno_s": {
            "p50": round(_percentil(duracoes, 50), 1),
            "p95": round(_percentil(duracoes, 95), 1),
        },
        "tokens": tokens,
        "modelos": sorted({t.modelo for t in turnos if t.modelo}),
        "custo": {**_custo(turnos), "por_conversa_usd": _media_por_conversa(execucoes)},
        "tokens_conferem_com_o_hermes": (
            None if tokens_do_hermes is None else tokens_do_hermes == tokens
        ),
    }


def reavaliar(cenario: Cenario, pasta: Path) -> list[Execucao]:
    """Julga de novo as transcrições salvas de um cenário, com as expectativas de agora.

    Corrigir um cenário mal escrito não deveria custar outra rodada no agente:
    a conversa aconteceu e está gravada; o que mudou foi a régua.
    """
    execucoes = []
    for arquivo in sorted((pasta / cenario.nome).glob("execucao-*.json")):
        salvo = json.loads(arquivo.read_text("utf-8"))
        turnos = tuple(Turno.de_json(t) for t in salvo["turnos"])
        execucao = Execucao(
            cenario=cenario.nome,
            indice=salvo["execucao"],
            turnos=turnos,
            veredito=avaliar(cenario, list(turnos)),
            erro=salvo.get("erro"),
        )
        arquivo.write_text(
            json.dumps(execucao.para_json(), ensure_ascii=False, indent=2) + "\n", "utf-8"
        )
        execucoes.append(execucao)
    return execucoes


def servidor_do_motor_responde(
    opcoes: Opcoes, rodar: Rodar = subprocess.run, limite_s: int = 150
) -> tuple[bool, str]:
    """O perfil conecta no servidor do motor? Confere antes de gastar com o modelo.

    Uma rodada inteira já foi gasta com o servidor fora do ar: o Hermes desistiu
    da conexão, o agente conversou sem nenhuma ferramenta do motor, e todos os
    cenários falharam sem que nada dissesse o porquê.
    """
    try:
        processo = rodar(
            [opcoes.hermes, "-p", opcoes.perfil, "mcp", "test", "mise"],
            capture_output=True,
            text=True,
            timeout=limite_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"o teste de conexão passou de {limite_s}s"
    saida = f"{processo.stdout}\n{processo.stderr}"
    return "Connected" in saida and "Tools discovered" in saida, saida.strip()[-400:]


def _hermes() -> str:
    achado = shutil.which("hermes")
    if achado:
        return achado
    local = Path.home() / ".local" / "bin" / "hermes"
    return str(local) if local.exists() else "hermes"


def main(argv: Sequence[str] | None = None) -> int:  # pragma: sem cobertura
    parser = argparse.ArgumentParser(prog="python -m evals.agente", description=__doc__)
    parser.add_argument("cenarios", nargs="+", type=Path)
    parser.add_argument("--k", type=int, default=1, help="execuções por cenário")
    parser.add_argument("--perfil", default=PERFIL_PADRAO)
    parser.add_argument("--modelo")
    parser.add_argument("--esforco")
    parser.add_argument("--max-turnos", type=int, default=40)
    parser.add_argument("--saida", type=Path, default=Path("docs/transcricoes"))
    parser.add_argument(
        "--reavaliar",
        action="store_true",
        help="julga de novo as transcrições em --saida, sem rodar o agente",
    )
    args = parser.parse_args(argv)

    dir_perfil = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "profiles"
    dir_perfil /= args.perfil

    if args.reavaliar:
        execucoes_salvas = [e for c in args.cenarios for e in reavaliar(carregar(c), args.saida)]
        # Julgar de novo não muda os tokens gastos: se o banco do perfil ainda
        # guarda aquelas sessões, a conferência com o Hermes continua valendo.
        sessoes = {t.sessao for e in execucoes_salvas for t in e.turnos if t.sessao}
        resumo = resumir(execucoes_salvas, tokens_das_sessoes(dir_perfil / "state.db", sessoes))
        (args.saida / "resumo.json").write_text(
            json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", "utf-8"
        )
        print(json.dumps(resumo, ensure_ascii=False, indent=2))
        return 0 if resumo["pass_k_geral"] == resumo["total_de_cenarios"] else 1

    opcoes = Opcoes(
        perfil=args.perfil,
        hermes=_hermes(),
        modelo=args.modelo,
        esforco=args.esforco,
        max_turnos=args.max_turnos,
        banco=dir_perfil / "state.db",
    )

    pronto, detalhe = servidor_do_motor_responde(opcoes)
    if not pronto:
        print(
            f"o servidor do motor não conectou pelo perfil {opcoes.perfil}:\n{detalhe}",
            file=sys.stderr,
        )
        return 2

    execucoes = []
    for caminho in args.cenarios:
        cenario = carregar(caminho)
        for i in range(1, args.k + 1):
            estado = Path(tempfile.mkdtemp(prefix=f"agente-{cenario.nome}-"))
            isolar(dir_perfil, estado)
            print(f"→ {cenario.nome} [{i}/{args.k}]", file=sys.stderr, flush=True)
            execucao = conversar(cenario, i, replace(opcoes, pasta=estado))
            execucoes.append(execucao)

            destino = args.saida / cenario.nome / f"execucao-{i}.json"
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(
                json.dumps(execucao.para_json(), ensure_ascii=False, indent=2) + "\n", "utf-8"
            )
            marca = "✓" if execucao.veredito.passou and not execucao.erro else "✗"
            print(f"  {marca} {destino}", file=sys.stderr)
            for falha in (*execucao.veredito.falhas, execucao.erro):
                if falha:
                    print(f"    {falha}", file=sys.stderr)

    sessoes = {t.sessao for e in execucoes for t in e.turnos if t.sessao}
    resumo = resumir(execucoes, tokens_das_sessoes(dir_perfil / "state.db", sessoes))
    args.saida.mkdir(parents=True, exist_ok=True)
    (args.saida / "resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    return 0 if resumo["pass_k_geral"] == resumo["total_de_cenarios"] else 1
