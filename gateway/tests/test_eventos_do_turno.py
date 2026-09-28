"""O normalizador: do stream do Hermes aos eventos da tela, evento por evento."""

from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from gateway.cartoes import Cartao
from gateway.cartoes_da_conversa import RefResolvida
from gateway.conversas_db import EstadoDoTurno
from gateway.eventos_do_turno import (
    CONTEXTO_CHEIO,
    DEMOROU,
    PROBLEMA,
    RECUSA,
    SEM_RESPOSTA,
    Falha,
    Normalizador,
    de_bastidor,
    e_do_motor,
    estimar_contexto,
    recursos_da_escrita,
    sem_nota_do_guard_rail,
    traduzir_aviso,
    valores_do_motor,
)
from gateway.frases import SENTINELA
from gateway.hermes_cliente import EventoSSE

PLUGIN = (
    Path(__file__).resolve().parents[2]
    / "hermes"
    / "plugins"
    / "guardrail-numerico"
    / "__init__.py"
)


class MontadorFalso:
    """Resolve todo card para uma rota fixa e devolve os dados que o teste mandar."""

    def __init__(self, dados: list[Any] | None = None, *, erro: bool = False) -> None:
        self.dados = list(dados or [{"n": 1}])
        self.erro = erro

    def resolver(self, cartao: Cartao) -> RefResolvida | None:
        if cartao["tipo_cartao"] == "ingrediente":
            return None
        return RefResolvida(cartao["tipo_cartao"], "/api/orcamento", {})

    async def montar_resolvido(self, ref: RefResolvida, *, cartao_id: str) -> dict[str, Any] | None:
        if self.erro:
            raise RuntimeError("quebrou")
        dados = self.dados.pop(0) if len(self.dados) > 1 else self.dados[0]
        if dados is None:
            return None
        return {
            "cartao_id": cartao_id,
            "tipo_cartao": ref.tipo_cartao,
            "ref": {"rota": ref.rota, "parametros": ref.parametros},
            "dados": dados,
            "gerado": "2026-09-25T17:30:00+00:00",
        }


class Tela:
    """Guarda o que o normalizador emite."""

    def __init__(self) -> None:
        self.eventos: list[dict[str, Any]] = []

    def __call__(self, tipo: str, campos: dict[str, Any]) -> None:
        self.eventos.append({"tipo": tipo, **campos})

    def tipos(self) -> list[str]:
        return [e["tipo"] for e in self.eventos]

    def de(self, tipo: str) -> list[dict[str, Any]]:
        return [e for e in self.eventos if e["tipo"] == tipo]


def _normalizador(tela: Tela, montador: Any = None, runs: list[str] | None = None) -> Normalizador:
    contador = iter(range(1, 100))

    async def ao_saber(run_id: str) -> None:
        if runs is not None:
            runs.append(run_id)

    return Normalizador(
        tela,
        montador,
        novo_cartao_id=lambda: f"k-{next(contador)}",
        quando=lambda _iso: "hoje, 14:30",
        ao_saber_do_run=ao_saber if runs is not None else None,
    )


def ev(nome: str, **dados: Any) -> EventoSSE:
    return EventoSSE(nome=nome, dados={"run_id": "run_1", **dados})


# --------------------------------------------------------------------------- #
# Funções soltas                                                               #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("aviso", "esperado"),
    [
        ("⚠️ Anthropic's safety filter refused this request.", Falha("consultora", RECUSA)),
        ("⚠️ The model declined to respond.", Falha("consultora", RECUSA)),
        (
            "⚠️ **Context window full.** The prompt used 1 of 2 tokens.",
            Falha("consultora", CONTEXTO_CHEIO, sessao_nova=True),
        ),
        ("⚠️ This turn stopped making progress", Falha("tempo", DEMOROU)),
        ("⚠️ Turn aborted by the liveness watchdog", Falha("tempo", DEMOROU)),
        (
            "⚠️ Provider rate-limited: 429",
            Falha(
                "consultora",
                "Estou atendendo muita coisa ao mesmo tempo agora. Tente de novo daqui a pouco.",
            ),
        ),
        (
            "⚠️ Provider authentication failed: x",
            Falha(
                "consultora", "Estou sem acesso ao meu serviço agora. Tente de novo daqui a pouco."
            ),
        ),
        ("⚠️ No reply: the model provider didn't answer", Falha("consultora", SEM_RESPOSTA)),
        ("⚠️ **Thinking Budget Exhausted**", Falha("consultora", SEM_RESPOSTA)),
        ("⚠️ algo que ninguém previu", Falha("consultora", PROBLEMA)),
    ],
)
def test_aviso_em_ingles_vira_frase_para_ela(aviso: str, esperado: Falha) -> None:
    assert traduzir_aviso(aviso) == esperado


