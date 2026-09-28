"""Rastreamento distribuído da execução do agente.

A pergunta que um trace responde é a única que importa quando algo demora oito
segundos: **onde foram os oito segundos?** Sem trace, a resposta é "o LLM está
lento", que costuma estar errada: na maioria dos agentes o tempo está numa
ferramenta, numa consulta ou numa fila.

A instrumentação usa a **API** do OpenTelemetry, não o SDK. A diferença importa:
a API é um no-op quando não há SDK configurado, então o código instrumentado
roda igual em quem só quer usar o agente e em quem quer exportar para um coletor.
Quem quiser Langfuse, Jaeger, Grafana ou o que for, configura o SDK e o exporta
por OTLP sem tocar em nenhuma linha daqui.

Os nomes de span e atributo seguem a convenção `gen_ai.*` das convenções
semânticas do OpenTelemetry, para que um coletor genérico entenda sem tradução.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

#: Nome do serviço nos traces. Sem isto tudo vira "unknown_service".
SERVICO = "sabor-da-maria"

_rastreador = trace.get_tracer(SERVICO)


def configurar(exportar: bool | None = None) -> bool:
    """Liga o SDK, se ele existir e se for pedido.

    Devolve se o SDK foi configurado. Sem SDK a instrumentação continua no lugar
    e não custa nada: é essa a razão de instrumentar com a API.

    `MISE_OTEL=1` liga. O padrão é desligado de propósito: quem clona o
    repositório para avaliar não deveria precisar de um coletor rodando.
    """
    if exportar is None:
        exportar = os.environ.get("MISE_OTEL", "").strip() in {"1", "true", "sim"}
    if not exportar:
        return False

    try:
        from opentelemetry.sdk.resources import Resource  # noqa: PLC0415
        from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
        from opentelemetry.sdk.trace.export import (  # noqa: PLC0415
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )
    except ImportError:
        # Sem SDK, seguir sem trace é melhor do que não subir. A instrumentação
        # continua lá e volta a produzir dado no dia em que o SDK aparecer.
        return False

    provedor = TracerProvider(resource=Resource.create({"service.name": SERVICO}))

    destino = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if destino:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # noqa: PLC0415
                OTLPSpanExporter,
            )

            provedor.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        except ImportError:
            provedor.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        provedor.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provedor)
    return True


@contextmanager
def span_de_ferramenta(nome: str, identidade: str = "") -> Iterator[Span]:
    """Uma chamada de ferramenta do agente.

    O atributo que mais importa aqui é o nome da ferramenta: é por ele que se
    descobre que 80% da latência está num lugar só.
    """
    with _rastreador.start_as_current_span(f"ferramenta {nome}") as span:
        span.set_attribute("gen_ai.operation.name", "execute_tool")
        span.set_attribute("gen_ai.tool.name", nome)
        if identidade:
            span.set_attribute("enduser.id", identidade)
        try:
            yield span
        except Exception as erro:
            span.set_status(Status(StatusCode.ERROR, str(erro)))
            span.record_exception(erro)
            raise


@contextmanager
def span_de_modelo(modelo: str, operacao: str = "chat") -> Iterator[Span]:
    """Uma chamada ao modelo, com os atributos que a convenção `gen_ai` define."""
    with _rastreador.start_as_current_span(f"modelo {modelo}") as span:
        span.set_attribute("gen_ai.operation.name", operacao)
        span.set_attribute("gen_ai.request.model", modelo)
        span.set_attribute("gen_ai.system", "anthropic")
        yield span


def registrar_uso(span: Span, entrada: int, saida: int, custo_usd: float) -> None:
    """Anota consumo no span da chamada ao modelo.

    Token e custo no **span**, e não só num contador agregado, é o que permite
    responder "qual pergunta dela custou caro?" em vez de só "quanto gastamos
    hoje".
    """
    span.set_attribute("gen_ai.usage.input_tokens", entrada)
    span.set_attribute("gen_ai.usage.output_tokens", saida)
    span.set_attribute("gen_ai.usage.total_tokens", entrada + saida)
    span.set_attribute("custo.usd", custo_usd)


@contextmanager
def span_de_rota(metodo: str, rota: str) -> Iterator[Span]:
    """Uma requisição HTTP à API do motor.

    Existe separado de `span_de_ferramenta` porque são pontos de entrada
    diferentes: o MCP é o agente pedindo, o HTTP é a interface pedindo. Misturar
    os dois numa métrica só esconderia qual dos caminhos está lento.
    """
    with _rastreador.start_as_current_span(f"{metodo} {rota}") as span:
        span.set_attribute("http.request.method", metodo)
        span.set_attribute("http.route", rota)
        try:
            yield span
        except Exception as erro:
            span.set_status(Status(StatusCode.ERROR, str(erro)))
            span.record_exception(erro)
            raise


@contextmanager
def span_de_busca(consulta: str, estrategia: str) -> Iterator[Span]:
    """Uma recuperação. `estrategia` distingue lexical, vetorial e fusão."""
    with _rastreador.start_as_current_span(f"busca {estrategia}") as span:
        span.set_attribute("retrieval.query", consulta[:200])
        span.set_attribute("retrieval.strategy", estrategia)
        yield span


def identificador_do_trace() -> str:
    """O `trace_id` atual em hexadecimal, ou vazio fora de um trace.

    Vai no envelope de erro da API: é o que transforma "deu errado" num chamado
    que alguém consegue investigar.
    """
    contexto = trace.get_current_span().get_span_context()
    if not contexto.is_valid:
        return ""
    return format(contexto.trace_id, "032x")


def anotar(**atributos: Any) -> None:
    """Acrescenta atributos ao span atual, se houver um."""
    span = trace.get_current_span()
    if span.get_span_context().is_valid:
        for chave, valor in atributos.items():
            span.set_attribute(chave, valor)


__all__ = [
    "SERVICO",
    "anotar",
    "configurar",
    "identificador_do_trace",
    "registrar_uso",
    "span_de_busca",
    "span_de_ferramenta",
    "span_de_modelo",
    "span_de_rota",
]
