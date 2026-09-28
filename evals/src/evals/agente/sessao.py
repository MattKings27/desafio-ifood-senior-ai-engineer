"""O que cada ferramenta devolveu, lido do banco de sessões do Hermes.

O `stream-json` do Hermes 0.21 emite `tool_result` com `output` vazio: o
callback de progresso não recebe o resultado. Sem a saída, a transcrição mostra
que o agente chamou `consultar_perfil`, mas não o que o motor respondeu, e aí
não dá para saber se uma frase dele veio da ferramenta ou foi inventada.

O `state.db` do perfil guarda cada mensagem de ferramenta por sessão. Este
módulo lê de lá, só leitura, e preenche as saídas que o stream deixou vazias.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import replace
from pathlib import Path

from evals.agente.protocolo import Turno

#: O Hermes embrulha resultado de MCP como dado não confiável antes de mostrar
#: ao modelo. Para a transcrição interessa o conteúdo, não o embrulho.
_EMBRULHO = re.compile(r"<untrusted_tool_result[^>]*>.*?(\{.*\})\s*</untrusted_tool_result>", re.S)


def desembrulhar(conteudo: str) -> str:
    """O texto que a ferramenta devolveu, sem o envelope de segurança do Hermes."""
    achado = _EMBRULHO.search(conteudo)
    if not achado:
        return conteudo
    try:
        dados = json.loads(achado.group(1))
    except json.JSONDecodeError:
        return achado.group(1)
    if isinstance(dados, dict) and isinstance(dados.get("result"), str):
        return str(dados["result"])
    return achado.group(1)


def mensagens_de_ferramenta(banco: Path, sessao: str) -> list[tuple[str, str, str]]:
    """`(tool_call_id, ferramenta, conteúdo)` da sessão, na ordem em que aconteceram."""
    if not banco.exists():
        return []
    conexao = sqlite3.connect(f"file:{banco}?mode=ro", uri=True)
    try:
        linhas = conexao.execute(
            "SELECT tool_call_id, tool_name, content FROM messages "
            "WHERE session_id = ? AND role = 'tool' ORDER BY id",
            (sessao,),
        ).fetchall()
    finally:
        conexao.close()
    return [(str(i or ""), str(n or ""), str(c or "")) for i, n, c in linhas]


def completar(turnos: list[Turno], mensagens: list[tuple[str, str, str]]) -> list[Turno]:
    """Preenche as saídas vazias, casando por id e, sem id, pela ordem e pelo nome.

    Se a ordem não bater com os nomes, a saída fica vazia: uma saída atribuída à
    chamada errada é pior que nenhuma, porque parece prova.
    """
    por_id = {i: desembrulhar(c) for i, _, c in mensagens if i}
    fila = [(n, desembrulhar(c)) for _, n, c in mensagens]
    completos = []
    for turno in turnos:
        chamadas = []
        for chamada in turno.chamadas:
            saida = chamada.saida
            if not saida and chamada.ident in por_id:
                saida = por_id[chamada.ident]
            elif not saida and fila and fila[0][0] == chamada.ferramenta:
                saida = fila[0][1]
            if fila and fila[0][0] == chamada.ferramenta:
                fila.pop(0)
            chamadas.append(replace(chamada, saida=saida))
        completos.append(replace(turno, chamadas=tuple(chamadas)))
    return completos


def tokens_das_sessoes(banco: Path, sessoes: set[str]) -> dict[str, int] | None:
    """Os tokens que o Hermes gravou para estas sessões, para conferir o stream.

    O Hermes 0.21 grava tokens por sessão, mas não o preço (fica US$ 0,00 com
    custo "unknown"). Então o custo sai de `telemetria.custo`, e o que dá para
    conferir de forma independente é a contagem de tokens.
    """
    if not sessoes or not banco.exists():
        return None
    marcas = ",".join("?" for _ in sessoes)
    conexao = sqlite3.connect(f"file:{banco}?mode=ro", uri=True)
    try:
        linha = conexao.execute(
            "SELECT COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0), "
            "COALESCE(SUM(cache_read_tokens), 0), COALESCE(SUM(cache_write_tokens), 0) "
            f"FROM sessions WHERE id IN ({marcas})",
            sorted(sessoes),
        ).fetchone()
    finally:
        conexao.close()
    entrada, saida, leitura, gravacao = (int(v) for v in linha)
    return {"entrada": entrada, "saida": saida, "cache_leitura": leitura, "cache_escrita": gravacao}