def test_texto_normal_nao_e_aviso() -> None:
    assert traduzir_aviso("Dá pra fazer, sim.") is None
    assert traduzir_aviso(None) is None
    assert traduzir_aviso("") is None


def test_nota_do_guard_rail_do_plugin_sai_inteira() -> None:
    especificacao = importlib.util.spec_from_file_location("guardrail_da_nota", PLUGIN)
    assert especificacao is not None and especificacao.loader is not None
    plugin = importlib.util.module_from_spec(especificacao)
    especificacao.loader.exec_module(plugin)
    for quantos in (1, 2):
        texto = "O prato sai [valor retirado]." + plugin.nota_rodape(quantos)
        assert sem_nota_do_guard_rail(texto) == "O prato sai [valor retirado]."
    antiga = (
        "O prato sai [valor retirado].\n\n---\nTirei 1 valor(es) desta resposta que eu não "
        "consegui conferir na conta do sistema. Me peça de novo que eu trago cada um com a conta "
        "aberta."
    )
    assert sem_nota_do_guard_rail(antiga) == "O prato sai [valor retirado]."
    assert sem_nota_do_guard_rail("Sem nota --- no meio.") == "Sem nota --- no meio."


def test_bastidor_e_recursos() -> None:
    assert de_bastidor("skill_view") and de_bastidor("todo_write") and de_bastidor("todo")
    assert not de_bastidor("web_search") and not de_bastidor("diagnostico_despensa")
    assert recursos_da_escrita("registrar_compra") == (
        "orcamento",
        "despensa",
        "receitas",
        "atividades",
    )
    assert recursos_da_escrita("registrar_algo_novo") == ("atividades",)
    assert recursos_da_escrita("atualizar_coisa") == ("atividades",)
    assert recursos_da_escrita("consultar_orcamento") == ()


def test_valores_do_motor_so_das_ferramentas_do_mise() -> None:
    mensagens = [
        {"role": "tool", "tool_name": "mcp__mise__calcular_cmv", "content": "R$ 2,47 e R$ 2,47"},
        {
            "role": "tool",
            "name": "mcp_mise_custo_unitario",
            "content": [{"text": "R$ 41,00/kg"}, 7],
        },
        {"role": "tool", "tool_name": "web_search", "content": "promoção R$ 3,99"},
        {"role": "tool", "tool_name": "mcp__mise__x", "content": None},
        {"role": "tool", "tool_name": "mcp__mise__y", "content": {"texto": "R$ 5,00"}},
        {"role": "assistant", "content": "R$ 99,00"},
        "lixo",
    ]
    assert valores_do_motor(mensagens) == (Decimal("2.47"), Decimal("41.00"), Decimal("5.00"))
    assert e_do_motor("mcp__mise__registrar_compra") and not e_do_motor(None)


@pytest.mark.parametrize(
    ("uso", "mensagens", "esperado"),
    [
        ({"input_tokens": 60_000}, [{"role": "assistant"}] * 3, 20_000),
        ({"input_tokens": 60_000}, [], 60_000),
        ({"input_tokens": 0}, [], 0),
        ({}, [], 0),
        (None, [], 0),
        ({"input_tokens": "muito"}, [], 0),
    ],
)
def test_estimativa_do_contexto(uso: Any, mensagens: list[Any], esperado: int) -> None:
    assert estimar_contexto(uso, mensagens) == esperado


# --------------------------------------------------------------------------- #
# O normalizador                                                               #
# --------------------------------------------------------------------------- #


async def test_rascunho_mascarado_e_raciocinio_descartado() -> None:
    tela = Tela()
    runs: list[str] = []
    normalizador = _normalizador(tela, runs=runs)
    for evento in (
        ev("run.started"),
        ev("assistant.delta", delta="Sai R$ 1"),
        ev("tool.progress", tool_name="_thinking", delta="R$ 12,50 de cabeça"),
        ev("assistant.delta", delta="2,50 a porção."),
        ev("assistant.delta", delta=""),
        ev("assistant.delta", delta=None),
        EventoSSE(nome="assistant.delta", dados="não é objeto"),
        ev("message.started"),
        ev("done"),
    ):
        await normalizador.processar(evento)
    assert runs == ["run_1"] and normalizador.run_id == "run_1"
    assert "".join(e["delta"] for e in tela.de("texto.parcial")) == f"Sai {SENTINELA} a porção."
    assert "12,50" not in str(tela.eventos)


