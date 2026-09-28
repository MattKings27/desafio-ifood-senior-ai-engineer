"""Como as respostas do motor saem: JSON com a derivação junto do número.

Separado do servidor MCP para que cada módulo de ferramentas (`mise.ferramentas`)
e a API HTTP usem a mesma forma de dinheiro, de receita, de avaliação e de erro
sem importar o servidor inteiro. O `mise.mcp_server` reexporta estes nomes: quem
já os importava de lá continua funcionando.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ParamSpec

from mise.erros import ErroDeDados, ErroDeRegra, ErroDeUso, ErroMise

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from mise.cmv import CMV
    from mise.dinheiro import Dinheiro
    from mise.receita import Receita
    from mise.viabilidade import Avaliacao


def prato_para_auditoria(
    cmv: CMV, preco: Dinheiro | None = None, lucro: Dinheiro | None = None
) -> dict[str, Any]:
    """O prato como o auditor lê: as linhas e o total delas, como foram mostrados.

    `total_das_linhas` é o total que as linhas somam na tela; `cmv` é o custo
    que vai para o preço. Num custo exato, os dois são o mesmo número. Numa
    faixa, o preço sai do topo, que inclui a incerteza e não é soma de linhas:
    mandar só o topo fazia o auditor comparar as linhas com outra conta e
    segurar um preço certo.
    """
    prato: dict[str, Any] = {
        "prato": cmv.receita,
        "linhas": [
            {"ingrediente": linha.ingrediente, "custo": str(exibido.valor)}
            for linha, exibido in zip(cmv.linhas, cmv.custos_exibidos(), strict=True)
        ],
        "total_das_linhas": str(cmv.total.arredondado_para_cima().valor),
        "cmv": str(cmv.para_precificar.valor),
    }
    if preco is not None and lucro is not None:
        prato |= {"preco": str(preco.valor), "lucro": str(lucro.arredondado().valor)}
    return prato


def _reais(valor: Dinheiro) -> dict[str, Any]:
    """Dinheiro sempre vai com número e texto: o agente lê o texto, não formata."""
    return {"valor": float(valor.arredondado().valor), "texto": str(valor)}


def _receita_json(receita: Receita) -> dict[str, Any]:
    """A receita como a interface e o agente a leem.

    Cada ingrediente leva o texto original junto: é o que permite à Dona Maria
    discordar da nossa interpretação, e discordar é como um erro nosso aparece.
    """
    return {
        "nome": receita.nome,
        "rendimento_porcoes": receita.rendimento_porcoes,
        "rendimento_informado": receita.rendimento_informado,
        "tempo_preparo_min": receita.tempo_preparo_min,
        "tempo_cozimento_min": receita.tempo_cozimento_min,
        "tempo_total_min": receita.tempo_total_min,
        "origem": receita.origem.value,
        "url": receita.url,
        "fonte": receita.fonte,
        "ingredientes": [
            {
                "texto": i.texto_original,
                "nome": i.nome,
                "quantidade": float(i.quantidade) if i.quantidade is not None else None,
                "medida": i.medida,
                "a_gosto": i.a_gosto,
            }
            for i in receita.ingredientes
        ],
        "modo_preparo": list(receita.modo_preparo),
        "equipamentos": sorted(receita.equipamentos),
        "tecnicas": sorted(receita.tecnicas),
    }


def avisos_json(avaliacao: Avaliacao) -> list[dict[str, str]]:
    """O que não impede o prato e ela precisa saber: `[{tipo, texto}]`, a forma do contrato."""
    return [{"tipo": a.tipo, "texto": a.texto} for a in avaliacao.avisos]


def _avaliacao_json(avaliacao: Avaliacao) -> dict[str, Any]:
    return {
        "prato": avaliacao.receita_nome,
        "veredito": avaliacao.veredito.rotulo,
        "pode_precificar": avaliacao.permite_precificar,
        "resumo": avaliacao.resumo(),
        "impedimentos": [
            {"tipo": i.tipo.name.lower(), "id": i.id, "motivo": i.descricao}
            for i in avaliacao.impedimentos
        ],
        "perguntas": [
            {"tipo": p.tipo.name.lower(), "campo": p.campo, "texto": p.texto, "motivo": p.motivo}
            for p in avaliacao.perguntas
        ],
        # O rendimento nunca é pergunta: o da receita, ou a estimativa, dita como estimativa.
        "rendimento": avaliacao.rendimento.texto if avaliacao.rendimento else None,
        "avisos": avisos_json(avaliacao),
        "ingredientes_na_despensa": [
            {
                "ingrediente": u.casamento.item.nome if u.casamento.item else "",
                "quantidade": f"{u.quantidade}",
                "custo": _reais(u.custo),
                "derivacao": u.derivacao,
            }
            for u in avaliacao.usos
        ],
        "falta_comprar": [
            {
                "ingrediente": f.nome,
                "quanto": f.quantidade_texto,
                "custo": _reais(f.custo_estimado) if f.custo_estimado else None,
                # O preço de referência vem com a fonte e diz que é referência.
                "preco_de_referencia": f.referencia.texto if f.referencia else None,
            }
            for f in avaliacao.faltantes
        ],
        "a_gosto": list(avaliacao.a_gosto),
    }


def _erro_json(erro: ErroMise) -> dict[str, Any]:
    """Erro estruturado, com a categoria que diz ao agente o que fazer."""
    categoria = (
        "dado"
        if isinstance(erro, ErroDeDados)
        else "regra"
        if isinstance(erro, ErroDeRegra)
        else "uso"
        if isinstance(erro, ErroDeUso)
        else "desconhecido"
    )
    payload: dict[str, Any] = {
        "erro": erro.mensagem,
        "categoria": categoria,
        "tipo": type(erro).__name__,
        "contexto": {k: str(v) for k, v in erro.contexto.items()},
    }
    if isinstance(erro, ErroDeDados):
        # Peso, medida e preço nunca se perguntam a ela: sem fonte, o número não sai.
        payload["orientacao"] = (
            "Não pergunte isso a ela: sem fonte para esse número, diga que não dá para "
            "calcular e de onde viria o dado; se ela quiser dizer, o dela vale."
        )
    elif categoria == "regra":
        # A recusa que já traz a pergunta (confirmar a cozinha antes do aceite) diz
        # também como gravar a resposta; as outras só pedem que não se contorne.
        if pergunta := getattr(erro, "pergunta", ""):
            payload["pergunta"] = pergunta
        payload["orientacao"] = getattr(erro, "orientacao", "") or (
            "Não contorne: resolva a pendência antes de prosseguir."
        )
    return payload


def _resposta(dados: dict[str, Any]) -> str:
    return json.dumps(dados, ensure_ascii=False, indent=2, default=str)


_P = ParamSpec("_P")


def protegido(fn: Callable[_P, Awaitable[str]]) -> Callable[_P, Awaitable[str]]:
    """Converte erros do domínio em JSON estruturado em vez de stack trace.

    Usa `functools.wraps` por necessidade, não por estilo: o `MCPServer` deriva
    o JSON Schema de cada ferramenta inspecionando a assinatura da função. Um
    wrapper `(*args, **kwargs)` sem `__wrapped__` faz o schema virar
    `{args, kwargs}` e toda chamada falhar na validação. É também o
    `__wrapped__` que faz as anotações serem lidas no módulo da ferramenta, e
    não neste: `ReceitaEntrada` só existe lá.
    """

    @functools.wraps(fn)
    async def envelope(*args: _P.args, **kwargs: _P.kwargs) -> str:
        try:
            resultado: str = await fn(*args, **kwargs)
        except ErroMise as erro:
            return _resposta(_erro_json(erro))
        return resultado

    return envelope


__all__ = [
    "_avaliacao_json",
    "_erro_json",
    "_reais",
    "_receita_json",
    "_resposta",
    "avisos_json",
    "prato_para_auditoria",
    "protegido",
]
