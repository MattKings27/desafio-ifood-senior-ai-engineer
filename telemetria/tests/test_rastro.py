"""Instrumentação com a API do OpenTelemetry.

A propriedade que estes testes protegem é a razão de instrumentar com a **API** e
não com o SDK: o código instrumentado tem que rodar igual em quem só quer usar o
agente e em quem quer exportar para um coletor. Se a instrumentação quebrar sem
SDK, ela vira uma dependência disfarçada.
"""

from __future__ import annotations

import pytest

from telemetria import rastro


def test_instrumentacao_nao_quebra_sem_sdk() -> None:
    """A API é um no-op sem SDK, e isso é o comportamento pretendido."""
    with rastro.span_de_ferramenta("custo_unitario", "dona-maria") as span:
        span.set_attribute("teste", 1)
        rastro.anotar(outro=2)
    # Chegar aqui sem exceção é o teste.


def test_trace_id_vazio_fora_de_um_trace() -> None:
    assert rastro.identificador_do_trace() == ""


def test_span_de_ferramenta_propaga_excecao() -> None:
    """Engolir a exceção para "não quebrar o trace" esconderia o erro real."""
    with pytest.raises(ValueError, match="explodiu"), rastro.span_de_ferramenta("x"):
        raise ValueError("explodiu")


def test_span_de_rota_propaga_excecao() -> None:
    with pytest.raises(RuntimeError), rastro.span_de_rota("GET", "/api/x"):
        raise RuntimeError


def test_configurar_desligado_devolve_falso() -> None:
    assert rastro.configurar(exportar=False) is False


def test_variavel_de_ambiente_controla(monkeypatch) -> None:
    monkeypatch.delenv("MISE_OTEL", raising=False)
    assert rastro.configurar() is False

    monkeypatch.setenv("MISE_OTEL", "nao-e-um-sim")
    assert rastro.configurar() is False


@pytest.mark.parametrize("valor", ["1", "true", "sim"])
def test_valores_que_ligam(monkeypatch, valor: str) -> None:
    from opentelemetry import trace

    instalados = []
    monkeypatch.setattr(trace, "set_tracer_provider", instalados.append)
    monkeypatch.setenv("MISE_OTEL", valor)
    # Devolve True porque o SDK está nas dependências de desenvolvimento.
    assert rastro.configurar() is True
    # Desligado aqui, e não no fim do processo: o exportador de console
    # escreveria no stdout do pytest, que já estaria fechado.
    (provedor,) = instalados
    provedor.shutdown()


def test_span_de_modelo_e_de_busca_nao_quebram() -> None:
    with rastro.span_de_modelo("claude-opus-5") as s:
        rastro.registrar_uso(s, 100, 50, 0.001)
    with rastro.span_de_busca("farinha de trigo", "hibrida"):
        pass


def test_anotar_fora_de_span_nao_quebra() -> None:
    rastro.anotar(qualquer="coisa")


# --------------------------------------------------------------------------- #
# Com o SDK ligado                                                             #
# --------------------------------------------------------------------------- #


@pytest.fixture
def com_sdk(monkeypatch):
    """Liga o SDK e devolve o provedor, para inspecionar os spans produzidos."""
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exportador = InMemorySpanExporter()
    provedor = TracerProvider(resource=Resource.create({"service.name": rastro.SERVICO}))
    provedor.add_span_processor(SimpleSpanProcessor(exportador))

    # `set_tracer_provider` é uma vez só por processo; trocar o tracer do módulo
    # é o caminho que funciona em teste sem poluir os outros.
    monkeypatch.setattr(rastro, "_rastreador", provedor.get_tracer(rastro.SERVICO))
    return exportador


@pytest.mark.usefixtures("com_sdk")
def test_trace_id_existe_dentro_de_um_span() -> None:
    """É ele que vai no cabeçalho da resposta e transforma erro em chamado."""
    with rastro.span_de_ferramenta("calcular_cmv"):
        identificador = rastro.identificador_do_trace()

    assert len(identificador) == 32
    assert int(identificador, 16) > 0


def test_atributos_seguem_a_convencao_gen_ai(com_sdk) -> None:
    """Um coletor genérico entende `gen_ai.*` sem tradução."""
    with rastro.span_de_modelo("claude-opus-5") as s:
        rastro.registrar_uso(s, 12000, 800, 0.2505)

    (span,) = com_sdk.get_finished_spans()
    assert span.attributes["gen_ai.request.model"] == "claude-opus-5"
    assert span.attributes["gen_ai.usage.input_tokens"] == 12000
    assert span.attributes["gen_ai.usage.output_tokens"] == 800
    assert span.attributes["gen_ai.usage.total_tokens"] == 12800
    assert span.attributes["custo.usd"] == pytest.approx(0.2505)


def test_span_aninhado_compartilha_o_trace(com_sdk) -> None:
    """É isso que permite responder "onde foram os oito segundos"."""
    with rastro.span_de_ferramenta("avaliar_receita"), rastro.span_de_busca("arroz", "bm25"):
        pass

    spans = com_sdk.get_finished_spans()
    assert len({s.context.trace_id for s in spans}) == 1
    assert {s.name for s in spans} == {"ferramenta avaliar_receita", "busca bm25"}


def test_anotar_acrescenta_ao_span_atual(com_sdk) -> None:
    with rastro.span_de_ferramenta("x"):
        rastro.anotar(prato="Frango à parmegiana")

    (span,) = com_sdk.get_finished_spans()
    assert span.attributes["prato"] == "Frango à parmegiana"


def test_erro_marca_o_span(com_sdk) -> None:
    from opentelemetry.trace import StatusCode

    with pytest.raises(ValueError, match="motivo"), rastro.span_de_ferramenta("quebra"):
        raise ValueError("motivo")

    (span,) = com_sdk.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR
    assert span.events  # a exceção foi registrada


def test_sem_sdk_instalado_segue_sem_trace(monkeypatch) -> None:
    """Seguir sem trace é melhor do que não subir."""
    import builtins

    original = builtins.__import__

    def recusar(nome: str, *resto, **chaves):
        if nome.startswith("opentelemetry.sdk"):
            raise ImportError(nome)
        return original(nome, *resto, **chaves)

    monkeypatch.setattr(builtins, "__import__", recusar)
    assert rastro.configurar(exportar=True) is False


def test_endpoint_otlp_usa_o_exportador_http(monkeypatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://coletor.invalido:4318")
    assert rastro.configurar(exportar=True) is True