async def test_cada_pedaco_do_hermes_sai_na_hora_sem_esperar_a_frase() -> None:
    """Nenhum buffer de frase ou de linha: o pedaço que chega é o pedaço que sai.

    O Hermes manda pedaços de 2 a 20 caracteres, às vezes dez no mesmo
    milissegundo. A tela é que dá o ritmo (letra a letra); o backend não segura
    nada além do fim que ainda pode virar dinheiro.
    """
    tela = Tela()
    normalizador = _normalizador(tela)
    pedacos = ["Olá", ", Dona", " Maria", "!", " Dá", " para fazer", " escondidinho", "\n\n- arroz"]
    for n, pedaco in enumerate(pedacos, start=1):
        await normalizador.processar(ev("assistant.delta", delta=pedaco))
        saiu = [e["delta"] for e in tela.de("texto.parcial")]
        assert len(saiu) == n, f"o pedaço {pedaco!r} ficou esperando"
        assert saiu[-1] == pedaco


async def test_valor_partido_so_sai_mascarado_e_o_resto_segue_na_hora() -> None:
    """O "R$ 6" num pedaço e o "6,39" no outro: nenhum dígito do valor aparece.

    Só o trecho que ainda pode virar valor fica retido, e só até o próximo
    pedaço dizer o que ele era; o texto antes dele já saiu.
    """
    tela = Tela()
    normalizador = _normalizador(tela)

    def na_tela() -> str:
        return "".join(e["delta"] for e in tela.de("texto.parcial"))

    await normalizador.processar(ev("assistant.delta", delta="A compra fica em R$ 6"))
    assert na_tela() == "A compra fica em "
    await normalizador.processar(ev("assistant.delta", delta="6,39 no total"))
    assert na_tela() == f"A compra fica em {SENTINELA} no total"
    await normalizador.processar(ev("assistant.delta", delta=", e sobram 4"))
    assert na_tela() == f"A compra fica em {SENTINELA} no total, e sobram "
    await normalizador.processar(ev("assistant.delta", delta=" reais."))
    assert na_tela() == f"A compra fica em {SENTINELA} no total, e sobram {SENTINELA}."
    assert not any(c.isdigit() for c in na_tela())


async def test_chamadas_em_paralelo_da_mesma_ferramenta() -> None:
    tela = Tela()
    normalizador = _normalizador(tela)
    for evento in (
        ev("tool.started", tool_name="web_search", args={"query": "bolo de fubá"}),
        ev("tool.started", tool_name="web_search", args={"query": "bolo de milho"}),
        ev("tool.completed", tool_name="web_search", args=None),
        ev("tool.failed", tool_name="web_search", args=None),
        ev("tool.completed", tool_name="web_search", args=None),  # sobrando: ignorado
        ev("tool.completed", tool_name="nunca_comecou"),
        ev("tool.started", args={}),  # sem nome: ignorado
    ):
        await normalizador.processar(evento)
    iniciadas = tela.de("atividade.iniciada")
    assert [a["rotulo"] for a in iniciadas] == [
        "pesquisando na internet: bolo de fubá",
        "pesquisando na internet: bolo de milho",
    ]
    assert [(c["atividade_id"], c["ok"]) for c in tela.de("atividade.concluida")] == [
        ("at-1", True),
        ("at-2", False),
    ]
    assert normalizador.atividades()[1]["ok"] is False


async def test_bastidor_some_da_linha_do_tempo() -> None:
    tela = Tela()
    normalizador = _normalizador(tela)
    for nome in ("skill_view", "tool_describe", "todo_write"):
        await normalizador.processar(ev("tool.started", tool_name=nome, args={"name": "x"}))
        await normalizador.processar(ev("tool.completed", tool_name=nome))
    assert tela.eventos == []


async def test_card_nao_se_repete_e_atualiza_com_o_mesmo_id() -> None:
    tela = Tela()
    montador = MontadorFalso([{"restante": 80}, {"restante": 80}, {"restante": 62}])
    normalizador = _normalizador(tela, montador)
    for _ in range(3):
        await normalizador.processar(ev("tool.started", tool_name="mcp__mise__consultar_orcamento"))
        await normalizador.processar(
            ev("tool.completed", tool_name="mcp__mise__consultar_orcamento")
        )
    cartoes = tela.de("cartao")
    assert [(c["cartao_id"], c["dados"]) for c in cartoes] == [
        ("k-1", {"restante": 80}),
        ("k-1", {"restante": 62}),
    ]
    assert cartoes[0]["gerado_texto"] == "conta de hoje, 14:30"
    assert "gerado" not in cartoes[0]
    assert [c["dados"] for c in normalizador.cartoes()] == [{"restante": 62}]


async def test_card_que_nao_resolve_ou_quebra_nao_derruba_nada() -> None:
    tela = Tela()
    normalizador = _normalizador(tela, MontadorFalso(erro=True))
    await normalizador.processar(ev("tool.started", tool_name="mcp__mise__consultar_orcamento"))
    await normalizador.processar(ev("tool.completed", tool_name="mcp__mise__consultar_orcamento"))
    await normalizador.processar(
        ev("tool.started", tool_name="mcp__mise__custo_unitario", args={"ingrediente": "sal"})
    )
    await normalizador.processar(ev("tool.completed", tool_name="mcp__mise__custo_unitario"))
    assert tela.de("cartao") == []
    assert tela.tipos().count("atividade.concluida") == 2
    sem_montador = _normalizador(Tela(), None)
    card: Cartao = {"tipo_cartao": "orcamento", "ref": {"rota": "/api/orcamento", "parametros": {}}}
    assert await sem_montador.montar_cartao(card) is None
    vazio = _normalizador(Tela(), MontadorFalso([None]))
    assert await vazio.montar_cartao(card) is None


async def test_comentario_do_meio_do_turno_nao_vai_para_a_tela() -> None:
    """O comentário é o agente narrando o trabalho: fica de fora, com ou sem valor."""
    tela = Tela()
    normalizador = _normalizador(tela)
    await normalizador.processar(
        ev("assistant.commentary", text="Custa uns R$ 9 por aí.", already_streamed=False)
    )
    await normalizador.processar(ev("assistant.commentary", text="   ", already_streamed=False))
    await normalizador.processar(ev("assistant.commentary", text="Já foi.", already_streamed=True))
    assert tela.de("texto.comentario") == []


async def _fim(normalizador: Normalizador, conteudo: str, status: str, **extra: Any) -> None:
    await normalizador.processar(ev("assistant.completed", content=conteudo, **extra))
    await normalizador.processar(ev(f"run.{status}", messages=[], usage={}, **extra))


async def test_texto_final_e_so_o_que_vem_depois_da_ultima_ferramenta() -> None:
    """O caso real: o turno começava com "Agora vou conferir se a cozinha dela dá conta"."""
    tela = Tela()
    normalizador = _normalizador(tela)
    narracao = "Agora vou conferir se a cozinha dela dá conta dessas três."
    await normalizador.processar(ev("assistant.delta", delta=narracao))
    await normalizador.processar(ev("assistant.commentary", text=narracao, already_streamed=True))
    await normalizador.processar(
        ev("tool.started", tool_name="mcp__mise__avaliar_receita", args={"receita_id": "a"})
    )
    await normalizador.processar(ev("tool.completed", tool_name="mcp__mise__avaliar_receita"))
    await normalizador.processar(ev("assistant.delta", delta="Pronto. Deu tudo certo."))
    await _fim(normalizador, "Pronto. Deu tudo certo.", "completed", session_id="api_2")
    desfecho = normalizador.concluir(set())
    assert desfecho.texto_final == "Pronto. Deu tudo certo."
    assert tela.de("texto.final")[0]["texto"] == "Pronto. Deu tudo certo."
    assert desfecho.rascunho == "Pronto. Deu tudo certo.", "o rascunho guardado também"
    assert (desfecho.estado, desfecho.sessao_id) == (EstadoDoTurno.CONCLUIDO, "api_2")


async def test_sem_texto_depois_da_ultima_ferramenta_vale_o_ultimo_comentario() -> None:
    tela = Tela()
    normalizador = _normalizador(tela)
    await normalizador.processar(
        ev("assistant.commentary", text="Vou olhar.", already_streamed=True)
    )
    await normalizador.processar(ev("tool.started", tool_name="mcp__mise__registrar_gosto"))
    await normalizador.processar(ev("tool.completed", tool_name="mcp__mise__registrar_gosto"))
    await normalizador.processar(
        ev("assistant.commentary", text="Anotei.  ", already_streamed=False)
    )
    await normalizador.processar(ev("assistant.commentary", text="  ", already_streamed=False))
    await _fim(normalizador, "", "completed")
    assert normalizador.concluir(set()).texto_final == "Anotei."


async def test_o_valor_retido_sai_antes_da_ferramenta_e_o_rascunho_recomeca() -> None:
    """O trecho antes da ferramenta sai inteiro (mascarado), e o guardado é só o depois."""
    tela = Tela()
    normalizador = _normalizador(tela)
    await normalizador.processar(ev("assistant.delta", delta="Custa R$ 12"))
    await normalizador.processar(ev("tool.started", tool_name="mcp__mise__custo_unitario"))
    assert SENTINELA in "".join(e["delta"] for e in tela.de("texto.parcial"))
    await normalizador.processar(ev("tool.completed", tool_name="mcp__mise__custo_unitario"))
    await normalizador.processar(ev("assistant.delta", delta="Conferi."))
    desfecho = normalizador.concluir(set(), falha=Falha("rede", "caiu"))
    assert (desfecho.texto_final, desfecho.rascunho) == (None, "Conferi.")


async def test_chamada_que_nunca_terminou_fecha_como_falha() -> None:
    tela = Tela()
    normalizador = _normalizador(tela)
    await normalizador.processar(ev("tool.started", tool_name="web_search", args={"query": "x"}))
    await normalizador.processar(ev("tool.started", tool_name="skill_view"))
    desfecho = normalizador.concluir(set(), falha=Falha("rede", "caiu"))
    assert tela.de("atividade.concluida") == [
        {"tipo": "atividade.concluida", "atividade_id": "at-1", "ok": False}
    ]
    assert (desfecho.estado, desfecho.texto_final) == (EstadoDoTurno.FALHOU, None)
    assert desfecho.falha == Falha("rede", "caiu")


@pytest.mark.parametrize(
    ("conteudo", "status", "extra", "estado", "falha"),
    [
        ("", "cancelled", {}, EstadoDoTurno.CANCELADO, None),
        ("Parei.", "completed", {"interrupted": True}, EstadoDoTurno.CANCELADO, None),
        (
            "Resposta pela metade",
            "failed",
            {},
            EstadoDoTurno.FALHOU,
            Falha("consultora", SEM_RESPOSTA),
        ),
        (
            "⚠️ safety filter refused",
            "failed",
            {},
            EstadoDoTurno.FALHOU,
            Falha("consultora", RECUSA),
        ),
        ("   ", "completed", {}, EstadoDoTurno.FALHOU, Falha("consultora", SEM_RESPOSTA)),
    ],
)
async def test_como_o_turno_termina(
    conteudo: str, status: str, extra: dict[str, Any], estado: EstadoDoTurno, falha: Falha | None
) -> None:
    tela = Tela()
    normalizador = _normalizador(tela)
    await _fim(normalizador, conteudo, status, **extra)
    desfecho = normalizador.concluir(set())
    assert (desfecho.estado, desfecho.falha) == (estado, falha)
    assert "texto.final" not in tela.tipos()


async def test_erro_do_hermes_e_pedido_de_parar() -> None:
    normalizador = _normalizador(Tela())
    await normalizador.processar(ev("error", message=None))
    assert normalizador.concluir(set()).falha == Falha("consultora", PROBLEMA)
    parado = _normalizador(Tela())
    assert parado.concluir(set(), cancelado=True).estado is EstadoDoTurno.CANCELADO


async def test_texto_final_conferido_com_o_que_ja_tinha_procedencia() -> None:
    tela = Tela()
    normalizador = _normalizador(tela)
    await normalizador.processar(ev("assistant.completed", content="Fica R$ 18,00 e R$ 3,00."))
    await normalizador.processar(
        ev(
            "run.completed",
            messages=[
                {"role": "tool", "tool_name": "mcp__mise__cenarios_preco", "content": "R$ 3,00"}
            ],
            usage={"input_tokens": 9000},
        )
    )
    desfecho = normalizador.concluir({Decimal("18")})
    assert (desfecho.texto_final, desfecho.retirados) == ("Fica R$ 18,00 e R$ 3,00.", 0)
    assert desfecho.valores_do_motor == (Decimal("3.00"),)
    assert desfecho.tokens_de_contexto == 9000
    assert tela.de("texto.final") == [
        {"tipo": "texto.final", "texto": "Fica R$ 18,00 e R$ 3,00.", "retirados": 0}
    ]
    assert "sugestoes" not in tela.tipos(), "sem card, sem sugestão"


async def test_alterou_sem_recurso_nao_emite() -> None:
    tela = Tela()
    normalizador = _normalizador(tela)
    normalizador.alterou([])
    normalizador.alterou(["receitas", "perfil", "receitas"])
    assert tela.eventos == [{"tipo": "estado.alterado", "recursos": ["perfil", "receitas"]}]
